# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-100: equipment maintenance in CARD (replaces equipment_manager's maintenance part).

* Card Maintenance Plan: service interval (hours, optionally litres) and a parts kit per
  equipment model or per machine. A machine plan wins over a model plan; without a plan
  the equipment's own interval is used, then the Card Settings default.
* Status (FR-067) from the meter history (card.meter): next service = last service meter +
  interval; Due Soon inside the warning window, Service Due at or past it. Unlike the old
  app it counts the hours since the LAST SERVICE, not the hours of one fill.
* Card Maintenance Order: records the service, writes a meter reading, moves the
  equipment's last service date/meter, and can create a Material Request or a draft
  Purchase Invoice with the user's own rights (no client-side documents, no fixed account).
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from card.settings import setting

NO_RECORD, WITHIN, SOON, DUE = "No Service Record", "Within Limit", "Due Soon", "Service Due"


def plan_for(equipment):
	"""The active plan of a machine, else of its model, else None."""
	row = frappe.db.get_value(
		"Card Maintenance Plan",
		{"applies_to": "Equipment", "card_equipment": equipment, "is_active": 1},
		["name", "interval_hours", "interval_litres", "warn_before_hours"],
		as_dict=True,
	)
	if row:
		return row
	model = frappe.db.get_value("Card Equipment", equipment, "equipment_model")
	if not model:
		return None
	return frappe.db.get_value(
		"Card Maintenance Plan",
		{"applies_to": "Equipment Model", "equipment_model": model, "is_active": 1},
		["name", "interval_hours", "interval_litres", "warn_before_hours"],
		as_dict=True,
	)


def interval_for(equipment, eq=None):
	"""(interval hours, warn-before hours, plan name)."""
	eq = eq or frappe.db.get_value("Card Equipment", equipment, ["service_interval_hours"], as_dict=True)
	plan = plan_for(equipment)
	if plan and plan_lines(plan) and flt(plan.interval_hours) <= 0:
		interval = 0  # service lines carry the intervals
	elif plan and flt(plan.interval_litres) > 0 and flt(plan.interval_hours) <= 0:
		interval = 0  # a litres-only plan: the hours default does not apply
	else:
		interval = (
			(flt(plan.interval_hours) if plan and flt(plan.interval_hours) > 0 else 0)
			or flt(eq.service_interval_hours)
			or flt(setting("default_service_interval_hours"))
		)
	warn = (flt(plan.warn_before_hours) if plan else 0) or flt(setting("maintenance_warn_before_hours"))
	return interval, warn, plan.name if plan else None


LITRES_WARN_SHARE = 0.9  # a litres-based plan warns at 90 % of its interval


def litres_since(equipment, since):
	"""Litres of the Valid readings of the equipment after its last service date."""
	from frappe.query_builder.functions import Sum

	t = frappe.qb.DocType("Card Meter Reading")
	q = frappe.qb.from_(t).select(Sum(t.litres)).where((t.equipment == equipment) & (t.status == "Valid"))
	if since:
		q = q.where(t.reading_time > getdate(since))
	return flt(q.run()[0][0])


def compute_status(equipment):
	"""(status, next service meter) of one equipment. The meter is in the equipment's own
	unit (hours, or kilometres for a kilometre meter); a plan with a litres interval is
	also due once that many litres were filled since the last service."""
	eq = frappe.db.get_value(
		"Card Equipment",
		equipment,
		["current_meter", "last_service_meter", "last_service_date", "service_interval_hours", "meter_type"],
		as_dict=True,
	)
	if not eq or eq.meter_type == "بدون عداد":
		return None, 0
	plan = plan_for(equipment)
	lines = plan_lines(plan)
	litres_interval = flt(plan.interval_litres) if plan else 0
	if lines:
		return _status_from_lines(equipment, eq, lines, litres_interval)
	interval, warn, _plan = interval_for(equipment, eq)
	if not interval and not litres_interval:
		return None, 0
	# a first service at meter 0 is a service record too (the date tells)
	if not flt(eq.last_service_meter) and not eq.last_service_date:
		return NO_RECORD, 0
	statuses = []
	next_at = 0
	if interval:
		next_at = flt(eq.last_service_meter) + interval
		remaining = next_at - flt(eq.current_meter)
		statuses.append(DUE if remaining <= 0 else SOON if remaining <= warn else WITHIN)
	if litres_interval:
		statuses.append(_litres_status(equipment, eq.last_service_date, litres_interval))
	return _worst(statuses), next_at


def _worst(statuses):
	for status in (DUE, SOON, WITHIN, NO_RECORD):
		if status in statuses:
			return status
	return WITHIN


def _litres_status(equipment, since, litres_interval):
	used = litres_since(equipment, since)
	if used >= litres_interval:
		return DUE
	return SOON if used >= litres_interval * LITRES_WARN_SHARE else WITHIN


# ---------- 4.4.0: several service lines per plan (oil 250 h, filters 500 h, ...) ----------


def plan_lines(plan):
	if not plan:
		return []
	return frappe.get_all(
		"Card Maintenance Plan Line",
		filters={"parent": plan.name, "parenttype": "Card Maintenance Plan"},
		fields=["service_name", "interval_hours", "warn_before_hours"],
		order_by="idx",
	)


def _service_orders(equipment):
	"""Submitted Scheduled Service orders with a Valid reading, newest first, with the
	services each one covered (empty = every service of the plan)."""
	orders = frappe.get_all(
		"Card Maintenance Order",
		filters={"equipment": equipment, "docstatus": 1, "service_type": "Scheduled Service"},
		fields=["name", "service_date", "meter_reading", "meter_reading_record"],
		order_by="service_date desc, meter_reading desc",
	)
	valid = set(
		frappe.get_all(
			"Card Meter Reading",
			filters={
				"name": ["in", [o.meter_reading_record for o in orders if o.meter_reading_record]],
				"status": "Valid",
			},
			pluck="name",
		)
	)
	orders = [o for o in orders if o.meter_reading_record in valid]
	done = {}
	for row in frappe.get_all(
		"Card Maintenance Order Service",
		filters={"parent": ["in", [o.name for o in orders]], "parenttype": "Card Maintenance Order"},
		fields=["parent", "service_name"],
	):
		done.setdefault(row.parent, set()).add(row.service_name)
	for o in orders:
		o.services = done.get(o.name)
	return orders


def line_statuses(equipment):
	"""Status of each service line of the equipment's plan (empty without lines)."""
	eq = frappe.db.get_value(
		"Card Equipment",
		equipment,
		["current_meter", "last_service_meter", "last_service_date"],
		as_dict=True,
	)
	plan = plan_for(equipment)
	lines = plan_lines(plan)
	if not (eq and lines):
		return []
	orders = _service_orders(equipment)
	pre = _pre_card_baseline(equipment, eq)
	default_warn = flt(setting("maintenance_warn_before_hours"))
	out = []
	for line in lines:
		last = next((o for o in orders if not o.services or line.service_name in o.services), None)
		if last:
			base_meter, base_date = flt(last.meter_reading), last.service_date
		elif pre:
			# never moved by an order that did not cover this line
			base_meter, base_date = pre
		else:
			out.append(
				frappe._dict(service_name=line.service_name, status=NO_RECORD, next_at=0, last_meter=None)
			)
			continue
		next_at = base_meter + flt(line.interval_hours)
		remaining = next_at - flt(eq.current_meter)
		warn = flt(line.warn_before_hours) or default_warn
		out.append(
			frappe._dict(
				service_name=line.service_name,
				interval_hours=flt(line.interval_hours),
				last_meter=base_meter,
				last_date=base_date,
				next_at=next_at,
				remaining=remaining,
				status=DUE if remaining <= 0 else SOON if remaining <= warn else WITHIN,
			)
		)
	return out


def _pre_card_baseline(equipment, eq):
	"""(meter, date) of the last service before the first CARD scheduled order, else the
	equipment's own last service when it has no CARD order; None without any record."""
	first = frappe.get_all(
		"Card Maintenance Order",
		filters={"equipment": equipment, "service_type": "Scheduled Service", "docstatus": ["!=", 0]},
		fields=["previous_service_meter", "previous_service_date"],
		order_by="creation asc",
		limit=1,
	)
	if first:
		row = first[0]
		return (
			(flt(row.previous_service_meter), row.previous_service_date)
			if (flt(row.previous_service_meter) or row.previous_service_date)
			else None
		)
	if flt(eq.last_service_meter) or eq.last_service_date:
		return flt(eq.last_service_meter), eq.last_service_date
	return None


def _status_from_lines(equipment, eq, lines, litres_interval):
	rows = line_statuses(equipment)
	statuses = [r.status for r in rows]
	if litres_interval and (flt(eq.last_service_meter) or eq.last_service_date):
		statuses.append(_litres_status(equipment, eq.last_service_date, litres_interval))
	if statuses and all(s == NO_RECORD for s in statuses):
		return NO_RECORD, 0
	dated = [r.next_at for r in rows if r.status != NO_RECORD]
	return _worst(statuses), (min(dated) if dated else 0)


def refresh_status(equipment, notify=True):
	"""Store the status on the equipment; tell the Card Managers once when it becomes due."""
	status, next_at = compute_status(equipment)
	before = frappe.db.get_value("Card Equipment", equipment, "maintenance_status")
	frappe.db.set_value(
		"Card Equipment",
		equipment,
		{"maintenance_status": status or "", "next_service_meter": next_at},
		update_modified=False,
	)
	if status == DUE and before != DUE:
		if notify and frappe.utils.cint(setting("notify_maintenance_due")):
			_notify_due(equipment, next_at)
		if frappe.utils.cint(setting("auto_create_due_orders")):
			try:
				frappe.db.savepoint("card_due_order")
				create_due_order(equipment)
			except Exception:
				# the reading / fill / order the user saved must not fail because of the scan
				frappe.db.rollback(save_point="card_due_order")
				frappe.log_error(title=_("CARD due order of {0} failed").format(equipment))
	return status


def create_due_order(equipment):
	"""A draft "Due" Scheduled Service order with the plan's kit, once per open due order
	(setting auto_create_due_orders, off by default). Never submitted by CARD."""
	frappe.db.get_value("Card Equipment", equipment, "name", for_update=True)  # one at a time
	if frappe.db.exists(
		"Card Maintenance Order",
		{"equipment": equipment, "docstatus": 0, "work_status": ["in", ["Due", "Approved", "In Progress"]]},
	):
		return None
	plan = plan_for(equipment)
	kit = (
		frappe.get_all(
			"Card Maintenance Kit Item",
			filters={"parent": plan.name, "parenttype": "Card Maintenance Plan"},
			fields=["item_code", "qty", "uom"],
			order_by="idx",
		)
		if plan
		else []
	)
	doc = frappe.get_doc(
		{
			"doctype": "Card Maintenance Order",
			"equipment": equipment,
			"service_date": nowdate(),
			"service_type": "Scheduled Service",
			"meter_reading": flt(frappe.db.get_value("Card Equipment", equipment, "current_meter")),
			"maintenance_plan": plan.name if plan else None,
			"items": [{**k, "from_kit": 1} for k in kit],
			"auto_created": 1,
		}
	)
	doc.flags.card_status_change = True
	doc.work_status = "Due"
	doc.insert(ignore_permissions=True)  # system scan; the order is approved and done by users
	return doc.name


def _notify_due(equipment, next_at):
	eq = frappe.db.get_value("Card Equipment", equipment, ["equipment_name", "company"], as_dict=True)
	users = frappe.get_all(
		"Has Role",
		filters={"role": "Card Manager", "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	from card.report_access import permitted_companies

	for user in users:
		if not frappe.db.get_value("User", user, "enabled"):
			continue
		if eq.company not in permitted_companies("Card Equipment", user=user):
			continue  # a manager of another company is not told about this machine
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "Card Equipment",
				"document_name": equipment,
				"subject": _(
					"Service due: {0} (next service at {1})",
					lang=frappe.db.get_value("User", user, "language") or None,
				).format(eq.equipment_name, flt(next_at)),
			}
		).insert(ignore_permissions=True)  # system alert to the managers


def daily_maintenance_scan():
	"""Scheduler (daily): refresh every equipment that has a meter."""
	for name in frappe.get_all(
		"Card Equipment",
		filters={"meter_type": ["!=", "بدون عداد"], "status": ["!=", "منتهية"]},
		pluck="name",
	):
		try:
			refresh_status(name)
		except Exception:
			frappe.log_error(title=_("CARD maintenance status of {0} failed").format(name))


# ---------- maintenance order -> ERPNext documents ----------


def _order_for(name, ptype="write"):
	"""The order, row-locked so two requests cannot both create a document for it."""
	frappe.db.get_value("Card Maintenance Order", name, "name", for_update=True)
	doc = frappe.get_doc("Card Maintenance Order", name)
	doc.check_permission(ptype)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the maintenance order first."))
	return doc


@frappe.whitelist(methods=["POST"])
def make_material_request(order: str):
	"""Draft Material Request (Material Issue from stock) for the order's parts, created
	with the user's own ERPNext rights."""
	doc = _order_for(order)
	if doc.material_request:
		frappe.throw(_("Material Request {0} already exists for this order.").format(doc.material_request))
	if doc.stock_entry:
		frappe.throw(
			_("The parts of this order are already issued by Stock Entry {0}.").format(doc.stock_entry)
		)
	if not doc.items:
		frappe.throw(_("The order has no parts."))
	mr = frappe.get_doc(
		{
			"doctype": "Material Request",
			"material_request_type": "Material Issue",
			"company": doc.company,
			"transaction_date": nowdate(),
			"schedule_date": getdate(doc.service_date),
			"items": [
				{
					"item_code": row.item_code,
					"qty": flt(row.qty),
					"uom": row.uom,
					"schedule_date": getdate(doc.service_date),
					"cost_center": doc.cost_center,
					"project": doc.project,
				}
				for row in doc.items
			],
		}
	)
	mr.insert()  # the user's own Material Request create right applies
	doc.db_set("material_request", mr.name)
	doc.add_comment("Info", _("Material Request {0} created.").format(mr.name))
	return mr.name


@frappe.whitelist(methods=["POST"])
def make_purchase_invoice(order: str):
	"""Draft Purchase Invoice for the order's parts from its supplier, with the user's own
	ERPNext rights; ERPNext fills accounts and taxes from its own defaults."""
	doc = _order_for(order)
	if doc.purchase_invoice:
		frappe.throw(_("Purchase Invoice {0} already exists for this order.").format(doc.purchase_invoice))
	if not doc.supplier:
		frappe.throw(_("Set the supplier on the order first."))
	if not doc.items:
		frappe.throw(_("The order has no parts."))
	pi = frappe.get_doc(
		{
			"doctype": "Purchase Invoice",
			"supplier": doc.supplier,
			"company": doc.company,
			"posting_date": nowdate(),
			"bill_date": getdate(doc.service_date),
			"project": doc.project,
			"cost_center": doc.cost_center,
			"remarks": _("Maintenance order {0} for {1}").format(
				doc.name, doc.equipment_name or doc.equipment
			),
			"items": [
				{
					"item_code": row.item_code,
					"qty": flt(row.qty),
					"uom": row.uom,
					"cost_center": doc.cost_center,
					"project": doc.project,
				}
				for row in doc.items
			],
		}
	)
	pi.set_missing_values()
	pi.insert()  # draft only; the user's own Purchase Invoice create right applies
	doc.db_set("purchase_invoice", pi.name)
	doc.add_comment("Info", _("Draft Purchase Invoice {0} created.").format(pi.name))
	return pi.name


@frappe.whitelist(methods=["GET"])
def get_plan_kit(equipment: str):
	"""Kit lines of the equipment's plan, to prefill a new order (read only)."""
	frappe.has_permission("Card Equipment", "read", equipment, throw=True)
	plan = plan_for(equipment)
	if not plan:
		return {"plan": None, "items": []}
	frappe.has_permission("Card Maintenance Plan", "read", plan.name, throw=True)
	items = frappe.get_all(
		"Card Maintenance Kit Item",
		filters={"parent": plan.name, "parenttype": "Card Maintenance Plan"},
		fields=["item_code", "qty", "uom", "notes"],
		order_by="idx",
	)
	return {"plan": plan.name, "items": items}


# ---------- 4.4.0: work-order lifecycle and parts issue ----------

APPROVER_ROLES = {"System Manager", "Card Manager"}


def _draft_order(name):
	frappe.db.get_value("Card Maintenance Order", name, "name", for_update=True)
	doc = frappe.get_doc("Card Maintenance Order", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("The maintenance order {0} is already submitted or cancelled.").format(name))
	return doc


def _set_work_status(doc, status):
	doc.flags.card_status_change = True
	doc.work_status = status
	doc.save()  # the user's own write right on the order


@frappe.whitelist(methods=["POST"])
def approve_order(order: str):
	"""Due → Approved, by a Card Manager (or System Manager) of the order's company."""
	if not APPROVER_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Only a Card Manager can approve a maintenance order."), frappe.PermissionError)
	doc = _draft_order(order)
	from card.report_access import permitted_companies

	if doc.company not in permitted_companies("Card Maintenance Order", "Card Equipment"):
		frappe.throw(_("Only a Card Manager can approve a maintenance order."), frappe.PermissionError)
	if doc.work_status != "Due":
		frappe.throw(_("Only a due order can be approved."))
	doc.approved_by = frappe.session.user
	doc.approved_on = frappe.utils.now_datetime()
	_set_work_status(doc, "Approved")
	return doc.work_status


@frappe.whitelist(methods=["POST"])
def start_order(order: str):
	"""Approved → In Progress (the work has started)."""
	doc = _draft_order(order)
	if doc.work_status != "Approved":
		frappe.throw(_("Approve the maintenance order first."))
	_set_work_status(doc, "In Progress")
	return doc.work_status


@frappe.whitelist(methods=["POST"])
def make_stock_entry(order: str):
	"""Draft Stock Entry (Material Issue) of the order's parts from its warehouse, with the
	user's own ERPNext stock rights; submitting it is an ERPNext step of the user."""
	doc = _order_for(order)
	if doc.stock_entry:
		frappe.throw(_("Stock Entry {0} already exists for this order.").format(doc.stock_entry))
	if doc.material_request:
		frappe.throw(
			_("The parts of this order are already requested by Material Request {0}.").format(
				doc.material_request
			)
		)
	if not doc.items:
		frappe.throw(_("The order has no parts."))
	if not doc.source_warehouse:
		frappe.throw(_("Set the warehouse of the parts on the order first."))
	entry_type = frappe.db.get_value("Stock Entry Type", {"purpose": "Material Issue"}, "name")
	if not entry_type:
		frappe.throw(_("Create a Stock Entry Type with the purpose Material Issue first."))
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": entry_type,
			"purpose": "Material Issue",
			"company": doc.company,
			"from_warehouse": doc.source_warehouse,
			"project": doc.project,
			"remarks": _("Maintenance order {0} for {1}").format(
				doc.name, doc.equipment_name or doc.equipment
			),
			"items": [
				{
					"item_code": row.item_code,
					"qty": flt(row.qty),
					"uom": row.uom,
					"s_warehouse": doc.source_warehouse,
					"cost_center": doc.cost_center,
					"project": doc.project,
				}
				for row in doc.items
			],
		}
	)
	se.insert()  # draft; the user's own Stock Entry create right applies
	doc.db_set("stock_entry", se.name)
	doc.add_comment("Info", _("Draft Stock Entry {0} created.").format(se.name))
	return se.name


# ---------- 4.4.0: part warranty alerts ----------


def daily_warranty_scan():
	"""Scheduler (daily): tell the company's Card Managers once when a part fitted to a
	machine reaches the end of its warranty within the configured days."""
	from frappe.utils import add_days, getdate, today

	days = frappe.utils.cint(setting("warranty_alert_days"))
	if days <= 0:
		return
	rows = frappe.get_all(
		"Card Equipment Part",
		filters={
			"applies_to": "Equipment",
			"is_active": 1,
			# includes parts already past their warranty when alerts were switched on
			"warranty_until": ["<=", add_days(today(), days)],
			"warranty_alerted_on": ["is", "not set"],
		},
		fields=["name", "item_code", "card_equipment", "warranty_until", "company"],
	)
	from card.report_access import permitted_companies

	managers = frappe.get_all(
		"Has Role", filters={"role": "Card Manager", "parenttype": "User"}, pluck="parent", distinct=True
	)
	for row in rows:
		try:
			company = row.company or frappe.db.get_value("Card Equipment", row.card_equipment, "company")
			for user in managers:
				if not frappe.db.get_value("User", user, "enabled"):
					continue
				if company not in permitted_companies("Card Equipment", user=user):
					continue
				lang = frappe.db.get_value("User", user, "language") or None
				frappe.get_doc(
					{
						"doctype": "Notification Log",
						"for_user": user,
						"type": "Alert",
						"document_type": "Card Equipment Part",
						"document_name": row.name,
						"subject": _("Part warranty ends on {0}: {1} on {2}", lang=lang).format(
							frappe.utils.formatdate(getdate(row.warranty_until)),
							row.item_code,
							row.card_equipment,
						),
					}
				).insert(ignore_permissions=True)  # system alert to the managers
			frappe.db.set_value(
				"Card Equipment Part", row.name, "warranty_alerted_on", today(), update_modified=False
			)
		except Exception:
			frappe.log_error(title=_("CARD warranty alert of {0} failed").format(row.name))
