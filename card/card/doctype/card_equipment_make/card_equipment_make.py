# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from card.fitment import normalise


class CardEquipmentMake(Document):
	"""The maker of a machine (FR-077). A CARD list of its own: ERPNext Manufacturer is the
	maker of a part (Item Manufacturer, OEM numbers) and is not used for machines (Q1)."""

	def validate(self):
		self.make_name = (self.make_name or "").strip()
		self.make_key = normalise(self.make_name)
		if not self.make_key:
			frappe.throw(_("Enter the make name."))
		# a clear message first; the unique make_key also stops a race between two saves
		other = frappe.db.get_value(
			"Card Equipment Make", {"make_key": self.make_key, "name": ["!=", self.name or ""]}, "name"
		)
		if other:
			frappe.throw(_("Equipment make {0} already exists.").format(other), frappe.DuplicateEntryError)
