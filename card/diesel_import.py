# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Import of reviewed diesel sessions (FR-086, Owner 2026-10-26): the WhatsApp sessions prepared and
checked off the site become draft Project Diesel Fills with their meter photos as private files.

Run by a manager on the server, e.g.
	bench --site <site> execute card.diesel_import.import_sessions \
		--kwargs "{'manifest': '/path/sessions.json', 'photos_dir': '/path/photos', 'dry_run': 1}"

Rules: one fill per source key (a re-run skips what exists, in any state); photos must match the
SHA-256 in the manifest; the price is always the company price (a session at another price is
refused); the import never approves, submits or posts. The fill's own validation (readings,
photos, duplicate photos, totalizer, review) applies to every row."""

import hashlib
import json
import mimetypes
import os

import frappe
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import flt
from frappe.utils.image import strip_exif_data

from card.card.doctype.project_diesel_fill.project_diesel_fill import REJECTED, REVIEW_ROLES, diesel_price

DOCTYPE = "Project Diesel Fill"
CREATED, EXISTING, WOULD_CREATE, ERROR = "Created", "Existing", "Would Create", "Error"
SAVEPOINT = "card_diesel_import"
FIELDS = ("company", "project", "supplier", "date", "cost_center", "photo_location", "remarks")


def import_sessions(manifest, photos_dir, dry_run=1):
	"""Create draft fills from `manifest` (a JSON list of sessions). Returns one result per session.
	With dry_run (the default) nothing is kept and no file is written. bench execute commits once at the
	end of the run; a run that stops keeps nothing, and a re-run of the same manifest is safe (existing
	keys are skipped), so runs go in small batches."""
	if not set(REVIEW_ROLES) & set(frappe.get_roles()):
		frappe.throw(
			_("Only a Card Manager or System Manager can import diesel sessions."), frappe.PermissionError
		)
	frappe.has_permission(DOCTYPE, "create", throw=True)
	# audited (FR-086 security review): the manifest path is given by the bench operator, not a web user
	with open(manifest, encoding="utf-8") as f:  # nosemgrep
		sessions = json.load(f)
	results, seen = [], set()  # seen: stored photo hashes of this run's dry-run sessions
	for session in sessions:
		results.append(_import_one(session, photos_dir, int(dry_run), seen))
	summary = {}
	for row in results:
		summary[row["result"]] = summary.get(row["result"], 0) + 1
	return {"dry_run": int(dry_run), "summary": summary, "results": results}


def _import_one(session, photos_dir, dry_run, seen):
	key = session.get("source_key")
	result = {"source_key": key, "result": ERROR, "name": None, "error": None}
	files = []
	frappe.db.savepoint(SAVEPOINT)
	try:
		if not key:
			frappe.throw(_("The session has no source key."))
		existing = frappe.db.get_value(DOCTYPE, {"source_key": key}, "name")
		if existing:
			result.update(result=EXISTING, name=existing)
			return result
		photos = {side: _read_photo(session.get(side), photos_dir) for side in ("opening", "closing")}
		if not photos["closing"]:
			frappe.throw(_("The session has no closing meter photo."))
		_check_price(session)
		doc = _new_fill(session)
		doc.insert()
		if dry_run:
			_check_unused(photos, seen)
			frappe.db.rollback(save_point=SAVEPOINT)
			result.update(result=WOULD_CREATE, litres=doc.litres, review_status=doc.review_status)
			return result
		for side, photo in photos.items():
			if photo:
				files.append(_attach(doc, side, photo))
				doc.set(f"{side}_photo", files[-1].file_url)
		doc.save()
		result.update(
			result=CREATED,
			name=doc.name,
			litres=doc.litres,
			review_status=doc.review_status,
			totalizer_check=doc.totalizer_check,
			files=len(files),
		)
	except Exception as e:
		frappe.db.rollback(save_point=SAVEPOINT)
		_remove_files(files)
		frappe.clear_messages()
		result["error"] = str(e)
	return result


def _read_photo(side, photos_dir):
	"""The photo bytes of one side of the session, checked against the manifest hash."""
	if not side or not side.get("photo"):
		return None
	name = side["photo"]
	if os.path.basename(name) != name or name in (".", ".."):
		frappe.throw(_("Invalid photo name {0}.").format(name))
	# audited (FR-086 security review): photos_dir comes from the bench operator; name is a bare file name
	with open(os.path.join(photos_dir, name), "rb") as f:  # nosemgrep
		content = f.read()
	if hashlib.sha256(content).hexdigest() != side.get("sha256"):
		frappe.throw(_("Photo {0} does not match its SHA-256 in the manifest.").format(name))
	return {**side, "name": name, "content": content}


def _check_price(session):
	if not session.get("unit_price"):
		frappe.throw(_("The session has no unit price."))
	price = flt(session.get("unit_price"))
	company_price = flt(diesel_price(session.get("company")))
	if price != company_price:
		frappe.throw(
			_(
				"The session price {0} is not the company price {1}; import it at the company price only."
			).format(price, company_price)
		)


def _new_fill(session):
	doc = frappe.new_doc(DOCTYPE)
	doc.flags.diesel_import = True  # the source fields may be set (ProjectDieselFill._guard_source)
	doc.update({field: session.get(field) for field in FIELDS if session.get(field)})
	for side in ("opening", "closing"):
		data = session.get(side) or {}
		doc.set(f"{side}_reading", flt(data.get("reading")))
		doc.set(f"{side}_totalizer", data.get("totalizer"))
		doc.set(f"{side}_photo_time", data.get("time"))
	doc.litres = flt(doc.closing_reading) - flt(doc.opening_reading)
	doc.source_key = session["source_key"]
	# the original WhatsApp photo hashes: Frappe may strip EXIF on upload, so the stored file can differ
	photos = [
		f"{side} photo {data['photo']} SHA-256 {data['sha256']}"
		for side, data in ((side, session.get(side)) for side in ("opening", "closing"))
		if data and data.get("photo")
	]
	doc.source_messages = "\n".join((session.get("messages") or []) + photos) or None
	doc.source_caption = session.get("caption")
	doc.review_notes = session.get("review_notes")
	for row in session.get("equipment") or []:
		# names as reported only: no equipment is chosen and no litres are split (Owner 2026-10-26)
		doc.append(
			"equipment_filled",
			{
				"reported_name": row[:140],
				"match_status": "Unmatched",
				"notes": row if len(row) > 140 else None,
			},
		)
	return doc


def _stored_hash(photo):
	"""The content hash Frappe will store for the photo (File.save_file strips EXIF from JPEGs when
	the system setting is on)."""
	content = photo["content"]
	content_type = mimetypes.guess_type(photo["name"])[0]
	if content_type == "image/jpeg" and frappe.get_system_settings(
		"strip_exif_metadata_from_uploaded_images"
	):
		content = strip_exif_data(content, content_type)
	return get_content_hash(content)


def _check_unused(photos, seen):
	"""Dry run: the duplicate-photo rule of the fill (live fills only; a rejected or cancelled fill
	does not hold its photo), also across the sessions of this run, without writing a file."""
	hashes = [_stored_hash(photo) for photo in photos.values() if photo]
	if len(hashes) != len(set(hashes)):
		frappe.throw(_("The opening and closing meter photos are the same file."))
	for photo_hash in hashes:
		urls = frappe.get_all("File", filters={"content_hash": photo_hash}, pluck="file_url")
		used = urls and frappe.get_all(
			DOCTYPE,
			filters={"docstatus": ["<", 2], "review_status": ["!=", REJECTED]},
			or_filters={"opening_photo": ["in", urls], "closing_photo": ["in", urls]},
			pluck="name",
			limit=1,
		)
		if used or photo_hash in seen:
			frappe.throw(_("A meter photo of this session is already used by another diesel fill."))
	seen.update(hashes)


def _attach(doc, side, photo):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": photo["name"],
			"is_private": 1,
			"content": photo["content"],
			"attached_to_doctype": DOCTYPE,
			"attached_to_name": doc.name,
			"attached_to_field": f"{side}_photo",
		}
	).insert()


def _remove_files(files):
	"""Files written for a failed session: their rows were rolled back, the disk copies were not."""
	for file in files:
		if not frappe.db.exists("File", {"file_url": file.file_url}):
			path = file.get_full_path()
			if os.path.exists(path):
				os.remove(path)
