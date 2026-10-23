# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

from card.materials import active_review_rows, tool_item_error


class EquipmentNeedsReview(Document):
	def validate(self):
		self.company = frappe.db.get_value("Project", self.project, "company")
		before = None if self.is_new() else self.get_doc_before_save()
		self.supervisor = before.supervisor if before and before.supervisor else frappe.session.user
		# only approve_review writes the approval (directly, after submit)
		self.approval_status, self.approved_by, self.approved_on = "Pending", None, None
		for row in self.items:
			row.material_request = None
		seen = set()
		for row in self.items:
			self._check_line(row, seen)

	def _check_line(self, row, seen):
		# every line comes from an operator's request (Get requests); none is typed here
		if not row.request_item:
			frappe.throw(_("Row {0}: add lines with Get requests only.").format(row.idx))
		if row.request_item:
			if row.request_item in seen:
				frappe.throw(_("Row {0}: this request line is listed twice.").format(row.idx))
			seen.add(row.request_item)
			if active_review_rows(row.request_item, self.name):
				frappe.throw(_("Row {0}: this request line is already in another review.").format(row.idx))
			source = frappe.db.get_value(
				"Equipment Needs Request Item",
				row.request_item,
				["parent", "qty", "kind"],
				as_dict=True,
			)
			request = source and frappe.db.get_value(
				"Equipment Needs Request",
				source.parent,
				["project", "docstatus", "equipment", "operator"],
				as_dict=True,
			)
			if not request or request.docstatus != 1 or request.project != self.project:
				frappe.throw(
					_("Row {0}: the request is not a submitted request of this project.").format(row.idx)
				)
			# what the operator asked is kept as he asked it
			row.request = source.parent
			row.requested_qty = source.qty
			row.kind = source.kind
			row.equipment = request.equipment
			row.operator = request.operator
		if flt(row.found_qty) < 0 or flt(row.approved_qty) < 0:
			frappe.throw(_("Row {0}: quantities cannot be negative.").format(row.idx))
		# a tool goes into custody: refuse a non-stock item or a fixed asset (approved qty 0 refuses the line)
		if row.kind == "Tool" and flt(row.approved_qty) > 0 and (error := tool_item_error(row.item_code)):
			frappe.throw(error)
		if row.inspection == "Inspected":
			row.inspected_by = row.inspected_by or frappe.session.user
			row.inspected_on = row.inspected_on or nowdate()
		else:
			row.inspected_by = row.inspected_on = None
		# never stored (F2): the form shows it live with the reader's rights (card.materials.review_stock)
		row.stock_qty = 0

	def on_submit(self):
		self._set_requests("In review")

	def before_cancel(self):
		if self.approval_status == "Approved" or any(row.material_request for row in self.items):
			frappe.throw(
				_("An approved review cannot be cancelled; its Material Requests are already created.")
			)

	def on_cancel(self):
		self._set_requests("Pending")

	def _set_requests(self, status):
		for request in {row.request for row in self.items if row.request}:
			frappe.db.set_value(
				"Equipment Needs Request", request, "review_status", status, update_modified=False
			)
