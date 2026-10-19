# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.utils import flt

from card.materials import custody_balances
from card.report_access import permitted_companies


def get_columns():
	return [
		{
			"fieldname": "employee",
			"label": _("Employee"),
			"fieldtype": "Link",
			"options": "Employee",
			"width": 140,
		},
		{"fieldname": "employee_name", "label": _("Employee name"), "fieldtype": "Data", "width": 160},
		{"fieldname": "item_code", "label": _("Tool"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "qty", "label": _("Held"), "fieldtype": "Float", "width": 90},
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 140},
		{"fieldname": "kind", "label": _("Kind"), "fieldtype": "Data", "width": 120},
	]


def execute(filters=None):
	# Report: "Worker Custody" — what each worker holds now: returnable tools from the
	# custody register, plus capital tools recorded as Assets with him as custodian.
	filters = frappe._dict(filters or {})
	companies = permitted_companies("Employee Tool Custody")
	if not companies:
		return get_columns(), []
	balances = custody_balances({"company": ["in", companies]})
	data = []
	for (employee, item_code), held in sorted(balances.items()):
		if flt(held) <= 0 or (filters.get("employee") and employee != filters.employee):
			continue
		data.append(
			{
				"employee": employee,
				"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
				"item_code": item_code,
				"qty": held,
				"kind": _("Returnable tool"),
			}
		)
	asset_filters = {
		"docstatus": 1,
		"company": ["in", companies],
		"custodian": ["is", "set"],
		"status": ["not in", ["Scrapped", "Sold"]],
	}
	if filters.get("employee"):
		asset_filters["custodian"] = filters.employee
	for asset in frappe.get_all("Asset", filters=asset_filters, fields=["name", "custodian", "item_code"]):
		data.append(
			{
				"employee": asset.custodian,
				"employee_name": frappe.db.get_value("Employee", asset.custodian, "employee_name"),
				"item_code": asset.item_code,
				"qty": 1,
				"asset": asset.name,
				"kind": _("Asset"),
			}
		)
	return get_columns(), data
