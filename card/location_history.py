# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment location history (#53, #127; FR-130). Read-only.

Where an equipment was on each day of a period, as date-aware segments. The rules are the
ones `card.transfer` already applies; nothing here decides a location of its own:

- on a project while a Card Equipment Assignment is in force (`card.transfer._in_force`).
  The assignment dates are the ones the transport wrote, so the move-day rule recorded on
  each transport (FR-117) is already in them;
- otherwise where the last submitted Equipment Transport on or before that day sent it
  (workshop, storage, supplier), as `card.transfer.current_location` does for today;
- otherwise in the initial place of the equipment's company (FR-116,
  Card Company Settings `initial_location`; empty when it is not set).

A move to a workshop, storage or supplier on day T closes the project assignment on T, so
the history shows the project on T and the new place from T+1.

A unit (Card Equipment with components) counts its own assignments and transports on every
day, and those of a component only on the days that component is in the unit
(`card.transfer._in_unit_on`). Every day is decided from the full history, so a row never
depends on the date range asked for; the range only clips it.

A segment's source is the transport that opened the assignment (its row
`created_assignment`), else the assignment itself; the transport for a workshop, storage or
supplier place; none for the initial place. Two projects in force on one day (overlapping
assignments) give one segment each, marked `overlap`."""

from itertools import pairwise

import frappe
from frappe.query_builder.functions import Max
from frappe.utils import add_days, getdate

from card.settings import company_setting
from card.transfer import _in_force, _in_unit_on

ASSIGNMENT = "Card Equipment Assignment"
TRANSPORT = "Equipment Transport"
EQUIPMENT = "Card Equipment"
PROJECT = "Project"
SUPPLIER = "Supplier"
INITIAL = "Initial"


# ---------- batched reads ----------
def _unit_components(units, company):
	"""Component rows of these units (component, from_date, to_date), per unit; only
	components of the same company are read."""
	result = {unit: [] for unit in units}
	if not units:
		return result
	rows = frappe.get_all(
		"Card Equipment Component",
		filters={"parent": ["in", list(units)], "parenttype": EQUIPMENT},
		fields=["parent", "component", "from_date", "to_date"],
		order_by="idx asc",
		limit_page_length=0,
	)
	components = {r.component for r in rows if r.component}
	same_company = (
		set(
			frappe.get_all(
				EQUIPMENT,
				filters={"name": ["in", list(components)], "company": company},
				pluck="name",
				limit_page_length=0,
			)
		)
		if components
		else set()
	)
	for r in rows:
		if r.component in same_company:
			result[r.parent].append(r)
	return result


def _assignments(equipment_names, start, end):
	"""Assignments of these machines that touch [start, end], per machine (one query)."""
	result = {name: [] for name in equipment_names}
	if not equipment_names:
		return result
	rows = frappe.get_all(
		ASSIGNMENT,
		filters=[
			["equipment", "in", list(equipment_names)],
			["from_date", "<=", end],
		],
		or_filters=[["to_date", "is", "not set"], ["to_date", ">=", start]],
		fields=["name", "equipment", "project", "from_date", "to_date"],
		order_by="from_date asc, creation asc",
		limit_page_length=0,
	)
	for r in rows:
		result[r.equipment].append(r)
	return result


def _transport_query():
	item = frappe.qb.DocType("Equipment Transport Item")
	transport = frappe.qb.DocType(TRANSPORT)
	query = (
		frappe.qb.from_(item)
		.join(transport)
		.on((transport.name == item.parent) & (item.parenttype == TRANSPORT))
		.select(
			item.card_equipment,
			item.created_assignment,
			transport.name,
			transport.date,
			transport.creation,
			transport.destination_type,
			transport.destination_location,
			transport.equipment_supplier,
		)
		.where(transport.docstatus == 1)
	)
	return query, item, transport


def submitted_moves(equipment_names, company, start, end):
	"""Submitted transports of the company moving these machines: per machine, its last one
	before `start` (where it stood when the range opens) and those inside [start, end], in
	move order (date, then creation, as current_location orders them)."""
	moves = {name: [] for name in equipment_names}
	if not equipment_names:
		return moves
	names = list(equipment_names)
	query, item, transport = _transport_query()
	inside = (
		query.where(item.card_equipment.isin(names))
		.where(transport.company == company)
		.where(transport.date >= start)
		.where(transport.date <= end)
		.run(as_dict=True)
	)
	# the last move before the range, per machine: the latest (date, creation) of each
	latest = (
		frappe.qb.from_(item)
		.join(transport)
		.on((transport.name == item.parent) & (item.parenttype == TRANSPORT))
		.select(item.card_equipment, Max(transport.date).as_("date"))
		.where(item.card_equipment.isin(names))
		.where(transport.docstatus == 1)
		.where(transport.company == company)
		.where(transport.date < start)
		.groupby(item.card_equipment)
		.run(as_dict=True)
	)
	before = []
	if latest:
		last_day = {r.card_equipment: getdate(r.date) for r in latest}
		dated = (
			query.where(item.card_equipment.isin(list(last_day)))
			.where(transport.company == company)
			.where(transport.date.isin(sorted({str(d) for d in last_day.values()})))
			.run(as_dict=True)
		)
		on_last_day = {}
		for r in dated:
			if getdate(r.date) == last_day[r.card_equipment]:
				on_last_day.setdefault(r.card_equipment, []).append(r)
		before = [max(rows, key=_move_order) for rows in on_last_day.values()]
	for r in sorted(before + inside, key=_move_order):
		moves[r.card_equipment].append(r)
	return moves


def _move_order(move):
	return (getdate(move.date), move.creation)


def _opened_by(assignment_names, company):
	"""Transport that opened each assignment (its row created_assignment), one query."""
	if not assignment_names:
		return {}
	query, item, transport = _transport_query()
	rows = (
		query.where(item.created_assignment.isin(list(assignment_names)))
		.where(transport.company == company)
		.run(as_dict=True)
	)
	return {r.created_assignment: r.name for r in rows}


# ---------- segments ----------
def company_segments(company, start, end, equipment_rows):
	"""Segments of every machine in `equipment_rows` (name, is_unit; all of `company`)
	inside [start, end], oldest first per machine."""
	start, end = getdate(start), getdate(end)
	names = [r.name for r in equipment_rows]
	units = [r.name for r in equipment_rows if r.get("is_unit")]
	components = _unit_components(units, company)
	every = set(names) | {c.component for rows in components.values() for c in rows}
	assignments = _assignments(every, start, end)
	moves = submitted_moves(every, company, start, end)
	opened_by = _opened_by({a.name for rows in assignments.values() for a in rows}, company)
	initial_place = company_setting(company, "initial_location")
	result = []
	for name in names:
		history = _History(name, components.get(name) or [], assignments, moves, opened_by, initial_place)
		result.extend(history.segments(start, end))
	return result


class _History:
	"""One machine's own history plus, for a unit, its components' on their member days."""

	def __init__(self, equipment, component_rows, assignments, moves, opened_by, initial_place):
		self.equipment = equipment
		self.component_rows = component_rows
		self.assignments = assignments
		self.moves = moves
		self.opened_by = opened_by
		self.initial_place = initial_place

	def _members(self, day):
		return [r.component for r in self.component_rows if _in_unit_on(r, day)]

	def _cuts(self, start, end):
		cuts = {start, add_days(end, 1)}
		names = [self.equipment] + [r.component for r in self.component_rows]
		for name in names:
			for a in self.assignments.get(name) or []:
				if a.from_date:
					cuts.add(getdate(a.from_date))
				if a.to_date:
					cuts.add(getdate(add_days(a.to_date, 1)))
			for m in self.moves.get(name) or []:
				cuts.add(getdate(m.date))
		for r in self.component_rows:
			if r.from_date:
				cuts.add(getdate(r.from_date))
			if r.to_date:
				cuts.add(getdate(add_days(r.to_date, 1)))
		return sorted(c for c in (getdate(c) for c in cuts) if start <= c <= add_days(end, 1))

	def segments(self, start, end):
		segments, open_runs = [], {}
		for first, nxt in pairwise(self._cuts(start, end)):
			last = add_days(nxt, -1)
			here = self._places_on(first)
			for key in list(open_runs):
				if key not in here:
					segments.append(open_runs.pop(key))
			for key, place in here.items():
				if key in open_runs:
					open_runs[key]["to_date"] = last
				else:
					open_runs[key] = dict(place, equipment=self.equipment, from_date=first, to_date=last)
		segments.extend(open_runs.values())
		return sorted(segments, key=lambda s: (s["from_date"], s["location_type"], s["project"] or ""))

	def _places_on(self, day):
		"""Where the machine is on `day`, keyed so equal places on consecutive days merge."""
		members = self._members(day)
		in_force = list(_in_force(self.assignments.get(self.equipment) or [], day))
		for component in members:
			in_force.extend(_in_force(self.assignments.get(component) or [], day))
		if in_force:
			return self._projects(in_force)
		last = None
		for name in [self.equipment, *members]:
			for m in self.moves.get(name) or []:
				if getdate(m.date) <= day and (last is None or _move_order(m) > _move_order(last)):
					last = m
		if last and last.destination_type and last.destination_type != PROJECT:
			location = (
				last.equipment_supplier if last.destination_type == SUPPLIER else last.destination_location
			)
			return {
				(last.destination_type, location, TRANSPORT, last.name): _place(
					last.destination_type, None, location, TRANSPORT, last.name
				)
			}
		return {
			(INITIAL, self.initial_place, None, None): _place(INITIAL, None, self.initial_place, None, None)
		}

	def _projects(self, in_force):
		"""One place per project in force: the unit's own assignment first, then the earliest
		component assignment, so the source stays the same while the same rows are in force."""
		own = {a.name for a in self.assignments.get(self.equipment) or []}
		chosen = {}
		for a in sorted(in_force, key=lambda a: (a.name not in own, getdate(a.from_date), a.name)):
			chosen.setdefault(a.project, a)
		overlap = len(chosen) > 1
		places = {}
		for project, a in chosen.items():
			source = (TRANSPORT, self.opened_by[a.name]) if a.name in self.opened_by else (ASSIGNMENT, a.name)
			places[(PROJECT, project, *source, overlap)] = _place(
				PROJECT, project, None, *source, overlap=overlap
			)
		return places


def _place(kind, project, location, source_doctype, source_document, overlap=False):
	return {
		"location_type": kind,
		"project": project,
		"location": location,
		"source_doctype": source_doctype,
		"source_document": source_document,
		"overlap": 1 if overlap else 0,
	}
