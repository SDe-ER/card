# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 1, database integration (Owner, 2026-11-16): a Draft Card Monthly Card with a valid
owner-paid cash row saves and edits; the row stays visible but is excluded from the card's totals and
invoice lines; an invalid cash account fails the save; an ordinary card is unaffected; a card with a
pending cash row cannot be submitted. Real rows, rolled back per test."""

import frappe

from card.constants import DIR_RENTED_IN
from card.tests.test_s3_config import _AdjBase


def _cash_account(company):
	"""An enabled leaf Cash account of the company; created under the company's Asset group if none exists."""
	acc = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Cash", "is_group": 0, "disabled": 0},
		"name",
	)
	if acc:
		return acc
	parent = frappe.db.get_value("Account", {"company": company, "root_type": "Asset", "is_group": 1}, "name")
	doc = frappe.get_doc(
		{
			"doctype": "Account",
			"account_name": "Test Owner Cash " + frappe.generate_hash(length=6),
			"parent_account": parent,
			"company": company,
			"root_type": "Asset",
			"account_type": "Cash",
			"is_group": 0,
		}
	).insert(ignore_permissions=True)
	return doc.name


class TestCashRowDraftIntegration(_AdjBase):
	def setUp(self):
		super().setUp()
		self._clear_types()
		self.cash = _cash_account(self.company)
		self.cash_row = {
			"is_cash_disbursement": 1,
			"cash_account": self.cash,
			"adjustment_type": "خصم",
			"description": "Diesel paid on behalf of the owner",
			"amount": 300,
			"side": "Supplier",
		}

	def test_draft_with_valid_cash_row_saves(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._typed_card(eq, [dict(self.cash_row)])
		self.assertEqual(card.docstatus, 0)
		self.assertEqual(len(card.adjustments), 1)
		self.assertEqual(card.adjustments[0].is_cash_disbursement, 1)
		self.assertEqual(card.adjustments[0].cash_account, self.cash)

	def test_draft_with_cash_row_can_be_edited_and_saved_again(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._typed_card(eq, [dict(self.cash_row)])
		card.adjustments[0].description = "Diesel paid, corrected"
		card.save()
		card.reload()
		self.assertEqual(card.adjustments[0].description, "Diesel paid, corrected")
		self.assertEqual(card.adjustments[0].is_cash_disbursement, 1)

	def test_cash_row_is_excluded_from_the_card_totals(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._typed_card(eq, [dict(self.cash_row)])
		self.assertEqual(card.total_deductions, 0)
		self.assertEqual(card.total_additions, 0)
		self.assertEqual(card.net_amount, card.amount)

	def test_invalid_cash_account_fails_the_draft_save(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		bank = frappe.db.get_value(
			"Account", {"company": self.company, "account_type": "Bank", "is_group": 0}, "name"
		)
		if not bank:
			self.skipTest("no bank account in the test company")
		bad = dict(self.cash_row, cash_account=bank)
		with self.assertRaises(frappe.ValidationError):
			self._typed_card(eq, [bad])

	def test_card_with_a_pending_cash_row_cannot_be_submitted(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._typed_card(eq, [dict(self.cash_row)])
		with self.assertRaises(frappe.ValidationError):
			card.submit()
		card.reload()
		self.assertEqual(card.docstatus, 0)

	def test_ordinary_card_keeps_its_deduction(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		ordinary = {
			"adjustment_type": "خصم",
			"description": "Late delivery",
			"amount": 120,
			"side": "Supplier",
		}
		card = self._typed_card(eq, [ordinary])
		self.assertEqual(card.total_deductions, 120)
		self.assertEqual(card.adjustments[0].is_cash_disbursement, 0)
