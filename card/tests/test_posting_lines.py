# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#34: monthly PI lines use the source document's own cost center (fill /
transport) when it has one, else the company default; a tank fill split by
hours states each line's own litres share, marked as an estimate."""

import frappe
from frappe.utils import flt

from card.gl.posting import build_monthly_posting
from card.tests.test_s3_posting import _PostingBase


class TestPostingLines(_PostingBase):
	def _cost_center(self, label):
		parent = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 1}, "name")
		cc = frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": f"TEST-PL-{label}-{self.token}",
				"parent_cost_center": parent,
				"company": self.company,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		return cc.name

	def _fill(self, **kw):
		f = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				**kw,
			}
		)
		f.insert(ignore_permissions=True)
		f.submit()
		return f

	def _pi(self):
		return frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)

	def test_fill_and_transport_lines_use_their_own_cost_center(self):
		eq = self._equipment()
		self._card(eq, [5], submit=True)
		own = self._cost_center("FILL")
		with_cc = self._fill(card_equipment=eq.name, litres=10, unit_price=2, cost_center=own)
		without_cc = self._fill(card_equipment=eq.name, litres=5, unit_price=2)
		transport = frappe.get_doc(
			{
				"doctype": "Equipment Transport",
				"date": "2026-09-14",
				"project": self.project,
				"transport_supplier": self.supplier,
				"company": self.company,
				"amount": 300,
				"cost_center": own,
			}
		)
		transport.insert(ignore_permissions=True)
		transport.submit()
		pi = self._pi()
		default = frappe.db.get_value(
			"Card Company Settings", {"parent": "Card Settings", "company": self.company}, "cost_center"
		)
		by_source = {}
		for item in pi.items:
			for name in (with_cc.name, without_cc.name, transport.name):
				if name in item.description:
					by_source[name] = item.cost_center
		self.assertEqual(by_source[with_cc.name], own)
		self.assertEqual(by_source[transport.name], own)
		self.assertEqual(by_source[without_cc.name], default)

	def test_split_lines_state_their_own_estimated_litres(self):
		eq_a = self._equipment()
		eq_b = self._equipment()
		self._card(eq_a, [6], submit=True)  # 6h
		self._card(eq_b, [2], submit=True)  # 2h -> 75% / 25%
		tank = self._fill(litres=1000, unit_price=1.0)
		direct = self._fill(card_equipment=eq_a.name, litres=40, unit_price=1.0)
		pi = self._pi()
		split = {i.card_equipment: i.description for i in pi.items if tank.name in i.description}
		self.assertIn("750", split[eq_a.name])
		self.assertIn("250", split[eq_b.name])
		for text in split.values():
			self.assertIn("1000", text)  # the whole fill is named once, as the reference
		self.assertNotIn("1000 L", split[eq_a.name].split("—")[1].split("estimated")[0])
		direct_line = next(i for i in pi.items if direct.name in i.description)
		self.assertNotIn("estimated", direct_line.description)
		self.assertEqual(flt(sum(flt(i.rate) for i in pi.items if tank.name in i.description), 2), 1000.0)


class TestLikeForLikeReconciliation(_PostingBase):
	def test_difference_closes_against_the_invoiced_net_not_the_vat_inclusive_gl(self):
		"""Card nets are before VAT; after the monthly PI (net + 15% VAT) is
		submitted the reconciliation difference is 0, while the GL accrual
		(VAT included) is shown separately."""
		self._vat_supplier()
		eq, _card = self._example_card()  # card net 10,277.81
		# a diesel fill billed on the SAME invoice is not a card: it must not move
		# the cards reconciliation (reviewer MEDIUM-1)
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"card_equipment": eq.name,
				"litres": 100,
				"unit_price": 20,
			}
		)
		fill.insert(ignore_permissions=True)
		fill.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-BILL-REC-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		from card.card.report.equipment_supplier_statement.equipment_supplier_statement import execute

		filters = frappe._dict(
			company=self.company,
			statement_type="مورد",
			supplier=self.supplier,
			from_month=9,
			from_year=2026,
			to_month=9,
			to_year=2026,
		)
		_c, _rows, _msg, _chart, summary, _f = execute(filters)
		tiles = {s["label"]: s["value"] for s in summary}
		self.assertEqual(tiles[frappe._("Net cards")], 10277.81)
		self.assertEqual(tiles[frappe._("Cards invoiced (net before VAT)")], 10277.81)
		self.assertEqual(tiles[frappe._("Reconciliation difference")], 0)
		# the GL accrual is the whole invoice, VAT included (cards + diesel 2,000)
		self.assertEqual(tiles[frappe._("Accrual entries (Credit)")], flt(pi.grand_total, 2))
		self.assertGreater(flt(pi.grand_total, 2), 11864.48)

		from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute as summ

		_c, rows, _msg, _chart, _s, _f = summ(
			frappe._dict(company=self.company, from_month=9, from_year=2026, to_month=9, to_year=2026)
		)
		row = next(r for r in rows if r.get("supplier") == self.supplier)
		self.assertEqual((row["invoiced_net"], row["diff"]), (10277.81, 0))
		self.assertEqual(row["accrued"], flt(pi.grand_total, 2))

	def test_unbilled_cards_keep_a_positive_difference(self):
		self._vat_supplier()
		self._example_card()  # submitted, never invoiced
		from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute as summ

		_c, rows, _msg, _chart, _s, _f = summ(
			frappe._dict(company=self.company, from_month=9, from_year=2026, to_month=9, to_year=2026)
		)
		row = next(r for r in rows if r.get("supplier") == self.supplier)
		self.assertEqual((row["invoiced_net"], row["diff"]), (0, 10277.81))


class TestSourceCostCenterGuard(_PostingBase):
	def test_a_group_cost_center_on_a_fill_is_refused_before_any_reservation(self):
		eq = self._equipment()
		self._card(eq, [5], submit=True)
		group = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 1}, "name")
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"card_equipment": eq.name,
				"litres": 10,
				"unit_price": 2,
			}
		)
		fill.insert(ignore_permissions=True)
		fill.submit()
		frappe.db.set_value("Project Diesel Fill", fill.name, "cost_center", group, update_modified=False)
		with self.assertRaisesRegex(frappe.ValidationError, "cost center"):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))

	def test_a_single_share_tank_fill_is_still_marked_estimated(self):
		eq = self._equipment()
		self._card(eq, [5], submit=True)  # the only equipment with hours
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 30,
				"unit_price": 2,
			}
		)
		fill.insert(ignore_permissions=True)
		fill.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		line = next(i for i in pi.items if fill.name in i.description)
		self.assertIn("estimated", line.description)
