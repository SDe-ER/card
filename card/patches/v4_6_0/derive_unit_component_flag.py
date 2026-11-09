# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""WP-05 (#42): is_unit_component is now derived from the units' component tables.

Choice (documented in CHANGELOG): only an unambiguous value is written.
- An equipment that a unit's component table lists (any row, open or closed) takes the
  value the table gives: ticked while a row has no To date, cleared once every row has one.
  Only the flag column is written (no modified date, no Version); a comment on the
  equipment records the change.
- A ticked flag on equipment that no unit lists is ambiguous (the unit's table may never
  have been filled in): it is kept, so the equipment still takes no card of its own, and
  listed in the Error Log with the owned-only findings (#42, WP-04) for the office to resolve
  (add it to its unit, or Card Equipment > resync_unit_component_flag).
- Rented units and rented components are only listed; nothing is changed.
Idempotent: a second run finds nothing to write and lists the same findings."""

import frappe
from frappe.utils import cint

from card.card.doctype.card_equipment.card_equipment import (
	derived_unit_component,
	sync_unit_component_flags,
	unit_integrity_issues,
)


def execute():
	listed = set(
		frappe.get_all(
			"Card Equipment Component",
			filters={"parenttype": "Card Equipment", "parentfield": "components"},
			pluck="component",
		)
	)
	stale = [
		row.name
		for row in frappe.get_all(
			"Card Equipment", filters={"name": ["in", list(listed) or [""]]}, fields=["name", "is_unit_component"]
		)
		if cint(row.is_unit_component) != derived_unit_component(row.name)
	]
	sync_unit_component_flags(stale)
	issues = unit_integrity_issues(
		frappe.get_all(
			"Card Equipment",
			fields=["name", "company", "ownership", "is_unit", "is_unit_component"],
			page_length=0,
		)
	)
	if issues:
		frappe.log_error(
			title="CARD unit records to review (#42)",
			message="\n".join(
				f"{i.company}: {i.equipment}: {i.issue}" + (f" (unit {i.unit})" if i.unit else "")
				for i in issues
			),
		)
