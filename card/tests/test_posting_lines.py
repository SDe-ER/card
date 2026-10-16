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
		self.assertEqual(tiles[frappe._("Invoiced through Card (net before VAT)")], 10277.81)
		self.assertEqual(tiles[frappe._("Not invoiced through Card")], 0)
		# CARD's own invoice is never counted as an invoice outside CARD
		self.assertEqual(tiles[frappe._("ERPNext invoices outside Card — to reconcile (net before VAT)")], 0)
		# the GL accrual is the whole invoice, VAT included (cards + diesel 2,000)
		self.assertEqual(tiles[frappe._("Accrual entries (Credit)")], flt(pi.grand_total, 2))
		self.assertGreater(flt(pi.grand_total, 2), 11864.48)

		from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute as summ

		_c, rows, _msg, _chart, _s, _f = summ(
			frappe._dict(company=self.company, from_month=9, from_year=2026, to_month=9, to_year=2026)
		)
		row = next(r for r in rows if r.get("supplier") == self.supplier)
		self.assertEqual((row["invoiced_net"], row["diff"], row["external_net"]), (10277.81, 0, 0))
		self.assertEqual(row["accrued"], flt(pi.grand_total, 2))

	def test_unbilled_cards_keep_a_positive_difference(self):
		self._vat_supplier()
		self._example_card()  # submitted, never invoiced
		from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute as summ

		_c, rows, _msg, _chart, _s, _f = summ(
			frappe._dict(company=self.company, from_month=9, from_year=2026, to_month=9, to_year=2026)
		)
		row = next(r for r in rows if r.get("supplier") == self.supplier)
		self.assertEqual((row["invoiced_net"], row["diff"], row["external_net"]), (0, 10277.81, 0))


class TestReconciliationCategories(_PostingBase):
	"""Owner decision (PR #39): the reconciliation keeps three things apart —
	cards invoiced through CARD, cards not invoiced through CARD, and ERPNext
	invoices of the party made outside CARD (shown for manual reconciliation,
	never matched to cards by party and month). Nothing existing is relinked."""

	def _manual_invoice(self, doctype, posting_date, rate, submit=True):
		from card.gl.masters import ensure_posting_masters

		row = ensure_posting_masters(self.company)
		doc = {
			"doctype": doctype,
			"company": self.company,
			"set_posting_time": 1,
			"posting_date": posting_date,
			"due_date": posting_date,
			"currency": frappe.db.get_value("Company", self.company, "default_currency"),
		}
		if doctype == "Purchase Invoice":
			doc.update(
				supplier=self.supplier,
				bill_no=f"TEST-MANUAL-{self.token}-{rate}",
				bill_date=posting_date,
				items=[
					{"item_code": row.rental_item, "qty": 1, "rate": rate, "expense_account": self.exp_rental}
				],
			)
		else:
			doc.update(
				customer=self.customer,
				selling_price_list=frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name"),
				items=[
					{"item_code": row.rental_item, "qty": 1, "rate": rate, "income_account": self.inc_rental}
				],
			)
		inv = frappe.get_doc(doc).insert(ignore_permissions=True)
		if submit:
			inv.submit()
		return inv

	def _supplier_statement(self):
		from card.card.report.equipment_supplier_statement.equipment_supplier_statement import execute

		_c, _rows, msg, _chart, summary, _f = execute(
			frappe._dict(
				company=self.company,
				statement_type="مورد",
				supplier=self.supplier,
				from_month=9,
				from_year=2026,
				to_month=9,
				to_year=2026,
			)
		)
		return {s["label"]: s["value"] for s in summary}, msg

	def _summary_row(self, report, party_field, party):
		execute = frappe.get_attr(f"card.card.report.{report}.{report}.execute")
		_c, rows, _msg, _chart, _s, _f = execute(
			frappe._dict(company=self.company, from_month=9, from_year=2026, to_month=9, to_year=2026)
		)
		return next(r for r in rows if r.get(party_field) == party)

	def test_manual_invoice_is_shown_apart_and_not_matched_to_cards(self):
		self._vat_supplier()
		_eq, card = self._example_card()  # submitted, net 10,277.81, never posted through CARD
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 4000)
		self._manual_invoice("Purchase Invoice", "2026-10-05", 999)  # outside the period
		self._manual_invoice("Purchase Invoice", "2026-09-21", 777, submit=False)  # draft: not counted
		before = frappe.db.get_value(
			"Purchase Invoice", manual.name, ["base_net_total", "modified"], as_dict=True
		)

		tiles, msg = self._supplier_statement()
		self.assertEqual(tiles[frappe._("Invoiced through Card (net before VAT)")], 0)
		self.assertEqual(tiles[frappe._("Not invoiced through Card")], 10277.81)
		self.assertEqual(
			tiles[frappe._("ERPNext invoices outside Card — to reconcile (net before VAT)")], 4000
		)
		self.assertIn(
			frappe._(
				"ERPNext invoices outside Card are shown for manual reconciliation and are not matched to cards automatically."
			),
			msg,
		)
		row = self._summary_row("equipment_suppliers_summary", "supplier", self.supplier)
		self.assertEqual((row["invoiced_net"], row["diff"], row["external_net"]), (0, 10277.81, 4000))

		# reading is not relinking: no posting log, no reservation, invoice untouched
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"posting_doc": manual.name}))
		self.assertFalse(frappe.get_all("GL Posting Source", filters={"source_name": card.name}))
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "gl_posting"))
		self.assertEqual(
			frappe.db.get_value(
				"Purchase Invoice", manual.name, ["base_net_total", "modified"], as_dict=True
			),
			before,
		)

	def test_card_invoice_and_manual_invoice_side_by_side(self):
		self._vat_supplier()
		self._example_card()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-BILL-MIX-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		self._manual_invoice("Purchase Invoice", "2026-09-20", 4000)

		tiles, _msg = self._supplier_statement()
		self.assertEqual(tiles[frappe._("Invoiced through Card (net before VAT)")], 10277.81)
		self.assertEqual(tiles[frappe._("Not invoiced through Card")], 0)
		self.assertEqual(
			tiles[frappe._("ERPNext invoices outside Card — to reconcile (net before VAT)")], 4000
		)

	def test_customer_side_keeps_the_same_three_categories(self):
		eq = self._rented_out(customer_rate=1000)  # 16h -> 1,600
		self._card(eq, [8, 8], submit=True)
		si = frappe.get_doc(
			"Sales Invoice", build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		)
		si.submit()
		self._manual_invoice("Sales Invoice", "2026-09-20", 500)

		row = self._summary_row("equipment_customers_summary", "customer", self.customer)
		self.assertEqual((row["invoiced_net"], row["diff"], row["external_net"]), (1600, 0, 500))

		from card.card.report.equipment_customer_statement.equipment_customer_statement import execute

		_c, _rows, _msg, _chart, summary, _f = execute(
			frappe._dict(
				company=self.company,
				customer=self.customer,
				from_month=9,
				from_year=2026,
				to_month=9,
				to_year=2026,
			)
		)
		tiles = {s["label"]: s["value"] for s in summary}
		self.assertEqual(tiles[frappe._("Invoiced through Card (net before VAT)")], 1600)
		self.assertEqual(tiles[frappe._("Not invoiced through Card")], 0)
		self.assertEqual(
			tiles[frappe._("ERPNext invoices outside Card — to reconcile (net before VAT)")], 500
		)


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
