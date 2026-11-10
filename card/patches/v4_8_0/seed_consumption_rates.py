# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-144 (#31, #42, #47): give each equipment that has a static expected consumption (litres per hour), no daily
standard basis and no dated consumption rate one rate row with that value, valid from 2000-01-01 (SEED_FROM).

consumption_rate() returns the same value as before on every date: the row holds the static value, which is left
unchanged and still answers a date before SEED_FROM. Skipped, so they keep their value too:
- equipment with no static value (empty or 0): no rate before, none after;
- equipment with daily_diesel_consumption and daily_hours set: its rate is daily / daily_hours (the basis Equipment
  Diesel Analysis uses first), which a seeded row would override.
Card Equipment Type has no static rate, so no type row is created.

Idempotent: an equipment that already has a rate row is skipped, so a second migrate adds nothing. The rows are
inserted on their own (no save of the equipment), so the equipment is not re-validated and its modified time and
change history stay as they are."""

import frappe
from frappe.utils import flt, getdate

ROW_DOCTYPE = "Card Consumption Rate"
PARENTFIELD = "consumption_rates"
STATIC_FIELD = "expected_consumption"
REASON = "Seeded from the static expected consumption (FR-144)"
SEED_FROM = "2000-01-01"


def execute():
	if not frappe.db.table_exists(ROW_DOCTYPE) or not frappe.db.has_column("Card Equipment", STATIC_FIELD):
		return
	equipment = frappe.get_all(
		"Card Equipment",
		filters={STATIC_FIELD: [">", 0]},
		fields=["name", STATIC_FIELD, "daily_diesel_consumption", "daily_hours"],
		order_by="creation asc",
		limit_page_length=0,
	)
	if not equipment:
		return
	seeded = set(
		frappe.get_all(
			ROW_DOCTYPE,
			filters={"parenttype": "Card Equipment", "parentfield": PARENTFIELD},
			pluck="parent",
			distinct=True,
			limit_page_length=0,
		)
	)
	for row in equipment:
		if row.name in seeded:
			continue
		if flt(row.daily_diesel_consumption) and flt(row.daily_hours) > 0:
			continue
		frappe.get_doc(
			{
				"doctype": ROW_DOCTYPE,
				"parent": row.name,
				"parenttype": "Card Equipment",
				"parentfield": PARENTFIELD,
				"idx": 1,
				"valid_from": getdate(SEED_FROM),
				"litres_per_hour": flt(row.get(STATIC_FIELD)),
				"reason": REASON,
			}
		).db_insert()
		frappe.clear_document_cache("Card Equipment", row.name)
