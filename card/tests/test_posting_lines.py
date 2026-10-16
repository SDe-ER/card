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
