# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-170 step 2: the cash-disbursement approval lifecycle and its accounting execution (verified Suppliers only).

Two separate parts, by design (owner decision 2026-11-17):

1. User-facing (runs under the real user's identity): request, approve, and queue_posting. queue_posting only
   claims an Approved record (Approved -> Posting, under a row lock). It creates no accounting entry.
2. Accounting execution: execute_posting. It creates one submitted Journal Entry (Dr the Supplier payable, Cr the
   validated Cash account) and links it back. It is run by an executor under a dedicated service identity that
   holds only the permissions the entry needs (see SERVICE_ROLE). This code never changes the session user, so the
   identity used is the one the executor runs as, and it is verified by the tests.

Frappe's background queue is not used for execution: enqueue records the requesting session as the job user, so a
queued job would run as the requester, not as the service identity (verified in frappe/utils/background_jobs.py,
version-16: enqueue sets "user": frappe.session.user; execute_job calls frappe.set_user(user)).

Exactly-once: the transaction key is unique in the database, the Journal Entry link is unique, the claim and the
posting run under a row lock, and a retry or a recovered run finds the entry by its remark before creating one.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime, nowdate

from card.settlement import posting_block_reason, resolve_beneficiary, validate_payment_date

DOCTYPE = "Card Cash Disbursement"
APPROVAL_ROLES = ("Card Manager", "System Manager")
# the dedicated identity the executor runs as: no broad accounting role, only what one entry needs
SERVICE_ROLE = "Card Cash Posting Service"


def _check_role(roles, allowed, message):
	if not set(roles) & set(allowed):
		frappe.throw(message)


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


def approve_cash_disbursement(name):
	"""Explicit approval by a Card Manager who is not the requester."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can approve a cash payment."))
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


def queue_posting(name):
	"""Claim an Approved cash payment for the accounting executor (Approved -> Posting, under a row lock).
	Creates no accounting entry. Returns the Journal Entry when the payment is already Posted."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can post a cash payment."))
	row = frappe.db.get_value(DOCTYPE, name, ["status", "journal_entry"], as_dict=True, for_update=True)
	if not row:
		frappe.throw(_("The cash payment {0} does not exist.").format(name))
	if row.status == "Posted":
		return row.journal_entry
	if row.status != "Approved":
		frappe.throw(
			_("Only an approved cash payment can be queued for posting; {0} is {1}.").format(name, row.status)
		)
	frappe.db.set_value(
		DOCTYPE,
		name,
		{
			"status": "Posting",
			"posting_claimed_by": frappe.session.user,
			"posting_claimed_on": now_datetime(),
		},
		update_modified=False,
	)
	return name


def _entry_for(name):
	"""The Journal Entry (not cancelled) a payment created, found by its remark: the recovery key."""
	return frappe.db.get_value(
		"Journal Entry",
		{"user_remark": ["like", "Card cash payment {0} (%".format(name)], "docstatus": ["!=", 2]},
		"name",
	)


def execute_posting(name):
	"""Accounting execution. Run by the executor under the service identity. Creates one submitted Journal Entry,
	or links the one an interrupted earlier run already created. Returns the entry name."""
	row = frappe.db.get_value(DOCTYPE, name, ["status", "journal_entry"], as_dict=True, for_update=True)
	if not row:
		frappe.throw(_("The cash payment {0} does not exist.").format(name))
	if row.status == "Posted":
		return row.journal_entry
	if row.status != "Posting":
		frappe.throw(_("Only a queued cash payment can be executed; {0} is {1}.").format(name, row.status))

	entry_name = _entry_for(name)
	if not entry_name:
		from erpnext.accounts.party import get_party_account

		doc = frappe.get_doc(DOCTYPE, name)
		entry = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"voucher_type": "Journal Entry",
				"company": doc.company,
				"posting_date": doc.payment_date,
				"user_remark": "Card cash payment {0} ({1}) for card {2}, row {3}, on behalf of {4}; requested by {5}, approved by {6}".format(
					doc.name,
					doc.transaction_key,
					doc.card,
					doc.adjustment_row,
					doc.supplier,
					doc.owner,
					doc.approved_by,
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
		entry.insert()
		entry.submit()
		entry_name = entry.name
	frappe.db.set_value(
		DOCTYPE,
		name,
		{"status": "Posted", "journal_entry": entry_name, "posted_on": now_datetime()},
		update_modified=False,
	)
	return entry_name


def _has_active_allocations(entry_name):
	"""True while the Journal Entry is still allocated against another document (an invoice or a payment
	reconciliation). Source: Payment Ledger Entry, fields voucher_no, against_voucher_no and delinked (verified in
	erpnext version-16). Such an entry is not cancelled here: the allocation is resolved in ERPNext first."""
	return bool(
		frappe.db.exists(
			"Payment Ledger Entry",
			{"delinked": 0, "voucher_no": entry_name, "against_voucher_no": ["!=", entry_name]},
		)
		or frappe.db.exists(
			"Payment Ledger Entry",
			{"delinked": 0, "against_voucher_no": entry_name, "voucher_no": ["!=", entry_name]},
		)
	)


def _refuse_if_allocated(entry_name):
	if _has_active_allocations(entry_name):
		frappe.throw(
			_(
				"Journal entry {0} still has active allocations. Resolve them in ERPNext (unreconcile or unlink) before cancelling it."
			).format(entry_name)
		)


@frappe.whitelist(methods=["POST"])
def request_cancellation(name, reason):
	"""Record the reason for cancelling a posted cash payment. ERPNext's own Journal Entry cancellation (a human
	action) is then allowed; without this request the linked entry cannot be cancelled. The payment is not
	reversed, reposted or replaced here, and a replacement needs its own request and approval."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can request a cancellation."))
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Give the reason for the cancellation."))
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.status != "Posted":
		frappe.throw(_("Only a posted cash payment can be cancelled; {0} is {1}.").format(name, doc.status))
	_refuse_if_allocated(doc.journal_entry)
	doc.status = "Cancellation Requested"
	doc.cancellation_reason = reason
	doc.cancellation_requested_by = frappe.session.user
	doc.cancellation_requested_on = now_datetime()
	doc.save()
	return doc.name


def before_journal_entry_cancel(doc, method=None):
	"""A cash-payment Journal Entry is cancelled only after its payment has a recorded cancellation request.
	Other Journal Entries pass through untouched."""
	row = frappe.db.get_value(DOCTYPE, {"journal_entry": doc.name}, ["name", "status"], as_dict=True)
	if not row:
		return
	_refuse_if_allocated(doc.name)
	if row.status != "Cancellation Requested":
		frappe.throw(
			_(
				"Journal entry {0} pays cash payment {1}. Request its cancellation with a reason first; the payment is then marked Cancelled."
			).format(doc.name, row.name)
		)


def on_journal_entry_cancel(doc, method=None):
	"""After ERPNext cancels the entry: mark the payment Cancelled with the actor and the time. The entry stays
	linked (audit), and a Cancelled payment can never be queued, executed or posted again."""
	name = frappe.db.get_value(DOCTYPE, {"journal_entry": doc.name}, "name")
	if not name:
		return
	frappe.db.set_value(
		DOCTYPE,
		name,
		{"status": "Cancelled", "cancelled_by": frappe.session.user, "cancelled_on": now_datetime()},
		update_modified=False,
	)


def has_cash_disbursement_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level company check (every path): the company of the record, sent or stored, must be one the
	user is permitted for. Unrestricted users are not limited. Denial only, as Frappe expects."""
	from card.party_registry import _restricted_companies

	companies = _restricted_companies(user or frappe.session.user, DOCTYPE)
	if companies is None:
		return True
	owners = {doc.get("company")}
	if not doc.is_new():
		owners.add(frappe.db.get_value(DOCTYPE, doc.name, "company"))
	return bool(companies) and all(c in companies for c in owners if c)
