# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2 database integration (owner decisions 2026-11-17): a cash payment for a verified external
Supplier is requested, approved by a Card Manager other than the requester, and posted once as a submitted
Journal Entry (Dr the Supplier payable, Cr the Cash account). Retries return the same entry; a duplicate key
is refused by the database; a card submits after its payment is posted. Real rows, rolled back per test."""

import frappe

from card.cash_disbursement import (
	approve_cash_disbursement,
	post_cash_disbursement,
	request_cash_disbursement,
)
from card.constants import DIR_RENTED_IN
from card.tests.test_cash_disbursement_db import _cash_account
from card.tests.test_s3_config import _AdjBase


class TestCashDisbursementPosting(_AdjBase):
	def setUp(self):
		super().setUp()
		self._clear_types()
		self.cash = _cash_account(self.company)
		self.manager = self._user("Card Manager")
		self.card_user = self._user("Card User")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

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

	def _user(self, role):
		email = "ccd-%s-%s@example.com" % (role.lower().replace(" ", "-"), frappe.generate_hash(length=6))
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

	def _request(self, card, row, payment_date="2026-09-10"):
		return request_cash_disbursement(card.name, row.name, payment_date, "Receipt R-1")

	def _journal_entries_for(self, record_name):
		return frappe.get_all(
			"Journal Entry",
			filters={"user_remark": ["like", "%" + record_name + "%"], "docstatus": 1},
			pluck="name",
		)

	def test_request_creates_a_pending_record_with_the_historical_supplier(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		record = frappe.get_doc("Card Cash Disbursement", name)
		self.assertEqual(record.status, "Pending")
		self.assertEqual(record.supplier, card.supplier)
		self.assertEqual(len(record.transaction_key), 64)

	def test_a_second_request_for_the_same_row_is_refused(self):
		card, row = self._card_with_cash_row()
		self._request(card, row)
		with self.assertRaises(frappe.ValidationError):
			self._request(card, row)

	def test_posting_before_approval_is_refused(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		frappe.set_user(self.manager)
		with self.assertRaises(frappe.ValidationError):
			post_cash_disbursement(name)

	def test_the_requester_cannot_approve_their_own_payment(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		with self.assertRaises(frappe.ValidationError):
			approve_cash_disbursement(name)  # Administrator requested it

	def test_a_card_user_cannot_approve_or_post(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		frappe.set_user(self.card_user)
		with self.assertRaises(frappe.ValidationError):
			approve_cash_disbursement(name)
		frappe.set_user("Administrator")

	def test_manager_approval_then_posting_creates_one_submitted_journal_entry(self):
		card, row = self._card_with_cash_row(amount=300)
		name = self._request(card, row)
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		entry_name = post_cash_disbursement(name)
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

		record = frappe.get_doc("Card Cash Disbursement", name)
		self.assertEqual(record.status, "Posted")
		self.assertEqual(record.journal_entry, entry_name)
		self.assertEqual(self._journal_entries_for(name), [entry_name])

	def test_retry_returns_the_same_entry_and_creates_no_second_one(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		first = post_cash_disbursement(name)
		second = post_cash_disbursement(name)
		frappe.set_user("Administrator")
		self.assertEqual(first, second)
		self.assertEqual(self._journal_entries_for(name), [first])

	def test_the_database_refuses_a_duplicate_transaction_key(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		original = frappe.get_doc("Card Cash Disbursement", name)
		with self.assertRaises(frappe.DuplicateEntryError):
			frappe.get_doc(
				{
					"doctype": "Card Cash Disbursement",
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
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		record = frappe.get_doc("Card Cash Disbursement", name)
		record.amount = 999
		with self.assertRaises(frappe.ValidationError):
			record.save()
		frappe.set_user("Administrator")

	def test_a_card_submits_only_after_its_cash_payment_is_posted(self):
		card, row = self._card_with_cash_row()
		name = self._request(card, row)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Card Monthly Card", card.name).submit()
		frappe.set_user(self.manager)
		approve_cash_disbursement(name)
		post_cash_disbursement(name)
		frappe.set_user("Administrator")
		submitted = frappe.get_doc("Card Monthly Card", card.name)
		submitted.submit()
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "docstatus"), 1)
