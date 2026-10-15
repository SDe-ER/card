# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3/F.4: every pre-existing card adjustment row was (implicitly) a
supplier-side row — the v1.1 net formula folded them all into net_amount.
Make that explicit so the sided split keeps every stored number unchanged.
SQL-only and idempotent; submitted documents' stored values are untouched
(side is a new column, amounts are not recomputed)."""

import frappe


def execute():
	# frappe skips an app's schema sync when its version is unchanged, and a
	# failed earlier migrate can leave patches pending on an old schema —
	# reload the doctypes this patch touches before reading their columns.
	frappe.reload_doctype("Card Monthly Card Adjustment")
	frappe.db.sql(
		"""UPDATE `tabCard Monthly Card Adjustment`
		SET side = 'Supplier'
		WHERE COALESCE(side, '') = ''"""
	)
