# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170: the complete operational workflow in one real database scenario (no injected states).

Monthly Card with a cash row (Card User requests) -> the card is submitted while the payment is Pending -> a Card
Manager approves (a different person) -> the Card Manager queues -> the accounting service identity dispatches the
queue through the whitelisted endpoint -> one submitted Journal Entry -> the Supplier's rental Purchase Invoice ->
ERPNext Payment Reconciliation -> ERPNext Unreconcile -> a cancellation request and the cancellation by an accountant ->
a replacement approved independently and posted once. Every step asserts the ERPNext party balance (GL) and the
invoice outstanding balance, and that retries create no second entry.
"""

import frappe
from frappe.utils import flt, nowdate

from card.cash_disbursement import (
	SERVICE_ROLE,
	approve_cash_disbursement,
	get_cash_disbursements,
	queue_posting,
	request_cancellation,
	request_cash_disbursement,
	request_replacement,
)
from card.gl.posting import build_monthly_posting
from card.tests.test_cash_disbursement_db import _cash_account
from card.tests.test_s3_posting import _PostingBase

DOCTYPE = "Card Cash Disbursement"
CASH_AMOUNT = 100


class TestCashOperationalWorkflow(_PostingBase):
	def setUp(self):
		super().setUp()
		self._vat_supplier()
		self.cash = _cash_account(self.company)
		self.card_user = self._user("Card User")
		self.manager = self._user("Card Manager")
		self.second_manager = self._user("Card Manager")
		self.accountant = self._user("Accounts Manager")
		self.service = self._service_user()
		self.payable = frappe.get_cached_value("Company", self.company, "default_payable_account")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _user(self, role):
		"""A user with one role, limited to this company (Company User Permission)."""
		email = "ops-%s-%s@example.com" % (role.lower().replace(" ", "-"), frappe.generate_hash(length=6))
		user = (
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

	def _service_user(self):
		"""The accounting service identity (test site only): its role, the rights one entry needs, its company."""
		if not frappe.db.exists("Role", SERVICE_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": SERVICE_ROLE}).insert(ignore_permissions=True)
		grants = {
			"Journal Entry": {"read": 1, "write": 1, "create": 1, "submit": 1},
			"Account": {"read": 1},
			"Supplier": {"read": 1},
			"Company": {"read": 1},
			"Project": {"read": 1},
		}
		for doctype, rights in grants.items():
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
		return self._user(SERVICE_ROLE)

	def _card_with_cash_row(self):
		eq = self._equipment()
		return self._card(
			eq,
			[5],
			adjustments=[
				{
					"adjustment_date": "2026-09-01",
					"is_cash_disbursement": 1,
					"cash_account": self.cash,
					"adjustment_type": "خصم",
					"description": "Diesel paid on behalf of the supplier",
					"amount": CASH_AMOUNT,
					"side": "Supplier",
				}
			],
		)

	def _balance(self):
		"""The Supplier's balance in the General Ledger (ERPNext's own party balance)."""
		from erpnext.accounts.utils import get_balance_on

		return flt(
			get_balance_on(
				party_type="Supplier", party=self.supplier, company=self.company, date="2026-12-31"
			),
			2,
		)

	def _invoice_outstanding(self, invoice):
		return flt(frappe.db.get_value("Purchase Invoice", invoice, "outstanding_amount"), 2)

	def _reconcile(self, invoice, entry):
		pr = frappe.new_doc("Payment Reconciliation")
		pr.company = self.company
		pr.party_type = "Supplier"
		pr.party = self.supplier
		pr.receivable_payable_account = self.payable
		pr.get_unreconciled_entries()
		payments = [p.as_dict() for p in pr.get("payments") if p.reference_name == entry]
		invoices = [i.as_dict() for i in pr.get("invoices") if i.invoice_number == invoice]
		self.assertEqual(len(payments), 1)
		self.assertEqual(len(invoices), 1)
		pr.allocate_entries(frappe._dict({"payments": payments, "invoices": invoices}))
		pr.reconcile()

	def _unreconcile(self, entry):
		ur = frappe.new_doc("Unreconcile Payment")
		ur.company = self.company
		ur.voucher_type = "Journal Entry"
		ur.voucher_no = entry
		ur.add_references()
		ur.save().submit()

	def _journal_entries_for(self, record_name):
		return frappe.get_all(
			"Journal Entry",
			filters={
				"user_remark": ["like", "%Card cash payment " + record_name + " (%"],
				"docstatus": ["!=", 2],
			},
			pluck="name",
		)

	def _status(self, card, row_name):
		return next(r for r in get_cash_disbursements(card) if r["name"] == row_name)

	def test_the_complete_cash_workflow_with_reconciliation_and_replacement(self):
		# 1. the Card User requests the payment on a Draft card (the ordinary user's action)
		card = self._card_with_cash_row()
		row = next(r for r in card.adjustments if r.is_cash_disbursement)
		frappe.set_user(self.card_user)
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")
		with self.assertRaises(frappe.ValidationError):  # 2. no duplicate request for the same row
			request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1 again")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "owner"), self.card_user)

		# 3. the monthly card is submitted while the payment is Pending (independent submission)
		frappe.get_doc("Card Monthly Card", card.name).submit()
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "card"), card.name)

		# the Supplier's rental invoice for the month (CARD's own posting); cash row not in its lines
		invoice = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = frappe.get_doc("Purchase Invoice", invoice)
		pi.bill_no = "SUP-BILL-" + invoice
		pi.bill_date = "2026-09-30"
		pi.save()
		pi.submit()
		rental = flt(frappe.db.get_value("Purchase Invoice", invoice, "grand_total"), 2)
		self.assertEqual(self._invoice_outstanding(invoice), rental)
		self.assertEqual(self._balance(), -rental)  # the invoice is the only payable so far

		# 4. a different Card Manager approves; the Card Manager queues
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		queue_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(self._status(card.name, name)["status"], "Posting")

		# 5. the accounting service identity dispatches the queue (whitelisted endpoint, service identity only)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=20)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posted"])
		entry = results[0]["journal_entry"]
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "owner"), self.service)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "posted_by"), self.service)
		self.assertEqual(
			self._balance(), -(rental - CASH_AMOUNT)
		)  # the cash payment reduces the Supplier balance

		# 6. retries create no second entry: the queue is empty and the payment is already posted
		frappe.set_user(self.service)
		self.assertEqual(frappe.call("card.cash_disbursement.run_posting_queue", limit=20), [])
		frappe.set_user("Administrator")
		self.assertEqual(self._journal_entries_for(name), [entry])

		# 7. reconcile the payment against the rental invoice (ERPNext's standard Payment Reconciliation)
		self._reconcile(invoice, entry)
		self.assertEqual(self._invoice_outstanding(invoice), flt(rental - CASH_AMOUNT, 2))
		self.assertEqual(self._balance(), -(rental - CASH_AMOUNT))  # reconciliation creates no new balance
		self.assertEqual(self._status(card.name, name)["reconciliation"], "Fully reconciled")

		# 8. cancellation is refused while allocated
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_cancellation(name, "Wrong receipt")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

		# 9. unreconcile through ERPNext, then request and make the cancellation (accountant)
		self._unreconcile(entry)
		self.assertEqual(self._invoice_outstanding(invoice), rental)
		self.assertEqual(self._status(card.name, name)["reconciliation"], "Unreconciled")
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong receipt; unreconciled")
		frappe.set_user(self.accountant)
		frappe.get_doc("Journal Entry", entry).cancel()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")
		self.assertEqual(self._balance(), -rental)  # back to the invoice alone

		# 10. replacement: a new Pending payment, approved by another Card Manager, posted once
		frappe.set_user(self.manager)
		replacement = request_replacement(name, "2026-09-11", "Receipt R-2")
		frappe.set_user("Administrator")
		self.assertTrue(
			self._status(card.name, name)["replacement_pending"]
		)  # the cancelled payment shows its replacement
		frappe.set_user(self.second_manager)
		approve_cash_disbursement(replacement)
		queue_posting(replacement)
		frappe.set_user(self.service)
		second = frappe.call("card.cash_disbursement.run_posting_queue", limit=20)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in second], ["Posted"])
		new_entry = second[0]["journal_entry"]
		self.assertNotEqual(new_entry, entry)
		self.assertEqual(self._journal_entries_for(replacement), [new_entry])
		self.assertEqual(self._journal_entries_for(name), [])  # the cancelled payment has no live entry
		self.assertEqual(self._balance(), -(rental - CASH_AMOUNT))  # exactly one live payment of the amount

		# the original chain: the replacement points at the cancelled payment
		self.assertEqual(frappe.db.get_value(DOCTYPE, replacement, "replaces"), name)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")

		# 11. no second live replacement for the same cancelled payment
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_replacement(name, "2026-09-12", "Receipt R-3")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count(DOCTYPE, {"replaces": name}), 1)
