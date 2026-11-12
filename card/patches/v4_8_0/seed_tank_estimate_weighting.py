# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-157 (#31, #47, #124; closure plan WP-G1, C-03): give every Card Company Settings row
saved before v4.8.0 the default tank estimate weighting ``Hours (tank estimate)``.

"Hours" matches the behaviour every tank diesel fill had before FR-157: the FR-033 read-time
estimate splits the litres by operating hours. The controller already reads an empty value as
this default; this patch only makes the stored value explicit so the form shows it. Only rows
with an empty value are written, without a new modified time; no diesel fill is touched or
re-allocated. Idempotent: a second migrate finds no empty row.
"""

import frappe

from card.diesel_fill_allocation import HOURS_WEIGHTING

FIELD = "tank_estimate_weighting"


def execute():
	if not frappe.db.table_exists("Card Company Settings") or not frappe.db.has_column(
		"Card Company Settings", FIELD
	):
		return
	names = frappe.get_all(
		"Card Company Settings",
		or_filters=[[FIELD, "is", "not set"], [FIELD, "=", ""]],
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Card Company Settings", name, FIELD, HOURS_WEIGHTING, update_modified=False)
