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
from frappe.utils import cint, flt, now_datetime, nowdate

from card.settlement import posting_block_reason, resolve_beneficiary, validate_payment_date

DOCTYPE = "Card Cash Disbursement"
APPROVAL_ROLES = ("Card Manager", "System Manager")
# the dedicated identity the executor runs as: no broad accounting role, only what one entry needs
SERVICE_ROLE = "Card Cash Posting Service"


def _check_role(roles, allowed, message):
	"""A role refusal is a permission error (the access-control matrix expects it), not a validation error."""
	if not set(roles) & set(allowed):
		frappe.throw(message, frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def request_cash_disbursement(card: str, row: str, payment_date: str, evidence: str) -> str:
	"""Record a Pending cash payment for a flagged row of a Draft card (the requester is the record owner).

	The card's company is checked for the caller (read on the card). The beneficiary is the Supplier the card keeps
	(historical snapshot, never the equipment's current owner). The row must be a cash row with a positive amount and
	a validated Cash account; the evidence is required; one payment per row, in any status."""
	doc = frappe.get_doc("Card Monthly Card", card)
	# the request is an action on the card: whoever may edit the card (its company included) may request its payment.
	# The payment record is then inserted under that explicit card check, not by widening the payment DocType's rights.
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("A cash payment is requested on a Draft card only."))
	source = next((r for r in doc.adjustments or [] if r.name == row), None)
	if not source or not cint(source.is_cash_disbursement):
		frappe.throw(_("The row {0} is not a cash payment on card {1}.").format(row, card))
	if flt(source.amount) <= 0:
		frappe.throw(_("The cash payment on row {0} must be an amount above zero.").format(row))
	if not (evidence or "").strip():
		frappe.throw(_("Enter the evidence of the cash payment (receipt number or reference)."))
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
	)
	record.insert(
		ignore_permissions=True
	)  # authorised above: write on the card (company checked by the card)
	return record.name


@frappe.whitelist(methods=["POST"])
def approve_cash_disbursement(name: str) -> str:
	"""Explicit approval by a Card Manager who is not the requester."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can approve a cash payment."))
	doc = frappe.get_doc(DOCTYPE, name)
	# ERPNext's own closed-period rule: a payment dated in a closed period could never be posted, so it is not approved
	from erpnext.accounts.general_ledger import validate_accounting_period

	validate_accounting_period(
		[frappe._dict(posting_date=doc.payment_date, company=doc.company, voucher_type="Journal Entry")]
	)
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
def queue_posting(name: str) -> str | None:
	"""Claim an Approved cash payment for the accounting executor (Approved -> Posting, under a row lock).
	Creates no accounting entry. Returns the Journal Entry when the payment is already Posted."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can post a cash payment."))
	# the company of the payment is checked on the server, for the caller (a raw row update has no permission check)
	frappe.get_doc(DOCTYPE, name).check_permission("write")
	row = frappe.db.get_value(DOCTYPE, name, ["status", "journal_entry"], as_dict=True, for_update=True)
	if not row:
		frappe.throw(_("The cash payment {0} does not exist.").format(name))
	if row.status == "Posted":
		return row.journal_entry
	if row.status not in ("Approved", "Posting Failed"):
		frappe.throw(
			_("Only an approved or failed cash payment can be queued for posting; {0} is {1}.").format(
				name, row.status
			)
		)
	frappe.db.set_value(
		DOCTYPE,
		name,
		{
			"status": "Posting",
			"posting_claimed_by": frappe.session.user,
			"posting_claimed_on": now_datetime(),
			"posting_error": None,
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


def _revalidate_source(doc):
	"""Before a Journal Entry is built: the approved payment must still match its source. The card row must still be a
	cash row with the approved amount and Cash account, and the Supplier must still be the card's beneficiary. The
	executor takes no amount, account or Supplier from anywhere but the approved record and its source."""
	card = frappe.get_doc("Card Monthly Card", doc.card)
	source = next((r for r in card.adjustments or [] if r.name == doc.adjustment_row), None)
	if (
		not source
		or not cint(source.is_cash_disbursement)
		or flt(source.amount, 2) != flt(doc.amount, 2)
		or source.cash_account != doc.cash_account
		or card.supplier != doc.supplier
		or card.company != doc.company
	):
		frappe.throw(
			_(
				"The source of cash payment {0} changed after approval (row, amount, Cash account or Supplier); it is not posted."
			).format(doc.name),
			frappe.ValidationError,
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
		# the executing identity must be permitted for the payment's company (its document rights are not needed:
		# the posting is a controlled transition, not a user save)
		if not has_cash_disbursement_permission(doc, "write", frappe.session.user):
			frappe.throw(
				_("You are not permitted for the company of the cash payment {0}.").format(name),
				frappe.PermissionError,
			)
		_revalidate_source(doc)
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
		{
			"status": "Posted",
			"journal_entry": entry_name,
			"posted_on": now_datetime(),
			"posted_by": frappe.session.user,
		},
		update_modified=False,
	)
	return entry_name


def _has_active_allocations(entry_name: str | None) -> bool:
	"""True while the Journal Entry is still allocated against another document (an invoice or a payment
	reconciliation). Source: Payment Ledger Entry, fields voucher_no, against_voucher_no and delinked (verified in
	erpnext version-16). Such an entry is not cancelled here: the allocation is resolved in ERPNext first."""
	if not entry_name:
		return False
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
def request_cancellation(name: str, reason: str) -> str:
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
	doc.flags.controlled_transition = "cancellation_request"
	doc.save()
	return doc.name


def request_replacement(name, payment_date, evidence):
	"""A correction after cancellation: a new Pending payment for the same flagged row, linked to the cancelled one
	(``replaces``). It needs its own approval by a different Card Manager. The cancelled payment and its Journal Entry
	stay as they are; nothing is reposted by this call."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can request a replacement."))
	# the row lock serialises concurrent requests for the same cancelled payment: the second waits, then sees the
	# live replacement the first one inserted (at most one active replacement per cancelled transaction)
	if frappe.db.get_value(DOCTYPE, name, "name", for_update=True) is None:
		frappe.throw(_("The cash payment {0} does not exist.").format(name))
	frappe.has_permission(DOCTYPE, "create", throw=True)
	original = frappe.get_doc(DOCTYPE, name)
	if original.status != "Cancelled":
		frappe.throw(
			_("Only a cancelled cash payment can be replaced; {0} is {1}.").format(name, original.status)
		)
	live = frappe.db.exists(
		DOCTYPE,
		{"card": original.card, "adjustment_row": original.adjustment_row, "status": ["!=", "Cancelled"]},
	)
	if live:
		frappe.throw(
			_("Row {0} of card {1} already has a live cash payment ({2}).").format(
				original.adjustment_row, original.card, live
			)
		)
	source = next(
		(
			r
			for r in frappe.get_doc("Card Monthly Card", original.card).adjustments or []
			if r.name == original.adjustment_row
		),
		None,
	)
	if not source:
		frappe.throw(
			_("The row {0} is no longer on card {1}.").format(original.adjustment_row, original.card)
		)
	record = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"company": original.company,
			"supplier": original.supplier,
			"card": original.card,
			"adjustment_row": original.adjustment_row,
			"equipment": original.equipment,
			"project": original.project,
			"amount": source.amount,
			"payment_date": payment_date,
			"cash_account": source.cash_account,
			"evidence": evidence,
			"status": "Pending",
			"replaces": original.name,
		}
	).insert()
	return record.name


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


@frappe.whitelist(methods=["POST"])
def run_posting_queue(limit: int = 20) -> list:
	"""The accounting executor's dispatch: process the queued payments the caller may post, one at a time.

	Only the dedicated service identity (SERVICE_ROLE) may call it, so the posting always runs as that identity; no
	code switches the user. Candidates are limited to the caller's permitted companies, checked on each row, so
	a payment of a company the identity is not permitted for is not even selected. Each payment is posted inside a
	savepoint: a failure rolls back that payment only and records status "Posting Failed" with the error, and the
	payment stays queueable again. A payment already posted by an interrupted run is linked, not posted twice
	(execute_posting). Returns one result per processed payment."""
	_check_role(
		frappe.get_roles(),
		(SERVICE_ROLE,),
		_("Only the accounting service identity can run the posting queue."),
	)
	from card.party_registry import _restricted_companies

	# the candidates a caller may post: its permitted companies (Company User Permission), checked here on the row
	# (the identity holds no document right on the payment DocType; the posting itself is a controlled transition)
	allowed = _restricted_companies(frappe.session.user, DOCTYPE)
	candidates = frappe.get_all(
		DOCTYPE,
		filters={"status": "Posting"},
		fields=["name", "company"],
		order_by="posting_claimed_on asc",
		limit=min(max(cint(limit), 1), 100),
	)
	if allowed is not None:
		candidates = [c for c in candidates if c.company in allowed]
	results = []
	for candidate in candidates:
		frappe.db.savepoint("ccd_posting")
		try:
			entry = execute_posting(candidate.name)
			results.append({"name": candidate.name, "status": "Posted", "journal_entry": entry})
		except Exception as error:
			frappe.db.rollback(save_point="ccd_posting")
			message = frappe.utils.strip_html(str(error))[:1000]
			frappe.db.set_value(
				DOCTYPE,
				candidate.name,
				{"status": "Posting Failed", "posting_error": message},
				update_modified=False,
			)
			results.append({"name": candidate.name, "status": "Posting Failed", "error": message})
	return results


def reconciliation_status(journal_entry, amount) -> str:
	"""The reconciliation of a posted payment, kept apart from its posting status. Source: active allocations of the
	Journal Entry's party row in the Payment Ledger Entry (delinked = 0; the allocation rows of erpnext version-16,
	which have the other document on one side). Returns "" before posting."""
	if not journal_entry:
		return ""
	amounts = frappe.get_all(
		"Payment Ledger Entry",
		filters={"delinked": 0, "against_voucher_no": journal_entry, "voucher_no": ["!=", journal_entry]},
		pluck="amount",
	) + frappe.get_all(
		"Payment Ledger Entry",
		filters={"delinked": 0, "voucher_no": journal_entry, "against_voucher_no": ["!=", journal_entry]},
		pluck="amount",
	)
	allocated = sum(abs(flt(value)) for value in amounts)
	if allocated <= 0:
		return "Unreconciled"
	if allocated + 0.005 < flt(amount):
		return "Partially reconciled"
	return "Fully reconciled"


@frappe.whitelist(methods=["GET"])
def get_cash_disbursements(card: str) -> list:
	"""Read-only status of the cash payments of one card, for the card's form. The caller must be permitted to read
	the card (its company). Each entry carries the posting status, the reconciliation status (kept separate), the
	cancellation state and whether a replacement is pending."""
	frappe.get_doc("Card Monthly Card", card).check_permission("read")
	rows = frappe.get_all(
		DOCTYPE,
		filters={"card": card},
		fields=["name", "adjustment_row", "status", "journal_entry", "amount", "posting_error", "replaces"],
		order_by="creation asc",
	)
	pending_replacements = {
		r.replaces
		for r in frappe.get_all(DOCTYPE, filters={"status": "Pending"}, fields=["replaces"])
		if r.replaces
	}
	for row in rows:
		row["reconciliation"] = (
			reconciliation_status(row.journal_entry, row.amount) if row.status == "Posted" else ""
		)
		row["replacement_pending"] = row.name in pending_replacements
	return rows
