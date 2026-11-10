# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment location history (#53, #127; FR-130). Read-only.

Where an equipment was on each day of a period, as date-aware segments. The rules are the
ones `card.transfer` already applies; nothing here decides a location of its own:

- on a project while a Card Equipment Assignment is in force (`card.transfer._in_force`,
  assignments read through `card.transfer.month_assignments`, which also covers a unit
  through its components). The assignment dates are the ones the transport wrote, so the
  move-day rule recorded on each transport (FR-117) is already in them;
- otherwise where the last submitted Equipment Transport on or before that day sent it
  (workshop, storage, supplier), as `card.transfer.current_location` does for today;
- otherwise in the initial place of the equipment's company (FR-116,
  Card Company Settings `initial_location`; empty when it is not set).

A segment's source is the transport that opened the assignment (its row
`created_assignment`), else the assignment itself; the transport for a workshop, storage or
supplier place; none for the initial place."""

from itertools import pairwise

import frappe
from frappe.utils import add_days, getdate

from card.settings import company_setting
from card.transfer import _in_force, month_assignments

ASSIGNMENT = "Card Equipment Assignment"
TRANSPORT = "Equipment Transport"
PROJECT = "Project"
INITIAL = "Initial"


def submitted_moves(equipment_names, company, end):
	"""Submitted transports of the company moving these machines, dated on or before `end`,
	per machine in move order (date, then creation, as current_location orders them)."""
	moves = {name: [] for name in equipment_names}
	if not equipment_names:
		return moves
	item = frappe.qb.DocType("Equipment Transport Item")
	transport = frappe.qb.DocType(TRANSPORT)
	rows = (
		frappe.qb.from_(item)
		.join(transport)
		.on((transport.name == item.parent) & (item.parenttype == TRANSPORT))
		.select(
			item.card_equipment,
			item.created_assignment,
			transport.name,
			transport.date,
			transport.destination_type,
			transport.destination_location,
			transport.project,
		)
		.where(item.card_equipment.isin(list(equipment_names)))
		.where(transport.docstatus == 1)
		.where(transport.company == company)
		.where(transport.date <= end)
		.orderby(transport.date)
		.orderby(transport.creation)
		.run(as_dict=True)
	)
	for row in rows:
		moves[row.card_equipment].append(row)
	return moves


def equipment_segments(equipment, company, start, end, moves=None, initial_place=None):
	"""Segments of `equipment` inside [start, end], oldest first. Each segment is a dict:
	equipment, from_date, to_date, location_type (Project / Workshop / Storage / Supplier /
	Initial), project, location, source_doctype, source_document."""
	start, end = getdate(start), getdate(end)
	if moves is None:
		moves = submitted_moves([equipment], company, end)[equipment]
	assignments = month_assignments(equipment, start, end)
	opened_by = {m.created_assignment: m.name for m in moves if m.created_assignment}

	cuts = {start, add_days(end, 1)}
	for a in assignments:
		cuts.add(getdate(a.from_date))
		if a.to_date:
			cuts.add(getdate(add_days(a.to_date, 1)))
	for m in moves:
		cuts.add(getdate(m.date))
	cuts = sorted(getdate(c) for c in cuts if start <= getdate(c) <= add_days(end, 1))

	segments, open_runs = [], {}
	for first, nxt in pairwise(cuts):
		last = add_days(nxt, -1)
		here = _places_on(first, assignments, moves, opened_by, initial_place)
		for key in list(open_runs):
			if key not in here:
				segments.append(open_runs.pop(key))
		for key, place in here.items():
			if key in open_runs:
				open_runs[key]["to_date"] = last
			else:
				open_runs[key] = dict(place, equipment=equipment, from_date=first, to_date=last)
	segments.extend(open_runs.values())
	return sorted(segments, key=lambda s: (s["from_date"], s["location_type"]))


def _places_on(day, assignments, moves, opened_by, initial_place):
	"""Where the machine is on `day`, keyed so equal places on consecutive days merge."""
	in_force = _in_force(assignments, day)
	if in_force:
		places = {}
		for a in in_force:
			source = (TRANSPORT, opened_by[a.name]) if a.name in opened_by else (ASSIGNMENT, a.name)
			places[(PROJECT, a.project, *source)] = {
				"location_type": PROJECT,
				"project": a.project,
				"location": None,
				"source_doctype": source[0],
				"source_document": source[1],
			}
		return places
	last = None
	for m in moves:
		if getdate(m.date) <= day:
			last = m
	if last and last.destination_type and last.destination_type != PROJECT:
		return {
			(last.destination_type, last.destination_location, TRANSPORT, last.name): {
				"location_type": last.destination_type,
				"project": None,
				"location": last.destination_location,
				"source_doctype": TRANSPORT,
				"source_document": last.name,
			}
		}
	return {
		(INITIAL, initial_place, None, None): {
			"location_type": INITIAL,
			"project": None,
			"location": initial_place,
			"source_doctype": None,
			"source_document": None,
		}
	}


def company_segments(company, start, end, equipment_names):
	"""Segments of every machine in `equipment_names` (all of `company`) inside the period."""
	moves = submitted_moves(equipment_names, company, getdate(end))
	initial_place = company_setting(company, "initial_location")
	rows = []
	for name in equipment_names:
		rows.extend(equipment_segments(name, company, start, end, moves[name], initial_place))
	return rows
