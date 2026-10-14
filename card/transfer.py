# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment Transport as a location transfer (phase A).

Submitting an Equipment Transport moves the equipment to a new project:
it closes the current open Card Equipment Assignment at the transfer date,
opens a new one for the new project, and updates current_project. Card days
must then fall inside an assignment period for the card's project. Units (a
Card Equipment with components) derive their effective project from their
component pieces: a day is valid for the unit on a project only when EVERY
component is assigned there that day.

Backward-compatible: equipment with NO assignment history is not constrained,
so existing/seed cards and controller tests are unaffected.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate


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


def _components(unit):
	return [
		c.component
		for c in frappe.get_all(
			"Card Equipment Component", filters={"parent": unit}, fields=["component"]
		)
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
	if prev:
		frappe.db.set_value("Card Equipment Assignment", prev.name, "to_date", tdate)
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
	frappe.db.set_value("Card Equipment", equipment, "current_project", txn.project)


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
	if txn.created_assignment and frappe.db.exists("Card Equipment Assignment", txn.created_assignment):
		frappe.delete_doc(
			"Card Equipment Assignment", txn.created_assignment, force=1, ignore_permissions=True
		)
	if txn.previous_assignment and frappe.db.exists("Card Equipment Assignment", txn.previous_assignment):
		frappe.db.set_value("Card Equipment Assignment", txn.previous_assignment, "to_date", None)
		prev_project = frappe.db.get_value("Card Equipment Assignment", txn.previous_assignment, "project")
		frappe.db.set_value("Card Equipment", equipment, "current_project", prev_project)
	else:
		frappe.db.set_value("Card Equipment", equipment, "current_project", None)


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
	members = _components(equipment) if is_unit else [equipment]
	# constrain only when assignment data exists for at least one member
	if not any(_has_any_assignment(m) for m in members):
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
