import frappe
from frappe import _
from frappe.utils import flt

from card.report_access import readable_links, resolve_company
from card.report_currency import company_currency_report
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
		{"fieldname": "transports", "label": _("Transports"), "fieldtype": "Int", "width": 100},
		{"fieldname": "amount", "label": _("Transport cost"), "fieldtype": "Currency", "width": 140},
		# #43/#48/#121 (WP-14): moves the company does not pay, shown apart; never in the transport cost
		{
			"fieldname": "not_company_transports",
			"label": _("Transports not paid by the company"),
			"fieldtype": "Int",
			"width": 120,
		},
		{
			"fieldname": "not_company_cost",
			"label": _("Agreed amount (not company cost)"),
			"fieldtype": "Currency",
			"width": 170,
		},
	]


@company_currency_report("Equipment Transport")
def execute(filters=None):
	# Report: "Transport Cost by Project" (Script Report, standard, ref doctype: Equipment Transport)
	# Read-only. One row per project: number and total amount of SUBMITTED Equipment Transport docs in range.
	filters = frappe._dict(filters or {})
	filters.company = resolve_company(filters, "Equipment Transport")
	args = (filters.get("company"), filters.get("from_date"), filters.get("to_date"), filters.get("project"))

	# only the company's transport cost, per project (card.transport_costs: P1-2 cost project rule)
	totals = transport_cost_by_project(*args)
	# information only: what the equipment supplier, the customer or another party pays (WP-14)
	informational = not_company_cost_by_project(*args)

	data = []
	for project in sorted(set(totals) | set(informational)):
		cost = totals.get(project) or {}
		other = informational.get(project) or {}
		data.append(
			{
				"project": project,
				"transports": cost.get("transports", 0),
				"amount": flt(cost.get("amount"), 2),
				"not_company_transports": other.get("transports", 0),
				"not_company_cost": flt(other.get("amount"), 2),
			}
		)

	return readable_links(get_columns(), data), data
