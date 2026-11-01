# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""R1 (CARD 4.5.0): where an employee worked, day by day — Employee → Equipment → Project →
Cost Center — from effective-dated Card Personnel Assignments and the equipment's own
project assignments. CARD stores no attendance, shift, leave or pay: HRMS stays their owner.
This module only resolves assignments (read-only); the cost allocation of R2 builds on it.
"""

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, flt, getdate

DOCTYPE = "Card Personnel Assignment"
OPEN_END = "9999-12-31"
MAX_DAYS = 62  # a query covers at most about two payroll months


def _cost_center_of_project(project):
	return frappe.db.get_value("Project", project, "cost_center") if project else None


def equipment_project_on(equipment, day, cache=None):
	"""(project, cost center, assignment) of an equipment on a day, from Card Equipment
	Assignment (history kept by transports; never rewritten). ``cache`` (a dict) keeps the
	equipment's assignments and the project cost centers for repeated days."""
	day = getdate(day)
	cache = {} if cache is None else cache
	key = ("ea", equipment)
	if key not in cache:
		cache[key] = frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": equipment, "from_date": ["is", "set"]},
			fields=["name", "project", "cost_center", "from_date", "to_date"],
			order_by="from_date desc",
		)
	for row in cache[key]:
		if getdate(row.from_date) <= day and (not row.to_date or getdate(row.to_date) >= day):
			return row.project, row.cost_center or _project_cc(row.project, cache), row.name
	return None, None, None


def _project_cc(project, cache):
	key = ("pcc", project)
	if key not in cache:
		cache[key] = _cost_center_of_project(project)
	return cache[key]


def assignments_covering(employee, start, end, companies=None):
	"""Submitted personnel assignments of the employee that overlap [start, end] (only of
	``companies`` when given: a report never mixes in another company's history)."""
	start, end = str(getdate(start)), str(getdate(end))
	filters = {"employee": employee, "docstatus": 1, "from_date": ["<=", end]}
	if companies is not None:
		filters["company"] = ["in", list(companies) or [""]]
	return frappe.get_all(
		DOCTYPE,
		filters=filters,
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", start]],
		fields=[
			"name",
			"assignment_type",
			"card_equipment",
			"project",
			"cost_center",
			"role",
			"share_percent",
			"from_date",
			"to_date",
		],
		order_by="from_date asc",
	)


def resolve_day(employee, day, rows=None, cache=None):
	"""Where the employee worked on ``day``: a list of {project, cost_center, card_equipment,
	share, assignment, equipment_assignment, issue}. An entry with ``issue`` set has no
	verified project (it goes to review, never to an arbitrary project)."""
	day = getdate(day)
	rows = rows if rows is not None else assignments_covering(employee, day, day)
	out = []
	for row in rows:
		if getdate(row.from_date) > day or (row.to_date and getdate(row.to_date) < day):
			continue
		entry = frappe._dict(
			assignment=row.name,
			role=row.role,
			share=flt(row.share_percent) / 100.0,
			card_equipment=row.card_equipment,
			project=None,
			cost_center=None,
			equipment_assignment=None,
			issue=None,
		)
		if row.assignment_type == "Equipment":
			project, cost_center, ea = equipment_project_on(row.card_equipment, day, cache)
			entry.update(project=project, cost_center=cost_center, equipment_assignment=ea)
			if not project:
				entry.issue = _("The equipment has no project assignment on this day.")
		else:
			entry.update(
				project=row.project, cost_center=row.cost_center or _cost_center_of_project(row.project)
			)
		if entry.project and not entry.cost_center:
			entry.issue = _("No cost center for project {0}.").format(entry.project)
		out.append(entry)
	return out


@frappe.whitelist(methods=["GET"])
def employee_days(employee: str, from_date: str, to_date: str):
	"""Day-by-day resolution of one employee over at most two months (read-only). Days
	without an assignment are listed with an issue for review."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	from card.report_access import permitted_companies

	allowed = permitted_companies(DOCTYPE)
	company = frappe.db.get_value("Employee", employee, "company")
	if not company or company not in allowed:
		frappe.throw(_("You may not read this employee's assignments."), frappe.PermissionError)
	start, end = getdate(from_date), getdate(to_date)
	if end < start or date_diff(end, start) + 1 > MAX_DAYS:
		frappe.throw(_("Choose a period of at most {0} days.").format(MAX_DAYS))
	rows = assignments_covering(employee, start, end, companies=allowed)
	cache = {}
	days = []
	day = start
	while day <= end:
		entries = resolve_day(employee, day, rows, cache)
		days.append(
			{
				"date": str(day),
				"entries": entries,
				"issue": None if entries else _("No assignment on this day."),
			}
		)
		day = add_days(day, 1)
	return days


def max_concurrent_share(employee, start, end, exclude=None, extra=None):
	"""Highest sum of share_percent of submitted assignments on any day in [start, end]
	(plus ``extra`` = (from, to, share) of the row being checked)."""
	rows = [r for r in assignments_covering(employee, start, end) if r.name != exclude]
	if extra:
		rows.append(frappe._dict(from_date=extra[0], to_date=extra[1], share_percent=extra[2]))
	points = set()
	for r in rows:
		points.add(max(getdate(r.from_date), getdate(start)))
	worst = 0.0
	for p in points:
		if p > getdate(end):
			continue
		total = sum(
			flt(r.share_percent)
			for r in rows
			if getdate(r.from_date) <= p and (not r.to_date or getdate(r.to_date) >= p)
		)
		worst = max(worst, total)
	return worst


def current_operator(equipment):
	"""The employee with an open Operator assignment on the equipment today, if exactly one."""
	today = frappe.utils.today()
	rows = frappe.get_all(
		DOCTYPE,
		filters={
			"card_equipment": equipment,
			"docstatus": 1,
			"role": "Operator",
			"from_date": ["<=", today],
		},
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", today]],
		pluck="employee",
		distinct=True,
	)
	return rows[0] if len(rows) == 1 else None


def sync_equipment_operator(equipment, released=None):
	"""Card Equipment.operator follows the one open Operator assignment. When the assignment
	of ``released`` ends or is cancelled and nobody else is assigned, an operator CARD set
	from it is cleared. A manual operator is never replaced by nothing, and equipment whose
	operator is charged to the lessor is left alone. The change is recorded in a Comment."""
	if not equipment:
		return
	eq = frappe.db.get_value(
		"Card Equipment", equipment, ["operator", "ownership", "operator_on"], as_dict=True
	)
	if not eq or (eq.ownership != "ملك" and eq.operator_on != "الشركة"):
		return  # the operator field is not used for this equipment
	operator = current_operator(equipment)
	if operator and operator != eq.operator:
		value = {
			"operator": operator,
			"operator_name": frappe.db.get_value("Employee", operator, "employee_name"),
		}
	elif not operator and released and eq.operator == released:
		value = {"operator": None, "operator_name": None}
	else:
		return
	frappe.db.set_value("Card Equipment", equipment, value)
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Card Equipment",
			"reference_name": equipment,
			"content": _("Operator set from the personnel assignments: {0}").format(
				value["operator_name"] or "-"
			),
		}
	).insert(ignore_permissions=True)  # audit note of a derived field


def daily_operator_sync():
	"""Scheduler (daily): assignments that start or end today move the operator too."""
	for equipment in frappe.get_all(
		DOCTYPE, filters={"docstatus": 1, "role": "Operator"}, pluck="card_equipment", distinct=True
	):
		try:
			sync_equipment_operator(equipment)
		except Exception:
			frappe.log_error(title=_("CARD operator sync of {0} failed").format(equipment))


@frappe.whitelist(methods=["POST"])
def seed_from_employee_project(from_date: str, dry_run: int | str = 1):
	"""System Manager tool: one DRAFT Project assignment per active employee that has the
	legacy ``Employee.custom_project`` (DAWM field) and no CARD assignment, starting on the
	date the owner confirms. Nothing is submitted; a dry run writes nothing."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can seed personnel assignments."), frappe.PermissionError)
	# anything but an explicit 0 / false is a dry run (fail closed)
	dry_run = 0 if str(dry_run).strip().lower() in ("0", "false", "no") else 1
	if not frappe.get_meta("Employee").has_field("custom_project"):
		return {"dry_run": dry_run, "candidates": [], "created": [], "skipped": []}
	have = set(frappe.get_all(DOCTYPE, filters={"docstatus": ["<", 2]}, pluck="employee"))
	candidates = [
		r
		for r in frappe.get_all(
			"Employee",
			filters={"status": "Active", "custom_project": ["is", "set"]},
			fields=["name", "company", "custom_project"],
		)
		if r.name not in have
	]
	created, skipped = [], []
	for r in candidates:
		if frappe.db.get_value("Project", r.custom_project, "company") != r.company:
			skipped.append({"employee": r.name, "reason": _("The project belongs to another company.")})
			continue
		if dry_run:
			continue
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"employee": r.name,
				"assignment_type": "Project",
				"project": r.custom_project,
				"role": "Site Staff",
				"from_date": from_date,
				"notes": _("Seeded from the legacy Employee project field; confirm the dates before submit."),
			}
		)
		try:
			frappe.db.savepoint("card_seed")
			doc.insert()  # the System Manager's own rights; a draft for review
			created.append(doc.name)
		except frappe.ValidationError as e:
			frappe.db.rollback(save_point="card_seed")
			skipped.append({"employee": r.name, "reason": str(e)})
	return {
		"dry_run": dry_run,
		"candidates": [{"employee": r.name, "project": r.custom_project} for r in candidates],
		"created": created,
		"skipped": skipped,
	}
