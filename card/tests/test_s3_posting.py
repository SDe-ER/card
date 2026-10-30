# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3: the monthly posting builder — the §F.4-panel numeric example to the
halala, GL sides/dimensions on submit, aggregation, diesel allocation split,
duplicate/lifecycle guards (4a-4c) and the foreign-invoice no-op."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.gl.posting import build_monthly_posting
from card.tests.diesel_price import approve_fill, use_fill_price
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
		# P0: the fixture's diesel prices are VAT-exclusive (the VAT-inclusive path is tested in test_p0_posting_integrity)
		row.diesel_price_vat_basis = "Exclusive"
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

	def _unrelated_manual_invoices(self):
		"""P0 (FR-090): the supplier's hand-booked invoices around 09/2026 (the evidence window) that CARD did not build, as an
		accountant who reviewed them as separate charges would list them for the build."""
		return [
			name
			for name in frappe.get_all(
				"Purchase Invoice",
				filters={
					"supplier": self.supplier,
					"docstatus": ["<", 2],
					"is_return": 0,
					"posting_date": ["between", ["2026-08-01", "2026-12-01"]],
				},
				pluck="name",
			)
			if not frappe.db.exists(
				"GL Posting Log", {"posting_doc": name, "status": ["in", ["Draft", "Submitted"]]}
			)
		]

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

	def _assert_no_posting_artifacts(self, card):
		"""A failed preflight must leave NO invoice, log or reservation behind."""
		self.assertFalse(
			frappe.get_all("Purchase Invoice", filters={"supplier": self.supplier, "docstatus": 0})
		)
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "gl_posting"))
		self.assertFalse(frappe.get_all("GL Posting Source", filters={"source_name": card.name}))

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
		# company currency always wins over the site/user default currency
		self.assertEqual(pi.currency, frappe.db.get_value("Company", self.company, "default_currency"))
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
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
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

	def test_imported_fill_is_never_posted(self):
		"""FR-086b (Owner 2026-10-27): an imported WhatsApp session is accounted by its supplier's own
		Purchase Invoice in Desk (its price includes VAT), so the monthly posting leaves it out."""
		fills = []
		for imported in (False, True):
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
			if imported:
				fill.flags.diesel_import = True
				fill.source_key = "WA-TEST-POSTING-" + frappe.generate_hash(length=8)
				fill.source_messages = "WA-TEST-1"  # the import always sets it (message ids, photo hashes)
			use_fill_price(fill).insert(ignore_permissions=True)
			approve_fill(fill)
			fill.submit()
			fills.append(fill)
		# an amendment of the imported fill keeps its source (not its unique key) and stays out too
		fills[1].cancel()
		amended = frappe.copy_doc(fills[1])
		amended.amended_from = fills[1].name
		amended.docstatus = 0
		amended.insert(ignore_permissions=True)
		self.assertFalse(amended.source_key)
		approve_fill(amended)
		amended.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		descriptions = " | ".join(i.description for i in pi.items)
		self.assertIn(fills[0].name, descriptions)
		self.assertNotIn(fills[1].name, descriptions)
		self.assertNotIn(amended.name, descriptions)
		# only the normal fill is on the invoice, in full: 100 L x 2 = 200, nothing counted twice
		self.assertEqual(
			sum(flt(i.rate, 2) for i in pi.items if fills[0].name in (i.description or "")), 200.0
		)
		for name in (fills[1].name, amended.name):
			self.assertFalse(frappe.db.get_value("Project Diesel Fill", name, "purchase_invoice"))

	def test_mixed_direct_and_tank_fill_split_by_hours_only(self):
		"""Checkpoint C: direct fills must never influence tank-fill weights."""
		eq_a = self._equipment()
		eq_b = self._equipment()
		self._card(eq_a, [5], submit=True)  # 5h
		self._card(eq_b, [5], submit=True)  # 5h -> hours say 50/50

		def _fill(**kw):
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
			use_fill_price(f).insert(ignore_permissions=True)
			approve_fill(f)
			f.submit()
			return f

		direct = _fill(card_equipment=eq_a.name, litres=1000, unit_price=2)  # 2,000 all to A
		tank = _fill(litres=100, unit_price=1)  # 100 -> 50/50 by hours, NOT by litres
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		direct_lines = [i for i in pi.items if direct.name in i.description]
		self.assertEqual(len(direct_lines), 1)
		self.assertEqual(flt(direct_lines[0].rate, 2), 2000.0)
		self.assertEqual(direct_lines[0].card_equipment, eq_a.name)
		tank_by_eq = {i.card_equipment: flt(i.rate, 2) for i in pi.items if tank.name in i.description}
		self.assertEqual(tank_by_eq, {eq_a.name: 50.0, eq_b.name: 50.0})

	def test_tank_fill_without_hours_stays_unallocated(self):
		"""Checkpoint C: no eligible operating hours -> the whole cost is kept
		as ONE project-level line with no invented equipment attribution."""
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-10-10",  # a month with no submitted cards on the project
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 300,
				"unit_price": 2,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 10, 2026)
		)
		self.assertEqual(len(pi.items), 1)
		self.assertEqual(flt(pi.items[0].rate, 2), 600.0)
		self.assertEqual(pi.items[0].project, self.project)
		self.assertFalse(pi.items[0].card_equipment)

	def test_tank_fill_rounding_preserves_total_to_the_halala(self):
		"""Checkpoint C: equal thirds cannot split 100.00 evenly — the
		largest-remainder line absorbs the halala and the sum stays exact."""
		for _ in range(3):
			self._card(self._equipment(), [1], submit=True)  # 1h each
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 50,
				"unit_price": 2,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		tank_lines = sorted(flt(i.rate, 2) for i in pi.items if fill.name in i.description)
		self.assertEqual(tank_lines, [33.33, 33.33, 33.34])
		self.assertEqual(flt(sum(tank_lines), 2), 100.0)

	def test_tank_allocation_isolated_by_project_and_month(self):
		"""Checkpoint C: only the fill's own project + month hours weigh the
		split — other projects and other months contribute nothing."""
		from card.tests.test_controllers import _days

		eq_a = self._equipment()
		eq_b = self._equipment()
		eq_c = self._equipment()
		self._card(eq_a, [8], submit=True)  # self.project, month 09
		proj2 = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "TEST-S3-ISO-" + self.token,
				"status": "Open",
				"company": self.company,
			}
		).insert(ignore_permissions=True)
		self._card(eq_b, [8], submit=True, project=proj2.name)  # other project, same month
		other_month = frappe.new_doc("Card Monthly Card")  # same project, month 08
		other_month.equipment = eq_c.name
		other_month.project = self.project
		other_month.shift = "نهاري"
		other_month.month = "08"
		other_month.year = 2026
		for day in _days([8], month=8):
			other_month.append("days", day)
		other_month.insert(ignore_permissions=True)
		other_month.submit()

		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 1,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		tank_lines = [i for i in pi.items if fill.name in i.description]
		self.assertEqual(len(tank_lines), 1)  # ONLY eq_a operated on this project in 09
		self.assertEqual(tank_lines[0].card_equipment, eq_a.name)
		self.assertEqual(flt(tank_lines[0].rate, 2), 100.0)

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
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
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
		# self-contained on a clean site: provision the CARD items instead of
		# assuming ANY non-stock Item exists (clean-site CI regression)
		from card.gl.masters import ensure_posting_masters

		row = ensure_posting_masters(self.company)
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": self.supplier,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"items": [
					{"item_code": row.rental_item, "qty": 1, "rate": 10, "expense_account": self.exp_rental}
				],
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

	def test_posting_rejected_when_dimension_disabled(self):
		"""Checkpoint B (fail-closed): no posting without an ACTIVE Card
		Equipment accounting dimension — and no bypass toggle."""
		_eq, card = self._example_card()
		dim = frappe.db.get_value("Accounting Dimension", {"document_type": "Card Equipment"}, "name")
		self.assertTrue(dim, "fixture sites must carry the dimension (before_tests provisions it)")
		frappe.db.set_value("Accounting Dimension", dim, "disabled", 1, update_modified=False)
		try:
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self.fail("posting must fail closed while the dimension is disabled")
		except frappe.ValidationError as e:
			self.assertIn("ensure_card_equipment_dimension", str(e))
		finally:
			frappe.db.set_value("Accounting Dimension", dim, "disabled", 0, update_modified=False)
		self._assert_no_posting_artifacts(card)
		# re-enabled -> the same month builds normally
		self.assertTrue(build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026))

	def test_posting_rejected_when_dimension_record_missing(self):
		"""Checkpoint B: a site whose dimension record was removed (fields may
		still exist) must also fail closed, atomically."""
		_eq, card = self._example_card()
		# transactional raw delete: rolled back with the test
		frappe.db.delete("Accounting Dimension", {"document_type": "Card Equipment"})
		try:
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self.fail("posting must fail closed while the dimension record is missing")
		except frappe.ValidationError as e:
			self.assertIn("ensure_card_equipment_dimension", str(e))
		self._assert_no_posting_artifacts(card)

	def test_gate_rejects_missing_dimension_fields(self):
		"""Checkpoint B: the gate also refuses when the custom field is gone
		from the invoice-item doctype or from GL Entry (meta checked per
		doctype; simulated — dropping real fields is DDL)."""
		from unittest.mock import patch

		from card.gl import preflight

		real_get_meta = frappe.get_meta

		def _hiding(target_dt):
			class _Meta:
				def __init__(self, real):
					self._real = real

				def has_field(self, fieldname):
					return False if fieldname == "card_equipment" else self._real.has_field(fieldname)

				def __getattr__(self, name):
					return getattr(self._real, name)

			def _get_meta(dt, *args, **kwargs):
				meta = real_get_meta(dt, *args, **kwargs)
				return _Meta(meta) if dt == target_dt else meta

			return _get_meta

		for target in ("Purchase Invoice Item", "GL Entry"):
			with patch.object(frappe, "get_meta", side_effect=_hiding(target)):
				with self.assertRaises(frappe.ValidationError):
					preflight.require_equipment_dimension("Purchase Invoice")


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
		# company currency always wins over the site/user default currency
		self.assertEqual(si.currency, frappe.db.get_value("Company", self.company, "default_currency"))
		self.assertTrue(si.selling_price_list)  # mandatory on SI; resolved deterministically
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


class TestG0LifecycleDebt(_PostingBase):
	"""G0 (owner-authorized): review-debt fixes on the SHARED lifecycle layer.
	H1 status-filtered unit resolution; H2 log tamper guards; H3 submit-time
	identity + period re-assert; M5 generalized template shape; M6 shared
	rounding; §5a type-free reservation scope."""

	def _draft_je(self, submit=False):
		"""A minimal Journal Entry standing in for a G2 posting document."""
		je = frappe.new_doc("Journal Entry")
		je.company = self.company
		je.posting_date = "2026-09-30"
		cc = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		je.append(
			"accounts",
			{"account": self.exp_rental, "debit_in_account_currency": 100, "cost_center": cc},
		)
		je.append(
			"accounts",
			{"account": self.exp_diesel, "credit_in_account_currency": 100, "cost_center": cc},
		)
		je.insert(ignore_permissions=True)
		if submit:
			je.submit()
		return je

	def _je_log(self, je, status="Draft", sources=None, sequence=1):
		log = frappe.get_doc(
			{
				"doctype": "GL Posting Log",
				"company": self.company,
				"party_type": "Supplier",
				"party": self.supplier,
				"month": "09",
				"year": 2026,
				"posting_type": "Journal Entry",
				"sequence": sequence,
				"status": status,
				"posting_doctype": "Journal Entry",
				"posting_doc": je.name,
			}
		)
		for doctype, name in sources or []:
			log.append("sources", {"source_doctype": doctype, "source_name": name, "amount": 0})
		log.flags.card_gl_build = True  # #57: an out-of-band unit, inserted as the builder would
		log.insert(ignore_permissions=True)
		return log

	# ---- H1: unit resolution must bind the ACTIVE log, not a cancelled namesake ----
	def test_submit_binds_the_active_log_after_name_reuse(self):
		from card.gl.posting import rebuild_monthly_posting

		self._card(self._equipment(), [8], submit=True)
		first = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		old_log = frappe.db.get_value("GL Posting Log", {"posting_doc": first, "status": "Draft"}, "name")
		self._card(self._equipment(), [4], submit=True)
		rebuilt = rebuild_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		new_log = frappe.db.get_value("GL Posting Log", {"posting_doc": rebuilt, "status": "Draft"}, "name")
		self.assertEqual(first, rebuilt)  # premise: frappe reverts the series -> same name
		self.assertNotEqual(old_log, new_log)
		# make the CANCELLED log the most recently touched (reviewer scenario)
		frappe.db.set_value("GL Posting Log", old_log, "remarks", "touched")
		frappe.get_doc("Purchase Invoice", rebuilt).submit()
		self.assertEqual(frappe.db.get_value("GL Posting Log", new_log, "status"), "Submitted")
		self.assertEqual(frappe.db.get_value("GL Posting Log", old_log, "status"), "Cancelled")

	# ---- H2: the authoritative log cannot be deleted while active ----
	def test_active_log_delete_refused(self):
		self._example_card()
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		log = frappe.db.get_value("GL Posting Log", {"posting_doc": pi, "status": "Draft"}, "name")
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("GL Posting Log", log, ignore_permissions=True)

	# ---- H3: value edits and period locks are re-asserted at submit ----
	def test_edited_draft_total_refused_at_submit(self):
		self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.items[0].rate = flt(pi.items[0].rate) - 1000
		pi.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			pi.submit()

	def test_card_period_lock_reasserted_at_submit(self):
		self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.db.set_single_value("Card Settings", "period_lock_date", "2026-10-31")
		frappe.db.set_single_value("Card Settings", "period_lock_override_role", None)
		frappe.clear_cache(doctype="Card Settings")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Purchase Invoice", pi_name).submit()

	# ---- M5: multi-row VAT templates are a valid shape; foreign charge types are not ----
	def test_multi_row_vat_template_shape_accepted(self):
		from card.gl.masters import vat_account_heads

		head2 = _leaf_under(self.company, "Asset", "Test VAT Input Second", "Tax")
		template = frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": "Test CGST-SGST style " + self.token,
				"company": self.company,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": self.vat_in,
						"rate": 9,
						"description": "A",
						"category": "Total",
						"add_deduct_tax": "Add",
					},
					{
						"charge_type": "On Net Total",
						"account_head": head2,
						"rate": 6,
						"description": "B",
						"category": "Total",
						"add_deduct_tax": "Add",
					},
				],
			}
		).insert(ignore_permissions=True)
		row = frappe._dict(purchase_tax_template=template.name, sales_tax_template=None)
		self.assertEqual(vat_account_heads(row), {self.vat_in, head2})

	def test_foreign_charge_type_still_refused(self):
		from card.gl.masters import vat_account_heads

		template = frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": "Test foreign charge " + self.token,
				"company": self.company,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": self.vat_in,
						"rate": 15,
						"description": "A",
						"category": "Total",
						"add_deduct_tax": "Add",
					},
					{
						"charge_type": "On Previous Row Total",
						"row_id": "1",
						"account_head": self.vat_in,
						"rate": 1,
						"description": "B",
						"category": "Total",
						"add_deduct_tax": "Add",
					},
				],
			}
		).insert(ignore_permissions=True)
		row = frappe._dict(purchase_tax_template=template.name, sales_tax_template=None)
		with self.assertRaises(frappe.ValidationError):
			vat_account_heads(row)

	# ---- M6: posting and display put the rounding halala on the SAME equipment ----
	def test_posting_and_display_remainder_agree(self):
		from card.diesel import allocate_project_diesel

		eqs = [self._equipment() for _ in range(3)]
		for eq in eqs:
			self._card(eq, [1], submit=True)
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-12",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 50,
				"unit_price": 2,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		posted = {i.card_equipment: flt(i.rate, 2) for i in pi.items if fill.name in i.description}
		display = {
			eq: flt(v["amount"], 2)
			for eq, v in allocate_project_diesel(self.project, 9, 2026, self.company).items()
		}
		self.assertEqual(posted, display)

	# ---- §5a: reservation is type-free (one active unit per party-month-side) ----
	def test_draft_unit_of_another_type_blocks_build(self):
		_eq, card = self._example_card()
		je = self._draft_je()
		self._je_log(je, status="Draft")
		logs_before = len(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))
		try:
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self.fail("a draft unit of ANY document type must block a second build")
		except frappe.ValidationError as e:
			self.assertIn(je.name, str(e))
		# the refused build left no NEW artifacts (the synthetic JE unit remains)
		self.assertFalse(
			frappe.get_all("Purchase Invoice", filters={"supplier": self.supplier, "docstatus": 0})
		)
		self.assertEqual(len(frappe.get_all("GL Posting Log", filters={"party": self.supplier})), logs_before)
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "gl_posting"))
		self.assertFalse(frappe.get_all("GL Posting Source", filters={"source_name": card.name}))

	def test_cross_type_supplementary_sequence_and_exclusion(self):
		card1 = self._card(self._equipment(), [8], submit=True)
		card2 = self._card(self._equipment(), [4], submit=True)
		je = self._draft_je(submit=True)
		self._je_log(je, status="Submitted", sources=[("Card Monthly Card", card1.name)])
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		descriptions = " | ".join(i.description for i in pi.items)
		self.assertIn(card2.name, descriptions)
		self.assertNotIn(card1.name, descriptions)  # held by the submitted JE unit
		self.assertEqual(
			frappe.db.get_value("GL Posting Log", {"posting_doc": pi_name, "status": "Draft"}, "sequence"),
			2,
		)

	def test_multi_rate_template_refused_at_posting(self):
		"""G0 review HIGH-1: a multi-row template is a valid SHAPE but posting
		through it must be REFUSED (flat per-head overrides would multiply VAT),
		never silently corrupted."""
		self._vat_supplier()
		self._example_card()
		head2 = _leaf_under(self.company, "Asset", "Test VAT Input Second", "Tax")
		multi = frappe.get_doc(
			{
				"doctype": "Purchase Taxes and Charges Template",
				"title": "Test multi-rate " + self.token,
				"company": self.company,
				"taxes": [
					{
						"charge_type": "On Net Total",
						"account_head": self.vat_in,
						"rate": 9,
						"description": "A",
						"category": "Total",
						"add_deduct_tax": "Add",
					},
					{
						"charge_type": "On Net Total",
						"account_head": head2,
						"rate": 6,
						"description": "B",
						"category": "Total",
						"add_deduct_tax": "Add",
					},
				],
			}
		).insert(ignore_permissions=True)
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == self.company)
		row.db_set("purchase_tax_template", multi.name, update_modified=False)
		frappe.clear_cache(doctype="Card Settings")
		with self.assertRaises(frappe.ValidationError):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertFalse(
			frappe.get_all("Purchase Invoice", filters={"supplier": self.supplier, "docstatus": 0})
		)

	def test_redated_draft_refused_at_submit(self):
		"""G0 review MEDIUM-4: the posting date must stay inside the unit's
		month — forward-dating a draft would post the value in another period."""
		self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		# back-dating exercises the month guard without tripping ERPNext's own
		# due-date checks (forward-dating is caught by those checks anyway)
		frappe.db.set_value("Purchase Invoice", pi_name, "posting_date", "2026-08-15", update_modified=False)
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		try:
			pi.submit()
			self.fail("a redated draft must be refused at submit")
		except frappe.ValidationError as e:
			self.assertIn("2026-08-15", str(e))

	def test_submit_reverifies_membership_in_other_active_units(self):
		_eq, card = self._example_card()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		# a second active unit grabs the card out-of-band after the build
		je = self._draft_je(submit=True)
		self._je_log(je, status="Submitted", sources=[("Card Monthly Card", card.name)], sequence=2)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Purchase Invoice", pi_name).submit()


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
		# G0 exit gate: the discounted composition must SUBMIT green under the
		# H3 identity (net_total is post-discount == customer_net_amount)
		si.submit()
		self.assertEqual(si.docstatus, 1)

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
		self.assertEqual(
			frappe.db.get_value("GL Posting Log", {"posting_doc": second, "status": "Draft"}, "sequence"), 2
		)
		# G0 exit gate: the supplementary composition must SUBMIT green under H3
		pi2.submit()
		self.assertEqual(frappe.db.get_value("Card Monthly Card", late.name, "purchase_invoice"), second)

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
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		draft = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		try:
			fill.reload()
			fill.cancel()
			self.fail("fill cancel must be blocked while the draft posting holds it")
		except frappe.ValidationError as e:
			self.assertIn(draft, str(e))
