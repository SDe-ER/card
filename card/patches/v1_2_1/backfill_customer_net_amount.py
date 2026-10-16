# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""customer_net_amount (customer amount + customer-side additions/deductions)
arrived with S3, so customer-billing cards saved before it carry 0 while their
customer_amount is set. The customer registry, summary and statement now read
that net (#24); fill it from the stored amount and the card's own rows, the
same formula the controller uses. Idempotent: a card whose stored net already
equals the formula is left alone; no other column is touched."""

import frappe
from frappe.utils import flt

from card.constants import CUSTOMER_BILLING_DIRECTIONS


def execute():
	cards = frappe.db.sql(
		"""
		select c.name, c.customer_amount,
			ifnull(sum(case when a.side = 'Customer' and a.adjustment_type = 'إضافة' then a.amount
				when a.side = 'Customer' and a.adjustment_type = 'خصم' then -a.amount else 0 end), 0) signed
		from `tabCard Monthly Card` c
		left join `tabCard Monthly Card Adjustment` a
			on a.parent = c.name and a.parenttype = 'Card Monthly Card'
		where c.docstatus < 2 and c.card_direction in %(directions)s
			and ifnull(c.customer_net_amount, 0) = 0 and ifnull(c.customer_amount, 0) != 0
		group by c.name, c.customer_amount
		""",
		{"directions": list(CUSTOMER_BILLING_DIRECTIONS)},
		as_dict=True,
	)
	for c in cards:
		net = flt(flt(c.customer_amount) + flt(c.signed), 2)
		if net:
			frappe.db.set_value(
				"Card Monthly Card", c.name, "customer_net_amount", net, update_modified=False
			)
