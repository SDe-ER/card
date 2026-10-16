import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.diesel import UNALLOCATED, allocate_project_diesel
from card.report_access import resolve_company


def get_columns():
	return [
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 140,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 160,
		},
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 100},
		{"fieldname": "litres", "label": _("Litres"), "fieldtype": "Float", "precision": 3, "width": 110},
		{"fieldname": "amount", "label": _("Diesel cost"), "fieldtype": "Currency", "width": 120},
	]


def execute(filters=None):
	# Report: "Equipment Diesel Consumption" (Script Report, standard, ref doctype: Project Diesel Fill)
	# Read-only. Per (project, month): reuses card.diesel.allocate_project_diesel, which returns the diesel
	# litres/amount attributed to each equipment (direct fills in full, project-tank fills pro-rata by hours).
	# Display/costing only: never posts GL and never touches a card's net amount.
	# Note: allocation is per whole calendar month; the date filter only selects which (project, month) pairs appear.
	filters = frappe._dict(filters or {})
	filters.company = resolve_company(filters, "Project Diesel Fill", "Card Monthly Card")

	fill_filters = [["docstatus", "=", 1]]
	if filters.get("company"):
		fill_filters.append(["company", "=", filters.get("company")])
	if filters.get("from_date"):
		fill_filters.append(["date", ">=", filters.get("from_date")])
	if filters.get("to_date"):
		fill_filters.append(["date", "<=", filters.get("to_date")])
	if filters.get("project"):
		fill_filters.append(["project", "=", filters.get("project")])

	fills = frappe.get_all(
		"Project Diesel Fill",
		filters=fill_filters,
		fields=["project", "date"],
		limit_page_length=0,
	)

	periods = set()
	for fill in fills:
		if not fill.project or not fill.date:
			continue
		fill_date = getdate(fill.date)
		periods.add((fill.project, "%02d" % fill_date.month, str(fill_date.year)))

	eq_filter = filters.get("equipment")
	data = []
	for project, month, year in sorted(periods, key=lambda p: (p[0], p[2], p[1])):
		allocation = allocate_project_diesel(project, month, year, filters.company, include_unallocated=True)
		for equipment in sorted(allocation):
			if eq_filter and equipment != eq_filter:
				continue
			share = allocation[equipment]
			data.append(
				{
					"equipment": _("Unallocated") if equipment == UNALLOCATED else equipment,
					"project": project,
					"month": year + "-" + month,
					"litres": flt(share.get("litres"), 3),
					"amount": flt(share.get("amount"), 2),
				}
			)

	return get_columns(), data
