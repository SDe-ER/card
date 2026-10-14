# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""F.7(b): DRAFT cards mirror their equipment (direction/customer/rates).
Runs AFTER backfill_rental_direction. SUBMITTED cards are untouched and no
amount is recomputed (drafts recalculate on their next save). Pure SQL —
no save(), so period lock / validation / hooks never fire during migrate.
Idempotent."""

import frappe

from card.constants import DIR_RENTED_OUT, DIR_SUBRENTAL


def execute():
	if not (
		frappe.db.has_column("Card Monthly Card", "card_direction")
		and frappe.db.has_column("Card Equipment", "rental_direction")
	):
		return
	billing = (DIR_RENTED_OUT, DIR_SUBRENTAL)
	frappe.db.sql(
		"""update `tabCard Monthly Card` c
		join `tabCard Equipment` e on e.name = c.equipment
		set c.card_direction = e.rental_direction,
			c.customer = case when e.rental_direction in (%s, %s) then e.default_customer else null end,
			c.customer_rate_type = case when e.rental_direction in (%s, %s) then e.customer_rate_type else null end,
			c.customer_rate = case when e.rental_direction in (%s, %s) then coalesce(e.customer_rate, 0) else 0 end
		where c.docstatus = 0""",
		billing * 3,
	)
