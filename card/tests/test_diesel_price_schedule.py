# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-125 (#46, #124 WP-10): an effective-dated diesel price schedule per company. A fill takes the
price of its company's row with the latest valid_from on or before the fill date; with no such row,
the company's diesel_unit_price exactly as before. Submitted fills keep their saved price."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, nowdate

from card.card.doctype.project_diesel_fill.project_diesel_fill import (
	diesel_price,
	get_diesel_price_context,
)
from card.patches.v4_7_0 import seed_diesel_price_schedule
from card.tests.diesel_price import approve_fill, set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _role_user, _set

PARENT = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "diesel_price_schedule"}


def add_price(company, valid_from, price):
	"""One schedule row, written on its own (rolled back with the test)."""
	frappe.get_doc(
		{
			"doctype": "Card Diesel Price",
			**PARENT,
			"company": company,
			"valid_from": valid_from,
			"unit_price": price,
		}
	).db_insert()


class TestDieselPriceSchedule(IntegrationTestCase):
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
		self.project = self._project(self.company)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DPS-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		set_diesel_price(self.company, 2)  # also clears the company's schedule rows
		self.card_user = _role_user("Card User")
		self.accountant = _role_user("Card User", "Accounts Manager")
		frappe.clear_messages()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- helpers ----------

	def _project(self, company):
		p = frappe.new_doc("Project")
		p.project_name = "TEST-DPS-PRJ-" + frappe.generate_hash(length=8)
		p.company = company
		return p.insert(ignore_permissions=True).name

	def _company(self):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-DPS-C-" + frappe.generate_hash(length=8)
		comp.abbr = "DS" + frappe.generate_hash(length=4)
		comp.default_currency = frappe.get_cached_value("Company", self.company, "default_currency")
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

	def _schedule_rows(self, company):
		return frappe.get_all(
			"Card Diesel Price",
			filters={**PARENT, "company": company},
			fields=["valid_from", "unit_price", "currency"],
		)

	def _settings_with(self, *rows):
		"""Card Settings in memory with extra schedule rows; only the schedule rule is run."""
		settings = frappe.get_single("Card Settings")
		for company, valid_from, price in rows:
			settings.append(
				"diesel_price_schedule", {"company": company, "valid_from": valid_from, "unit_price": price}
			)
		return settings

	def _messages(self):
		return " ".join(str(m.get("message") if isinstance(m, dict) else m) for m in frappe.local.message_log)

	# ---------- no rows: unchanged ----------

	def test_no_rows_keeps_the_company_price(self):
		self.assertFalse(self._schedule_rows(self.company))
		f = self._as(self.card_user, self._new)
		self.assertEqual((flt(f.unit_price), f.price_source, flt(f.company_price)), (2, "Company Price", 2))
		self.assertEqual(diesel_price(self.company, "2020-01-01"), 2)
		self.assertEqual(diesel_price(self.company), 2)

	# ---------- price by date ----------

	def test_price_by_date_and_boundaries(self):
		add_price(self.company, "2026-09-01", 3)
		add_price(self.company, "2026-10-01", 4)
		cases = {
			"2026-08-31": 2,  # before the first row: the company's diesel unit price
			"2026-09-01": 3,  # valid_from itself
			"2026-09-30": 3,
			"2026-10-01": 4,
			"2027-01-01": 4,
		}
		for date, price in cases.items():
			with self.subTest(date=date):
				self.assertEqual(diesel_price(self.company, date), price)
				f = self._as(self.card_user, self._new, date=date)
				self.assertEqual((flt(f.unit_price), flt(f.company_price)), (price, price))
				self.assertEqual(flt(f.amount), 100 * price)
				self.assertEqual(f.price_source, "Company Price")

	def test_form_context_uses_the_fill_date(self):
		add_price(self.company, "2026-09-01", 3)
		ctx = self._as(self.card_user, get_diesel_price_context, self.company, "2026-09-10")
		self.assertEqual(flt(ctx["price"]), 3)
		ctx = self._as(self.card_user, get_diesel_price_context, self.company, "2026-08-10")
		self.assertEqual(flt(ctx["price"]), 2)

	def test_typed_price_of_another_period_refused(self):
		add_price(self.company, "2026-09-01", 3)
		with self.assertRaises(frappe.ValidationError):
			self._as(self.card_user, self._new, date="2026-09-10", unit_price=2)

	# ---------- snapshot ----------

	def test_submitted_fill_never_changes(self):
		f = self._new(date="2026-09-15")
		approve_fill(f)
		f.submit()
		add_price(self.company, "2026-09-01", 9)
		f.reload()
		self.assertEqual((flt(f.unit_price), flt(f.amount), flt(f.company_price)), (2, 200, 2))
		self.assertEqual(f.docstatus, 1)

	def test_saved_draft_keeps_its_price(self):
		f = self._new(date="2026-09-15")
		add_price(self.company, "2026-09-01", 3)
		f.reload()
		f.remarks = "edited"
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source), (2, "Company Price"))

	def test_draft_moved_to_another_price_period_needs_review(self):
		add_price(self.company, "2026-09-01", 3)
		f = self._new(date="2026-08-20")  # before the first row: the diesel unit price 2
		self.assertEqual((flt(f.unit_price), f.price_source), (2, "Company Price"))
		f.date = "2026-08-25"  # same price on the new date
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source, flt(f.company_price)), (2, "Company Price", 2))
		f.date = "2026-09-10"  # the schedule price 3 applies on the new date
		self._as(self.card_user, f.save)
		f.reload()
		self.assertEqual((flt(f.unit_price), f.price_source, flt(f.company_price)), (2, "Needs Review", 3))
		approve_fill(f)
		with self.assertRaises(frappe.ValidationError):
			f.submit()  # the mismatch is decided before submit

	def test_backdated_row_lists_submitted_fills(self):
		f = self._new(date="2026-09-15")
		approve_fill(f)
		f.submit()
		settings = self._settings_with((self.company, "2026-09-01", 3))
		settings._validate_diesel_price_schedule()
		self.assertIn("submitted diesel fills", self._messages())
		self.assertEqual(flt(frappe.db.get_value("Project Diesel Fill", f.name, "unit_price")), 2)
		frappe.clear_messages()
		settings = self._settings_with((self.company, "2026-10-01", 3))
		settings._validate_diesel_price_schedule()
		self.assertNotIn(self.company, self._messages())  # no submitted fill on or after that date

	# ---------- validation ----------

	def test_duplicate_date_refused(self):
		settings = self._settings_with((self.company, "2026-09-01", 3), (self.company, "2026-09-01", 4))
		with self.assertRaises(frappe.ValidationError):
			settings._validate_diesel_price_schedule()

	def test_zero_or_negative_price_refused(self):
		for price in (-1, 0):
			with self.subTest(price=price):
				settings = self._settings_with((self.company, "2026-09-01", price))
				with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
					settings._validate_diesel_price_schedule()
		self.assertTrue(frappe.get_meta("Card Diesel Price").get_field("unit_price").reqd)

	def test_unit_price_is_locked_while_a_schedule_exists(self):
		add_price(self.company, "2026-09-01", 3)
		settings = frappe.get_single("Card Settings")
		settings._doc_before_save = frappe.get_single("Card Settings")
		row = next(r for r in settings.company_settings if r.company == self.company)
		row.diesel_unit_price = 2.5
		with self.assertRaisesRegex(frappe.ValidationError, "adding a dated row"):
			settings._validate_diesel_price_schedule()
		row.diesel_unit_price = 2  # unchanged: allowed
		settings._validate_diesel_price_schedule()
		# without a schedule the price is edited as before
		set_diesel_price(self.company, 2)
		settings = frappe.get_single("Card Settings")
		settings._doc_before_save = frappe.get_single("Card Settings")
		next(r for r in settings.company_settings if r.company == self.company).diesel_unit_price = 2.5
		settings._validate_diesel_price_schedule()

	def test_restricted_accounts_manager_cannot_change_another_companys_rows(self):
		other = self._company()
		set_diesel_price(other, 5)
		add_price(other, "2026-09-01", 6)
		manager = _role_user("Accounts Manager")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": manager,
				"allow": "Company",
				"for_value": self.company,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(manager)
		settings = frappe.get_doc("Card Settings")
		next(r for r in settings.diesel_price_schedule if r.company == other).unit_price = 7
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to change the Card settings"):
			settings.save(ignore_permissions=True)  # the CARD scope check, without Frappe's link check
		settings = frappe.get_doc("Card Settings")
		settings.append(
			"diesel_price_schedule", {"company": other, "valid_from": "2026-10-01", "unit_price": 8}
		)
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to change the Card settings"):
			settings.save(ignore_permissions=True)
		frappe.set_user("Administrator")
		self.assertEqual([flt(r.unit_price) for r in self._schedule_rows(other)], [6])

	def test_session_import_checks_the_session_date_price(self):
		from card.diesel_import import _check_price

		add_price(self.company, "2026-09-01", 3)
		_check_price({"company": self.company, "date": "2026-09-10", "unit_price": 3})
		with self.assertRaises(frappe.ValidationError):
			_check_price({"company": self.company, "date": "2026-08-10", "unit_price": 3})
		_check_price({"company": self.company, "date": "2026-08-10", "unit_price": 2})

	def test_currency_defaults_to_company_currency(self):
		settings = self._settings_with((self.company, "2026-09-01", 3))
		settings._validate_diesel_price_schedule()
		row = settings.diesel_price_schedule[-1]
		self.assertEqual(row.currency, frappe.get_cached_value("Company", self.company, "default_currency"))
		other = "USD" if row.currency != "USD" else "EUR"
		if frappe.db.exists("Currency", other):
			row.currency = other
			with self.assertRaises(frappe.ValidationError):
				settings._validate_diesel_price_schedule()

	def test_same_date_in_two_companies_allowed(self):
		other = self._company()
		settings = self._settings_with((self.company, "2026-09-01", 3), (other, "2026-09-01", 4))
		settings._validate_diesel_price_schedule()

	# ---------- multi-company ----------

	def test_each_company_has_its_own_schedule(self):
		other = self._company()
		set_diesel_price(other, 5)
		add_price(other, "2026-09-01", 6)
		self.assertEqual(diesel_price(self.company, "2026-09-15"), 2)
		self.assertEqual(diesel_price(other, "2026-09-15"), 6)
		f = self._new(date="2026-09-15", company=other, project=self._project(other))
		self.assertEqual(flt(f.unit_price), 6)
		mine = self._new(date="2026-09-15")
		self.assertEqual(flt(mine.unit_price), 2)

	# ---------- FR-002 exception ----------

	def test_price_exception_still_works(self):
		add_price(self.company, "2026-09-01", 3)
		f = self._as(
			self.accountant,
			self._new,
			date="2026-09-15",
			unit_price=2.5,
			price_exception=1,
			exception_reason="supplier discount",
		)
		self.assertEqual((flt(f.unit_price), f.price_source, flt(f.company_price)), (2.5, "Exception", 3))
		with self.assertRaises(frappe.PermissionError):
			self._as(
				self.card_user,
				self._new,
				date="2026-09-15",
				unit_price=2.5,
				price_exception=1,
				exception_reason="x",
			)

	# ---------- patch ----------

	def test_patch_seeds_once(self):
		with_fills = self._company()
		project = self._project(with_fills)
		set_diesel_price(with_fills, 1.8)
		self._new(date="2026-09-15", company=with_fills, project=project)
		self._new(date="2026-08-03", company=with_fills, project=project)
		without_fills = self._company()
		set_diesel_price(without_fills, 1.9)
		no_price = self._company()
		set_diesel_price(no_price, 0)
		seeded = self._company()
		set_diesel_price(seeded, 2.4)
		add_price(seeded, "2026-01-01", 2.3)

		seed_diesel_price_schedule.execute()
		seed_diesel_price_schedule.execute()  # a second migrate adds nothing

		rows = self._schedule_rows(with_fills)
		self.assertEqual(len(rows), 1)
		self.assertEqual((getdate(rows[0].valid_from), flt(rows[0].unit_price)), (getdate("2026-08-03"), 1.8))
		self.assertEqual(rows[0].currency, frappe.get_cached_value("Company", with_fills, "default_currency"))
		rows = self._schedule_rows(without_fills)
		self.assertEqual(
			[(getdate(r.valid_from), flt(r.unit_price)) for r in rows], [(getdate(nowdate()), 1.9)]
		)
		self.assertFalse(self._schedule_rows(no_price))
		rows = self._schedule_rows(seeded)
		self.assertEqual([flt(r.unit_price) for r in rows], [2.3])  # an existing schedule is left alone
		# diesel_unit_price is not changed
		self.assertEqual(
			flt(
				frappe.db.get_value(
					"Card Company Settings",
					{"parent": "Card Settings", "company": with_fills},
					"diesel_unit_price",
				)
			),
			1.8,
		)
		# every price stays what it was: the earliest fill date and later take the same price
		self.assertEqual(diesel_price(with_fills, "2026-08-03"), 1.8)
		self.assertEqual(diesel_price(with_fills, "2026-08-01"), 1.8)
