# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

# FR-134 (#45): fields whose change must go through the card's own save, so it is validated with
# the card's rules and recorded in the card's Version history
GUARDED_FIELDS = (
	"amount",
	"adjustment_type",
	"adjustment_type_ref",
	"side",
	"stop_reason",
	"responsible_party_type",
	"responsible_party",
	"responsible_party_name",
	"agreement_reference",
)


class CardMonthlyCardAdjustment(Document):
	def validate(self):
		"""Runs only when the row itself is saved or inserted (REST PUT/POST on the row,
		frappe.client.save); the card's own save checks its rows in CardMonthlyCard and does
		not call this. As for unit components (#59), a direct row write of the amount, the
		type, the side or a downtime-charge field is refused: frappe's row-save path re-saves
		the card after the row, so the card's Version diff would not show the change."""
		if frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		if self.parenttype != "Card Monthly Card":
			return
		before = self.get_doc_before_save()
		if before and any(before.get(f) != self.get(f) for f in ("parent", "parenttype", "parentfield")):
			frappe.throw(_("An addition/deduction row cannot be moved to another card."))
		if before and all(before.get(f) == self.get(f) for f in GUARDED_FIELDS):
			return  # e.g. only the description changed
		frappe.throw(
			_(
				"To change additions and deductions, edit monthly card {0} itself; a direct row update is not allowed."
			).format(self.parent or "")
		)
