# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Step 1 of the owner-paid cash expense feature (Owner, 2026-11-16): the cash account is validated by its
actual Account Type, and an owner-paid cash row is refused until its approval and Journal Entry exist.
Pure validators with the account read patched, so no site data is needed."""

from unittest import TestCase
from unittest.mock import patch

import frappe

from card.adjustments import refuse_cash_disbursement_until_enabled, validate_cash_account

COMPANY = "Test Company"


def _account(**overrides):
	row = {"company": COMPANY, "is_group": 0, "disabled": 0, "account_type": "Cash"}
	row.update(overrides)
	return frappe._dict(row)


class TestCashAccountValidation(TestCase):
	def _validate(self, account, row):
		with patch("frappe.db.get_value", return_value=row):
			validate_cash_account(account, COMPANY)

	def test_petty_cash_account_is_accepted(self):
		self._validate("1120 - Petty Cash", _account())

	def test_cash_account_is_accepted(self):
		self._validate("1110 - Cash", _account())

	def test_bank_account_is_refused_even_with_a_cash_looking_name(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate("1110 - Cash at bank", _account(account_type="Bank"))

	def test_account_of_another_company_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate("1110 - Cash", _account(company="Other Company"))

	def test_group_account_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate("1100 - Cash", _account(is_group=1))

	def test_disabled_account_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._validate("1110 - Cash", _account(disabled=1))

	def test_missing_account_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			validate_cash_account("", COMPANY)
		with self.assertRaises(frappe.ValidationError):
			self._validate("9999 - Nope", None)


class TestCashDisbursementGate(TestCase):
	def test_an_owner_paid_cash_row_is_refused_until_it_is_enabled(self):
		with self.assertRaises(frappe.ValidationError):
			refuse_cash_disbursement_until_enabled(frappe._dict(is_cash_disbursement=1, description="diesel"))

	def test_an_ordinary_row_passes_the_gate(self):
		refuse_cash_disbursement_until_enabled(frappe._dict(is_cash_disbursement=0, description="diesel"))
		refuse_cash_disbursement_until_enabled(frappe._dict(description="diesel"))
