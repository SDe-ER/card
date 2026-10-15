# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""F.7(a): backfill Card Equipment.rental_direction (the new single source of
truth). Evidence first — equipment that historically billed a customer (E-era
cards or its own customer config) keeps the customer side instead of being
flattened by the ownership default. Pure SQL / db.set_value: no save(), so no
period-lock, validation or hook side effects during migrate. Idempotent."""

import frappe
from frappe.utils import flt

from card.constants import (
	DIR_INTERNAL,
	DIR_RENTED_IN,
	DIR_RENTED_OUT,
	DIR_SUBRENTAL,
	OWNED,
)


def execute():
	# frappe skips an app's schema sync when its version is unchanged, and a
	# failed earlier migrate can leave patches pending on an old schema —
	# reload the doctypes this patch touches before reading their columns.
	frappe.reload_doctype("Card Equipment")
	frappe.reload_doctype("Card Monthly Card")
	if not frappe.db.has_column("Card Equipment", "rental_direction"):
		return

	# 1) lift E-era per-card customer billing up to the equipment (submitted first,
	#    then drafts; latest wins) and give it the matching billing direction.
	rows = frappe.db.sql(
		"""select c.equipment, c.customer, c.customer_rate_type, c.customer_rate
		from `tabCard Monthly Card` c
		join `tabCard Equipment` e on e.name = c.equipment
		where coalesce(e.rental_direction, '') = ''
		and c.card_direction in (%s, %s)
		and coalesce(c.customer, '') != ''
		and c.docstatus < 2
		order by c.docstatus desc, c.creation desc""",
		(DIR_RENTED_OUT, DIR_SUBRENTAL),
		as_dict=True,
	)
	lifted = set()
	for r in rows:
		if r.equipment in lifted:
			continue
		lifted.add(r.equipment)
		e = frappe.db.get_value(
			"Card Equipment",
			r.equipment,
			["ownership", "default_customer", "customer_rate_type", "customer_rate"],
			as_dict=True,
		)
		updates = {"rental_direction": DIR_RENTED_OUT if e.ownership == OWNED else DIR_SUBRENTAL}
		if not e.default_customer:
			updates["default_customer"] = r.customer
		if not e.customer_rate_type and r.customer_rate_type:
			updates["customer_rate_type"] = r.customer_rate_type
		if not flt(e.customer_rate) and flt(r.customer_rate):
			updates["customer_rate"] = r.customer_rate
		frappe.db.set_value("Card Equipment", r.equipment, updates, update_modified=False)

	# 2) equipment carrying its own customer config also keeps the customer side
	frappe.db.sql(
		"""update `tabCard Equipment`
		set rental_direction = case when ownership = %s then %s else %s end
		where coalesce(rental_direction, '') = ''
		and coalesce(default_customer, '') != '' and coalesce(customer_rate, 0) > 0""",
		(OWNED, DIR_RENTED_OUT, DIR_SUBRENTAL),
	)

	# 3) everything else: the ownership default
	frappe.db.sql(
		"""update `tabCard Equipment` set rental_direction = %s
		where coalesce(rental_direction, '') = '' and ownership = %s""",
		(DIR_INTERNAL, OWNED),
	)
	frappe.db.sql(
		"""update `tabCard Equipment` set rental_direction = %s
		where coalesce(rental_direction, '') = ''""",
		(DIR_RENTED_IN,),
	)
