# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

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
# the status changes a save may make, each only with the flag of the server action that owns it (FR-170 review)
CONTROLLED_TRANSITIONS = {
	("Pending", "Approved"): "approval",
	("Posted", "Cancellation Requested"): CANCELLATION_REQUEST,
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


class CardCashDisbursement(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if self.is_new():
			self._validate_creation()
		elif before and any(before.get(f) != self.get(f) for f in REPLACEMENT_FIELDS):
			frappe.throw(
				_("The replacement link and reason of cash payment {0} cannot be changed.").format(self.name)
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
			# approval fields are set only by approve_cash_disbursement()
			approval_fields = ("approved_by", "approved_on", "journal_entry", "posted_on", "posted_by")
			if self.flags.get("controlled_transition") != "approval" and any(
				before.get(f) != self.get(f) for f in approval_fields
			):
				frappe.throw(
					_("The approval fields of cash payment {0} are set by the approval only.").format(
						self.name
					)
				)
		if before and before.status != "Pending":
			protected = (*FROZEN_AFTER_APPROVAL, *EVIDENCE_AFTER_APPROVAL, "status")
			changed = [f for f in protected if before.get(f) != self.get(f)]
			controlled = self.flags.get("controlled_transition") == CANCELLATION_REQUEST
			if controlled and before.status == "Posted" and self.status == "Cancellation Requested":
				changed = [f for f in changed if f != "status"]
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
