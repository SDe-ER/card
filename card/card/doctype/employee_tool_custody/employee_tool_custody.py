# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, get_datetime, now_datetime, nowdate

from card.materials import (
	DIMENSION_FIELD,
	custody_balance,
	make_handover_draft,
	tool_item_error,
)
from card.settings import setting

# Owner 2026-10-19 (hybrid custody): returnable tools stay on the books in ONE shared
# custody store while a worker holds them; only a loss or damage is issued as cost.
STOCK_MOVES = ("Handover", "Return", "Loss", "Damage")
OUT_MOVES = ("Return", "Transfer", "Loss", "Damage")
# #113: moves between the store and the custody store are confirmed by the store side; the
# Stock Entry is submitted in the same transaction as the custody record (Owner T7 / T8)
CONFIRMED_MOVES = ("Handover", "Return")
# the holder changes: a receipt signed by the worker(s) and the issuer is required (Owner H-1 / H-3)
RECEIPT_MOVES = ("Handover", "Transfer")
# written by the server only (approval, confirmation, close); a client value is ignored
SERVER_FIELDS = ("review", "review_item", "handover_status", "not_handed_reason", "handed_by", "handed_on")
# the store side may choose the store it hands out from (same company) and lower the quantity
FIXED_ON_REVIEW = ("employee", "movement", "item_code", "project", "card_equipment")
REVIEW_LINE = "Equipment Needs Review Item"


class EmployeeToolCustody(Document):
	def validate(self):
		before = None if self.is_new() else self.get_doc_before_save()
		self._keep_server_fields(before)
		self.company = frappe.db.get_value("Employee", self.employee, "company")
		self.stock_entry = None  # only on_submit links the entry it creates
		if flt(self.qty) <= 0:
			frappe.throw(_("The quantity must be more than zero."))
		# a tool already held can still leave custody if its Item changed later
		if error := tool_item_error(self.item_code, need_stock=self.movement == "Handover"):
			frappe.throw(error)
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
		self._check_amended_from()
		self._check_company()
		self._check_receipt_file()
		if self.review_item and self.docstatus == 0:
			self._check_remaining()  # again under the line lock at confirmation
		# a loss or damage is reviewed by people; nothing is deducted automatically
		self.review_required = 1 if self.movement in ("Loss", "Damage") else 0
		if self.movement != "Handover":
			self.handover_status = None
		elif self.docstatus == 0 and self.handover_status != "Not handed over":
			self.handover_status = "Awaiting handover"

	def _check_amended_from(self):
		"""An amendment copies the attachments (and the receipt) of the record it amends: only a
		cancelled movement of the same company that the user may amend (Frappe checks the status)."""
		before = None if self.is_new() else self.get_doc_before_save()
		if before and (before.amended_from or None) != (self.amended_from or None):
			frappe.throw(
				_("Only a cancelled movement of the same company that you may amend can be amended.")
			)
		if not (self.is_new() and self.amended_from):
			return
		source = frappe.db.get_value(self.doctype, self.amended_from, ["docstatus", "company"], as_dict=True)
		if (
			not source
			or source.docstatus != 2
			or source.company != self.company
			or not frappe.has_permission(self.doctype, "amend", doc=self.amended_from)
		):
			frappe.throw(
				_("Only a cancelled movement of the same company that you may amend can be amended.")
			)

	def _check_remaining(self):
		line = frappe.db.get_value(
			REVIEW_LINE, self.review_item, ["approved_qty", "handed_qty"], as_dict=True
		)
		remaining = flt(line.approved_qty) - flt(line.handed_qty) if line else 0
		if flt(self.qty) > remaining:
			frappe.throw(
				_("Only {0} of {1} are still to be handed over on this line.").format(
					remaining, self.item_code
				)
			)

	def _keep_server_fields(self, before):
		if before and before.handover_status == "Not handed over":
			frappe.throw(_("This handover was closed as not handed over; it cannot change."))
		if self.amended_from and frappe.db.get_value(self.doctype, self.amended_from, "review_item"):
			frappe.throw(_("A handover of a reviewed line is replaced by a Card Manager, not amended."))
		if self.flags.card_server:
			return
		for fieldname in SERVER_FIELDS:
			self.set(fieldname, before.get(fieldname) if before else None)
		if before and before.review_item:
			# what the approval decided stays
			for fieldname in FIXED_ON_REVIEW:
				if self.get(fieldname) != before.get(fieldname):
					frappe.throw(
						_("The approved handover cannot change its {0}.").format(
							_(self.meta.get_label(fieldname))
						)
					)

	def _check_receipt_file(self):
		# a file of another document is not this movement's receipt (as FR-077 evidence files)
		if not self.handover_receipt or not (self.is_new() or self.has_value_changed("handover_receipt")):
			return
		files = frappe.get_all(
			"File",
			filters={"file_url": self.handover_receipt, "is_private": 1},
			fields=["attached_to_doctype", "attached_to_name", "owner", "creation"],
		)
		# an unattached file counts only when the user uploaded it for this record: after the record
		# was made (a new record: within the last day), not an old scan of something else
		since = get_datetime(add_days(self.creation or now_datetime(), -1 if self.is_new() else 0))
		# its own receipt, or the receipt of the record it amends (Amend copies the field)
		own = {(self.doctype, self.name), (self.doctype, self.amended_from)}
		if not any(
			(f.attached_to_doctype, f.attached_to_name) in own
			or (
				not f.attached_to_doctype
				and f.owner == frappe.session.user
				and get_datetime(f.creation) >= since
			)
			for f in files
		):
			frappe.throw(_("The signed receipt must be a private file uploaded to this record."))

	def before_submit(self):
		"""The confirmation (Owner T2, H-1, H-3, H-5, H-6), checked again under row locks: a
		second click or a second user waits, then sees the first confirmation."""
		if (
			not self.is_new()
			and frappe.db.get_value(self.doctype, self.name, "docstatus", for_update=True) != 0
		):
			frappe.throw(_("This movement is already confirmed."))
		if self.movement in CONFIRMED_MOVES and not frappe.has_permission("Stock Entry", "submit"):
			frappe.throw(
				_("Confirming moves stock: you also need permission to submit Stock Entries in ERPNext."),
				frappe.PermissionError,
			)
		if self.movement in CONFIRMED_MOVES:
			self.date = nowdate()  # the day the stock moves (the Stock Entry posts today)
		if self.movement in RECEIPT_MOVES and not self.handover_receipt:
			frappe.throw(_("Attach the receipt signed by the receiving employee and the issuer."))
		if self.movement in RECEIPT_MOVES + CONFIRMED_MOVES:
			self._check_confirmer()  # Loss / Damage keep today's rules (Owner H-4)
		if self.review_item:
			self._check_review_line()
		if self.movement in OUT_MOVES:
			self._check_held_under_lock()

	def _check_held_under_lock(self):
		"""Two movements out of one worker's custody at the same moment: the worker's row lock
		makes the second wait; the balance is then read again with a locking read."""
		frappe.db.get_value("Employee", self.employee, "name", for_update=True)
		held = custody_balance(self.employee, self.item_code, exclude=self.name, for_update=True)
		if flt(self.qty) > held:
			frappe.throw(
				_("{0} holds {1} of {2}; {3} cannot leave his custody.").format(
					self.employee_name or self.employee, held, self.item_code, flt(self.qty)
				)
			)

	def _check_confirmer(self):
		"""Separation of duties: the worker(s), the requester, who entered the request for the
		worker and the approver never confirm. Administrator is not exempt."""
		excluded = {
			frappe.db.get_value("Employee", employee, "user_id")
			for employee in (self.employee, self.to_employee)
			if employee
		}
		if self.review_item:
			excluded.add(frappe.db.get_value("Equipment Needs Review", self.review, "approved_by"))
			request = frappe.db.get_value(REVIEW_LINE, self.review_item, "request")
			if not request:
				frappe.throw(_("This handover no longer matches its approved review line."))
			excluded.update(
				frappe.db.get_value("Equipment Needs Request", request, ["owner", "entered_by"]) or ()
			)
		if frappe.session.user in excluded - {None, ""}:
			frappe.throw(
				_("You cannot confirm this movement: you are its worker, its requester or its approver."),
				frappe.PermissionError,
			)

	def _check_review_line(self):
		line = frappe.db.get_value(
			REVIEW_LINE,
			self.review_item,
			["parent", "kind", "operator", "item_code", "approved_qty", "handed_qty"],
			as_dict=True,
			for_update=True,  # one confirmation per line at a time
		)
		review = frappe.db.get_value(
			"Equipment Needs Review", self.review, ["company", "approval_status"], as_dict=True
		)
		if (
			not line
			or not review
			or line.parent != self.review
			or line.kind != "Tool"
			or review.approval_status != "Approved"
			or review.company != self.company
			or line.operator != self.employee
			or line.item_code != self.item_code
		):
			frappe.throw(_("This handover no longer matches its approved review line."))
		remaining = flt(line.approved_qty) - flt(line.handed_qty)
		self._locked_line = line  # read under the lock; reused in on_submit (no older snapshot)
		if flt(self.qty) < remaining and not frappe.has_permission(self.doctype, "create"):
			frappe.throw(
				_(
					"A partial handover leaves a new draft: you also need permission to create custody records."
				),
				frappe.PermissionError,
			)
		if flt(self.qty) > remaining:
			frappe.throw(
				_("Only {0} of {1} are still to be handed over on this line.").format(
					remaining, self.item_code
				)
			)

	def _check_company(self):
		"""Every linked record belongs to the employee's company (a Transfer cannot cross companies)."""
		custody = setting("tool_custody_warehouse") if self.movement in STOCK_MOVES else None
		for doctype, name in (
			("Employee", self.to_employee),
			("Warehouse", self.warehouse),
			("Warehouse", custody),
			("Project", self.project),
			("Card Equipment", self.card_equipment),
		):
			if name and frappe.db.get_value(doctype, name, "company") != self.company:
				frappe.throw(
					_("Tool custody: {0} {1} is not in the employee's company ({2}).").format(
						_(doctype), name, self.company
					)
				)

	def on_submit(self):
		values = {}
		if self.movement in STOCK_MOVES:
			values["stock_entry"] = self._make_stock_entry()
		if self.movement in RECEIPT_MOVES + CONFIRMED_MOVES:
			values.update({"handed_by": frappe.session.user, "handed_on": now_datetime()})
			if self.movement == "Handover":
				values["handover_status"] = "Handed over"
		if values:
			self.db_set(values)
		if self.review_item:
			self._hand_over_on_line()

	def _hand_over_on_line(self):
		# the line row is locked since before_submit; its values were read there
		line = self._locked_line
		handed = flt(line.handed_qty) + flt(self.qty)
		frappe.db.set_value(REVIEW_LINE, self.review_item, "handed_qty", handed, update_modified=False)
		remaining = flt(line.approved_qty) - handed
		if remaining > 0:
			# a partial handover (Owner T6): the rest waits in a new draft
			review = frappe.get_doc("Equipment Needs Review", self.review)
			make_handover_draft(review, review.getone("items", {"name": self.review_item}), remaining)

	def _make_stock_entry(self):
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
		if self.movement in CONFIRMED_MOVES:
			# one transaction with the custody record, with the confirmer's own ERPNext rights:
			# ERPNext refuses a store without stock and the whole confirmation rolls back
			entry.insert()
			entry.submit()
		else:
			# a loss or damage: a draft for the stock team to submit (unchanged, Owner H-4)
			entry.insert(ignore_permissions=True)
		return entry.name

	def before_cancel(self):
		submitted = (
			self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1
		)
		# a confirmed Handover / Return cancels its own submitted entry (on_cancel): ERPNext
		# refuses to cancel an entry while a submitted custody record links it
		if submitted and not self._cancels_own_entry():
			frappe.throw(_("Cancel Stock Entry {0} first.").format(self.stock_entry))
		if submitted and not frappe.has_permission("Stock Entry", "cancel"):
			frappe.throw(
				_("Cancelling moves stock back: you also need permission to cancel Stock Entries."),
				frappe.PermissionError,
			)
		if self.movement in ("Handover", "Transfer"):
			receiver = self.employee if self.movement == "Handover" else self.to_employee
			if custody_balance(receiver, self.item_code, exclude=self.name) < 0:
				frappe.throw(_("Later movements already use these tools; cancel them first."))

	def on_cancel(self):
		# the approved review line links its handover; the cancel gives the qty back to it
		# (Frappe checks back links after on_cancel and reads this from the instance)
		self.ignore_linked_doctypes = (REVIEW_LINE,)
		entry = self.stock_entry
		if entry and self._cancels_own_entry():
			# the confirmed move goes back in the same transaction, with the user's own rights
			frappe.get_doc("Stock Entry", entry).cancel()
		elif entry:
			# unlink first, or the link check refuses to delete the draft this movement made
			self.db_set("stock_entry", None)
			if self._made_here(entry):
				frappe.delete_doc("Stock Entry", entry, ignore_permissions=True)
		if self.review_item:
			handed = frappe.db.get_value(REVIEW_LINE, self.review_item, "handed_qty", for_update=True)
			frappe.db.set_value(
				REVIEW_LINE,
				self.review_item,
				"handed_qty",
				max(flt(handed) - flt(self.qty), 0),
				update_modified=False,
			)

	def _cancels_own_entry(self):
		"""Only a Handover / Return confirmed by the store side (#113, handed_by set) submitted
		its entry together with the record; an older record keeps "cancel the entry first"."""
		return bool(
			self.movement in CONFIRMED_MOVES and self.handed_by and self._made_here(self.stock_entry, 1)
		)

	def on_trash(self):
		if self.review_item:
			frappe.throw(_("A handover of a reviewed line is kept; close it as not handed over instead."))

	def _made_here(self, entry, docstatus=0):
		"""Only the entry this movement created (same company, its own remark)."""
		values = frappe.db.get_value("Stock Entry", entry, ["docstatus", "company", "remarks"], as_dict=True)
		return bool(
			values
			and values.docstatus == docstatus
			and values.company == self.company
			and (values.remarks or "") == self._marker()
		)

	def _marker(self):
		# fixed text (not translated) so a cancel in another language still recognises it
		return f"CARD tool custody {self.name}"
