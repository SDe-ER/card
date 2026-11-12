# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-156 (#49, #126; conflict C-10, owner decision O-15) — Payment Entry parity:
once the monthly Sales Invoice and its non-taxable credit note are submitted,
applying a native ERPNext Payment Entry on both brings the customer's
outstanding to zero, and the pair's GL is flat — CARD never touches the PE
flow. Confirms the standard ERPNext pair carries the deductions correctly.
"""

import frappe
from frappe.utils import flt

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.gl import preflight
from card.gl.posting import build_monthly_posting
from card.tests.test_s3_posting import _PostingBase

CREDIT_NOTE = preflight.NON_TAXABLE_DEDUCTION_CREDIT_NOTE


class _ParityBase(_PostingBase):
	def setUp(self):
		super().setUp()
		settings = frappe.get_doc("Card Settings")
		row = next((r for r in settings.company_settings if r.company == self.company), None)
		if row is None:
			row = settings.append("company_settings", {"company": self.company})
		row.non_taxable_customer_deduction = CREDIT_NOTE
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")

	def _submit_main_and_cn(self, customer_rate=1000, deduction=100):
		"""Build and submit the main SI, let the on_submit hook build the CN draft,
		then submit the CN. Returns (si, cn)."""
		eq = self._rented_out(customer=self.customer, customer_rate=customer_rate)
		self._card(
			eq,
			[8, 8],
			adjustments=[
				{
					"adjustment_type_ref": "DieselNT",
					"side": "Customer",
					"description": "nt",
					"amount": deduction,
				}
			],
			submit=True,
		)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		cn_name = frappe.db.get_value(
			"Sales Invoice",
			{"is_return": 1, "customer": self.customer, "docstatus": 0},
			"name",
		)
		self.assertTrue(cn_name, "on_submit of the main SI built the CN draft")
		cn = frappe.get_doc("Sales Invoice", cn_name)
		cn.submit()
		return frappe.get_doc("Sales Invoice", si_name), frappe.get_doc("Sales Invoice", cn_name)


class TestPaymentEntryParity(_ParityBase):
	"""Native ERPNext Payment Entry on the pair clears the customer's outstanding."""

	def test_pair_outstanding_sum_is_zero_after_payment_entry(self):
		si, cn = self._submit_main_and_cn(customer_rate=1000, deduction=100)
		# the main SI's outstanding starts at grand_total
		self.assertGreater(flt(si.outstanding_amount), 0)
		# apply a Payment Entry on the pair: pay (grand_total(main) - |grand_total(cn)|)
		pe = _payment_entry_for_pair(si, cn, company_currency=si.currency)
		pe.submit()
		si.reload()
		cn.reload()
		self.assertEqual(flt(si.outstanding_amount, 2), 0.0)
		self.assertEqual(flt(cn.outstanding_amount, 2), 0.0)

	def test_gl_entries_of_the_pair_plus_payment_sum_to_zero(self):
		"""GL parity: the main SI + the CN + the Payment Entry's GL must net to
		zero for the customer's party ledger."""
		si, cn = self._submit_main_and_cn(customer_rate=1000, deduction=100)
		pe = _payment_entry_for_pair(si, cn, company_currency=si.currency)
		pe.submit()
		# sum of GL entries against the customer's receivable account for this
		# pair + PE
		rows = frappe.get_all(
			"GL Entry",
			filters={
				"voucher_type": ["in", ["Sales Invoice", "Payment Entry"]],
				"voucher_no": ["in", [si.name, cn.name, pe.name]],
				"party": self.customer,
				"is_cancelled": 0,
			},
			fields=["debit", "credit"],
		)
		# net = debits - credits = 0 when the pair is fully reconciled
		net = flt(
			sum(flt(r.debit) - flt(r.credit) for r in rows),
			2,
		)
		self.assertEqual(net, 0.0)

	def test_company_currency_is_stated_and_single_currency(self):
		"""Owner O-17: company currency only, labelled. The pair carries one
		currency (the company's default); the test asserts the label and the
		absence of a second currency on the invoices."""
		si, cn = self._submit_main_and_cn()
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		self.assertEqual(si.currency, company_currency)
		self.assertEqual(cn.currency, company_currency)
		self.assertEqual(flt(si.conversion_rate), 1.0)
		self.assertEqual(flt(cn.conversion_rate), 1.0)
		# GL entries keep the company's party ledger in the company's currency
		rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": ["in", [si.name, cn.name]], "party": self.customer, "is_cancelled": 0},
			fields=["account_currency"],
		)
		currencies = {r.account_currency for r in rows}
		self.assertEqual(currencies, {company_currency}, "one-currency scope (O-17)")


def _payment_entry_for_pair(si, cn, company_currency):
	"""Native ERPNext Payment Entry builder: pay the net amount (main - CN) and
	allocate against both invoices. The test does not import or wrap any CARD
	code for the PE — only standard ERPNext. CARD's policy (FR-156) is that
	the PE flow is untouched."""
	company = si.company
	paid_to = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
		"name",
	)
	if not paid_to:
		# a minimal cash account for the test; the party-posting path is the point
		parent = frappe.db.get_value(
			"Account", {"company": company, "root_type": "Asset", "is_group": 1}, "name"
		)
		paid_to = (
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": "Test Cash FR156",
					"parent_account": parent,
					"company": company,
					"root_type": "Asset",
					"account_type": "Cash",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
	net = flt(si.outstanding_amount, 2) + flt(cn.outstanding_amount, 2)
	pe = frappe.get_doc(
		{
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"company": company,
			"posting_date": si.posting_date,
			"party_type": "Customer",
			"party": si.customer,
			"paid_from": si.debit_to,
			"paid_to": paid_to,
			"paid_from_account_currency": company_currency,
			"paid_to_account_currency": company_currency,
			"paid_amount": net,
			"received_amount": net,
			"source_exchange_rate": 1,
			"target_exchange_rate": 1,
			"references": [
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": si.name,
					"total_amount": flt(si.grand_total, 2),
					"outstanding_amount": flt(si.outstanding_amount, 2),
					"allocated_amount": flt(si.outstanding_amount, 2),
				},
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": cn.name,
					"total_amount": flt(cn.grand_total, 2),
					"outstanding_amount": flt(cn.outstanding_amount, 2),
					# the CN's outstanding is negative; allocated_amount matches so it is settled
					"allocated_amount": flt(cn.outstanding_amount, 2),
				},
			],
		}
	)
	pe.insert(ignore_permissions=True)
	return pe
