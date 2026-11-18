# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2: reconciliation-safe cancellation with real ERPNext documents (no hand-built ledger rows).

Flow per scenario: a submitted rental Purchase Invoice for the Supplier (built by CARD's own monthly posting), a
cash-disbursement Journal Entry (submitted by the service identity), ERPNext's standard Payment Reconciliation, and
ERPNext's standard Unreconcile Payment. The cancellation gate is exercised against the ledger ERPNext writes.
"""

import frappe
from frappe.utils import flt

from card.cash_disbursement import (
	SERVICE_ROLE,
	approve_cash_disbursement,
	execute_posting,
	queue_posting,
	request_cancellation,
	request_cash_disbursement,
)
from card.gl.posting import build_monthly_posting
from card.tests.cash_service_perms import copy_standard_perms
from card.tests.test_cash_disbursement_db import _cash_account
from card.tests.test_s3_posting import _PostingBase

DOCTYPE = "Card Cash Disbursement"


class TestCashReconciliationERPNext(_PostingBase):
	def setUp(self):
		super().setUp()
		self._vat_supplier()
		self.cash = _cash_account(self.company)
		self.manager = self._user("Card Manager")
		self.service = self._service_user()
		self.payable = frappe.get_cached_value("Company", self.company, "default_payable_account")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _user(self, role):
		email = "rec-%s-%s@example.com" % (role.lower().replace(" ", "-"), frappe.generate_hash(length=6))
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Test",
					"send_welcome_email": 0,
					"user_type": "System User",
					"roles": [{"role": role}],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _service_user(self):
		"""The dedicated accounting identity, created in the test site only (as in test_cash_disbursement_post)."""
		if not frappe.db.exists("Role", SERVICE_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": SERVICE_ROLE}).insert(ignore_permissions=True)
		grants = {
			"Journal Entry": {"read": 1, "write": 1, "create": 1, "submit": 1, "cancel": 1},
			"Account": {"read": 1},
			"Supplier": {"read": 1},
			"Company": {"read": 1},
			"Project": {"read": 1},
		}
		for doctype, rights in grants.items():
			copy_standard_perms(doctype)
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": doctype,
					"role": SERVICE_ROLE,
					"permlevel": 0,
					**rights,
				}
			).insert(ignore_permissions=True)
			frappe.clear_cache(doctype=doctype)
		user = self._user(SERVICE_ROLE)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": self.company,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		return user

	def _rental_invoice(self):
		"""The Supplier's rental Purchase Invoice for September 2026, built and submitted by CARD's posting."""
		eq = self._equipment()
		self._card(eq, [5], submit=True)
		name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", name)
		# VAT input needs the supplier's own invoice number and date before submission (CARD rule)
		pi.bill_no = "SUP-BILL-" + name
		pi.bill_date = "2026-09-30"
		pi.save()
		pi.submit()
		return frappe.get_doc("Purchase Invoice", name)

	def _cash_payment(self, amount):
		"""A cash payment of ``amount`` posted through the real executor path; returns (payment, journal entry)."""
		eq = self._equipment()
		card = self._card(
			eq,
			[5],
			adjustments=[
				{
					"adjustment_date": "2026-09-01",
					"is_cash_disbursement": 1,
					"cash_account": self.cash,
					"adjustment_type": "خصم",
					"description": "Diesel paid on behalf of the supplier",
					"amount": amount,
					"side": "Supplier",
				}
			],
		)
		row = next(r for r in card.adjustments if r.is_cash_disbursement)
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		queue_posting(name)
		frappe.set_user(self.service)
		entry = execute_posting(name)
		frappe.set_user("Administrator")
		return name, entry

	def _reconcile(self, pi, entry):
		"""ERPNext's standard Payment Reconciliation between the Journal Entry payment and the invoice."""
		pr = frappe.new_doc("Payment Reconciliation")
		pr.company = self.company
		pr.party_type = "Supplier"
		pr.party = self.supplier
		pr.receivable_payable_account = self.payable
		pr.get_unreconciled_entries()
		payments = [p.as_dict() for p in pr.get("payments") if p.reference_name == entry]
		invoices = [i.as_dict() for i in pr.get("invoices") if i.invoice_number == pi.name]
		self.assertEqual(len(payments), 1, "the Journal Entry is not offered for reconciliation")
		self.assertEqual(len(invoices), 1, "the Purchase Invoice is not offered for reconciliation")
		pr.allocate_entries(frappe._dict({"payments": payments, "invoices": invoices}))
		pr.reconcile()

	def _unreconcile(self, entry):
		"""ERPNext's standard Unreconcile Payment for every allocation of the Journal Entry."""
		ur = frappe.new_doc("Unreconcile Payment")
		ur.company = self.company
		ur.voucher_type = "Journal Entry"
		ur.voucher_no = entry
		ur.add_references()
		ur.save().submit()

	def _supplier_ledger_balance(self):
		"""Net of the Supplier's live Payment Ledger Entries (delinked = 0)."""
		return flt(
			frappe.db.sql(
				"select coalesce(sum(amount), 0) from `tabPayment Ledger Entry` "
				"where party = %s and company = %s and delinked = 0",
				(self.supplier, self.company),
			)[0][0]
		)

	def _cancel_blocked(self, name, entry):
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_cancellation(name, "Reconciled payment")
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_unreconciled_entry_cancels_after_an_authorized_request(self):
		pi = self._rental_invoice()
		before = self._supplier_ledger_balance()
		name, entry = self._cash_payment(100)
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong receipt; not reconciled")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), pi.grand_total
		)
		self.assertEqual(self._supplier_ledger_balance(), before)

	def test_partially_reconciled_entry_cannot_be_cancelled(self):
		"""The payment is larger than the invoice: the invoice is paid, the payment keeps an unallocated remainder."""
		pi = self._rental_invoice()
		name, entry = self._cash_payment(flt(pi.grand_total) + 100)
		self._reconcile(pi, entry)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 0)
		self._cancel_blocked(name, entry)

	def test_fully_reconciled_entry_cannot_be_cancelled(self):
		"""The payment is smaller than the invoice: the whole payment is allocated, the invoice keeps its balance."""
		pi = self._rental_invoice()
		amount = flt(pi.grand_total / 2, 2)
		name, entry = self._cash_payment(amount)
		self._reconcile(pi, entry)
		self.assertEqual(
			flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 2),
			flt(pi.grand_total - amount, 2),
		)
		self._cancel_blocked(name, entry)

	def test_unreconciled_through_erpnext_then_cancelled_restores_the_ledger(self):
		"""Reconcile, refuse the cancel, unreconcile with ERPNext's workflow, then cancel: the invoice and the Supplier
		ledger return to their state before the payment, and the cancelled payment cannot be posted again."""
		pi = self._rental_invoice()
		before = self._supplier_ledger_balance()
		amount = flt(pi.grand_total / 2, 2)
		name, entry = self._cash_payment(amount)
		self._reconcile(pi, entry)
		self._cancel_blocked(name, entry)

		self._unreconcile(entry)
		self.assertEqual(
			flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 2),
			flt(pi.grand_total, 2),
		)
		frappe.set_user(self.manager)
		request_cancellation(name, "Unreconciled through ERPNext; wrong receipt")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()

		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")
		self.assertEqual(
			flt(frappe.db.get_value("Purchase Invoice", pi.name, "outstanding_amount"), 2),
			flt(pi.grand_total, 2),
		)
		self.assertEqual(self._supplier_ledger_balance(), before)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			queue_posting(name)
		frappe.set_user("Administrator")
