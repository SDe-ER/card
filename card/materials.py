# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD v4.0.0 — equipment materials (Owner plan 2026-10-19).

The operator named on a machine asks for its needs (parts and consumables are the
machine's; tools are the operator's custody). The supervisor reviews what was asked,
what is already on site and what to approve. Management approval turns the approved
lines into standard ERPNext Material Requests carrying the item, project, cost center
and the Card Equipment dimension; buying and stock then run in ERPNext. A part's cost
reaches the machine only when stock is issued to it. CARD never posts GL, never creates
salary deductions or HR violations: a repeated request is only flagged for review."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, now_datetime, nowdate

from card.report_access import _role_reads
from card.settings import setting
from card.transfer import current_location

OPERATOR_ROLE = "Card Operator"
SUPERVISOR_ROLE = "Card Supervisor"
APPROVER_ROLES = ("Card Manager", "System Manager")
REVIEW_ROLES = (SUPERVISOR_ROLE, *APPROVER_ROLES)
DIMENSION_FIELD = "card_equipment"
ENDED_STATUS = "منتهية"


# ---------- who is asking ----------
def has_any_role(roles, user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(roles) & set(frappe.get_roles(user)))


def session_employee(user=None):
	"""The active Employee linked to the user account (standard Employee.user_id)."""
	return frappe.db.get_value(
		"Employee", {"user_id": user or frappe.session.user, "status": "Active"}, "name"
	)


def operator_equipment(employee, on=None):
	"""Machines the employee operates: named as the equipment's operator, or on the
	machine's monthly card for the month (draft or submitted)."""
	if not employee:
		return []
	day = getdate(on or nowdate())
	names = set(
		frappe.get_all(
			"Card Equipment",
			filters={"operator": employee, "status": ["!=", ENDED_STATUS]},
			pluck="name",
		)
	)
	for card in frappe.get_all(
		"Card Monthly Card",
		filters={"operator": employee, "docstatus": ["<", 2], "year": str(day.year)},
		fields=["equipment", "month"],
	):
		if card.equipment and cint(card.month) == day.month:
			names.add(card.equipment)
	return sorted(names)


def equipment_project(equipment):
	"""The project the machine is on now (its open assignment), else its stored project."""
	here = current_location(equipment)
	if here.type == "Project" and here.project:
		return here.project
	return frappe.db.get_value("Card Equipment", equipment, "current_project")


def check_requester(doc):
	"""An operator asks only for a machine he operates; a supervisor or manager may
	enter it on his behalf (both names kept). Enforced on every save, also via REST."""
	user = frappe.session.user
	before = None if doc.is_new() else doc.get_doc_before_save()
	doc.entered_by = before.entered_by if before and before.entered_by else user
	if doc.equipment not in operator_equipment(doc.operator, doc.request_date):
		frappe.throw(
			_("{0} is not the operator of equipment {1}.").format(doc.operator, doc.equipment),
			frappe.PermissionError,
		)
	if session_employee(user) != doc.operator and not has_any_role(REVIEW_ROLES, user):
		frappe.throw(_("You can only ask for the equipment you operate."), frappe.PermissionError)
	# on behalf = whoever first entered it is not the operator (kept on later edits)
	doc.on_behalf = 0 if session_employee(doc.entered_by) == doc.operator else 1


# ---------- record-level access for operators ----------
def _operator_only(user):
	return (
		user != "Administrator"
		and OPERATOR_ROLE in frappe.get_roles(user)
		and not has_any_role((*REVIEW_ROLES, "Card User"), user)
	)


def needs_request_query(user=None):
	"""Operators list only their own requests."""
	user = user or frappe.session.user
	if not _operator_only(user):
		return ""
	return "`tabEquipment Needs Request`.`operator` = {}".format(
		frappe.db.escape(session_employee(user) or "")
	)


def needs_request_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _operator_only(user):
		return True
	return bool(doc.operator) and doc.operator == session_employee(user)


# ---------- hints for the supervisor ----------
def repeat_days():
	return cint(setting("repeat_request_days")) or 30


def last_asked_on(equipment, item_code, exclude_request=None):
	"""Last date the same item was asked for (or issued to) the same machine within
	the repeat window; None when it was not. A review hint only."""
	since = add_days(nowdate(), -repeat_days())
	dates = []
	asked = frappe.db.sql(
		"""select max(r.request_date) from `tabEquipment Needs Request Item` i
		join `tabEquipment Needs Request` r on r.name = i.parent
		where r.equipment = %s and i.item_code = %s and r.docstatus = 1
		and r.name != %s and r.request_date >= %s""",
		(equipment, item_code, exclude_request or "", since),
	)
	if asked and asked[0][0]:
		dates.append(getdate(asked[0][0]))
	if frappe.get_meta("Stock Entry Detail").has_field(DIMENSION_FIELD):
		issued = frappe.db.sql(
			"""select max(se.posting_date) from `tabStock Entry Detail` d
			join `tabStock Entry` se on se.name = d.parent
			where d.card_equipment = %s and d.item_code = %s and se.docstatus = 1
			and se.purpose = 'Material Issue' and se.posting_date >= %s""",
			(equipment, item_code, since),
		)
		if issued and issued[0][0]:
			dates.append(getdate(issued[0][0]))
	return max(dates) if dates else None


def can_read_stock():
	"""Stock is shown only to a user whose roles read Bin and Warehouse (F2): not through a shared
	Bin or an if_owner read, as for the ledger figures in the reports."""
	return _role_reads("Bin") and _role_reads("Warehouse")


def stock_by_item(item_codes, warehouse=None, companies=None):
	"""Stock on hand per item, read with the user's own ERPNext rights (F2): only the warehouses
	he may read (Company and Warehouse User Permissions apply; Bin has no company of its own),
	limited to ``companies`` when given. None when he may not read stock or ``warehouse``."""
	if not can_read_stock():
		return None
	filters = {"company": ["in", list(companies)]} if companies else {}
	warehouses = set(frappe.get_list("Warehouse", filters=filters, pluck="name", limit_page_length=0))
	if warehouse:
		if warehouse not in warehouses:
			return None
		warehouses = {warehouse}
	totals = dict.fromkeys(item_codes, 0.0)
	if not totals or not warehouses:
		return totals
	for row in frappe.get_list(
		"Bin",
		filters={"item_code": ["in", list(totals)], "warehouse": ["in", list(warehouses)]},
		fields=["item_code", "actual_qty"],
		limit_page_length=0,
	):
		totals[row.item_code] += flt(row.actual_qty)
	return totals


def stock_qty(item_code, warehouse=None, companies=None):
	stock = stock_by_item([item_code], warehouse, companies)
	return None if stock is None else stock[item_code]


@frappe.whitelist(methods=["GET"])
def review_stock(review: str):
	"""Stock hint per review line, read live with the reader's rights. The hint is never stored on
	the review (F2): a stored figure would show stock to every reader of the review. A line
	without an item, or in a warehouse the reader may not see, has no hint."""
	doc = frappe.get_doc("Equipment Needs Review", review)
	doc.check_permission("read")
	if not can_read_stock():
		return {}
	by_warehouse = {}
	for row in doc.items:
		if row.item_code:
			by_warehouse.setdefault(row.warehouse or None, []).append(row)
	hints = {}
	for warehouse, rows in by_warehouse.items():
		stock = stock_by_item({row.item_code for row in rows}, warehouse, [doc.company])
		for row in rows:
			hints[row.name] = None if stock is None else stock[row.item_code]
	return hints


def active_review_rows(request_item, exclude_review=None):
	"""Review lines (draft or submitted) already holding a request line."""
	return frappe.db.sql(
		"""select i.parent from `tabEquipment Needs Review Item` i
		join `tabEquipment Needs Review` r on r.name = i.parent
		where i.request_item = %s and r.docstatus < 2 and r.name != %s""",
		(request_item, exclude_review or ""),
	)


# ---------- supervisor: consolidate ----------
@frappe.whitelist(methods=["POST"])
def pull_requests(review: str):
	"""Add every submitted, pending request line of the review's project (and dates)
	that no other review holds. Requested quantities are copied, never edited."""
	doc = frappe.get_doc("Equipment Needs Review", review)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft review can take requests."))
	filters = {"project": doc.project, "docstatus": 1, "review_status": "Pending"}
	if doc.from_date and doc.to_date:
		filters["request_date"] = ["between", [doc.from_date, doc.to_date]]
	elif doc.from_date:
		filters["request_date"] = [">=", doc.from_date]
	elif doc.to_date:
		filters["request_date"] = ["<=", doc.to_date]
	held = {r.request_item for r in doc.items}
	store = setting("default_store_warehouse") or None
	added = 0
	for name in frappe.get_all(
		"Equipment Needs Request", filters=filters, pluck="name", order_by="request_date"
	):
		request = frappe.get_doc("Equipment Needs Request", name)
		for line in request.items:
			if line.name in held or active_review_rows(line.name, doc.name):
				continue
			doc.append(
				"items",
				{
					"request": request.name,
					"request_item": line.name,
					"equipment": request.equipment,
					"operator": request.operator,
					"kind": line.kind,
					"item_code": line.item_code,
					"description": line.description,
					"uom": line.uom,
					"requested_qty": line.qty,
					"found_qty": 0,
					"approved_qty": line.qty,
					"route": "From store",
					"warehouse": store,
					"repeat_flag": line.repeat_flag,
				},
			)
			added += 1
	doc.save()
	return added


# ---------- management: approve into ERPNext ----------
def _cost_center(project, company):
	return frappe.db.get_value("Project", project, "cost_center") or frappe.get_cached_value(
		"Company", company, "cost_center"
	)


def _mr_type(line):
	"""The Material Request type of an approved line; None for a tool from the store, which
	goes to the worker through a custody handover (#113), not through a Material Request."""
	if line.route == "Buy for project":
		return "Purchase"
	return None if line.kind == "Tool" else "Material Issue"


@frappe.whitelist(methods=["POST"])
def approve_review(review: str):
	"""Management approval: every approved line goes into a draft ERPNext Material
	Request (Purchase, or Material Issue for parts from the store), with item, project, cost
	center and the equipment dimension on each row. Every approved tool line also gets a
	draft custody Handover for its worker (#113): approval moves no stock and gives nobody a
	tool; the store side confirms the physical handover later. All stay drafts."""
	if not has_any_role(APPROVER_ROLES):
		frappe.throw(_("Only Card Manager may approve equipment needs."), frappe.PermissionError)
	# the Material Requests are made with the approver's own ERPNext rights
	if not frappe.has_permission("Material Request", "create"):
		frappe.throw(
			_("You also need permission to create Material Requests in ERPNext (for example Stock User)."),
			frappe.PermissionError,
		)
	doc = frappe.get_doc("Equipment Needs Review", review)
	doc.check_permission("read")
	# one approval at a time: the row lock makes a second click wait, then see "already approved"
	doc.approval_status = frappe.db.get_value(
		"Equipment Needs Review", review, "approval_status", for_update=True
	)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the review before approving it."))
	if doc.approval_status == "Approved":
		frappe.throw(_("This review is already approved."))
	lines = [line for line in doc.items if flt(line.approved_qty) > 0]
	missing = [line.description or line.request for line in lines if not line.item_code]
	if missing:
		frappe.throw(_("Match these lines to an Item before approval: {0}").format(", ".join(missing)))
	tools = [line for line in lines if line.kind == "Tool"]
	if tools and not setting("tool_custody_warehouse"):
		frappe.throw(_("Set the tool custody store in Card Settings (Materials) before approving tools."))
	if tools and not frappe.has_permission(CUSTODY_DOCTYPE, "create"):
		frappe.throw(
			_("You also need permission to create Employee Tool Custody records."), frappe.PermissionError
		)
	for line in lines:
		if not line.warehouse:
			frappe.throw(_("Choose the warehouse for {0}.").format(line.item_code))
		# checked again here: the Item may have changed since the review was saved
		if line.kind == "Tool" and (error := tool_item_error(line.item_code)):
			frappe.throw(error)
		if line.kind == "Tool" and not line.operator:
			frappe.throw(_("The request of {0} names no worker to receive the tool.").format(line.item_code))

	cost_center = _cost_center(doc.project, doc.company)
	has_dimension = frappe.get_meta("Material Request Item").has_field(DIMENSION_FIELD)
	today = nowdate()
	groups = {}
	for line in lines:
		if mr_type := _mr_type(line):
			groups.setdefault(mr_type, []).append(line)
	created = []
	for mr_type, group in groups.items():
		mr = frappe.new_doc("Material Request")
		mr.update(
			{
				"material_request_type": mr_type,
				"company": doc.company,
				"transaction_date": today,
				"schedule_date": today,
			}
		)
		for line in group:
			row = {
				"item_code": line.item_code,
				"qty": flt(line.approved_qty),
				"schedule_date": today,
				"project": doc.project,
				"cost_center": cost_center,
			}
			row["warehouse"] = line.warehouse
			if has_dimension and line.kind == "Part":
				row[DIMENSION_FIELD] = line.equipment
			mr.append("items", row)
		mr.insert()  # a draft for the buying/stock team
		for line in group:
			line.db_set("material_request", mr.name, update_modified=False)
		created.append(mr.name)
	for line in tools:
		make_handover_draft(doc, line, flt(line.approved_qty))

	doc.db_set(
		{"approval_status": "Approved", "approved_by": frappe.session.user, "approved_on": now_datetime()}
	)
	for request in {line.request for line in doc.items if line.request}:
		approved = any(flt(line.approved_qty) > 0 for line in doc.items if line.request == request)
		frappe.db.set_value(
			"Equipment Needs Request",
			request,
			"review_status",
			"Approved" if approved else "Rejected",
			update_modified=False,
		)
	return created


# ---------- tool custody ----------
CUSTODY_DOCTYPE = "Employee Tool Custody"
HANDOVER_MANAGER_ROLE = "Card Manager"  # Owner H-2: only he makes a replacement draft


def make_handover_draft(review, line, qty):
	"""A draft custody Handover of an approved tool line (approval or replacement). It moves no
	stock and counts for nobody until the store side confirms it (custody submit)."""
	draft = frappe.get_doc(
		{
			"doctype": CUSTODY_DOCTYPE,
			"employee": line.operator,
			"movement": "Handover",
			"date": nowdate(),
			"item_code": line.item_code,
			"qty": qty,
			"warehouse": line.warehouse,
			"project": review.project,
			"card_equipment": line.equipment,
			"review": review.name,
			"review_item": line.name,
		}
	)
	draft.flags.card_server = True  # the review links are written by the server only
	draft.insert()  # with the user's own rights
	frappe.db.set_value(
		"Equipment Needs Review Item", line.name, "tool_custody", draft.name, update_modified=False
	)
	return draft


def can_confirm_custody():
	"""The store side: may submit custody records and Stock Entries (Owner T2 / H-5)."""
	return frappe.has_permission(CUSTODY_DOCTYPE, "submit") and frappe.has_permission("Stock Entry", "submit")


@frappe.whitelist(methods=["POST"])
def close_tool_handover(custody: str, reason: str):
	"""The worker did not take the tool: the draft is closed with a reason, never submitted;
	nothing is counted or moved. A replacement draft is made only by a Card Manager."""
	doc = frappe.get_doc(CUSTODY_DOCTYPE, custody)
	doc.check_permission("write")
	if not (has_any_role((HANDOVER_MANAGER_ROLE,)) or can_confirm_custody()):
		frappe.throw(_("Only the store side or a Card Manager may close a handover."), frappe.PermissionError)
	if frappe.db.get_value("Employee", doc.employee, "user_id") == frappe.session.user:
		frappe.throw(_("You cannot close a handover to yourself."), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Give the reason why the tool was not handed over."))
	status = frappe.db.get_value(CUSTODY_DOCTYPE, custody, ["docstatus", "handover_status"], for_update=True)
	if not doc.review_item or tuple(status) != (0, "Awaiting handover"):
		frappe.throw(_("Only a handover that is still awaiting can be closed."))
	doc.flags.card_server = True
	doc.handover_status, doc.not_handed_reason = "Not handed over", reason
	doc.save()
	return doc.name


@frappe.whitelist(methods=["POST"])
def make_tool_handover(review_item: str):
	"""Card Manager only (Owner H-2): a replacement draft for the tools of an approved line that
	are not handed over yet, after a documented failed handover (closed or cancelled)."""
	if not has_any_role((HANDOVER_MANAGER_ROLE,)):
		frappe.throw(_("Only a Card Manager may make a new handover."), frappe.PermissionError)
	parent = frappe.db.get_value("Equipment Needs Review Item", review_item, "parent")
	if not parent:
		frappe.throw(_("This review line does not exist."), frappe.DoesNotExistError)
	review = frappe.get_doc("Equipment Needs Review", parent)
	review.check_permission("read")
	# lock order as a confirmation (custody row, then line): two requests never deadlock
	last_name = frappe.db.get_value("Equipment Needs Review Item", review_item, "tool_custody")
	last = last_name and frappe.db.get_value(
		CUSTODY_DOCTYPE, last_name, ["docstatus", "handover_status"], for_update=True
	)
	# one replacement at a time: the line row lock makes a second call wait, then see the draft
	line = frappe.db.get_value(
		"Equipment Needs Review Item",
		review_item,
		[
			"name",
			"kind",
			"operator",
			"item_code",
			"warehouse",
			"equipment",
			"approved_qty",
			"handed_qty",
			"tool_custody",
			"material_request",
		],
		as_dict=True,
		for_update=True,
	)
	if review.approval_status != "Approved" or line.kind != "Tool":
		frappe.throw(_("Only a tool line of an approved review can be handed over."))
	# a line approved before #113 went to the custody store through a Material Transfer MR
	if line.material_request and (
		frappe.db.get_value("Material Request", line.material_request, "material_request_type")
		== "Material Transfer"
	):
		frappe.throw(_("This line is handled by its Material Request {0}.").format(line.material_request))
	# locking reads: a plain read would use this request's older snapshot and miss a draft
	# that another request committed while this one waited for the line lock
	if line.tool_custody != last_name:
		frappe.throw(_("This line changed while you worked on it; try again."))
	if last and tuple(last) == (0, "Awaiting handover"):
		frappe.throw(_("A handover of this line is already awaiting confirmation."))
	remaining = flt(line.approved_qty) - flt(line.handed_qty)
	if remaining <= 0:
		frappe.throw(_("All the approved tools of this line are handed over."))
	return make_handover_draft(review, line, remaining).name


def tool_item_error(item_code, need_stock=True):
	"""Why `item_code` cannot be a returnable tool, or None: a tool is never a fixed asset and, when it comes
	into custody (`need_stock`), a stock item."""
	item = frappe.db.get_value("Item", item_code, ["is_stock_item", "is_fixed_asset"], as_dict=True)
	if not item:
		return None  # the Link check reports an Item that does not exist
	if item.is_fixed_asset:
		return _("{0} is a fixed asset: record its custodian on the Asset (Asset Movement).").format(
			item_code
		)
	if need_stock and not item.is_stock_item:
		return _("{0} is not a stock item; a tool must be a stock item.").format(item_code)
	return None


def _sum_custody(rows):
	totals = {}
	for r in rows:
		key = (r.employee, r.item_code)
		totals[key] = totals.get(key, 0.0) + (flt(r.qty) if r.movement == "Handover" else -flt(r.qty))
		if r.movement == "Transfer" and r.to_employee:
			key = (r.to_employee, r.item_code)
			totals[key] = totals.get(key, 0.0) + flt(r.qty)
	return totals


def custody_balances(filters=None):
	"""{(employee, item_code): qty held} from submitted custody movements, in one query."""
	return _sum_custody(
		frappe.get_all(
			"Employee Tool Custody",
			filters=dict(filters or {}, docstatus=1),
			fields=["employee", "to_employee", "movement", "item_code", "qty"],
		)
	)


def custody_balance(employee, item_code, exclude=None, for_update=False):
	"""Tools of `item_code` the employee holds, from submitted custody movements (`for_update`: a
	locking read, so a request that waited on a lock sees the rows committed meanwhile)."""
	if for_update:
		rows = frappe.db.sql(
			"""select employee, to_employee, movement, item_code, qty from `tabEmployee Tool Custody`
			where docstatus = 1 and item_code = %s and name != %s and (employee = %s or to_employee = %s)
			for update""",
			(item_code, exclude or "", employee, employee),
			as_dict=True,
		)
		return flt(_sum_custody(rows).get((employee, item_code), 0))
	balances = custody_balances({"item_code": item_code, "name": ["!=", exclude or ""]})
	return flt(balances.get((employee, item_code), 0))


# ---------- operator portal ----------
PORTAL_ROLES = (OPERATOR_ROLE, *REVIEW_ROLES)


def portal_context():
	"""What the operator page shows: his machines and his recent requests."""
	user = frappe.session.user
	employee = session_employee(user)
	machines = []
	for name in operator_equipment(employee):
		values = frappe.db.get_value("Card Equipment", name, ["equipment_name"], as_dict=True)
		machines.append(
			{"name": name, "equipment_name": values.equipment_name, "project": equipment_project(name)}
		)
	requests = []
	if employee:
		for r in frappe.get_all(
			"Equipment Needs Request",
			filters={"operator": employee, "docstatus": ["<", 2]},
			fields=["name", "equipment_name", "request_date", "review_status", "docstatus"],
			order_by="creation desc",
			limit=20,
		):
			r.items = frappe.get_all(
				"Equipment Needs Request Item",
				filters={"parent": r.name, "parenttype": "Equipment Needs Request"},
				fields=["kind", "item_code", "description", "qty"],
				order_by="idx",
			)
			requests.append(r)
	return {
		"employee": employee,
		"allowed": bool(employee) and has_any_role(PORTAL_ROLES, user),
		"machines": machines,
		"requests": requests,
	}


def _check_portal_user():
	if frappe.session.user == "Guest" or not has_any_role(PORTAL_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def get_portal_context():
	_check_portal_user()
	return portal_context()


@frappe.whitelist(methods=["GET"])
def search_items(txt: str | None = None):
	"""Items an operator may pick, by code, name, barcode or OEM number: 20 at most, code, name and
	unit only. Operators have no Item read permission; this is the one deliberate exception, so they
	can name what their machine needs (G1). The rules and User Permissions are those of the catalog
	search (``card.catalog``), so the inline list never shows an item the catalog hides."""
	_check_portal_user()
	from card.catalog import quick_search

	return quick_search(txt, limit=20)


@frappe.whitelist(methods=["POST"])
def submit_needs(equipment: str, items: str | list, notes: str | None = None):
	"""The operator's own request for one of his machines, submitted at once."""
	_check_portal_user()
	employee = session_employee()
	if not employee:
		frappe.throw(_("Your account is not linked to an employee."), frappe.PermissionError)
	rows = json.loads(items) if isinstance(items, str) else items
	doc = frappe.new_doc("Equipment Needs Request")
	doc.update({"equipment": equipment, "operator": employee, "request_date": nowdate(), "notes": notes})
	for row in rows or []:
		doc.append(
			"items",
			{
				"kind": "Tool" if row.get("kind") == "Tool" else "Part",
				"item_code": row.get("item_code") or None,
				"description": (row.get("description") or "")[:140],
				"qty": flt(row.get("qty")),
				"reason": (row.get("reason") or "")[:140],
			},
		)
	doc.insert()
	doc.submit()
	return doc.name
