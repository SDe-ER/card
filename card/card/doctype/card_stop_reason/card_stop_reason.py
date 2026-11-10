# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Configurable downtime ("stopped") reasons of one company (#45, WP-09, FR-118).

A monthly card day row may name a reason. A reason earns rental only when it is
explicitly billable (default off): the stopped hours of such a row are billed like
operating hours (card.card.doctype.card_monthly_card) on the reason's billable side
(Supplier, Customer or Both; Both is the merged FR-118 behaviour). A billable reason must
record its approval reason (FR-134, #45 C-07). A reason never changes the four fixed day
statuses or what they bill."""

import frappe
from frappe import _
from frappe.model.document import Document

PARTY_TYPES = ("Company", "Supplier", "Customer", "Other")
SIDE_BOTH = "Both"
BILLABLE_SIDES = (SIDE_BOTH, "Supplier", "Customer")


def billable_side_of(reason):
	"""The side a billable reason bills; an empty value (a row from before FR-134) is Both."""
	return (reason.get("billable_side") or SIDE_BOTH) if reason else SIDE_BOTH


def reason_docname(reason_name, company):
	"""Company-aware name, like ERPNext accounts and cost centres: "<reason> - <abbr>"."""
	abbr = frappe.get_cached_value("Company", company, "abbr") or company
	return "{0} - {1}".format((reason_name or "").strip(), abbr)


class CardStopReason(Document):
	def autoname(self):
		self.reason_name = (self.reason_name or "").strip()
		self.name = reason_docname(self.reason_name, self.company)
		if frappe.db.exists(self.doctype, self.name):
			frappe.throw(
				_("Stop reason {0} already exists for company {1}.").format(self.reason_name, self.company),
				frappe.DuplicateEntryError,
			)

	def validate(self):
		if not (self.reason_name or "").strip():
			frappe.throw(_("Enter the stop reason."))
		if self.default_responsible_party_type and self.default_responsible_party_type not in PARTY_TYPES:
			frappe.throw(_("Invalid responsible party type: {0}").format(self.default_responsible_party_type))
		# FR-134 (#45, C-07): a billable reason names the side it bills and why it was approved
		self.billable_side = self.billable_side or SIDE_BOTH
		if self.billable_side not in BILLABLE_SIDES:
			frappe.throw(_("Invalid billable side: {0}").format(self.billable_side))
		self.billable_approval_reason = (self.billable_approval_reason or "").strip() or None
		if self.billable and not self.billable_approval_reason:
			frappe.throw(
				_(
					"A billable stop reason needs a billable approval reason (who approved it and under which agreement)."
				)
			)
