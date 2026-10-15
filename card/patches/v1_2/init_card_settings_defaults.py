# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Initialise the Card Settings Single with the doctype defaults for the policy
fields. Frappe does NOT backfill a Single's stored values when new fields with
defaults are added by a migration, so an existing Single returns 0/'' for the
new Operations/Period-Lock/Notifications fields (e.g. reconciliation_tolerance
would read 0.0 instead of 0.01, warnings would read off). This one-time,
idempotent patch writes the meta default for any field that has never been
stored (no tabSingles row), so behaviour matches the intended baseline."""

import frappe
from frappe.utils import cint, flt

FIELDS = (
	"enable_accounting",
	"auto_submit",
	"default_shift",
	"default_daily_hours",
	"default_fuel_charged_to",
	"default_operator_on",
	"reconciliation_tolerance",
	"warn_on_shift_hours_exceeded",
	"warn_outside_rental_period",
	"default_statement_type",
	"include_draft_in_reports",
	"notify_on_card_submit",
	"notify_on_posting",
	"notify_on_period_lock_override",
)


def execute():
	if not frappe.db.exists("DocType", "Card Settings"):
		return
	meta = frappe.get_meta("Card Settings")
	stored = set(frappe.db.sql_list("select field from tabSingles where doctype='Card Settings'"))
	doc = frappe.get_single("Card Settings")
	changed = False
	for fieldname in FIELDS:
		df = meta.get_field(fieldname)
		if not df or fieldname in stored or df.default is None:
			continue
		if df.fieldtype in ("Check", "Int"):
			value = cint(df.default)
		elif df.fieldtype in ("Float", "Currency", "Percent"):
			value = flt(df.default)
		else:
			value = df.default
		doc.set(fieldname, value)
		changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
