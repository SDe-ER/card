# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Backfill the snapshot fields (daily_hours_used / hourly_rate_used /
diesel_policy_used) on already-submitted Card Monthly Cards from the values they
were computed with. Read-only w.r.t. amounts: uses db_set and NEVER touches
net_amount or any amount field. Idempotent (skips cards already backfilled)."""

import frappe
from frappe.utils import flt


def execute():
	cards = frappe.get_all(
		"Card Monthly Card",
		filters={"docstatus": 1},
		fields=["name", "equipment", "rate", "rate_type", "daily_hours_used", "hourly_rate_used"],
	)
	for c in cards:
		# already backfilled (either field populated) -> skip
		if flt(c.daily_hours_used) or flt(c.hourly_rate_used):
			continue
		eq = (
			frappe.db.get_value("Card Equipment", c.equipment, ["daily_hours", "الوقود_على"], as_dict=True)
			or frappe._dict()
		)
		daily_hours = flt(eq.daily_hours)
		if c.rate_type == "باليوم" and daily_hours > 0:
			hourly = flt(c.rate) / daily_hours
		else:
			hourly = flt(c.rate)
		frappe.db.set_value(
			"Card Monthly Card",
			c.name,
			{
				"daily_hours_used": daily_hours,
				"hourly_rate_used": hourly,
				"diesel_policy_used": eq.get("الوقود_على"),
			},
			update_modified=False,
		)
