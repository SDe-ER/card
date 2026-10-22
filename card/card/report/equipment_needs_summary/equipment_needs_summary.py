# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.utils import flt

from card.materials import stock_by_item
from card.report_access import permitted_companies, strip_ledger


def get_columns():
	return [
		{
			"fieldname": "item_code",
			"label": _("Needed item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{"fieldname": "description", "label": _("Description"), "fieldtype": "Data", "width": 180},
		{"fieldname": "requested_qty", "label": _("Requested qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "found_qty", "label": _("Found on site"), "fieldtype": "Float", "width": 110},
		{"fieldname": "approved_qty", "label": _("Approved qty"), "fieldtype": "Float", "width": 100},
		{"fieldname": "stock_qty", "label": _("In stock"), "fieldtype": "Float", "width": 100},
		{"fieldname": "equipment", "label": _("Equipment and quantities"), "fieldtype": "Data", "width": 260},
		{"fieldname": "reviews", "label": _("Reviews"), "fieldtype": "Data", "width": 160},
	]


def execute(filters=None):
	# Report: "Equipment Needs Summary" — the one consolidated list management reviews:
	# every submitted supervisor review line, merged by item, keeping each machine's share.
	filters = frappe._dict(filters or {})
	companies = permitted_companies("Equipment Needs Review")
	if not companies:
		return get_columns(), []
	conditions = {"docstatus": 1, "company": ["in", companies]}
	if filters.get("project"):
		conditions["project"] = filters.project
	if filters.get("approval_status"):
		conditions["approval_status"] = filters.approval_status
	# get_list: the user's own record rules apply (e.g. a supervisor limited to his projects)
	reviews = frappe.get_list("Equipment Needs Review", filters=conditions, pluck="name", limit_page_length=0)
	if not reviews:
		return get_columns(), []
	lines = frappe.get_all(
		"Equipment Needs Review Item",
		filters={"parent": ["in", reviews], "parenttype": "Equipment Needs Review"},
		fields=[
			"parent",
			"item_code",
			"description",
			"equipment",
			"requested_qty",
			"found_qty",
			"approved_qty",
		],
	)
	grouped = {}
	for line in lines:
		key = line.item_code or (line.description or "").strip()
		entry = grouped.setdefault(
			key,
			{
				"item_code": line.item_code,
				"description": line.description,
				"requested_qty": 0.0,
				"found_qty": 0.0,
				"approved_qty": 0.0,
				"shares": {},
				"reviews": set(),
			},
		)
		entry["requested_qty"] += flt(line.requested_qty)
		entry["found_qty"] += flt(line.found_qty)
		entry["approved_qty"] += flt(line.approved_qty)
		entry["shares"][line.equipment] = entry["shares"].get(line.equipment, 0) + flt(line.approved_qty)
		entry["reviews"].add(line.parent)
	# stock only for a user who may read it, in the warehouses of the report's companies (F2)
	stock = stock_by_item({e["item_code"] for e in grouped.values() if e["item_code"]}, companies=companies)
	data = []
	for key in sorted(grouped):
		entry = grouped[key]
		data.append(
			{
				"item_code": entry["item_code"],
				"description": entry["description"],
				"requested_qty": entry["requested_qty"],
				"found_qty": entry["found_qty"],
				"approved_qty": entry["approved_qty"],
				"stock_qty": stock[entry["item_code"]] if stock is not None and entry["item_code"] else None,
				"equipment": ", ".join(f"{eq}: {flt(qty):g}" for eq, qty in sorted(entry["shares"].items())),
				"reviews": ", ".join(sorted(entry["reviews"])),
			}
		)
	columns = get_columns()
	if stock is None:
		columns, _summary = strip_ledger(columns, data, [], ("stock_qty",), ())
	return columns, data
