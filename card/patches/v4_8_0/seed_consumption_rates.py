# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-144 (#31, #42, #47): give each equipment that has a static expected consumption (litres per hour) and no
dated consumption rate one rate row with that value, valid from the day the equipment was created.

consumption_rate() returns the same value as before on every date: from the row's date on it reads the row (the
same value), and before that date it falls back to the static field, which is left unchanged. Equipment with no
static value (empty or 0) gets no row and keeps returning no rate. Card Equipment Type has no static rate, so no
type row is created. daily_diesel_consumption (litres per standard day) is a different unit and is not converted.

Idempotent: an equipment that already has a rate row is skipped, so a second migrate adds nothing. The rows are
inserted on their own (no save of the equipment), so the equipment is not re-validated and its modified time and
change history stay as they are."""

import frappe
from frappe.utils import flt, getdate

ROW_DOCTYPE = "Card Consumption Rate"
PARENTFIELD = "consumption_rates"
STATIC_FIELD = "expected_consumption"
REASON = "Seeded from the static expected consumption (FR-144)"


def execute():
	if not frappe.db.table_exists(ROW_DOCTYPE) or not frappe.db.has_column("Card Equipment", STATIC_FIELD):
		return
	equipment = frappe.get_all(
		"Card Equipment",
		filters={STATIC_FIELD: [">", 0]},
		fields=["name", "creation", STATIC_FIELD],
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
		frappe.get_doc(
			{
				"doctype": ROW_DOCTYPE,
				"parent": row.name,
				"parenttype": "Card Equipment",
				"parentfield": PARENTFIELD,
				"idx": 1,
				"valid_from": getdate(row.creation),
				"litres_per_hour": flt(row.get(STATIC_FIELD)),
				"reason": REASON,
			}
		).db_insert()
		frappe.clear_document_cache("Card Equipment", row.name)
