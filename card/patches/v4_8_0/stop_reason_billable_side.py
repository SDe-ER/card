# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-134 (#45, C-07): every existing Card Stop Reason gets billable side "Both", which is how a
billable reason billed before v4.8.0 (both the supplier and the customer side).

Only rows without a side are written; the billable flag, the approval reason and every card day
row are left unchanged. Idempotent: a second migrate finds no row without a side."""

import frappe


def execute():
	if not frappe.db.table_exists("Card Stop Reason"):
		return
	if not frappe.db.has_column("Card Stop Reason", "billable_side"):
		return
	names = frappe.get_all(
		"Card Stop Reason",
		or_filters=[["billable_side", "is", "not set"], ["billable_side", "=", ""]],
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Card Stop Reason", name, "billable_side", "Both", update_modified=False)
