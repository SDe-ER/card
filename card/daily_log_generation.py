# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-145 (#44, #123; closure plan WP-K2): draft monthly cards from approved daily logs.

``generate_monthly_cards`` is a manual action (POST only). For one company, one project, one month and optionally
one equipment it reads the Approved, submitted Card Daily Logs and creates or updates DRAFT Card Monthly Cards:

- one card per equipment, project, month and shift, as the card's own duplicate guard keys it: the day shift hours
  and the stop data (stop reason, stopped hours, responsible party) of a log row go to the day shift card, the night
  shift hours to the night shift card. A shift card is created only when a log row has hours for it; a shift card
  that exists as a draft gets every log date of the month (a zero day included);
- the approved log wins: a day of a draft card covered by an approved log is set from the log on every run (the
  day's notes name the log); when the card's day held other values (a manual correction, or an earlier log) they are
  replaced and every such day is listed in ``overwritten_days`` with its old and new hours and notes; every other day
  row of the card is kept;
- a day whose notes name a daily log that is no longer Approved (cancelled, for example) is cleared on a draft card
  (hours, stop data and notes emptied; listed in ``cleared_days``); on a submitted card it is only reported
  (``stale_days`` of its ``kept_submitted`` entry);
- a submitted card is never changed; no card is ever submitted;
- every card is built and saved through ``insert()`` / ``save()``, so the card's own validation runs (duplicate guard,
  assignment days, unit-component days, stop reasons, fiscal-year window, rates), with the user's permissions;
- a second run changes nothing (no duplicate day or card); a log approved later fills its day on the next run.

Concurrency: the equipment row is locked, then the equipment's cards of the month are read twice, from the
request's REPEATABLE READ snapshot and with a locking read (the latest committed rows). When they differ another run
changed them after this request started: the equipment is skipped and listed in ``conflicts`` (run again), so two
concurrent runs never create the same card twice.

Days left out (reported, never written): a day the equipment is not on the project (yard, workshop, storage or
another project; the same check as the card, ``card.transfer.validate_card_days``), and a day the equipment is a
component of a unit (it belongs on the unit's card, as ``CardMonthlyCard._refuse_unit_component_days`` requires).
A machine moved between two projects in the month gets one card per project: each run names one project and reads
only that project's logs.

Authorization: the user must be allowed to create a Card Monthly Card of the company and project (DocPerm, Company
User Permissions, ``has_card_permission``) and to read the company's daily logs (FR-131 hooks through
``frappe.get_list``); every card is then inserted or saved with the user's own permissions. A missing project and a
project of another company get the same answer. A card that fails its validation is rolled back alone and reported;
a permission error stops the whole run."""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_last_day, getdate

from card.constants import SHIFT_DAY, SHIFT_NIGHT
from card.daily_log import APPROVED
from card.daily_log import DOCTYPE as LOG_DOCTYPE
from card.daily_log import ROW_DOCTYPE as LOG_ROW_DOCTYPE
from card.transfer import _in_unit_on, validate_card_days

CARD = "Card Monthly Card"
CARD_DAY = "Card Monthly Card Day"
WORK_STATUS = "عمل"  # the card day status that keeps the working hours (Card Monthly Card Day.day_status)
# the card form's day names (card_monthly_card.js CARD_DAYS, Sunday first)
DAY_NAMES = ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت")
STOP_FIELDS = (
	"stop_reason",
	"stopped_hours",
	"responsible_party_type",
	"responsible_party",
	"responsible_party_name",
)
HOUR_FIELDS = ("working_hours", "stopped_hours")

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


def day_name(day):
	"""The card form's day name of a date (card_monthly_card.js)."""
	return DAY_NAMES[(getdate(day).weekday() + 1) % 7]


def _authorize(company, project, equipment):
	"""Refuse unless the user may create a monthly card of this company and project and read its daily logs. A
	missing project and a project of another company get the same answer (no existence probe across companies)."""
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
	if not company or frappe.db.get_value("Project", project, "company") != company:
		frappe.throw(_("Company or project not found."), frappe.DoesNotExistError)
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


def _card_equipment(company, project, month, year, equipment):
	"""Equipment with a card of the month the user can read (a card may hold days of a log no longer approved)."""
	filters = {"company": company, "project": project, "month": month, "year": year, "docstatus": ["!=", 2]}
	if equipment:
		filters["equipment"] = equipment
	return set(frappe.get_list(CARD, filters=filters, pluck="equipment", limit_page_length=0))


def _month_cards(equipment, project, month, year, lock=False):
	"""{name: (shift, docstatus, modified)} of the equipment's live cards of the month; ``lock`` reads the latest
	committed rows with a locking read, otherwise the request's snapshot is read."""
	card = frappe.qb.DocType(CARD)
	query = (
		frappe.qb.from_(card)
		.select(card.name, card.shift, card.docstatus, card.modified)
		.where(card.equipment == equipment)
		.where(card.project == project)
		.where(card.month == month)
		.where(card.year == year)
		.where(card.docstatus != 2)
	)
	if lock:
		query = query.for_update()
	return {r.name: (r.shift, r.docstatus, r.modified) for r in query.run(as_dict=True)}


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
		if field in HOUR_FIELDS:
			if flt(stored) != flt(value):
				return False
		elif (stored or None) != (value or None):
			return False
	return True


def _change(card, shift, day, current, values):
	return {
		"card": card.name,
		"equipment": card.equipment,
		"shift": shift,
		"date": str(day),
		"old_hours": flt(current.get("working_hours")),
		"new_hours": flt(values.get("working_hours")),
		"old_stopped_hours": flt(current.get("stopped_hours")),
		"new_stopped_hours": flt(values.get("stopped_hours")),
		"old_notes": current.get("notes") or None,
		"new_notes": values.get("notes") or None,
	}


def _apply_days(card, rows, shift, overwritten):
	"""Set the card's day rows of the log dates (the approved log wins); a replaced day with other values is added
	to ``overwritten``. True when something changed."""
	by_date = {getdate(d.operation_date): d for d in card.get("days") or [] if d.operation_date}
	changed = False
	for day in sorted(rows):
		values = _day_values(rows[day], shift)
		current = by_date.get(day)
		if current is None:
			card.append("days", {"operation_date": day, "day_name": day_name(day), **values})
			changed = True
		elif not _same(current, values):
			if not card.is_new():
				overwritten.append(_change(card, shift, day, current, values))
			current.update({**values, "day_name": day_name(day)})
			changed = True
	if changed:
		card.days.sort(key=lambda d: getdate(d.operation_date))
		for idx, d in enumerate(card.days, start=1):
			d.idx = idx
	return changed


def _stale_rows(days, covered, company, project, equipment):
	"""Day rows (not in ``covered``) that came from a daily log no longer Approved and submitted. A day counts only
	when the log its notes name is a log of the card's company and project, dated on the day's date, with a row for
	the card's equipment (the filters of ``_approved_rows``); any other text in the notes, a log name typed by hand
	included, is never touched or reported."""
	candidates = [d for d in days if d.notes and getdate(d.operation_date) not in covered]
	if not candidates:
		return []
	log, row = frappe.qb.DocType(LOG_DOCTYPE), frappe.qb.DocType(LOG_ROW_DOCTYPE)
	found = (
		frappe.qb.from_(log)
		.join(row)
		.on((row.parent == log.name) & (row.parenttype == LOG_DOCTYPE))
		.select(log.name, log.log_date, log.docstatus, log.approval_status)
		.where(log.name.isin(list({d.notes for d in candidates})))
		.where(log.company == company)
		.where(log.project == project)
		.where(row.equipment == equipment)
		.distinct()
	).run(as_dict=True)
	stale = {
		(r.name, getdate(r.log_date))
		for r in found
		if not (r.docstatus == 1 and r.approval_status == APPROVED)
	}
	return [d for d in candidates if (d.notes, getdate(d.operation_date)) in stale]


def _stale_entry(card, shift, row):
	return {
		"card": card,
		"shift": shift,
		"date": str(getdate(row.operation_date)),
		"log": row.notes,
		"hours": flt(row.working_hours),
		"stopped_hours": flt(row.stopped_hours),
	}


def _clear_stale(card, rows, shift, cleared):
	"""Empty the draft card's days that came from a log no longer approved; True when something changed."""
	stale = _stale_rows(card.get("days") or [], set(rows), card.company, card.project, card.equipment)
	for row in stale:
		cleared.append(_stale_entry(card.name, shift, row))
		row.update({"working_hours": 0, "notes": None, **dict.fromkeys(STOP_FIELDS)})
		row.stopped_hours = 0
	return bool(stale)


def _kept_submitted(name, shift, rows, company, project, equipment):
	days = frappe.get_all(
		CARD_DAY,
		filters={"parent": name, "parenttype": CARD},
		fields=["operation_date", "working_hours", "stopped_hours", "notes"],
	)
	stale = _stale_rows(days, set(rows), company, project, equipment)
	return {"card": name, "stale_days": [_stale_entry(name, shift, d) for d in stale]}


def _build_card(company, project, equipment, month, year, shift, existing, rows, result):
	"""Create or update one shift card. ``existing`` is (name, docstatus) from the locking read, or None."""
	if existing and existing[1] == 1:
		result["kept_submitted"].append(
			_kept_submitted(existing[0], shift, rows, company, project, equipment)
		)
		return
	if not existing and not _shift_has_hours(rows, shift):
		return
	log_size = len(frappe.local.message_log or [])
	savepoint = "card_k2_" + frappe.generate_hash(length=8)
	frappe.db.savepoint(savepoint)
	overwritten, cleared = [], []
	try:
		if existing:
			card = frappe.get_doc(CARD, existing[0])
			changed = _apply_days(card, rows, shift, overwritten)
			changed = _clear_stale(card, rows, shift, cleared) or changed
			if not changed:
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
			_apply_days(card, rows, shift, overwritten)
			card.insert()
			result["created"].append(card.name)
		result["overwritten_days"].extend(overwritten)
		result["cleared_days"].extend(cleared)
	except frappe.PermissionError:
		raise
	except frappe.ValidationError as exc:
		frappe.db.rollback(save_point=savepoint)
		del frappe.local.message_log[log_size:]
		result["errors"].append(
			{
				"equipment": equipment,
				"shift": shift,
				"card": existing[0] if existing else None,
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
		"overwritten_days": [],
		"cleared_days": [],
		"skipped_days": [],
		"conflicts": [],
		"errors": [],
	}
	by_equipment = _approved_rows(company, project, first_day, last_day, equipment)
	names = set(by_equipment) | _card_equipment(company, project, card_month, card_year, equipment)
	for name in sorted(names):
		# one run at a time per equipment, then the cards as committed by any other run (a locking read): the
		# card's own duplicate guard reads the request's snapshot, which cannot see another run's new card
		frappe.db.get_value("Card Equipment", name, "name", for_update=True)
		latest = _month_cards(name, project, card_month, card_year, lock=True)
		if latest != _month_cards(name, project, card_month, card_year):
			result["conflicts"].append(
				{
					"equipment": name,
					"message": _("Changed by another run; run the generation again."),
				}
			)
			continue
		rows = _kept_days(name, project, by_equipment.get(name) or {}, result["skipped_days"])
		by_shift = {shift: (card, docstatus) for card, (shift, docstatus, _m) in latest.items()}
		for shift in (SHIFT_DAY, SHIFT_NIGHT):
			_build_card(
				company, project, name, card_month, card_year, shift, by_shift.get(shift), rows, result
			)
	return result
