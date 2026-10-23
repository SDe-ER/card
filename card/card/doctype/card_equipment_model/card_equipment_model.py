# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from card.fitment import normalise


class CardEquipmentModel(Document):
	"""A machine model of one make and one equipment type (FR-077, Q2). The key blocks the
	same model written twice in different ways ("PC200-8" and "pc 200 8")."""

	def validate(self):
		self.model_name = (self.model_name or "").strip()
		if not normalise(self.model_name):
			frappe.throw(_("Enter the model name."))
		self.model_key = f"{self.equipment_make}|{normalise(self.model_name)}"
		if (self.is_new() or self.has_value_changed("equipment_make")) and frappe.db.get_value(
			"Card Equipment Make", self.equipment_make, "disabled"
		):
			frappe.throw(_("Equipment make {0} is disabled.").format(self.equipment_make))
		# machines and fitment rows rely on the make and type of their model
		if (
			not self.is_new()
			and (self.has_value_changed("equipment_make") or self.has_value_changed("equipment_type"))
			and (
				frappe.db.exists("Card Equipment", {"equipment_model": self.name})
				or frappe.db.exists("Card Equipment Part", {"equipment_model": self.name})
			)
		):
			frappe.throw(_("The make and type of a model in use cannot change."))
		other = frappe.db.get_value(
			"Card Equipment Model", {"model_key": self.model_key, "name": ["!=", self.name or ""]}, "name"
		)
		if other:
			frappe.throw(_("Equipment model {0} already exists.").format(other), frappe.DuplicateEntryError)
