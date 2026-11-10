# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-132 (#46, #124 WP-X): each diesel fill keeps, next to its company price, the currency, the unit
and the valid-from date of the price it was resolved from. The price itself is unchanged (FR-125) and
no unit conversion is made: an empty unit means per litre. The snapshot follows company_price: it is
set when the price is resolved, kept wherever the price is kept, never copied by Duplicate or Amend,
and never changed after submit or on cancel. Card Diesel Price gets a fuel type, "Diesel" by default."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from card.card.doctype.project_diesel_fill.project_diesel_fill import diesel_price, diesel_price_details
from card.tests.cancel_reason import with_reason
from card.tests.diesel_price import approve_fill, set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_diesel_price_schedule import PARENT, add_price
from card.tests.test_settings_wiring import _role_user, _set

SNAPSHOT = ("price_currency", "price_uom", "price_valid_from")


def add_row(company, valid_from, price, currency=None, uom=None):
	"""One schedule row with a currency and a unit, written on its own (rolled back with the test)."""
	frappe.get_doc(
		{
			"doctype": "Card Diesel Price",
			**PARENT,
			"company": company,
			"valid_from": valid_from,
			"unit_price": price,
			"currency": currency,
			"uom": uom,
		}
	).db_insert()


class TestFillPriceSnapshot(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.company = self._m["company"]
		self.currency = frappe.get_cached_value("Company", self.company, "default_currency")
		_set("period_lock_date", None)
		_set("diesel_supplier", None)
		_set("diesel_supplier_policy", "متغير")
		_set("diesel_price_exception_role", "Accounts Manager")
		_set("diesel_zero_price_role", None)
		self.project = self._project(self.company)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-FPS-SUP-" + frappe.generate_hash(length=8)
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		set_diesel_price(self.company, 2)  # also clears the company's schedule rows
		self.card_user = _role_user("Card User")
		self.accountant = _role_user("Card User", "Accounts Manager")
		if not frappe.db.exists("UOM", "Litre"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Litre"}).insert(ignore_permissions=True)
		frappe.clear_messages()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- helpers ----------

	def _project(self, company):
		p = frappe.new_doc("Project")
		p.project_name = "TEST-FPS-PRJ-" + frappe.generate_hash(length=8)
		p.company = company
		return p.insert(ignore_permissions=True).name

	def _company(self, currency):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-FPS-C-" + frappe.generate_hash(length=8)
		comp.abbr = "FP" + frappe.generate_hash(length=4)
		comp.default_currency = currency
		comp.country = frappe.get_cached_value("Company", self.company, "country")
		return comp.insert(ignore_permissions=True).name

	def _new(self, date="2026-09-15", company=None, project=None, **extra):
		data = {
			"doctype": "Project Diesel Fill",
			"date": date,
			"project": project or self.project,
			"supplier": self.supplier,
			"company": company or self.company,
			"litres": 100,
		}
		data.update(extra)
		return frappe.get_doc(data).insert()

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _snapshot(self, fill):
		fill.reload()
		return (
			flt(fill.company_price),
			fill.price_currency,
			fill.price_uom,
			getdate(fill.price_valid_from) if fill.price_valid_from else None,
		)

	# ---------- schema ----------

	def test_snapshot_fields_are_read_only_and_not_copied(self):
		meta = frappe.get_meta("Project Diesel Fill")
		for fieldname in SNAPSHOT:
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertTrue(field.read_only)
				self.assertTrue(field.no_copy)
		self.assertEqual(meta.get_field("price_currency").options, "Currency")
		self.assertEqual(meta.get_field("price_uom").options, "UOM")

	def test_fuel_type_defaults_to_diesel(self):
		field = frappe.get_meta("Card Diesel Price").get_field("fuel_type")
		self.assertEqual((field.fieldtype, field.options, field.default), ("Select", "Diesel", "Diesel"))
		row = frappe.new_doc("Card Diesel Price")
		self.assertEqual(row.fuel_type, "Diesel")
		add_price(self.company, "2026-09-01", 3)  # a row written without a fuel type
		self.assertEqual(diesel_price(self.company, "2026-09-15"), 3)  # the price is unchanged

	# ---------- years-long price ----------

	def test_years_long_price_is_snapshotted_on_every_fill(self):
		add_row(self.company, "2020-01-01", 3, self.currency)
		for date in ("2020-01-01", "2023-06-30", "2026-09-15"):
			with self.subTest(date=date):
				f = self._new(date=date)
				self.assertEqual(flt(f.unit_price), 3)
				self.assertEqual(self._snapshot(f), (3, self.currency, None, getdate("2020-01-01")))

	# ---------- mid-month change ----------

	def test_mid_month_change_snapshots_the_period_of_the_fill_date(self):
		add_row(self.company, "2026-09-01", 3, self.currency)
		add_row(self.company, "2026-09-16", 4, self.currency, "Litre")
		before = self._new(date="2026-09-15")
		on = self._new(date="2026-09-16")
		after = self._new(date="2026-09-30")
		self.assertEqual(self._snapshot(before), (3, self.currency, None, getdate("2026-09-01")))
		self.assertEqual(self._snapshot(on), (4, self.currency, "Litre", getdate("2026-09-16")))
		self.assertEqual(self._snapshot(after), (4, self.currency, "Litre", getdate("2026-09-16")))
		self.assertEqual([flt(f.unit_price) for f in (before, on, after)], [3, 4, 4])

	def test_draft_moved_to_another_period_takes_that_periods_snapshot(self):
		add_row(self.company, "2026-09-01", 3, self.currency)
		add_row(self.company, "2026-09-16", 4, self.currency, "Litre")
		f = self._new(date="2026-09-10")
		f.date = "2026-09-20"
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source), (3, "Needs Review"))
		self.assertEqual(self._snapshot(f), (4, self.currency, "Litre", getdate("2026-09-16")))

	def test_saved_draft_keeps_its_snapshot_with_its_price(self):
		add_row(self.company, "2026-09-01", 3, self.currency)
		f = self._new(date="2026-09-15")
		frappe.db.delete("Card Diesel Price", {**PARENT, "company": self.company})
		add_row(self.company, "2026-09-01", 5, self.currency, "Litre")  # the period's price is changed
		f.reload()
		f.remarks = "edited"
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source), (3, "Company Price"))
		self.assertEqual(self._snapshot(f), (3, self.currency, None, getdate("2026-09-01")))

	# ---------- backdated entry ----------

	def test_backdated_fill_before_the_first_row_snapshots_the_company_price(self):
		add_row(self.company, "2026-09-01", 3, self.currency)
		f = self._new(date="2026-08-10")  # entered today, dated before the schedule
		self.assertEqual(flt(f.unit_price), 2)
		self.assertEqual(self._snapshot(f), (2, self.currency, None, None))

	def test_backdated_fill_in_an_old_period_snapshots_that_period(self):
		add_row(self.company, "2025-01-01", 2.5, self.currency)
		add_row(self.company, "2026-09-01", 3, self.currency, "Litre")
		f = self._new(date="2025-06-01")
		self.assertEqual(flt(f.unit_price), 2.5)
		self.assertEqual(self._snapshot(f), (2.5, self.currency, None, getdate("2025-01-01")))

	# ---------- missing price ----------

	def test_missing_price_refuses_the_fill_and_resolves_nothing(self):
		set_diesel_price(self.company, 0)
		self.assertEqual(
			diesel_price_details(self.company, "2026-09-15"),
			{"price": 0, "currency": None, "uom": None, "valid_from": None},
		)
		self.assertEqual(diesel_price_details(None).price, 0)
		with self.assertRaisesRegex(frappe.ValidationError, "No approved diesel price"):
			self._as(self.card_user, self._new, date="2026-09-15")

	def test_exception_without_a_company_price_has_an_empty_snapshot(self):
		set_diesel_price(self.company, 0)
		f = self._as(
			self.accountant,
			self._new,
			date="2026-09-15",
			unit_price=2.5,
			price_exception=1,
			exception_reason="no approved price yet",
		)
		self.assertEqual((flt(f.unit_price), f.price_source), (2.5, "Exception"))
		self.assertEqual(self._snapshot(f), (0, None, None, None))

	def test_unchanged_exception_keeps_its_snapshot(self):
		add_row(self.company, "2026-09-01", 3, self.currency)
		f = self._as(
			self.accountant,
			self._new,
			date="2026-09-15",
			unit_price=2.5,
			price_exception=1,
			exception_reason="supplier discount",
		)
		frappe.db.delete("Card Diesel Price", {**PARENT, "company": self.company})
		add_row(self.company, "2026-09-10", 4, self.currency, "Litre")
		f.reload()
		f.litres = 120
		self._as(self.card_user, f.save)
		self.assertEqual(self._snapshot(f), (3, self.currency, None, getdate("2026-09-01")))

	# ---------- two companies, two currencies ----------

	def test_two_companies_with_two_currencies(self):
		other_currency = "USD" if self.currency != "USD" else "EUR"
		if not frappe.db.exists("Currency", other_currency):
			frappe.get_doc({"doctype": "Currency", "currency_name": other_currency, "enabled": 1}).insert(
				ignore_permissions=True
			)
		other = self._company(other_currency)
		set_diesel_price(other, 5)
		add_row(self.company, "2026-09-01", 3, self.currency)
		add_row(other, "2026-09-01", 6, other_currency, "Litre")
		mine = self._new(date="2026-09-15")
		theirs = self._new(date="2026-09-15", company=other, project=self._project(other))
		self.assertEqual(self._snapshot(mine), (3, self.currency, None, getdate("2026-09-01")))
		self.assertEqual(self._snapshot(theirs), (6, other_currency, "Litre", getdate("2026-09-01")))
		# before the first row each company's own price, in its own currency, no conversion
		old = self._new(date="2026-08-15", company=other, project=theirs.project)
		self.assertEqual(self._snapshot(old), (5, other_currency, None, None))

	def test_row_without_currency_snapshots_the_company_currency(self):
		add_row(self.company, "2026-09-01", 3)
		f = self._new(date="2026-09-15")
		self.assertEqual(self._snapshot(f), (3, self.currency, None, getdate("2026-09-01")))

	# ---------- submit, cancel, amend ----------

	def test_submit_and_cancel_never_change_the_snapshot(self):
		add_row(self.company, "2026-09-01", 3, self.currency, "Litre")
		f = self._new(date="2026-09-15")
		approve_fill(f)
		f.submit()
		expected = (3, self.currency, "Litre", getdate("2026-09-01"))
		self.assertEqual(self._snapshot(f), expected)
		frappe.db.delete("Card Diesel Price", {**PARENT, "company": self.company})
		add_row(self.company, "2026-09-10", 9, self.currency)  # a later schedule edit
		self.assertEqual(self._snapshot(f), expected)
		with_reason(f).cancel()
		self.assertEqual(f.docstatus, 2)
		self.assertEqual(self._snapshot(f), expected)
		self.assertEqual(flt(f.unit_price), 3)

	def test_amendment_resolves_its_own_snapshot(self):
		add_row(self.company, "2026-09-01", 3, self.currency, "Litre")
		f = self._new(date="2026-09-15")
		approve_fill(f)
		f.submit()
		with_reason(f).cancel()
		frappe.db.delete("Card Diesel Price", {**PARENT, "company": self.company})
		add_row(self.company, "2026-09-10", 4, self.currency)
		duplicate = frappe.copy_doc(f, ignore_no_copy=False)  # Duplicate leaves no_copy fields out
		for fieldname in SNAPSHOT:
			self.assertFalse(duplicate.get(fieldname))
		amended = frappe.copy_doc(f)  # an amendment may carry the old values; validate replaces them
		self.assertEqual(amended.price_uom, "Litre")
		amended.amended_from = f.name
		amended.docstatus = 0
		amended.insert()
		self.assertEqual((flt(amended.unit_price), amended.price_source), (3, "Needs Review"))
		self.assertEqual(self._snapshot(amended), (4, self.currency, None, getdate("2026-09-10")))
