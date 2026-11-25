# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-159 (WP-E; #35, #49, closure plan C row E): one company's approval-tier threshold row on
Card Settings (``approval_tier_thresholds``). A company without a row means every card is tier 0:
no role gate at submit, current behaviour unchanged. The amount applies to the card's net amount
(the larger of the supplier and customer net amounts, absolute value). The highest matching
threshold wins. The row grants no read, write, submit or cancel permission of its own: it only
names a role the running user must already hold to submit a card at or above that amount."""

from frappe.model.document import Document


class CardApprovalTierThreshold(Document):
	# Row-level rules live in CardSettings.validate (``_validate_approval_tier_thresholds``).
	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		# FR-133 (R-14): a company-restricted user never reads or saves another company's row on its
		# own (frappe.client.get / set_value, REST GET / PUT of the row); permission is otherwise the
		# parent's
		if not super().has_permission(permtype, debug=debug, user=user):
			return False
		if self.flags.ignore_permissions:
			return True
		from card.card.doctype.card_settings.card_settings import settings_row_readable

		return settings_row_readable(self, user)
