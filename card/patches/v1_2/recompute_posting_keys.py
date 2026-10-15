# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""G0 §5a: the posting key becomes TYPE-FREE (one active posting unit per
party-month-side). Recompute the stored keys of ACTIVE logs. Single-mode
history makes collisions impossible (posting_type was a pure function of
party_type); checked anyway — a collision aborts the migration with the pair
named, and the operator resolves it by cancelling one unit, then re-runs."""

import frappe


def execute():
	frappe.reload_doctype("GL Posting Log")
	from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES, build_posting_key

	logs = frappe.get_all(
		"GL Posting Log",
		filters={"status": ["in", list(ACTIVE_STATES)]},
		fields=["name", "company", "party_type", "party", "month", "year", "sequence"],
	)
	keys = {}
	for row in logs:
		key = build_posting_key(row.company, row.party_type, row.party, row.month, row.year)
		if (row.sequence or 1) > 1:
			key = "{0}|{1}".format(key, row.sequence)
		if key in keys:
			frappe.throw(
				"posting_key collision while re-scoping to type-free keys: "
				f"{keys[key]} vs {row.name} ({key}). Cancel one of the two units, then re-run migrate."
			)
		keys[key] = row.name
	for key, name in keys.items():
		frappe.db.set_value("GL Posting Log", name, "posting_key", key, update_modified=False)
