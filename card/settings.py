# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Card Settings (Single) readers. Every value falls back to the baseline
default so behaviour is unchanged when a value is unconfigured. Reads the
raw Singles row directly so a MISSING row (never configured) is distinguished
from an explicit 0/empty — frappe.db.get_single_value casts a missing numeric
field to 0.0, which would mask the default."""

import frappe

_DEFAULTS = {
	"enable_accounting": 0,
	"auto_submit": 0,
	"default_shift": "نهاري",
	"max_day_shift_hours": 12.0,
	"max_night_shift_hours": 12.0,
	"default_daily_hours": 0.0,
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
	# F.5: calculation bases
	"default_rate_basis": "",
	"standard_month_hours": 260.0,
	# F.1: diesel supplier policy + per-project transport prices
	"diesel_supplier_policy": "متغير",
	"diesel_supplier": "",
	"diesel_supplier_editor_role": "Card Manager",
	"transport_price_editor_role": "Card Manager",
	# FR-002: diesel price exceptions; zero price stays refused until a role is named
	"diesel_price_exception_role": "Accounts Manager",
	"diesel_zero_price_role": None,
	# #56: the daily location sync is off until the owner enables it
	"sync_equipment_location_daily": 0,
	# v4.0.0: equipment materials
	"default_store_warehouse": "",
	"tool_custody_warehouse": "",
	"repeat_request_days": 30,
	# FR-099/FR-100: meters and maintenance (replace equipment_manager)
	"default_service_interval_hours": 300.0,
	"maintenance_warn_before_hours": 50.0,
	"max_meter_hours_per_day": 24.0,
	"notify_maintenance_due": 1,
	"auto_create_due_orders": 0,
	"warranty_alert_days": 30,
}


def setting(fieldname):
	"""Return a Card Settings value, or its baseline default when the field
	has no stored Singles row (never configured) or is empty."""
	row = frappe.db.sql(
		"select value from tabSingles where doctype='Card Settings' and field=%s",
		fieldname,
	)
	val = row[0][0] if row else None
	if val is None or val == "":
		return _DEFAULTS.get(fieldname)
	default = _DEFAULTS.get(fieldname)
	if isinstance(default, int | float):
		try:
			return float(val)
		except (TypeError, ValueError):
			return default
	return val
