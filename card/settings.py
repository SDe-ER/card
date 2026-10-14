# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Card Settings (Single) readers. Every value falls back to the baseline
default so behaviour is unchanged when settings are unconfigured."""

import frappe

_DEFAULTS = {
	"enable_accounting": 0,
	"auto_submit": 0,
	"default_shift": "نهاري",
	"max_hours_per_day": 24,
	"default_daily_hours": 0,
	"default_fuel_charged_to": "",
	"default_operator_on": "",
	"reconciliation_tolerance": 0.01,
	"warn_on_shift_hours_exceeded": 1,
	"warn_outside_rental_period": 1,
	"default_statement_type": "مورد",
	"include_draft_in_reports": 0,
	"period_lock_date": None,
	"period_lock_override_role": None,
	"notify_on_card_submit": 0,
	"notify_on_posting": 0,
	"notify_on_period_lock_override": 0,
}


def setting(fieldname):
	"""Return a Card Settings value, or its baseline default when unset."""
	try:
		val = frappe.db.get_single_value("Card Settings", fieldname)
	except Exception:
		val = None
	if val is None or val == "":
		return _DEFAULTS.get(fieldname)
	return val
