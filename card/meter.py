# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-099: one meter history per equipment (Card Meter Reading), replacing the per-machine
Fueling Log of the retired equipment_manager app.

* Append-only: a reading is never edited or deleted; a wrong one is marked Rejected (or
  Suspect) with a reason, and a correction is a new reading.
* Sources: a diesel fill row with a meter (per-machine fuelling), a maintenance order, a
  manual entry, or a legacy Fueling Log copy (kept read-only with its original values).
* Plausibility: a reading below the previous valid one, or a jump faster than the
  configured hours per day, is recorded as Suspect (never refused, never altered).
* The equipment's ``current_meter`` is the highest Valid reading (read-only on the form).
* Consumption: litres of a reading / hours since the previous valid reading.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, time_diff_in_hours

from card.settings import setting

VALID, SUSPECT, REJECTED = "Valid", "Suspect", "Rejected"
DOCTYPE = "Card Meter Reading"


def previous_valid(equipment=None, asset=None, before=None, exclude=None):
	"""The latest Valid reading of the equipment (or of the Asset when no equipment)
	strictly before ``before``."""
	filters = {"status": VALID}
	if equipment:
		filters["equipment"] = equipment
	elif asset:
		filters["asset"] = asset
	else:
		return None
	if before:
		filters["reading_time"] = ["<", before]
	if exclude:
		filters["name"] = ["!=", exclude]
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		fields=["name", "reading", "reading_time"],
		order_by="reading_time desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def next_valid(equipment=None, asset=None, after=None, exclude=None):
	"""The earliest Valid reading strictly after ``after`` (a back-dated reading is checked
	against the readings recorded after it too)."""
	filters = {"status": VALID, "reading_time": [">", after]}
	if equipment:
		filters["equipment"] = equipment
	elif asset:
		filters["asset"] = asset
	else:
		return None
	if exclude:
		filters["name"] = ["!=", exclude]
	rows = frappe.get_all(
		DOCTYPE,
		filters=filters,
		fields=["name", "reading", "reading_time"],
		order_by="reading_time asc, creation asc",
		limit=1,
	)
	return rows[0] if rows else None


def assess(doc):
	"""Set previous reading, hours since, consumption and a Suspect status for an
	implausible reading. Never changes the reading itself."""
	prev = previous_valid(doc.equipment, doc.asset, doc.reading_time, exclude=doc.name)
	doc.previous_reading = flt(prev.reading) if prev else 0
	doc.hours_since_previous = flt(doc.reading) - flt(prev.reading) if prev else 0
	doc.consumption_rate = (
		flt(flt(doc.litres) / doc.hours_since_previous, 2)
		if prev and doc.hours_since_previous > 0 and flt(doc.litres) > 0
		else 0
	)
	if doc.status != VALID:
		return
	later = next_valid(doc.equipment, doc.asset, doc.reading_time, exclude=doc.name)
	if later and flt(doc.reading) > flt(later.reading):
		doc.status = SUSPECT
		doc.status_reason = _("Higher than the later valid reading {0} ({1}).").format(
			flt(later.reading), later.name
		)
		return
	if not prev:
		return
	if flt(doc.reading) < flt(prev.reading):
		doc.status = SUSPECT
		doc.status_reason = _("Lower than the previous valid reading {0} ({1}).").format(
			flt(prev.reading), prev.name
		)
		return
	max_per_day = flt(setting("max_meter_hours_per_day")) or 24
	elapsed_days = max(time_diff_in_hours(doc.reading_time, prev.reading_time) / 24.0, 0)
	allowed = max_per_day * max(elapsed_days, 1 / 24.0)
	if doc.hours_since_previous > allowed:
		doc.status = SUSPECT
		doc.status_reason = _(
			"{0} hours since the previous reading {1} in {2} days is more than {3} hours a day."
		).format(flt(doc.hours_since_previous, 1), prev.name, flt(elapsed_days, 1), max_per_day)


def refresh_current_meter(equipment):
	"""Equipment current meter = highest Valid reading (0 when none)."""
	if not equipment:
		return
	from frappe.query_builder.functions import Max

	t = frappe.qb.DocType(DOCTYPE)
	value = (
		frappe.qb.from_(t)
		.select(Max(t.reading))
		.where((t.equipment == equipment) & (t.status == VALID))
		.run()[0][0]
	)
	frappe.db.set_value("Card Equipment", equipment, "current_meter", flt(value), update_modified=False)


def add_reading(
	equipment,
	reading,
	reading_time,
	source_type,
	source_doctype=None,
	source_name=None,
	litres=0,
	asset=None,
	source_key=None,
	refresh=True,
):
	"""Insert a reading from a system source (diesel fill, maintenance order). The
	source document's own permission check has passed; the reading is its history."""
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"equipment": equipment,
			"asset": asset,
			"reading": flt(reading),
			"reading_time": get_datetime(reading_time),
			"source_type": source_type,
			"source_doctype": source_doctype,
			"source_name": source_name,
			"litres": flt(litres),
			"source_key": source_key,
		}
	)
	doc.flags.card_system_source = True
	doc.flags.card_skip_refresh = not refresh  # the caller refreshes the equipment itself
	doc.insert(ignore_permissions=True)  # written for the source document the user just submitted
	return doc


def reject_reading(name, reason):
	"""Mark one reading Rejected by CARD (its source replaced or withdrew it)."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.status = REJECTED
	doc.status_reason = reason
	doc.flags.card_system_source = True
	doc.save(ignore_permissions=True)  # the caller checked the right on the source document


def reject_for_source(source_doctype, source_name, reason):
	"""A cancelled source keeps its readings, marked Rejected (append-only history)."""
	for name in frappe.get_all(
		DOCTYPE,
		filters={"source_doctype": source_doctype, "source_name": source_name, "status": ["!=", REJECTED]},
		pluck="name",
	):
		doc = frappe.get_doc(DOCTYPE, name)
		doc.status = REJECTED
		doc.status_reason = reason
		doc.flags.card_system_source = True
		doc.save(ignore_permissions=True)  # follows the cancellation the user was allowed to make


def attach_asset_readings(equipment, asset):
	"""Readings recorded for an Asset before it had a Card Equipment (legacy copies) join the
	equipment once it is linked to that Asset."""
	if not (equipment and asset):
		return 0
	names = frappe.get_all(DOCTYPE, filters={"asset": asset, "equipment": ["is", "not set"]}, pluck="name")
	for name in names:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.equipment = equipment
		doc.flags.card_system_source = True
		doc.save(ignore_permissions=True)  # follows the Asset link the user just saved
	if names:
		refresh_current_meter(equipment)
	return len(names)
