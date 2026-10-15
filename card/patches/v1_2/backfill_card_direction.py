# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Backfill card_direction on existing Card Monthly Cards (phase E).

Pre-E cards never billed a customer, so the direction is derived from the
stored ownership only: owned -> internal operation, rented -> rented-in.
Idempotent (only touches rows with an empty direction); never recomputes
any amount."""

import frappe


def execute():
	# frappe skips an app's schema sync when its version is unchanged, and a
	# failed earlier migrate can leave patches pending on an old schema —
	# reload the doctypes this patch touches before reading their columns.
	frappe.reload_doctype("Card Monthly Card")
	frappe.reload_doctype("Card Equipment")
	if not frappe.db.has_column("Card Monthly Card", "card_direction"):
		return
	frappe.db.sql(
		"""update `tabCard Monthly Card`
		set card_direction = %s
		where coalesce(card_direction, '') = '' and ownership = %s""",
		("تشغيل داخلي", "ملك"),
	)
	frappe.db.sql(
		"""update `tabCard Monthly Card`
		set card_direction = %s
		where coalesce(card_direction, '') = '' and coalesce(ownership, '') != %s""",
		("مستأجَرة من مورد", "ملك"),
	)
