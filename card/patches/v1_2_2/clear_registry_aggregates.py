# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""#23: a CARD party registry row (Card Equipment Supplier / Customer) is per
party across every company, so the figures stored on it (counts, hours, totals,
first/last month) mixed companies and were readable by any report role. They
are no longer stored — the form computes them per company the user may see
(card.api.party_figures). Clear the stored values. Derived data only: every
figure is recomputable from the monthly cards; no card or accounting document
is touched. Idempotent."""

import frappe

FIELDS = {
	"Card Equipment Supplier": (
		"first_month",
		"last_month",
		"equipment_count",
		"card_count",
		"total_hours",
		"total_net",
		"last_refreshed",
	),
	"Card Equipment Customer": (
		"first_month",
		"last_month",
		"equipment_count",
		"card_count",
		"total_hours",
		"total_accrued",
		"last_refreshed",
	),
}


def execute():
	for registry, fields in FIELDS.items():
		if not frappe.db.table_exists(registry):
			continue
		present = [f for f in fields if frappe.db.has_column(registry, f)]
		if present:
			frappe.db.sql(
				"update `tab{}` set {}".format(registry, ", ".join(f"`{f}` = null" for f in present))
			)
