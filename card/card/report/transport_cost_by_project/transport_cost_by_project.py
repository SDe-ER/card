import frappe
from frappe import _
from frappe.utils import flt


def get_columns():
	return [
		{"fieldname": "project", "label": _("Project"), "fieldtype": "Link", "options": "Project", "width": 200},
		{"fieldname": "transports", "label": _("Transports"), "fieldtype": "Int", "width": 100},
		{"fieldname": "amount", "label": _("Amount"), "fieldtype": "Currency", "width": 140},
	]


def execute(filters=None):
	# Report: "Transport Cost by Project" (Script Report, standard, ref doctype: Equipment Transport)
	# Read-only. One row per project: number and total amount of SUBMITTED Equipment Transport docs in range.
	filters = frappe._dict(filters or {})

	transport_filters = [["docstatus", "=", 1]]
	if filters.get("company"):
		transport_filters.append(["company", "=", filters.get("company")])
	if filters.get("from_date"):
		transport_filters.append(["date", ">=", filters.get("from_date")])
	if filters.get("to_date"):
		transport_filters.append(["date", "<=", filters.get("to_date")])
	if filters.get("project"):
		transport_filters.append(["project", "=", filters.get("project")])

	transports = frappe.get_all(
		"Equipment Transport",
		filters=transport_filters,
		fields=["project", "amount"],
		limit_page_length=0,
	)

	totals = {}
	for row in transports:
		if not row.project:
			continue
		entry = totals.setdefault(row.project, {"transports": 0, "amount": 0.0})
		entry["transports"] = entry["transports"] + 1
		entry["amount"] = entry["amount"] + flt(row.amount)

	data = []
	for project in sorted(totals):
		data.append(
			{
				"project": project,
				"transports": totals[project]["transports"],
				"amount": flt(totals[project]["amount"], 2),
			}
		)

	return get_columns(), data
