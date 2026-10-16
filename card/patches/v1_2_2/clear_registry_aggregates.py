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
		meta = frappe.get_meta(registry)
		table = frappe.qb.DocType(registry)
		query = frappe.qb.update(table)
		touched = False
		for field in fields:
			df = meta.get_field(field)
			if not df or not frappe.db.has_column(registry, field):
				continue
			# numeric columns are NOT NULL in Frappe: their "empty" value is 0
			numeric = df.fieldtype in ("Int", "Float", "Currency", "Percent")
			query = query.set(table[field], 0 if numeric else None)
			touched = True
		if touched:
			query.run()
