# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.materials import DIMENSION_FIELD, custody_balance
from card.settings import setting

# Owner 2026-10-19 (hybrid custody): returnable tools stay on the books in ONE shared
# custody store while a worker holds them; only a loss or damage is issued as cost.
STOCK_MOVES = ("Handover", "Return", "Loss", "Damage")
OUT_MOVES = ("Return", "Transfer", "Loss", "Damage")


class EmployeeToolCustody(Document):
	def validate(self):
		self.company = frappe.db.get_value("Employee", self.employee, "company")
		self.stock_entry = None  # only on_submit links the entry it creates
		if flt(self.qty) <= 0:
			frappe.throw(_("The quantity must be more than zero."))
		if frappe.db.get_value("Item", self.item_code, "is_fixed_asset"):
			frappe.throw(
				_("{0} is a fixed asset: record its custodian on the Asset (Asset Movement).").format(
					self.item_code
				)
			)
		if self.movement == "Transfer":
			if not self.to_employee or self.to_employee == self.employee:
				frappe.throw(_("Choose another employee to receive the tool."))
		else:
			self.to_employee = None
		if self.movement in OUT_MOVES:
			held = custody_balance(self.employee, self.item_code, exclude=self.name)
			if flt(self.qty) > held:
				frappe.throw(
					_("{0} holds {1} of {2}; {3} cannot leave his custody.").format(
						self.employee_name or self.employee, held, self.item_code, flt(self.qty)
					)
				)
		if self.movement in STOCK_MOVES and not setting("tool_custody_warehouse"):
			frappe.throw(_("Set the tool custody store in Card Settings (Materials)."))
		if self.movement not in ("Handover", "Return"):
			self.warehouse = None
		# a loss or damage is reviewed by people; nothing is deducted automatically
		self.review_required = 1 if self.movement in ("Loss", "Damage") else 0

	def on_submit(self):
		if self.movement not in STOCK_MOVES:
			return
		custody = setting("tool_custody_warehouse")
		entry = frappe.new_doc("Stock Entry")
		row = {"item_code": self.item_code, "qty": flt(self.qty)}
		if self.serial_no:
			row["serial_no"] = self.serial_no
		if self.movement == "Handover":
			purpose = "Material Transfer"
			row.update({"s_warehouse": self.warehouse, "t_warehouse": custody})
		elif self.movement == "Return":
			purpose = "Material Transfer"
			row.update({"s_warehouse": custody, "t_warehouse": self.warehouse})
		else:
			purpose = "Material Issue"
			row["s_warehouse"] = custody
			if self.project:
				row["project"] = self.project
				row["cost_center"] = frappe.db.get_value("Project", self.project, "cost_center")
			if self.card_equipment and frappe.get_meta("Stock Entry Detail").has_field(DIMENSION_FIELD):
				row[DIMENSION_FIELD] = self.card_equipment
		entry.update({"stock_entry_type": purpose, "purpose": purpose, "company": self.company})
		if self.project:
			entry.project = self.project
		entry.append("items", row)
		entry.remarks = self._marker()
		# a draft for the stock team to submit; the custody register is the movement itself
		entry.insert(ignore_permissions=True)
		self.db_set("stock_entry", entry.name)

	def before_cancel(self):
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			frappe.throw(_("Cancel Stock Entry {0} first.").format(self.stock_entry))
		if self.movement in ("Handover", "Transfer"):
			receiver = self.employee if self.movement == "Handover" else self.to_employee
			if custody_balance(receiver, self.item_code, exclude=self.name) < 0:
				frappe.throw(_("Later movements already use these tools; cancel them first."))

	def on_cancel(self):
		entry = self.stock_entry
		# unlink first, or the link check refuses to delete the draft this movement made
		self.db_set("stock_entry", None)
		if entry and self._made_here(entry):
			frappe.delete_doc("Stock Entry", entry, ignore_permissions=True)

	def _made_here(self, entry):
		"""Only the draft this movement created is removed (same company, its own remark)."""
		values = frappe.db.get_value("Stock Entry", entry, ["docstatus", "company", "remarks"], as_dict=True)
		return bool(
			values
			and values.docstatus == 0
			and values.company == self.company
			and (values.remarks or "") == self._marker()
		)

	def _marker(self):
		# fixed text (not translated) so a cancel in another language still recognises it
		return f"CARD tool custody {self.name}"
