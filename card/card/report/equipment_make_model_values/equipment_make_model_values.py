# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _

from card.fitment import normalise


def get_columns():
	return [
		{"fieldname": "brand", "label": _("Brand (text)"), "fieldtype": "Data", "width": 160},
		{"fieldname": "model", "label": _("Model (text)"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "equipment_type",
			"label": _("Equipment type"),
			"fieldtype": "Link",
			"options": "Card Equipment Type",
			"width": 150,
		},
		{"fieldname": "equipment_count", "label": _("Equipment count"), "fieldtype": "Int", "width": 120},
		{
			"fieldname": "equipment_make",
			"label": _("Equipment make"),
			"fieldtype": "Link",
			"options": "Card Equipment Make",
			"width": 150,
		},
		{
			"fieldname": "equipment_model",
			"label": _("Equipment model"),
			"fieldtype": "Link",
			"options": "Card Equipment Model",
			"width": 150,
		},
	]


def execute(filters=None):
	# Report: "Equipment Make Model Values" (FR-077) — the free-text brand / model values
	# of the equipment, grouped after normalising, so a Card Manager can create the make
	# and model records by hand. Read only: nothing is matched or written automatically.
	filters = frappe._dict(filters or {})
	conditions = {"equipment_model": ["is", "not set"]} if filters.get("unlinked_only") else {}
	# get_list: the user's own record rules apply (company User Permissions)
	rows = frappe.get_list(
		"Card Equipment",
		filters=conditions,
		fields=["brand", "model", "equipment_type", "equipment_make", "equipment_model"],
		limit_page_length=0,
	)
	groups = {}
	for row in rows:
		key = (
			normalise(row.brand),
			normalise(row.model),
			row.equipment_type,
			row.equipment_make,
			row.equipment_model,
		)
		group = groups.get(key)
		if group:
			group["equipment_count"] += 1
			continue
		groups[key] = {
			"brand": (row.brand or "").strip(),
			"model": (row.model or "").strip(),
			"equipment_type": row.equipment_type,
			"equipment_count": 1,
			"equipment_make": row.equipment_make,
			"equipment_model": row.equipment_model,
		}
	data = sorted(
		groups.values(), key=lambda r: (r["brand"].upper(), r["model"].upper(), r["equipment_type"] or "")
	)
	return get_columns(), data
