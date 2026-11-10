# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-144 (#31, #42, #47): effective-dated diesel consumption rates in litres per operating hour.

Two child tables hold dated rows (`valid_from`, `litres_per_hour`, `reason`); a row is valid from its date until
the next row of the same table (and, on a type, of the same company), with no end date:
- Card Equipment `consumption_rates` (Card Consumption Rate): the equipment's own rates. Every field is at
  permlevel 1, the level of the static `expected_consumption`, so Frappe applies the equipment's level-1 rights to
  the rows on every path (form, REST get/get_list/get_value, report view fields and filters, change history).
- Card Equipment Type `default_consumption_rates` (Card Type Consumption Rate): the type default, for one company
  (`company`) or for every company (empty). Level-0 fields (the type has no level-1 DocPerms); only Card Manager and
  System Manager change them, and a company-restricted user only rows of a permitted company or with no company
  (validate_type_rate_changes).

`consumption_rate(equipment, on_date)` resolves, in this order:
1. the equipment's own row valid on the date;
2. "daily standard": daily_diesel_consumption / daily_hours when both are set (the basis Equipment Diesel Analysis
   uses first, FR-033), so the helper equals that report for every existing equipment;
3. the equipment's static `expected_consumption` (0 = not set);
4. the type row valid on the date for the equipment's company, else the type row with no company;
5. None (no rate: a caller must not divide by it or invent one).

A row whose valid_from is before today is final: its date, rate, company and reason cannot change and it cannot be
deleted; a correction is a new row with a reason, and a new backdated row needs a reason too.

Known limit: the type step reads the equipment's CURRENT type, also for past dates (a type change is not dated).

It reads only and checks no permission: an internal helper, not whitelisted. A rate is equipment data, not an
amount. No existing caller is switched to it."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate

EQUIPMENT_TABLE = "consumption_rates"
TYPE_TABLE = "default_consumption_rates"
STATIC_FIELD = "expected_consumption"
EQUIPMENT_ROW_DOCTYPE = "Card Consumption Rate"
TYPE_ROW_DOCTYPE = "Card Type Consumption Rate"
RATE_MANAGER_ROLES = ("Card Manager", "System Manager")

SOURCE_EQUIPMENT = "Equipment"
SOURCE_DAILY = "Daily standard"
SOURCE_STATIC = "Static"
SOURCE_TYPE = "Equipment type"


def _row_on(doctype, parenttype, parent, parentfield, on_date, **extra):
	"""The row of one rate table with the latest valid_from on or before `on_date`, or None."""
	rows = frappe.get_all(
		doctype,
		filters={
			"parenttype": parenttype,
			"parent": parent,
			"parentfield": parentfield,
			"valid_from": ["<=", on_date],
			**extra,
		},
		fields=["litres_per_hour", "valid_from"],
		order_by="valid_from desc, idx desc",
		limit=1,
	)
	return rows[0] if rows else None


def _result(rate, source, valid_from=None):
	return frappe._dict(rate=rate, source=source, valid_from=valid_from)


def consumption_rate_details(equipment, on_date=None):
	"""The rate `consumption_rate` returns, with where it came from: `source` (Equipment, Daily standard, Static,
	Equipment type or None) and the row's `valid_from` (None when no row decided). Read-only."""
	if not equipment:
		return _result(None, None)
	values = frappe.db.get_value(
		"Card Equipment",
		equipment,
		["name", "company", "equipment_type", STATIC_FIELD, "daily_diesel_consumption", "daily_hours"],
		as_dict=True,
	)
	if not values:
		return _result(None, None)
	on_date = getdate(on_date or nowdate())
	row = _row_on(EQUIPMENT_ROW_DOCTYPE, "Card Equipment", values.name, EQUIPMENT_TABLE, on_date)
	if row:
		return _result(flt(row.litres_per_hour), SOURCE_EQUIPMENT, row.valid_from)
	# FR-033 parity: Equipment Diesel Analysis uses this basis before the per-hour field
	if flt(values.daily_diesel_consumption) and flt(values.daily_hours) > 0:
		return _result(flt(values.daily_diesel_consumption) / flt(values.daily_hours), SOURCE_DAILY)
	static = flt(values.get(STATIC_FIELD))
	if static:
		return _result(static, SOURCE_STATIC)
	if values.equipment_type:
		row = None
		if values.company:
			row = _row_on(
				TYPE_ROW_DOCTYPE,
				"Card Equipment Type",
				values.equipment_type,
				TYPE_TABLE,
				on_date,
				company=values.company,
			)
		if not row:
			row = _row_on(
				TYPE_ROW_DOCTYPE,
				"Card Equipment Type",
				values.equipment_type,
				TYPE_TABLE,
				on_date,
				company=["is", "not set"],
			)
		if row:
			return _result(flt(row.litres_per_hour), SOURCE_TYPE, row.valid_from)
	return _result(None, None)


def consumption_rate(equipment, on_date=None):
	"""Litres per operating hour of `equipment` on `on_date` (today when empty), or None. Read-only."""
	return consumption_rate_details(equipment, on_date).rate


# ---------- validation (called from the parents' validate) ----------


def validate_consumption_rates(doc, parentfield):
	"""Each row has a date and a rate of zero or more; no two rows of the table (of one company, on a type) start
	on the same date; rows dated before today are final (validate_past_rows)."""
	seen = {}
	for row in doc.get(parentfield) or []:
		if not row.valid_from:
			frappe.throw(_("Row {0}: enter the date the consumption rate is valid from.").format(row.idx))
		if flt(row.litres_per_hour) < 0:
			frappe.throw(_("Row {0}: the consumption rate cannot be negative.").format(row.idx))
		key = (row.get("company") or None, getdate(row.valid_from))
		if key in seen:
			frappe.throw(
				_("Rows {0} and {1} both start a consumption rate on {2}. Keep one row per date.").format(
					seen[key], row.idx, formatdate(key[1])
				),
				title=_("Duplicate consumption rate"),
			)
		seen[key] = row.idx
	validate_past_rows(doc, parentfield)


def _fields(row):
	"""The comparable values of a rate row (date, rate, reason, company)."""
	return (
		getdate(row.valid_from) if row.get("valid_from") else None,
		flt(row.get("litres_per_hour")),
		(row.get("reason") or "").strip() or None,
		row.get("company") or None,
	)


def validate_past_rows(doc, parentfield):
	"""#31 auditability: a row whose valid_from is before today is final. Its fields cannot change and it cannot be
	removed; a correction is a new row with a reason. A new row dated before today needs a reason."""
	today = getdate(nowdate())
	before = doc.get_doc_before_save() if not doc.is_new() else None
	old = {r.name: r for r in (before.get(parentfield) if before else None) or []}
	current = {r.name: r for r in doc.get(parentfield) or [] if r.name}
	for name, row in old.items():
		if not row.valid_from or getdate(row.valid_from) >= today:
			continue
		new = current.get(name)
		if new is None:
			frappe.throw(
				_(
					"The consumption rate valid from {0} is already in use and cannot be removed. Add a new row"
					" with a reason instead."
				).format(formatdate(row.valid_from)),
				title=_("Consumption rate in use"),
			)
		if _fields(new) != _fields(row):
			frappe.throw(
				_(
					"The consumption rate valid from {0} is already in use and cannot be changed. Add a new row"
					" with a reason instead."
				).format(formatdate(row.valid_from)),
				title=_("Consumption rate in use"),
			)
	for row in doc.get(parentfield) or []:
		if row.name in old or not row.valid_from or getdate(row.valid_from) >= today:
			continue
		if not (row.get("reason") or "").strip():
			frappe.throw(
				_("Row {0}: a consumption rate dated before today needs a reason.").format(row.idx),
				title=_("Reason required"),
			)


def _type_rows(doc):
	return {
		(r.name or "new-%s" % r.idx): (r.get("company") or None, _fields(r))
		for r in doc.get(TYPE_TABLE) or []
	}


def validate_type_rate_changes(doc):
	"""Card Equipment Type validate: only Card Manager and System Manager add, change or remove default rate rows
	(no DocPerm is added: Card User keeps writing the other type fields). A company-restricted user may only touch
	rows of a permitted company; a row with no company applies to every company, so only an unrestricted user adds,
	changes or removes it. Unchanged rows are never checked."""
	before = doc.get_doc_before_save() if not doc.is_new() else None
	old = _type_rows(before) if before else {}
	new = _type_rows(doc)
	# an edited row counts with its old and its new values (a row moved between companies touches both)
	touched = [v for k, v in new.items() if old.get(k) != v]
	touched += [v for k, v in old.items() if k not in new or new[k] != v]
	if not touched:
		return
	user = frappe.session.user
	if user != "Administrator" and not set(RATE_MANAGER_ROLES) & set(frappe.get_roles(user)):
		frappe.throw(
			_("Only a Card Manager or System Manager can change the default consumption rates."),
			frappe.PermissionError,
		)
	from card.party_registry import _restricted_companies

	companies = _restricted_companies(user, "Card Equipment")
	if companies is None:
		return
	for company, _values in touched:
		if not company:
			frappe.throw(
				_(
					"A default consumption rate with no company applies to every company. Only a user who is"
					" not limited to some companies can change it."
				),
				frappe.PermissionError,
			)
		if company not in companies:
			frappe.throw(
				_("You cannot change the default consumption rates of company {0}.").format(company),
				frappe.PermissionError,
			)


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
