# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment Transport as a location transfer (phase A).

Submitting an Equipment Transport moves the equipment to a new project:
it closes the current open Card Equipment Assignment at the transfer date,
opens a new one for the new project, and re-syncs current_project. Card days
must then fall inside an assignment period for the card's project. Units (a
Card Equipment with components) derive their effective project from their
component pieces: a day is valid for the unit on a project only when EVERY
component is assigned there that day.

Backward-compatible: equipment with NO assignment history is not constrained,
so existing/seed cards and controller tests are unaffected.

#56: the equipment's current_project / assignment_date are read-only and
derived from the assignment in force TODAY (sync_equipment_location). A
transfer opens the new assignment the day after its date, so the fields move
to the new project from that day on: through the next assignment event, or
the daily job when Card Settings enables it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from card.settings import setting


# ---------- assignment helpers ----------
def _open_assignment(equipment):
	# An open assignment has an empty to_date (stored as NULL for a Date field);
	# `in (NULL,'')` never matches NULL in SQL, so use "is not set".
	rows = frappe.get_all(
		"Card Equipment Assignment",
		filters={"equipment": equipment, "to_date": ["is", "not set"]},
		fields=["name", "project"],
		order_by="from_date desc, creation desc",
		limit=1,
	)
	return rows[0] if rows else None


def _has_any_assignment(equipment):
	return bool(frappe.db.exists("Card Equipment Assignment", {"equipment": equipment}))


def covering_assignment(equipment, first_day, last_day):
	"""Latest assignment whose period overlaps [first_day, last_day] (F.7: the
	card's project follows it; retro months keep their historical project).
	None when nothing overlaps — the card's project is then free entry."""
	best = None
	for a in frappe.get_all(
		"Card Equipment Assignment",
		filters={"equipment": equipment},
		fields=["name", "project", "from_date", "to_date"],
	):
		if not a.from_date:
			continue
		f = getdate(a.from_date)
		t = getdate(a.to_date) if a.to_date else None
		if f <= getdate(last_day) and (t is None or t >= getdate(first_day)):
			if best is None or f > getdate(best.from_date):
				best = a
	return best


def _assigned_on(equipment, project, day):
	"""Is `equipment` assigned to `project` on `day` (within an assignment period)?"""
	for a in frappe.get_all(
		"Card Equipment Assignment",
		filters={"equipment": equipment, "project": project},
		fields=["from_date", "to_date"],
	):
		if not a.from_date:
			continue
		f = getdate(a.from_date)
		t = getdate(a.to_date) if a.to_date else None
		if f <= day and (t is None or day <= t):
			return True
	return False


def _in_force(rows, day):
	"""Assignments whose period contains `day` (an empty to_date is open)."""
	return [
		a
		for a in rows
		if a.from_date and getdate(a.from_date) <= day and (not a.to_date or getdate(a.to_date) >= day)
	]


# ---------- equipment location (#56) ----------
def sync_equipment_location(equipment, exclude=None, source="assignment"):
	"""Set the equipment's current_project / assignment_date from the assignment
	in force TODAY: its project and its start date. A future assignment never
	moves them; with none in force, or two overlapping, they are emptied —
	nothing is invented. Called only from assignment events (and the opt-in
	daily job, which visits only equipment that has assignments), so equipment
	without assignment history keeps its values. Writes only these two fields
	(db.set_value: the equipment's validate/on_update, and so the Asset
	dimension sync, do not run); an overwritten value leaves a comment."""
	if not equipment or not frappe.db.exists("Card Equipment", equipment):
		return
	filters = {"equipment": equipment}
	if exclude:
		filters["name"] = ["!=", exclude]
	rows = frappe.get_all(
		"Card Equipment Assignment", filters=filters, fields=["name", "project", "from_date", "to_date"]
	)
	today = getdate(nowdate())
	in_force = _in_force(rows, today)
	project, start = None, None
	if len(in_force) == 1:
		project, start = in_force[0].project, getdate(in_force[0].from_date)
	elif len(in_force) > 1:
		_record_overlap(equipment, sorted(a.name for a in in_force), today, source)
	stored = frappe.db.get_value(
		"Card Equipment", equipment, ["current_project", "assignment_date"], as_dict=True
	)
	old_project = stored.current_project or None
	old_start = getdate(stored.assignment_date) if stored.assignment_date else None
	if (old_project, old_start) == (project, start):
		return
	if old_project or old_start:
		message = {
			"assignment": _(
				"Location sync after an assignment change: project {0} → {1}; assignment date {2} → {3}"
			),
			"transfer": _("Location sync after a transfer: project {0} → {1}; assignment date {2} → {3}"),
			"daily": _("Daily location sync: project {0} → {1}; assignment date {2} → {3}"),
		}[source]
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Card Equipment",
				"reference_name": equipment,
				"content": message.format(old_project or "-", project or "-", old_start or "-", start or "-"),
			}
		).insert(ignore_permissions=True)
	frappe.db.set_value(
		"Card Equipment",
		equipment,
		{"current_project": project, "assignment_date": start},
		update_modified=False,
	)


# plain-text tag (comment HTML is sanitized), the same in every language
OVERLAP_MARK = "(overlap:"


def _record_overlap(equipment, assignments, day, source):
	"""Overlapping assignments in force: nothing is guessed (the location stays
	empty) and the case is recorded — a comment on the equipment's timeline,
	whatever its current fields hold, once per distinct set of assignments (a
	changed set is recorded again); the user acting in a request also gets a
	message, and the daily job adds one Error Log entry per newly recorded set.
	A failure to record never stops the location sync."""
	key = OVERLAP_MARK + ",".join(assignments) + ")"
	message = _(
		"Overlapping assignments in force on {0}: {1}. The current project and assignment date stay empty until the overlap is corrected."
	).format(day, ", ".join(assignments))
	frappe.msgprint(message, indicator="orange")  # shown to the user acting in a request
	frappe.db.savepoint("card_location_overlap")
	try:
		latest = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Card Equipment",
				"reference_name": equipment,
				"comment_type": "Info",
				"content": ["like", "%" + OVERLAP_MARK + "%"],
			},
			pluck="content",
			order_by="creation desc",
			limit=1,
		)
		if latest and key in latest[0]:
			return  # this exact set is already recorded
		frappe.get_doc(
			{
				"doctype": "Comment",
				"comment_type": "Info",
				"reference_doctype": "Card Equipment",
				"reference_name": equipment,
				"content": "%s %s" % (message, key),
			}
		).insert(ignore_permissions=True)
		if source == "daily":
			frappe.log_error(
				title=_("CARD equipment location overlap"),
				message="%s: %s" % (equipment, message),
				reference_doctype="Card Equipment",
				reference_name=equipment,
			)
	except Exception:
		frappe.db.rollback(save_point="card_location_overlap")


def sync_equipment_locations_daily():
	"""Daily job (hooks.scheduler_events): off unless Card Settings enables it.
	Each equipment runs in its own savepoint, so one failure neither stops nor
	undoes the others; the failures are reported in a single Error Log entry."""
	if not cint(setting("sync_equipment_location_daily")):
		return
	failed = []
	for equipment in sorted(
		{a.equipment for a in frappe.get_all("Card Equipment Assignment", fields=["equipment"])}
	):
		frappe.db.savepoint("card_location_sync")
		try:
			sync_equipment_location(equipment, source="daily")
		except Exception:
			frappe.db.rollback(save_point="card_location_sync")
			failed.append(equipment)
	if failed:
		frappe.log_error(
			title=_("CARD daily location sync"),
			message=_("The location of these equipment could not be synced: {0}").format(", ".join(failed)),
		)


def _components(unit):
	return [
		c.component
		for c in frappe.get_all("Card Equipment Component", filters={"parent": unit}, fields=["component"])
		if c.component
	]


def _periods_text(equipment, project):
	"""Human-readable assignment periods of `equipment` on `project` (for the
	unit error message), e.g. '2026-08-01 → 2026-08-10، 2026-08-13 → (open)'."""
	rows = frappe.get_all(
		"Card Equipment Assignment",
		filters={"equipment": equipment, "project": project},
		fields=["from_date", "to_date"],
		order_by="from_date",
	)
	parts = []
	for r in rows:
		if not r.from_date:
			continue
		end = getdate(r.to_date) if r.to_date else _("(open)")
		parts.append("%s → %s" % (getdate(r.from_date), end))
	return "، ".join(parts) if parts else _("no assignment on this project")


# ---------- transfer (Equipment Transport on_submit / on_cancel) ----------
def apply_transfer(txn):
	equipment = txn.equipment
	if not equipment or not txn.project or not txn.date:
		return
	tdate = getdate(txn.date)
	prev = _open_assignment(equipment)
	if prev and prev.project == txn.project:
		# already on this project; nothing to move
		return
	# one location sync for the whole transfer, not one per assignment write
	deferred = frappe.flags.get("card_defer_location_sync")
	frappe.flags.card_defer_location_sync = True
	try:
		if prev:
			# save (not db.set_value) so the change is in the assignment's history
			closing = frappe.get_doc("Card Equipment Assignment", prev.name)
			closing.to_date = tdate
			closing.save(ignore_permissions=True, ignore_version=False)
			txn.db_set("previous_assignment", prev.name, update_modified=False)
			new_from = add_days(tdate, 1)
		else:
			new_from = tdate
		na = frappe.new_doc("Card Equipment Assignment")
		na.equipment = equipment
		na.project = txn.project
		na.from_date = new_from
		na.equipment_name = frappe.db.get_value("Card Equipment", equipment, "equipment_name")
		na.insert(ignore_permissions=True)
		txn.db_set("created_assignment", na.name, update_modified=False)
	finally:
		frappe.flags.card_defer_location_sync = deferred
	sync_equipment_location(equipment, source="transfer")


def check_cancel_allowed(txn):
	"""Guards, run in before_cancel (before docstatus flips) so a block leaves
	the document submitted."""
	equipment = txn.equipment
	if not equipment or not txn.date:
		return
	tdate = getdate(txn.date)
	# (a) no later transfer for this piece
	if frappe.get_all(
		"Equipment Transport",
		filters={"equipment": equipment, "docstatus": 1, "date": [">", str(tdate)], "name": ["!=", txn.name]},
		limit=1,
	):
		frappe.throw(_("Cannot cancel: a later transfer exists for this equipment. Cancel it first."))
	# (b) no card day recorded on the new project after the transfer
	if _card_day_after(equipment, txn.project, tdate):
		frappe.throw(
			_("Cannot cancel: operation days are recorded on project {0} after the transfer date.").format(
				txn.project
			)
		)


def reverse_transfer(txn):
	"""Undo the transfer, run in on_cancel (guards already passed)."""
	equipment = txn.equipment
	if not equipment or not txn.date:
		return
	deferred = frappe.flags.get("card_defer_location_sync")
	frappe.flags.card_defer_location_sync = True
	try:
		if txn.created_assignment and frappe.db.exists("Card Equipment Assignment", txn.created_assignment):
			frappe.delete_doc(
				"Card Equipment Assignment", txn.created_assignment, force=1, ignore_permissions=True
			)
		if txn.previous_assignment and frappe.db.exists("Card Equipment Assignment", txn.previous_assignment):
			reopened = frappe.get_doc("Card Equipment Assignment", txn.previous_assignment)
			reopened.to_date = None
			reopened.save(ignore_permissions=True, ignore_version=False)
	finally:
		frappe.flags.card_defer_location_sync = deferred
	sync_equipment_location(equipment, source="transfer")


def _card_day_after(equipment, project, tdate):
	return bool(
		frappe.db.sql(
			"""select 1 from `tabCard Monthly Card Day` d
			join `tabCard Monthly Card` c on c.name = d.parent
			where c.equipment=%s and c.project=%s and c.docstatus=1
			and d.working_hours > 0 and d.operation_date > %s limit 1""",
			(equipment, project, str(tdate)),
		)
	)


# ---------- card-day validation (Card Monthly Card before_validate) ----------
def validate_card_days(card):
	"""Every working day must fall inside an assignment period for the card's
	project. For a unit, every component must be assigned to the project that
	day. Skipped for equipment with no assignment history (backward-compatible)."""
	equipment = card.equipment
	project = card.project
	if not equipment or not project:
		return
	is_unit = frappe.db.get_value("Card Equipment", equipment, "is_unit")
	if is_unit:
		# components are checked as before: all of them once any has history.
		# #56: the unit's own assignments are checked too — components without
		# history no longer switch the whole check off.
		components = _components(equipment)
		members = components if any(_has_any_assignment(m) for m in components) else []
		if _has_any_assignment(equipment):
			members = [equipment, *members]
	else:
		members = [equipment] if _has_any_assignment(equipment) else []
	if not members:
		return
	for d in card.days:
		if not d.operation_date or flt(d.working_hours) <= 0:
			continue
		day = getdate(d.operation_date)
		missing = [m for m in members if not _assigned_on(m, project, day)]
		if not missing:
			continue
		if is_unit:
			details = []
			for m in missing:
				mname = frappe.db.get_value("Card Equipment", m, "equipment_name") or m
				details.append("%s (%s)" % (mname, _periods_text(m, project)))
			frappe.throw(
				_(
					"Unit card for project {0}: on {1} these components are not assigned to this project: {2}. "
					"Move every component to the project before recording this day."
				).format(project, day, "؛ ".join(details))
			)
		frappe.throw(
			_("Operation day {0} is outside the equipment's assignment period for project {1}.").format(
				day, project
			)
		)
