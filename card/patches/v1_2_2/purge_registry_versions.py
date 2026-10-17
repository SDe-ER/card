# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""#23 (security review MEDIUM-1): before 1.2.2 every registry recompute saved
the Card Equipment Supplier / Customer row with track_changes on, so Version
rows hold the old party-wide (cross-company) counts, totals and months.

Owner decision (2026-10-17): this history is audit evidence and is KEPT as is —
no Version is deleted or rewritten. This patch only counts and reports the
registry Versions that carry a legacy figure. They are not exposed:
- the form shows a document's Versions only while its DocType tracks changes;
  both registries have track_changes off, and
  card.party_registry.guard_registry_track_changes refuses turning it on through
  a Property Setter (Customize Form, REST, imports);
- the Version DocType is readable by System Manager / Administrator only (audit).
Direct database writes bypass any application hook. Idempotent (read-only)."""

import json

import frappe

from card.patches.v1_2_2.clear_registry_aggregates import FIELDS

# the cleared registry fields that held party-wide (cross-company) figures
FIGURE_FIELDS = {
	registry: tuple(f for f in fields if f != "last_refreshed") for registry, fields in FIELDS.items()
}


def carries_aggregates(data, fields):
	try:
		parsed = json.loads(data or "{}")
	except ValueError:
		return any(f'"{field}"' in (data or "") for field in fields)
	changed = parsed.get("changed") if isinstance(parsed, dict) else None
	return any(isinstance(row, list | tuple) and row and row[0] in fields for row in changed or [])


def execute():
	counts = {
		registry: sum(
			1
			for v in frappe.get_all(
				"Version",
				filters={"ref_doctype": registry},
				fields=["data"],
				limit_page_length=0,
			)
			if carries_aggregates(v.data, fields)
		)
		for registry, fields in FIGURE_FIELDS.items()
	}
	if any(counts.values()):
		# visible in the migrate output; nothing is deleted or changed
		print(
			"CARD registry history kept (legacy figures, not exposed): "
			+ ", ".join(f"{registry} {count}" for registry, count in counts.items())
		)
	return counts
