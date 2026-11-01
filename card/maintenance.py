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
	if plan and flt(plan.interval_litres) > 0 and flt(plan.interval_hours) <= 0:
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
	interval, warn, _plan = interval_for(equipment, eq)
	litres_interval = flt(plan.interval_litres) if plan else 0
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
		used = litres_since(equipment, eq.last_service_date)
		statuses.append(
			DUE
			if used >= litres_interval
			else SOON
			if used >= litres_interval * LITRES_WARN_SHARE
			else WITHIN
		)
	for status in (DUE, SOON, WITHIN):
		if status in statuses:
			return status, next_at
	return WITHIN, next_at


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
	if notify and status == DUE and before != DUE and frappe.utils.cint(setting("notify_maintenance_due")):
		_notify_due(equipment, next_at)
	return status


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


def on_meter_reading_change(doc, method=None):
	"""Card Meter Reading on_update: the equipment status follows its meter."""
	if doc.equipment:
		refresh_status(doc.equipment)


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
