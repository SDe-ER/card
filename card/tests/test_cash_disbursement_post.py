# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2 database integration (owner security decision 2026-11-17).

The user-facing steps (request, approval, queueing) run under the real users. The accounting execution runs as a
dedicated service identity (SERVICE_ROLE) that holds only what one Journal Entry needs, and never as Administrator.
These tests create that identity in the test site (rolled back), so the rights it actually has are verified:
the Card Manager cannot execute a posting; the service identity can, and only for what it needs; a retry or an
interrupted run never creates a second entry."""

import frappe

from card.cash_disbursement import (
	SERVICE_ROLE,
	approve_cash_disbursement,
	execute_posting,
	queue_posting,
	request_cash_disbursement,
)
from card.constants import DIR_RENTED_IN
from card.tests.test_cash_disbursement_db import _cash_account
from card.tests.test_s3_config import _AdjBase

DOCTYPE = "Card Cash Disbursement"


class TestCashDisbursementPosting(_AdjBase):
	def setUp(self):
		super().setUp()
		self._clear_types()
		self.cash = _cash_account(self.company)
		self.manager = self._user("Card Manager")
		self.card_user = self._user("Card User")
		self.service = self._service_user()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _user(self, role, roles=None):
		email = "ccd-%s-%s@example.com" % (role.lower().replace(" ", "-"), frappe.generate_hash(length=6))
		return (
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "Test",
					"send_welcome_email": 0,
					"user_type": "System User",
					"roles": [{"role": r} for r in (roles or [role])],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _service_user(self):
		"""The dedicated accounting identity: its role, the rights one Journal Entry needs, and the company
		restriction. Created in the test site only; production creation needs the owner's approval."""
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

	def _card_with_cash_row(self, amount=300):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._typed_card(
			eq,
			[
				{
					"is_cash_disbursement": 1,
					"cash_account": self.cash,
					"adjustment_type": "خصم",
					"description": "Diesel paid on behalf of the supplier",
					"amount": amount,
					"side": "Supplier",
				}
			],
		)
		return card, card.adjustments[0]

	def _typed_card(self, eq, rows):
		"""A Draft monthly card for September 2026 with two worked days and the given adjustment rows."""
		from card.tests.test_controllers import _days

		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days([8, 8]):
			c.append("days", row)
		for r in rows:
			c.append("adjustments", {"adjustment_date": "2026-09-01", **r})
		c.insert(ignore_permissions=True)
		c.reload()
		return c

	def _approved(self, amount=300):
		"""A requested (by Administrator) and approved (by the Card Manager) cash payment."""
		card, row = self._card_with_cash_row(amount)
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		frappe.set_user("Administrator")
		return card, name

	def _journal_entries_for(self, record_name):
		return frappe.get_all(
			"Journal Entry",
			filters={
				"user_remark": ["like", "%Card cash payment " + record_name + " (%"],
				"docstatus": ["!=", 2],
			},
			pluck="name",
		)

	def test_approval_segregation_the_requester_cannot_approve(self):
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")
		with self.assertRaises(frappe.ValidationError):
			approve_cash_disbursement(name)  # Administrator requested it

	def test_unauthorized_user_cannot_queue_a_posting(self):
		_card, name = self._approved()
		frappe.set_user(self.card_user)
		with self.assertRaises(frappe.PermissionError):
			queue_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Approved")

	def test_card_manager_cannot_execute_the_accounting_posting(self):
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(self._journal_entries_for(name), [])

	def test_queueing_claims_an_approved_request_once(self):
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		with self.assertRaises(frappe.ValidationError):
			queue_posting(name)  # simultaneous or repeated request: already claimed
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting")

	def test_service_identity_posts_one_submitted_journal_entry(self):
		card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		entry_name = execute_posting(name)
		frappe.set_user("Administrator")

		entry = frappe.get_doc("Journal Entry", entry_name)
		self.assertEqual(entry.docstatus, 1)
		self.assertEqual(str(entry.posting_date), "2026-09-10")
		debit = [a for a in entry.accounts if a.debit_in_account_currency]
		credit = [a for a in entry.accounts if a.credit_in_account_currency]
		self.assertEqual(len(debit), 1)
		self.assertEqual(debit[0].party_type, "Supplier")
		self.assertEqual(debit[0].party, card.supplier)
		self.assertAlmostEqual(debit[0].debit_in_account_currency, 300.0)
		self.assertEqual(credit[0].account, self.cash)
		self.assertAlmostEqual(credit[0].credit_in_account_currency, 300.0)
		self.assertIn("requested by", entry.user_remark)
		self.assertIn("approved by " + self.manager, entry.user_remark)

		record = frappe.get_doc(DOCTYPE, name)
		self.assertEqual(record.status, "Posted")
		self.assertEqual(record.journal_entry, entry_name)
		self.assertEqual(self._journal_entries_for(name), [entry_name])

	def test_retry_returns_the_same_entry_and_creates_no_second_one(self):
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		first = execute_posting(name)
		second = execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(first, second)
		self.assertEqual(self._journal_entries_for(name), [first])

	def test_interrupted_run_links_the_entry_it_created_and_creates_no_second(self):
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		first = execute_posting(name)
		frappe.set_user("Administrator")
		# simulate a run that created the entry but lost the status update
		frappe.db.set_value(
			DOCTYPE,
			name,
			{"status": "Posting", "journal_entry": None, "posted_on": None},
			update_modified=False,
		)
		frappe.set_user(self.service)
		recovered = execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(recovered, first)
		self.assertEqual(self._journal_entries_for(name), [first])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_the_database_refuses_a_duplicate_transaction_key(self):
		_card, name = self._approved()
		original = frappe.get_doc(DOCTYPE, name)
		with self.assertRaises(frappe.ValidationError):  # the database unique violation, as Frappe reports it
			frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"company": original.company,
					"supplier": original.supplier,
					"card": original.card,
					"adjustment_row": original.adjustment_row,
					"amount": original.amount,
					"payment_date": original.payment_date,
					"cash_account": original.cash_account,
					"evidence": "second copy",
					"status": "Pending",
					"transaction_key": original.transaction_key,
				}
			).insert()

	def test_an_approved_payment_cannot_change_its_amount(self):
		_card, name = self._approved()
		record = frappe.get_doc(DOCTYPE, name)
		record.amount = 999
		with self.assertRaises(frappe.ValidationError):
			record.save()

	def test_the_service_identity_holds_only_the_rights_it_needs(self):
		self.assertTrue(frappe.has_permission("Journal Entry", "submit", user=self.service))
		self.assertTrue(frappe.has_permission("Account", "read", user=self.service))
		self.assertFalse(frappe.has_permission("Purchase Invoice", "write", user=self.service))
		self.assertFalse(frappe.has_permission("Card Monthly Card", "write", user=self.service))
		# a user may always edit their own User profile (Frappe standard); another user's record must be refused
		other = frappe.get_doc("User", self.card_user)
		self.assertFalse(frappe.has_permission("User", "write", doc=other, user=self.service))

	def test_a_monthly_card_with_its_own_pending_cash_row_submits_independently(self):
		"""Independence: the card's own cash row is still Pending when the card is submitted. The card submits; the
		row stays linked and visible; it is in no adjustment total and no ledger entry; approval and posting still work
		after submission; the row is counted in no total, before or after posting (never counted twice)."""
		from card.adjustments import sided_adjustments

		card, row = self._card_with_cash_row(amount=300)
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")

		frappe.get_doc("Card Monthly Card", card.name).submit()
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "docstatus"), 1)

		# visible and linked to the card
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "card"), card.name)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "adjustment_row"), row.name)
		# excluded from the adjustment totals, and no ledger effect while pending
		self.assertEqual(sided_adjustments([card.name], "Supplier").get(card.name, (0.0, 0.0)), (0.0, 0.0))
		self.assertEqual(self._journal_entries_for(name), [])

		# approval and posting still work after the card is submitted
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		queue_posting(name)
		frappe.set_user(self.service)
		entry = execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")
		self.assertEqual(self._journal_entries_for(name), [entry])
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "docstatus"), 1)
		# the posted payment is still in no card total (counted once, in the Journal Entry only)
		self.assertEqual(sided_adjustments([card.name], "Supplier").get(card.name, (0.0, 0.0)), (0.0, 0.0))

	def test_a_card_without_cash_rows_submits_while_another_payment_is_pending(self):
		"""Independence: the submit gate applies only to a card's own cash rows, never to another card's payment."""
		self._approved()  # another card's payment waits for the executor
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._typed_card(eq, [])
		card.submit()
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "docstatus"), 1)

	def test_company_scope_refuses_a_record_outside_the_users_companies(self):
		"""The document-level hook: a record of a company the user is not permitted for is refused on every path."""
		from unittest.mock import patch

		from card.cash_disbursement import has_cash_disbursement_permission

		_card, name = self._approved()
		record = frappe.get_doc(DOCTYPE, name)
		with patch("card.party_registry._restricted_companies", return_value=["Another Company"]):
			self.assertFalse(has_cash_disbursement_permission(record, "read", user=self.card_user))
		with patch("card.party_registry._restricted_companies", return_value=[]):
			self.assertFalse(has_cash_disbursement_permission(record, "read", user=self.card_user))
		with patch("card.party_registry._restricted_companies", return_value=[self.company]):
			self.assertTrue(has_cash_disbursement_permission(record, "read", user=self.card_user))
		with patch("card.party_registry._restricted_companies", return_value=None):
			self.assertTrue(has_cash_disbursement_permission(record, "read", user=self.card_user))

	def test_a_closed_accounting_period_refuses_the_posting(self):
		"""UNVERIFIED until CI runs it: ERPNext must refuse a Journal Entry dated in a closed Accounting Period,
		so a payment dated in a closed month cannot be posted into it. The service identity runs the posting."""
		_card, name = self._approved()
		frappe.get_doc(
			{
				"doctype": "Accounting Period",
				"period_name": "CCD closed " + frappe.generate_hash(length=6),
				"company": self.company,
				"start_date": "2026-09-01",
				"end_date": "2026-09-30",
				"closed_documents": [{"document_type": "Journal Entry", "closed": 1}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		with self.assertRaises(frappe.ValidationError):
			execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(self._journal_entries_for(name), [])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting")

	def test_an_allocated_journal_entry_is_not_cancelled(self):
		"""Reconciliation safety: while the entry has active allocations, neither the request nor the cancel passes."""
		from unittest.mock import patch

		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		with patch("card.cash_disbursement._has_active_allocations", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				request_cancellation(name, "Wrong supplier")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")
		with patch("card.cash_disbursement._has_active_allocations", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)

	def _posted(self):
		"""A cash payment posted through the real executor path; returns (card, payment, journal entry)."""
		card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		entry = execute_posting(name)
		frappe.set_user("Administrator")
		return card, name, entry

	def test_a_posted_journal_entry_cannot_be_cancelled_without_a_cancellation_request(self):
		_card, name, entry = self._posted()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_only_a_card_manager_can_request_a_cancellation(self):
		from card.cash_disbursement import request_cancellation

		_card, name, _entry = self._posted()
		frappe.set_user(self.card_user)
		with self.assertRaises(frappe.PermissionError):
			request_cancellation(name, "Wrong supplier")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_a_cancellation_request_cancels_the_entry_and_blocks_any_repost(self):
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong supplier on the receipt")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()

		record = frappe.get_doc(DOCTYPE, name)
		self.assertEqual(record.status, "Cancelled")
		self.assertEqual(record.journal_entry, entry)  # kept for the audit trail
		self.assertEqual(record.cancellation_reason, "Wrong supplier on the receipt")
		self.assertEqual(record.cancelled_by, "Administrator")
		self.assertTrue(record.cancelled_on)
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 2)

		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			queue_posting(name)  # a cancelled payment is never reposted automatically
		frappe.set_user("Administrator")
		self.assertEqual(self._journal_entries_for(name), [])

	def _ledger_row(self, entry, supplier, voucher, against, amount, delinked=0):
		"""A Payment Ledger Entry shaped like ERPNext v16 writes it (fields verified in erpnext version-16). The
		original row of a Journal Entry has voucher == against; an allocation has the other document on one side."""
		from frappe.utils import now_datetime

		doc = frappe.get_doc(
			{
				"doctype": "Payment Ledger Entry",
				"company": self.company,
				"account_type": "Payable",
				"account": "CCD-TEST-PAYABLE",
				"party_type": "Supplier",
				"party": supplier,
				"voucher_type": voucher[0],
				"voucher_no": voucher[1],
				"against_voucher_type": against[0],
				"against_voucher_no": against[1],
				"amount": amount,
				"amount_in_account_currency": amount,
				"posting_date": "2026-09-10",
				"delinked": delinked,
			}
		)
		doc.name = frappe.generate_hash(length=10)
		doc.owner = doc.modified_by = "Administrator"
		doc.creation = doc.modified = now_datetime()
		doc.db_insert()

	def _with_original_ledger_row(self, name, entry, amount=300):
		record = frappe.get_doc(DOCTYPE, name)
		je = ("Journal Entry", entry)
		self._ledger_row(entry, record.supplier, je, je, amount)
		return record

	def test_unreconciled_journal_entry_cancels_after_an_authorized_request(self):
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		self._with_original_ledger_row(name, entry)  # only the original row: nothing allocated
		frappe.set_user(self.manager)
		request_cancellation(name, "Unreconciled; wrong supplier")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 2)

	def test_partially_reconciled_journal_entry_cannot_be_cancelled(self):
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		record = self._with_original_ledger_row(name, entry)
		# an active allocation of 100 against the Journal Entry (a Purchase Invoice side, delinked = 0)
		self._ledger_row(
			entry, record.supplier, ("Purchase Invoice", "PI-CCD-PART"), ("Journal Entry", entry), 100
		)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_cancellation(name, "Partially reconciled")
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_fully_reconciled_journal_entry_cannot_be_cancelled(self):
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		record = self._with_original_ledger_row(name, entry)
		self._ledger_row(
			entry, record.supplier, ("Purchase Invoice", "PI-CCD-FULL"), ("Journal Entry", entry), 300
		)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_cancellation(name, "Fully reconciled")
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)

	def test_a_previously_delinked_allocation_does_not_block_cancellation(self):
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		record = self._with_original_ledger_row(name, entry)
		# an allocation that was unreconciled earlier: its ledger row is delinked, so ERPNext no longer counts it
		self._ledger_row(
			entry, record.supplier, ("Purchase Invoice", "PI-CCD-OLD"), ("Journal Entry", entry), 300, 1
		)
		frappe.set_user(self.manager)
		request_cancellation(name, "Allocation was undone earlier")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")

	def test_a_posted_payment_is_immutable_except_the_cancellation_request(self):
		_card, name, entry = self._posted()
		record = frappe.get_doc(DOCTYPE, name)
		record.amount = 999
		with self.assertRaises(frappe.ValidationError):
			record.save()
		record = frappe.get_doc(DOCTYPE, name)
		record.evidence = "rewritten receipt"
		with self.assertRaises(frappe.ValidationError):
			record.save()
		record = frappe.get_doc(DOCTYPE, name)
		record.status = "Pending"  # a Posted payment cannot be sent back to Pending
		with self.assertRaises(frappe.ValidationError):
			record.save()
		record = frappe.get_doc(DOCTYPE, name)
		record.journal_entry = None  # the link to the accounting evidence cannot be cut
		with self.assertRaises(frappe.ValidationError):
			record.save()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc(DOCTYPE, name)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "journal_entry"), entry)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "amount"), 300)

	def test_a_cancelled_payment_is_replaced_by_a_new_payment_with_its_own_approval(self):
		from card.cash_disbursement import request_cancellation, request_replacement

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_replacement(name, "2026-09-11", "Receipt R-2")  # refused: the original is still Posted
		request_cancellation(name, "Wrong receipt")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()

		frappe.set_user(self.manager)
		new = request_replacement(name, "2026-09-11", "Receipt R-2")
		frappe.set_user("Administrator")
		record = frappe.get_doc(DOCTYPE, new)
		self.assertEqual(record.status, "Pending")
		self.assertEqual(record.replaces, name)
		self.assertNotEqual(record.transaction_key, frappe.db.get_value(DOCTYPE, name, "transaction_key"))

		second = self._user("Card Manager")  # the correction needs a different approver than the requester
		frappe.set_user(second)
		approve_cash_disbursement(new)
		queue_posting(new)
		frappe.set_user(self.service)
		new_entry = execute_posting(new)
		frappe.set_user("Administrator")

		self.assertNotEqual(new_entry, entry)
		self.assertEqual(frappe.db.get_value("Journal Entry", new_entry, "docstatus"), 1)
		self.assertEqual(
			frappe.db.get_value("Journal Entry", entry, "docstatus"), 2
		)  # the original stays cancelled
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "journal_entry"), entry)
		self.assertEqual(frappe.db.get_value(DOCTYPE, new, "status"), "Posted")
