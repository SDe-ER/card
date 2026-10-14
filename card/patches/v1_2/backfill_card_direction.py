# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Backfill card_direction on existing Card Monthly Cards (phase E).

Pre-E cards never billed a customer, so the direction is derived from the
stored ownership only: owned -> internal operation, rented -> rented-in.
Idempotent (only touches rows with an empty direction); never recomputes
any amount."""

import frappe


def execute():
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
