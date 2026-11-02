# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""One validator for the files users attach to CARD records (H-CARD-1, H-CARD-2).

Frappe's File upload accepts any bytes under any name. CARD evidence (meter photos, custody receipts,
fitment evidence, transport authorization documents, equipment documents) is photos and scans, so:

* `check_attachment_content` - the stored file is a JPEG, PNG, WebP or PDF (by its own bytes, not only
  its name), within the size cap, and an image decodes. Callers run it AFTER their own "which record
  does this file belong to" check, and only when the field is new or changed, so evidence saved
  earlier stays valid.
* `require_record_file` - the file is private and attached to this record (or is the uploader's own
  unattached or unsaved-form upload, which the record then claims).

Pillow is used for the decode check (a Frappe dependency; Frappe itself opens images on upload)."""

import io

import frappe
from frappe import _
from frappe.utils import cint, cstr

MAX_BYTES = 10 * 1024 * 1024  # 10 MB: a phone photo or a multi-page scan
# 50 Mpx: covers the 48/50 MP phone cameras; a flat PNG can reach 100+ Mpx in 140 KB
MAX_PIXELS = 50_000_000
PRIVATE_PREFIX = "/private/files/"

# kind -> (file name extensions, PIL format names). Many phones save a JPEG that Pillow reports as "MPO"
# (multi-picture JPEG); it is a normal JPEG for our purpose. HEIC is not supported (Pillow has no decoder).
KINDS = {
	"jpeg": ((".jpg", ".jpeg"), ("JPEG", "MPO")),
	"png": ((".png",), ("PNG",)),
	"webp": ((".webp",), ("WEBP",)),
	"pdf": ((".pdf",), ()),
}


def detect_kind(content: bytes) -> str | None:
	"""The file type named by the content's own signature, or None."""
	if content.startswith(b"\xff\xd8\xff"):
		return "jpeg"
	if content.startswith(b"\x89PNG\r\n\x1a\n"):
		return "png"
	if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
		return "webp"
	if content.startswith(b"%PDF-"):
		return "pdf"
	return None


def check_content(content: bytes, file_name: str = "", kinds=tuple(KINDS)) -> str:
	"""Throw unless `content` is an allowed, intact file whose name agrees with its type; returns the kind.
	`kinds` narrows the allowlist (an image field passes ("jpeg", "png", "webp"))."""
	if not content:
		frappe.throw(_("The attached file is empty."))
	if len(content) > MAX_BYTES:
		frappe.throw(_("The attached file is larger than {0} MB.").format(MAX_BYTES // (1024 * 1024)))
	kind = detect_kind(content)
	if not kind or kind not in kinds:
		if "pdf" in kinds:
			frappe.throw(_("Attach a JPEG, PNG, WebP or PDF file."))
		frappe.throw(_("Attach a JPEG, PNG or WebP image."))
	name = cstr(file_name).lower()
	if name and not name.endswith(KINDS[kind][0]):
		frappe.throw(_("The file name does not match its content. Attach a JPEG, PNG, WebP or PDF file."))
	if kind == "pdf":
		# trailing NUL / whitespace padding is common; the end marker may sit up to 64 KB from the real end
		if b"%%EOF" not in content.rstrip(b"\x00 \t\r\n\f")[-65536:]:
			frappe.throw(_("The PDF file is incomplete or damaged."))
		return kind
	_check_image(content, KINDS[kind][1])
	return kind


def _check_image(content: bytes, expected_formats: tuple):
	import warnings

	from PIL import Image

	too_big = False
	try:
		# a small file can describe a huge image (decompression bomb): the pixel count is read from the
		# header and capped BEFORE decoding, and Pillow's own bomb warning is an error here
		with warnings.catch_warnings():
			warnings.simplefilter("error", Image.DecompressionBombWarning)
			with Image.open(io.BytesIO(content)) as image:
				actual = image.format
				if image.size[0] * image.size[1] > MAX_PIXELS:
					too_big = True
				else:
					image.load()  # decodes every pixel: a truncated or crafted file fails here
	except (Image.DecompressionBombWarning, Image.DecompressionBombError):
		too_big = True
	except Exception:
		frappe.throw(_("The image file is damaged or cannot be read."))
	if too_big:
		frappe.throw(
			_("The image has too many pixels (more than {0} megapixels).").format(MAX_PIXELS // 1_000_000)
		)
	if actual not in expected_formats:
		frappe.throw(_("The file name does not match its content. Attach a JPEG, PNG, WebP or PDF file."))


IMAGE_KINDS = ("jpeg", "png", "webp")


def check_attachment_content(file_url: str, kinds=tuple(KINDS), file_row: str | None = None):
	"""Validate the content behind a File url (private files only). The caller has already decided that
	the file may be used on its record; pass the File row it accepted as `file_row` so that row (and its
	file name) is the one checked."""
	filters = {"file_url": file_url, "is_folder": 0}
	if file_row:
		filters["name"] = file_row
	if not cstr(file_url).startswith(PRIVATE_PREFIX):
		frappe.throw(_("Attach a private file uploaded to this record."))
	rows = frappe.get_all(
		"File",
		filters=filters,
		fields=["name", "file_name", "file_size"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		frappe.throw(_("The attached file was not found."))
	row = rows[0]
	if cint(row.file_size) > MAX_BYTES:
		frappe.throw(_("The attached file is larger than {0} MB.").format(MAX_BYTES // (1024 * 1024)))
	try:
		# the RAW bytes through the official File API: get_content(encodings=()) skips the text-decoding loop (a photo must not
		# come back as a decoded str, which would corrupt it) and resolves the path with get_full_path + is_safe_path
		content = frappe.get_doc("File", row.name).get_content(encodings=())
		if not isinstance(content, bytes):
			raise ValueError("not bytes")
	except Exception:
		frappe.throw(_("The attached file could not be read."))
	check_content(content, row.file_name or file_url, kinds)


def require_record_file(
	file_url: str,
	doctype: str,
	name: str | None,
	temporary: str | None = None,
	attached_only: bool = False,
) -> str:
	"""Throw unless `file_url` is a private file of this record; returns the File row name to use.

	Accepted rows: attached to this record; an upload on this record's unsaved form (attached to
	`temporary`, only the session user's own); an unattached upload of the session user (not with
	`attached_only`). Public files and files of other records are refused, and a row of another record
	is never claimed."""
	if not cstr(file_url).startswith(PRIVATE_PREFIX):
		frappe.throw(_("Attach a private file uploaded to this record."))
	user = frappe.session.user
	rows = frappe.get_all(
		"File",
		filters={"file_url": file_url, "is_private": 1, "is_folder": 0},
		fields=["name", "attached_to_doctype", "attached_to_name", "owner"],
	)
	for row in rows:
		if name and (row.attached_to_doctype, row.attached_to_name) == (doctype, name):
			return row.name
		if (
			temporary
			and (row.attached_to_doctype, row.attached_to_name) == (doctype, temporary)
			and row.owner == user
		):
			return row.name
		if not attached_only and not row.attached_to_doctype and row.owner == user:
			return row.name
	frappe.throw(_("Attach a private file uploaded to this record."))


def claim_file(file_row: str, doctype: str, name: str, fieldname: str):
	"""Attach an unattached File row to the record that uses it (rows already attached are left as they are)."""
	# security: db.set_value skips File permissions and hooks, so only a row that is unattached AND owned
	# by the session user is written (require_record_file returns such rows or rows of this record only)
	current = frappe.db.get_value("File", file_row, ["attached_to_doctype", "owner"], as_dict=True)
	if current and not current.attached_to_doctype and current.owner == frappe.session.user:
		frappe.db.set_value(
			"File",
			file_row,
			{"attached_to_doctype": doctype, "attached_to_name": name, "attached_to_field": fieldname},
			update_modified=False,
		)


def new_form_prefix(doctype: str) -> str:
	"""Prefix of the temporary name the Desk gives an unsaved form of `doctype`."""
	return "new-" + frappe.scrub(doctype).replace("_", "-") + "-"
