# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-138 (#123, #44; C-05): give every equipment saved before v4.8.0 the default day billing basis.

The default, "Prorated by hours", is the behaviour every card had before FR-138, and the card
controller already reads an empty value as that default; this patch only makes the stored value
explicit so the form shows it. Only equipment rows with an empty value are written, without a new
modified time; no card is touched or repriced. Idempotent: a second migrate finds no empty row."""

import frappe

from card.card_value import DAY_BASIS_PRORATED

FIELD = "day_billing_basis"


def execute():
	if not frappe.db.table_exists("Card Equipment") or not frappe.db.has_column("Card Equipment", FIELD):
		return
	names = frappe.get_all(
		"Card Equipment",
		filters=[[FIELD, "is", "not set"]],
		pluck="name",
		limit_page_length=0,
	)
	for name in names:
		frappe.db.set_value("Card Equipment", name, FIELD, DAY_BASIS_PRORATED, update_modified=False)
