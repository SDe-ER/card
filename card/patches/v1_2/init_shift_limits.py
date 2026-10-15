# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Initialise the per-shift hour limits on the Card Settings Single. They
replace the former single daily limit. Frappe does not backfill a Single's
stored values for newly added fields, so an existing Single would read 0.0.
Idempotent: writes 12 only for a limit that has never been stored
(no tabSingles row) or is empty."""

import frappe

FIELDS = ("max_day_shift_hours", "max_night_shift_hours")
DEFAULT = 12


def execute():
	if not frappe.db.exists("DocType", "Card Settings"):
		return
	stored = {
		field: value
		for field, value in frappe.db.sql(
			"select field, value from tabSingles where doctype='Card Settings' and field in %s",
			(FIELDS,),
		)
		if value not in (None, "")
	}
	missing = [f for f in FIELDS if f not in stored]
	if not missing:
		return
	for fieldname in missing:
		frappe.db.set_single_value("Card Settings", fieldname, DEFAULT)
