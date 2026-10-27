# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-002 diesel price lock (Owner 2026-10-19, Q1–Q4): the company price from Card Settings,
exceptions only for the Settings role with a reason, zero price refused unless a role is named,
old drafts never repriced silently, submitted fills never touched. Owner 2026-10-20: a saved draft
keeps its price when the company price changes; changing it needs the exception role and a reason."""

import frappe
from frappe.client import insert as rest_insert
from frappe.client import save as rest_save
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.doctype.project_diesel_fill.project_diesel_fill import (
	get_diesel_price_context,
	remove_price_exception,
	use_company_price,
)
from card.tests.diesel_price import approve_fill, set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _role_user, _set


class TestDieselPriceLock(IntegrationTestCase):
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
		_set("diesel_zero_price_role", None)
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DPL-PRJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DPL-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		set_diesel_price(self.company, 2)
		self.card_user = _role_user("Card User")
		self.accountant = _role_user("Card User", "Accounts Manager")
		self.accounts_only = _role_user("Accounts Manager")

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _data(self, **extra):
		data = {
			"doctype": "Project Diesel Fill",
			"date": "2026-09-15",
			"project": self.project,
			"supplier": self.supplier,
			"company": self.company,
			"litres": 100,
		}
		data.update(extra)
		return data

	def _new(self, **extra):
		return frappe.get_doc(self._data(**extra)).insert()

	def _other_project(self, company):
		"""A fill moved to another company takes a project of that company (P0 company check)."""
		p = frappe.new_doc("Project")
		p.project_name = "TEST-DPL-PRJ-" + frappe.generate_hash(length=8)
		p.company = company
		return p.insert(ignore_permissions=True).name

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _legacy_draft(self, price):
		"""A draft saved before the price lock: typed price, empty price source."""
		f = self._new()
		frappe.db.set_value(
			"Project Diesel Fill",
			f.name,
			{"unit_price": price, "price_source": None, "company_price": 0, "amount": 100 * price},
		)
		return frappe.get_doc("Project Diesel Fill", f.name)

	# ---------- company price (Q1) ----------

	def test_card_user_gets_company_price(self):
		f = self._as(self.card_user, self._new)
		self.assertEqual(flt(f.unit_price), 2)
		self.assertEqual(flt(f.amount), 200)
		self.assertEqual(f.price_source, "Company Price")
		self.assertEqual(flt(f.company_price), 2)

	def test_card_user_typed_price_refused_also_via_rest(self):
		with self.assertRaises(frappe.ValidationError):
			self._as(self.card_user, self._new, unit_price=1.5)
		with self.assertRaises(frappe.ValidationError):
			self._as(self.card_user, rest_insert, self._data(unit_price=1.5))
		f = self._as(self.card_user, self._new)
		doc = f.as_dict()
		doc["unit_price"] = 1.5
		with self.assertRaises(frappe.ValidationError):
			self._as(self.card_user, rest_save, doc)
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", f.name, "unit_price")), 2)

	def test_tampered_audit_fields_are_overwritten(self):
		f = self._as(
			self.card_user,
			rest_insert,
			self._data(
				price_source="Exception",
				company_price=9,
				exception_by="Administrator",
				exception_on="2026-01-01",
			),
		)
		row = frappe.db.get_value(
			"Project Diesel Fill", f["name"], ["price_source", "company_price", "exception_by"], as_dict=True
		)
		self.assertEqual(row.price_source, "Company Price")
		self.assertEqual(flt(row.company_price), 2)
		self.assertFalse(row.exception_by)

	def test_missing_or_zero_company_price_refused(self):
		set_diesel_price(self.company, 0)
		with self.assertRaises(frappe.ValidationError):
			self._as(self.card_user, self._new)
		with self.assertRaises(frappe.ValidationError):
			self._new()  # Administrator too: no exception, no price

	# ---------- exception (Q1) ----------

	def test_exception_by_role_with_reason_is_audited(self):
		f = self._as(self.card_user, self._new)
		f.reload()
		f.price_exception = 1
		f.unit_price = 2.4
		f.exception_reason = "Supplier invoice price for this delivery"
		self._as(self.accountant, f.save, ignore_version=False)  # frappe skips Version rows in tests
		f.reload()
		self.assertEqual(f.price_source, "Exception")
		self.assertEqual(flt(f.unit_price), 2.4)
		self.assertEqual(flt(f.company_price), 2)  # the original value
		self.assertEqual(f.exception_by, self.accountant)
		self.assertTrue(f.exception_on)
		self.assertEqual(flt(f.amount), 240)
		versions = frappe.db.get_all(
			"Version", filters={"ref_doctype": "Project Diesel Fill", "docname": f.name}, fields=["data"]
		)
		self.assertTrue(any('"unit_price"' in (v.data or "") for v in versions), versions)

	def test_exception_needs_a_reason(self):
		f = self._new()
		for reason in (None, "   "):
			f.reload()
			f.price_exception = 1
			f.unit_price = 2.4
			f.exception_reason = reason
			with self.assertRaises(frappe.ValidationError):
				self._as(self.accountant, f.save)

	def test_card_user_cannot_set_exception_even_via_rest(self):
		f = self._new()
		doc = f.as_dict()
		doc.update({"price_exception": 1, "unit_price": 2.4, "exception_reason": "x"})
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, rest_save, doc)
		with self.assertRaises(frappe.PermissionError):
			self._as(
				self.card_user,
				rest_insert,
				self._data(price_exception=1, unit_price=2.4, exception_reason="x"),
			)

	def test_accounts_manager_alone_cannot_edit_the_fill(self):
		# Owner: the exception role also needs rights on the document; no write grant was added
		f = self._new()
		f.reload()
		f.price_exception = 1
		f.unit_price = 2.4
		f.exception_reason = "x"
		with self.assertRaises(frappe.PermissionError):
			self._as(self.accounts_only, f.save)

	def test_accountant_with_card_user_has_write_but_not_submit(self):
		self.assertTrue(frappe.has_permission("Project Diesel Fill", "write", user=self.accountant))
		self.assertFalse(frappe.has_permission("Project Diesel Fill", "submit", user=self.accountant))
		self.assertFalse(frappe.has_permission("Project Diesel Fill", "write", user=self.accounts_only))

	def test_card_user_edit_keeps_exception_and_its_stamps(self):
		f = self._new()
		f.reload()
		f.update({"price_exception": 1, "unit_price": 2.4, "exception_reason": "invoice"})
		self._as(self.accountant, f.save)
		f.reload()
		stamped = (f.exception_by, f.exception_on)
		set_diesel_price(self.company, 2.2)  # the audited original value must not drift
		f.litres = 50
		f.exception_by = self.card_user  # tampering is ignored
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual(flt(f.unit_price), 2.4)
		self.assertEqual(flt(f.amount), 120)
		self.assertEqual((f.exception_by, f.exception_on), stamped)
		self.assertEqual(flt(f.company_price), 2)
		f.unit_price = 3  # but the price itself is locked
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, f.save)
		f.reload()
		f.price_exception = 0  # and so is removing the exception
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, f.save)

	def _audit(self, name):
		return frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Project Diesel Fill",
				"reference_name": name,
				"comment_type": "Info",
			},
			fields=["owner", "content", "creation"],
			order_by="creation",
		)

	def _exception_fill(self):
		f = frappe.get_doc("Project Diesel Fill", self._new().name)
		f.update({"price_exception": 1, "unit_price": 2.4, "exception_reason": "invoice"})
		self._as(self.accountant, f.save)
		return frappe.get_doc("Project Diesel Fill", f.name)

	def test_removing_exception_needs_the_role_and_a_reason(self):
		f = self._exception_fill()
		set_diesel_price(self.company, 3)
		f.price_exception = 0  # a plain save, even by the exception role, cannot end it
		with self.assertRaises(frappe.ValidationError):
			self._as(self.accountant, f.save)
		doc = frappe.get_doc("Project Diesel Fill", f.name).as_dict()
		doc.update({"price_exception": 0, "exception_reason": ""})
		with self.assertRaises(frappe.ValidationError):  # nor through REST
			self._as(self.accountant, rest_save, doc)
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, remove_price_exception, f.name, "no longer valid")
		with self.assertRaises(frappe.ValidationError):
			self._as(self.accountant, remove_price_exception, f.name, "  ")
		row = frappe.db.get_value(
			"Project Diesel Fill", f.name, ["unit_price", "price_exception"], as_dict=True
		)
		self.assertEqual((flt(row.unit_price), row.price_exception), (2.4, 1))
		self._as(self.accountant, remove_price_exception, f.name, "supplier invoice corrected")
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source, f.price_exception), (3, "Company Price", 0))
		self.assertFalse(f.exception_by or f.exception_reason)
		last = self._audit(f.name)[-1]
		self.assertEqual(last.owner, self.accountant)
		for part in ("2.4", "3.0", "supplier invoice corrected"):
			self.assertIn(part, last.content)

	def test_new_exception_price_needs_its_own_reason(self):
		f = self._exception_fill()
		f.unit_price = 2.5  # same reason as before
		with self.assertRaises(frappe.ValidationError):
			self._as(self.accountant, f.save)
		f = frappe.get_doc("Project Diesel Fill", f.name)
		f.update({"unit_price": 2.5, "exception_reason": "second invoice"})
		self._as(self.accountant, f.save)
		last = self._audit(f.name)[-1]
		self.assertEqual(last.owner, self.accountant)
		for part in ("2.4", "2.5", "second invoice"):
			self.assertIn(part, last.content)

	def test_exception_on_a_saved_draft_is_audited(self):
		f = self._exception_fill()
		last = self._audit(f.name)[-1]
		self.assertEqual(last.owner, self.accountant)
		for part in ("2.0", "2.4", "invoice"):
			self.assertIn(part, last.content)
		self.assertEqual((f.exception_by, flt(f.company_price)), (self.accountant, 2))
		self.assertTrue(f.exception_on)

	def test_plain_edits_write_no_price_audit(self):
		f = self._exception_fill()
		count = len(self._audit(f.name))
		f.litres = 50
		self._as(self.card_user, f.save)
		self.assertEqual(len(self._audit(f.name)), count)

	def test_exception_role_is_configurable(self):
		_set("diesel_price_exception_role", "Card Manager")
		f = self._new()
		f.reload()
		f.update({"price_exception": 1, "unit_price": 2.4, "exception_reason": "invoice"})
		with self.assertRaises(frappe.PermissionError):
			self._as(self.accountant, f.save)

	# ---------- zero price (Q2) ----------

	def _zero(self, name):
		"""A fresh copy of the fill with a zero-price exception (a failed save leaves the
		in-memory document with a newer timestamp, so every attempt starts fresh)."""
		f = frappe.get_doc("Project Diesel Fill", name)
		f.update({"price_exception": 1, "unit_price": 0, "exception_reason": "free delivery"})
		return f

	def test_zero_price_refused_while_no_role_is_named(self):
		name = self._new().name
		with self.assertRaises(frappe.PermissionError):
			self._as(self.accountant, self._zero(name).save)
		with self.assertRaises(frappe.PermissionError):
			self._zero(name).save()  # Administrator too while the role is empty
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, rest_save, self._zero(name).as_dict())
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", name, "unit_price")), 2)

	def test_zero_price_with_named_role_and_reason(self):
		zero_user = _role_user("Card User", "Accounts Manager", "Purchase Manager")
		_set("diesel_zero_price_role", "Purchase Manager")
		name = self._new().name
		with self.assertRaises(frappe.PermissionError):
			self._as(self.accountant, self._zero(name).save)
		f = self._zero(name)
		self._as(zero_user, f.save)
		f.reload()
		self.assertEqual((f.price_source, flt(f.unit_price), flt(f.amount)), ("Exception", 0, 0))

	def test_negative_price_refused(self):
		f = self._new()
		f.reload()
		f.update({"price_exception": 1, "unit_price": -1, "exception_reason": "x"})
		with self.assertRaises(frappe.ValidationError):
			self._as(self.accountant, f.save)

	# ---------- old documents (Q3, Q4) ----------

	def test_company_price_change_never_touches_submitted_fills(self):
		f = self._new()
		approve_fill(f)
		f.submit()
		set_diesel_price(self.company, 3)
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", f.name, "unit_price")), 2)
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", f.name, "amount")), 200)

	# Owner 2026-10-20: a saved draft is never repriced when the company price changes.

	def test_company_price_draft_keeps_its_price_with_a_warning(self):
		f = self._new()
		set_diesel_price(self.company, 3)
		f.reload()
		frappe.clear_messages()
		f.save()
		self.assertEqual((flt(f.unit_price), f.price_source, flt(f.company_price)), (2, "Company Price", 2))
		messages = [str(m.get("message") if isinstance(m, dict) else m) for m in frappe.get_message_log()]
		self.assertTrue(any("3" in m for m in messages), messages)

	def test_non_financial_edits_keep_the_draft_price(self):
		f = self._as(self.card_user, self._new)
		set_diesel_price(self.company, 3)
		f = frappe.get_doc("Project Diesel Fill", f.name)
		f.update({"litres": 150, "remarks": "edited " + self.token})
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), flt(f.amount), f.price_source), (2, 300, "Company Price"))
		approve_fill(f)
		f.submit()  # the draft is final at the price it was created with
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", f.name, "unit_price")), 2)

	def test_new_price_applies_to_new_fills_only(self):
		old = self._new()
		set_diesel_price(self.company, 3)
		new = self._as(self.card_user, self._new)
		self.assertEqual(flt(new.unit_price), 3)
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", old.name, "unit_price")), 2)

	def test_card_user_cannot_reprice_a_draft_even_via_rest(self):
		f = self._as(self.card_user, self._new)
		set_diesel_price(self.company, 3)
		for change in ({"unit_price": 3}, {"price_source": "Exception", "company_price": 9}):
			doc = frappe.get_doc("Project Diesel Fill", f.name).as_dict()
			doc.update(change)
			try:
				self._as(self.card_user, rest_save, doc)
			except frappe.ValidationError:
				pass
			row = frappe.db.get_value(
				"Project Diesel Fill", f.name, ["unit_price", "price_source", "company_price"], as_dict=True
			)
			self.assertEqual(
				(flt(row.unit_price), row.price_source, flt(row.company_price)), (2, "Company Price", 2)
			)

	def test_moving_a_draft_to_another_company_needs_a_decision(self):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-DPL-CMOVE-" + self.token
		comp.abbr = "DC" + self.token[:3]
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		other = comp.insert(ignore_permissions=True).name
		set_diesel_price(other, 5)
		f = frappe.get_doc("Project Diesel Fill", self._new().name)
		f.update({"company": other, "project": self._other_project(other)})
		f.save()
		self.assertEqual((flt(f.unit_price), f.price_source), (2, "Needs Review"))

	def test_old_draft_keeps_its_price_and_needs_a_decision(self):
		f = self._legacy_draft(2.1)
		f.remarks = "edited"
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual(flt(f.unit_price), 2.1)  # never repriced silently
		self.assertEqual(f.price_source, "Needs Review")
		approve_fill(f)
		with self.assertRaises(frappe.ValidationError):
			f.submit()
		f.reload()
		f.unit_price = 2  # a Card User cannot just type the company price either
		with self.assertRaises(frappe.ValidationError):
			self._as(self.card_user, f.save)
		with self.assertRaises(frappe.PermissionError):  # an explicit price change is not a Card User's
			self._as(self.card_user, use_company_price, f.name, "typo")
		with self.assertRaises(frappe.ValidationError):  # the exception role must give a reason
			self._as(self.accountant, use_company_price, f.name, " ")
		self._as(self.accountant, use_company_price, f.name, "price agreed with the supplier")
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source), (2, "Company Price"))
		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Project Diesel Fill",
				"reference_name": f.name,
				"comment_type": "Info",
			},
			fields=["owner", "content"],
		)
		self.assertTrue(
			any(
				c.owner == self.accountant and "price agreed with the supplier" in c.content for c in comments
			),
			comments,
		)
		approve_fill(f)
		f.submit()
		self.assertEqual(f.docstatus, 1)

	def test_old_draft_price_approved_as_exception(self):
		f = self._legacy_draft(2.1)
		f.update({"price_exception": 1, "exception_reason": "price agreed before the lock"})
		self._as(self.accountant, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source), (2.1, "Exception"))
		approve_fill(f)
		f.submit()

	def test_old_draft_matching_company_price_passes(self):
		f = self._legacy_draft(2)
		f.save()
		self.assertEqual(f.price_source, "Company Price")

	def test_use_company_price_rules(self):
		f = self._legacy_draft(2.1)
		with self.assertRaises(frappe.PermissionError):
			self._as(self.accounts_only, use_company_price, f.name)
		f.update({"price_exception": 1, "exception_reason": "agreed"})
		self._as(self.accountant, f.save)
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, use_company_price, f.name, "reason")
		with self.assertRaises(frappe.ValidationError):  # an exception is changed on the form, not here
			self._as(self.accountant, use_company_price, f.name, "reason")

	def test_amended_copy_keeps_original_price_until_decided(self):
		f = self._new()
		approve_fill(f)
		f.submit()
		set_diesel_price(self.company, 3)
		f.cancel()
		a = frappe.copy_doc(f)
		a.amended_from = f.name
		a.docstatus = 0
		a.insert()
		self.assertEqual((flt(a.unit_price), a.price_source), (2, "Needs Review"))
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", f.name, "unit_price")), 2)

	# ---------- form endpoint ----------

	def test_price_context_for_the_form(self):
		ctx = self._as(self.card_user, get_diesel_price_context, self.company)
		self.assertEqual(flt(ctx["price"]), 2)
		self.assertFalse(ctx["can_except"] or ctx["can_zero"])
		ctx = self._as(self.accountant, get_diesel_price_context, self.company)
		self.assertTrue(ctx["can_except"])
		self.assertFalse(ctx["can_zero"])
		with self.assertRaises(frappe.PermissionError):
			self._as(_role_user("Website Manager"), get_diesel_price_context, self.company)

	def test_price_context_hides_other_companies(self):
		user = _role_user("Card User")
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-DPL-OTHER-" + self.token
		comp.abbr = "DP" + self.token[:3]
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		other = comp.insert(ignore_permissions=True).name
		set_diesel_price(other, 5)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Company", "for_value": self.company}
		).insert(ignore_permissions=True)
		ctx = self._as(user, get_diesel_price_context, other)
		self.assertEqual((ctx["price"], ctx["can_except"]), (0, False))

	def test_endpoint_methods(self):
		from card.card.doctype.project_diesel_fill import project_diesel_fill as m

		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[m.get_diesel_price_context], ["GET"]
		)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[m.use_company_price], ["POST"])
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[m.remove_price_exception], ["POST"])

	def test_amended_zero_price_copy_is_not_repriced_silently(self):
		zero_user = _role_user("Card User", "Accounts Manager", "Purchase Manager")
		_set("diesel_zero_price_role", "Purchase Manager")
		f = frappe.get_doc("Project Diesel Fill", self._new().name)
		f.update({"price_exception": 1, "unit_price": 0, "exception_reason": "free delivery"})
		self._as(zero_user, f.save)
		f.reload()
		approve_fill(f)
		f.submit()
		f.cancel()
		a = frappe.copy_doc(f)
		a.amended_from = f.name
		a.docstatus = 0
		a.insert()
		self.assertEqual((flt(a.unit_price), a.price_source), (0, "Needs Review"))

	def test_moving_an_exception_fill_to_another_company_needs_the_role(self):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-DPL-MOVE-" + self.token
		comp.abbr = "DM" + self.token[:3]
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		other = comp.insert(ignore_permissions=True).name
		set_diesel_price(other, 5)
		f = frappe.get_doc("Project Diesel Fill", self._new().name)
		f.update({"price_exception": 1, "unit_price": 2.4, "exception_reason": "invoice"})
		self._as(self.accountant, f.save)
		f = frappe.get_doc("Project Diesel Fill", f.name)
		f.update({"company": other, "project": self._other_project(other)})
		with self.assertRaises(frappe.PermissionError):
			self._as(self.card_user, f.save)

	def test_amended_exception_needs_a_new_approval(self):
		f = frappe.get_doc("Project Diesel Fill", self._new().name)
		f.update({"price_exception": 1, "unit_price": 2.4, "exception_reason": "invoice"})
		self._as(self.accountant, f.save)
		f.reload()
		approve_fill(f)
		f.submit()
		f.cancel()
		copied = frappe.copy_doc(f)
		copied.update({"amended_from": f.name, "docstatus": 0})
		copied.insert()  # the copied approval does not carry over
		self.assertEqual((flt(copied.unit_price), copied.price_source), (2.4, "Needs Review"))
		self.assertFalse(copied.price_exception or copied.exception_by)
		frappe.delete_doc("Project Diesel Fill", copied.name, force=True)  # the next amend reuses its name
		again = frappe.copy_doc(f)
		again.update({"amended_from": f.name, "docstatus": 0, "exception_reason": "invoice re-checked"})
		self._as(self.accountant, again.insert)  # a new reason from the role is a new approval
		self.assertEqual((again.price_source, again.exception_by), ("Exception", self.accountant))
