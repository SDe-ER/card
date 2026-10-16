# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#24: supplier and customer totals keep each side's additions/deductions.

A sub-rental card bills a supplier (Purchase Invoice: net_amount) and a
customer (Sales Invoice: customer_net_amount). The registries, summaries and
statements used to fold every row into the supplier net and leave the customer
side gross, so both reconciliations drifted from the invoices. All data is
per-test and rolled back."""

import frappe

from card.api import recompute_customer, recompute_supplier
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase

ADD, DED = "إضافة", "خصم"
PERIOD = {"from_month": 9, "from_year": 2026, "to_month": 9, "to_year": 2026}


def _run(module, filters):
	execute = frappe.get_attr(f"card.card.report.{module}.{module}.execute")
	_columns, rows, _message, _chart, summary, _flag = execute(frappe._dict(filters))
	return rows, summary


def _tile(summary, label):
	return next((i["value"] for i in summary if i["label"] == frappe._(label)), None)


class TestSidedTotals(_CustomerCardsBase):
	def setUp(self):
		super().setUp()
		# supplier 75/h x 48 h = 3,600 (+100 supplier addition) = 3,700
		# customer 120/h x 48 h = 5,760 (-200 customer deduction) = 5,560
		self.card = self._sub_card(
			[(ADD, 100, "Supplier", "TEST-SIDED-S"), (DED, 200, "Customer", "TEST-SIDED-C")]
		)

	def _sub_card(self, adjustments):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = self._sub_rental().name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days([10, 10, 10, 10, 8]):
			c.append("days", row)
		for kind, amount, side, description in adjustments:
			c.append(
				"adjustments",
				{"adjustment_type": kind, "amount": amount, "side": side, "description": description},
			)
		c.insert(ignore_permissions=True)
		c.submit()
		c.reload()
		return c

	def test_card_nets_are_the_invoice_figures(self):
		self.assertEqual((self.card.amount, self.card.net_amount), (3600, 3700))
		self.assertEqual((self.card.customer_amount, self.card.customer_net_amount), (5760, 5560))

	def test_registries_keep_each_side(self):
		recompute_supplier(self.supplier)
		recompute_customer(self.customer)
		self.assertEqual(frappe.db.get_value("Card Equipment Supplier", self.supplier, "total_net"), 3700)
		self.assertEqual(frappe.db.get_value("Card Equipment Customer", self.customer, "total_accrued"), 5560)

	def test_summaries_keep_each_side(self):
		rows, _ = _run("equipment_suppliers_summary", {"company": self.company, **PERIOD})
		row = next(r for r in rows if r.get("supplier") == self.supplier)
		self.assertEqual(row["net"], 3700)
		rows, _ = _run("equipment_customers_summary", {"company": self.company, **PERIOD})
		row = next(r for r in rows if r.get("customer") == self.customer)
		self.assertEqual(row["accrued"], 5560)

	def test_statements_keep_each_side(self):
		rows, summary = _run(
			"equipment_supplier_statement",
			{"company": self.company, "statement_type": "مورد", "supplier": self.supplier, **PERIOD},
		)
		card = next(r for r in rows if r.get("card") == self.card.name)
		self.assertEqual((card["additions"], card["deductions"], card["net"]), (100, 0, 3700))
		total = next(r for r in rows if r.get("row_id") == "TOTAL")
		self.assertEqual(total["net"], 3700)

		rows, summary = _run(
			"equipment_customer_statement",
			{"company": self.company, "customer": self.customer, **PERIOD},
		)
		card = next(r for r in rows if r.get("card") == self.card.name)
		self.assertEqual(
			(card["customer_amount"], card["additions"], card["deductions"], card["net"]),
			(5760, 0, 200, 5560),
		)
		self.assertEqual(_tile(summary, "Total accrued (cards)"), 5560)
		# nothing invoiced yet: the reconciliation difference is the customer net, not the gross
		self.assertEqual(_tile(summary, "Reconciliation difference"), 5560)

	def test_a_v1_1_row_without_side_counts_on_the_supplier_side(self):
		from card.adjustments import sided_adjustments

		row = self.card.adjustments[0]
		frappe.db.set_value(row.doctype, row.name, "side", None, update_modified=False)
		self.assertEqual(sided_adjustments([self.card.name], "Supplier"), {self.card.name: (100, 0)})
		self.assertEqual(sided_adjustments([self.card.name], "Customer"), {self.card.name: (0, 200)})

	def test_totals_equal_what_the_invoices_bill(self):
		# posting._card_lines builds the PI/SI lines of one card and side; its lines
		# minus the Net Total discount are the invoice net before VAT
		from card.gl.posting import _card_lines

		row = frappe._dict(
			rental_item="X",
			rental_out_item="X",
			equipment_rental_expense_account="X",
			equipment_rental_income_account="X",
		)
		billed = {}
		for side in ("Supplier", "Customer"):
			_doc, lines, discount = _card_lines(self.card.name, side, row, {})
			billed[side] = sum(line["rate"] for line in lines) - discount
		recompute_supplier(self.supplier)
		recompute_customer(self.customer)
		self.assertEqual(
			frappe.db.get_value("Card Equipment Supplier", self.supplier, "total_net"), billed["Supplier"]
		)
		self.assertEqual(
			frappe.db.get_value("Card Equipment Customer", self.customer, "total_accrued"), billed["Customer"]
		)

	def test_reports_stay_scoped_to_the_company(self):
		other = "TEST-SIDED-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": other,
				"abbr": "S" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = other
		co.db_insert()
		moved = self._sub_card([(DED, 50, "Customer", "TEST-SIDED-OTHER")])
		frappe.db.set_value("Card Monthly Card", moved.name, "company", other, update_modified=False)
		rows, _ = _run("equipment_suppliers_summary", {"company": self.company, **PERIOD})
		self.assertEqual(next(r for r in rows if r.get("supplier") == self.supplier)["net"], 3700)
		rows, _ = _run("equipment_customers_summary", {"company": self.company, **PERIOD})
		self.assertEqual(next(r for r in rows if r.get("customer") == self.customer)["accrued"], 5560)
		rows, _ = _run(
			"equipment_customer_statement", {"company": self.company, "customer": self.customer, **PERIOD}
		)
		self.assertNotIn(moved.name, [r.get("card") for r in rows])

	def test_patch_backfills_customer_net_of_pre_s3_cards(self):
		from card.patches.v1_2_1.backfill_customer_net_amount import execute

		frappe.db.set_value(
			"Card Monthly Card", self.card.name, "customer_net_amount", 0, update_modified=False
		)
		execute()
		self.assertEqual(
			frappe.db.get_value("Card Monthly Card", self.card.name, "customer_net_amount"), 5560
		)
		execute()  # idempotent
		self.assertEqual(
			frappe.db.get_value("Card Monthly Card", self.card.name, "customer_net_amount"), 5560
		)

	def test_patch_recomputes_stale_registry_totals(self):
		from card.patches.v1_2_1.recompute_party_registries import execute

		recompute_supplier(self.supplier)
		recompute_customer(self.customer)
		# what the pre-fix code stored: the mixed-side net and the gross accrual
		frappe.db.set_value("Card Equipment Supplier", self.supplier, "total_net", 3500)
		frappe.db.set_value("Card Equipment Customer", self.customer, "total_accrued", 5760)
		execute()
		self.assertEqual(frappe.db.get_value("Card Equipment Supplier", self.supplier, "total_net"), 3700)
		self.assertEqual(frappe.db.get_value("Card Equipment Customer", self.customer, "total_accrued"), 5560)
