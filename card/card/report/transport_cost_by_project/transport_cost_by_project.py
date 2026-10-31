import frappe
from frappe import _
from frappe.utils import flt

from card.report_access import readable_links, resolve_company
from card.transport_costs import transport_cost_by_project


def get_columns():
	return [
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 200,
		},
		{"fieldname": "transports", "label": _("Transports"), "fieldtype": "Int", "width": 100},
		{"fieldname": "amount", "label": _("Transport cost"), "fieldtype": "Currency", "width": 140},
	]


def execute(filters=None):
	# Report: "Transport Cost by Project" (Script Report, standard, ref doctype: Equipment Transport)
	# Read-only. One row per project: number and total amount of SUBMITTED Equipment Transport docs in range.
	filters = frappe._dict(filters or {})
	filters.company = resolve_company(filters, "Equipment Transport")

	# only the company's transport cost, per project (card.transport_costs: P1-2 cost project rule)
	totals = transport_cost_by_project(
		filters.get("company"), filters.get("from_date"), filters.get("to_date"), filters.get("project")
	)

	data = []
	for project in sorted(totals):
		data.append(
			{
				"project": project,
				"transports": totals[project]["transports"],
				"amount": flt(totals[project]["amount"], 2),
			}
		)

	return readable_links(get_columns(), data), data
