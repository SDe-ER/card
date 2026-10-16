# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""#23 (security review MEDIUM-1): before 1.2.2 every registry recompute saved
the Card Equipment Supplier / Customer row with track_changes on, so Version
rows hold the old party-wide (cross-company) counts, totals and months — and a
form load returns recent Versions to any user who may open the party.

Owner decision (PR #39): delete ONLY the registry Versions that carry one of
the legacy aggregate fields (a Version mixing identity and aggregate changes is
deleted whole: it cannot be trimmed without rewriting history). Identity-only
registry history and every other doctype's history are kept. A Version whose
data cannot be parsed is deleted only if it names an aggregate field. Idempotent."""

import json

import frappe

from card.patches.v1_2_2.clear_registry_aggregates import FIELDS


def carries_aggregates(data, fields):
	try:
		parsed = json.loads(data or "{}")
	except ValueError:
		return any(f'"{field}"' in (data or "") for field in fields)
	changed = parsed.get("changed") if isinstance(parsed, dict) else None
	return any(isinstance(row, list | tuple) and row and row[0] in fields for row in changed or [])


def execute():
	for registry, fields in FIELDS.items():
		doomed = [
			v.name
			for v in frappe.get_all(
				"Version",
				filters={"ref_doctype": registry},
				fields=["name", "data"],
				limit_page_length=0,
			)
			if carries_aggregates(v.data, fields)
		]
		for start in range(0, len(doomed), 500):
			frappe.db.delete("Version", {"name": ["in", doomed[start : start + 500]]})
