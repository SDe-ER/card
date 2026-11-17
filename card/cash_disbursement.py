# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2: the cash-disbursement approval lifecycle and its Journal Entry (verified Suppliers only).

Lifecycle of one "Card Cash Disbursement" record: Pending (requested) -> Approved (by a Card Manager other
than the requester) -> Posted (one submitted Journal Entry, linked back). The Journal Entry debits the
Supplier's payable account for the card's historical Supplier and credits the approved Cash account.

Exactly-once: the transaction key is unique in the database, the Journal Entry link is unique, and posting
runs under a row lock and returns the existing Journal Entry when the record is already Posted. A failed
submit rolls the whole transaction back, so the record stays Approved and a retry is safe.

Only a supplier-billed card whose stored Supplier is the beneficiary is accepted (settlement.resolve_beneficiary).
Other beneficiary types are not posted (settlement.posting_block_reason).
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, nowdate

from card.adjustments import validate_cash_account
from card.settlement import posting_block_reason, resolve_beneficiary, validate_payment_date

DOCTYPE = "Card Cash Disbursement"
APPROVAL_ROLES = ("Card Manager", "System Manager")


def _check_role(roles, allowed, message):
	if not set(roles) & set(allowed):
		frappe.throw(message)


@frappe.whitelist(methods=["POST"])
def request_cash_disbursement(card, row, payment_date, evidence):
	"""Record a Pending cash payment for a flagged row of a Draft card (the requester is the record owner)."""
	doc = frappe.get_doc("Card Monthly Card", card)
	doc.check_permission("read")
	if doc.docstatus != 0:
		frappe.throw(_("A cash payment is requested on a Draft card only."))
	source = next((r for r in doc.adjustments or [] if r.name == row), None)
	if not source or not cint(source.is_cash_disbursement):
		frappe.throw(_("The row {0} is not a cash payment on card {1}.").format(row, card))
	if frappe.db.exists(DOCTYPE, {"card": card, "adjustment_row": row}):
		frappe.throw(_("A cash payment is already requested for row {0} of card {1}.").format(row, card))
	beneficiary_type, supplier = resolve_beneficiary(doc.card_direction, doc.supplier)
	reason = posting_block_reason(beneficiary_type)
	if reason:
		frappe.throw(reason)
	validate_payment_date(payment_date, nowdate(), False)
	record = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"company": doc.company,
			"supplier": supplier,
			"card": card,
			"adjustment_row": row,
			"equipment": doc.equipment,
			"project": doc.project,
			"amount": source.amount,
			"payment_date": payment_date,
			"cash_account": source.cash_account,
			"evidence": evidence,
			"status": "Pending",
		}
	).insert()
	return record.name


@frappe.whitelist(methods=["POST"])
def approve_cash_disbursement(name):
	"""Explicit approval by a Card Manager who is not the requester."""
	roles = frappe.get_roles()
	_check_role(roles, APPROVAL_ROLES, _("Only a Card Manager can approve a cash payment."))
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.owner == frappe.session.user:
		frappe.throw(_("The requester cannot approve their own cash payment."))
	if doc.status != "Pending":
		frappe.throw(_("Only a Pending cash payment can be approved; {0} is {1}.").format(name, doc.status))
	doc.status = "Approved"
	doc.approved_by = frappe.session.user
	doc.approved_on = now_datetime()
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def post_cash_disbursement(name):
	"""Post the approved cash payment as one submitted Journal Entry; return it (the same one on a retry)."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can post a cash payment."))
	row = frappe.db.get_value(DOCTYPE, name, ["status", "journal_entry"], as_dict=True, for_update=True)
	if not row:
		frappe.throw(_("The cash payment {0} does not exist.").format(name))
	if row.status == "Posted":
		return row.journal_entry
	if row.status != "Approved":
		frappe.throw(_("Only an approved cash payment can be posted; {0} is {1}.").format(name, row.status))

	doc = frappe.get_doc(DOCTYPE, name)
	from erpnext.accounts.party import get_party_account

	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": doc.payment_date,
			"user_remark": "Card cash payment {0} ({1}) for card {2}, row {3}, on behalf of {4}".format(
				doc.name, doc.transaction_key, doc.card, doc.adjustment_row, doc.supplier
			),
			"accounts": [
				{
					"account": get_party_account("Supplier", doc.supplier, doc.company),
					"party_type": "Supplier",
					"party": doc.supplier,
					"debit_in_account_currency": doc.amount,
					"project": doc.project,
				},
				{"account": doc.cash_account, "credit_in_account_currency": doc.amount},
			],
		}
	)
	# ignore_permissions: the posting is an explicit, role-checked service action of this record (above), and
	# the entry's accounts are fixed by the record; the requester's own Journal Entry rights are not used.
	entry.insert(ignore_permissions=True)
	entry.submit()
	frappe.db.set_value(
		DOCTYPE,
		name,
		{"status": "Posted", "journal_entry": entry.name, "posted_on": now_datetime()},
		update_modified=False,
	)
	return entry.name
