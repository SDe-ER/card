# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""The Tool Custody screen (#113 PR-T3): awaiting handovers, held tools and history in one Desk
page, with only the actions the user may take.

Every read goes through frappe.get_list (DocPerms, Company User Permissions); every write goes
through Employee Tool Custody with the user's own rights, so the controller's rules (store-side
confirmation, signed receipt, separation of duties, locks, company checks) decide. The screen only
fills in defaults and hides actions the server would refuse."""

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from card.card.doctype.employee_tool_custody.employee_tool_custody import confirmer_excluded
from card.materials import (
	CUSTODY_DOCTYPE,
	HANDOVER_MANAGER_ROLE,
	_sum_custody,
	can_confirm_custody,
	equipment_project,
	has_any_role,
	operator_equipment,
	stock_by_item,
)
from card.settings import setting

# Owner U-3: not every CARD user sees custody history; the page is for the store side and the
# people who prepare, confirm and manage handovers (Card User keeps only his DocType read)
SCREEN_ROLES = ("Card Supervisor", "Card Manager", "Stock Manager", "System Manager")
PAGE_LENGTH = 25
TABS = ("awaiting", "held", "history")
SCREEN_MOVES = ("Handover", "Return", "Transfer")


def _check_screen():
	if not (has_any_role(SCREEN_ROLES) and frappe.has_permission(CUSTODY_DOCTYPE, "read")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _may(ptype, doc=None):
	"""Whether the user has `ptype` on custody records (or on `doc`): used to show actions only;
	the action itself checks the permission again."""
	return frappe.has_permission(CUSTODY_DOCTYPE, ptype, doc=doc)


def _filters(employee=None, item_code=None):
	out = {}
	if employee:
		out["employee"] = employee
	if item_code:
		out["item_code"] = item_code
	return out


@frappe.whitelist(methods=["GET"])
def context():
	"""What the screen shows this user: tabs, default tab (Owner U-5) and the main buttons."""
	_check_screen()
	store_side = can_confirm_custody()
	manager = has_any_role((HANDOVER_MANAGER_ROLE,))
	return {
		"tabs": list(TABS),
		# the store side and managers work the queue; a supervisor mostly looks at who holds what
		"default_tab": "awaiting" if (store_side or manager) else "held",
		"can_confirm": store_side,
		"can_prepare": bool(_may("create")),
		"default_store": setting("default_store_warehouse"),
	}


@frappe.whitelist(methods=["GET"])
def view(tab: str = "awaiting", employee: str | None = None, item_code: str | None = None, start: int = 0):
	"""One page of a tab. Reads only."""
	_check_screen()
	if tab not in TABS:
		frappe.throw(_("Unknown tab."))
	start = max(cint(start), 0)
	rows = {"awaiting": _awaiting, "held": _held, "history": _history}[tab](
		_filters(employee, item_code), start
	)
	more = len(rows) > PAGE_LENGTH
	return {"tab": tab, "rows": rows[:PAGE_LENGTH], "more": more, "start": start}


def _awaiting(filters, start):
	user = frappe.session.user
	store_side = can_confirm_custody()
	manager = has_any_role((HANDOVER_MANAGER_ROLE,))
	rows = frappe.get_list(
		CUSTODY_DOCTYPE,
		filters=dict(filters, docstatus=0, movement=["in", list(SCREEN_MOVES)]),
		fields=[
			"name",
			"movement",
			"employee",
			"employee_name",
			"to_employee",
			"item_code",
			"item_name",
			"qty",
			"warehouse",
			"project",
			"card_equipment",
			"handover_status",
			"not_handed_reason",
			"review",
			"review_item",
			"creation",
		],
		order_by="creation desc",
		limit_start=start,
		limit_page_length=PAGE_LENGTH + 1,
	)
	can_submit = bool(_may("submit"))
	# U-4: the store's stock, read with the user's own rights (nothing when he may not read it), one
	# read per store for the page; the confirmation checks it again in ERPNext under the transaction
	stock = {}
	for warehouse in {r.warehouse for r in rows if r.movement == "Handover" and r.warehouse}:
		items = {r.item_code for r in rows if r.movement == "Handover" and r.warehouse == warehouse}
		stock[warehouse] = stock_by_item(items, warehouse)
	workers = dict(
		frappe.get_all(
			"Employee",
			filters={"name": ["in", list({r.employee for r in rows})]},
			fields=["name", "user_id"],
			as_list=True,
		)
	)
	for row in rows:
		awaiting = row.movement != "Handover" or row.handover_status == "Awaiting handover"
		in_store = stock.get(row.warehouse) if row.movement == "Handover" else None
		row.stock = None if in_store is None else in_store.get(row.item_code)
		row.waiting_for_stock = row.stock is not None and flt(row.stock) < flt(row.qty)
		own = user in confirmer_excluded(row)
		worker = workers.get(row.employee) == user
		# a Handover or Return moves stock (store side); a Transfer needs custody submit only
		may_confirm = store_side if row.movement in ("Handover", "Return") else can_submit
		may_close = (
			awaiting
			and row.review_item
			and (store_side or manager)
			and not worker
			and _may("write", row.name)
		)
		row.actions = [
			action
			for action, allowed in (
				("confirm", awaiting and may_confirm and not own and not row.waiting_for_stock),
				("not_handed", may_close),
				("replace", not awaiting and row.review_item and manager and _rest_open(row.review_item)),
			)
			if allowed
		]
	return rows


def _rest_open(review_item):
	"""The line still has tools to hand over and no handover waits for them."""
	line = frappe.db.get_value(
		"Equipment Needs Review Item",
		review_item,
		["approved_qty", "handed_qty", "tool_custody"],
		as_dict=True,
	)
	if not line or flt(line.approved_qty) - flt(line.handed_qty) <= 0:
		return False
	last = line.tool_custody and frappe.db.get_value(
		CUSTODY_DOCTYPE, line.tool_custody, ["docstatus", "handover_status"], as_dict=True
	)
	return not (last and last.docstatus == 0 and last.handover_status == "Awaiting handover")


def _held(filters, start):
	"""Who holds what, from the movements the user may read (a user who may read only some
	movements sees totals of those; Return and Transfer are checked again on the full balance)."""
	names, companies = {}, {}
	employee = filters.pop("employee", None)
	movements = frappe.get_list(
		CUSTODY_DOCTYPE,
		filters=dict(filters, docstatus=1),
		or_filters={"employee": employee, "to_employee": employee} if employee else None,
		fields=[
			"employee",
			"employee_name",
			"to_employee",
			"movement",
			"item_code",
			"item_name",
			"qty",
			"company",
		],
		limit_page_length=0,
	)
	for r in movements:
		names[r.item_code] = r.item_name
		companies[r.employee] = companies[r.to_employee or r.employee] = r.company
	totals = _sum_custody(movements)
	held = [
		(emp, item, qty)
		for (emp, item), qty in sorted(totals.items())
		if flt(qty) > 0 and not (employee and emp != employee)
	][start : start + PAGE_LENGTH + 1]
	user = frappe.session.user
	store_side = can_confirm_custody()
	can_transfer = bool(_may("create") and _may("submit"))
	rows = []
	for emp, item, qty in held:
		emp_name, emp_user = frappe.db.get_value("Employee", emp, ["employee_name", "user_id"]) or ("", None)
		own = emp_user == user
		rows.append(
			frappe._dict(
				employee=emp,
				employee_name=emp_name,
				company=companies.get(emp),
				item_code=item,
				item_name=names.get(item),
				qty=flt(qty),
				actions=[
					action
					for action, allowed in (
						("return", store_side and not own),
						("transfer", can_transfer and not own),
					)
					if allowed
				],
			)
		)
	return rows


def _history(filters, start):
	employee = filters.pop("employee", None)
	or_filters = {"employee": employee, "to_employee": employee} if employee else None
	return frappe.get_list(
		CUSTODY_DOCTYPE,
		filters=dict(filters, docstatus=["in", [1, 2]]),
		or_filters=or_filters,
		fields=[
			"name",
			"movement",
			"docstatus",
			"employee_name",
			"to_employee",
			"item_name",
			"item_code",
			"qty",
			"date",
			"handed_by",
			"handed_on",
			"stock_entry",
			"review",
			"project",
			"card_equipment",
		],
		order_by="modified desc",
		limit_start=start,
		limit_page_length=PAGE_LENGTH + 1,
	)


@frappe.whitelist(methods=["POST"])
def confirm(custody: str, receipt: str | None = None, qty: float | None = None, serial_no: str | None = None):
	"""Confirm a waiting Handover, Return or Transfer in one step: quantity, serial no and the
	signed receipt, then the standard Submit (all of the controller's rules run)."""
	_check_screen()
	doc = frappe.get_doc(CUSTODY_DOCTYPE, custody)
	doc.check_permission("submit")
	if doc.docstatus != 0 or doc.movement not in SCREEN_MOVES:
		frappe.throw(_("This movement is already confirmed."))
	values = {}
	if receipt:
		values["handover_receipt"] = receipt
	if qty is not None:
		if flt(qty) <= 0:
			frappe.throw(_("The quantity must be more than zero."))
		values["qty"] = flt(qty)
	if serial_no:
		values["serial_no"] = serial_no
	doc.update(values)
	doc.submit()
	return {"name": doc.name, "stock_entry": doc.stock_entry}


@frappe.whitelist(methods=["POST"])
def move(
	movement: str,
	employee: str,
	item_code: str,
	qty: float,
	to_employee: str | None = None,
	warehouse: str | None = None,
	serial_no: str | None = None,
):
	"""A new movement from the screen, saved as a draft with its defaults filled in (store from
	Card Settings; for a Handover the worker's machine and its project). It is confirmed with
	`confirm`, after its receipt is printed and signed (the receipt names this record)."""
	_check_screen()
	if movement not in SCREEN_MOVES:
		frappe.throw(_("Unknown movement."))
	doc = frappe.new_doc(CUSTODY_DOCTYPE)
	doc.update(
		{
			"movement": movement,
			"employee": employee,
			"item_code": item_code,
			"qty": flt(qty),
			"date": nowdate(),
			"serial_no": serial_no,
		}
	)
	if movement == "Transfer":
		doc.to_employee = to_employee
	else:
		doc.warehouse = warehouse or setting("default_store_warehouse")
	machines = operator_equipment(employee)
	if movement == "Handover" and machines:
		# the worker's machine and its project, as for his requests
		doc.card_equipment = machines[0]
		doc.project = equipment_project(machines[0])
	doc.insert()
	# the screen offers the confirmation at once only to a user the server lets confirm it
	may_confirm = can_confirm_custody() if movement in ("Handover", "Return") else bool(_may("submit"))
	return {
		"name": doc.name,
		"may_confirm": may_confirm and frappe.session.user not in confirmer_excluded(doc),
	}
