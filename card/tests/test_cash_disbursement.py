# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 1 (owner decisions 2026-11-16): an owner-paid cash row is validated when the Draft is saved,
it is excluded from the card's totals, and the card cannot be submitted while it is pending. Pure checks with
the account read patched, so no site data is needed."""

from unittest import TestCase
from unittest.mock import patch

import frappe

from card.adjustments import validate_cash_account, validate_cash_row
from card.constants import DIR_INTERNAL, DIR_RENTED_IN

COMPANY = "Test Company"


def _account(**overrides):
	row = {"company": COMPANY, "is_group": 0, "disabled": 0, "account_type": "Cash"}
	row.update(overrides)
	return frappe._dict(row)


def _cash_row(account="1120 - Petty Cash", **overrides):
	row = {"is_cash_disbursement": 1, "cash_account": account, "description": "diesel"}
	row.update(overrides)
	return frappe._dict(row)


class TestCashAccountValidation(TestCase):
	def _validate(self, account, row):
		with patch("frappe.db.get_value", return_value=row):
			validate_cash_account(account, COMPANY)

	def test_petty_cash_account_1120_is_accepted(self):
		self._validate("1120 - Petty Cash", _account())

	def test_cash_account_1110_is_accepted(self):
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


class TestCashRowSaveValidation(TestCase):
	"""A Draft with a valid cash row saves; an invalid cash account or a non-supplier card does not."""

	def test_ordinary_row_is_not_a_cash_row_and_is_not_checked(self):
		self.assertFalse(validate_cash_row(frappe._dict(is_cash_disbursement=0), COMPANY, None, DIR_INTERNAL))

	def test_valid_cash_row_on_a_supplier_card_saves(self):
		with patch("frappe.db.get_value", return_value=_account()):
			self.assertTrue(validate_cash_row(_cash_row(), COMPANY, "Owner Supplier", DIR_RENTED_IN))

	def test_invalid_cash_account_fails_the_save(self):
		with patch("frappe.db.get_value", return_value=_account(account_type="Bank")):
			with self.assertRaises(frappe.ValidationError):
				validate_cash_row(_cash_row("1210 - Bank"), COMPANY, "Owner Supplier", DIR_RENTED_IN)

	def test_cash_row_without_the_owner_supplier_fails_the_save(self):
		with patch("frappe.db.get_value", return_value=_account()):
			with self.assertRaises(frappe.ValidationError):
				validate_cash_row(_cash_row(), COMPANY, None, DIR_RENTED_IN)
			with self.assertRaises(frappe.ValidationError):
				validate_cash_row(_cash_row(), COMPANY, "Owner Supplier", DIR_INTERNAL)
