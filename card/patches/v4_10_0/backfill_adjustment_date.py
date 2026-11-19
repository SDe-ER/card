# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Give every addition/deduction saved before v4.10.0 the date of its card's period.

The row date is new. An existing row takes the first day of its card's month (the card's from_date,
or the year and month when from_date is empty). No card total changes: the amounts, the sides and the
totals stay as they are, and no modified time is written. Only empty dates are written, so a second
migrate changes nothing. Owners may correct a legacy date afterwards on the card itself."""

import frappe


def execute():
	# The patch is listed under [post_model_sync], so the schema sync has normally added the column already. As in
	# v1_2.backfill_adjustment_side, the doctype is reloaded first: a site whose earlier migrate failed, or whose sync
	# skipped the doctype, still gets the column before the rows are filled. The patch never ends without writing.
	frappe.reload_doctype("Card Monthly Card Adjustment")
	frappe.db.sql(
		"""
		UPDATE `tabCard Monthly Card Adjustment` adj
		INNER JOIN `tabCard Monthly Card` card ON card.name = adj.parent
		SET adj.adjustment_date = COALESCE(
			card.from_date,
			MAKEDATE(card.year, 1) + INTERVAL (CAST(card.month AS UNSIGNED) - 1) MONTH
		)
		WHERE adj.parenttype = 'Card Monthly Card'
		  AND adj.adjustment_date IS NULL
		"""
	)
