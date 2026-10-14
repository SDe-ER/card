# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Wiring tests for Card Settings -> equipment defaults and report behaviour
(app-level so Frappe does not auto-build dependency test records). Each test
proves that changing the setting changes behaviour AND that the baseline
value reproduces the pre-settings behaviour. Setting writes and all records
are rolled back by the test transaction."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.settings import setting
from card.tests.test_controllers import _days, _ensure_masters

FUEL_FIELD = "الوقود_على"
LESSOR = "المؤجر"
COMPANY = "الشركة"
OWNED = "ملك"
SUPPLIER_STATEMENT = "مورد"
OWNED_STATEMENT = "معدات ملك"


def _set(field, value):
	frappe.db.set_single_value("Card Settings", field, value)
	# flipping single values mid-test: drop any cached single value so the next
	# setting() read is fresh (production rarely re-reads within one request).
	frappe.clear_document_cache("Card Settings", "Card Settings")


def _statement(filters):
	from card.card.report.equipment_supplier_statement.equipment_supplier_statement import execute

	columns, rows, message, _chart, summary, _flag = execute(filters)
	return columns, rows, message, summary


def _summary_report(filters):
	from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute

	columns, rows, message, _chart, summary, _flag = execute(filters)
	return columns, rows, message, summary


def _indicator(summary, label):
	for item in summary:
		if item["label"] == frappe._(label):
			return item["indicator"]
	return None


class TestCardSettingsWiring(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		# A project of its own so report assertions are not polluted by other site data.
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		frappe.db.rollback()

	# ---------- helpers ----------

	def _equipment(self, name_suffix="", ownership="إيجار"):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self.etype
		d.ownership = ownership
		d.equipment_name = "TEST-EQ-" + self.token + name_suffix
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		if ownership != OWNED:
			d.supplier = self.supplier
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _card(self, eq, hours_list, submit=False):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _statement_filters(self, **kw):
		f = {"from_month": 9, "from_year": 2026, "project": self.project}
		f.update(kw)
		return f

	# ---------- 1. equipment new-record defaults ----------

	def test_equipment_defaults_from_settings(self):
		_set("default_daily_hours", 8)
		_set("default_fuel_charged_to", COMPANY)
		_set("default_operator_on", COMPANY)

		def make(**kw):
			d = frappe.new_doc("Card Equipment")
			d.company = self.company
			d.equipment_type = self.etype
			d.ownership = "إيجار"
			d.supplier = self.supplier
			d.equipment_name = "TEST-EQ-" + frappe.generate_hash(length=8)
			for key, value in kw.items():
				d.set(key, value)
			d.insert(ignore_permissions=True)
			d.reload()
			return d

		# daily_hours / fuel / operator_on left blank -> defaulted from settings.
		# operator_on no longer carries a hardcoded DocType default, so the
		# Card Settings value governs a new record.
		eq = make()
		self.assertEqual(flt(eq.daily_hours), 8.0)
		self.assertEqual(eq.get(FUEL_FIELD), COMPANY)
		self.assertEqual(eq.operator_on, COMPANY)

		# a provided value is never overridden
		eq2 = make(daily_hours=5, operator_on=LESSOR, **{FUEL_FIELD: LESSOR})
		self.assertEqual(flt(eq2.daily_hours), 5.0)
		self.assertEqual(eq2.operator_on, LESSOR)
		self.assertEqual(eq2.get(FUEL_FIELD), LESSOR)

		# existing (not new) equipment is untouched when settings change later
		_set("default_daily_hours", 12)
		_set("default_fuel_charged_to", LESSOR)
		_set("default_operator_on", LESSOR)
		eq.save(ignore_permissions=True)
		eq.reload()
		self.assertEqual(flt(eq.daily_hours), 8.0)
		self.assertEqual(eq.get(FUEL_FIELD), COMPANY)
		self.assertEqual(eq.operator_on, COMPANY)

		# baseline (0 / blank) reproduces current behaviour: no daily_hours default,
		# so the mandatory field still rejects an empty value.
		_set("default_daily_hours", 0)
		_set("default_fuel_charged_to", "")
		_set("default_operator_on", "")
		with self.assertRaises(frappe.ValidationError):
			make()
		eq4 = make(daily_hours=7)
		self.assertFalse(eq4.get(FUEL_FIELD))
		self.assertFalse(eq4.operator_on)  # no hardcoded default; blank setting -> stays empty

	# ---------- 2a. statement_type default ----------

	def test_statement_type_default_from_settings(self):
		eq = self._equipment(ownership=OWNED)
		card = self._card(eq, [10, 10, 10], submit=True)

		# baseline: "مورد" with no supplier -> empty statement (no rows), supplier-style columns
		_set("default_statement_type", SUPPLIER_STATEMENT)
		cols_default, rows_default, _msg, _summary = _statement(self._statement_filters())
		self.assertEqual(rows_default, [])

		# setting -> owned-equipment branch: our owned card is listed, fewer columns (no money columns)
		_set("default_statement_type", OWNED_STATEMENT)
		cols_owned, rows_owned, _msg, _summary = _statement(self._statement_filters())
		self.assertIn(card.name, [r.get("card") for r in rows_owned])
		self.assertLess(len(cols_owned), len(cols_default))

		# an explicit filter still wins over the setting
		_cols, rows_explicit, _msg, _summary = _statement(
			self._statement_filters(statement_type=SUPPLIER_STATEMENT)
		)
		self.assertEqual(rows_explicit, [])

	# ---------- 2b. include_draft default ----------

	def test_include_draft_default_from_settings(self):
		submitted = self._card(self._equipment("-A"), [10, 10], submit=True)
		draft = self._card(self._equipment("-B"), [10, 10], submit=False)
		self.assertEqual(draft.docstatus, 0)

		def card_names(**kw):
			filters = self._statement_filters(supplier=self.supplier, statement_type=SUPPLIER_STATEMENT, **kw)
			_cols, rows, _msg, _summary = _statement(filters)
			return [r.get("card") for r in rows]

		# baseline (0): draft excluded when the filter is not provided
		_set("include_draft_in_reports", 0)
		names = card_names()
		self.assertIn(submitted.name, names)
		self.assertNotIn(draft.name, names)

		# setting on: draft included when the filter is not provided
		_set("include_draft_in_reports", 1)
		names = card_names()
		self.assertIn(submitted.name, names)
		self.assertIn(draft.name, names)

		# an explicitly provided filter wins over the setting
		self.assertNotIn(draft.name, card_names(include_draft=0))
		_set("include_draft_in_reports", 0)
		self.assertIn(draft.name, card_names(include_draft=1))

	# ---------- 2c. reconciliation tolerance ----------

	def test_reconciliation_tolerance_from_settings(self):
		# A submitted card with NO supplier GL entries: net cards > 0, accrual = 0, so the
		# reconciliation difference is large (2,250). The report exposes the flag as the
		# "indicator" of the summary item labelled "Reconciliation difference"
		# (Green = within tolerance, Red = over tolerance); that is what is asserted.
		# The summary report is limited to this test's own project so other data cannot
		# offset the total difference.
		self._card(self._equipment(), [10, 10, 10], submit=True)

		# default reproduces the old hardcoded 0.01 when the setting is unset
		frappe.db.delete("Singles", {"doctype": "Card Settings", "field": "reconciliation_tolerance"})
		self.assertEqual(flt(setting("reconciliation_tolerance")), 0.01)

		label = "Reconciliation difference"
		statement_filters = self._statement_filters(supplier=self.supplier, statement_type=SUPPLIER_STATEMENT)
		summary_filters = {"from_month": 9, "from_year": 2026, "project": self.project}

		# baseline tolerance (0.01): the large difference IS flagged in both reports
		_set("reconciliation_tolerance", 0.01)
		self.assertEqual(_indicator(_statement(statement_filters)[3], label), "Red")
		self.assertEqual(_indicator(_summary_report(summary_filters)[3], label), "Red")

		# huge tolerance: nothing is flagged (kept below the Currency column limit)
		_set("reconciliation_tolerance", 1000000000)
		self.assertEqual(_indicator(_statement(statement_filters)[3], label), "Green")
		self.assertEqual(_indicator(_summary_report(summary_filters)[3], label), "Green")

	# ---------- 3. empty operator_on / الوقود_على handled where read ----------

	def test_empty_fuel_company_bears(self):
		from card.diesel import get_card_diesel

		eq = self._equipment()
		card = self._card(eq, [10, 10], submit=True)
		# empty fuel -> the company does not bear the diesel (no crash)
		frappe.db.set_value("Card Equipment", eq.name, "الوقود_على", "")
		self.assertFalse(get_card_diesel(card.name)["company_bears"])
		# المؤجر (the restored default) also means the company does not bear it
		frappe.db.set_value("Card Equipment", eq.name, "الوقود_على", "المؤجر")
		self.assertFalse(get_card_diesel(card.name)["company_bears"])
		# الشركة -> company bears
		frappe.db.set_value("Card Equipment", eq.name, "الوقود_على", "الشركة")
		self.assertTrue(get_card_diesel(card.name)["company_bears"])
