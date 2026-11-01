# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD integration API v1 (4.4.0): the stable service other apps (DAWM field and mobile
screens) call for equipment data, so that CARD is the one equipment application and no app
needs equipment_manager.

* Lookups (GET, no side effects): the equipment of an ERPNext Asset, and an equipment
  snapshot (meter, last service, maintenance status per service line, latest fuelling).
* Field readings (POST): a meter reading or a per-machine fuelling recorded from a field
  document of another app (for example a shift log). The caller needs write on that source
  document, the equipment's company must be permitted to the caller, and the source DocType
  must be registered by an app through the ``card_field_meter_sources`` hook WITH an
  authorizer: ``{"Source DocType": "app.module.fn"}``, ``fn(source_doc, equipment) -> bool``
  proves that the document concerns that equipment (fail closed: no authorizer, no reading).
  One reading per (source document, key) — without a key, one per source document: sending it
  again with the same value returns it; a new value replaces it (the old one is Rejected).
* No cost: litres are kept for consumption and maintenance; diesel cost stays with the CARD
  diesel fill and the supplier's invoice (FR-033).

CARD never imports the calling app; the calling app imports this module.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from card.meter import DOCTYPE as METER
from card.meter import REJECTED, VALID, add_reading, previous_valid

API_VERSION = "1.0"
ASSET_LINK = "الأصل_في_erpnext"
FIELD_OPERATION, FIELD_FUELLING = "Field Operation", "Field Fuelling"
MAX_ASSETS = 200


@frappe.whitelist(methods=["GET"])
def api_version():
	return {"version": API_VERSION}


# ---------- lookups ----------


def _readable(equipment):
	return bool(equipment) and frappe.has_permission("Card Equipment", "read", equipment)


@frappe.whitelist(methods=["GET"])
def equipment_for_asset(asset: str):
	"""The Card Equipment linked to an ERPNext Asset, or None (also when the user may not
	read it, so the answer never reveals another company's machine)."""
	name = frappe.db.get_value("Card Equipment", {ASSET_LINK: asset}, "name")
	return name if _readable(name) else None


@frappe.whitelist(methods=["GET"])
def equipment_for_assets(assets: list | str):
	"""{asset: equipment} for the Assets whose equipment the user may read (at most 200)."""
	if isinstance(assets, str):
		try:
			assets = frappe.parse_json(assets)
		except ValueError:
			assets = None
	if not isinstance(assets, list) or len(assets) > MAX_ASSETS:
		frappe.throw(_("Send a list of at most {0} Assets.").format(MAX_ASSETS))
	rows = frappe.get_all(
		"Card Equipment", filters={ASSET_LINK: ["in", list(assets or [])]}, fields=["name", ASSET_LINK]
	)
	return {r.get(ASSET_LINK): r.name for r in rows if _readable(r.name)}


@frappe.whitelist(methods=["GET"])
def equipment_snapshot(equipment: str):
	"""Meter, service and fuelling state of one equipment (read right required)."""
	from card.maintenance import line_statuses

	frappe.has_permission("Card Equipment", "read", equipment, throw=True)
	eq = frappe.db.get_value(
		"Card Equipment",
		equipment,
		[
			"name",
			"equipment_name",
			"company",
			ASSET_LINK,
			"current_project",
			"status",
			"meter_type",
			"current_meter",
			"last_service_meter",
			"last_service_date",
			"maintenance_status",
			"next_service_meter",
		],
		as_dict=True,
	)
	eq["asset"] = eq.pop(ASSET_LINK, None)
	eq["hours_since_last_service"] = (
		flt(eq.current_meter) - flt(eq.last_service_meter)
		if eq.last_service_date or eq.last_service_meter
		else None
	)
	# part of the equipment's own state: the equipment read right checked above covers it
	fuel = frappe.get_all(
		METER,
		filters={"equipment": equipment, "status": VALID, "litres": [">", 0]},
		fields=["reading_time", "reading", "litres", "source_type"],
		order_by="reading_time desc, creation desc",
		limit=1,
	)
	eq["last_fuelling"] = fuel[0] if fuel else None
	eq["service_lines"] = line_statuses(equipment)
	return eq


# ---------- field readings ----------


def _authorizers(source_doctype):
	"""The authorizer paths an app registered for this source DocType (empty = not a source)."""
	hooks = frappe.get_hooks("card_field_meter_sources") or {}
	paths = hooks.get(source_doctype) if isinstance(hooks, dict) else None
	return [p for p in (paths or []) if p]


def _check_registered(source_doctype):
	paths = _authorizers(source_doctype)
	if not paths:
		frappe.throw(
			_("{0} is not a registered source of CARD meter readings.").format(source_doctype),
			frappe.PermissionError,
		)
	return paths


def _check_equipment(source, equipment, paths):
	from card.report_access import permitted_companies

	company = frappe.db.get_value("Card Equipment", equipment, "company")
	if not company:
		frappe.throw(_("Choose the equipment."))
	if company not in permitted_companies("Card Equipment"):
		frappe.throw(_("You may not record readings for this equipment."), frappe.PermissionError)
	for path in paths:
		if not frappe.get_attr(path)(source, equipment):
			frappe.throw(
				_("{0} {1} does not concern this equipment.").format(_(source.doctype), source.name),
				frappe.PermissionError,
			)


def _authorize_source(equipment, source_doctype, source_name):
	paths = _check_registered(source_doctype)
	if not frappe.db.exists(source_doctype, source_name):
		frappe.throw(_("{0} {1} was not found.").format(_(source_doctype), source_name))
	# one request per source document at a time (same source and key, any equipment)
	frappe.db.get_value(source_doctype, source_name, "name", for_update=True)
	source = frappe.get_doc(source_doctype, source_name)
	source.check_permission("write")
	_check_equipment(source, equipment, paths)


def _record(
	equipment, reading, reading_time, source_type, source_doctype, source_name, source_key, litres, strict
):
	_authorize_source(equipment, source_doctype, source_name)
	reading, litres = flt(reading), flt(litres)
	if reading < 0 or litres < 0:
		frappe.throw(_("A meter reading cannot be negative."))
	reading_time = get_datetime(reading_time) if reading_time else now_datetime()
	key = source_key or None
	# one writer per equipment at a time: the check below and the insert stay consistent
	frappe.db.get_value("Card Equipment", equipment, "name", for_update=True)
	existing = frappe.get_all(
		METER,
		filters={
			"source_doctype": source_doctype,
			"source_name": source_name,
			"source_key": key or ["is", "not set"],
			"status": ["!=", REJECTED],
		},
		fields=["name", "reading", "litres", "equipment"],
	)
	for row in existing:
		if row.equipment == equipment and flt(row.reading) == reading and flt(row.litres) == litres:
			return frappe.get_doc(METER, row.name).as_dict()  # sent again: nothing new
	if frappe.utils.cint(strict):
		prev = previous_valid(equipment, None, reading_time, exclude=None)
		if prev and reading < flt(prev.reading):
			frappe.throw(
				_("The reading {0} is lower than the last reading {1} of this equipment.").format(
					reading, flt(prev.reading)
				)
			)
	from card.meter import reject_reading

	for row in existing:
		reject_reading(
			row.name, _("Replaced by a new value from {0} {1}.").format(_(source_doctype), source_name)
		)
	doc = add_reading(
		equipment,
		reading,
		reading_time,
		source_type,
		source_doctype,
		source_name,
		litres=litres,
		asset=frappe.db.get_value("Card Equipment", equipment, ASSET_LINK),
		source_key=key,
	)
	return doc.as_dict()


@frappe.whitelist(methods=["POST"])
def record_meter_reading(
	equipment: str,
	reading: float,
	source_doctype: str,
	source_name: str,
	reading_time: str | datetime | None = None,  # in-process callers may pass a datetime
	source_key: str | None = None,
	strict: int | str = 0,
):
	"""A meter reading from a field document (for example the start or end of a shift)."""
	return _record(
		equipment, reading, reading_time, FIELD_OPERATION, source_doctype, source_name, source_key, 0, strict
	)


@frappe.whitelist(methods=["POST"])
def record_machine_fuelling(
	equipment: str,
	litres: float,
	reading: float,
	source_doctype: str,
	source_name: str,
	reading_time: str | datetime | None = None,  # in-process callers may pass a datetime
	source_key: str | None = None,
	strict: int | str = 0,
):
	"""A per-machine fuelling (litres and meter) from a field document. No cost is posted."""
	if flt(litres) <= 0:
		frappe.throw(_("Fuel quantity must be greater than zero."))
	return _record(
		equipment,
		reading,
		reading_time,
		FIELD_FUELLING,
		source_doctype,
		source_name,
		source_key,
		litres,
		strict,
	)


@frappe.whitelist(methods=["POST"])
def reject_source_readings(source_doctype: str, source_name: str, reason: str | None = None):
	"""The field document was cancelled or withdrew its readings: they become Rejected
	(kept). A writer of the source may reject only readings whose equipment the source
	concerns (registered authorizer) in a permitted company; a deleted source is handled by
	a System Manager."""
	paths = _check_registered(source_doctype)
	from card.meter import reject_reading

	reason = reason or _("{0} {1} was cancelled.").format(_(source_doctype), source_name)
	rows = frappe.get_all(
		METER,
		filters={"source_doctype": source_doctype, "source_name": source_name, "status": ["!=", REJECTED]},
		fields=["name", "equipment"],
	)
	if frappe.db.exists(source_doctype, source_name):
		source = frappe.get_doc(source_doctype, source_name)
		source.check_permission("write")
		for row in rows:
			_check_equipment(source, row.equipment, paths)
	elif "System Manager" not in frappe.get_roles():
		frappe.throw(_("{0} {1} was not found.").format(_(source_doctype), source_name))
	for row in rows:
		reject_reading(row.name, reason)
	return [row.name for row in rows]
