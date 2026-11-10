# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-145 (#44, #123; closure plan WP-K2): draft monthly cards from approved daily logs.

``generate_monthly_cards`` is a manual action (POST only). For one company, one project, one month and optionally
one equipment it reads the Approved, submitted Card Daily Logs and creates or updates DRAFT Card Monthly Cards:

- one card per equipment, project, month and shift, as the card's own duplicate guard keys it: the day shift hours
  and the stop data (stop reason, stopped hours, responsible party) of a log row go to the day shift card, the night
  shift hours to the night shift card. A shift card is created only when a log row has hours for it; a shift card
  that exists as a draft gets every log date of the month (a zero day included);
- a day of a draft card covered by an approved log is set from the log on every run; every other day row of the card
  is kept; the day's notes name the log;
- a submitted card is never changed (it is reported); no card is ever submitted;
- every card is built and saved through ``insert()`` / ``save()``, so the card's own validation runs (duplicate guard,
  assignment days, unit-component days, stop reasons, fiscal-year window, rates), with the user's permissions;
- a second run changes nothing (no duplicate day or card); a log approved later fills its day on the next run.

Days left out (reported, never written): a day the equipment is not on the project (yard, workshop, storage or
another project; the same check as the card, ``card.transfer.validate_card_days``), and a day the equipment is a
component of a unit (it belongs on the unit's card, as ``CardMonthlyCard._refuse_unit_component_days`` requires).
A machine moved between two projects in the month gets one card per project: each run names one project and reads
only that project's logs.

Authorization: the user must be allowed to create a Card Monthly Card of the company and project (DocPerm, Company
User Permissions, ``has_card_permission``) and to read the company's daily logs (FR-131 hooks through
``frappe.get_list``); every card is then inserted or saved with the user's own permissions. A card that fails its
validation is rolled back alone and reported; a permission error stops the whole run."""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, getdate

from card.constants import SHIFT_DAY, SHIFT_NIGHT
from card.daily_log import APPROVED
from card.daily_log import DOCTYPE as LOG_DOCTYPE
from card.daily_log import ROW_DOCTYPE as LOG_ROW_DOCTYPE
from card.transfer import _in_unit_on, validate_card_days

CARD = "Card Monthly Card"
WORK_STATUS = "عمل"  # the card day status that keeps the working hours (Card Monthly Card Day.day_status)
STOP_FIELDS = (
	"stop_reason",
	"stopped_hours",
	"responsible_party_type",
	"responsible_party",
	"responsible_party_name",
)
DAY_FIELDS = ("day_status", "working_hours", *STOP_FIELDS, "notes")

SKIP_OFF_PROJECT = "off_project"
SKIP_UNIT_COMPONENT = "unit_component"


def _first_day(month):
	"""The first day of the month given as YYYY-MM or as any date of the month."""
	text = str(month or "").strip()
	if len(text) == 7:
		text += "-01"
	try:
		day = getdate(text)
	except Exception:
		day = None
	if not day:
		frappe.throw(_("Give the month as YYYY-MM or as a date of that month."))
	return day.replace(day=1)


def _authorize(company, project, equipment):
	"""Refuse unless the user may create a monthly card of this company and project and read its daily logs."""
	if not frappe.db.exists("Company", company) or not frappe.db.exists("Project", project):
		frappe.throw(_("Company or project not found."), frappe.DoesNotExistError)
	probe = frappe.new_doc(CARD)
	probe.update({"company": company, "project": project, "equipment": equipment})
	if not frappe.has_permission(CARD, "create", doc=probe):
		frappe.throw(
			_("You are not allowed to create monthly cards for company {0} and project {1}.").format(
				company, project
			),
			frappe.PermissionError,
		)
	if not frappe.has_permission(LOG_DOCTYPE, "read"):
		frappe.throw(_("You are not allowed to read daily logs."), frappe.PermissionError)
	if frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Project {0} does not belong to company {1}.").format(project, company))
	if equipment:
		if not frappe.has_permission("Card Equipment", "read", equipment):
			frappe.throw(
				_("You are not allowed to read equipment {0}.").format(equipment), frappe.PermissionError
			)
		if frappe.db.get_value("Card Equipment", equipment, "company") != company:
			frappe.throw(_("Equipment {0} does not belong to company {1}.").format(equipment, company))


def _approved_rows(company, project, first_day, last_day, equipment):
	"""{equipment: {date: row}} of the Approved, submitted logs the user may read (FR-131 list scope)."""
	logs = frappe.get_list(
		LOG_DOCTYPE,
		filters={
			"company": company,
			"project": project,
			"docstatus": 1,
			"approval_status": APPROVED,
			"log_date": ["between", [first_day, last_day]],
		},
		fields=["name", "log_date"],
		limit_page_length=0,
	)
	if not logs:
		return {}
	dates = {log.name: getdate(log.log_date) for log in logs}
	filters = {"parent": ["in", list(dates)], "parenttype": LOG_DOCTYPE}
	if equipment:
		filters["equipment"] = equipment
	out = {}
	for row in frappe.get_all(
		LOG_ROW_DOCTYPE,
		filters=filters,
		fields=["parent", "equipment", "day_hours", "night_hours", *STOP_FIELDS],
		order_by="idx asc",
	):
		row.log_date = dates[row.parent]
		out.setdefault(row.equipment, {})[row.log_date] = row
	return out


def _on_project(equipment, project, day):
	"""The card's own assignment rule for one billed day (``validate_card_days``), without its message."""
	probe = frappe._dict(
		equipment=equipment,
		project=project,
		days=[frappe._dict(operation_date=day, working_hours=1, stopped_hours=0, reason_billable=0)],
	)
	muted = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		validate_card_days(probe)
		return True
	except frappe.ValidationError:
		return False
	finally:
		frappe.flags.mute_messages = muted


def _kept_days(equipment, project, rows, skipped):
	"""The log dates that may go on this equipment's card for the project; the others are added to ``skipped``."""
	from card.card.doctype.card_equipment.card_equipment import component_periods

	periods = component_periods(equipment)
	flagged = not periods and cint(frappe.db.get_value("Card Equipment", equipment, "is_unit_component"))
	kept = {}
	for day in sorted(rows):
		row = rows[day]
		if flagged or any(_in_unit_on(p, day) for p in periods):
			skipped.append(
				{"equipment": equipment, "date": str(day), "reason": SKIP_UNIT_COMPONENT, "log": row.parent}
			)
			continue
		hours = flt(row.day_hours) + flt(row.night_hours) + flt(row.stopped_hours)
		if hours > 0 and not _on_project(equipment, project, day):
			skipped.append(
				{"equipment": equipment, "date": str(day), "reason": SKIP_OFF_PROJECT, "log": row.parent}
			)
			continue
		kept[day] = row
	return kept


def _day_values(row, shift):
	"""The card day row of one log row for one shift card."""
	values = {"day_status": WORK_STATUS, "notes": row.parent}
	if shift == SHIFT_DAY:
		values["working_hours"] = flt(row.day_hours)
		values.update({field: row.get(field) for field in STOP_FIELDS})
		values["stopped_hours"] = flt(row.stopped_hours)
	else:
		values["working_hours"] = flt(row.night_hours)
		values.update(dict.fromkeys(STOP_FIELDS))
		values["stopped_hours"] = 0
	return values


def _shift_has_hours(rows, shift):
	if shift == SHIFT_DAY:
		return any(flt(r.day_hours) > 0 or flt(r.stopped_hours) > 0 for r in rows.values())
	return any(flt(r.night_hours) > 0 for r in rows.values())


def _same(current, values):
	for field, value in values.items():
		stored = current.get(field)
		if field in ("working_hours", "stopped_hours"):
			if flt(stored) != flt(value):
				return False
		elif (stored or None) != (value or None):
			return False
	return True


def _apply_days(card, rows, shift):
	"""Set the card's day rows of the log dates; True when something changed."""
	by_date = {getdate(d.operation_date): d for d in card.get("days") or [] if d.operation_date}
	changed = False
	for day in sorted(rows):
		values = _day_values(rows[day], shift)
		current = by_date.get(day)
		if current is None:
			card.append("days", {"operation_date": day, **values})
			changed = True
		elif not _same(current, values):
			current.update(values)
			changed = True
	if changed:
		card.days.sort(key=lambda d: getdate(d.operation_date))
		for idx, d in enumerate(card.days, start=1):
			d.idx = idx
	return changed


def _existing_card(equipment, project, month, year, shift):
	return frappe.db.get_value(
		CARD,
		{
			"equipment": equipment,
			"project": project,
			"month": month,
			"year": year,
			"shift": shift,
			"docstatus": ["!=", 2],
		},
		["name", "docstatus"],
		as_dict=True,
	)


def _build_card(company, project, equipment, month, year, shift, rows, result):
	existing = _existing_card(equipment, project, month, year, shift)
	if existing and existing.docstatus == 1:
		result["kept_submitted"].append(existing.name)
		return
	if not existing and not _shift_has_hours(rows, shift):
		return
	log_size = len(frappe.local.message_log or [])
	savepoint = "card_k2_" + frappe.generate_hash(length=8)
	frappe.db.savepoint(savepoint)
	try:
		if existing:
			card = frappe.get_doc(CARD, existing.name)
			if not _apply_days(card, rows, shift):
				result["unchanged"].append(card.name)
				return
			card.save()
			result["updated"].append(card.name)
		else:
			card = frappe.new_doc(CARD)
			card.update(
				{
					"company": company,
					"project": project,
					"equipment": equipment,
					"month": month,
					"year": year,
					"shift": shift,
				}
			)
			_apply_days(card, rows, shift)
			card.insert()
			result["created"].append(card.name)
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as exc:
		frappe.db.rollback(save_point=savepoint)
		del frappe.local.message_log[log_size:]
		result["errors"].append(
			{
				"equipment": equipment,
				"shift": shift,
				"card": existing.name if existing else None,
				"message": str(exc),
			}
		)


@frappe.whitelist(methods=["POST"])
def generate_monthly_cards(company: str, project: str, month: str, equipment: str | None = None) -> dict:
	"""Create or update the draft monthly cards of one company, project and month (optionally one equipment) from
	the Approved daily logs. Never submits a card and never changes a submitted one (module docstring)."""
	equipment = equipment or None
	_authorize(company, project, equipment)
	first_day = _first_day(month)
	last_day = get_last_day(first_day)
	card_month, card_year = "%02d" % first_day.month, first_day.year
	result = {
		"created": [],
		"updated": [],
		"unchanged": [],
		"kept_submitted": [],
		"skipped_days": [],
		"errors": [],
	}
	by_equipment = _approved_rows(company, project, first_day, last_day, equipment)
	for name in sorted(by_equipment):
		# one run at a time per equipment: the card's duplicate guard reads without a lock
		frappe.db.get_value("Card Equipment", name, "name", for_update=True)
		rows = _kept_days(name, project, by_equipment[name], result["skipped_days"])
		if not rows:
			continue
		for shift in (SHIFT_DAY, SHIFT_NIGHT):
			_build_card(company, project, name, card_month, card_year, shift, rows, result)
	return result
