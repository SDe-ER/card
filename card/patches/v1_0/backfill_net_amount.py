# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Backfill net_amount on submitted Card Monthly Card rows that predate CARD v1.0.

Cards submitted under the legacy Server Script left ``net_amount`` at 0/NULL
while ``amount`` is non-zero (e.g. EOMC-2026-09-0240: amount 5,280, net 0). The
v1.0 controller computes ``net_amount = amount + total_additions -
total_deductions`` on validate, so only historical submitted rows need the fix.

Field-only ``db_set`` (no re-submit, no GL impact). Idempotent: a row is touched
only when its stored net_amount is 0/NULL AND the recomputed value is non-zero,
so re-running is a no-op and genuinely-zero cards (e.g. owned equipment) are
never written.
"""

import frappe
from frappe.utils import flt

CMC = "Card Monthly Card"


def execute():
	if not frappe.db.has_column(CMC, "net_amount"):
		return
	rows = frappe.get_all(
		CMC,
		filters={"docstatus": 1},
		fields=["name", "amount", "total_additions", "total_deductions", "net_amount"],
	)
	fixed = 0
	for r in rows:
		# only rows whose net is currently 0/NULL (flt(None) == 0)
		if flt(r.net_amount) != 0:
			continue
		computed = flt(flt(r.amount) + flt(r.total_additions) - flt(r.total_deductions), 2)
		if computed == 0:
			continue  # genuinely zero (e.g. owned equipment) — nothing to backfill
		frappe.db.set_value(CMC, r.name, "net_amount", computed, update_modified=False)
		fixed += 1
	if fixed:
		frappe.logger("card").info("card: backfilled net_amount on %d submitted card(s)" % fixed)
