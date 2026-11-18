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
	# a locking read on the card row first; a missing card and a card of another company get the same refusal
	if not frappe.db.get_value("Card Monthly Card", card, "name", for_update=True):
		_refuse_card()
	# the request is an action on the card: whoever may edit the card (its company included) may request its payment.
	# The payment record is then inserted under that explicit card check, not by widening the payment DocType's rights.
	doc = _card_for_read(card, "write")
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


def _refuse_payment():
	"""The one refusal for a payment the caller may not change, whether the name is missing or belongs to another
	company: the same error class and text, so the response does not show which names exist."""
	frappe.throw(_("You are not permitted to change this cash payment."), frappe.PermissionError)


def _refuse_card():
	"""The one refusal for a card the caller may not use for cash payments (missing or of another company)."""
	frappe.throw(_("You are not permitted to use this card for cash payments."), frappe.PermissionError)


def _card_for_read(card, ptype="read"):
	"""The card, if the caller may use it for ``ptype``. A missing card and a card of another company get the same
	refusal, so the response does not show which card names exist."""
	if not frappe.db.exists("Card Monthly Card", card):
		_refuse_card()
	doc = frappe.get_doc("Card Monthly Card", card)
	if not frappe.has_permission("Card Monthly Card", ptype, doc=doc):
		_refuse_card()
	return doc


def _lock_payment(name):
	"""The first read of every state-changing action: a locking read on the payment row, so no decision below is made on
	a row another transaction is still changing."""
	if not frappe.db.get_value(DOCTYPE, name, "name", for_update=True):
		_refuse_payment()


def _require_payment_right(doc, ptype="write"):
	"""The company check of a locked payment (the same hook as the Desk), answered with the common refusal."""
	if not frappe.has_permission(DOCTYPE, ptype, doc=doc):
		_refuse_payment()


@frappe.whitelist(methods=["POST"])
def approve_cash_disbursement(name: str) -> str:
	"""Explicit approval by a Card Manager who is not the requester."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can approve a cash payment."))
	_lock_payment(name)
	doc = frappe.get_doc(DOCTYPE, name)
	_require_payment_right(doc, "write")
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
	doc.flags.controlled_transition = "approval"  # the only save that may move Pending -> Approved
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def queue_posting(name: str) -> str | None:
	"""Claim an Approved cash payment for the accounting executor (Approved -> Posting, under a row lock).
	Creates no accounting entry. Returns the Journal Entry when the payment is already Posted."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can post a cash payment."))
	_lock_payment(name)
	# the company of the payment is checked on the server, for the caller (a raw row update has no permission check)
	_require_payment_right(frappe.get_doc(DOCTYPE, name), "write")
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


def executor_companies(user=None):
	"""The companies the executing identity is explicitly granted: its Company User Permission rules, and nothing else.

	Fail closed: no rule means no company. Role membership alone never grants a company, and an unrestricted user is not
	treated as "all companies" here (that reading is for display only, never for posting)."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return frozenset()
	return frozenset(
		frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
	)


def _require_company_grant(company, companies):
	"""Refuse a company the identity is not explicitly granted (the same check at selection and before posting)."""
	if not companies or company not in companies:
		frappe.throw(
			_("The accounting identity is not granted the company of this cash payment."),
			frappe.PermissionError,
		)


def _create_entry(doc):
	"""The draft Journal Entry of one approved payment: Dr the Supplier payable, Cr the validated Cash account.

	The remark is human-readable audit text only; the identity of the entry is the link stored on the payment."""
	from erpnext.accounts.party import get_party_account

	entry = frappe.get_doc(
		{
			"doctype": "Journal Entry",
			"voucher_type": "Journal Entry",
			"company": doc.company,
			"posting_date": doc.payment_date,
			"user_remark": "Card cash payment {0} for card {1}, row {2}, on behalf of {3}; requested by {4}, approved by {5}".format(
				doc.name, doc.card, doc.adjustment_row, doc.supplier, doc.owner, doc.approved_by
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
	return entry


def _validated_entry(doc):
	"""The Journal Entry a payment is linked to is accepted only when it is the entry of this payment: not cancelled, the
	company of the payment, created by the executing identity, exactly one Supplier debit to the payment's Supplier at the
	approved amount, and exactly one credit to the approved Cash account at the approved amount. Anything else is refused."""
	from erpnext.accounts.party import get_party_account

	entry = frappe.get_doc("Journal Entry", doc.journal_entry)

	def refuse(reason):
		frappe.throw(
			_("The linked journal entry {0} does not match cash payment {1}: {2}.").format(
				entry.name, doc.name, reason
			),
			frappe.ValidationError,
		)

	if entry.docstatus == 2:
		refuse(_("it is cancelled"))
	if entry.company != doc.company:
		refuse(_("another company"))
	if entry.owner != frappe.session.user:
		refuse(_("not created by this accounting identity"))
	if len(entry.accounts or []) != 2:
		refuse(_("it does not have the two accounts of a payment"))
	debits = [a for a in entry.accounts if flt(a.debit_in_account_currency, 2)]
	credits = [a for a in entry.accounts if flt(a.credit_in_account_currency, 2)]
	if len(debits) != 1 or len(credits) != 1:
		refuse(_("its debit and credit do not form one payment"))
	debit, credit = debits[0], credits[0]
	if debit.party_type != "Supplier" or debit.party != doc.supplier:
		refuse(_("the party is not the Supplier of the payment"))
	if debit.account != get_party_account("Supplier", doc.supplier, doc.company):
		refuse(_("the debit is not on the Supplier's payable account"))
	if flt(debit.debit_in_account_currency, 2) != flt(doc.amount, 2):
		refuse(_("the amount differs from the approved amount"))
	if credit.account != doc.cash_account or flt(credit.credit_in_account_currency, 2) != flt(doc.amount, 2):
		refuse(_("the Cash account or amount differs from the approved payment"))
	return entry


def execute_posting(name):
	"""Accounting execution for one approved payment, by the executing identity.

	``companies`` is the identity's explicit company grant (executor_companies). An empty or missing set, or a payment
	outside it, is refused before anything is written. The durable link ``journal_entry`` on the payment is the only way
	an existing entry is recognised: it is set in the same transaction that creates the entry, before submission, and it
	is unique in the database. Recovery validates the linked entry (see _validated_entry) and never searches by remark.
	Returns the entry name."""
	# the posting boundary establishes the identity and its company grants itself, from the session and the stored
	# permissions; no argument can supply or widen them
	_check_role(
		frappe.get_roles(),
		(SERVICE_ROLE,),
		_("Only the accounting service identity can post a cash payment."),
	)
	companies = executor_companies()
	row = frappe.db.get_value(
		DOCTYPE, name, ["status", "company", "journal_entry", "approved_by"], as_dict=True, for_update=True
	)
	if not row:
		frappe.throw(_("The cash payment {0} does not exist.").format(name))
	_require_company_grant(row.company, companies)
	if row.status == "Posted":
		return row.journal_entry
	if row.status != "Posting":
		frappe.throw(_("Only a queued cash payment can be executed; {0} is {1}.").format(name, row.status))
	# defence in depth: a posting needs a recorded approval, whatever moved the status (FR-170 security review)
	if not row.approved_by:
		frappe.throw(
			_("The cash payment {0} has no approval; it cannot be posted.").format(name),
			frappe.ValidationError,
		)

	doc = frappe.get_doc(DOCTYPE, name)
	_revalidate_source(doc)
	if doc.journal_entry:
		# recovery: the link was written by an earlier run; it is accepted only if it validates
		entry = _validated_entry(doc)
		if entry.docstatus == 0:
			entry.submit()
	else:
		entry = _create_entry(doc)
		# the durable relationship, written before submission in the same transaction (unique in the database)
		frappe.db.set_value(DOCTYPE, name, "journal_entry", entry.name, update_modified=False)
		entry.submit()
	frappe.db.set_value(
		DOCTYPE,
		name,
		{
			"status": "Posted",
			"posted_on": now_datetime(),
			"posted_by": frappe.session.user,
		},
		update_modified=False,
	)
	return entry.name


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
	_lock_payment(name)
	doc = frappe.get_doc(DOCTYPE, name)
	_require_payment_right(doc, "write")
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


@frappe.whitelist(methods=["POST"])
def request_replacement(name: str, reason: str, payment_date: str, evidence: str) -> str:
	"""A correction after cancellation: a new Pending payment for the same flagged row, linked to the cancelled one
	(``replaces``) and carrying the mandatory reason. It needs its own approval by a different Card Manager (approve_cash_
	disbursement refuses the requester). The cancelled payment and its Journal Entry stay as they are; nothing is posted
	by this call, so a click creates no ledger effect."""
	_check_role(frappe.get_roles(), APPROVAL_ROLES, _("Only a Card Manager can request a replacement."))
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Give the reason for the replacement."))
	if not (evidence or "").strip():
		frappe.throw(_("Enter the evidence of the replacement payment (receipt number or reference)."))
	# Locking reads come first, so every plain read below sees the rows as committed after the locks were granted. The
	# live check is per card row and two cancelled payments can share one row: the card row is locked too, so requests
	# for the same row serialise and the second one sees the live replacement the first one inserted.
	# A missing name and a refused company give the same PermissionError: the response does not show which names exist.
	locked = frappe.db.get_value(DOCTYPE, name, ["card"], as_dict=True, for_update=True)
	if not locked:
		_refuse_payment()
	frappe.db.get_value("Card Monthly Card", locked.card, "name", for_update=True)
	original = frappe.get_doc(DOCTYPE, name)
	_require_payment_right(original, "write")
	frappe.has_permission(DOCTYPE, "create", throw=True)
	if original.status != "Cancelled":
		frappe.throw(
			_("Only a cancelled cash payment can be replaced; {0} is {1}.").format(name, original.status)
		)
	live = frappe.db.get_value(
		DOCTYPE,
		{"card": original.card, "adjustment_row": original.adjustment_row, "status": ["!=", "Cancelled"]},
		"name",
		for_update=True,
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
	validate_payment_date(payment_date, nowdate(), False)
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
			"replacement_reason": reason,
		}
	)
	record.insert(
		ignore_permissions=True
	)  # authorised above: create right and the company check on the original
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
	"""The accounting executor's dispatch, run by the dedicated service identity.

	Fail closed on two levels. The caller must hold the service role, and it may act only for the companies it is
	explicitly granted (executor_companies). With no grant the result is empty. Candidates are selected with the granted
	companies in the query itself, and each payment is checked again immediately before posting (execute_posting). A
	payment outside the grant is never selected, never posted and never marked failed. A failure of an authorized
	payment rolls back that payment only (savepoint) and records Posting Failed with the error."""
	_check_role(
		frappe.get_roles(),
		(SERVICE_ROLE,),
		_("Only the accounting service identity can run the posting queue."),
	)
	companies = executor_companies()
	if not companies:
		return []
	candidates = frappe.get_all(
		DOCTYPE,
		filters={"status": "Posting", "company": ["in", sorted(companies)]},
		fields=["name"],
		order_by="posting_claimed_on asc",
		limit=min(max(cint(limit), 1), 100),
	)
	results = []
	for candidate in candidates:
		frappe.db.savepoint("ccd_posting")
		try:
			entry = execute_posting(candidate.name)
			results.append({"name": candidate.name, "status": "Posted", "journal_entry": entry})
		except frappe.PermissionError:
			frappe.db.rollback(save_point="ccd_posting")
			results.append({"name": candidate.name, "status": "Not permitted"})
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


def cash_row_status(card, row):
	"""The display state of one cash row of a Monthly Card: the latest payment of the row, its status, the journal entry
	and the reconciliation, as one label for the table. A plain read; nothing is written and nothing is posted."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"card": card, "adjustment_row": row},
		fields=["name", "status", "journal_entry", "amount"],
		order_by="creation desc",
		limit=1,
	)
	if not rows:
		return {"name": None, "journal_entry": None, "label": _("Not requested")}
	latest = rows[0]
	# literal translatable strings (a dynamic _(status) could not be extracted into the message catalogue)
	status_labels = {
		"Pending": _("Pending"),
		"Approved": _("Approved"),
		"Posting": _("Posting"),
		"Posting Failed": _("Posting Failed"),
		"Posted": _("Posted"),
		"Cancellation Requested": _("Cancellation Requested"),
		"Cancelled": _("Cancelled"),
	}
	recon_labels = {
		"Unreconciled": _("Unreconciled"),
		"Partially reconciled": _("Partially reconciled"),
		"Fully reconciled": _("Fully reconciled"),
	}
	label = status_labels.get(latest.status, latest.status)
	if latest.status == "Posted":
		recon = reconciliation_status(latest.journal_entry, latest.amount)
		if recon:
			label = f"{label} · {recon_labels.get(recon, recon)}"
	return {"name": latest.name, "journal_entry": latest.journal_entry, "label": label}


@frappe.whitelist(methods=["GET"])
def get_cash_row_status(card: str) -> dict:
	"""The display state of every cash row of one card, keyed by the child row name, for the table of the Monthly Card.
	The caller must be permitted to read the card. Read only."""
	_card_for_read(card)
	rows = frappe.get_all(
		"Card Monthly Card Adjustment",
		filters={"parent": card, "is_cash_disbursement": 1},
		pluck="name",
	)
	return {row: cash_row_status(card, row) for row in rows}


@frappe.whitelist(methods=["GET"])
def get_cash_disbursements(card: str) -> list:
	"""Read-only status of the cash payments of one card, for the card's form. The caller must be permitted to read
	the card (its company). Each entry carries the posting status, the reconciliation status (kept separate), the
	cancellation state and whether a replacement is pending."""
	_card_for_read(card)
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
