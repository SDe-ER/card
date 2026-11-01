# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment meter reconciliation (maintenance plan R1, Owner approval 2026-10-31). Read-only.

Compares, per machine, the hour-meter readings recorded elsewhere on the site (the legacy fuelling log of
another app, when that DocType exists and the user may read it, and the hour-meter fields an Asset may carry)
with the operating hours of CARD's submitted monthly cards. It never writes, never sums cumulative meter readings
as hours (only the differences between consecutive plausible readings count) and never sets a maintenance
baseline: a baseline needs a verified meter reading and a verified maintenance event (Owner decision D-M4).

CARD does not depend on the other app: its DocType and fields are looked up at run time and skipped when absent.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.report_access import _role_reads

REPORT = "Equipment Meter Reconciliation"
DOCTYPES = ("Card Equipment", "Card Monthly Card", "Asset")
# maintenance policy kept from the existing practice (Owner 2026-10-31): shown, never applied here
ALERT_HOURS, OIL_CHANGE_HOURS = 250, 300
# a reading below this share of the previous plausible reading is a meter reset (new or replaced meter)
RESET_RATIO = 0.05
MAX_HOURS_PER_DAY = 24
# legacy fuelling log (another app): read only when present
LEGACY_LOG = "Fueling Log"
LEGACY_FIELDS = ("asset", "date", "hour_meter_reading", "hours_run")
# hour-meter fields an Asset may carry (custom fields of other apps), read only when present
ASSET_METER_FIELDS = (
	"custom_hour_meter_reading",
	"custom_current_operating_hours",
	"custom_last_fueling_hour_meter",
)

# reading flags (codes; the report translates them)
OK, INVALID, DUPLICATE, BACKWARD, RESET, JUMP = "ok", "invalid", "duplicate", "backward", "reset", "jump"
CUMULATIVE = "cumulative_hours_run"
FLAG_LABELS = {
	OK: "Plausible",
	INVALID: "Invalid reading (zero, negative or empty)",
	DUPLICATE: "Duplicate reading",
	BACKWARD: "Backward reading",
	RESET: "Meter reset (reading restarts near zero)",
	JUMP: "Impossible jump (more hours than elapsed time)",
	CUMULATIVE: "Recorded hours equal the whole meter (cumulative): ignored",
}
IDENTITY_TOKEN = re.compile(r"\b([A-Z]{1,4})-?(\d{1,3})\b")


def assert_report_access():
	"""One of the report's roles, and roles that read the equipment, the monthly cards and the Assets."""
	if frappe.session.user != "Administrator" and not frappe.get_cached_doc("Report", REPORT).is_permitted():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	for doctype in DOCTYPES:
		if not _role_reads(doctype):
			frappe.throw(
				_("You need read access to {0} to run this report").format(_(doctype)), frappe.PermissionError
			)


def classify_readings(readings):
	"""Flag each reading of ONE machine (dicts with ``at`` (datetime/date), ``reading`` and optional
	``hours_run``), oldest first. Returns the readings with ``flag``, ``note`` and ``meter_hours`` (the
	hours between this plausible reading and the previous one; 0 otherwise). Cumulative readings are never
	added: only differences between consecutive plausible readings count, and a reset starts a new run."""
	rows = sorted(readings, key=lambda r: (getdate(r["at"]), str(r["at"])))
	previous = None  # last plausible reading
	seen = set()
	for row in rows:
		value = flt(row.get("reading"))
		row["meter_hours"] = 0.0
		row["note"] = ""
		key = (str(row["at"]), value)
		if not row.get("reading") or value <= 0:
			row["flag"] = INVALID
		elif key in seen or (previous and value == flt(previous["reading"]) and _same_day(row, previous)):
			row["flag"] = DUPLICATE
		elif previous and value < flt(previous["reading"]):
			row["flag"] = RESET if value < flt(previous["reading"]) * RESET_RATIO else BACKWARD
			if row["flag"] == RESET:
				previous = row  # a new meter run starts here; its hours before the reset are unknown
		else:
			delta = value - flt(previous["reading"]) if previous else 0.0
			days = (getdate(row["at"]) - getdate(previous["at"])).days if previous else 0
			if previous and delta > MAX_HOURS_PER_DAY * (days + 1):
				row["flag"] = JUMP
			else:
				row["flag"] = OK
				row["meter_hours"] = delta
				previous = row
		if row.get("hours_run") is not None and value > 0 and flt(row["hours_run"]) >= value:
			row["note"] = FLAG_LABELS[CUMULATIVE]
		seen.add(key)
	return rows


def _same_day(a, b):
	return getdate(a["at"]) == getdate(b["at"])


def summarize(rows, card_hours_between):
	"""Summary of one machine's classified readings. ``card_hours_between(from_date, to_date)`` returns the
	CARD operating hours in that period. The meter hours are the sum of the plausible differences only."""
	plausible = [r for r in rows if r["flag"] == OK]
	counts = {flag: sum(1 for r in rows if r["flag"] == flag) for flag in FLAG_LABELS if flag != CUMULATIVE}
	counts[CUMULATIVE] = sum(1 for r in rows if r.get("note"))
	summary = {
		"readings": len(rows),
		"counts": counts,
		"first": plausible[0] if plausible else None,
		"last": plausible[-1] if plausible else None,
		"meter_hours": flt(sum(r["meter_hours"] for r in plausible), 2),
		"card_hours": None,
	}
	if len(plausible) >= 2:
		summary["card_hours"] = flt(
			card_hours_between(getdate(plausible[0]["at"]), getdate(plausible[-1]["at"])), 2
		)
	return summary


def identity_conflict(asset_id, *other_names):
	"""Model codes that share a prefix but differ in number between the Asset ID and its own name or item
	(e.g. an ID ``C15-1`` whose name and item say ``C13-1``). A heuristic: it flags for review only."""

	def tokens(text):
		return {(p, int(n)) for p, n in IDENTITY_TOKEN.findall((text or "").upper())}

	own = tokens(asset_id)
	others = set().union(*(tokens(t) for t in other_names)) if other_names else set()
	conflicts = sorted(
		f"{p}{n} / {p}{m}" for p, n in own for q, m in others if p == q and n != m and (q, n) not in others
	)
	return conflicts


def legacy_readings(assets):
	"""Hour-meter readings for these Assets: {asset: [reading dicts]}, from the legacy fuelling log while
	that app is installed, plus CARD's own meter history (FR-099; its imported legacy copies are skipped
	while the original log is still there, so nothing is counted twice). Returns (readings, available)."""
	found, available = _fueling_log_readings(assets)
	card = _card_meter_readings(assets, skip_legacy=available)
	for asset, rows in card.items():
		found.setdefault(asset, []).extend(rows)
	return found, available or bool(card)


def _card_meter_readings(assets, skip_legacy):
	if not assets or not frappe.has_permission("Card Meter Reading", "read"):
		return {}
	filters = [["status", "!=", "Rejected"], ["asset", "in", list(assets)]]
	if skip_legacy:
		filters.append(["source_type", "!=", "Legacy Fueling Log"])
	found = {}
	for row in frappe.get_list(
		"Card Meter Reading",
		filters=filters,
		fields=["name", "asset", "reading_time", "reading", "hours_since_previous"],
		order_by="reading_time asc",
		limit_page_length=0,
	):
		found.setdefault(row.asset, []).append(
			{
				"source": "Card Meter Reading",
				"ref": row.name,
				"at": row.reading_time,
				"reading": row.reading,
				"hours_run": row.hours_since_previous,
			}
		)
	return found


def _fueling_log_readings(assets):
	if not assets or not frappe.db.exists("DocType", LEGACY_LOG):
		return {}, False
	meta = frappe.get_meta(LEGACY_LOG)
	if not all(meta.has_field(f) for f in LEGACY_FIELDS):
		return {}, False
	if not frappe.has_permission(LEGACY_LOG, "read"):
		return {}, False
	found = {}
	for row in frappe.get_list(
		LEGACY_LOG,
		filters={"asset": ["in", list(assets)], "docstatus": 1},
		fields=["name", *LEGACY_FIELDS],
		order_by="date asc",
		limit_page_length=0,
	):
		found.setdefault(row.asset, []).append(
			{
				"source": LEGACY_LOG,
				"ref": row.name,
				"at": row.date,
				"reading": row.hour_meter_reading,
				"hours_run": row.hours_run,
			}
		)
	return found, True


def asset_meter_values(asset):
	"""The hour-meter fields the Asset carries (other apps' custom fields), when present."""
	meta = frappe.get_meta("Asset")
	fields = [f for f in ASSET_METER_FIELDS if meta.has_field(f)]
	if not fields:
		return {}
	return frappe.db.get_value("Asset", asset, fields, as_dict=True) or {}


def card_hours(equipment, from_date, to_date):
	"""Operating hours of the machine's SUBMITTED monthly cards between two dates (cancelled and amended-away
	cards are not submitted, so an amendment never counts twice)."""
	cards = frappe.get_list(
		"Card Monthly Card",
		filters={"equipment": equipment, "docstatus": 1},
		pluck="name",
		limit_page_length=0,
	)
	if not cards:
		return 0.0
	days = frappe.get_all(
		"Card Monthly Card Day",
		filters={
			"parent": ["in", cards],
			"parenttype": "Card Monthly Card",
			"operation_date": ["between", [from_date, to_date]],
		},
		fields=["working_hours"],
	)
	return sum(flt(d.working_hours) for d in days)


def completed_maintenance(asset):
	"""Completed native maintenance events of an Asset the user may read (for the baseline note only)."""
	sources = (
		("Asset Repair", {"asset": asset, "repair_status": "Completed"}),
		("Asset Maintenance Log", {"asset_name": asset, "maintenance_status": "Completed"}),
	)
	dates = []
	for doctype, filters in sources:
		if not frappe.has_permission(doctype, "read"):
			continue
		dates += [
			getdate(d)
			for d in frappe.get_list(
				doctype,
				filters={**filters, "docstatus": 1},
				pluck="completion_date",
				order_by="completion_date desc",
				limit=1,
			)
			if d
		]
	return max(dates) if dates else None
