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


def month_assignments(equipment, first_day, last_day):
	"""Assignments of `equipment` overlapping [first_day, last_day], oldest first.
	A unit with no assignment of its own uses its components' (v3.0.0)."""

	def overlapping(name):
		rows = []
		for a in frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": name},
			fields=["name", "project", "from_date", "to_date"],
		):
			if not a.from_date:
				continue
			f = getdate(a.from_date)
			t = getdate(a.to_date) if a.to_date else None
			if f <= getdate(last_day) and (t is None or t >= getdate(first_day)):
				rows.append(a)
		return rows

	rows = overlapping(equipment)
	if not rows and frappe.db.get_value("Card Equipment", equipment, "is_unit"):
		for c in _component_rows(equipment):
			rows.extend(overlapping(c.component))
	return sorted(rows, key=lambda a: getdate(a.from_date))


def assignment_projects(equipment, first_day, last_day):
	"""Projects the equipment was on during the period (v3.0.0: the card's project
	comes only from these), in the order it reached them."""
	projects = []
	for a in month_assignments(equipment, first_day, last_day):
		if a.project not in projects:
			projects.append(a.project)
	return projects


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


def _component_rows(unit):
	return [
		c
		for c in frappe.get_all(
			"Card Equipment Component",
			filters={"parent": unit, "parenttype": "Card Equipment"},
			fields=["component", "from_date", "to_date"],
		)
		if c.component
	]


def _in_unit_on(row, day):
	"""v3.0.0: a component counts for a unit only between its From and To dates
	(either empty = open), so a replaced or moved piece stops being checked."""
	return (not row.from_date or getdate(row.from_date) <= day) and (
		not row.to_date or getdate(row.to_date) >= day
	)


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
	return _(", ", context="Card").join(parts) if parts else _("no assignment on this project")


def current_location(equipment, exclude=None):
	"""Where the equipment is now (Owner 2026-10-19): on the project of its open
	assignment; otherwise wherever its last approved transport sent it (workshop,
	storage, supplier); otherwise in storage — equipment never assigned to a project is
	recorded as coming from storage on its first move. `exclude` leaves out the
	transport being edited."""
	open_row = _open_assignment(equipment)
	if open_row:
		return frappe._dict(type="Project", project=open_row.project, location=None)
	last = frappe.db.sql(
		"""select t.destination_type, t.project, t.destination_location
		from `tabEquipment Transport Item` i
		join `tabEquipment Transport` t on t.name = i.parent and i.parenttype = 'Equipment Transport'
		where i.card_equipment=%s and t.docstatus=1 and t.name != %s
		order by t.date desc, t.creation desc limit 1""",
		(equipment, exclude or ""),
		as_dict=True,
	)
	if last and last[0].destination_type and last[0].destination_type != "Project":
		return frappe._dict(
			type=last[0].destination_type, project=None, location=last[0].destination_location
		)
	return frappe._dict(type="Storage", project=None, location=None, initial=1)


# ---------- transfer (Equipment Transport on_submit / on_cancel) ----------
# v3.0.0: a transport moves every equipment in its `items` table; each row keeps its
# own previous/created assignment so cancel undoes exactly what submit did.
def apply_transfer(txn):
	if not txn.date:
		return
	if (txn.get("destination_type") or "Project") == "Project" and not txn.project:
		return
	for row in txn.get("items") or []:
		if row.card_equipment:
			_apply_row_transfer(txn, row)


def _apply_row_transfer(txn, row):
	equipment = row.card_equipment
	tdate = getdate(txn.date)
	prev = _open_assignment(equipment)
	if (txn.get("destination_type") or "Project") != "Project":
		# workshop / storage / supplier: the project assignment (if any) ends on the
		# transport date and nothing new opens, so card days after it are refused
		# (validate_card_days); earlier cards stay as they are
		if not prev:
			return  # not on a project: the move is recorded on the transport only
		deferred = frappe.flags.get("card_defer_location_sync")
		frappe.flags.card_defer_location_sync = True
		try:
			closing = frappe.get_doc("Card Equipment Assignment", prev.name)
			closing.to_date = tdate
			closing.save(ignore_permissions=True, ignore_version=False)
			_set_link(txn, row, "previous_assignment", prev.name)
		finally:
			frappe.flags.card_defer_location_sync = deferred
		sync_equipment_location(equipment, source="transfer")
		return
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
			_set_link(txn, row, "previous_assignment", prev.name)
			new_from = add_days(tdate, 1)
		else:
			new_from = tdate
		na = frappe.new_doc("Card Equipment Assignment")
		na.equipment = equipment
		na.project = txn.project
		na.from_date = new_from
		# R1: the new row names its cost center (the project's), like a hand-made assignment
		from card.card.doctype.card_equipment_assignment.card_equipment_assignment import (
			_valid_cost_center,
		)

		project_cc = frappe.db.get_value("Project", txn.project, "cost_center")
		company = frappe.db.get_value("Card Equipment", equipment, "company")
		if project_cc and _valid_cost_center(project_cc, company):
			na.cost_center = project_cc  # else empty: the posting resolver refuses it for review
		na.equipment_name = frappe.db.get_value("Card Equipment", equipment, "equipment_name")
		na.insert(ignore_permissions=True)
		_set_link(txn, row, "created_assignment", na.name)
	finally:
		frappe.flags.card_defer_location_sync = deferred
	sync_equipment_location(equipment, source="transfer")


def _set_link(txn, row, fieldname, value):
	row.db_set(fieldname, value, update_modified=False)
	# the header mirrors the first row, like `equipment` (older readers and links)
	if row.idx == 1:
		txn.db_set(fieldname, value, update_modified=False)


def check_cancel_allowed(txn):
	"""Guards, run in before_cancel (before docstatus flips) so a block leaves
	the document submitted."""
	if not txn.date:
		return
	tdate = getdate(txn.date)
	for row in txn.get("items") or []:
		equipment = row.card_equipment
		if not equipment:
			continue
		# (a) no later transfer for this piece; (d) nor one on the same date that came
		# after this one (the date alone cannot order two moves of one day)
		if _later_transfer(equipment, tdate, txn.name) or _depends_on(txn, row):
			frappe.throw(
				_("Cannot cancel: a later transfer exists for equipment {0}. Cancel it first.").format(
					equipment
				)
			)
		# (b) no card day recorded on the new project after the transfer
		if _card_day_after(equipment, txn.project, tdate):
			frappe.throw(
				_(
					"Cannot cancel: operation days are recorded for equipment {0} on project {1} after the transfer date."
				).format(equipment, txn.project)
			)
		# (c) the row's assignment links are the ones this transport wrote on submit; one
		# that is missing has nothing to undo, one changed or forged since is never touched,
		# so a cancel never undoes only half a move
		for fieldname in ("created_assignment", "previous_assignment"):
			assignment = row.get(fieldname)
			if (
				assignment
				and frappe.db.exists("Card Equipment Assignment", assignment)
				and not _written_by(txn, row, fieldname)
			):
				frappe.throw(
					_(
						"Cannot cancel: assignment {0} of equipment {1} was not written by this transport or was changed after it."
					).format(assignment, equipment)
				)


def _depends_on(txn, row):
	"""True when another submitted transport moved this row's machine after this one: on a
	later date, or on the same date after closing the assignment this row opened or opening
	one of its own. The machine's transport rows are read with a lock (index on
	card_equipment), which returns the latest committed rows (MariaDB REPEATABLE READ) and
	makes a cancel wait for a submit of the same machine in flight; the lock order (rows,
	then assignments) is the one submit uses. A row without links (an old transport, or a
	machine already on the project) has nothing to undo."""
	ours = {row.created_assignment, row.previous_assignment} - {None, ""}
	if not ours:
		return False
	others = frappe.db.sql(
		"""select parent, docstatus, created_assignment, previous_assignment
		from `tabEquipment Transport Item`
		where card_equipment=%s and parenttype='Equipment Transport' and parent != %s
		for update""",
		(row.card_equipment, txn.name),
		as_dict=True,
	)
	others = [other for other in others if other.docstatus == 1]
	if not others:
		return False
	dates = dict(
		frappe.get_all(
			"Equipment Transport",
			filters={"name": ["in", list({other.parent for other in others})]},
			fields=["name", "date"],
			as_list=True,
		)
	)
	tdate = getdate(txn.date)
	for other in others:
		other_date = getdate(dates.get(other.parent)) if dates.get(other.parent) else None
		if not other_date or other_date < tdate:
			continue
		if other_date > tdate:
			return True
		if row.created_assignment and other.previous_assignment == row.created_assignment:
			return True
		if other.created_assignment and other.created_assignment not in ours:
			return True
	return False


def _later_transfer(equipment, tdate, exclude):
	return bool(
		frappe.db.sql(
			"""select 1 from `tabEquipment Transport Item` i
			join `tabEquipment Transport` t on t.name = i.parent and i.parenttype = 'Equipment Transport'
			where i.card_equipment=%s and t.docstatus=1 and t.date > %s and t.name != %s limit 1""",
			(equipment, str(tdate), exclude),
		)
	)


def reverse_transfer(txn):
	"""Undo the transfer, run in on_cancel (guards already passed)."""
	if not txn.date:
		return
	for row in txn.get("items") or []:
		if not row.card_equipment:
			continue
		deferred = frappe.flags.get("card_defer_location_sync")
		frappe.flags.card_defer_location_sync = True
		try:
			# only assignments this transport wrote on submit (checked again in before_cancel)
			if row.created_assignment and _written_by(txn, row, "created_assignment"):
				frappe.delete_doc(
					"Card Equipment Assignment", row.created_assignment, force=1, ignore_permissions=True
				)
			if row.previous_assignment and _written_by(txn, row, "previous_assignment"):
				reopened = frappe.get_doc("Card Equipment Assignment", row.previous_assignment)
				reopened.to_date = None
				reopened.save(ignore_permissions=True, ignore_version=False)
		finally:
			frappe.flags.card_defer_location_sync = deferred
		sync_equipment_location(row.card_equipment, source="transfer")


def _written_by(txn, row, fieldname):
	"""True only for an assignment `apply_transfer` wrote for this row: of the row's
	equipment, a machine of the transport's company, claimed by no other submitted
	transport, and created on the transport's project from the transport date or the day
	after and still open (created_assignment) or closed on the transport date
	(previous_assignment). A forged or legacy link, or one changed since, is left as it is.
	Read with a lock: the latest committed assignment, kept until the cancel ends."""
	assignment = row.get(fieldname)
	a = frappe.db.get_value(
		"Card Equipment Assignment",
		assignment,
		["equipment", "project", "from_date", "to_date"],
		as_dict=True,
		for_update=True,
	)
	if not a or a.equipment != row.card_equipment:
		return False
	if frappe.db.get_value("Card Equipment", a.equipment, "company") != txn.company:
		return False
	tdate = getdate(txn.date)
	if fieldname == "created_assignment":
		if a.project != txn.project or getdate(a.from_date) not in (tdate, getdate(add_days(tdate, 1))):
			return False
		if a.to_date:
			return False
	elif not a.to_date or getdate(a.to_date) != tdate:
		return False
	item = frappe.qb.DocType("Equipment Transport Item")
	transport = frappe.qb.DocType("Equipment Transport")
	claimed = (
		frappe.qb.from_(item)
		.join(transport)
		.on((transport.name == item.parent) & (item.parenttype == "Equipment Transport"))
		.select(item.name)
		.where(item[fieldname] == assignment)
		.where(transport.docstatus == 1)
		.where(transport.name != txn.name)
		.limit(1)
		.run()
	)
	return not claimed


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
	component_rows = []
	if is_unit:
		# components are checked as before: all of them once any has history.
		# #56: the unit's own assignments are checked too — components without
		# history no longer switch the whole check off.
		rows = _component_rows(equipment)
		if any(_has_any_assignment(r.component) for r in rows):
			component_rows = rows
		unit_checked = _has_any_assignment(equipment)
	else:
		unit_checked = _has_any_assignment(equipment)
	if not unit_checked and not component_rows:
		return
	for d in card.days:
		if not d.operation_date or flt(d.working_hours) <= 0:
			continue
		day = getdate(d.operation_date)
		members = [r.component for r in component_rows if _in_unit_on(r, day)]
		if unit_checked:
			members = [equipment, *members]
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
				).format(project, day, _("; ", context="Card").join(details))
			)
		frappe.throw(
			_("Operation day {0} is outside the equipment's assignment period for project {1}.").format(
				day, project
			)
		)
