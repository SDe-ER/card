# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Card Settings (Single) readers. Every value falls back to the baseline
default so behaviour is unchanged when a value is unconfigured. Reads the
raw Singles row directly so a MISSING row (never configured) is distinguished
from an explicit 0/empty — frappe.db.get_single_value casts a missing numeric
field to 0.0, which would mask the default."""

import frappe
from frappe import _

# FR-124 (WP-08): the two deprecated Card Settings fields (docs/governance/SETTINGS-AND-CONSTANTS.md section 4)
# are hidden, read only and never read, so they have no default here. Their columns and stored values stay.
_DEFAULTS = {
	"enable_accounting": 0,
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


def company_setting(company, fieldname):
	"""A value of the company's row in Card Settings > Company settings, or None when the
	company has no row or the value is empty. No company is ever assumed."""
	if not company:
		return None
	value = frappe.db.get_value(
		"Card Company Settings",
		{
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": "company_settings",
			"company": company,
		},
		fieldname,
	)
	return value or None


# FR-135 (#50, #126): materials values per company. The company's row in Card Settings > Company
# settings wins; when it is empty (no row, no warehouse, 0 days) the site-wide Card Settings value
# applies, so an unconfigured company behaves exactly as before.
_COMPANY_SITE_FALLBACK = {
	"store_warehouse": "default_store_warehouse",
	"custody_warehouse": "tool_custody_warehouse",
	"repeat_request_days": "repeat_request_days",
}
COMPANY_WAREHOUSE_FIELDS = ("store_warehouse", "custody_warehouse")


def company_or_site_setting(company, fieldname):
	"""The company's value of `fieldname`, or the site-wide Card Settings value when the company
	has none. No company: the site value."""
	value = company_setting(company, fieldname)
	if fieldname == "repeat_request_days":
		try:
			value = int(value or 0)
		except (TypeError, ValueError):
			value = 0
		if value > 0:
			return value
		value = None
	if value:
		return value
	return setting(_COMPANY_SITE_FALLBACK[fieldname])


def _company_warehouse(company, fieldname, strict):
	"""The company's warehouse in `fieldname`, checked again at read time: one that belongs to
	another company (saved before the check, or the warehouse moved) is refused, or with
	strict=False not offered. Empty: the site value, as before."""
	value = company_setting(company, fieldname)
	if not value:
		return setting(_COMPANY_SITE_FALLBACK[fieldname]) or None
	owner = frappe.db.get_value("Warehouse", value, "company")
	if owner != company:
		if not strict:
			return None
		frappe.throw(
			_("Card Settings: warehouse {0} belongs to company {1}, not {2}.").format(
				value, owner or "-", company
			)
		)
	return value


def store_warehouse(company, strict=True):
	"""The main store of `company` (FR-135), else the site's main store."""
	return _company_warehouse(company, "store_warehouse", strict)


def custody_warehouse(company, strict=True):
	"""The tool custody store of `company` (FR-135), else the site's tool custody store."""
	return _company_warehouse(company, "custody_warehouse", strict)


def repeat_request_days(company):
	"""The repeated-request window in days of `company` (FR-135), else the site value (30 by
	default)."""
	try:
		days = int(float(company_or_site_setting(company, "repeat_request_days") or 0))
	except (TypeError, ValueError):
		days = 0
	return days or 30


def validate_company_warehouses(doc):
	"""FR-135: a store or custody warehouse on a company row must belong to that row's company.
	Called from Card Settings validation; empty values are allowed (the site value applies)."""
	for row in doc.get("company_settings") or []:
		for fieldname in COMPANY_WAREHOUSE_FIELDS:
			warehouse = row.get(fieldname)
			if not warehouse:
				continue
			owner = frappe.db.get_value("Warehouse", warehouse, "company")
			if owner != row.company:
				frappe.throw(
					_("Card Settings: warehouse {0} belongs to company {1}, not {2}.").format(
						warehouse, owner or "-", row.company
					)
				)
