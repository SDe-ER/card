# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-134 (#45): fill the per-side billable stopped hours of monthly cards saved before v4.8.0.

Before FR-134 every billable stop reason billed both sides (FR-118), so a card's supplier and
customer billable stopped hours both equal its billable_stopped_hours. Only cards with billable
stopped hours and no per-side figure are written; the amounts, the day rows and the modified
time are left unchanged, so no card is repriced. Idempotent: a second migrate finds no such card.
Statements also fall back to the total at read time (card_stop_reason.side_stopped_hours)."""

import frappe

FIELDS = ("supplier_billable_stopped_hours", "customer_billable_stopped_hours")


def execute():
	if not frappe.db.table_exists("Card Monthly Card"):
		return
	if not all(frappe.db.has_column("Card Monthly Card", f) for f in FIELDS):
		return
	cards = frappe.get_all(
		"Card Monthly Card",
		filters={
			"billable_stopped_hours": [">", 0],
			FIELDS[0]: 0,
			FIELDS[1]: 0,
		},
		fields=["name", "billable_stopped_hours"],
		limit_page_length=0,
	)
	for card in cards:
		frappe.db.set_value(
			"Card Monthly Card",
			card.name,
			{f: card.billable_stopped_hours for f in FIELDS},
			update_modified=False,
		)
