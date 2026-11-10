# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-144 (#31, #42, #47): effective-dated diesel consumption rates in litres per operating hour.

A rate row (Card Consumption Rate) holds `valid_from` and `litres_per_hour`. It sits on a Card Equipment Type
(`default_consumption_rates`, the type default) or on a Card Equipment (`consumption_rates`, its override). A row is
valid from its date until the next row of the same table; there is no end date.

`consumption_rate(equipment, on_date)` resolves, in this order:
1. the equipment's own row valid on the date;
2. the row of the equipment's type valid on the date;
3. the equipment's static `expected_consumption` (the field kept as the fallback);
4. None (no rate: a caller must not divide by it or invent one).

It reads only and checks no permission: it is an internal helper and is not whitelisted. A rate is equipment data,
not an amount; on Card Equipment the table keeps the permlevel of the static field (level 1).

No existing caller is switched to it: the Equipment Diesel Analysis report keeps its own basis (FR-033)."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate

EQUIPMENT_TABLE = "consumption_rates"
TYPE_TABLE = "default_consumption_rates"
STATIC_FIELD = "expected_consumption"
ROW_DOCTYPE = "Card Consumption Rate"

SOURCE_EQUIPMENT = "Equipment"
SOURCE_TYPE = "Equipment type"
SOURCE_STATIC = "Static"


def _row_on(parenttype, parent, parentfield, on_date):
	"""The row of one rate table with the latest valid_from on or before `on_date`, or None."""
	rows = frappe.get_all(
		ROW_DOCTYPE,
		filters={
			"parenttype": parenttype,
			"parent": parent,
			"parentfield": parentfield,
			"valid_from": ["<=", on_date],
		},
		fields=["litres_per_hour", "valid_from"],
		order_by="valid_from desc, idx desc",
		limit=1,
	)
	return rows[0] if rows else None


def consumption_rate_details(equipment, on_date=None):
	"""The rate `consumption_rate` returns, with where it came from: `source` (Equipment, Equipment type,
	Static or None) and the row's `valid_from` (None for the static field). Read-only."""
	empty = frappe._dict(rate=None, source=None, valid_from=None)
	if not equipment:
		return empty
	values = frappe.db.get_value(
		"Card Equipment", equipment, ["name", "equipment_type", STATIC_FIELD], as_dict=True
	)
	if not values:
		return empty
	on_date = getdate(on_date or nowdate())
	row = _row_on("Card Equipment", values.name, EQUIPMENT_TABLE, on_date)
	if row:
		return frappe._dict(rate=flt(row.litres_per_hour), source=SOURCE_EQUIPMENT, valid_from=row.valid_from)
	if values.equipment_type:
		row = _row_on("Card Equipment Type", values.equipment_type, TYPE_TABLE, on_date)
		if row:
			return frappe._dict(rate=flt(row.litres_per_hour), source=SOURCE_TYPE, valid_from=row.valid_from)
	static = flt(values.get(STATIC_FIELD))
	if static:
		return frappe._dict(rate=static, source=SOURCE_STATIC, valid_from=None)
	return empty


def consumption_rate(equipment, on_date=None):
	"""Litres per operating hour of `equipment` on `on_date` (today when empty), or None. Read-only."""
	return consumption_rate_details(equipment, on_date).rate


def validate_consumption_rates(doc, parentfield):
	"""Parent validate: each row has a date and a rate of zero or more, and no two rows of the table start on
	the same date (with no end date, the same start date is the only possible overlap)."""
	seen = {}
	for row in doc.get(parentfield) or []:
		if not row.valid_from:
			frappe.throw(_("Row {0}: enter the date the consumption rate is valid from.").format(row.idx))
		if flt(row.litres_per_hour) < 0:
			frappe.throw(_("Row {0}: the consumption rate cannot be negative.").format(row.idx))
		day = getdate(row.valid_from)
		if day in seen:
			frappe.throw(
				_("Rows {0} and {1} both start a consumption rate on {2}. Keep one row per date.").format(
					seen[day], row.idx, formatdate(day)
				),
				title=_("Duplicate consumption rate"),
			)
		seen[day] = row.idx


def warn_static_rate_shadowed(doc):
	"""Card Equipment validate: a change to the static expected consumption is only a fallback once the
	equipment has dated rates; say so (warning only, nothing is refused or changed)."""
	if doc.is_new() or not doc.get(EQUIPMENT_TABLE) or not doc.has_value_changed(STATIC_FIELD):
		return
	frappe.msgprint(
		_(
			"This equipment has dated consumption rates. They decide the rate from their dates; the expected"
			" consumption (liter/hour) is used only before the first dated rate."
		),
		indicator="orange",
		alert=True,
	)
