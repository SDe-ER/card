# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2, shared components (owner decisions 2026-11-17): the beneficiary is verified only for a
supplier-billed card whose supplier is the equipment's current owner; the transaction identity is stable
and changes with any economic difference; the payment date cannot be future or in a closed period."""

from datetime import date
from unittest import TestCase

import frappe

from card.constants import DIR_INTERNAL, DIR_RENTED_IN, DIR_RENTED_OUT
from card.settlement import (
	BENEFICIARY_SUPPLIER,
	cash_transaction_key,
	posting_block_reason,
	resolve_beneficiary,
	supplier_change_refused,
	validate_payment_date,
)


class TestBeneficiary(TestCase):
	def test_supplier_of_a_rented_in_card_is_the_verified_beneficiary(self):
		self.assertEqual(resolve_beneficiary(DIR_RENTED_IN, "Owner Co"), (BENEFICIARY_SUPPLIER, "Owner Co"))

	def test_historical_supplier_is_kept_as_stored_after_an_owner_change(self):
		# the card's stored supplier is the identity of its period; the equipment's current owner is not an input
		self.assertEqual(resolve_beneficiary(DIR_RENTED_IN, "Old Owner"), (BENEFICIARY_SUPPLIER, "Old Owner"))

	def test_customer_billed_card_has_no_supplier_beneficiary(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_beneficiary(DIR_RENTED_OUT, "Owner Co")
		with self.assertRaises(frappe.ValidationError):
			resolve_beneficiary(DIR_INTERNAL, "Owner Co")

	def test_card_without_supplier_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			resolve_beneficiary(DIR_RENTED_IN, None)


class TestPostingGate(TestCase):
	def test_supplier_beneficiary_is_not_blocked(self):
		self.assertIsNone(posting_block_reason(BENEFICIARY_SUPPLIER))

	def test_unverified_beneficiary_types_are_blocked(self):
		for kind in ("Shareholder", "Partnership", "Partner current account", "Other"):
			self.assertIsNotNone(posting_block_reason(kind), kind)


class TestTransactionKey(TestCase):
	def _key(self, **kw):
		args = {
			"card_name": "EOMC-1",
			"row_name": "r1",
			"amount": 300,
			"payment_date": "2026-11-10",
			"cash_account": "1120",
		}
		args.update(kw)
		return cash_transaction_key(**args)

	def test_same_event_gives_the_same_key(self):
		self.assertEqual(self._key(), self._key())

	def test_any_economic_difference_gives_a_different_key(self):
		base = self._key()
		self.assertNotEqual(base, self._key(amount=301))
		self.assertNotEqual(base, self._key(payment_date="2026-11-11"))
		self.assertNotEqual(base, self._key(cash_account="1110"))
		self.assertNotEqual(base, self._key(row_name="r2"))
		self.assertNotEqual(base, self._key(card_name="EOMC-2"))

	def test_key_is_a_sha256_hex_digest(self):
		self.assertEqual(len(self._key()), 64)


class TestPaymentDate(TestCase):
	def test_a_past_date_in_an_open_period_is_accepted(self):
		self.assertEqual(validate_payment_date("2026-11-10", date(2026, 11, 17), False), date(2026, 11, 10))

	def test_a_future_date_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			validate_payment_date("2026-11-18", date(2026, 11, 17), False)

	def test_a_closed_period_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			validate_payment_date("2026-10-10", date(2026, 11, 17), True)

	def test_a_missing_date_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			validate_payment_date(None, date(2026, 11, 17), False)


class TestSupplierChangeGuard(TestCase):
	"""FR-171 security review: only a correction role may set or change a card's supplier on the server."""

	def test_new_card_may_take_the_equipment_owner(self):
		self.assertFalse(supplier_change_refused(["Card User"], None, "Owner Co", "Owner Co"))

	def test_new_card_with_another_supplier_is_refused_for_a_non_manager(self):
		self.assertTrue(supplier_change_refused(["Card User"], None, "Other Co", "Owner Co"))

	def test_changing_a_stored_supplier_is_refused_for_a_non_manager(self):
		self.assertTrue(supplier_change_refused(["Card User"], "Owner Co", "Other Co", "Owner Co"))

	def test_unchanged_stored_supplier_is_allowed(self):
		self.assertFalse(supplier_change_refused(["Card User"], "Old Owner", "Old Owner", "New Owner"))

	def test_card_manager_may_correct_a_supplier(self):
		self.assertFalse(supplier_change_refused(["Card Manager"], "Owner Co", "Other Co", "Owner Co"))
		self.assertFalse(supplier_change_refused(["System Manager"], None, "Other Co", "Owner Co"))
