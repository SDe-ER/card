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


class CardCashDisbursement(Document):
	def validate(self):
		before = self.get_doc_before_save()
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

	def on_trash(self):
		if self.status != "Pending":
			frappe.throw(
				_("The cash payment {0} is {1}; it cannot be deleted. Cancel it instead.").format(
					self.name, self.status
				)
			)
