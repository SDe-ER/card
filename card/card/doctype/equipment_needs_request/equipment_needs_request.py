# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.fitment import COMPATIBLE, FIT_LABELS, effective_fit
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
		self.set_fit_status()

	def set_fit_status(self):
		"""Q10: each line keeps the fit its Item had for the machine when it was asked for. Reads
		the fitment rows only; nothing here changes them (Q6)."""
		fits = effective_fit(self.equipment, [row.item_code for row in self.items])
		for row in self.items:
			fit = fits.get(row.item_code, {}).get("fit") if row.item_code else None
			row.fit_status = FIT_LABELS.get(fit)
			row.flags.compatible = fit in COMPATIBLE

	def before_submit(self):
		# validate has just read the fit in this same submit; a line without a confirmed fit
		# needs its reason
		for row in self.items:
			if row.item_code and not row.flags.compatible and not (row.fit_reason or "").strip():
				frappe.throw(
					_("Row {0}: {1} has no confirmed fit for this machine ({2}); enter the reason.").format(
						row.idx, row.item_code, _(row.fit_status)
					)
				)

	def before_cancel(self):
		for row in self.items:
			if active_review_rows(row.name):
				frappe.throw(_("This request is in a supervisor review; cancel the review first."))
