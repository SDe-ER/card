# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-0 (integration plan 2026-10-30): CARD posting lines carry the project/equipment cost
allocation — the equipment's assignment to the card's project, then the project's cost
center, then the equipment's own — instead of the company default; diesel fills without
their own cost center take their project's. An allocation that cannot be determined reliably
(different assignment cost centers in one card's period, or a set but unusable cost center)
refuses the build for review."""

import frappe
from frappe.utils import flt

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

	def _assign(self, eq, cost_center, from_date="2026-09-01", to_date=None, project=None):
		return frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": eq.name,
				"project": project or self.project,
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

	def test_two_assignment_cost_centers_in_the_period_are_an_exception(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		self._assign(eq, self._cc("A1"), "2026-09-01", "2026-09-10")
		self._assign(eq, self._cc("A2"), "2026-09-11")
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "carry different cost centers"):
			self._pi()
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))

	def test_two_assignments_with_the_same_cost_center_are_one_allocation(self):
		eq = self._equipment()
		cc = self._cc("SAME")
		self._assign(eq, cc, "2026-09-01", "2026-09-10")
		self._assign(eq, cc, "2026-09-11")
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, cc)

	def test_assignment_without_cost_center_falls_back_to_the_project(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._assign(eq, None)
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_a_set_but_unusable_cost_center_is_an_exception_not_a_fallback(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("GROUP", is_group=1))
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot carry a posting"):
			self._pi()

	def test_a_disabled_equipment_cost_center_is_an_exception(self):
		cc = self._cc("EQOFF")
		eq = self._equipment(cost_center=cc)
		frappe.db.set_value("Cost Center", cc, "disabled", 1)
		self._set_project_cc(None)
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot carry a posting"):
			self._pi()

	def test_equipment_on_two_projects_in_one_month_splits_by_project(self):
		eq = self._equipment()
		other = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-P1-PRJ-B-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		cc_a, cc_b = self._cc("PA"), self._cc("PB")
		self._assign(eq, cc_a, "2026-09-01", "2026-09-15")
		self._assign(eq, cc_b, "2026-09-16", None, project=other.name)
		card_a = self._card(eq, [8, 8], submit=True)  # 1-2 Sep on project A: 1,200
		card_b = frappe.new_doc("Card Monthly Card")
		card_b.update(
			{"equipment": eq.name, "project": other.name, "shift": "نهاري", "month": "09", "year": 2026}
		)
		card_b.append(
			"days", {"operation_date": "2026-09-20", "day_status": "عمل", "working_hours": 4}
		)  # 300
		card_b.insert(ignore_permissions=True)
		card_b.submit()
		pi = self._pi()
		by_card = {}
		for item in pi.items:
			for card in (card_a, card_b):
				if card.name in item.description:
					by_card[card.name] = (
						item.project,
						item.cost_center,
						item.card_equipment,
						flt(item.rate, 2),
					)
		self.assertEqual(by_card[card_a.name], (self.project, cc_a, eq.name, 1200.0))
		self.assertEqual(by_card[card_b.name], (other.name, cc_b, eq.name, 300.0))

	def test_every_line_carries_project_cost_center_and_equipment(self):
		eq = self._equipment()
		cc = self._cc("ALL")
		self._assign(eq, cc)
		self._set_project_cc(self._cc("PROJ"))
		self._card(eq, [8], submit=True)
		self._fill(card_equipment=eq.name)  # direct fill
		pi = self._pi()
		for item in pi.items:
			self.assertEqual(item.project, self.project, item.description)
			self.assertTrue(item.cost_center, item.description)
			self.assertEqual(item.card_equipment, eq.name, item.description)

	def test_fill_keeps_its_equipment_when_it_takes_the_project_cost_center(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._fill(card_equipment=eq.name)
		item = self._pi().items[0]
		self.assertEqual(
			(item.cost_center, item.card_equipment, item.project), (project_cc, eq.name, self.project)
		)

	def test_signature_protects_the_allocated_cost_center(self):
		from card.gl.integrity import accept_correction

		eq = self._equipment()
		self._assign(eq, self._cc("ASSIGN"))
		self._card(eq, [8], submit=True)
		pi = self._pi()
		other = self._cc("OTHER")
		pi.items[0].cost_center = other
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "differs from what CARD built"):
			pi.submit()
		pi.reload()
		pi.items[0].project = None
		pi.items[0].cost_center = other
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "Only cost center and account changes"):
			accept_correction("Purchase Invoice", pi.name, "try")

	def _fill(self, **kw):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
				**kw,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		return fill

	def test_fill_with_an_unusable_project_cost_center_is_an_exception(self):
		self._set_project_cc(self._cc("GROUP", is_group=1))
		self._fill()
		with self.assertRaisesRegex(frappe.ValidationError, "cannot carry a posting"):
			self._pi()

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
