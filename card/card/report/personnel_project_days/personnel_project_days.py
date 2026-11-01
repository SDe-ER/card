# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""R1: assigned days per employee, project and cost center for a period (read-only), from
Card Personnel Assignments and the equipment's project history. Days that resolve to no
project are shown as "Needs review". Calendar days only: attendance and pay stay in HRMS;
the R2 allocation combines them."""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

from card.personnel import DOCTYPE, MAX_DAYS, assignments_covering, resolve_day
from card.report_access import resolve_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, DOCTYPE)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Choose the period."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start or date_diff(end, start) + 1 > MAX_DAYS:
		frappe.throw(_("Choose a period of at most {0} days.").format(MAX_DAYS))
	conditions = [["company", "=", company], ["docstatus", "=", 1], ["from_date", "<=", end]]
	if filters.get("employee"):
		conditions.append(["employee", "=", filters.employee])
	employees = sorted(
		{
			r.employee: r.employee_name
			for r in frappe.get_list(
				DOCTYPE,
				filters=conditions,
				or_filters=[["to_date", "is", "not set"], ["to_date", ">=", start]],
				fields=["employee", "employee_name"],
				limit_page_length=0,
			)
		}.items()
	)
	review = _("Needs review")
	data = []
	cache = {}
	for employee, employee_name in employees:
		rows = assignments_covering(employee, start, end, companies=[company])
		totals = {}
		day = start
		while day <= end:
			entries = resolve_day(employee, day, rows, cache)
			for e in entries:
				key = (e.project or review, e.cost_center or "", e.card_equipment or "", e.issue or "")
				totals[key] = totals.get(key, 0.0) + e.share
			day = add_days(day, 1)
		for (project, cost_center, equipment, issue), days in sorted(totals.items()):
			data.append(
				{
					"employee": employee,
					"employee_name": employee_name,
					"project": project,
					"cost_center": cost_center,
					"card_equipment": equipment,
					"days": flt(days, 2),
					"issue": issue,
				}
			)
	columns = [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 130,
		},
		{"fieldname": "employee_name", "label": _("Employee name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 180,
		},
		{
			"fieldname": "card_equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 130,
		},
		{"fieldname": "days", "label": _("Assigned days"), "fieldtype": "Float", "width": 110},
		{"fieldname": "issue", "label": _("Review reason"), "fieldtype": "Data", "width": 260},
	]
	return columns, data
