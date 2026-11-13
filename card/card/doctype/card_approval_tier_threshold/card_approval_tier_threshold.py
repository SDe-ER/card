# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-159 (WP-E; #35, #49, closure plan C row E): one company's approval-tier threshold row on
Card Company Settings (``approval_tier_thresholds``). An empty table means every card is tier 0:
no role gate at submit, current behaviour unchanged. The amount applies to the card's net amount
(the larger of the supplier and customer net amounts, absolute value). The highest matching
threshold wins. The row grants no read, write, submit or cancel permission of its own: it only
names a role the running user must already hold to submit a card at or above that amount."""

from frappe.model.document import Document


class CardApprovalTierThreshold(Document):
	pass
