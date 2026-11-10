# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class CardEquipmentType(Document):
	def validate(self):
		# FR-144: the type's default dated consumption rates (one row per start date)
		from card.consumption import TYPE_TABLE, validate_consumption_rates

		validate_consumption_rates(self, TYPE_TABLE)
		# an equipment linked to an Asset takes its type from the Asset's category,
		# so one category points to one type
		if not self.asset_category:
			return
		other = frappe.db.get_value(
			"Card Equipment Type",
			{"asset_category": self.asset_category, "name": ["!=", self.name or ""]},
			"name",
		)
		if other:
			frappe.throw(
				_("Asset category {0} is already used by equipment type {1}.").format(
					self.asset_category, other
				)
			)
