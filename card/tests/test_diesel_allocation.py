# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Diesel allocation + D1 doctype tests (CARD v1.2).

Covers: direct allocation (fill.card_equipment set), pro-rata allocation by
operating hours (project-tank fill), rounding (last row absorbs → shares sum to
the fill amount exactly), cancelled fills excluded, allocation never changes a
card's net_amount, and the D1 amount fields (diesel = litres x price, transport).
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, nowdate

from card.card.report.equipment_diesel_consumption.equipment_diesel_consumption import execute
from card.diesel import UNALLOCATED, allocate_project_diesel, get_card_diesel
from card.tests.test_controllers import _ensure_masters


def _past_month_year():
	today = getdate(nowdate())
	year, month = today.year, today.month - 2
	if month < 1:
		month += 12
		year -= 1
	return f"{month:02d}", str(year)


class TestDieselAllocation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.month_str, self.year_str = _past_month_year()
		# F.1: a site-configured diesel supplier policy must never gate these fills
		# (pin the policy too: a fixed policy with no supplier rejects every save)
		frappe.db.set_single_value("Card Settings", "diesel_supplier", None)
		frappe.db.set_single_value("Card Settings", "diesel_supplier_policy", "متغير")
		frappe.clear_document_cache("Card Settings", "Card Settings")
		# a UNIQUE project per test so the allocation sees only this test's cards
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DSL-PROJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DSL-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _day(self, day, hours):
		return {
			"operation_date": f"{self.year_str}-{self.month_str}-{day:02d}",
			"day_status": "عمل",
			"working_hours": hours,
		}

	def _make_equipment(self, name, fuel_on=None):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self.etype
		d.ownership = "إيجار"
		d.equipment_name = name + "-" + self.token
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self.supplier
		if fuel_on:
			d.set("الوقود_على", fuel_on)
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _make_card(self, eq, days, submit=True):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = self.month_str
		c.year = int(self.year_str)
		for row in days:
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _make_fill(self, litres, unit_price, card_equipment=None, submit=True):
		f = frappe.new_doc("Project Diesel Fill")
		f.date = f"{self.year_str}-{self.month_str}-15"
		f.project = self.project
		f.supplier = self.supplier
		f.company = self.company
		f.litres = litres
		f.unit_price = unit_price
		if card_equipment:
			f.card_equipment = card_equipment
		f.insert(ignore_permissions=True)
		if submit:
			f.submit()
		f.reload()
		return f

	# ---- allocation ----
	def test_direct_allocation_whole_fill_to_one_equipment(self):
		eq1 = self._make_equipment("EQ1")
		eq2 = self._make_equipment("EQ2")
		c1 = self._make_card(eq1, [self._day(2, 10)])
		c2 = self._make_card(eq2, [self._day(2, 10)])
		self._make_fill(litres=200, unit_price=2, card_equipment=eq1.name)  # amount 400
		d1 = get_card_diesel(c1.name)
		d2 = get_card_diesel(c2.name)
		self.assertAlmostEqual(d1["amount"], 400.0)
		self.assertAlmostEqual(d1["litres"], 200.0)
		self.assertAlmostEqual(d2["amount"], 0.0)

	def test_prorata_by_operating_hours(self):
		eq1 = self._make_equipment("EQ1")
		eq2 = self._make_equipment("EQ2")
		c1 = self._make_card(eq1, [self._day(2, 10)])  # 10 h
		c2 = self._make_card(eq2, [self._day(2, 10), self._day(3, 10), self._day(4, 10)])  # 30 h
		self._make_fill(litres=400, unit_price=1)  # project tank, amount 400
		d1 = get_card_diesel(c1.name)
		d2 = get_card_diesel(c2.name)
		self.assertAlmostEqual(d1["amount"] + d2["amount"], 400.0)
		self.assertAlmostEqual(d1["amount"], 100.0)  # 10/40
		self.assertAlmostEqual(d2["amount"], 300.0)  # 30/40

	def test_rounding_last_row_absorbs_difference(self):
		eqs = [self._make_equipment(f"EQ{i}") for i in range(3)]
		cards = [self._make_card(eq, [self._day(2, 10)]) for eq in eqs]  # 10 h each
		fill = self._make_fill(litres=100, unit_price=1)  # amount 100, splits 1/3 each
		shares = [get_card_diesel(c.name)["amount"] for c in cards]
		# sums EXACTLY to the fill at currency precision (last row absorbs the cent)
		self.assertEqual(flt(sum(shares), 2), flt(fill.amount, 2))
		self.assertTrue(all(flt(s, 2) in (33.33, 33.34) for s in shares))  # 100/3 split

	def test_cancelled_fill_excluded(self):
		eq = self._make_equipment("EQ1")
		c = self._make_card(eq, [self._day(2, 10)])
		fill = self._make_fill(litres=100, unit_price=1, card_equipment=eq.name)
		self.assertAlmostEqual(get_card_diesel(c.name)["amount"], 100.0)
		fill.cancel()
		self.assertAlmostEqual(get_card_diesel(c.name)["amount"], 0.0)

	def test_allocation_does_not_change_net_amount(self):
		eq = self._make_equipment("EQ1")
		c = self._make_card(eq, [self._day(2, 10)])
		before = flt(c.net_amount)
		self._make_fill(litres=300, unit_price=2, card_equipment=eq.name)  # amount 600
		c.reload()
		self.assertEqual(flt(c.net_amount), before)  # rental amount untouched
		self.assertAlmostEqual(get_card_diesel(c.name)["amount"], 600.0)  # but diesel is shown

	def test_company_bears_flag(self):
		eq = self._make_equipment("EQ1", fuel_on="الشركة")
		c = self._make_card(eq, [self._day(2, 10)])
		self._make_fill(litres=10, unit_price=2, card_equipment=eq.name)
		self.assertTrue(get_card_diesel(c.name)["company_bears"])

	def test_unallocated_fill_surfaces_and_total_matches(self):
		# project-tank fill in a project/month with NO submitted card hours
		fill = self._make_fill(litres=250, unit_price=2)  # amount 500
		# backward-compat: default call drops it
		self.assertNotIn(
			UNALLOCATED, allocate_project_diesel(self.project, self.month_str, self.year_str, self.company)
		)
		alloc = allocate_project_diesel(
			self.project, self.month_str, self.year_str, self.company, include_unallocated=True
		)
		self.assertIn(UNALLOCATED, alloc)
		self.assertAlmostEqual(alloc[UNALLOCATED]["litres"], flt(fill.litres))
		self.assertAlmostEqual(alloc[UNALLOCATED]["amount"], flt(fill.amount))
		# the report total for this project equals the submitted fill total
		_cols, data = execute({"project": self.project})
		self.assertAlmostEqual(sum(flt(r["litres"]) for r in data), flt(fill.litres))
		self.assertAlmostEqual(sum(flt(r["amount"]) for r in data), flt(fill.amount))
		self.assertEqual(len(data), 1)
		# #33: the unallocated diesel is neither recorded nor estimated for any equipment
		self.assertEqual(flt(alloc[UNALLOCATED]["litres_recorded"]), 0.0)
		self.assertEqual(flt(alloc[UNALLOCATED]["litres_estimated"]), 0.0)
		self.assertIsNone(data[0]["litres_recorded"])
		self.assertIsNone(data[0]["litres_estimated"])
		# an equipment filter hides the synthetic row
		_cols, data = execute({"project": self.project, "equipment": "no-such-equipment"})
		self.assertEqual(data, [])

	# ---- #33: recorded (direct fill) vs estimated (hours split) ----
	def _alloc(self):
		return allocate_project_diesel(self.project, self.month_str, self.year_str, self.company)

	def test_direct_fill_counts_only_as_recorded(self):
		eq = self._make_equipment("EQ1")
		c = self._make_card(eq, [self._day(2, 10)])
		self._make_fill(litres=200, unit_price=2, card_equipment=eq.name)  # amount 400
		share = self._alloc()[eq.name]
		self.assertEqual(flt(share["litres"]), 200.0)
		self.assertEqual(flt(share["litres_recorded"]), 200.0)
		self.assertEqual(flt(share["litres_estimated"]), 0.0)
		self.assertEqual(flt(share["amount_recorded"]), 400.0)
		self.assertEqual(flt(share["amount_estimated"]), 0.0)
		d = get_card_diesel(c.name)
		self.assertAlmostEqual(d["litres_recorded"], 200.0)
		self.assertAlmostEqual(d["litres_estimated"], 0.0)

	def test_tank_fill_split_counts_only_as_estimated(self):
		eq1 = self._make_equipment("EQ1")
		eq2 = self._make_equipment("EQ2")
		c1 = self._make_card(eq1, [self._day(2, 10)])  # 10 h
		self._make_card(eq2, [self._day(2, 10), self._day(3, 10), self._day(4, 10)])  # 30 h
		self._make_fill(litres=400, unit_price=1)  # project tank, amount 400
		alloc = self._alloc()
		for eq, litres in ((eq1, 100.0), (eq2, 300.0)):
			share = alloc[eq.name]
			self.assertEqual(flt(share["litres"]), litres)
			self.assertEqual(flt(share["litres_estimated"]), litres)
			self.assertEqual(flt(share["litres_recorded"]), 0.0)
			self.assertEqual(flt(share["amount_estimated"]), flt(share["amount"]))
			self.assertEqual(flt(share["amount_recorded"]), 0.0)
		d1 = get_card_diesel(c1.name)
		self.assertAlmostEqual(d1["litres_estimated"], 100.0)
		self.assertAlmostEqual(d1["litres_recorded"], 0.0)

	def test_mixed_month_recorded_plus_estimated_equals_allocated(self):
		eq1 = self._make_equipment("EQ1")
		eq2 = self._make_equipment("EQ2")
		self._make_card(eq1, [self._day(2, 10)])  # 10 h
		self._make_card(eq2, [self._day(2, 10), self._day(3, 10), self._day(4, 10)])  # 30 h
		direct = self._make_fill(litres=50, unit_price=2, card_equipment=eq1.name)  # amount 100
		tank = self._make_fill(litres=400, unit_price=1)  # amount 400, split 100 / 300
		alloc = self._alloc()
		e1, e2 = alloc[eq1.name], alloc[eq2.name]
		self.assertEqual(flt(e1["litres_recorded"]), 50.0)
		self.assertEqual(flt(e1["litres_estimated"]), 100.0)
		self.assertEqual(flt(e1["litres"]), 150.0)
		self.assertEqual(flt(e2["litres_recorded"]), 0.0)
		self.assertEqual(flt(e2["litres_estimated"]), 300.0)
		for share in (e1, e2):
			self.assertEqual(
				flt(share["litres_recorded"] + share["litres_estimated"], 3), flt(share["litres"], 3)
			)
			self.assertEqual(
				flt(share["amount_recorded"] + share["amount_estimated"], 2), flt(share["amount"], 2)
			)
		# totals unchanged: allocated litres/amount still sum to the submitted fills
		self.assertEqual(
			flt(sum(s["litres"] for s in alloc.values()), 3), flt(direct.litres + tank.litres, 3)
		)
		self.assertEqual(
			flt(sum(s["amount"] for s in alloc.values()), 2), flt(direct.amount + tank.amount, 2)
		)
		# the consumption report carries the same split and the same totals
		_cols, data = execute({"company": self.company, "project": self.project})
		self.assertEqual(flt(sum(flt(r["litres"]) for r in data), 3), 450.0)
		self.assertEqual(flt(sum(flt(r["amount"]) for r in data), 2), 500.0)
		self.assertEqual(flt(sum(flt(r["litres_recorded"]) for r in data), 3), 50.0)
		self.assertEqual(flt(sum(flt(r["litres_estimated"]) for r in data), 3), 400.0)
		for r in data:
			self.assertEqual(flt(r["litres_recorded"] + r["litres_estimated"], 3), flt(r["litres"], 3))

	def test_consumption_report_columns_label_allocated_and_split(self):
		cols, _data = execute({"company": self.company, "project": self.project})
		labels = {c["fieldname"]: c["label"] for c in cols}
		self.assertEqual(labels["litres"], frappe._("Allocated litres"))
		self.assertEqual(labels["litres_recorded"], frappe._("Recorded litres (direct fills)"))
		self.assertEqual(labels["litres_estimated"], frappe._("Estimated litres (hours split)"))
		self.assertIn("amount", labels)

	# ---- D1 amount fields ----
	def test_diesel_fill_amount_is_litres_times_price(self):
		f = self._make_fill(litres=500, unit_price=2.5, submit=False)
		self.assertAlmostEqual(flt(f.amount), 1250.0)

	def test_diesel_unit_price_defaults_from_settings(self):
		settings = frappe.get_single("Card Settings")
		row = next((r for r in settings.get("company_settings") or [] if r.company == self.company), None)
		if row:
			row.diesel_unit_price = 1.75
		else:
			settings.append("company_settings", {"company": self.company, "diesel_unit_price": 1.75})
		settings.save(ignore_permissions=True)

		# blank price -> defaulted from settings, amount follows
		f = self._make_fill(litres=100, unit_price=0, submit=False)
		self.assertAlmostEqual(flt(f.unit_price), 1.75)
		self.assertAlmostEqual(flt(f.amount), 175.0)

		# explicit price is kept (editable per fill)
		f2 = self._make_fill(litres=100, unit_price=2.0, submit=False)
		self.assertAlmostEqual(flt(f2.unit_price), 2.0)
		self.assertAlmostEqual(flt(f2.amount), 200.0)

		# company with no settings row -> price stays as entered, no throw
		f3 = frappe.new_doc("Project Diesel Fill")
		f3.company = "NO-SETTINGS-CO-" + self.token
		f3.litres = 10
		f3.unit_price = 0
		f3.validate()
		self.assertAlmostEqual(flt(f3.unit_price), 0.0)
		self.assertAlmostEqual(flt(f3.amount), 0.0)

	def test_transport_amount_stored(self):
		t = frappe.new_doc("Equipment Transport")
		t.date = f"{self.year_str}-{self.month_str}-15"
		t.project = self.project
		t.transport_supplier = self.supplier
		t.company = self.company
		t.amount = 3500
		t.insert(ignore_permissions=True)
		self.assertAlmostEqual(flt(t.amount), 3500.0)
