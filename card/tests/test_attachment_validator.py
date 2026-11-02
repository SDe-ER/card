# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""H-CARD-1 / H-CARD-2: the shared attachment validator and its use on Card Equipment and Equipment Transport."""

import json
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from card.attachment_validator import (
	IMAGE_KINDS,
	MAX_BYTES,
	check_attachment_content,
	check_content,
	claim_file,
	detect_kind,
	require_record_file,
)
from card.tests.sample_files import pdf, png


class TestCheckContent(IntegrationTestCase):
	def test_allowed_types_pass(self):
		self.assertEqual(check_content(png("a"), "x.png"), "png")
		self.assertEqual(check_content(pdf("a"), "x.PDF"), "pdf")
		self.assertEqual(detect_kind(b"RIFF\0\0\0\0WEBPVP8 "), "webp")
		self.assertEqual(detect_kind(b"\xff\xd8\xff\xe0"), "jpeg")

	def test_refused_content(self):
		for content, name in (
			(b"", "x.png"),
			(b"just text", "x.txt"),
			(b"<html><script>1</script></html>", "x.png"),
			(b"MZ\x90\x00", "x.pdf"),
		):
			with self.assertRaises(frappe.ValidationError, msg=name):
				check_content(content, name)

	def test_name_must_match_content(self):
		with self.assertRaises(frappe.ValidationError):
			check_content(png("a"), "x.pdf")
		with self.assertRaises(frappe.ValidationError):
			check_content(pdf("a"), "x.png")

	def test_size_cap(self):
		with self.assertRaises(frappe.ValidationError):
			check_content(pdf("a") + b" " * MAX_BYTES, "x.pdf")

	def test_damaged_image_and_pdf(self):
		with self.assertRaises(frappe.ValidationError):
			check_content(png("a")[:40], "x.png")  # truncated: signature ok, decode fails
		with self.assertRaises(frappe.ValidationError):
			check_content(b"%PDF-1.4 no end", "x.pdf")

	def test_decompression_bomb_is_refused_before_decoding(self):
		"""F-1: a flat 12000x12000 PNG is about 140 KB and 144 Mpx; it is refused by the pixel cap."""
		import io

		from PIL import Image

		buffer = io.BytesIO()
		Image.new("L", (12000, 12000)).save(buffer, "PNG", optimize=False)
		self.assertLess(len(buffer.getvalue()), MAX_BYTES)
		with self.assertRaises(frappe.ValidationError):
			check_content(buffer.getvalue(), "bomb.png")
		# a 48 MP phone photo is still accepted
		small = io.BytesIO()
		Image.new("L", (8000, 6000)).save(small, "PNG")  # 48 Mpx
		self.assertEqual(check_content(small.getvalue(), "ok.png"), "png")

	def test_mpo_phone_jpeg_is_accepted(self):
		"""T0029 (1): Pillow reports many phone JPEGs as MPO."""
		import io

		from PIL import Image

		first, second = Image.new("RGB", (16, 16), (200, 10, 10)), Image.new("RGB", (16, 16), (10, 200, 10))
		buffer = io.BytesIO()
		first.save(buffer, "MPO", save_all=True, append_images=[second])
		self.assertEqual(Image.open(io.BytesIO(buffer.getvalue())).format, "MPO")
		self.assertEqual(check_content(buffer.getvalue(), "IMG_0001.jpg", ("jpeg", "png", "webp")), "jpeg")

	def test_pdf_end_marker_tolerates_padding(self):
		"""T0029 (7): trailing NUL / whitespace padding is fine; a marker far from the end is not."""
		self.assertEqual(check_content(pdf("a") + b"\x00" * 5000 + b"\r\n ", "x.pdf"), "pdf")
		self.assertEqual(check_content(pdf("a") + b"x" * 60000, "x.pdf"), "pdf")  # within the last 64 KB
		with self.assertRaises(frappe.ValidationError):
			check_content(pdf("a") + b"x" * 70000, "x.pdf")

	def test_image_field_refuses_pdf(self):
		with self.assertRaises(frappe.ValidationError):
			check_content(pdf("a"), "x.pdf", IMAGE_KINDS)


class TestAttachmentFiles(IntegrationTestCase):
	def _file(self, content, name, private=1, **extra):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{frappe.generate_hash(length=6)}-{name}",
				"content": content,
				"is_private": private,
				**extra,
			}
		).insert(ignore_permissions=True)

	def test_stored_file_is_checked_by_content(self):
		good = self._file(png("g"), "g.png")
		check_attachment_content(good.file_url)
		# a text file saved as .png is refused although Frappe stored it
		bad = self._file(b"not an image", "b.png")
		with self.assertRaises(frappe.ValidationError):
			check_attachment_content(bad.file_url)
		with self.assertRaises(frappe.ValidationError):
			check_attachment_content("/private/files/missing-file.png")
		# F-3: the File row the caller accepted is the one checked
		check_attachment_content(good.file_url, file_row=good.name)
		with self.assertRaises(frappe.ValidationError):
			check_attachment_content(good.file_url, file_row=bad.name)  # a row that is not this url's

	def test_the_official_file_api_is_read_for_raw_bytes_and_a_str_or_a_failure_is_refused(self):
		"""T0059 C1: File.get_content(encodings=()) returns raw bytes; a decoded str or a failing read never passes."""
		good = self._file(png("raw"), "raw.png")
		get_content = "frappe.core.doctype.file.file.File.get_content"
		with mock.patch(get_content, return_value=png("raw")) as read:
			check_attachment_content(good.file_url)
		self.assertEqual(read.call_args.kwargs, {"encodings": ()})  # empty encodings = no text-decoding loop
		with mock.patch(get_content, return_value="decoded text"), self.assertRaises(frappe.ValidationError):
			check_attachment_content(good.file_url)
		with mock.patch(get_content, side_effect=OSError("gone")), self.assertRaises(frappe.ValidationError):
			check_attachment_content(good.file_url)
		check_attachment_content(good.file_url)  # the unmocked read still works

	def test_attached_only_refuses_loose_and_public_files(self):
		"""T0029 (4): a re-decision keeps the stored document only if it is a private file of THIS record."""
		mine = self._file(
			png("m"), "m.png", attached_to_doctype="Equipment Transport", attached_to_name="TRN-ATT"
		)
		self.assertEqual(
			require_record_file(mine.file_url, "Equipment Transport", "TRN-ATT", attached_only=True),
			mine.name,
		)
		loose = self._file(png("l"), "l.png")  # my own unattached upload: fine for a new document, not here
		with self.assertRaises(frappe.ValidationError):
			require_record_file(loose.file_url, "Equipment Transport", "TRN-ATT", attached_only=True)
		public = self._file(
			png("p"),
			"p.png",
			private=0,
			attached_to_doctype="Equipment Transport",
			attached_to_name="TRN-ATT",
		)
		with self.assertRaises(frappe.ValidationError):
			require_record_file(public.file_url, "Equipment Transport", "TRN-ATT", attached_only=True)
		with self.assertRaises(frappe.ValidationError):
			require_record_file(mine.file_url, "Equipment Transport", "TRN-OTHER", attached_only=True)

	def test_equipment_document_files_cannot_be_copied_and_are_claimed(self):
		"""T0029 (5): Duplicate must not copy the four document fields; the own upload is claimed on save."""
		# read the app's DocType JSON (the site's meta only changes after a migrate)
		path = frappe.get_app_path("card", "card", "doctype", "card_equipment", "card_equipment.json")
		with open(path, encoding="utf-8") as handle:
			fields = {f["fieldname"]: f for f in json.load(handle)["fields"]}
		for fieldname in ("registration_file", "inspection_file", "insurance_file", "tuv_file"):
			self.assertEqual(fields[fieldname].get("no_copy"), 1, fieldname)
		loose = self._file(png("eq"), "eq.png")
		doc = frappe.new_doc("Card Equipment")
		doc.name = "EQ-CLAIM"
		doc.flags.document_file_rows = {"registration_file": loose.name}
		doc.claim_document_files()
		saved = frappe.db.get_value(
			"File", loose.name, ["attached_to_doctype", "attached_to_name", "attached_to_field"], as_dict=True
		)
		self.assertEqual(
			(saved.attached_to_doctype, saved.attached_to_name, saved.attached_to_field),
			("Card Equipment", "EQ-CLAIM", "registration_file"),
		)

	def test_amendments_do_not_revalidate_the_kept_file(self):
		"""T0029 (2, 3): an amended fill / custody record keeps its original photo / receipt unchecked; a new one is checked."""
		from unittest import mock

		fill = frappe.get_doc({"doctype": "Project Diesel Fill", "amended_from": "DSL-OLD"})
		with mock.patch("frappe.db.get_value", return_value="/private/files/kept.png"):
			self.assertFalse(fill._photo_needs_content_check("opening_photo", "/private/files/kept.png"))
			self.assertTrue(fill._photo_needs_content_check("opening_photo", "/private/files/new.png"))
		fresh = frappe.get_doc({"doctype": "Project Diesel Fill"})
		self.assertTrue(fresh._photo_needs_content_check("opening_photo", "/private/files/kept.png"))

		module = "card.card.doctype.employee_tool_custody.employee_tool_custody"
		custody = frappe.get_doc(
			{
				"doctype": "Employee Tool Custody",
				"handover_receipt": "/private/files/r.png",
				"amended_from": "ETC-OLD",
			}
		)
		row = frappe._dict(
			name="F1", attached_to_doctype=None, attached_to_name=None, owner=frappe.session.user
		)
		row.creation = frappe.utils.now_datetime()
		setattr(custody, "__islocal", 1)  # a new record: an unattached upload of the last day counts
		for stored, expect_check in (("/private/files/r.png", False), ("/private/files/other.png", True)):
			with (
				mock.patch("frappe.get_all", return_value=[row]),
				mock.patch("frappe.db.get_value", return_value=stored),
				mock.patch(f"{module}.check_attachment_content") as checked,
			):
				custody._check_receipt_file()
			self.assertEqual(checked.called, expect_check)

	def test_claimed_file_is_attached_and_foreign_file_refused(self):
		loose = self._file(png("claim"), "claim.png")
		row = require_record_file(loose.file_url, "Equipment Transport", "TRN-CLAIM")
		claim_file(row, "Equipment Transport", "TRN-CLAIM", "billing_document")
		saved = frappe.db.get_value(
			"File", row, ["attached_to_doctype", "attached_to_name", "attached_to_field"], as_dict=True
		)
		self.assertEqual(
			(saved.attached_to_doctype, saved.attached_to_name, saved.attached_to_field),
			("Equipment Transport", "TRN-CLAIM", "billing_document"),
		)
		# now attached: it is that record's file, and another record may not use it
		self.assertEqual(require_record_file(loose.file_url, "Equipment Transport", "TRN-CLAIM"), row)
		with self.assertRaises(frappe.ValidationError):
			require_record_file(loose.file_url, "Equipment Transport", "TRN-OTHER")
		# claiming never re-points a file that already belongs to a record
		claim_file(row, "Equipment Transport", "TRN-OTHER", "billing_document")
		self.assertEqual(frappe.db.get_value("File", row, "attached_to_name"), "TRN-CLAIM")

	def test_record_file_rules(self):
		own = self._file(
			png("own"),
			"own.png",
			attached_to_doctype="Equipment Transport",
			attached_to_name="TRN-X",
		)
		self.assertEqual(require_record_file(own.file_url, "Equipment Transport", "TRN-X"), own.name)
		with self.assertRaises(frappe.ValidationError):  # another record's file
			require_record_file(own.file_url, "Equipment Transport", "TRN-OTHER")
		loose = self._file(png("loose"), "loose.png")  # unattached, owned by the session user
		self.assertEqual(require_record_file(loose.file_url, "Card Equipment", "EQ-1"), loose.name)
		public = self._file(png("pub"), "pub.png", private=0)
		with self.assertRaises(frappe.ValidationError):
			require_record_file(public.file_url, "Card Equipment", "EQ-1")
		elsewhere = self._file(
			png("other"), "other.png", attached_to_doctype="Card Equipment", attached_to_name="EQ-OTHER"
		)
		with self.assertRaises(frappe.ValidationError):  # attached to a different Card Equipment
			require_record_file(elsewhere.file_url, "Card Equipment", "EQ-1")
		unsaved = self._file(
			png("unsaved"),
			"unsaved.png",
			attached_to_doctype="Card Equipment",
			attached_to_name="new-card-equipment-abc123",
		)
		self.assertEqual(
			require_record_file(unsaved.file_url, "Card Equipment", None, "new-card-equipment-abc123"),
			unsaved.name,
		)
