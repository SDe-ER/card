# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""F-phase guard rails: the fiscal-year back-entry window, the single-company
rule, and the byte-integrity of the direction Select options (the Arabic values
carry diacritics — a retyped copy that LOOKS identical but differs in combining
marks breaks every card save, so the doctype JSONs must be byte-equal to
card/constants.py)."""

import json
import os

import frappe
from frappe.tests import IntegrationTestCase

from card.constants import DIR_INTERNAL, DIR_RENTED_IN, DIR_RENTED_OUT, DIR_SUBRENTAL
from card.tests.test_controllers import _days, _ensure_masters

DIRECTION_OPTIONS = "\n" + "\n".join([DIR_RENTED_IN, DIR_RENTED_OUT, DIR_SUBRENTAL, DIR_INTERNAL])


class TestDirectionOptionBytes(IntegrationTestCase):
	def _field(self, doctype_dir, fname, fieldname):
		path = os.path.join(frappe.get_app_path("card"), "card", "doctype", doctype_dir, fname)
		data = json.load(open(path, encoding="utf-8"))
		return next(f for f in data["fields"] if f.get("fieldname") == fieldname)

	def test_options_byte_equal_constants(self):
		eq = self._field("card_equipment", "card_equipment.json", "rental_direction")
		self.assertEqual(eq["options"], DIRECTION_OPTIONS)
		card = self._field("card_monthly_card", "card_monthly_card.json", "card_direction")
		self.assertEqual(card["options"], DIRECTION_OPTIONS)


class TestFiscalYearWindow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def test_previous_fiscal_year_card_rejected(self):
		try:
			from erpnext.accounts.utils import get_fiscal_year

			fy = get_fiscal_year(frappe.utils.nowdate(), company=self._m["company"])
		except Exception:
			self.skipTest("no fiscal year configured for today")
		prev_year = frappe.utils.getdate(fy[1]).year - 1
		d = frappe.new_doc("Card Equipment")
		d.company = self._m["company"]
		d.equipment_type = self._m["etype"]
		d.ownership = "ملك"
		d.equipment_name = "TEST-FY-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.insert(ignore_permissions=True)
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = d.name
		c.project = self._m["project"]
		c.shift = "نهاري"
		c.month = "12"
		c.year = prev_year
		for row in _days([8], year=prev_year, month=12):
			c.append("days", row)
		with self.assertRaises(frappe.ValidationError):
			c.insert(ignore_permissions=True)


class TestCompanyConsistency(IntegrationTestCase):
	"""F.8 (owner amendment): a second company is NEVER blocked — CARD validates
	consistency instead: document company = equipment company, and configured
	accounts belong to their row's company."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-F8-OTHER-" + self.token
		comp.abbr = "F8" + self.token[:3]
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		comp.insert(ignore_permissions=True)  # allowed: creation is never blocked
		self.other_company = comp.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def _equipment(self):
		d = frappe.new_doc("Card Equipment")
		d.company = self._m["company"]
		d.equipment_type = self._m["etype"]
		d.ownership = "ملك"
		d.equipment_name = "TEST-F8-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.insert(ignore_permissions=True)
		return d

	def _supplier(self):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-F8-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def test_second_company_is_allowed(self):
		from card.company import single_company

		self.assertTrue(single_company())
		self.assertTrue(frappe.db.exists("Company", self.other_company))

	def test_transport_company_must_match_equipment(self):
		eq = self._equipment()
		t = frappe.new_doc("Equipment Transport")
		t.equipment = eq.name
		t.project = self._m["project"]
		t.date = frappe.utils.nowdate()
		t.transport_supplier = self._supplier()
		t.company = self.other_company
		t.amount = 100
		with self.assertRaises(frappe.ValidationError):
			t.insert(ignore_permissions=True)

	def test_diesel_fill_company_must_match_equipment(self):
		eq = self._equipment()
		f = frappe.new_doc("Project Diesel Fill")
		f.date = frappe.utils.nowdate()
		f.project = self._m["project"]
		f.supplier = self._supplier()
		f.card_equipment = eq.name
		f.company = self.other_company
		f.litres = 10
		f.unit_price = 2
		with self.assertRaises(frappe.ValidationError):
			f.insert(ignore_permissions=True)

	def test_settings_account_must_belong_to_row_company(self):
		cash_other = frappe.db.get_value(
			"Account", {"company": self.other_company, "account_type": "Cash", "is_group": 0}, "name"
		)
		self.assertTrue(cash_other, "the scratch company has no Cash account")
		settings = frappe.get_doc("Card Settings")
		# a clean CI site has no seeded company rows; the check is per-row anyway
		row = next((r for r in settings.company_settings if r.company == self._m["company"]), None)
		if row is None:
			row = settings.append("company_settings", {"company": self._m["company"]})
		row.bank_cash_account = cash_other  # other company's account on TEC's row
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)
