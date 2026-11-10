# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

# import frappe
from frappe.model.document import Document


class CardCompanySettings(Document):
	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		# FR-133 (R-14): a company-restricted user never reads another company's row on its own
		# (frappe.client.get, REST GET of the row); permission is otherwise the parent's
		if not super().has_permission(permtype, debug=debug, user=user):
			return False
		if self.flags.ignore_permissions:
			return True
		from card.card.doctype.card_settings.card_settings import settings_row_readable

		return settings_row_readable(self, user)
