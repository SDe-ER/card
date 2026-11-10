# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-140 (#31 D6): Equipment Meter Reading.

Monotonic engine hours per equipment, the meter reset with a reason, the company taken from the equipment,
cross-company refusal through Frappe's own entry points (generic company scope, FR-131), a REST create with
docstatus=1, cancel and amend, the private attachment rule and the role permissions. Company B and the equipment
are inserted raw (only the stored company matters); no role is widened; everything is rolled back."""

from unittest.mock import patch

import frappe
from frappe.client import insert as rest_insert
from frappe.tests import IntegrationTestCase

from card.tests.sample_files import png
from card.tests.test_controllers import _ensure_masters

DOCTYPE = "Equipment Meter Reading"


class TestMeterReading(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.A = self._m["company"]
		self.B = self._company("TEST-EMR-CO-" + self.token)
		self.eq_a = self._raw("Card Equipment", "TEST-EMR-EA-" + self.token, company=self.A)
		self.eq_a2 = self._raw("Card Equipment", "TEST-EMR-EA2-" + self.token, company=self.A)
		self.eq_b = self._raw("Card Equipment", "TEST-EMR-EB-" + self.token, company=self.B)
		self.supervisor = self._user(("Card Supervisor",), restrict=self.A)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders ----------
	def _company(self, name):
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "M" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.A, "default_currency"),
				"country": frappe.db.get_value("Company", self.A, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _raw(self, doctype, name, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = name
		doc.db_insert()
		return name

	def _user(self, roles, restrict=None):
		email = f"emr-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Meter Reading",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _reading(self, hours, when, equipment=None, submit=True, **values):
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"equipment": equipment or self.eq_a,
				"reading_datetime": when,
				"engine_hours": hours,
				**values,
			}
		)
		doc.insert()
		if submit:
			doc.submit()
		return doc

	def _file(self, private=1, owner=None):
		frappe.set_user(owner or "Administrator")
		row = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"meter-{frappe.generate_hash(length=6)}.png",
				"content": png("meter"),
				"is_private": private,
			}
		).insert()
		frappe.set_user("Administrator")
		return row.file_url

	# ---------- monotonic rule and reset ----------
	def test_company_comes_from_the_equipment(self):
		doc = self._reading(100, "2026-09-01 08:00:00", company=self.B, submit=False)
		self.assertEqual(doc.company, self.A)

	def test_equipment_without_company_refused(self):
		loose = self._raw("Card Equipment", "TEST-EMR-EN-" + self.token)
		with self.assertRaises(frappe.ValidationError):
			self._reading(10, "2026-09-01 08:00:00", equipment=loose, submit=False)

	def test_rising_readings_pass_and_record_the_previous(self):
		first = self._reading(100, "2026-09-01 08:00:00")
		second = self._reading(100, "2026-09-08 08:00:00")  # equal is not lower
		third = self._reading(150.5, "2026-09-15 08:00:00")
		self.assertEqual(second.previous_reading, first.name)
		self.assertEqual(third.previous_reading, second.name)
		self.assertEqual(third.previous_engine_hours, 100)
		self.assertFalse(first.previous_reading)

	def test_lower_reading_refused(self):
		self._reading(500, "2026-09-01 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			self._reading(499, "2026-09-08 08:00:00", submit=False)

	def test_lower_draft_refused_at_submit(self):
		draft = self._reading(400, "2026-09-08 08:00:00", submit=False)
		self._reading(500, "2026-09-01 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			draft.submit()

	def test_drafts_and_cancelled_readings_do_not_count(self):
		self._reading(900, "2026-09-01 08:00:00", submit=False)
		cancelled = self._reading(800, "2026-09-02 08:00:00")
		cancelled.cancel()
		self.assertEqual(self._reading(10, "2026-09-08 08:00:00").docstatus, 1)

	def test_other_equipment_does_not_count(self):
		self._reading(500, "2026-09-01 08:00:00", equipment=self.eq_a2)
		self.assertEqual(self._reading(5, "2026-09-08 08:00:00").docstatus, 1)

	def test_reset_with_reason_passes(self):
		self._reading(500, "2026-09-01 08:00:00")
		reset = self._reading(3, "2026-09-08 08:00:00", is_meter_reset=1, reset_reason="Meter replaced")
		self.assertEqual(reset.docstatus, 1)
		self.assertEqual(reset.previous_engine_hours, 500)
		# the next reading compares with the reset value
		self.assertEqual(self._reading(40, "2026-09-15 08:00:00").previous_reading, reset.name)

	def test_reset_needs_a_reason(self):
		self._reading(500, "2026-09-01 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			self._reading(3, "2026-09-08 08:00:00", is_meter_reset=1, reset_reason="  ", submit=False)

	def test_reset_only_for_a_lower_reading(self):
		with self.assertRaises(frappe.ValidationError):
			self._reading(3, "2026-09-01 08:00:00", is_meter_reset=1, reset_reason="x", submit=False)
		self._reading(500, "2026-09-02 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			self._reading(600, "2026-09-08 08:00:00", is_meter_reset=1, reset_reason="x", submit=False)

	def test_reason_cleared_without_reset(self):
		doc = self._reading(5, "2026-09-01 08:00:00", reset_reason="not a reset", submit=False)
		self.assertIsNone(doc.reset_reason)

	def test_backdated_reading_above_a_later_one_refused(self):
		self._reading(100, "2026-09-01 08:00:00")
		self._reading(200, "2026-09-15 08:00:00")
		self.assertEqual(self._reading(150, "2026-09-08 08:00:00").docstatus, 1)
		with self.assertRaises(frappe.ValidationError):
			self._reading(250, "2026-09-10 08:00:00", submit=False)

	def test_backdated_reading_before_a_later_reset_passes(self):
		self._reading(100, "2026-09-01 08:00:00")
		self._reading(5, "2026-09-15 08:00:00", is_meter_reset=1, reset_reason="Meter replaced")
		self.assertEqual(self._reading(180, "2026-09-08 08:00:00").docstatus, 1)

	def test_same_date_and_time_refused(self):
		self._reading(100, "2026-09-01 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			self._reading(100, "2026-09-01 08:00:00", submit=False)

	def test_submit_rechecks_with_locking_reads(self):
		"""Submit locks the equipment row and reads the neighbours with locking reads (latest committed rows, not
		the transaction's REPEATABLE READ snapshot), so two parallel submits of one equipment cannot both pass."""
		draft = self._reading(100, "2026-09-01 08:00:00", submit=False)
		real_values, real_value = frappe.db.get_values, frappe.db.get_value
		calls = []

		def get_values(doctype, *args, **kwargs):
			if doctype == DOCTYPE:
				calls.append(("values", kwargs.get("for_update")))
			return real_values(doctype, *args, **kwargs)

		def get_value(doctype, *args, **kwargs):
			if doctype == "Card Equipment" and kwargs.get("for_update"):
				calls.append(("lock", True))
			return real_value(doctype, *args, **kwargs)

		with (
			patch.object(frappe.db, "get_values", side_effect=get_values),
			patch.object(frappe.db, "get_value", side_effect=get_value),
		):
			draft.submit()
		self.assertIn(("lock", True), calls)
		locked = calls[calls.index(("lock", True)) + 1 :]
		self.assertEqual(locked, [("values", True)] * 3)

	# ---------- cancel keeps the sequence ----------
	def test_cancel_of_a_reset_that_a_later_reading_needs_refused(self):
		"""100, 10 (reset), 20: cancelling the reset would leave 100 -> 20 without a reset."""
		self._reading(100, "2026-09-01 08:00:00")
		reset = self._reading(10, "2026-09-08 08:00:00", is_meter_reset=1, reset_reason="Meter replaced")
		self._reading(20, "2026-09-15 08:00:00")
		with self.assertRaises(frappe.ValidationError):
			reset.cancel()
		self.assertEqual(frappe.db.get_value(DOCTYPE, reset.name, "docstatus"), 1)

	def test_cancel_before_a_reset_that_needs_it_refused(self):
		"""100, 10 (reset): cancelling the 100 would leave a reset without a higher previous reading."""
		first = self._reading(100, "2026-09-01 08:00:00")
		self._reading(10, "2026-09-08 08:00:00", is_meter_reset=1, reset_reason="Meter replaced")
		with self.assertRaises(frappe.ValidationError):
			first.cancel()
		# with an earlier higher reading the reset still holds, so the cancel passes
		self._reading(90, "2026-08-25 08:00:00")
		first.reload()
		first.cancel()
		self.assertEqual(first.docstatus, 2)

	def test_cancel_that_keeps_the_sequence_passes(self):
		self._reading(100, "2026-09-01 08:00:00")
		middle = self._reading(150, "2026-09-08 08:00:00")
		last = self._reading(200, "2026-09-15 08:00:00")
		middle.cancel()
		self.assertEqual(middle.docstatus, 2)
		last.cancel()  # nothing after it
		self.assertEqual(last.docstatus, 2)

	def test_cancel_takes_the_lock_and_locking_reads(self):
		reading = self._reading(100, "2026-09-01 08:00:00")
		real_values, real_value = frappe.db.get_values, frappe.db.get_value
		calls = []

		def get_values(doctype, *args, **kwargs):
			if doctype == DOCTYPE and kwargs.get("for_update"):
				calls.append("read")
			return real_values(doctype, *args, **kwargs)

		def get_value(doctype, *args, **kwargs):
			if doctype == "Card Equipment" and kwargs.get("for_update"):
				calls.append("lock")
			return real_value(doctype, *args, **kwargs)

		with (
			patch.object(frappe.db, "get_values", side_effect=get_values),
			patch.object(frappe.db, "get_value", side_effect=get_value),
		):
			reading.cancel()
		self.assertEqual(calls, ["lock", "read", "read", "read"])

	def test_backdated_reset_before_a_later_reset_refused(self):
		"""100, 10 (reset): a backdated 5 (reset) between them would make the 10 reset no longer lower."""
		self._reading(100, "2026-09-01 08:00:00")
		self._reading(10, "2026-09-15 08:00:00", is_meter_reset=1, reset_reason="Meter replaced")
		with self.assertRaises(frappe.ValidationError):
			self._reading(5, "2026-09-08 08:00:00", is_meter_reset=1, reset_reason="x", submit=False)
		with self.assertRaises(frappe.ValidationError):
			self._reading(10, "2026-09-08 08:00:00", submit=False)  # equal is not lower either
		self.assertEqual(self._reading(150, "2026-09-08 08:00:00").docstatus, 1)

	def test_previous_fields_are_a_snapshot(self):
		"""The previous-reading fields are not rewritten when an earlier reading is added later."""
		self._reading(100, "2026-09-01 08:00:00")
		later = self._reading(200, "2026-09-15 08:00:00")
		self._reading(150, "2026-09-08 08:00:00")
		later.reload()
		self.assertEqual(later.previous_engine_hours, 100)
		meta = frappe.get_meta(DOCTYPE)
		for fieldname in ("previous_reading", "previous_engine_hours"):
			self.assertIn("Snapshot", meta.get_field(fieldname).description or "")

	def test_negative_hours_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._reading(-1, "2026-09-01 08:00:00", submit=False)

	# ---------- cross-company refusal through Frappe ----------
	def test_cross_company_create_refused(self):
		frappe.set_user(self.supervisor)
		for company in (self.A, self.B):
			with self.subTest(company=company), self.assertRaises(frappe.PermissionError):
				rest_insert(
					{
						"doctype": DOCTYPE,
						"equipment": self.eq_b,
						"company": company,
						"reading_datetime": "2026-09-01 08:00:00",
						"engine_hours": 10,
					}
				)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists(DOCTYPE, {"equipment": self.eq_b}))

	def test_cross_company_read_list_and_edit_refused(self):
		own = self._reading(10, "2026-09-01 08:00:00")
		other = self._reading(10, "2026-09-01 08:00:00", equipment=self.eq_b)
		frappe.set_user(self.supervisor)
		self.assertTrue(frappe.has_permission(DOCTYPE, "read", own.name))
		self.assertFalse(frappe.has_permission(DOCTYPE, "read", other.name))
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(DOCTYPE, other.name).check_permission("read")
		names = frappe.get_list(DOCTYPE, filters={"name": ["in", [own.name, other.name]]}, pluck="name")
		self.assertEqual(names, [own.name])
		# moving an own draft to the other company's equipment is refused too
		draft = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"equipment": self.eq_a,
				"reading_datetime": "2026-09-08 08:00:00",
				"engine_hours": 20,
			}
		).insert()
		draft.equipment = self.eq_b
		with self.assertRaises(frappe.PermissionError):
			draft.save()

	def test_amend_of_another_company_reading_refused(self):
		other = self._reading(10, "2026-09-01 08:00:00", equipment=self.eq_b)
		other.cancel()
		frappe.set_user(self.supervisor)
		with self.assertRaises(frappe.PermissionError):
			rest_insert(
				{
					"doctype": DOCTYPE,
					"equipment": self.eq_a,
					"reading_datetime": "2026-09-01 08:00:00",
					"engine_hours": 10,
					"amended_from": other.name,
				}
			)

	# ---------- REST and roles ----------
	def test_rest_create_with_docstatus_1(self):
		frappe.set_user(self.supervisor)
		saved = rest_insert(
			{
				"doctype": DOCTYPE,
				"equipment": self.eq_a,
				"reading_datetime": "2026-09-01 08:00:00",
				"engine_hours": 1234.5,
				"source": "Weekly reading",
				"docstatus": 1,
			}
		)
		frappe.set_user("Administrator")
		row = frappe.db.get_value(
			DOCTYPE, saved["name"], ["docstatus", "company", "engine_hours"], as_dict=True
		)
		self.assertEqual((row.docstatus, row.company, row.engine_hours), (1, self.A, 1234.5))
		# a lower one through REST is refused, and nothing is stored
		frappe.set_user(self.supervisor)
		with self.assertRaises(frappe.ValidationError):
			rest_insert(
				{
					"doctype": DOCTYPE,
					"equipment": self.eq_a,
					"reading_datetime": "2026-09-08 08:00:00",
					"engine_hours": 1000,
					"docstatus": 1,
				}
			)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count(DOCTYPE, {"equipment": self.eq_a}), 1)

	def test_card_user_reads_but_cannot_create(self):
		reading = self._reading(10, "2026-09-01 08:00:00")
		user = self._user(("Card User",), restrict=self.A)
		frappe.set_user(user)
		self.assertTrue(frappe.has_permission(DOCTYPE, "read", reading.name))
		with self.assertRaises(frappe.PermissionError):
			rest_insert(
				{
					"doctype": DOCTYPE,
					"equipment": self.eq_a,
					"reading_datetime": "2026-09-08 08:00:00",
					"engine_hours": 20,
				}
			)

	def test_only_card_roles_hold_permissions(self):
		roles = {p.role for p in frappe.get_meta(DOCTYPE).permissions}
		self.assertEqual(roles, {"Card Manager", "Card Supervisor", "Card User"})
		create = {p.role for p in frappe.get_meta(DOCTYPE).permissions if p.create}
		self.assertEqual(create, {"Card Manager", "Card Supervisor"})
		meta = frappe.get_meta(DOCTYPE)
		self.assertTrue(meta.is_submittable)
		self.assertTrue(meta.track_changes)

	# ---------- amend ----------
	def test_cancel_and_amend(self):
		frappe.set_user(self.supervisor)
		wrong = self._reading(1500, "2026-09-01 08:00:00")
		self._reading(1510, "2026-09-08 08:00:00")
		wrong.cancel()
		amended = frappe.copy_doc(wrong)
		amended.amended_from = wrong.name
		amended.docstatus = 0
		amended.engine_hours = 1490
		amended.insert()
		amended.submit()
		self.assertEqual(amended.name, wrong.name + "-1")
		self.assertEqual(amended.company, self.A)
		self.assertEqual(amended.docstatus, 1)

	def test_amend_needs_a_cancelled_reading(self):
		reading = self._reading(10, "2026-09-01 08:00:00")
		amended = frappe.copy_doc(reading)
		amended.amended_from = reading.name
		amended.docstatus = 0
		amended.reading_datetime = "2026-09-08 08:00:00"
		with self.assertRaises(frappe.ValidationError):
			amended.insert()

	# ---------- attachment ----------
	def test_private_own_upload_accepted_and_claimed(self):
		url = self._file(private=1, owner=self.supervisor)
		frappe.set_user(self.supervisor)
		doc = self._reading(10, "2026-09-01 08:00:00", attachment=url)
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": url}, ["attached_to_doctype", "attached_to_name"]),
			(DOCTYPE, doc.name),
		)

	def test_public_or_foreign_file_refused(self):
		public = self._file(private=0)
		with self.assertRaises(frappe.ValidationError):
			self._reading(10, "2026-09-01 08:00:00", attachment=public, submit=False)
		foreign = self._file(private=1)  # another user's (Administrator's) loose upload
		frappe.set_user(self.supervisor)
		with self.assertRaises(frappe.ValidationError):
			self._reading(10, "2026-09-01 08:00:00", attachment=foreign, submit=False)

	def test_amend_keeps_the_attachment(self):
		url = self._file(private=1, owner=self.supervisor)
		frappe.set_user(self.supervisor)
		reading = self._reading(10, "2026-09-01 08:00:00", attachment=url)
		reading.cancel()
		amended = frappe.copy_doc(reading)
		amended.amended_from = reading.name
		amended.docstatus = 0
		amended.engine_hours = 12
		amended.insert()
		self.assertEqual(amended.attachment, url)
