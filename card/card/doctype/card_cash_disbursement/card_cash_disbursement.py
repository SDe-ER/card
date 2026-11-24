# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, getdate, nowdate

from card.adjustments import validate_cash_account
from card.settlement import cash_transaction_key, validate_payment_date

# the fields that define the economic transaction: frozen once it is approved (FR-170 step 2)
FROZEN_AFTER_APPROVAL = (
	"company",
	"supplier",
	"card",
	"adjustment_row",
	"amount",
	"payment_date",
	"cash_account",
)
# the record of the accounting evidence: never edited after approval, whatever the caller (FR-170 financial immutability)
EVIDENCE_AFTER_APPROVAL = (
	"evidence",
	"transaction_key",
	"journal_entry",
	"replaces",
	"approved_by",
	"approved_on",
	"posted_on",
	"posted_by",
	"posting_error",
	"posting_claimed_by",
	"posting_claimed_on",
)
# the one controlled change a Posted payment may take: a cancellation request by request_cancellation()
CANCELLATION_REQUEST = "cancellation_request"
# the fields that controlled change writes (with the status); every other field stays as it is
CANCELLATION_REQUEST_FIELDS = (
	"status",
	"cancellation_reason",
	"cancellation_requested_by",
	"cancellation_requested_on",
)
# an approved payment that was never posted (no Journal Entry) is cancelled directly by request_cancellation() with
# its reason: there is no entry to cancel in ERPNext (FR-170 final code review)
WITHDRAWAL = "withdrawal"
WITHDRAWABLE_STATUSES = ("Approved", "Posting Failed")
WITHDRAWAL_FIELDS = (*CANCELLATION_REQUEST_FIELDS, "cancelled_by", "cancelled_on")
# the status changes a save may make, each only with the flag of the server action that owns it (FR-170 review)
CONTROLLED_TRANSITIONS = {
	("Pending", "Approved"): "approval",
	("Posted", "Cancellation Requested"): CANCELLATION_REQUEST,
	**{(status, "Cancelled"): WITHDRAWAL for status in WITHDRAWABLE_STATUSES},
}
# the only two ways a payment is created: the request on a card row and the replacement of a cancelled payment; each
# server action sets its flag (a client cannot send flags), so a direct insert is refused (FR-170 security review)
CREATION_REQUEST = "request"
REPLACEMENT_REQUEST = "replacement"
# set only by the server actions after creation; a new record carries none of them
SERVER_OWNED_FIELDS = (
	"approved_by",
	"approved_on",
	"journal_entry",
	"posted_on",
	"posted_by",
	"posting_error",
	"posting_claimed_by",
	"posting_claimed_on",
	"cancellation_reason",
	"cancellation_requested_by",
	"cancellation_requested_on",
	"cancelled_by",
	"cancelled_on",
)
# the replacement link and its reason are written once, by request_replacement(), and never changed by a save
REPLACEMENT_FIELDS = ("replaces", "replacement_reason")
# fixed when the payment is created, in every status: the requester (the four-eyes rule compares the approver with it),
# the card row it pays, its beneficiary, amount and Cash account, and the replacement link (FR-170 final reviews: a
# plain save could rewrite the owner to self-approve, or re-point a pending payment to an already paid row)
FIXED_FROM_CREATION = (
	"owner",
	"company",
	"supplier",
	"card",
	"adjustment_row",
	"equipment",
	"project",  # the Journal Entry's project dimension comes from the payment record
	"amount",
	"cash_account",
	*REPLACEMENT_FIELDS,
)


def _differs(meta, before, doc, field):
	"""A stored value compared as stored: a client save sends a date, a datetime or a number as text, so an unchanged
	"2026-09-30 10:00:00" equals the stored datetime and "120" equals 120.0 (FR-170 final code review)."""
	old, new = before.get(field), doc.get(field)
	fieldtype = (meta.get_field(field) or frappe._dict()).fieldtype
	if fieldtype == "Datetime":
		return (get_datetime(old) if old else None) != (get_datetime(new) if new else None)
	if fieldtype == "Date":
		return (getdate(old) if old else None) != (getdate(new) if new else None)
	if fieldtype in ("Currency", "Float"):
		return flt(old) != flt(new)
	return (old or None) != (new or None)


class CardCashDisbursement(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if self.is_new():
			self._validate_creation()
		elif before:
			# Frappe casts numbers only after validate(): the amount is compared as a number, so "120" equals 120.0
			changed = [
				f
				for f in FIXED_FROM_CREATION
				if (flt(before.get(f)) != flt(self.get(f)) if f == "amount" else before.get(f) != self.get(f))
			]
			if changed:
				frappe.throw(
					_("These fields of cash payment {0} are fixed when it is created: {1}.").format(
						self.name, ", ".join(changed)
					)
				)
		if before and before.status != self.status:
			# a status change is allowed only as the server's own transition (the flag is set by that action alone);
			# a plain save of the record must not approve, queue or cancel it (FR-170 review, High)
			# an unlisted pair has no owner: it is refused even when no flag is set (None == None must not pass)
			expected = CONTROLLED_TRANSITIONS.get((before.status, self.status))
			if expected is None or self.flags.get("controlled_transition") != expected:
				frappe.throw(
					_("The cash payment {0} cannot move from {1} to {2} by a plain save.").format(
						self.name, before.status, self.status
					)
				)
		if before and before.status == "Pending" and self.status == "Pending":
			# approval, posting and cancellation fields are set only by their server actions, never on a pending payment
			if self.flags.get("controlled_transition") != "approval" and any(
				_differs(self.meta, before, self, f) for f in SERVER_OWNED_FIELDS
			):
				frappe.throw(
					_("The approval fields of cash payment {0} are set by the approval only.").format(
						self.name
					)
				)
		if before and before.status != "Pending":
			# the cancellation record too: its reason and actors are written only by request_cancellation() and the
			# Journal Entry cancellation, never by a plain save (FR-170 final audit M1)
			protected = dict.fromkeys(
				(*FROZEN_AFTER_APPROVAL, *EVIDENCE_AFTER_APPROVAL, *SERVER_OWNED_FIELDS, "status")
			)
			changed = [f for f in protected if _differs(self.meta, before, self, f)]
			controlled = self.flags.get("controlled_transition") == CANCELLATION_REQUEST
			if controlled and before.status == "Posted" and self.status == "Cancellation Requested":
				changed = [f for f in changed if f not in CANCELLATION_REQUEST_FIELDS]
			withdrawn = self.flags.get("controlled_transition") == WITHDRAWAL
			if withdrawn and before.status in WITHDRAWABLE_STATUSES and self.status == "Cancelled":
				if before.journal_entry or self.journal_entry:
					frappe.throw(
						_("The cash payment {0} has a journal entry; cancel that entry instead.").format(
							self.name
						)
					)
				changed = [f for f in changed if f not in WITHDRAWAL_FIELDS]
			if changed:
				frappe.throw(
					_(
						"The cash payment {0} is approved; {1} cannot be changed. Cancel it and request a replacement."
					).format(self.name, ", ".join(changed))
				)
		if self.status == "Pending" or not self.transaction_key:
			validate_payment_date(self.payment_date, nowdate(), False)
			validate_cash_account(self.cash_account, self.company)
			self.transaction_key = cash_transaction_key(
				self.card,
				self.adjustment_row,
				self.amount,
				self.payment_date,
				self.cash_account,
				revision=self.replaces or "",
			)

	def _validate_creation(self):
		"""A new payment comes only from request_cash_disbursement() or request_replacement(): Pending, with no
		approval, posting or cancellation data, and a replacement link only from the replacement action. A direct
		insert (REST, frappe.client.insert) cannot create a queued or approved payment (FR-170 security review)."""
		action = self.flags.get("controlled_transition")
		forged = [f for f in SERVER_OWNED_FIELDS if self.get(f)]
		if action != REPLACEMENT_REQUEST:
			forged += [f for f in REPLACEMENT_FIELDS if self.get(f)]
		if action not in (CREATION_REQUEST, REPLACEMENT_REQUEST) or self.status != "Pending" or forged:
			frappe.throw(_("A cash payment is created only by a request or a replacement on its card."))

	def on_trash(self):
		if self.status != "Pending":
			frappe.throw(
				_("The cash payment {0} is {1}; it cannot be deleted. Cancel it instead.").format(
					self.name, self.status
				)
			)
