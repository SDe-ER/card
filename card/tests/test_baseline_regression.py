# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE

"""ADDENDUM E regression guard.

Recomputes the operational signals captured in the pre-S1 baseline fixture
(`card/tests/fixtures/baseline_v1_2.json`) and asserts they are unchanged.
This proves the Settings/permissions/GL layer never perturbs the existing
net_amount and report numbers. It runs only on a site that still holds the
seeded cards (e.g. v11-dev); on a clean test DB it self-skips.
"""

import json
import os

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt


def _fixture():
	path = os.path.join(frappe.get_app_path("card"), "tests", "fixtures", "baseline_v1_2.json")
	with open(path, encoding="utf-8") as fh:
		return json.load(fh)


class TestBaselineRegression(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.base = _fixture()
		cls.company = cls.base.get("company")

	def _skip_if_unseeded(self):
		# seed-scope guard: the gate watches the FIXTURE's cards by name, so later
		# additive demo/customer data never silences it; a clean DB still self-skips.
		names = [c["name"] for c in self.base.get("cards") or []]
		if not names:
			self.skipTest("baseline fixture carries no card names")
		present = frappe.db.count("Card Monthly Card", {"name": ["in", names], "docstatus": 1})
		if present != len(names):
			self.skipTest(
				f"baseline regression needs the seeded site (fixture cards={len(names)}, found={present})"
			)

	def test_cards_net_sum_unchanged(self):
		self._skip_if_unseeded()
		# every seed card keeps its exact stored net (stronger than the grand sum)
		total = 0.0
		for c in self.base["cards"]:
			net = flt(frappe.db.get_value("Card Monthly Card", c["name"], "net_amount"), 2)
			self.assertEqual(net, flt(c["net_amount"], 2), c["name"])
			total += net
		self.assertEqual(flt(total, 2), self.base["cards_net_sum"])

	def test_diesel_transport_sums_unchanged(self):
		self._skip_if_unseeded()
		dl = flt(
			frappe.db.sql("select coalesce(sum(litres),0) from `tabProject Diesel Fill` where docstatus=1")[
				0
			][0],
			3,
		)
		da = flt(
			frappe.db.sql("select coalesce(sum(amount),0) from `tabProject Diesel Fill` where docstatus=1")[
				0
			][0],
			2,
		)
		ta = flt(
			frappe.db.sql("select coalesce(sum(amount),0) from `tabEquipment Transport` where docstatus=1")[
				0
			][0],
			2,
		)
		self.assertEqual(dl, self.base["diesel_litres_sum"])
		self.assertEqual(da, self.base["diesel_amount_sum"])
		self.assertEqual(ta, self.base["transport_amount_sum"])

	def test_d3_reports_unchanged(self):
		self._skip_if_unseeded()
		f = {"company": self.company, "from_date": "2026-01-01", "to_date": "2026-12-31"}
		from card.card.report.equipment_diesel_consumption import equipment_diesel_consumption as edc
		from card.card.report.operating_cost_by_project import operating_cost_by_project as ocp
		from card.card.report.transport_cost_by_project import transport_cost_by_project as tcp

		d = edc.execute(dict(f))[1]
		self.assertEqual(
			flt(sum(flt(r.get("litres")) for r in d), 3),
			self.base["r_equipment_diesel_consumption"]["litres"],
		)
		self.assertEqual(
			flt(sum(flt(r.get("amount")) for r in d), 2),
			self.base["r_equipment_diesel_consumption"]["amount"],
		)

		d = tcp.execute(dict(f))[1]
		self.assertEqual(
			flt(sum(flt(r.get("amount")) for r in d), 2), self.base["r_transport_cost_by_project"]["amount"]
		)

		d = ocp.execute(dict(f))[1]
		self.assertEqual(
			flt(sum(flt(r.get("diesel")) for r in d), 2), self.base["r_operating_cost_by_project"]["diesel"]
		)
		self.assertEqual(
			flt(sum(flt(r.get("transport")) for r in d), 2),
			self.base["r_operating_cost_by_project"]["transport"],
		)
		self.assertEqual(
			flt(sum(flt(r.get("total")) for r in d), 2), self.base["r_operating_cost_by_project"]["total"]
		)

	def test_supplier_summary_net_unchanged(self):
		self._skip_if_unseeded()
		from card.card.report.equipment_suppliers_summary import equipment_suppliers_summary as m

		data = m.execute({"from_month": "01", "from_year": 2026, "to_month": "12", "to_year": 2026})[1]
		total = next((r for r in data if r.get("is_total")), None)
		net = (
			flt(total["net"], 2)
			if total
			else flt(sum(flt(r.get("net")) for r in data if not r.get("is_total")), 2)
		)
		self.assertEqual(net, self.base["r_equipment_suppliers_summary"]["net"])
