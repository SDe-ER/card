# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-101: retire the equipment_manager app into CARD without losing anything.

1. ``archive()``: a full JSON copy of every equipment_manager record (Fueling Log,
   maintenance requests, settings and their child rows), the site scripts that drove them
   and the Asset fields they wrote, saved as ONE private File (attached to no record, so only
   System Managers open it) with its SHA-256 noted in a Comment on Card Settings. Read-only on the source.
2. ``import_fueling_logs(dry_run=1)``: every Fueling Log (submitted, cancelled and draft)
   becomes a read-only "Legacy Fueling Log" Card Meter Reading that keeps the original
   record name, values, owner and timestamps. Litres are kept for consumption history and
   are NEVER posted as cost (CARD diesel fills and supplier invoices are the cost source).
   Cancelled logs are kept as Rejected, drafts and zero readings as Suspect, and the
   plausibility rules mark the rest. Idempotent (one reading per legacy record). A dry run
   writes nothing and reports exactly what an import would do.
3. ``verify()``: counts and litres of the copies against the source, per Asset.

Both writing steps are System Manager only and never change or delete a legacy record.
The source app is uninstalled by the owner afterwards (bench), not by CARD.
"""

import hashlib
import json

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, now_datetime

from card.meter import DOCTYPE as METER
from card.meter import REJECTED, SUSPECT, VALID, assess, refresh_current_meter

LOG = "Fueling Log"
ARCHIVE_DOCTYPES = (
	"Fueling Log",
	"Maintenance Request",
	"Maintenance Request For Asset",
	"Equipment Maintenance Settings",
)
CHILD_DOCTYPES = ("Equipment Spare Part", "Maintenance Required Item")
MODULE = "Equipment Manager"
ASSET_FIELDS = (
	"custom_current_operating_hours",
	"custom_hours_since_last_service",
	"custom_total_diesel_consumed",
	"custom_last_fueling_hour_meter",
	"custom_hour_meter_reading",
	"custom_dawm_meter_reading",
	"custom_service_due_hours",
)
ASSET_LINK = "الأصل_في_erpnext"


def _require_system_manager():
	if "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only a System Manager can run the equipment_manager retirement."), frappe.PermissionError
		)


def installed():
	return bool(frappe.db.exists("DocType", LOG))


# ---------- 1. archive ----------


@frappe.whitelist(methods=["POST"])
def archive():
	"""Save the full equipment_manager data as one private JSON file on Card Settings."""
	_require_system_manager()
	if not installed():
		frappe.throw(_("equipment_manager is not installed on this site."))
	payload = {"created_on": str(now_datetime()), "site": frappe.local.site, "doctypes": {}}
	for doctype in ARCHIVE_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		names = frappe.get_all(doctype, pluck="name", order_by="creation asc")
		payload["doctypes"][doctype] = [
			frappe.get_doc(doctype, n).as_dict(no_default_fields=False) for n in names
		]
	payload["server_scripts"] = frappe.get_all(
		"Server Script", filters={"reference_doctype": ["in", list(ARCHIVE_DOCTYPES)]}, fields=["*"]
	)
	payload["client_scripts"] = frappe.get_all(
		"Client Script", filters={"dt": ["in", list(ARCHIVE_DOCTYPES)]}, fields=["*"]
	)
	# the site configuration built on the app (kept so it can be rebuilt or reviewed later)
	targets = [*ARCHIVE_DOCTYPES, *CHILD_DOCTYPES]
	seen = {s.name for s in payload["server_scripts"]}
	for filters in ({"module": MODULE}, {"script": ["like", "%Fueling Log%"]}):
		for row in frappe.get_all("Server Script", filters=filters, fields=["*"]):
			if row.name not in seen:  # API / scheduler scripts that read the app's tables
				seen.add(row.name)
				payload["server_scripts"].append(row)
	for key, doctype, filters in (
		("custom_fields", "Custom Field", {"dt": ["in", targets]}),
		("asset_custom_fields", "Custom Field", {"dt": "Asset", "fieldname": ["in", list(ASSET_FIELDS)]}),
		("property_setters", "Property Setter", {"doc_type": ["in", targets]}),
		("custom_docperms", "Custom DocPerm", {"parent": ["in", targets]}),
		("reports", "Report", {"ref_doctype": ["in", targets]}),
		("number_cards", "Number Card", {"document_type": ["in", targets]}),
		("dashboard_charts", "Dashboard Chart", {"module": MODULE}),
		("web_forms", "Web Form", {"doc_type": ["in", targets]}),
		("comments", "Comment", {"reference_doctype": ["in", targets]}),
	):
		payload[key] = frappe.get_all(doctype, filters=filters, fields=["*"], order_by="creation asc")
	meta = frappe.get_meta("Asset")
	fields = [f for f in ASSET_FIELDS if meta.has_field(f)]
	payload["asset_fields"] = frappe.get_all("Asset", fields=["name", "asset_name", "modified", *fields])
	content = frappe.as_json(payload, indent=1).encode()
	digest = hashlib.sha256(content).hexdigest()
	file = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"equipment_manager_archive_{now_datetime():%Y%m%d_%H%M%S}.json",
			# private and not attached: only System Managers can open it (it holds site
			# scripts and user names; Card Settings is readable by Card Managers)
			"is_private": 1,
			"content": content,
		}
	).insert(ignore_permissions=True)  # System Manager checked above
	counts = {d: len(rows) for d, rows in payload["doctypes"].items()}
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Card Settings",
			"reference_name": "Card Settings",
			"content": _("equipment_manager archive {0}: SHA-256 {1}; records {2}").format(
				file.file_url, digest, json.dumps(counts, ensure_ascii=False)
			),
		}
	).insert(ignore_permissions=True)
	return {"file": file.file_url, "sha256": digest, "counts": counts}


# ---------- 2. import ----------


def _legacy_status(row):
	if row.docstatus == 2:
		return REJECTED, _("Cancelled in the legacy Fueling Log.")
	if row.docstatus == 0:
		return SUSPECT, _("Draft in the legacy Fueling Log (never submitted).")
	if flt(row.hour_meter_reading) <= 0:
		return SUSPECT, _("No meter reading in the legacy Fueling Log.")
	return VALID, None


@frappe.whitelist(methods=["POST"])
def import_fueling_logs(dry_run: int | str = 1):
	"""Copy every Fueling Log into the CARD meter history (see module docstring)."""
	_require_system_manager()
	if not installed():
		frappe.throw(_("equipment_manager is not installed on this site."))
	dry_run = frappe.utils.cint(dry_run)
	if dry_run:
		return _import(dry_run)
	from frappe.utils.synchronization import filelock

	# one import at a time; the unique legacy_record stops any duplicate anyway
	with filelock("card_legacy_fueling_import", timeout=5):
		return _import(dry_run)


def _import(dry_run):
	equipment_of = {
		r.get(ASSET_LINK): r.name
		for r in frappe.get_all(
			"Card Equipment", filters={ASSET_LINK: ["is", "set"]}, fields=["name", ASSET_LINK]
		)
	}
	existing = set(frappe.get_all(METER, filters={"legacy_record": ["is", "set"]}, pluck="legacy_record"))
	logs = frappe.get_all(LOG, fields=["*"], order_by="date asc, creation asc")
	report = {
		"dry_run": dry_run,
		"source": len(logs),
		"already": 0,
		"created": 0,
		"by_status": {},
		"by_asset": {},
	}
	touched = set()
	for row in logs:
		per_asset = report["by_asset"].setdefault(row.asset, {"logs": 0, "litres": 0.0, "equipment": None})
		per_asset["logs"] += 1
		per_asset["litres"] = flt(per_asset["litres"] + flt(row.fuel_qty), 3)
		per_asset["equipment"] = equipment_of.get(row.asset)
		if row.name in existing:
			report["already"] += 1
			continue
		status, reason = _legacy_status(row)
		doc = frappe.get_doc(
			{
				"doctype": METER,
				"equipment": equipment_of.get(row.asset),
				"asset": row.asset,
				"reading": flt(row.hour_meter_reading),
				"reading_time": get_datetime(row.date or row.creation),
				"source_type": "Legacy Fueling Log",
				"source_doctype": None,
				"source_name": None,
				"litres": flt(row.fuel_qty),
				"status": status,
				"status_reason": reason,
				"legacy_record": row.name,
				"legacy_created": row.creation,
				"legacy_owner": row.owner,
				"legacy_docstatus": row.docstatus,
				"legacy_values": frappe.as_json(row, indent=None),
			}
		)
		if dry_run:
			assess(doc)  # same rules as the import, nothing saved
			# a dry run does not see the readings it would create before this one
		else:
			doc.flags.card_system_source = True
			doc.flags.card_skip_refresh = True  # each equipment is refreshed once below
			doc.insert(ignore_permissions=True)  # System Manager checked above
			touched.add(doc.equipment)
		report["by_status"][doc.status] = report["by_status"].get(doc.status, 0) + 1
		report["created"] += 0 if dry_run else 1
	from card.maintenance import refresh_status

	for equipment in touched - {None}:
		refresh_current_meter(equipment)
		refresh_status(equipment, notify=False)
	report["unmapped_assets"] = sorted(a for a, v in report["by_asset"].items() if not v["equipment"])
	return report


# ---------- 3. verify ----------


@frappe.whitelist(methods=["GET"])
def verify():
	"""Source vs CARD copies: counts per docstatus, litres and per-Asset counts must match."""
	_require_system_manager()
	if not installed():
		frappe.throw(_("equipment_manager is not installed on this site."))
	source = frappe.get_all(
		LOG, fields=["name", "asset", "docstatus", "fuel_qty", "hour_meter_reading", "date"]
	)
	copies = {
		r.legacy_record: r
		for r in frappe.get_all(
			METER,
			filters={"source_type": "Legacy Fueling Log"},
			fields=["legacy_record", "asset", "legacy_docstatus", "litres", "reading", "reading_time"],
		)
	}
	missing = [r.name for r in source if r.name not in copies]
	mismatch = [
		r.name
		for r in source
		if r.name in copies
		and (
			copies[r.name].asset != r.asset
			or copies[r.name].legacy_docstatus != r.docstatus
			or flt(copies[r.name].litres, 3) != flt(r.fuel_qty, 3)
			or flt(copies[r.name].reading, 3) != flt(r.hour_meter_reading, 3)
		)
	]
	return {
		"source_rows": len(source),
		"copied_rows": len([r for r in source if r.name in copies]),
		"source_litres": flt(sum(flt(r.fuel_qty) for r in source), 3),
		"copied_litres": flt(sum(flt(copies[r.name].litres) for r in source if r.name in copies), 3),
		"missing": missing,
		"mismatch": mismatch,
		"ok": not missing and not mismatch,
	}
