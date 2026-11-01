# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-100: maintenance status per equipment (read-only)."""

import frappe
from frappe import _
from frappe.utils import flt

from card.maintenance import DUE, SOON, interval_for
from card.report_access import resolve_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, "Card Equipment")
	conditions = {"company": company, "status": ["!=", "منتهية"], "meter_type": ["!=", "بدون عداد"]}
	if filters.get("equipment"):
		conditions["name"] = filters.equipment
	if filters.get("maintenance_status"):
		conditions["maintenance_status"] = filters.maintenance_status
	rows = []
	for eq in frappe.get_list(
		"Card Equipment",
		filters=conditions,
		fields=[
			"name",
			"equipment_name",
			"equipment_type",
			"current_project",
			"status",
			"current_meter",
			"last_service_date",
			"last_service_meter",
			"next_service_meter",
			"maintenance_status",
		],
		order_by="name asc",
		limit_page_length=0,
	):
		interval, _warn, plan = interval_for(eq.name)
		remaining = flt(eq.next_service_meter) - flt(eq.current_meter) if flt(eq.next_service_meter) else None
		rows.append(
			dict(
				eq,
				equipment=eq.name,
				interval=interval,
				plan=plan,
				remaining=remaining,
				indicator="red"
				if eq.maintenance_status == DUE
				else "orange"
				if eq.maintenance_status == SOON
				else "",
			)
		)
	if filters.get("only_attention"):
		rows = [r for r in rows if r["maintenance_status"] in (DUE, SOON)]
	return _columns(), rows


def _columns():
	return [
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 110,
		},
		{"fieldname": "equipment_name", "label": _("Equipment name"), "fieldtype": "Data", "width": 200},
		{"fieldname": "equipment_type", "label": _("Equipment type"), "fieldtype": "Data", "width": 110},
		{"fieldname": "current_project", "label": _("Project"), "fieldtype": "Data", "width": 110},
		{"fieldname": "current_meter", "label": _("Current meter"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "last_service_date",
			"label": _("Last service date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "last_service_meter",
			"label": _("Last service meter"),
			"fieldtype": "Float",
			"width": 110,
		},
		{"fieldname": "interval", "label": _("Service every (hours)"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "plan",
			"label": _("Maintenance plan"),
			"fieldtype": "Link",
			"options": "Card Maintenance Plan",
			"width": 110,
		},
		{
			"fieldname": "next_service_meter",
			"label": _("Next service at (meter)"),
			"fieldtype": "Float",
			"width": 120,
		},
		{"fieldname": "remaining", "label": _("Hours remaining"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "maintenance_status",
			"label": _("Maintenance status"),
			"fieldtype": "Data",
			"width": 130,
		},
	]
