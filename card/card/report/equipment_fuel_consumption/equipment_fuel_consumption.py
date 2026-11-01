# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-099: per-machine fuel consumption from the meter history (read-only).

Litres per hour = litres filled / hours between consecutive valid readings. Only Valid
readings count. This is operational consumption; the diesel COST stays with the diesel
fills and their supplier invoices (no amount is computed from legacy litres)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.report_access import resolve_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, "Card Meter Reading")
	conditions = [["company", "=", company], ["status", "=", "Valid"]]
	if filters.get("equipment"):
		conditions.append(["equipment", "=", filters.equipment])
	if filters.get("from_date"):
		conditions.append(["reading_time", ">=", getdate(filters.from_date)])
	if filters.get("to_date"):
		conditions.append(["reading_time", "<", frappe.utils.add_days(getdate(filters.to_date), 1)])
	readings = frappe.get_list(
		"Card Meter Reading",
		filters=conditions,
		fields=["equipment", "reading", "reading_time", "litres", "hours_since_previous", "source_type"],
		order_by="equipment asc, reading_time asc",
		limit_page_length=0,
	)
	summary = {}
	for r in readings:
		if not r.equipment:
			continue
		row = summary.setdefault(
			r.equipment,
			{
				"equipment": r.equipment,
				"readings": 0,
				"first": None,
				"last": None,
				"hours": 0.0,
				"litres": 0.0,
			},
		)
		row["readings"] += 1
		row["first"] = row["first"] if row["first"] is not None else flt(r.reading)
		row["last"] = flt(r.reading)
		if flt(r.hours_since_previous) > 0:
			row["hours"] += flt(r.hours_since_previous)
			row["litres"] += flt(r.litres)
	names = dict(
		frappe.get_all(
			"Card Equipment",
			filters={"name": ["in", list(summary)]},
			fields=["name", "equipment_name"],
			as_list=True,
		)
	)
	rows = []
	for row in summary.values():
		row["equipment_name"] = names.get(row["equipment"])
		row["consumption_rate"] = flt(row["litres"] / row["hours"], 2) if row["hours"] else None
		rows.append(row)
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
		{"fieldname": "readings", "label": _("Readings"), "fieldtype": "Int", "width": 80},
		{"fieldname": "first", "label": _("First reading"), "fieldtype": "Float", "width": 110},
		{"fieldname": "last", "label": _("Last reading"), "fieldtype": "Float", "width": 110},
		{"fieldname": "hours", "label": _("Metered hours"), "fieldtype": "Float", "width": 110},
		{"fieldname": "litres", "label": _("Litres over those hours"), "fieldtype": "Float", "width": 130},
		{
			"fieldname": "consumption_rate",
			"label": _("Consumption (litres per hour)"),
			"fieldtype": "Float",
			"width": 140,
		},
	]
