# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Shared settlement components for owner-paid cash expenses (FR-170 step 2).

Pure functions, no database writes. They serve every later stage:

- the beneficiary of a card's cash expense, resolved only where the relationship is verified;
- the stable identity of one cash transaction (exactly-once posting);
- the payment-date rule.

Posting is allowed only for the beneficiary types whose accounting treatment is verified. The
partner and joint-ownership treatments are assumptions A1 to A5 of docs/governance/SETTLEMENT-PARTY-DESIGN.md,
so they are blocked until the accountant validates them.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import getdate

from card.constants import SUPPLIER_BILLING_DIRECTIONS

BENEFICIARY_SUPPLIER = "Supplier"
# the verified case: a rented-in or sub-rental machine whose owner is its Supplier (Lessor / Owner)
VERIFIED_BENEFICIARY_TYPES = (BENEFICIARY_SUPPLIER,)


def resolve_beneficiary(card_direction, card_supplier):
	"""The financial beneficiary of an owner-paid cash expense on this card: the Supplier the card keeps.

	The card keeps the beneficiary it was created with (its supplier, a one-time default from the equipment's
	current owner). It is not compared with the equipment's current owner, because ownership or management can
	change after the operating period; the stored value is the identity of that period (FR-171 review).
	Verified only for a supplier-billed card that names a Supplier."""
	if card_direction not in SUPPLIER_BILLING_DIRECTIONS:
		frappe.throw(_("The card is not supplier-billed, so no supplier beneficiary can be verified."))
	if not card_supplier:
		frappe.throw(_("The card has no supplier, so the beneficiary cannot be verified."))
	return BENEFICIARY_SUPPLIER, card_supplier


SUPPLIER_CORRECTION_ROLES = ("Card Manager", "System Manager")


def supplier_change_refused(roles, stored_supplier, new_supplier, equipment_supplier):
	"""True when a save would set the card's historical beneficiary without a correction role.

	The field is read only on the Desk form, but the API writes any field the user may write, so the server
	checks it here (FR-171 security review). A new card may take the equipment's current owner as its supplier;
	any other value, and any change of a stored supplier, needs Card Manager or System Manager (the documented
	correction of an incorrect assignment)."""
	if set(roles or ()) & set(SUPPLIER_CORRECTION_ROLES):
		return False
	if stored_supplier is None:
		return bool(new_supplier) and new_supplier != equipment_supplier
	return new_supplier != stored_supplier


def posting_block_reason(beneficiary_type):
	"""None when the beneficiary type is verified for posting; otherwise the reason to block it."""
	if beneficiary_type in VERIFIED_BENEFICIARY_TYPES:
		return None
	return _("The accounting treatment of this beneficiary type is not verified (assumptions A1 to A5).")


def cash_transaction_key(card_name, row_name, amount, payment_date, cash_account):
	"""The stable identity of one owner-paid cash transaction: a SHA-256 over the source card, the source
	row, the amount, the payment date and the cash account. The same economic event always gets the same key,
	so a retry cannot post it twice; a changed payment is a different key and needs its own approval."""
	payload = {
		"card": card_name,
		"row": row_name,
		"amount": f"{float(amount):.2f}",
		"payment_date": str(getdate(payment_date)),
		"cash_account": cash_account,
	}
	return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def validate_payment_date(payment_date, today, period_closed):
	"""The actual payment date. It cannot be in the future, and it cannot fall in a closed period."""
	if not payment_date:
		frappe.throw(_("Enter the payment date of the cash expense."))
	paid = getdate(payment_date)
	if paid > getdate(today):
		frappe.throw(_("The payment date {0} cannot be in the future.").format(paid))
	if period_closed:
		frappe.throw(
			_("The period of payment date {0} is closed; the payment cannot be posted into it.").format(paid)
		)
	return paid
