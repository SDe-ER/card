import frappe
from frappe import _
from frappe.utils import flt

from card.report_access import readable_links, resolve_company
from card.transport_costs import not_company_cost_by_project, transport_cost_by_project


def get_columns():
	return [
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 200,
		},
		{"fieldname": "diesel", "label": _("Diesel"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "transport", "label": _("Transport"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "total", "label": _("Total operating cost"), "fieldtype": "Currency", "width": 160},
		# #43/#48/#121 (WP-14): moves the company does not pay; shown apart, never in the total
		{
			"fieldname": "transport_not_company_cost",
			"label": _("Agreed amount (not company cost)"),
			"fieldtype": "Currency",
			"width": 170,
		},
	]


def get_project_totals(doctype, filters):
	"""Return {project: sum of amount} for SUBMITTED docs of `doctype` matching the report filters."""
	doc_filters = [["docstatus", "=", 1]]
	if filters.get("company"):
		doc_filters.append(["company", "=", filters.get("company")])
	if filters.get("from_date"):
		doc_filters.append(["date", ">=", filters.get("from_date")])
	if filters.get("to_date"):
		doc_filters.append(["date", "<=", filters.get("to_date")])
	if filters.get("project"):
		doc_filters.append(["project", "=", filters.get("project")])

	rows = frappe.get_all(
		doctype,
		filters=doc_filters,
		fields=["project", "amount"],
		limit_page_length=0,
	)
	totals = {}
	for row in rows:
		if not row.project:
			continue
		totals[row.project] = totals.get(row.project, 0.0) + flt(row.amount)
	return totals


def execute(filters=None):
	# Report: "Operating Cost by Project" (Script Report, standard, ref doctype: Project Diesel Fill)
	# Read-only. Per project: SUBMITTED Project Diesel Fill amount + SUBMITTED Equipment Transport amount.
	# Project totals come straight from the documents (no pro-rata allocation); display only, no GL.
	filters = frappe._dict(filters or {})
	filters.company = resolve_company(filters, "Project Diesel Fill", "Equipment Transport")

	diesel = get_project_totals("Project Diesel Fill", filters)
	args = (filters.get("company"), filters.get("from_date"), filters.get("to_date"), filters.get("project"))
	transport = {project: entry["amount"] for project, entry in transport_cost_by_project(*args).items()}
	informational = {
		project: entry["amount"] for project, entry in not_company_cost_by_project(*args).items()
	}

	data = []
	for project in sorted(set(diesel) | set(transport) | set(informational)):
		diesel_amount = flt(diesel.get(project), 2)
		transport_amount = flt(transport.get(project), 2)
		data.append(
			{
				"project": project,
				"diesel": diesel_amount,
				"transport": transport_amount,
				"total": flt(diesel_amount + transport_amount, 2),
				"transport_not_company_cost": flt(informational.get(project), 2),
			}
		)

	return readable_links(get_columns(), data), data
