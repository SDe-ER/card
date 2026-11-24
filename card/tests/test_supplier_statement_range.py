# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment Supplier Statement for a date range (interim settlement, Owner 2026-11-22).

Proven here, with per-test fixtures that are rolled back (no real company data):
R1 the from/to dates override the months, and the month filters are unchanged without them;
R2 only the day rows inside the range count, priced with the exact hourly rate (425 / 8 = 53.125);
R3 additions/deductions count by their own date; R4 payments are the submitted supplier debits of the
range (draft and cancelled entries never count); R5 the balance (previous_due, period_net, period_paid,
current_due) with the double-count guard for CARD postings and the VAT of CARD purchase invoices;
the printed statement shows the balance lines and the payments; R6 the exact rate the card form uses."""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from card.card.doctype.card_monthly_card.card_monthly_card import get_standard_month_hours
from card.card.report.equipment_supplier_statement.equipment_supplier_statement import (
	execute as supplier_statement,
)
from card.card.report.equipment_supplier_statement.statement_pdf import build_html
from card.card_value import exact_hourly_rate
from card.gl.posting import build_monthly_posting
from card.tests.cancel_reason import with_reason
from card.tests.test_cash_disbursement_db import _cash_account
from card.tests.test_s3_posting import _PostingBase

RATE = 425  # per day over 8 daily hours = 53.125 per hour (the equipment shows 53.13)
HOURS = [8, 8, 8, 8, 5, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8]  # days 1..20; days 1-5 = 37 h


class TestSupplierStatementRange(_PostingBase):
	def _eq(self):
		return self._equipment(rate=RATE, daily_hours=8)

	def _run(self, **extra):
		filters = {
			"company": self.company,
			"statement_type": "مورد",
			"supplier": self.supplier,
			"from_month": 9,
			"from_year": 2026,
			"include_draft": 1,
		}
		filters.update(extra)
		columns, rows, message, _chart, summary, _skip = supplier_statement(filters)
		return frappe._dict(
			columns=columns,
			rows=rows,
			message=message,
			summary=summary,
			by_key={s["key"]: s["value"] for s in summary if s.get("key")},
			cards={r["card"]: r for r in rows if r.get("card")},
			total=next((r for r in rows if r.get("row_id") == "TOTAL"), {}),
		)

	def _payment(self, amount, date, submit=True, credit=False, equipment=None, project=None):
		"""A journal entry on the supplier (a payment/advance debit, or a non-CARD credit)."""
		payable = frappe.get_cached_value("Company", self.company, "default_payable_account") or (
			frappe.db.get_value(
				"Account", {"company": self.company, "account_type": "Payable", "is_group": 0}, "name"
			)
		)
		cc = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		je = frappe.new_doc("Journal Entry")
		je.company = self.company
		je.posting_date = date
		je.user_remark = "TEST supplier entry " + self.token
		side = "credit_in_account_currency" if credit else "debit_in_account_currency"
		other = "debit_in_account_currency" if credit else "credit_in_account_currency"
		je.append(
			"accounts",
			{
				"account": payable,
				"party_type": "Supplier",
				"party": self.supplier,
				side: amount,
				"is_advance": "No" if credit else "Yes",
				"cost_center": cc,
				# FR-176: the Card Equipment accounting dimension and the project on the supplier line
				"card_equipment": equipment,
				"project": project,
			},
		)
		je.append("accounts", {"account": _cash_account(self.company), other: amount, "cost_center": cc})
		je.insert(ignore_permissions=True)
		if submit:
			je.submit()
		return je

	# ---- R2: exact rate, range splitting a card ----
	def test_partial_range_prices_days_with_the_exact_hourly_rate(self):
		card = self._card(self._eq(), HOURS)
		r = self._run(from_date="2026-09-01", to_date="2026-09-05")
		row = r.cards[card.name]
		self.assertEqual(flt(row["hours"]), 37)
		self.assertEqual(row["working_days"], 5)
		self.assertEqual(flt(row["amount"], 2), flt(37 * RATE / 8, 2))
		self.assertNotEqual(flt(row["amount"], 2), flt(37 * 53.13, 2))  # never the rounded rate
		self.assertEqual(str(row["first_date"]), "2026-09-01")
		self.assertEqual(str(row["last_date"]), "2026-09-05")
		# the rest of the card is in the next range; together they make the card
		rest = self._run(from_date="2026-09-06", to_date="2026-09-30").cards[card.name]
		self.assertAlmostEqual(flt(row["amount"]) + flt(rest["amount"]), flt(card.amount), delta=0.011)

	def test_range_holding_the_whole_card_prints_the_card_amount(self):
		card = self._card(self._eq(), HOURS)
		row = self._run(from_date="2026-08-25", to_date="2026-10-05").cards[card.name]
		self.assertEqual(flt(row["amount"], 2), flt(card.amount, 2))
		self.assertEqual(flt(card.amount, 2), flt(sum(HOURS) * RATE / 8, 2))

	def test_card_without_days_in_the_range_is_not_listed(self):
		card = self._card(self._eq(), [8, 8])
		self.assertNotIn(card.name, self._run(from_date="2026-09-10", to_date="2026-09-15").cards)

	# ---- R3: additions / deductions by date ----
	def test_deductions_count_by_their_own_date(self):
		card = self._card(
			self._eq(),
			HOURS,
			adjustments=[
				{
					"adjustment_date": "2026-09-05",
					"adjustment_type_ref": "Penalty",
					"description": "diesel 1",
					"amount": 378,
				},
				{
					"adjustment_date": "2026-09-08",
					"adjustment_type_ref": "Penalty",
					"description": "diesel 2",
					"amount": 100,
				},
			],
		)
		first = self._run(from_date="2026-09-01", to_date="2026-09-05").cards[card.name]
		self.assertEqual(flt(first["deductions"]), 378)
		self.assertEqual(flt(first["net"], 2), flt(flt(37 * RATE / 8, 2) - 378, 2))
		later = self._run(from_date="2026-09-06", to_date="2026-09-30").cards[card.name]
		self.assertEqual(flt(later["deductions"]), 100)

	# ---- drafts and cancelled cards ----
	def test_drafts_only_with_include_draft_and_cancelled_never(self):
		draft = self._card(self._eq(), [8, 8])
		cancelled = self._card(self._eq(), [8, 8], submit=True)
		with_reason(cancelled).cancel()
		with_drafts = self._run(from_date="2026-09-01", to_date="2026-09-30")
		self.assertIn(draft.name, with_drafts.cards)
		self.assertNotIn(cancelled.name, with_drafts.cards)
		without = self._run(from_date="2026-09-01", to_date="2026-09-30", include_draft=0)
		self.assertNotIn(draft.name, without.cards)
		self.assertNotIn(cancelled.name, without.cards)

	# ---- R1: the month filters are unchanged without dates ----
	def test_month_filters_without_dates_are_unchanged(self):
		card = self._card(
			self._eq(),
			HOURS,
			adjustments=[
				{
					"adjustment_date": "2026-09-05",
					"adjustment_type_ref": "Penalty",
					"description": "d",
					"amount": 378,
				}
			],
		)
		r = self._run()
		row = r.cards[card.name]
		self.assertEqual(flt(row["amount"], 2), flt(card.amount, 2))
		self.assertEqual(flt(row["deductions"]), 378)
		self.assertIn("net_cards", r.by_key)
		self.assertNotIn("period_net", r.by_key)
		self.assertNotIn("current_due", r.by_key)
		self.assertFalse([x for x in r.rows if x.get("payment")])
		# one date alone is refused, never silently replaced by the months
		with self.assertRaises(frappe.ValidationError):
			self._run(from_date="2026-09-01")

	def test_end_before_start_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(from_date="2026-09-10", to_date="2026-09-01")

	# ---- R4 / R5: payments and the running balance (the R7 shape with fixtures) ----
	# ---- #295 (Owner decision 2026-11-24, option A): no figure derived from card amounts without the money level ----
	MONEY_GATE = "card.card.report.equipment_supplier_statement.equipment_supplier_statement.role_reads_money"
	CARD_MONEY = ("rate", "hourly_rate", "amount", "additions", "deductions", "net")

	def test_range_statement_without_money_level_keeps_only_the_accounting_lines(self):
		self._card(self._eq(), HOURS)
		paid = self._payment(1000, "2026-09-16")
		with patch(self.MONEY_GATE, return_value=False):
			r = self._run(from_date="2026-09-01", to_date="2026-09-30")
		# the net work, the balance carried from before the period and the current due add card work: gone
		for key in ("period_net", "previous_due", "current_due", "net_cards", "not_invoiced"):
			self.assertNotIn(key, r.by_key)
		self.assertEqual(r.by_key["period_paid"], 1000)  # an accounting line stays
		work_rows = [x for x in r.rows if not x.get("payment")]
		self.assertTrue(work_rows)
		for key in self.CARD_MONEY:
			self.assertFalse([x for x in work_rows if key in x], key)
		payments = [x for x in r.rows if x.get("payment") and x.get("parent_row")]
		self.assertEqual(
			[(p["voucher_no"], flt(p["payment_amount"])) for p in payments], [(paid.name, 1000.0)]
		)
		fieldnames = [c["fieldname"] for c in r.columns]
		self.assertIn("payment_amount", fieldnames)  # the payment amounts have their own column
		for key in self.CARD_MONEY:
			self.assertNotIn(key, fieldnames)
		# the A4 PDF uses the hours layout (no empty money cells) and still lists the payment with its note
		filters = {
			"company": self.company,
			"statement_type": "مورد",
			"supplier": self.supplier,
			"from_month": 9,
			"from_year": 2026,
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"include_draft": 1,
		}
		html = build_html(filters, r.columns, r.rows, r.message, r.summary)
		self.assertIn(paid.name, html)
		self.assertIn("Payments are submitted accounting entries only", html)
		self.assertNotIn("Supplier signature", html)

	def test_month_statement_without_money_level_has_no_card_money(self):
		self._card(self._eq(), HOURS)
		with patch(self.MONEY_GATE, return_value=False):
			r = self._run()
		self.assertNotIn("net_cards", r.by_key)
		self.assertNotIn("not_invoiced", r.by_key)
		self.assertIn("opening", r.by_key)  # GL items keep their own gate (can_view_ledger)
		fieldnames = [c["fieldname"] for c in r.columns]
		for key in self.CARD_MONEY:
			self.assertNotIn(key, fieldnames)
			self.assertFalse([x for x in r.rows if key in x], key)

	def test_suppliers_summary_without_money_level_has_no_card_money(self):
		from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import (
			execute as suppliers_summary,
		)

		self._card(self._eq(), HOURS, submit=True)
		filters = {"company": self.company, "from_month": 9, "from_year": 2026}
		target = "card.card.report.equipment_suppliers_summary.equipment_suppliers_summary.role_reads_money"
		with patch(target, return_value=False):
			columns, rows, _m, _c, summary, *_ = suppliers_summary(filters)
		fieldnames = [c["fieldname"] for c in columns]
		for key in ("net", "diff"):
			self.assertNotIn(key, fieldnames)
			self.assertFalse([x for x in rows if key in x], key)
		labels = {t.get("label") for t in summary}
		for label in ("Net cards", "Not invoiced through Card"):
			self.assertNotIn(frappe._(label), labels)
		self.assertTrue([x for x in rows if x.get("supplier") == self.supplier])  # the row itself stays

	def test_every_money_report_role_reads_the_money_level(self):
		"""Today every role of these reports reads permlevel 1 of Card Monthly Card, so their reports are unchanged
		(checked on the DocPerms of the shipped Report roles; a site Custom Role is not covered. Administrator passes role_reads_money whatever they say)."""
		level_1 = {
			p.role for p in frappe.get_meta("Card Monthly Card").permissions if p.permlevel == 1 and p.read
		}
		for report in (
			"Equipment Supplier Statement",
			"Equipment Suppliers Summary",
			"Equipment Customers Summary",
			"Equipment Customer Statement",
		):
			roles = {r.role for r in frappe.get_doc("Report", report).roles}
			with self.subTest(report=report):
				self.assertTrue(roles)
				self.assertLessEqual(roles, level_1)

	def test_payments_and_balance_across_ranges(self):
		cards = [
			self._card(
				self._eq(),
				HOURS,
				adjustments=[
					{
						"adjustment_date": "2026-09-05",
						"adjustment_type_ref": "Penalty",
						"description": "d",
						"amount": 378,
					}
				],
			)
		]
		cards.append(self._card(self._eq(), HOURS))
		paid = self._payment(1587.63, "2026-09-16")
		self._payment(999, "2026-09-10", submit=False)  # a draft entry never counts
		cancelled = self._payment(500, "2026-09-12")
		cancelled.cancel()

		first = self._run(from_date="2026-09-01", to_date="2026-09-05")
		net_1_5 = flt(first.by_key["period_net"], 2)
		self.assertEqual(net_1_5, flt(2 * flt(37 * RATE / 8, 2) - 378, 2))
		self.assertEqual(first.by_key["previous_due"], 0)
		self.assertEqual(first.by_key["period_paid"], 0)  # the payment is dated after the range
		self.assertEqual(first.by_key["current_due"], net_1_5)

		month = self._run(from_date="2026-09-01", to_date="2026-09-30")
		net_month = flt(sum(flt(c.net_amount) for c in cards), 2)
		self.assertEqual(month.by_key["period_net"], net_month)
		self.assertEqual(month.by_key["period_paid"], 1587.63)
		self.assertEqual(month.by_key["current_due"], flt(net_month - 1587.63, 2))
		payments = [x for x in month.rows if x.get("payment") and x.get("parent_row")]
		self.assertEqual([p["voucher_no"] for p in payments], [paid.name])
		self.assertEqual(str(payments[0]["posting_date"]), "2026-09-16")
		self.assertIn("draft journal entries are not counted", month.message)

		first_16 = self._run(from_date="2026-09-01", to_date="2026-09-16").by_key["period_net"]
		late = self._run(from_date="2026-09-17", to_date="2026-09-30")
		self.assertEqual(late.by_key["previous_due"], flt(first_16 - 1587.63, 2))
		self.assertEqual(
			late.by_key["current_due"], flt(late.by_key["previous_due"] + late.by_key["period_net"], 2)
		)
		# the balance runs: the last range ends where the whole month ends
		# (each of the two cards split at 16/17 may round by one halala)
		self.assertAlmostEqual(late.by_key["current_due"], month.by_key["current_due"], delta=0.021)

	def test_equipment_type_filter_keeps_payments_for_the_whole_supplier(self):
		eq = self._eq()
		self._card(eq, HOURS)
		self._payment(100, "2026-09-03")
		r = self._run(from_date="2026-09-01", to_date="2026-09-05", equipment_type=eq.equipment_type)
		self.assertEqual(r.by_key["period_paid"], 100)
		self.assertIn("payments, VAT and other credits are for the whole supplier", r.message)

	# ---- R8 / FR-176: payments linked to an equipment ----
	def test_equipment_statement_counts_only_its_own_payments(self):
		a, b = self._eq(), self._eq()
		self._card(a, HOURS)
		self._card(b, HOURS)
		linked = self._payment(300, "2026-09-03", equipment=a.name)
		self._payment(200, "2026-09-04", equipment=b.name)  # another equipment: neither counted nor warned
		self._payment(100, "2026-09-02")  # no equipment: warned, never deducted
		r = self._run(from_date="2026-09-01", to_date="2026-09-05", equipment=a.name)
		net = flt(37 * RATE / 8, 2)
		self.assertEqual(r.by_key["period_net"], net)
		self.assertEqual(r.by_key["period_paid"], 300)
		self.assertEqual(r.by_key["unallocated_paid"], 100)
		self.assertEqual(r.by_key["current_due"], flt(net - 300, 2))
		payments = [x for x in r.rows if x.get("payment") and x.get("parent_row")]
		self.assertEqual([p["voucher_no"] for p in payments], [linked.name])
		self.assertIn("entries without one are shown apart and not counted", r.message)
		# the other equipment: its own payment only, the same untagged warning
		other = self._run(from_date="2026-09-01", to_date="2026-09-05", equipment=b.name)
		self.assertEqual(other.by_key["period_paid"], 200)
		self.assertEqual(other.by_key["unallocated_paid"], 100)
		# no equipment filter: every supplier payment, as before, and no warning line
		whole = self._run(from_date="2026-09-01", to_date="2026-09-05")
		self.assertEqual(whole.by_key["period_paid"], 600)
		self.assertNotIn("unallocated_paid", whole.by_key)

	def test_equipment_previous_due_uses_its_own_earlier_payments(self):
		a, b = self._eq(), self._eq()
		self._card(a, HOURS)
		self._card(b, HOURS)
		self._payment(500, "2026-09-10", equipment=a.name)
		self._payment(700, "2026-09-11", equipment=b.name)
		self._payment(50, "2026-09-12")
		late = self._run(from_date="2026-09-17", to_date="2026-09-30", equipment=a.name)
		first_16 = self._run(from_date="2026-09-01", to_date="2026-09-16", equipment=a.name)
		self.assertEqual(late.by_key["previous_due"], flt(first_16.by_key["period_net"] - 500, 2))
		self.assertEqual(late.by_key["period_paid"], 0)
		self.assertEqual(late.by_key["unallocated_paid"], 50)  # untagged up to the end date

	def test_draft_payment_with_equipment_is_never_counted(self):
		a = self._eq()
		self._card(a, HOURS)
		self._payment(400, "2026-09-03", submit=False, equipment=a.name)
		r = self._run(from_date="2026-09-01", to_date="2026-09-05", equipment=a.name)
		self.assertEqual(r.by_key["period_paid"], 0)
		self.assertNotIn("unallocated_paid", r.by_key)

	def test_project_filter_uses_the_payment_project(self):
		a = self._eq()
		self._card(a, HOURS)
		self._payment(120, "2026-09-03", project=self.project)
		self._payment(80, "2026-09-04")
		r = self._run(from_date="2026-09-01", to_date="2026-09-05", project=self.project)
		self.assertEqual(r.by_key["period_paid"], 120)
		self.assertEqual(r.by_key["unallocated_paid"], 80)
		self.assertIn("Payments not allocated to a project (not deducted)", [s["label"] for s in r.summary])

	def test_owner_scenario_payment_reissued_with_the_equipment(self):
		# R7 shape: three equipment of one supplier; the 1,587.63 payment re-issued with the third equipment
		eqs = [self._eq(), self._eq(), self._eq()]
		for eq in eqs:
			self._card(eq, HOURS)
		self._payment(1587.63, "2026-09-16", equipment=eqs[2].name)
		for eq, paid in zip(eqs, (0, 0, 1587.63), strict=True):
			r = self._run(from_date="2026-09-01", to_date="2026-09-30", equipment=eq.name)
			self.assertEqual(r.by_key["period_paid"], paid)
			self.assertNotIn("unallocated_paid", r.by_key)
			self.assertEqual(r.by_key["current_due"], flt(r.by_key["period_net"] - paid, 2))
		whole = self._run(from_date="2026-09-01", to_date="2026-09-30")
		self.assertEqual(whole.by_key["period_paid"], 1587.63)

	def test_equipment_vat_is_allocated_by_the_invoice_item_share(self):
		self._vat_supplier()
		a, b = self._eq(), self._eq()
		card_a = self._card(a, [8, 8], submit=True)
		self._card(b, [8], submit=True)
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-BILL-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		vat = flt(pi.base_taxes_and_charges_added) - flt(pi.base_taxes_and_charges_deducted)
		total = sum(flt(i.base_net_amount) for i in pi.items)
		own = sum(flt(i.base_net_amount) for i in pi.items if i.get("card_equipment") == a.name)
		self.assertTrue(own and own < total)  # premise: the invoice lines carry the equipment
		r = self._run(from_date="2026-09-01", to_date=str(pi.posting_date), equipment=a.name)
		self.assertEqual(r.by_key["period_vat"], flt(vat * own / total, 2))
		self.assertEqual(r.by_key["period_net"], flt(card_a.net_amount, 2))

	def test_equipment_and_project_filters_need_both_tags(self):
		a, b = self._eq(), self._eq()
		self._card(a, HOURS)
		self._card(b, HOURS)
		self._payment(
			3000, "2026-09-03", project=self.project
		)  # project only: never deducted from one equipment
		self._payment(250, "2026-09-03", equipment=a.name, project=self.project)
		for eq, paid in ((a, 250), (b, 0)):
			r = self._run(
				from_date="2026-09-01", to_date="2026-09-05", equipment=eq.name, project=self.project
			)
			self.assertEqual(r.by_key["period_paid"], paid)
			self.assertEqual(r.by_key["unallocated_paid"], 3000)
			labels = [s["label"] for s in r.summary]
			self.assertIn("Payments without the selected equipment and project (not deducted)", labels)
		# the project statement deducts both
		whole_project = self._run(from_date="2026-09-01", to_date="2026-09-05", project=self.project)
		self.assertEqual(whole_project.by_key["period_paid"], 3250)

	def test_untagged_other_credit_is_information_only(self):
		a = self._eq()
		self._card(a, HOURS)
		self._payment(90, "2026-09-03", credit=True)
		self._payment(40, "2026-09-03", credit=True, equipment=a.name)
		r = self._run(from_date="2026-09-01", to_date="2026-09-05", equipment=a.name)
		self.assertEqual(r.by_key["period_other"], 40)
		self.assertEqual(r.by_key["unallocated_other"], 90)
		self.assertEqual(r.by_key["current_due"], flt(r.by_key["period_net"] + 40, 2))

	def test_printed_statement_shows_the_unallocated_line(self):
		a = self._eq()
		self._card(a, HOURS)
		self._payment(100, "2026-09-02")
		filters = frappe._dict(
			company=self.company,
			statement_type="مورد",
			supplier=self.supplier,
			from_month=9,
			from_year=2026,
			from_date="2026-09-01",
			to_date="2026-09-05",
			equipment=a.name,
			include_draft=1,
		)
		r = self._run(from_date="2026-09-01", to_date="2026-09-05", equipment=a.name)
		html = build_html(filters, r.columns, r.rows, r.message, r.summary)
		self.assertIn("Payments not allocated to an equipment (not deducted)", html)
		template = frappe.read_file(
			frappe.get_app_path(
				"card", "card", "report", "equipment_supplier_statement", "equipment_supplier_statement.html"
			)
		)
		self.assertIn("unallocated_paid", template)

	# ---- R5: double-count guard and VAT of CARD purchase invoices ----
	def test_card_invoice_credit_is_not_counted_twice_and_its_vat_is_added(self):
		self._vat_supplier()
		card = self._card(self._eq(), [8, 8], submit=True)
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-BILL-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		self.assertTrue(flt(pi.base_taxes_and_charges_added))  # premise: the CARD invoice carries VAT
		other = self._payment(250, pi.posting_date, credit=True)  # a credit CARD did not post

		r = self._run(from_date="2026-09-01", to_date=str(pi.posting_date))
		vat = flt(pi.base_taxes_and_charges_added - pi.base_taxes_and_charges_deducted, 2)
		self.assertEqual(r.by_key["period_net"], flt(card.net_amount, 2))
		self.assertEqual(r.by_key["period_vat"], vat)
		self.assertEqual(r.by_key["period_other"], 250)
		# the invoice's own credit (net + VAT) is not added on top of the card work
		self.assertEqual(r.by_key["current_due"], flt(flt(card.net_amount, 2) + vat + 250, 2))
		self.assertTrue(other.name)

	# ---- print ----
	def test_printed_statement_shows_the_balance_and_the_payments(self):
		self._card(self._eq(), HOURS)
		je = self._payment(300, "2026-09-03")
		filters = frappe._dict(
			company=self.company,
			statement_type="مورد",
			supplier=self.supplier,
			from_month=9,
			from_year=2026,
			from_date="2026-09-01",
			to_date="2026-09-05",
			include_draft=1,
		)
		r = self._run(from_date="2026-09-01", to_date="2026-09-05")
		html = build_html(filters, r.columns, r.rows, r.message, r.summary)
		for label in (
			"Balance carried from before the period",
			"Net work for the period",
			"Payments in the period (submitted entries only)",
			"Current due to the supplier",
			"Payment date",
			je.name,
		):
			self.assertIn(label, html)
		# zero VAT / other credits are hidden; the period prints its own dates; no ERPNext wording
		self.assertNotIn("VAT on CARD purchase invoices", html)
		self.assertNotIn("Other supplier credits", html)
		self.assertIn(frappe.utils.formatdate("2026-09-05"), html)
		self.assertNotIn("ERPNext", html)
		# the payment row is not repeated in the work table
		self.assertEqual(html.count(je.name), 1)

	def test_browser_template_reads_the_range_keys(self):
		template = frappe.read_file(
			frappe.get_app_path(
				"card", "card", "report", "equipment_supplier_statement", "equipment_supplier_statement.html"
			)
		)
		for key in ("previous_due", "period_net", "period_paid", "current_due", "filters.from_date"):
			self.assertIn(key, template)

	# ---- R6: the exact rate of the card form ----
	def test_exact_hourly_rate_matches_the_card_pricing(self):
		card = frappe.new_doc("Card Monthly Card")
		card.equipment = "TEST"
		self.assertEqual(exact_hourly_rate("باليوم", 425, 8), 53.125)
		for basis, rate, dh in (("باليوم", 425, 8), ("بالساعة", 53.125, 0), ("بالشهر", 13000, 0)):
			self.assertEqual(exact_hourly_rate(basis, rate, dh), card._hourly_for(basis, rate, dh, False))
		self.assertEqual(exact_hourly_rate("باليوم", 425, 0), 0)
		self.assertEqual(
			get_standard_month_hours(),
			flt(frappe.db.get_single_value("Card Settings", "standard_month_hours")) or 260,
		)

	def test_draft_card_amount_uses_the_exact_rate(self):
		# EOMC-2026-11-0339 shape: the server never prices with the rounded 53.13
		card = self._card(self._eq(), [8] * 14 + [6])  # 118 h
		self.assertEqual(flt(card.amount, 2), flt(118 * RATE / 8, 2))
		self.assertNotEqual(flt(card.amount, 2), flt(118 * 53.13, 2))

	# ---- review fixes ----
	def test_submitted_card_keeps_its_submitted_hourly_rate(self):
		eq = self._equipment(rate_type="بالشهر", rate=26000)
		frappe.db.set_single_value("Card Settings", "standard_month_hours", 260)
		frappe.clear_cache(doctype="Card Settings")
		card = self._card(eq, HOURS, submit=True)
		self.assertEqual(flt(card.hourly_rate_used), 100.0)
		frappe.db.set_single_value("Card Settings", "standard_month_hours", 200)  # changed after submit
		frappe.clear_cache(doctype="Card Settings")
		row = self._run(from_date="2026-09-01", to_date="2026-09-05").cards[card.name]
		self.assertEqual(flt(row["amount"], 2), 37 * 100.0)

	def test_previous_due_counts_cards_that_ended_before_the_range(self):
		eq = self._eq()
		august = frappe.new_doc("Card Monthly Card")
		august.update(
			{"equipment": eq.name, "project": self.project, "shift": "نهاري", "month": "08", "year": 2026}
		)
		from card.tests.test_controllers import _days

		for row in _days([8, 8, 8], month=8):
			august.append("days", row)
		august.append(
			"adjustments",
			{
				"adjustment_date": "2026-08-02",
				"adjustment_type_ref": "Penalty",
				"description": "d",
				"amount": 50,
			},
		)
		august.insert(ignore_permissions=True)
		august.reload()
		self._card(eq, HOURS)
		r = self._run(from_date="2026-09-01", to_date="2026-09-05")
		self.assertEqual(r.by_key["previous_due"], flt(august.net_amount, 2))
		self.assertEqual(r.by_key["current_due"], flt(flt(august.net_amount, 2) + r.by_key["period_net"], 2))

	# ---- FR-176 follow-up: the month statement applies the same equipment rules ----
	def test_month_statement_equipment_filter_counts_only_its_own_payments(self):
		a, b = self._eq(), self._eq()
		self._card(a, HOURS)
		self._card(b, HOURS)
		self._payment(300, "2026-09-03", equipment=a.name)  # linked
		self._payment(200, "2026-09-04", equipment=b.name)  # another equipment
		self._payment(100, "2026-09-02")  # unlinked: warned, never deducted
		self._payment(40, "2026-08-20", equipment=a.name)  # before the month: in the opening
		r = self._run(equipment=a.name)
		self.assertEqual(r.by_key["paid"], 300)
		self.assertEqual(r.by_key["opening"], -40)
		self.assertEqual(r.by_key["unallocated_paid"], 100)
		self.assertEqual(r.by_key["closing"], flt(-40 + r.by_key["accrued"] - 300, 2))
		self.assertIn("entries without one are shown apart and not counted", r.message)
		self.assertIn("net_cards", r.by_key)  # still the month statement
		self.assertNotIn("period_net", r.by_key)

	def test_month_statement_mixed_project_and_equipment_tags(self):
		a = self._eq()
		self._card(a, HOURS)
		self._payment(70, "2026-09-03", equipment=a.name, project=self.project)
		self._payment(30, "2026-09-03", project=self.project)  # project only
		r = self._run(equipment=a.name, project=self.project)
		self.assertEqual(r.by_key["paid"], 70)
		self.assertEqual(r.by_key["unallocated_paid"], 30)
		self.assertEqual(self._run(project=self.project).by_key["paid"], 100)

	def test_month_statement_without_equipment_filter_is_unchanged(self):
		a = self._eq()
		self._card(a, HOURS)
		self._payment(300, "2026-09-03", equipment=a.name)
		self._payment(100, "2026-09-02")
		self._payment(5, "2026-09-02", credit=True)
		r = self._run()
		self.assertEqual(r.by_key["paid"], 400)
		self.assertEqual(r.by_key["accrued"], 5)
		self.assertNotIn("unallocated_paid", r.by_key)
		self.assertNotIn("entries without one are shown apart", r.message)

	def test_month_statement_card_invoice_credit_counts_by_line_share(self):
		self._vat_supplier()
		a, b = self._eq(), self._eq()
		self._card(a, [8, 8], submit=True)
		self._card(b, [8], submit=True)
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-BILL-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		month = str(pi.posting_date)[5:7]
		year = int(str(pi.posting_date)[:4])
		total = sum(flt(i.base_net_amount) for i in pi.items)
		own = sum(flt(i.base_net_amount) for i in pi.items if i.get("card_equipment") == a.name)
		r = self._run(equipment=a.name, from_month=9, to_month=int(month), to_year=year)
		credit = frappe.db.get_value(
			"GL Entry", {"voucher_no": pi.name, "party": self.supplier, "is_cancelled": 0}, "credit"
		)
		self.assertEqual(r.by_key["accrued"], flt(flt(credit) * own / total, 2))
		self.assertNotIn("unallocated_other", r.by_key)

	def test_month_statement_linked_accrual_journal_counts_for_its_cards_equipment(self):
		a, b = self._eq(), self._eq()
		card_a = self._card(a, [8, 8], submit=True)
		card_b = self._card(b, [8], submit=True)
		je = self._payment(1000, "2026-09-30", credit=True)  # the accrual: no equipment on the party row
		log = frappe.get_doc(
			{
				"doctype": "GL Posting Log",
				"company": self.company,
				"party_type": "Supplier",
				"party": self.supplier,
				"month": "09",
				"year": 2026,
				"posting_type": "Journal Entry",
				"sequence": 1,
				"status": "Draft",
				"posting_doctype": "Journal Entry",
				"posting_doc": je.name,
			}
		)
		for card in (card_a, card_b):
			log.append(
				"sources", {"source_doctype": "Card Monthly Card", "source_name": card.name, "amount": 0}
			)
		log.flags.card_gl_build = (
			True  # an out-of-band unit, inserted as the builder would (test_s3_posting._je_log)
		)
		log.insert(ignore_permissions=True)
		log.db_set("status", "Submitted", update_modified=False)  # the linked accrual is submitted
		share = flt(card_a.net_amount) / (flt(card_a.net_amount) + flt(card_b.net_amount))
		r = self._run(equipment=a.name)
		self.assertEqual(r.by_key["accrued"], flt(1000 * share, 2))
		self.assertNotIn("unallocated_other", r.by_key)  # the accrual belongs to the two cards' equipment
