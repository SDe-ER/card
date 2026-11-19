# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2 database integration (owner security decision 2026-11-17).

The user-facing steps (request, approval, queueing) run under the real users. The accounting execution runs as a
dedicated service identity (SERVICE_ROLE) that holds only what one Journal Entry needs, and never as Administrator.
These tests create that identity in the test site (rolled back), so the rights it actually has are verified:
the Card Manager cannot execute a posting; the service identity can, and only for what it needs; a retry or an
interrupted run never creates a second entry."""

import frappe
from frappe.utils import cint, flt, nowdate

from card.card.doctype.card_cash_disbursement.card_cash_disbursement import CREATION_REQUEST
from card.cash_disbursement import (
	SERVICE_ROLE,
	approve_cash_disbursement,
	execute_posting,
	queue_posting,
	request_cash_disbursement,
)
from card.constants import DIR_RENTED_IN
from card.tests.cancel_reason import with_reason
from card.tests.cash_service_perms import copy_standard_perms
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

	def _service_user(self, companies=None):
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
			if frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": SERVICE_ROLE}):
				continue  # granted once per test; a second identity only differs in its company grants
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
		for company in companies if companies is not None else [self.company]:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": user,
					"allow": "Company",
					"for_value": company,
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
				"user_remark": ["like", "%Card cash payment " + record_name + "%"],
				"docstatus": 1,
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

	def test_recovery_with_an_already_linked_valid_entry_creates_no_second_entry(self):
		"""Interruption after the entry was submitted and linked, before the payment's status update: the recovery
		validates the linked entry and marks the payment Posted; no second entry is created."""
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		first = execute_posting(name)
		frappe.set_user("Administrator")
		frappe.db.set_value(
			DOCTYPE,
			name,
			{"status": "Posting", "posted_on": None, "posted_by": None},
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
		copy = frappe.get_doc(
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
		)
		copy.flags.controlled_transition = (
			CREATION_REQUEST  # as the request action would: the database is under test
		)
		with self.assertRaises(
			frappe.UniqueValidationError
		):  # the database unique violation, as Frappe reports it
			copy.insert()

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

	def _close_period(self, start, end):
		"""A closed Accounting Period for Journal Entries (ERPNext closes a document type per period)."""
		return frappe.get_doc(
			{
				"doctype": "Accounting Period",
				"period_name": "CCD closed " + frappe.generate_hash(length=6),
				"company": self.company,
				"start_date": start,
				"end_date": end,
				"closed_documents": [{"document_type": "Journal Entry", "closed": 1}],
			}
		).insert(ignore_permissions=True)

	def test_a_closed_accounting_period_refuses_the_posting(self):
		"""ERPNext refuses a Journal Entry dated in a closed Accounting Period (accounting_period.py
		validate_accounting_period_on_doc_save, raising ClosedAccountingPeriod). Source: erpnext version-16."""
		from erpnext.accounts.doctype.accounting_period.accounting_period import ClosedAccountingPeriod

		_card, name = self._approved()
		self._close_period("2026-09-01", "2026-09-30")
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		with self.assertRaises(ClosedAccountingPeriod):
			execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(self._journal_entries_for(name), [])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting")

	def test_a_closed_accounting_period_refuses_the_cancellation(self):
		"""ERPNext refuses to cancel accounting entries in a closed period (general_ledger.validate_accounting_period:
		"You cannot create or cancel any accounting entries ..."). A posted payment in a later-closed period stays Posted
		and its entry stays submitted."""
		from erpnext.accounts.doctype.accounting_period.accounting_period import ClosedAccountingPeriod

		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		self._close_period("2026-09-01", "2026-09-30")
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong receipt; period closed")
		frappe.set_user("Administrator")
		# the refused cancel is rolled back to the savepoint, as the request is rolled back in production
		frappe.db.savepoint("ccd_closed_cancel")
		with self.assertRaises(ClosedAccountingPeriod):
			frappe.get_doc("Journal Entry", entry).cancel()
		frappe.db.rollback(save_point="ccd_closed_cancel")
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "journal_entry"), entry)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancellation Requested")

	def test_late_approval_of_a_payment_dated_in_a_closed_period_is_refused(self):
		"""A Pending payment dated in a period closed later cannot be approved: it could never be posted."""
		from erpnext.accounts.doctype.accounting_period.accounting_period import ClosedAccountingPeriod

		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-LATE")
		self._close_period("2026-09-01", "2026-09-30")
		frappe.set_user(self.manager)
		with self.assertRaises(ClosedAccountingPeriod):
			approve_cash_disbursement(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")
		self.assertEqual(self._journal_entries_for(name), [])

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

	def test_cash_row_columns_follow_the_payment_record(self):
		"""The Additions & Deductions table shows the payment status, its journal entry and the reconciliation of its
		cash row, read from the payment record (the authority); the amount of the row is never touched."""
		from card.cash_disbursement import cash_row_status, get_cash_row_status

		card, name, entry = self._posted()
		row = next(r.name for r in card.adjustments if cint(r.is_cash_disbursement))
		info = cash_row_status(card.name, row)
		self.assertEqual(info["name"], name)
		self.assertEqual(info["journal_entry"], entry)
		self.assertTrue(info["label"].startswith("Posted"), info["label"])
		by_row = get_cash_row_status(card.name)
		self.assertEqual(by_row[row]["name"], name)
		self.assertEqual(by_row[row]["journal_entry"], entry)
		# the display columns read the record; the payment amount still equals the row amount (no change by the display)
		self.assertEqual(
			flt(frappe.db.get_value(DOCTYPE, name, "amount"), 2),
			flt(frappe.db.get_value("Card Monthly Card Adjustment", row, "amount"), 2),
		)
		# the card's own refresh writes the three display columns of the cash row, and nothing else
		doc = frappe.get_doc("Card Monthly Card", card.name)
		amounts_before = [flt(r.amount, 2) for r in doc.adjustments]
		doc._refresh_cash_rows()
		child = next(r for r in doc.adjustments if r.name == row)
		self.assertEqual(child.cash_payment, name)
		self.assertEqual(child.cash_journal_entry, entry)
		self.assertTrue(child.cash_status.startswith("Posted"), child.cash_status)
		self.assertEqual([flt(r.amount, 2) for r in doc.adjustments], amounts_before)

	def test_a_plain_save_cannot_approve_a_pending_payment(self):
		"""FR-170 review (High): a Card Manager's ordinary save must not move a Pending payment to Approved."""
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-9")
		frappe.set_user(self.manager)
		doc = frappe.get_doc(DOCTYPE, name)
		doc.status = "Approved"
		doc.approved_by = self.manager
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")
		self.assertFalse(frappe.db.get_value(DOCTYPE, name, "approved_by"))

	def test_a_plain_save_cannot_skip_to_any_other_status(self):
		"""FR-170 review (High): a status pair with no server owner (Pending -> Posted, Pending -> Cancelled, ...) is refused
		by a plain save, even though no flag is set (None must not equal None)."""
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt SKIP-1")
		for target in ("Posted", "Cancelled", "Posting", "Cancellation Requested"):
			with self.subTest(target=target):
				frappe.set_user(self.manager)
				doc = frappe.get_doc(DOCTYPE, name)
				doc.status = target
				with self.assertRaises(frappe.ValidationError):
					doc.save()
				frappe.set_user("Administrator")
				self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")

	def test_posting_without_a_recorded_approval_is_refused(self):
		"""FR-170 security review: even if a status were moved to Posting without an approval, the executor refuses it
		and creates no Journal Entry (the approver is required)."""
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt NOAPP-1")
		frappe.db.set_value(DOCTYPE, name, "status", "Posting")  # a tampered status: no approval exists
		frappe.set_user(self.service)
		with self.assertRaisesRegex(frappe.ValidationError, "has no approval"):
			execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting")
		self.assertEqual(self._journal_entries_for(name), [])

	def test_a_client_supplied_flags_key_cannot_approve_a_payment(self):
		"""FR-170 security review: a client document carrying a flags key (the path of a save with client data) must
		not carry the approval authority. Frappe's update() skips the reserved key 'flags', so the save is refused."""
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt FLAG-1")
		frappe.set_user(self.manager)
		doc = frappe.get_doc(DOCTYPE, name)
		doc.update(
			{
				"status": "Approved",
				"approved_by": self.manager,
				"flags": {"controlled_transition": "approval"},
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")
		self.assertFalse(frappe.db.get_value(DOCTYPE, name, "approved_by"))

	def test_a_plain_save_cannot_queue_an_approved_payment(self):
		_card, name = self._approved()
		frappe.set_user(self.manager)
		doc = frappe.get_doc(DOCTYPE, name)
		doc.status = "Posting"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Approved")

	def test_refused_status_moves_create_no_accounting_entry(self):
		"""FR-170 security (negative cases): every refused approval, posting and tampering attempt is refused, and none of
		them creates a Journal Entry. Covers: a Card User calling approval; the requester approving her own request;
		posting a Pending payment; queueing it; a plain save that approves it, sets approval evidence, or uses the
		REST set_value route to approve it."""
		from card.cash_disbursement import approve_cash_disbursement, execute_posting, queue_posting

		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt NEG-1")
		# 3. a user without an approval role calls the approval endpoint
		frappe.set_user(self._user("Card User"))
		with self.assertRaises(frappe.PermissionError):
			approve_cash_disbursement(name)
		# 4. the requester approves her own request (a Card Manager who requested it)
		requester = self._user("Card Manager")
		card2, row2 = self._card_with_cash_row()
		frappe.set_user(requester)
		own = request_cash_disbursement(card2.name, row2.name, "2026-09-10", "Receipt NEG-2")
		with self.assertRaises(frappe.ValidationError):
			approve_cash_disbursement(own)
		# 5. posting without a valid approval: the service identity cannot post a Pending payment
		frappe.set_user(self.service)
		with self.assertRaises(frappe.ValidationError):
			execute_posting(name)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=20)
		self.assertNotIn(name, [r["name"] for r in results])
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			queue_posting(name)
		# 7. tampering with the approval evidence by an ordinary save
		doc = frappe.get_doc(DOCTYPE, name)
		doc.approved_by = self.manager
		doc.approved_on = nowdate()
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		# 1. Pending -> Approved by an ordinary save, and by the REST set_value route
		doc = frappe.get_doc(DOCTYPE, name)
		doc.status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		with self.assertRaises(frappe.ValidationError):
			frappe.client.set_value(DOCTYPE, name, "status", "Approved")
		frappe.set_user("Administrator")
		# 8. nothing moved and no accounting entry was created by any refused attempt
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")
		self.assertFalse(frappe.db.get_value(DOCTYPE, name, "approved_by"))
		self.assertEqual(self._journal_entries_for(name), [])
		self.assertEqual(self._journal_entries_for(own), [])

	def test_approval_keeps_the_approver_and_the_time(self):
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt A-1")
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "approved_by"), self.manager)
		self.assertTrue(frappe.db.get_value(DOCTYPE, name, "approved_on"))
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Approved")

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

	def test_the_desk_reads_cash_status_with_a_get(self):
		"""Regression: frappe.call sends POST unless type is set, and the GET-only status endpoint refuses a POST with
		"Not permitted" on every Monthly Card form. Every Desk call site of that endpoint must declare type GET."""
		import re
		from pathlib import Path

		# every JavaScript file of the CARD module, so a new Desk call site elsewhere is checked too
		module_dir = Path(__file__).resolve().parents[1] / "card"
		sites = 0
		for script in sorted(module_dir.rglob("*.js")):
			text = script.read_text(encoding="utf-8")
			for match in re.finditer(r"card\.cash_disbursement\.get_cash_disbursements", text):
				sites += 1
				# the call's own argument list: from the match up to the closing of its frappe.call block
				call = text[match.start() : text.find("})", match.start()) + 2]
				self.assertIn('type: "GET"', call, script.name)
		self.assertGreaterEqual(sites, 2)

	def test_replacement_needs_a_reason_is_stored_and_a_second_live_one_is_refused(self):
		from card.cash_disbursement import request_cancellation, request_replacement

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong receipt")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()

		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_replacement(name, "   ", "2026-09-11", "Receipt R-2")  # the reason is mandatory
		new = request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
		with self.assertRaises(frappe.ValidationError):
			request_replacement(name, "Again", "2026-09-11", "Receipt R-9")  # one live replacement at a time
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, new, "replacement_reason"), "Wrong amount")
		self.assertEqual(frappe.db.get_value(DOCTYPE, new, "status"), "Pending")

	def _cancelled_posted(self):
		"""A posted payment, then its cancellation request and the cancellation of its entry; returns (card, payment)."""
		from card.cash_disbursement import request_cancellation

		card, name, entry = self._posted()
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong receipt")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()
		return card, name

	def test_a_direct_insert_cannot_create_a_queued_or_approved_payment(self):
		"""FR-170 security review: a Card Manager has create on the payment DocType, so the API insert path
		(frappe.client.insert) must not create a payment in any state but through the request or the replacement."""
		from frappe.client import insert

		_paid_card, paid, entry = (
			self._posted()
		)  # real names, so link validation passes and the guard itself refuses
		card, row = self._card_with_cash_row()
		other = self._user("Card Manager")
		base = {
			"doctype": DOCTYPE,
			"company": card.company,
			"supplier": card.supplier,
			"card": card.name,
			"adjustment_row": row.name,
			"amount": row.amount,
			"payment_date": "2026-09-10",
			"cash_account": self.cash,
			"evidence": "Receipt FORGED-1",
		}
		attempts = [
			{"status": "Posting", "approved_by": other},
			{"status": "Approved", "approved_by": other, "approved_on": "2026-09-10 10:00:00"},
			{"status": "Posted", "journal_entry": entry},
			{"status": "Pending"},  # even a Pending one: the request's own checks would be skipped
			{"status": "Pending", "replaces": paid, "replacement_reason": "forged"},
		]
		frappe.set_user(self.manager)
		for extra in attempts:
			with (
				self.subTest(extra=extra),
				self.assertRaisesRegex(frappe.ValidationError, "created only by a request or a replacement"),
			):
				insert({**base, **extra})
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists(DOCTYPE, {"card": card.name}))

	def test_a_pending_payment_keeps_its_requester_row_and_server_fields(self):
		"""FR-170 final reviews: a plain save (frappe.client.save, PUT /api/resource) of a Pending payment cannot rewrite
		the requester to self-approve, re-point it to another card row, or set a server-owned field."""
		from frappe.client import save

		card, row = self._card_with_cash_row()
		frappe.set_user(self.manager)
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt OWN-1")
		other_card, other_row = self._card_with_cash_row()
		changes = [
			({"owner": self._user("Card Manager")}, "fixed when it is created"),
			({"card": other_card.name, "adjustment_row": other_row.name}, "fixed when it is created"),
			({"amount": 1}, "fixed when it is created"),
			({"equipment": other_card.equipment}, "fixed when it is created"),
			({"project": self._other_project()}, "fixed when it is created"),
			({"posting_claimed_by": self.manager}, "set by the approval only"),
			({"cancellation_reason": "forged"}, "set by the approval only"),
		]
		for change, message in changes:
			doc = frappe.get_doc(DOCTYPE, name).as_dict()
			doc.update(change)
			with self.subTest(change=change), self.assertRaisesRegex(frappe.ValidationError, message):
				save(doc)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot approve their own"):
			approve_cash_disbursement(name)  # the requester is still the owner
		evidence = frappe.get_doc(DOCTYPE, name)
		evidence.evidence = (
			"Receipt OWN-1 (corrected)"  # the evidence of a pending request may still be corrected
		)
		evidence.save()
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(
			DOCTYPE, name, ["owner", "card", "amount", "status", "approved_by"], as_dict=True
		)
		self.assertEqual((stored.owner, stored.card, stored.status), (self.manager, card.name, "Pending"))
		self.assertEqual(flt(stored.amount), flt(row.amount))
		self.assertFalse(stored.approved_by)

	def _other_project(self):
		"""A second Project of the test company (a real link, so only the payment guard can refuse it)."""
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "CCD other project " + frappe.generate_hash(length=6),
				"company": self.company,
			}
		)
		project.insert(ignore_permissions=True)
		return project.name

	def test_a_replacement_describes_the_card_and_stays_in_its_company(self):
		"""FR-170 final reviews: the replacement takes equipment and project from the card, and a card that moved to
		another company is refused with the common refusal (nothing about that card is answered)."""
		from card.cash_disbursement import request_replacement

		card, name = self._cancelled_posted()
		frappe.set_user(self.manager)
		new = request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(DOCTYPE, new, ["equipment", "project", "company"], as_dict=True)
		expected = frappe.db.get_value(
			"Card Monthly Card", card.name, ["equipment", "project", "company"], as_dict=True
		)
		self.assertEqual(stored, expected)

		other_card, other_name = self._cancelled_posted()
		frappe.db.set_value(
			"Card Monthly Card", other_card.name, "company", "CCD Moved Company", update_modified=False
		)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.PermissionError):
			request_replacement(other_name, "Wrong amount", "2026-09-11", "Receipt R-3")
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists(DOCTYPE, {"replaces": other_name}))

	def test_the_executor_refuses_an_approval_recorded_by_the_requester(self):
		"""Defence in depth: the posting checks the four-eyes rule again on the stored record."""
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user("Administrator")
		owner = frappe.db.get_value(DOCTYPE, name, "owner")
		frappe.db.set_value(DOCTYPE, name, "approved_by", owner, update_modified=False)  # a tampered approver
		frappe.set_user(self.service)
		with self.assertRaisesRegex(frappe.ValidationError, "approved by its requester"):
			execute_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(self._journal_entries_for(name), [])

	def test_the_replacement_link_and_reason_cannot_be_changed_by_a_save(self):
		from card.cash_disbursement import request_replacement

		_card, name = self._cancelled_posted()
		frappe.set_user(self.manager)
		new = request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
		for field, value in (("replacement_reason", "rewritten"), ("replaces", None)):
			record = frappe.get_doc(DOCTYPE, new)
			record.set(field, value)
			with self.subTest(field=field), self.assertRaises(frappe.ValidationError):
				record.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, new, "replacement_reason"), "Wrong amount")
		self.assertEqual(frappe.db.get_value(DOCTYPE, new, "replaces"), name)

	def test_a_cancelled_payment_is_replaced_once(self):
		"""A replaced payment cannot be replaced again after its replacement is cancelled: the chain does not fork."""
		from card.cash_disbursement import request_cancellation, request_replacement

		_card, name = self._cancelled_posted()
		frappe.set_user(self.manager)
		new = request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
		frappe.set_user(self._user("Card Manager"))
		approve_cash_disbursement(new)
		queue_posting(new)
		frappe.set_user(self.service)
		new_entry = execute_posting(new)
		frappe.set_user(self.manager)
		request_cancellation(new, "Wrong receipt again")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", new_entry).cancel()

		frappe.set_user(self.manager)
		with self.assertRaisesRegex(frappe.ValidationError, "already replaced"):
			request_replacement(name, "Third try", "2026-09-12", "Receipt R-3")
		latest = request_replacement(
			new, "Third try", "2026-09-12", "Receipt R-3"
		)  # the latest one may be replaced
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, latest, "replaces"), new)
		self.assertEqual(frappe.db.count(DOCTYPE, {"replaces": name}), 1)

	def test_a_replacement_needs_the_same_source_checks_as_a_request(self):
		"""A replacement is refused for a row that is no longer a cash row, for an amount of zero, and on a cancelled
		card, as a first request is (FR-170 review)."""
		from card.cash_disbursement import request_replacement

		card, name = self._cancelled_posted()
		row = frappe.db.get_value(DOCTYPE, name, "adjustment_row")
		child = "Card Monthly Card Adjustment"
		cases = (
			("is_cash_disbursement", 0, "not a cash payment"),
			("amount", 0, "above zero"),
		)
		for field, value, message in cases:
			original = frappe.db.get_value(child, row, field)
			frappe.db.set_value(child, row, field, value, update_modified=False)
			frappe.set_user(self.manager)
			with self.subTest(field=field), self.assertRaisesRegex(frappe.ValidationError, message):
				request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
			frappe.set_user("Administrator")
			frappe.db.set_value(child, row, field, original, update_modified=False)
		frappe.db.set_value("Card Monthly Card", card.name, "docstatus", 2, update_modified=False)
		frappe.set_user(self.manager)
		with self.assertRaisesRegex(frappe.ValidationError, "is cancelled"):
			request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists(DOCTYPE, {"replaces": name}))

	def test_a_cancelled_payment_is_replaced_by_a_new_payment_with_its_own_approval(self):
		from card.cash_disbursement import request_cancellation, request_replacement

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			request_replacement(
				name, "Wrong amount", "2026-09-11", "Receipt R-2"
			)  # refused: the original is still Posted
		request_cancellation(name, "Wrong receipt")
		frappe.set_user("Administrator")
		frappe.get_doc("Journal Entry", entry).cancel()

		frappe.set_user(self.manager)
		new = request_replacement(name, "Wrong amount", "2026-09-11", "Receipt R-2")
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

	def test_only_the_service_identity_can_dispatch_the_queue(self):
		_card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		with self.assertRaises(frappe.PermissionError):
			frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting")
		self.assertEqual(self._journal_entries_for(name), [])

	def test_a_failed_posting_is_recorded_retried_and_posted_once(self):
		"""A real database failure (the Cash account is disabled, so the Journal Entry is refused) rolls the attempt back,
		records Posting Failed with the error, and a retry after the fix posts exactly one entry."""
		_card, name = self._approved(amount=300)
		account = frappe.db.get_value(DOCTYPE, name, "cash_account")
		frappe.db.set_value("Account", account, "disabled", 1)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertTrue(results[0]["error"])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting Failed")
		self.assertTrue(frappe.db.get_value(DOCTYPE, name, "posting_error"))
		self.assertEqual(self._journal_entries_for(name), [])  # the failed attempt left no entry

		frappe.db.set_value("Account", account, "disabled", 0)
		frappe.set_user(self.manager)
		queue_posting(name)  # a failed payment can be queued again (the retry)
		frappe.set_user(self.service)
		again = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in again], ["Posted"])
		self.assertEqual(self._journal_entries_for(name), [again[0]["journal_entry"]])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "posting_error"), None)

	def test_the_executor_refuses_a_source_changed_after_approval(self):
		"""Security: the approved amount, Cash account and source row are revalidated before any Journal Entry is built.
		A changed source row is not posted (Posting Failed, no entry); after the source is restored, one entry is posted."""
		card, name = self._approved(amount=300)
		row = next(r for r in card.adjustments if r.is_cash_disbursement)
		frappe.db.set_value("Card Monthly Card Adjustment", row.name, "amount", 999)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertIn("changed after approval", results[0]["error"])
		self.assertEqual(self._journal_entries_for(name), [])

		frappe.db.set_value("Card Monthly Card Adjustment", row.name, "amount", 300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		again = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in again], ["Posted"])
		self.assertEqual(self._journal_entries_for(name), [again[0]["journal_entry"]])

	def test_a_pending_cash_row_is_in_no_card_total_and_no_net(self):
		"""Accounting regression: a pending owner-paid cash row adds nothing to the card's totals or its supplier net, so
		the invoice lines built from the card match its stored net (the submit-time identity check)."""
		card, _row = self._card_with_cash_row(amount=300)
		card.reload()
		self.assertEqual(flt(card.total_deductions, 2), 0)
		self.assertEqual(flt(card.total_additions, 2), 0)
		self.assertEqual(flt(card.net_amount, 2), flt(card.amount, 2))

	def test_cancelling_the_entry_needs_an_accounting_role(self):
		"""Authorization: ERPNext's own cancel decides. An Accounts Manager (least-privileged accounting role that cancels
		a Journal Entry in this site) cancels after the request; a Card Manager is refused by ERPNext itself."""
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		request_cancellation(name, "Wrong receipt; authorization test")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc("Journal Entry", entry).cancel()  # Card Manager has no right to cancel the entry
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancellation Requested")

		accountant = self._user("Accounts Manager")
		frappe.set_user(accountant)
		frappe.get_doc("Journal Entry", entry).cancel()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")

	def test_an_approved_payment_keeps_its_snapshot_when_the_equipment_owner_changes(self):
		"""Historical integrity: the approved snapshot (company, beneficiary, source row, amount, Cash account, payment
		date, approval evidence) does not follow the equipment. A later owner change neither changes the snapshot nor
		moves the posting to the new owner: the Journal Entry debits the Supplier the card kept."""
		card, name = self._approved(amount=300)
		snapshot_fields = [
			"company",
			"supplier",
			"adjustment_row",
			"amount",
			"cash_account",
			"payment_date",
			"evidence",
		]
		before = frappe.db.get_value(DOCTYPE, name, snapshot_fields, as_dict=True)
		historical = frappe.db.get_value(DOCTYPE, name, "supplier")
		self.assertEqual(historical, card.supplier)

		new_owner = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "HIST-NEW-" + frappe.generate_hash(length=6),
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Card Equipment", card.equipment, "supplier", new_owner.name)

		self.assertEqual(frappe.db.get_value(DOCTYPE, name, snapshot_fields, as_dict=True), before)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posted"])
		entry = results[0]["journal_entry"]
		debit = frappe.db.get_value(
			"Journal Entry Account",
			{"parent": entry, "debit_in_account_currency": ["!=", 0]},
			["party", "party_type"],
			as_dict=True,
		)
		self.assertEqual(debit.party, historical)
		self.assertNotEqual(debit.party, new_owner.name)

	def test_a_pending_cash_row_is_in_no_customer_side_total(self):
		"""Regression: a cash row is a Supplier-side row (validated); no Customer-side total or invoice line counts it."""
		from card.adjustments import sided_adjustments

		card, _row = self._card_with_cash_row(amount=300)
		self.assertEqual(sided_adjustments([card.name], "Customer").get(card.name, (0.0, 0.0)), (0.0, 0.0))
		self.assertEqual(sided_adjustments([card.name], "Supplier").get(card.name, (0.0, 0.0)), (0.0, 0.0))

	# ---- Finding 1: the company grant is explicit and fail-closed (run_posting_queue and execute_posting) ----

	def _second_company(self):
		"""A second company of the test site (database insert, no chart: it is only used to prove a refusal)."""
		token = frappe.generate_hash(length=6).upper()
		name = "TEST-SEC-CO-" + token
		company = frappe.new_doc("Company")
		company.update(
			{
				"company_name": name,
				"abbr": "S" + token[:5],
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		company.name = name
		company.db_insert()
		return name

	def _foreign_posting(self, company):
		"""A payment of another company in the Posting state (access-control fixture: the transition is not under test)."""
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"company": company,
				"supplier": self.supplier,
				"card": "CARD-FOREIGN-" + frappe.generate_hash(length=6),
				"adjustment_row": "ROW-FOREIGN",
				"amount": 100,
				"payment_date": "2026-09-10",
				"cash_account": self.cash,
				"evidence": "foreign fixture",
				"status": "Posted",
				"transaction_key": frappe.generate_hash(length=64),
			}
		)
		doc.db_insert()  # straight to the database: a direct insert of a non-requested payment is refused by validate
		frappe.db.set_value(DOCTYPE, doc.name, "status", "Posting", update_modified=False)
		return doc.name

	def test_no_company_grant_means_no_company(self):
		"""Service-role membership alone grants nothing: with no Company User Permission the dispatch returns nothing,
		and a direct executor call with no company is refused. The payment stays queued and no entry is created."""
		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user("Administrator")
		identity = self._service_user(companies=[])
		frappe.set_user(identity)
		self.assertEqual(frappe.call("card.cash_disbursement.run_posting_queue", limit=5), [])
		with self.assertRaises(frappe.PermissionError):
			execute_posting(name)  # the identity has no company grant: refused before any write
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting")
		self.assertEqual(self._journal_entries_for(name), [])

	def test_one_company_grant_posts_only_that_company(self):
		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posted"])

	def test_multiple_company_grants_post_each_granted_company(self):
		"""Two granted companies: the payment of each is selected and attempted; neither is refused as unauthorized."""
		second = self._second_company()
		identity = self._service_user(companies=[self.company, second])
		_card, name = self._approved(amount=300)
		other = self._foreign_posting(second)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(identity)
		results = {
			r["name"]: r["status"] for r in frappe.call("card.cash_disbursement.run_posting_queue", limit=10)
		}
		frappe.set_user("Administrator")
		self.assertEqual(results[name], "Posted")
		self.assertIn(other, results)
		self.assertNotEqual(results[other], "Not permitted")

	def test_cross_company_posting_is_denied_and_creates_no_entry(self):
		"""A company the identity is not granted is never selected, never posted, never marked failed, and a direct
		executor call for it is refused before anything is written. No Journal Entry exists for that company."""
		second = self._second_company()
		identity = self._service_user(companies=[self.company])
		foreign = self._foreign_posting(second)
		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(identity)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=10)
		with self.assertRaises(frappe.PermissionError):
			execute_posting(foreign)
		frappe.set_user("Administrator")
		self.assertNotIn(foreign, [r["name"] for r in results])
		self.assertEqual(
			frappe.db.get_value(DOCTYPE, foreign, ["status", "journal_entry"], as_dict=True).status, "Posting"
		)
		self.assertIsNone(frappe.db.get_value(DOCTYPE, foreign, "journal_entry"))
		self.assertEqual(frappe.db.count("Journal Entry", {"company": second}), 0)

	# ---- Finding 2: the entry is identified only by the durable link, validated, never by a remark ----

	def _forged_entry(self, name, amount, party=None):
		"""A draft Journal Entry with the remark of a payment, created outside the executor (a forgery attempt)."""
		from erpnext.accounts.party import get_party_account

		party = party or self.supplier
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": self.company,
				"posting_date": "2026-09-10",
				"user_remark": "Card cash payment " + name + " (forged) on behalf of the Supplier",
				"accounts": [
					{
						"account": get_party_account("Supplier", party, self.company),
						"party_type": "Supplier",
						"party": party,
						"debit_in_account_currency": amount,
					},
					{"account": self.cash, "credit_in_account_currency": amount},
				],
			}
		).insert(ignore_permissions=True)
		return entry.name

	def test_a_forged_remark_with_a_wrong_amount_is_not_linked(self):
		_card, name = self._approved(amount=300)
		forged = self._forged_entry(name, 999)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		own = execute_posting(name)
		frappe.set_user("Administrator")
		self.assertNotEqual(own, forged)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "journal_entry"), own)
		self.assertEqual(frappe.db.get_value("Journal Entry", own, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Journal Entry", forged, "docstatus"), 0)

	def test_a_forged_remark_with_a_wrong_supplier_is_not_linked(self):
		_card, name = self._approved(amount=300)
		other = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "FORGE-SUP-" + frappe.generate_hash(length=6),
				"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name"),
			}
		).insert(ignore_permissions=True)
		forged = self._forged_entry(name, 300, party=other.name)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		own = execute_posting(name)
		frappe.set_user("Administrator")
		self.assertNotEqual(own, forged)
		self.assertEqual(
			frappe.db.get_value("Journal Entry Account", {"parent": own, "party_type": "Supplier"}, "party"),
			self.supplier,
		)

	def test_a_linked_entry_with_mismatched_fields_is_refused(self):
		"""Correct transaction key in the remark, mismatched accounting fields, and the link written to it: the recovery
		refuses it (Posting Failed with the mismatch), never marks the payment Posted, and does not touch the entry."""
		_card, name = self._approved(amount=300)
		key = frappe.db.get_value(DOCTYPE, name, "transaction_key")
		forged = self._forged_entry(name, 999)
		frappe.db.set_value(
			"Journal Entry", forged, "user_remark", "Card cash payment " + name + " (" + key + ")"
		)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.db.set_value(DOCTYPE, name, "journal_entry", forged, update_modified=False)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertIn("does not match", results[0]["error"])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting Failed")
		self.assertEqual(frappe.db.get_value("Journal Entry", forged, "docstatus"), 0)

	def test_an_interruption_before_submit_leaves_no_entry_and_is_retried(self):
		from unittest.mock import patch

		from erpnext.accounts.doctype.journal_entry.journal_entry import JournalEntry

		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		with patch.object(
			JournalEntry, "submit", side_effect=frappe.ValidationError("interrupted before submit")
		):
			results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertIsNone(frappe.db.get_value(DOCTYPE, name, "journal_entry"))
		self.assertEqual(frappe.db.count("Journal Entry", {"user_remark": ["like", "%" + name + "%"]}), 0)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		again = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in again], ["Posted"])
		self.assertEqual(self._journal_entries_for(name), [again[0]["journal_entry"]])

	def test_recovery_of_a_linked_draft_entry_submits_it_once(self):
		"""Interruption after the link was written and before submission: the recovery submits the linked entry and
		marks the payment Posted; no second entry is created."""
		from card.cash_disbursement import _create_entry

		_card, name = self._approved(amount=300)
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.set_user(self.service)
		draft = _create_entry(doc)
		frappe.db.set_value(DOCTYPE, name, "journal_entry", draft.name, update_modified=False)
		frappe.db.set_value(DOCTYPE, name, "status", "Posting", update_modified=False)
		frappe.set_user(self.service)
		self.assertEqual(execute_posting(name), draft.name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Journal Entry", draft.name, "docstatus"), 1)
		self.assertEqual(self._journal_entries_for(name), [draft.name])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_repeated_or_concurrent_dispatch_creates_one_entry(self):
		"""Two dispatches of the same queue (a retry or a second worker): the second finds the payment Posted, or waits on
		the row lock and then finds it Posted; one submitted entry in every case. The two-connection race itself is not
		reproducible in this single-connection suite; the row lock and the unique link are the database guarantees."""
		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		first = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		second = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in first], ["Posted"])
		self.assertEqual(second, [])
		self.assertEqual(self._journal_entries_for(name), [first[0]["journal_entry"]])

	def test_a_linked_cancelled_entry_is_refused(self):
		"""A link to a cancelled entry is never accepted: the payment is Posting Failed and stays unposted."""
		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		own = execute_posting(name)
		frappe.set_user("Administrator")
		frappe.db.set_value(DOCTYPE, name, {"status": "Posting", "posted_on": None}, update_modified=False)
		frappe.db.set_value("Journal Entry", own, "docstatus", 2, update_modified=False)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertIn("it is cancelled", results[0]["error"])
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posting Failed")

	def test_an_interruption_after_submit_before_status_update_rolls_back_and_posts_once(self):
		"""Interruption after the entry was submitted but before the payment became Posted: the whole posting rolls
		back (the entry and the link with it), the payment is Posting Failed, and the retry posts exactly one entry."""
		from unittest.mock import patch

		_card, name = self._approved(amount=300)
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		with patch(
			"card.cash_disbursement.now_datetime",
			side_effect=frappe.ValidationError("interrupted after submit"),
		):
			results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertIsNone(frappe.db.get_value(DOCTYPE, name, "journal_entry"))
		self.assertEqual(self._journal_entries_for(name), [])
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user(self.service)
		again = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in again], ["Posted"])
		self.assertEqual(self._journal_entries_for(name), [again[0]["journal_entry"]])

	# ---------------------------------------------------------------- FR-170 final audit: the card row of a live payment

	def _row_save_refused(self, card_name, change, user="Administrator"):
		"""Apply ``change`` to the Draft card and save it as ``user``: the save must be refused."""
		frappe.set_user(user)
		doc = frappe.get_doc("Card Monthly Card", card_name)
		change(doc)
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		frappe.set_user("Administrator")

	def _cash_row(self, card_name):
		doc = frappe.get_doc("Card Monthly Card", card_name)
		return next(r for r in doc.adjustments if cint(r.is_cash_disbursement))

	def test_a_paid_cash_row_cannot_be_unticked_or_changed_on_save(self):
		"""H2: on a Draft card, the row of a posted payment cannot become an ordinary deduction (it would be deducted
		again by the invoice) and keeps its amount, Cash account, kind and side."""
		card, name, entry = self._posted()
		row_name = self._cash_row(card.name).name
		other_cash = frappe.copy_doc(frappe.get_doc("Account", self.cash))
		other_cash.account_name = "Second cash " + frappe.generate_hash(length=4)
		other_cash.insert(ignore_permissions=True)

		def setter(field, value):
			def change(doc):
				next(r for r in doc.adjustments if r.name == row_name).set(field, value)

			return change

		for field, value in (
			("is_cash_disbursement", 0),
			("amount", 250),
			("cash_account", other_cash.name),
			("adjustment_type", "إضافة"),
			("side", "Customer"),
		):
			self._row_save_refused(card.name, setter(field, value))
		row = self._cash_row(card.name)
		self.assertEqual((cint(row.is_cash_disbursement), flt(row.amount, 2)), (1, 300.0))
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, ["status", "journal_entry"]), ("Posted", entry))

	def test_a_paid_cash_row_cannot_be_removed_and_its_card_cannot_be_deleted(self):
		"""H2: the row of a live payment stays on the card, and the card itself cannot be deleted (the payment links it)."""
		card, name, _entry = self._posted()
		row_name = self._cash_row(card.name).name
		self._row_save_refused(card.name, lambda doc: doc.set("adjustments", []))
		with self.assertRaises(frappe.LinkExistsError):
			frappe.delete_doc("Card Monthly Card", card.name)
		self.assertTrue(frappe.db.exists("Card Monthly Card Adjustment", row_name))
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Posted")

	def test_a_paid_cash_row_is_protected_on_the_api_save_paths(self):
		"""H2: frappe.client.save (PUT /api/resource) and frappe.client.set_value on the row, as a Card Manager who may
		edit the card, are refused like a form save."""
		from frappe.client import save, set_value

		card, _name, _entry = self._posted()
		row = self._cash_row(card.name)
		frappe.set_user(self.manager)
		doc = frappe.get_doc("Card Monthly Card", card.name).as_dict()
		for adj in doc["adjustments"]:
			if adj["name"] == row.name:
				adj["is_cash_disbursement"] = 0
		with self.assertRaises(frappe.ValidationError):
			save(frappe.as_json(doc))
		with self.assertRaises(frappe.ValidationError):
			set_value("Card Monthly Card Adjustment", row.name, "is_cash_disbursement", 0)
		with self.assertRaises(frappe.ValidationError):
			set_value("Card Monthly Card Adjustment", row.name, {"amount": 1})
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(
			"Card Monthly Card Adjustment", row.name, ["is_cash_disbursement", "amount"]
		)
		self.assertEqual((cint(stored[0]), flt(stored[1], 2)), (1, 300.0))

	def test_a_paid_cash_row_keeps_its_description_and_date_editable(self):
		"""H2 is narrow: the description and the date of the row do not change what is paid, so they stay editable."""
		card, _name, _entry = self._posted()
		doc = frappe.get_doc("Card Monthly Card", card.name)
		row = next(r for r in doc.adjustments if cint(r.is_cash_disbursement))
		row.description = "Diesel paid on behalf of the supplier (receipt 7)"
		row.adjustment_date = "2026-09-02"
		doc.save()
		self.assertEqual(
			str(frappe.db.get_value("Card Monthly Card Adjustment", row.name, "adjustment_date")),
			"2026-09-02",
		)

	def test_a_pending_payment_locks_its_row_until_it_is_deleted(self):
		"""H2: a Pending payment fixes its row too. The authorized way to change the row is to delete the pending
		payment first; then the row is an ordinary row again."""
		card, row = self._card_with_cash_row(amount=300)
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")

		def change_amount(doc):
			doc.adjustments[0].amount = 200

		self._row_save_refused(card.name, change_amount)
		frappe.delete_doc(DOCTYPE, name)
		doc = frappe.get_doc("Card Monthly Card", card.name)
		change_amount(doc)
		doc.save()
		self.assertEqual(
			flt(frappe.db.get_value("Card Monthly Card Adjustment", row.name, "amount"), 2), 200.0
		)

	def test_a_cancelled_payment_frees_its_row(self):
		"""H2 keeps the correction path: after the payment is cancelled (its entry cancelled in ERPNext) the row may be
		corrected, then replaced or turned into an ordinary deduction."""
		card, name = self._cancelled_posted()
		doc = frappe.get_doc("Card Monthly Card", card.name)
		row = next(r for r in doc.adjustments if cint(r.is_cash_disbursement))
		row.is_cash_disbursement = 0
		row.cash_account = None
		doc.save()
		self.assertEqual(
			cint(frappe.db.get_value("Card Monthly Card Adjustment", row.name, "is_cash_disbursement")), 0
		)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Cancelled")

	def test_the_invoice_builder_refuses_a_paid_row_that_is_not_marked_cash(self):
		"""H2, old or damaged data: a row of a live payment that lost its Cash paid flag outside the card's save (raw
		write) is never invoiced; the invoice builder refuses the card instead of deducting the amount a second time."""
		from card.gl.posting import _card_lines, _types_map

		card, name, _entry = self._posted()
		row = self._cash_row(card.name)
		frappe.db.set_value(
			"Card Monthly Card Adjustment", row.name, "is_cash_disbursement", 0, update_modified=False
		)
		settings_row = frappe._dict(rental_item=None, equipment_rental_expense_account=None)
		with self.assertRaises(frappe.ValidationError) as ctx:
			_card_lines(card.name, "Supplier", settings_row, _types_map(card.company))
		self.assertIn(name, str(ctx.exception))

	# ---------------------------------------------------------------- FR-170 final audit M1: the cancellation record

	def test_the_cancellation_record_cannot_be_rewritten_by_a_save(self):
		"""M1: the cancellation reason and its actors are written only by their server actions; a save of a Posted,
		Cancellation Requested or Cancelled payment cannot set or rewrite them."""
		from card.cash_disbursement import request_cancellation

		_card, name, entry = self._posted()
		frappe.set_user(self.manager)
		doc = frappe.get_doc(DOCTYPE, name)
		doc.cancellation_reason = "Invented reason"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		request_cancellation(name, "Wrong receipt")
		for field, value in (
			("cancellation_reason", "Rewritten reason"),
			("cancellation_requested_by", "Administrator"),
			("cancelled_by", self.manager),
		):
			doc = frappe.get_doc(DOCTYPE, name)
			doc.set(field, value)
			with self.assertRaises(frappe.ValidationError):
				doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "cancellation_reason"), "Wrong receipt")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "cancellation_requested_by"), self.manager)
		frappe.get_doc("Journal Entry", entry).cancel()
		doc = frappe.get_doc(DOCTYPE, name)
		doc.cancelled_on = "2026-09-30 10:00:00"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	# ---------------------------------------------------------------- FR-170 final audit M2: a cancelled card

	def _cancel_card(self, card_name):
		doc = frappe.get_doc("Card Monthly Card", card_name)
		if doc.docstatus == 0:
			doc.submit()
			doc.reload()
		with_reason(doc).cancel()

	def test_a_payment_of_a_cancelled_card_is_not_approved(self):
		card, row = self._card_with_cash_row()
		name = request_cash_disbursement(card.name, row.name, "2026-09-10", "Receipt R-1")
		self._cancel_card(card.name)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError) as ctx:
			approve_cash_disbursement(name)
		frappe.set_user("Administrator")
		self.assertIn("is cancelled", str(ctx.exception))
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Pending")

	def test_a_payment_of_a_cancelled_card_is_not_queued(self):
		card, name = self._approved()
		self._cancel_card(card.name)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			queue_posting(name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "status"), "Approved")

	def test_a_queued_payment_of_a_card_cancelled_before_execution_fails_without_an_entry(self):
		"""Cancellation between queueing and execution: the executor checks the card immediately before the entry, marks
		the payment Posting Failed with the reason, creates no entry, and the payment cannot be queued again."""
		card, name = self._approved()
		frappe.set_user(self.manager)
		queue_posting(name)
		frappe.set_user("Administrator")
		self._cancel_card(card.name)
		frappe.set_user(self.service)
		results = frappe.call("card.cash_disbursement.run_posting_queue", limit=5)
		frappe.set_user("Administrator")
		self.assertEqual([r["status"] for r in results], ["Posting Failed"])
		self.assertIn("is cancelled", results[0]["error"])
		self.assertIsNone(frappe.db.get_value(DOCTYPE, name, "journal_entry"))
		self.assertEqual(self._journal_entries_for(name), [])
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			queue_posting(name)
		frappe.set_user("Administrator")

	def test_a_posted_payment_stays_posted_when_its_card_is_cancelled(self):
		"""The accounting evidence is kept: cancelling the card neither cancels nor changes the posted payment or its
		Journal Entry (the correction stays the controlled cancellation in ERPNext)."""
		card, name, entry = self._posted()
		self._cancel_card(card.name)
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, ["status", "journal_entry"]), ("Posted", entry))
		self.assertEqual(frappe.db.get_value("Journal Entry", entry, "docstatus"), 1)
