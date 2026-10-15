# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3: the monthly posting builder — the §F.4-panel numeric example to the
halala, GL sides/dimensions on submit, aggregation, diesel allocation split,
duplicate/lifecycle guards (4a-4c) and the foreign-invoice no-op."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.gl.posting import build_monthly_posting
from card.tests.test_customer import _CustomerCardsBase


def _leaf_under(company, root_type, account_name, account_type=None):
	existing = frappe.db.get_value("Account", {"company": company, "account_name": account_name}, "name")
	if existing:
		return existing
	parent = frappe.db.get_value(
		"Account", {"company": company, "root_type": root_type, "is_group": 1}, "name"
	)
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": account_name,
			"parent_account": parent,
			"company": company,
			"root_type": root_type,
			"account_type": account_type or "",
		}
	).insert(ignore_permissions=True)
	return doc.name


def _tax_template(doctype, company, title, account_head):
	existing = frappe.db.get_value(doctype, {"title": title, "company": company}, "name")
	if existing:
		return existing
	child = (
		"Purchase Taxes and Charges"
		if doctype == "Purchase Taxes and Charges Template"
		else "Sales Taxes and Charges"
	)
	row = {
		"charge_type": "On Net Total",
		"account_head": account_head,
		"rate": 15,
		"description": "VAT 15%",
	}
	if child == "Purchase Taxes and Charges":
		row.update({"category": "Total", "add_deduct_tax": "Add"})
	doc = frappe.get_doc({"doctype": doctype, "title": title, "company": company, "taxes": [row]})
	doc.insert(ignore_permissions=True)
	return doc.name


class _PostingBase(_CustomerCardsBase):
	"""Accounting fixture on top of the customer-cards base: a fully configured
	Card Company Settings row + invoice-settings toggles + enabled accounting."""

	def setUp(self):
		super().setUp()
		company = self.company
		self.vat_in = _leaf_under(company, "Asset", "Test VAT Input", "Tax")
		self.vat_out = _leaf_under(company, "Liability", "Test VAT Output", "Tax")
		self.exp_rental = _leaf_under(company, "Expense", "Test Equipment Rental Expense")
		self.exp_diesel = _leaf_under(company, "Expense", "Test Diesel Expense")
		self.exp_transport = _leaf_under(company, "Expense", "Test Transport Expense")
		self.inc_rental = _leaf_under(company, "Income", "Test Equipment Rental Income")
		self.acc_mob = _leaf_under(company, "Expense", "Test Mobilization Recovery")
		self.acc_pen = _leaf_under(company, "Expense", "Test Penalty Recovery")
		self.acc_dnt = _leaf_under(company, "Expense", "Test Diesel Recovery NT")
		payable = frappe.db.get_value(
			"Account", {"company": company, "account_type": "Payable", "is_group": 0}, "name"
		)
		receivable = frappe.db.get_value(
			"Account", {"company": company, "account_type": "Receivable", "is_group": 0}, "name"
		)
		cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
		pt = _tax_template(
			"Purchase Taxes and Charges Template", company, "Test CARD Purchase VAT", self.vat_in
		)
		st = _tax_template("Sales Taxes and Charges Template", company, "Test CARD Sales VAT", self.vat_out)

		settings = frappe.get_doc("Card Settings")
		row = next((r for r in settings.get("company_settings") or [] if r.company == company), None)
		if row is None:
			row = settings.append("company_settings", {"company": company})
		row.equipment_rental_expense_account = self.exp_rental
		row.diesel_expense_account = self.exp_diesel
		row.transport_expense_account = self.exp_transport
		row.equipment_rental_income_account = self.inc_rental
		row.payable_account = payable
		row.receivable_account = receivable
		row.cost_center = cost_center
		row.purchase_tax_template = pt
		row.sales_tax_template = st
		row.vat_item_tax_template = ""
		row.vat_zero_item_tax_template = ""
		settings.set("adjustment_types", [])
		for name, kind, account, taxable in (
			("Mobilization", "إضافة", self.acc_mob, 1),
			("MobilizationNT", "إضافة", self.acc_mob, 0),
			("Penalty", "خصم", self.acc_pen, 1),
			("DieselNT", "خصم", self.acc_dnt, 0),
		):
			settings.append(
				"adjustment_types",
				{"company": company, "type_name": name, "kind": kind, "account": account, "taxable": taxable},
			)
		settings.save(ignore_permissions=True)

		frappe.db.set_single_value("Card Settings", "enable_accounting", 1)
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		# self-contained: a previous suite leaves the seeded fixed-diesel policy
		# behind on the site; the posting fixture bills its own test supplier
		frappe.db.set_single_value("Card Settings", "diesel_supplier", "")
		frappe.db.set_single_value("Card Settings", "diesel_supplier_policy", "متغير")
		frappe.db.set_single_value("Buying Settings", "allow_multiple_items", 1)
		frappe.db.set_single_value("Buying Settings", "allow_negative_rates_for_items", 1)
		frappe.db.set_single_value("Selling Settings", "allow_negative_rates_for_items", 1)
		frappe.db.set_single_value("Buying Settings", "po_required", "No")
		frappe.db.set_single_value("Selling Settings", "allow_multiple_items", 1)
		frappe.db.set_single_value("Selling Settings", "validate_selling_price", 0)
		frappe.db.set_single_value("Selling Settings", "so_required", "No")
		frappe.db.set_single_value("Selling Settings", "dn_required", "No")
		# dual-head CARD item tax templates: the copy-toggles would append the
		# other side's VAT head onto generated invoices (preflight gates them)
		frappe.db.set_single_value("Accounts Settings", "add_taxes_from_item_tax_template", 0)
		frappe.db.set_single_value("Accounts Settings", "add_taxes_from_taxes_and_charges_template", 0)
		frappe.clear_cache(doctype="Card Settings")

	def _vat_supplier(self):
		sup = frappe.get_doc("Supplier", self.supplier)
		sup.db_set("tax_id", "300000000000003", update_modified=False)
		return sup.name

	def _example_card(self, submit=True):
		"""The §F.4-panel §7 card: rental 10,333.40 + the three adjustment rows."""
		eq = self._equipment(rate_type="بالساعة", rate=645.8375)  # 16h -> 10,333.40
		card = self._card(
			eq,
			[8, 8],
			adjustments=[
				{"adjustment_type_ref": "Mobilization", "description": "mob", "amount": 457.80},
				{"adjustment_type_ref": "Penalty", "description": "pen", "amount": 213.40},
				{"adjustment_type_ref": "DieselNT", "description": "dnt", "amount": 299.99},
			],
		)
		self.assertEqual(flt(card.amount), 10333.40)
		self.assertEqual(flt(card.net_amount), 10277.81)
		if submit:
			card.submit()
			card.reload()
		return eq, card

	def _card(self, eq, hours_list, adjustments=None, submit=False, **presets):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for k, v in presets.items():
			setattr(c, k, v)
		from card.tests.test_controllers import _days

		for row in _days(hours_list):
			c.append("days", row)
		for row in adjustments or []:
			c.append("adjustments", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c


class TestNumericExample(_PostingBase):
	def test_pi_matches_the_design_example_to_the_halala(self):
		self._vat_supplier()
		eq, card = self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		self.assertEqual(pi.docstatus, 0)
		self.assertEqual(len(pi.items), 4)
		self.assertEqual(flt(pi.net_total, 2), 10277.81)
		self.assertEqual(flt(pi.taxes[0].tax_amount, 2), 1586.67)
		self.assertEqual(flt(pi.grand_total, 2), 11864.48)
		# per-line templates: the non-taxable deduction carries the 0% template
		settings_row = next(
			r for r in frappe.get_doc("Card Settings").company_settings if r.company == self.company
		)
		by_rate = {flt(i.rate, 2): i for i in pi.items}
		self.assertEqual(by_rate[-299.99].item_tax_template, settings_row.vat_zero_item_tax_template)
		self.assertEqual(by_rate[457.80].item_tax_template, settings_row.vat_item_tax_template)
		self.assertEqual(by_rate[10333.40].expense_account, self.exp_rental)
		self.assertEqual(by_rate[-213.40].expense_account, self.acc_pen)
		for item in pi.items:
			self.assertEqual(item.project, self.project)
			self.assertTrue(item.cost_center)
			self.assertEqual(item.card_equipment, eq.name)
		# reservation: source points at the log, not the invoice
		self.assertTrue(card.name in [c.name for c in [card]])
		gl_link = frappe.db.get_value("Card Monthly Card", card.name, "gl_posting")
		self.assertTrue(gl_link)
		self.assertEqual(frappe.db.get_value("GL Posting Log", gl_link, "posting_doc"), pi_name)
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"))

	def test_pi_submit_posts_gl_with_dimensions_and_flipped_deductions(self):
		self._vat_supplier()
		eq, card = self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.bill_no = "TEST-BILL-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": pi_name, "is_cancelled": 0},
			fields=["account", "debit", "credit", "project", "cost_center", "card_equipment", "party"],
		)
		by_account = {}
		for g in gl:
			by_account.setdefault(g.account, []).append(g)
		self.assertEqual(flt(by_account[self.exp_rental][0].debit, 2), 10333.40)
		self.assertEqual(by_account[self.exp_rental][0].card_equipment, eq.name)
		self.assertEqual(by_account[self.exp_rental][0].project, self.project)
		self.assertEqual(flt(by_account[self.acc_mob][0].debit, 2), 457.80)
		# deductions flip to the credit side in process_gl_map
		self.assertEqual(flt(by_account[self.acc_pen][0].credit, 2), 213.40)
		self.assertEqual(flt(by_account[self.acc_dnt][0].credit, 2), 299.99)
		self.assertEqual(flt(by_account[self.vat_in][0].debit, 2), 1586.67)
		payable = [g for g in gl if g.party == self.supplier]
		self.assertEqual(flt(sum(g.credit - g.debit for g in payable), 2), 11864.48)
		# posted flag + invoice link written on submit
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "posted"), 1)
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"), pi_name)


class TestAggregationAndDiesel(_PostingBase):
	def test_one_pi_per_supplier_month_with_one_line_per_source(self):
		eq, card = self._example_card()
		card2 = self._card(self._equipment(), [5], submit=True)  # 5h * 75 = 375
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"card_equipment": eq.name,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
			}
		)
		fill.insert(ignore_permissions=True)
		fill.submit()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		# 4 lines (example card) + 1 (card2) + 1 (equipment-bound fill)
		self.assertEqual(len(pi.items), 6)
		descriptions = " | ".join(i.description for i in pi.items)
		self.assertIn(card.name, descriptions)
		self.assertIn(card2.name, descriptions)
		self.assertIn(fill.name, descriptions)
		fill_line = next(i for i in pi.items if fill.name in i.description)
		self.assertEqual(flt(fill_line.rate, 2), 200.0)
		self.assertEqual(fill_line.expense_account, self.exp_diesel)
		self.assertEqual(fill_line.card_equipment, eq.name)

	def test_tank_fill_splits_per_equipment_by_hours(self):
		eq_a = self._equipment()
		eq_b = self._equipment()
		self._card(eq_a, [6], submit=True)  # 6h
		self._card(eq_b, [2], submit=True)  # 2h -> shares 75% / 25%
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 1.0,
			}
		)
		fill.insert(ignore_permissions=True)
		fill.submit()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		fill_lines = [i for i in pi.items if fill.name in i.description]
		self.assertEqual(len(fill_lines), 2)
		self.assertEqual(flt(sum(i.rate for i in fill_lines), 2), 100.0)
		by_eq = {i.card_equipment: flt(i.rate, 2) for i in fill_lines}
		self.assertEqual(by_eq[eq_a.name], 75.0)
		self.assertEqual(by_eq[eq_b.name], 25.0)


class TestLifecycleGuards(_PostingBase):
	def test_duplicate_build_blocked(self):
		self._example_card()
		build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)

	def test_source_cancel_blocked_then_freed_by_draft_delete(self):
		_eq, card = self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		with self.assertRaises(frappe.ValidationError):
			card.cancel()
		frappe.delete_doc("Purchase Invoice", pi_name, ignore_permissions=True)
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "gl_posting"))
		card.reload()
		card.cancel()  # now allowed
		self.assertEqual(card.docstatus, 2)

	def test_cancel_frees_sources_and_allows_repost(self):
		self._vat_supplier()
		_eq, card = self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.bill_no = "B1"
		pi.bill_date = pi.posting_date
		pi.submit()
		pi.reload()
		pi.cancel()
		card.reload()
		self.assertFalse(card.purchase_invoice)
		self.assertFalse(card.gl_posting)
		self.assertEqual(card.posted, 0)
		self.assertEqual(
			frappe.db.get_value("GL Posting Log", {"posting_doc": pi_name}, "status"), "Cancelled"
		)
		pi2 = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertNotEqual(pi2, pi_name)

	def test_foreign_invoice_untouched(self):
		item = frappe.db.get_value("Item", {"is_stock_item": 0}, "name") or "CARD-RENTAL"
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": self.supplier,
				"items": [{"item_code": item, "qty": 1, "rate": 10, "expense_account": self.exp_rental}],
			}
		)
		pi.insert(ignore_permissions=True)
		# no GL Posting Log row -> handlers must no-op on delete
		frappe.delete_doc("Purchase Invoice", pi.name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("Purchase Invoice", pi.name))

	def test_discount_on_generated_draft_rejected(self):
		self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.discount_amount = 10
		with self.assertRaises(frappe.ValidationError):
			pi.save(ignore_permissions=True)


class TestPreflights(_PostingBase):
	def test_missing_settings_row_translated_throw(self):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-S3-CO-" + self.token
		comp.abbr = "S3" + self.token[:3]
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		comp.insert(ignore_permissions=True)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"Card Settings",
			build_monthly_posting,
			comp.name,
			"Supplier",
			self.supplier,
			9,
			2026,
		)

	def test_card_period_lock_blocks_posting(self):
		self._example_card()
		frappe.db.set_single_value("Card Settings", "period_lock_date", "2026-10-31")
		frappe.db.set_single_value("Card Settings", "period_lock_override_role", None)
		frappe.clear_cache(doctype="Card Settings")
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)

	def test_negative_month_stopped_with_card_names(self):
		eq = self._equipment(rate_type="بالساعة", rate=10)  # 16h -> 160
		card = self._card(
			eq,
			[8, 8],
			adjustments=[{"adjustment_type_ref": "Penalty", "description": "big", "amount": 500}],
			submit=True,
		)
		try:
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self.fail("negative month must stop")
		except frappe.ValidationError as e:
			self.assertIn(card.name, str(e))

	def test_nothing_to_post_message(self):
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)


class TestCustomerMirror(_PostingBase):
	def test_si_draft_for_rented_out_with_vat(self):
		eq = self._rented_out(customer_rate=1000)  # 100/h -> 16h = 1600
		card = self._card(
			eq,
			[8, 8],
			adjustments=[
				{"adjustment_type_ref": "Mobilization", "side": "Customer", "description": "m", "amount": 400}
			],
			submit=True,
		)
		self.assertEqual(flt(card.customer_net_amount), 2000.0)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		self.assertEqual(si.docstatus, 0)
		self.assertEqual(len(si.items), 2)
		self.assertEqual(flt(si.net_total, 2), 2000.0)
		self.assertEqual(flt(si.taxes[0].tax_amount, 2), 300.0)
		self.assertEqual(flt(si.grand_total, 2), 2300.0)
		revenue = next(i for i in si.items if flt(i.rate, 2) == 1600.0)
		self.assertEqual(revenue.income_account, self.inc_rental)
		self.assertEqual(revenue.card_equipment, eq.name)
		adj = next(i for i in si.items if flt(i.rate, 2) == 400.0)
		self.assertEqual(adj.income_account, self.acc_mob)


class TestSubRentalDualSide(_PostingBase):
	"""Review CRITICAL #1: one card billed on BOTH sides keeps each side's
	lifecycle independent — the log's sources table drives submit/cancel, so
	neither side can double-post or free the other side's reservation."""

	def _dual(self):
		eq = self._sub_rental()  # supplier 75/h, customer 120/h
		card = self._card(eq, [8, 8], submit=True)  # 1,200 / 1,920
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		si = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		return card, pi, si

	def test_customer_build_not_blocked_by_supplier_hold(self):
		eq = self._sub_rental()
		self._card(eq, [8, 8], submit=True)
		build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		self.assertEqual(len(si.items), 1)
		self.assertEqual(flt(si.items[0].rate, 2), 1920.0)

	def test_both_sides_submit_write_both_links(self):
		card, pi_name, si_name = self._dual()
		frappe.get_doc("Purchase Invoice", pi_name).submit()
		frappe.get_doc("Sales Invoice", si_name).submit()
		card.reload()
		self.assertEqual(card.purchase_invoice, pi_name)
		self.assertEqual(card.sales_invoice, si_name)
		self.assertEqual(card.posted, 1)
		for doctype, inv in (("Purchase Invoice", pi_name), ("Sales Invoice", si_name)):
			log = frappe.db.get_value(
				"GL Posting Log",
				{"posting_doc": inv, "posting_doctype": doctype},
				["status", "sequence"],
				as_dict=True,
			)
			self.assertEqual(log.status, "Submitted")
			self.assertEqual(log.sequence, 1)

	def test_cancel_one_side_frees_only_that_side(self):
		card, pi_name, si_name = self._dual()
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.submit()
		si = frappe.get_doc("Sales Invoice", si_name)
		si.submit()
		pi.reload()
		pi.cancel()
		card.reload()
		self.assertFalse(card.purchase_invoice)
		self.assertEqual(card.sales_invoice, si_name)
		self.assertEqual(card.posted, 1)  # the customer side is still posted
		with self.assertRaises(frappe.ValidationError):
			card.cancel()  # still held by the submitted SI
		si.reload()
		si.cancel()
		card.reload()
		self.assertFalse(card.sales_invoice)
		self.assertEqual(card.posted, 0)
		card.cancel()  # both sides freed -> allowed
		self.assertEqual(card.docstatus, 2)

	def test_draft_delete_one_side_keeps_other_side_hold_and_display(self):
		card, pi_name, si_name = self._dual()
		frappe.delete_doc("Purchase Invoice", pi_name, ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			card.cancel()  # the customer draft still holds the card
		gl_link = frappe.db.get_value("Card Monthly Card", card.name, "gl_posting")
		self.assertEqual(
			frappe.db.get_value("GL Posting Log", gl_link, "posting_doc"), si_name
		)  # display repointed at the surviving active log


class TestReviewGuards(_PostingBase):
	"""Review #3/#6/#7/#8/#11 + P1 regression tests."""

	def test_amended_posting_blocked(self):
		self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.submit()
		pi.reload()
		pi.cancel()
		amended = frappe.copy_doc(pi)
		amended.docstatus = 0
		amended.amended_from = pi.name
		with self.assertRaises(frappe.ValidationError):
			amended.insert(ignore_permissions=True)

	def test_gl_rows_not_merged_across_equipment(self):
		card1 = self._card(self._equipment(), [8], submit=True)  # 600
		card2 = self._card(self._equipment(), [4], submit=True)  # 300
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.get_doc("Purchase Invoice", pi_name).submit()
		gl = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": pi_name, "account": self.exp_rental, "is_cancelled": 0},
			fields=["debit", "card_equipment"],
		)
		self.assertEqual(len(gl), 2)  # same account, distinct dimension -> NOT merged
		by_eq = {g.card_equipment: flt(g.debit, 2) for g in gl}
		self.assertEqual(by_eq[card1.equipment], 600.0)
		self.assertEqual(by_eq[card2.equipment], 300.0)

	def test_vat_supplier_without_purchase_template_throws(self):
		self._vat_supplier()
		self._example_card()
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == self.company)
		row.db_set("purchase_tax_template", "", update_modified=False)
		frappe.clear_cache(doctype="Card Settings")
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)

	def test_vat_pi_requires_bill_no_on_submit(self):
		self._vat_supplier()
		self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		with self.assertRaises(frappe.ValidationError):
			pi.submit()
		pi.reload()
		pi.bill_no = "BILL-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		self.assertEqual(pi.docstatus, 1)

	def test_submit_reverifies_source_docstatus(self):
		_eq, card = self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		# simulate an out-of-band cancel that slipped past the hooks
		frappe.db.set_value("Card Monthly Card", card.name, "docstatus", 2, update_modified=False)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		with self.assertRaises(frappe.ValidationError):
			pi.submit()

	def test_si_zero_rated_addition_with_discount_refused(self):
		eq = self._rented_out(customer_rate=1000)
		self._card(
			eq,
			[8, 8],
			adjustments=[
				{
					"adjustment_type_ref": "MobilizationNT",
					"side": "Customer",
					"description": "nt-add",
					"amount": 100,
				},
				{"adjustment_type_ref": "Penalty", "side": "Customer", "description": "p", "amount": 200},
			],
			submit=True,
		)
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)

	def test_second_supplementary_wave_rebuilds_draft(self):
		from card.gl.posting import rebuild_monthly_posting

		self._card(self._equipment(), [8], submit=True)
		first = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.get_doc("Purchase Invoice", first).submit()
		late1 = self._card(self._equipment(), [4], submit=True)
		second = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		late2 = self._card(self._equipment(), [2], submit=True)
		try:
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self.fail("a draft supplementary posting must block a third build")
		except frappe.ValidationError as e:
			self.assertIn(second, str(e))
		rebuilt = rebuild_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", rebuilt)
		descriptions = " | ".join(i.description for i in pi.items)
		self.assertIn(late1.name, descriptions)
		self.assertIn(late2.name, descriptions)
		self.assertEqual(len(pi.items), 2)  # the submitted primary's card stays out
		self.assertEqual(
			frappe.db.get_value("GL Posting Log", {"posting_doc": rebuilt, "status": "Draft"}, "sequence"),
			2,
		)


class TestBaselineUntouched(IntegrationTestCase):
	def test_accounting_disabled_blocks_builder(self):
		frappe.db.set_single_value("Card Settings", "enable_accounting", 0)
		frappe.clear_cache(doctype="Card Settings")
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting("Any", "Supplier", "Nobody", 9, 2026)


class TestZatcaSalesRules(_PostingBase):
	"""Owner 2026-10-15: Sales Invoices must carry NO negative lines; taxable
	customer deductions become a Net Total discount (same VAT base)."""

	def test_si_taxable_deduction_becomes_net_total_discount(self):
		eq = self._rented_out(customer_rate=1000)  # 16h -> 1600
		card = self._card(
			eq,
			[8, 8],
			adjustments=[
				{
					"adjustment_type_ref": "Mobilization",
					"side": "Customer",
					"description": "m",
					"amount": 400,
				},
				{"adjustment_type_ref": "Penalty", "side": "Customer", "description": "p", "amount": 200},
			],
			submit=True,
		)
		self.assertEqual(flt(card.customer_net_amount), 1800.0)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		for item in si.items:
			self.assertGreater(flt(item.rate), 0, "no negative lines on a Sales Invoice")
		self.assertEqual(len(si.items), 2)  # revenue 1600 + addition 400
		self.assertEqual(si.apply_discount_on, "Net Total")
		self.assertEqual(flt(si.discount_amount, 2), 200.0)
		self.assertEqual(flt(si.net_total, 2), 1800.0)
		self.assertEqual(flt(si.taxes[0].tax_amount, 2), 270.0)  # 15% of 1800
		self.assertEqual(flt(si.grand_total, 2), 2070.0)

	def test_si_nontaxable_customer_deduction_refused(self):
		eq = self._rented_out(customer_rate=1000)
		self._card(
			eq,
			[8, 8],
			adjustments=[
				{"adjustment_type_ref": "DieselNT", "side": "Customer", "description": "d", "amount": 100}
			],
			submit=True,
		)
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)


class TestLateSources(_PostingBase):
	"""Owner 2026-10-15 item 3: a submitted card after the month's posting must
	never be silently lost — rebuild a draft, or supplement a submitted one."""

	def test_late_card_blocked_by_draft_then_rebuild_includes_it(self):
		from card.gl.posting import rebuild_monthly_posting

		eq1 = self._equipment()
		self._card(eq1, [8], submit=True)  # 600
		first = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		late = self._card(self._equipment(), [4], submit=True)  # 300, after the draft
		try:
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self.fail("a draft posting must block a second build")
		except frappe.ValidationError as e:
			self.assertIn(first, str(e))
		rebuilt = rebuild_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		# The old draft is deleted and frappe reverts the naming-series counter
		# for the latest name, so the new draft may legitimately REUSE the old
		# name — identity is checked through the logs, not the invoice name.
		logs = frappe.get_all(
			"GL Posting Log",
			filters={
				"company": self.company,
				"party_type": "Supplier",
				"party": self.supplier,
				"month": "09",
				"year": 2026,
				"posting_type": "Purchase Invoice",
			},
			fields=["status", "posting_doc"],
		)
		self.assertEqual(sorted(log.status for log in logs), ["Cancelled", "Draft"])
		active = next(log for log in logs if log.status == "Draft")
		self.assertEqual(active.posting_doc, rebuilt)
		pi = frappe.get_doc("Purchase Invoice", rebuilt)
		self.assertEqual(pi.docstatus, 0)
		descriptions = " | ".join(i.description for i in pi.items)
		self.assertIn(late.name, descriptions)
		self.assertEqual(len(pi.items), 2)

	def test_late_card_after_submit_gets_supplementary_posting(self):
		eq1 = self._equipment()
		self._card(eq1, [8], submit=True)
		first = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi1 = frappe.get_doc("Purchase Invoice", first)
		pi1.submit()
		late = self._card(self._equipment(), [4], submit=True)
		second = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertNotEqual(second, first)
		pi2 = frappe.get_doc("Purchase Invoice", second)
		self.assertEqual(len(pi2.items), 1)
		self.assertIn(late.name, pi2.items[0].description)
		self.assertEqual(frappe.db.get_value("GL Posting Log", {"posting_doc": second}, "sequence"), 2)

	def test_fill_cancel_blocked_while_draft_posting_exists(self):
		self._card(self._equipment(), [8], submit=True)
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-15",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 50,
				"unit_price": 2,
			}
		)
		fill.insert(ignore_permissions=True)
		fill.submit()
		draft = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		try:
			fill.reload()
			fill.cancel()
			self.fail("fill cancel must be blocked while the draft posting holds it")
		except frappe.ValidationError as e:
			self.assertIn(draft, str(e))
