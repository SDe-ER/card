# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.materials import active_review_rows, check_requester, equipment_project, last_asked_on


class EquipmentNeedsRequest(Document):
	def validate(self):
		self.company = frappe.db.get_value("Card Equipment", self.equipment, "company")
		check_requester(self)
		self.review_status = "Pending"  # only the review and the approval move it
		self.project = equipment_project(self.equipment)
		if not self.project:
			frappe.throw(
				_("Equipment {0} is not on a project; record its transport first.").format(self.equipment)
			)
		if not self.items:
			frappe.throw(_("Add at least one item."))
		for row in self.items:
			if not row.item_code and not (row.description or "").strip():
				frappe.throw(_("Row {0}: choose an item or describe it.").format(row.idx))
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: the quantity must be more than zero.").format(row.idx))
			last = last_asked_on(self.equipment, row.item_code, self.name) if row.item_code else None
			row.repeat_flag = 1 if last else 0
			row.last_requested_on = last

	def before_cancel(self):
		for row in self.items:
			if active_review_rows(row.name):
				frappe.throw(_("This request is in a supervisor review; cancel the review first."))
