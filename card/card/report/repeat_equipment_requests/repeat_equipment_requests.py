# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _

from card.report_access import permitted_companies


def get_columns():
	return [
		{
			"fieldname": "request",
			"label": _("Request"),
			"fieldtype": "Link",
			"options": "Equipment Needs Request",
			"width": 130,
		},
		{"fieldname": "request_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 130,
		},
		{"fieldname": "operator_name", "label": _("Operator name"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "item_code",
			"label": _("Item", context="Card"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 150,
		},
		{"fieldname": "qty", "label": _("Quantity"), "fieldtype": "Float", "width": 90},
		{"fieldname": "last_requested_on", "label": _("Last asked on"), "fieldtype": "Date", "width": 110},
	]


def execute(filters=None):
	# Report: "Repeat Equipment Requests" — items asked again for the same machine within
	# the window in Card Settings. A list to review, never a penalty or deduction.
	filters = frappe._dict(filters or {})
	companies = permitted_companies("Equipment Needs Request")
	if not companies:
		return get_columns(), []
	conditions = {"docstatus": 1, "company": ["in", companies]}
	if filters.get("project"):
		conditions["project"] = filters.project
	if filters.get("equipment"):
		conditions["equipment"] = filters.equipment
	# get_list: the user's own record rules apply (e.g. a supervisor limited to his projects)
	requests = frappe.get_list(
		"Equipment Needs Request", filters=conditions, pluck="name", limit_page_length=0
	)
	if not requests:
		return get_columns(), []
	data = frappe.db.sql(
		"""select r.name as request, r.request_date, r.equipment, r.operator_name, i.item_code, i.qty,
			i.last_requested_on
		from `tabEquipment Needs Request Item` i join `tabEquipment Needs Request` r on r.name = i.parent
		where i.repeat_flag = 1 and r.name in %(requests)s
		order by r.request_date desc""",
		{"requests": tuple(requests)},
		as_dict=True,
	)
	return get_columns(), data
