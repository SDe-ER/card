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
		path = os.path.join(
			frappe.get_app_path("card"), "card", "doctype", doctype_dir, fname
		)
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


class TestSingleCompany(IntegrationTestCase):
	def test_additional_company_blocked(self):
		from card.company import single_company

		self.assertTrue(single_company())
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-F8-SUB-" + frappe.generate_hash(length=6)
		comp.abbr = "F8" + frappe.generate_hash(length=3)
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		old_flag = frappe.flags.in_test
		frappe.flags.in_test = False  # the guard exempts test runs; simulate real usage
		try:
			with self.assertRaises(frappe.ValidationError):
				comp.insert(ignore_permissions=True)
		finally:
			frappe.flags.in_test = old_flag
			frappe.db.rollback()