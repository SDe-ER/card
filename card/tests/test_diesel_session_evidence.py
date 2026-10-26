# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Phase 1 (Owner 2026-10-26): a Project Diesel Fill is a metered session. Meter readings give the
litres, the meter photos are private and prove one fill only, the totalizer check is advisory, and
the operations review (Card Manager / System Manager) is separate from the accounting submit."""

import frappe
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.doctype.project_diesel_fill.project_diesel_fill import totalizer_bounds
from card.tests.diesel_price import set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _role_user, _set


class TestTotalizerBounds(IntegrationTestCase):
	def test_bounds(self):
		self.assertEqual(totalizer_bounds("0556232"), (556232, 556232))
		self.assertEqual(totalizer_bounds("055793?"), (557930, 557939))
		self.assertEqual(totalizer_bounds("05579??"), (557900, 557999))
		for unreadable in (None, "", "?", "0563?8?", "abc"):
			self.assertIsNone(totalizer_bounds(unreadable))


class TestDieselSessionEvidence(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		_set("period_lock_date", None)
		_set("diesel_supplier", None)
		_set("diesel_supplier_policy", "متغير")
		_set("diesel_price_exception_role", "Accounts Manager")
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DSE-PRJ-" + self.token
		proj.company = self.company
		self.project = proj.insert(ignore_permissions=True).name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DSE-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		set_diesel_price(self.company, 1.79)
		self.card_user = _role_user("Card User")
		self.manager = _role_user("Card Manager")
		self.accountant = _role_user("Accounts Manager")

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _photo(self, temp, field="closing_photo", private=1, content=None, attach=True, user=None):
		"""A meter photo uploaded on the unsaved form by `user`, as the Desk does: attached to the
		form's temporary name, which Frappe relinks to the real name on insert."""
		data = {
			"doctype": "File",
			"file_name": f"meter-{frappe.generate_hash(length=10)}.txt",
			"is_private": private,
			"content": content or frappe.generate_hash(length=32),
		}
		if attach:
			data.update(
				{
					"attached_to_doctype": "Project Diesel Fill",
					"attached_to_name": temp,
					"attached_to_field": field,
				}
			)
		insert = frappe.get_doc(data).insert
		return (
			self._as(user, insert, ignore_permissions=True) if user else insert(ignore_permissions=True)
		).file_url

	def _new(self, user=None, **extra):
		temp = extra.pop("_temp", None)
		data = {
			"doctype": "Project Diesel Fill",
			"date": "2026-08-25",
			"project": self.project,
			"supplier": self.supplier,
			"company": self.company,
			"litres": 1,
		}
		data.update(extra)
		doc = frappe.get_doc(data)
		if temp:
			setattr(doc, "__temporary_name", temp)
		return self._as(user, doc.insert) if user else doc.insert()

	def _evidence(self, content=None, private=1, attach=True, opening_content=None, user=None, **extra):
		temp = "new-project-diesel-fill-" + frappe.generate_hash(length=8)
		data = {
			"_temp": temp,
			"opening_reading": 0,
			"closing_reading": 1702,
			"closing_photo": self._photo(temp, private=private, content=content, attach=attach, user=user),
		}
		if opening_content:
			data["opening_photo"] = self._photo(temp, "opening_photo", content=opening_content)
		data.update(extra)
		return data

	# ---------- readings (T1, T2) ----------

	def test_litres_come_from_the_readings(self):
		f = self._new(**self._evidence(litres=50))
		self.assertEqual(flt(f.litres), 1702)
		self.assertEqual(flt(f.amount), flt(1702 * 1.79, 2))

	def test_closing_below_opening_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._new(**self._evidence(opening_reading=500, closing_reading=400))

	def test_manual_fill_without_readings_keeps_its_litres(self):
		f = self._new(litres=300)
		self.assertEqual(flt(f.litres), 300)
		self.assertEqual(f.totalizer_check, "Not Checkable")
		# Frappe stores the empty closing reading as 0: a later save must not turn the litres into 0
		f = frappe.get_doc(f.doctype, f.name)
		self.assertEqual(flt(f.closing_reading), 0)
		f.remarks = "edited"
		f.save()
		self.assertEqual(flt(f.litres), 300)

	# ---------- review (T3, T4, T5, T6, T13, T14) ----------

	def test_draft_without_photo_saves_but_cannot_be_approved(self):
		f = self._new(litres=300)
		self.assertEqual(f.review_status, "Draft")
		f.review_status = "Operations Approved"
		with self.assertRaises(frappe.ValidationError):
			self._as(self.manager, f.save)

	def test_card_user_cannot_approve_on_the_form(self):
		f = self._new(user=self.card_user, **self._evidence(user=self.card_user))
		f.review_status = "Operations Approved"
		f.ops_reviewed_by = self.card_user
		self._as(self.card_user, f.save)  # permlevel 1: the value is not taken from this user
		f.reload()
		self.assertNotEqual(f.review_status, "Operations Approved")
		self.assertFalse(f.ops_reviewed_by)

	def test_card_user_cannot_approve_via_rest(self):
		f = self._new(user=self.card_user, **self._evidence(user=self.card_user))
		try:
			self._as(
				self.card_user, rest_set_value, f.doctype, f.name, "review_status", "Operations Approved"
			)
		except frappe.PermissionError:
			pass
		self.assertNotEqual(frappe.db.get_value(f.doctype, f.name, "review_status"), "Operations Approved")

	def test_card_user_cannot_approve_even_when_permlevel_is_bypassed(self):
		# the server role check stands also where the permlevel guard is not applied
		f = self._new(user=self.card_user, **self._evidence(user=self.card_user))
		f.review_status = "Operations Approved"
		f.flags.ignore_permissions = True
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, f.save)

	def test_manager_approves_and_the_server_names_the_reviewer(self):
		f = self._new(**self._evidence())
		f.review_status = "Operations Approved"
		f.ops_reviewed_by = self.card_user  # spoofed: ignored
		self._as(self.manager, f.save)
		f.reload()
		self.assertEqual(f.review_status, "Operations Approved")
		self.assertEqual(f.ops_reviewed_by, self.manager)
		self.assertTrue(f.ops_reviewed_on)

	def test_submit_needs_operations_approval(self):
		f = self._new(**self._evidence())
		with self.assertRaises(frappe.ValidationError):
			f.submit()
		f.reload()
		f.review_status = "Operations Approved"
		self._as(self.manager, f.save)
		f.reload()
		f.submit()
		self.assertEqual(f.docstatus, 1)
		self.assertEqual(f.price_source, "Company Price")  # the price lock is unchanged

	def test_change_after_approval_returns_to_review(self):
		f = self._new(**self._evidence())
		f.review_status = "Operations Approved"
		self._as(self.manager, f.save)
		f = frappe.get_doc(f.doctype, f.name)
		f.closing_reading = 1800
		self._as(self.card_user, f.save)  # any user's material edit voids the approval
		f.reload()
		self.assertEqual(f.review_status, "Needs Review")
		self.assertFalse(f.ops_reviewed_by)

	def test_review_fields_are_read_only_for_card_user_and_accounts(self):
		meta = frappe.get_meta("Project Diesel Fill")
		perms = {(p.role, p.permlevel): p for p in meta.permissions}
		for role in ("Card User", "Accounts Manager"):
			self.assertTrue(perms[(role, 1)].read)
			self.assertFalse(perms[(role, 1)].write)
		for role in ("Card Manager", "System Manager"):
			self.assertTrue(perms[(role, 1)].write)
		self.assertEqual(meta.get_field("review_status").permlevel, 1)

	# ---------- overlaps and photos (T7, T8, T9) ----------

	def test_second_fill_same_project_and_day_is_allowed_with_a_warning(self):
		first = self._new(litres=100)
		second = self._new(litres=200)
		self.assertIn(first.name, second.evidence_warnings or "")
		self.assertEqual(second.review_status, "Needs Review")

	def test_same_photo_cannot_prove_two_fills(self):
		# the real 2026-08-24 case: one session's photos sent again for another site
		content = frappe.generate_hash(length=32)
		first = self._new(**self._evidence(content=content))
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._new(date="2026-08-24", **self._evidence(content=content))
		self.assertIn(first.name, str(ctx.exception))

	def test_rejected_fill_releases_its_photo(self):
		content = frappe.generate_hash(length=32)
		wrong = self._new(**self._evidence(content=content))
		wrong.review_status = "Rejected"
		self._as(self.manager, wrong.save)
		corrected = self._new(date="2026-08-24", **self._evidence(content=content))
		self.assertTrue(corrected.name)

	def test_opening_and_closing_cannot_be_the_same_photo(self):
		content = frappe.generate_hash(length=32)
		with self.assertRaises(frappe.ValidationError):
			self._new(**self._evidence(content=content, opening_content=content))

	def test_public_photo_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._new(**self._evidence(private=0))

	def test_photo_not_uploaded_to_this_fill_is_refused(self):
		# a private path of an unrelated file (or no File at all) is not evidence
		with self.assertRaises(frappe.ValidationError):
			self._new(**self._evidence(attach=False))
		with self.assertRaises(frappe.ValidationError):
			self._new(**self._evidence(closing_photo="/private/files/does-not-exist.jpg"))

	def test_forged_temporary_name_cannot_take_another_fills_photo(self):
		# security review 2026-10-26: the temporary name comes from the client
		victim = self._new(**self._evidence())
		photo = victim.closing_photo
		data = {"_temp": victim.name, "closing_reading": 1702, "closing_photo": photo}
		with self.assertRaises(frappe.ValidationError):
			self._new(user=self.card_user, date="2026-08-24", **data)
		self.assertEqual(frappe.db.get_value("File", {"file_url": photo}, "attached_to_name"), victim.name)

	def test_temporary_upload_of_another_user_is_refused(self):
		temp = "new-project-diesel-fill-" + frappe.generate_hash(length=8)
		photo = self._photo(temp)  # uploaded by Administrator
		with self.assertRaises(frappe.ValidationError):
			self._new(user=self.card_user, _temp=temp, closing_reading=1702, closing_photo=photo)

	def test_equipment_change_after_approval_returns_to_review(self):
		f = self._new(**self._evidence(equipment_filled=[{"reported_name": "بكلين"}]))
		f.review_status = "Operations Approved"
		self._as(self.manager, f.save)
		f = frappe.get_doc(f.doctype, f.name)
		f.append("equipment_filled", {"reported_name": "شيول"})
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual(f.review_status, "Needs Review")

	def test_amendment_keeps_the_cancelled_fills_photo(self):
		f = self._new(**self._evidence())
		f.review_status = "Operations Approved"
		self._as(self.manager, f.save)
		f.reload()
		f.submit()
		f.cancel()
		a = frappe.copy_doc(f)  # the server copy keeps the photo fields
		a.update({"amended_from": f.name, "docstatus": 0})
		a.insert()
		self.assertEqual(a.closing_photo, f.closing_photo)
		self.assertEqual(a.review_status, "Draft")  # the approval does not carry over

	def test_live_fill_photo_cannot_be_taken_by_an_amendment_claim(self):
		live = self._new(**self._evidence())
		a = frappe.copy_doc(live)
		a.update({"amended_from": live.name, "docstatus": 0, "date": "2026-08-24"})
		with self.assertRaises(frappe.ValidationError):
			a.insert()  # the original is not cancelled: its photo is not this fill's evidence

	def test_photo_uploaded_on_the_new_form_is_relinked(self):
		f = self._new(**self._evidence())
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": f.closing_photo}, "attached_to_name"), f.name
		)
		f.remarks = "edited"
		f.save()  # the saved fill finds its photo under its real name

	# ---------- totalizer (T10, TOLERANCE-EVIDENCE §6) ----------

	def _check(self, opening_tot, closing_tot, closing_reading):
		return self._new(
			**self._evidence(
				closing_reading=closing_reading,
				opening_totalizer=opening_tot,
				closing_totalizer=closing_tot,
			)
		).totalizer_check

	def test_totalizer_cases(self):
		cases = [
			("0556232", "055793?", 1702, "Consistent"),  # real photos 00003924/00003925
			("0437028", "0439108", 2080, "Consistent"),  # exact, difference 0
			("0500000", "0501399", 1400, "Consistent"),  # exact, difference -1
			("0610000", "0611448", 1451, "Inconsistent"),  # -3: a misread digit
			("0650000", "0651585", 1595, "Inconsistent"),  # -10
			("0871971", "0871962", 100, "Inconsistent"),  # totalizer went backwards
			(None, "0563081", 2080, "Not Checkable"),  # no reset photo
		]
		for opening_tot, closing_tot, reading, expected in cases:
			with self.subTest(opening_tot=opening_tot, closing_tot=closing_tot):
				self.assertEqual(self._check(opening_tot, closing_tot, reading), expected)

	def test_inconsistent_totalizer_sends_draft_to_review(self):
		f = self._new(
			**self._evidence(opening_totalizer="0650000", closing_totalizer="0651585", closing_reading=1595)
		)
		self.assertEqual(f.review_status, "Needs Review")
		self.assertTrue(f.evidence_warnings)

	# ---------- equipment table (T11) ----------

	def _equipment(self):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "إيجار"
		d.equipment_name = "TEST-DSE-EQ-" + frappe.generate_hash(length=8)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self.supplier
		return d.insert(ignore_permissions=True).name

	def test_one_equipment_and_a_list_are_exclusive(self):
		equipment = self._equipment()
		self._new(litres=100, card_equipment=equipment)  # one equipment alone is fine
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._new(
				litres=100,
				card_equipment=equipment,
				equipment_filled=[{"card_equipment": equipment, "match_status": "Matched"}],
			)
		self.assertIn("not both", str(ctx.exception))

	def test_matched_row_needs_equipment(self):
		with self.assertRaises(frappe.ValidationError):
			self._new(litres=100, equipment_filled=[{"reported_name": "شيول", "match_status": "Matched"}])

	def test_unmatched_rows_keep_the_supplier_words(self):
		f = self._new(
			litres=100,
			equipment_filled=[
				{"reported_name": "بكلين كبير"},
				{"reported_name": "قلاب", "match_status": "Third Party"},
			],
		)
		self.assertEqual([r.match_status for r in f.equipment_filled], ["Unmatched", "Third Party"])
		self.assertFalse(any(hasattr(r, "litres") and r.get("litres") for r in f.equipment_filled))
