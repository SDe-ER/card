# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment Diesel Analysis report (F.2). Expected litres = operating hours x
(daily_diesel_consumption / daily standard hours); equipment without the daily
figure falls back to the older per-hour expected_consumption; with neither the
expected side stays empty (row listed, never a crash). Actual litres come from
submitted Project Diesel Fills via the card.diesel allocation. Display only —
no accounting. Every record is per-test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.report.equipment_diesel_analysis.equipment_diesel_analysis import execute
from card.tests.test_controllers import _days, _ensure_masters


def _value(summary, label):
	for item in summary:
		if item["label"] == frappe._(label):
			return item["value"]
	return None


class TestEquipmentDieselAnalysis(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		# the F.1 diesel supplier policy must not interfere with this report's fills
		frappe.db.set_single_value("Card Settings", "diesel_supplier", "")
		frappe.clear_document_cache("Card Settings", "Card Settings")
		# a UNIQUE project per test so the allocation sees only this test's data
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DSLA-PRJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DSLA-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _equipment(self, daily_diesel=None, per_hour=None):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "إيجار"
		d.equipment_name = "TEST-DSLA-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self.supplier
		if daily_diesel is not None:
			d.daily_diesel_consumption = daily_diesel
		if per_hour is not None:
			d.expected_consumption = per_hour
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _card(self, eq, hours_list):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		c.submit()
		c.reload()
		return c

	def _fill(self, eq, litres, unit_price=2):
		# a direct fill: the whole amount is charged to this equipment
		f = frappe.new_doc("Project Diesel Fill")
		f.date = "2026-09-15"
		f.project = self.project
		f.supplier = self.supplier
		f.company = self.company
		f.card_equipment = eq.name
		f.litres = litres
		f.unit_price = unit_price
		f.insert(ignore_permissions=True)
		f.submit()
		return f

	def _run(self, **kw):
		filters = {"from_month": 9, "from_year": 2026, "project": self.project}
		filters.update(kw)
		return execute(filters)

	# ---- expected vs actual ----
	def test_daily_figure_expected_vs_actual(self):
		eq = self._equipment(daily_diesel=50)  # 50 L per 10h standard day = 5 L/h
		self._card(eq, [10, 10])  # 20 operating hours -> expected 100 L
		self._fill(eq, litres=90)  # actual 90 L
		result = self._run()
		# standard script-report shape: [columns, rows, message, None, summary, True]
		self.assertEqual(len(result), 6)
		self.assertIsNone(result[3])
		self.assertTrue(result[5])
		columns, rows, message, _chart, summary, _flag = result
		self.assertTrue(columns)
		self.assertTrue(message)
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual(row["equipment"], eq.name)
		self.assertEqual(row["project"], self.project)
		self.assertEqual(row["period"], "2026-09")
		self.assertEqual(flt(row["hours"]), 20.0)
		self.assertEqual(flt(row["daily_consumption"]), 50.0)
		self.assertEqual(flt(row["expected_litres"]), 100.0)  # 20h x (50/10)
		self.assertEqual(flt(row["actual_litres"]), 90.0)
		self.assertEqual(flt(row["variance"]), -10.0)
		self.assertEqual(flt(row["variance_pct"]), -10.0)
		self.assertEqual(flt(_value(summary, "Expected litres")), 100.0)
		self.assertEqual(flt(_value(summary, "Actual litres")), 90.0)
		self.assertEqual(flt(_value(summary, "Litres variance")), -10.0)

	def test_per_hour_fallback(self):
		eq = self._equipment(per_hour=4)  # no daily figure -> older L/h fallback
		self._card(eq, [10, 10])
		_cols, rows, _msg, _chart, _summary, _flag = self._run()
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertIsNone(row["daily_consumption"])
		self.assertEqual(flt(row["expected_litres"]), 80.0)  # 20h x 4 L/h
		self.assertEqual(flt(row["actual_litres"]), 0.0)  # no fills
		self.assertEqual(flt(row["variance"]), -80.0)
		self.assertEqual(flt(row["variance_pct"]), -100.0)

	def test_no_consumption_figures_row_still_listed(self):
		eq = self._equipment()  # neither daily figure nor per-hour figure
		self._card(eq, [10])
		_cols, rows, _msg, _chart, _summary, _flag = self._run()
		self.assertEqual(len(rows), 1)
		row = rows[0]
		self.assertEqual(flt(row["hours"]), 10.0)
		self.assertIsNone(row["expected_litres"])  # flagged empty, never a crash
		self.assertIsNone(row["variance"])
		self.assertIsNone(row["variance_pct"])
		self.assertEqual(flt(row["actual_litres"]), 0.0)

	def test_empty_period_returns_no_rows(self):
		eq = self._equipment(daily_diesel=50)
		self._card(eq, [10])  # lives in 09/2026, outside the queried period
		_cols, rows, _msg, _chart, summary, _flag = self._run(from_month=1, to_month=1)
		self.assertEqual(rows, [])
		self.assertEqual(flt(_value(summary, "Expected litres")), 0.0)
		self.assertEqual(flt(_value(summary, "Actual litres")), 0.0)
