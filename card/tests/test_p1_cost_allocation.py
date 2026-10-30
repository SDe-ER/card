# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-0 (integration plan 2026-10-30): CARD posting lines carry the project/equipment cost
allocation — the equipment's assignment to the card's project, then the project's cost
center, then the equipment's own — instead of the company default; diesel fills without
their own cost center take their project's."""

import frappe

from card.gl.posting import build_monthly_posting
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_s3_posting import _PostingBase


class TestCostAllocation(_PostingBase):
	def setUp(self):
		super().setUp()
		self.default_cc = next(
			r.cost_center
			for r in frappe.get_doc("Card Settings").company_settings
			if r.company == self.company
		)

	def _cc(self, suffix, is_group=0):
		parent = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 1}, "name")
		doc = frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": f"P1-{suffix}-{self.token}",
				"parent_cost_center": parent,
				"company": self.company,
				"is_group": is_group,
			}
		).insert(ignore_permissions=True)
		return doc.name

	def _assign(self, eq, cost_center, from_date="2026-09-01", to_date=None):
		return frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": eq.name,
				"project": self.project,
				"from_date": from_date,
				"to_date": to_date,
				"cost_center": cost_center,
			}
		).insert(ignore_permissions=True)

	def _set_project_cc(self, cc):
		frappe.db.set_value("Project", self.project, "cost_center", cc)

	def _pi(self):
		return frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)

	def test_assignment_cost_center_wins(self):
		eq = self._equipment()
		assigned, project_cc = self._cc("ASSIGN"), self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._assign(eq, assigned)
		self._card(eq, [8], submit=True)
		pi = self._pi()
		self.assertEqual({i.cost_center for i in pi.items}, {assigned})

	def test_adjustment_lines_carry_the_same_cost_center(self):
		eq = self._equipment()
		assigned = self._cc("ASSIGN")
		self._assign(eq, assigned)
		self._card(
			eq,
			[8],
			adjustments=[{"adjustment_type_ref": "Mobilization", "description": "m", "amount": 100}],
			submit=True,
		)
		pi = self._pi()
		self.assertEqual(len(pi.items), 2)
		self.assertEqual({i.cost_center for i in pi.items}, {assigned})

	def test_project_cost_center_without_an_assignment_cost_center(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_equipment_cost_center_when_project_has_none(self):
		eq_cc = self._cc("EQ")
		eq = self._equipment(cost_center=eq_cc)
		self._set_project_cc(None)
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, eq_cc)

	def test_company_default_when_nothing_is_set(self):
		eq = self._equipment()
		self._set_project_cc(None)
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, self.default_cc)

	def test_two_assignment_cost_centers_in_the_period_fall_back_to_the_project(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._assign(eq, self._cc("A1"), "2026-09-01", "2026-09-10")
		self._assign(eq, self._cc("A2"), "2026-09-11")
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_a_group_cost_center_is_skipped(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("GROUP", is_group=1))
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, self.default_cc)

	def test_fill_without_its_own_cost_center_takes_the_project_cost_center(self):
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_gl_carries_the_allocated_cost_center_and_signature_holds(self):
		eq = self._equipment()
		assigned = self._cc("ASSIGN")
		self._assign(eq, assigned)
		self._card(eq, [8], submit=True)
		pi = self._pi()
		pi.submit()
		rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": pi.name, "is_cancelled": 0, "account": self.exp_rental},
			fields=["cost_center", "project", "card_equipment"],
		)
		self.assertEqual(
			[(r.cost_center, r.project, r.card_equipment) for r in rows], [(assigned, self.project, eq.name)]
		)
