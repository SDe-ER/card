# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Report filters link to the CARD party registries (Card Equipment Supplier /
Card Equipment Customer). Registry rows used to appear only on card submit, so
a party with draft cards only could not be selected. Create the missing rows
(idempotent; totals come from submitted cards as always)."""

import frappe

from card.api import recompute_customer, recompute_supplier
from card.constants import CUSTOMER_BILLING_DIRECTIONS


def execute():
	suppliers = frappe.db.sql_list(
		"""
		select distinct c.supplier from `tabCard Monthly Card` c
		where c.docstatus < 2 and ifnull(c.supplier, '') != '' and c.ownership != 'ملك'
		and not exists (select 1 from `tabCard Equipment Supplier` r where r.name = c.supplier)
		"""
	)
	for supplier in suppliers:
		recompute_supplier(supplier)
	customers = frappe.db.sql_list(
		"""
		select distinct c.customer from `tabCard Monthly Card` c
		where c.docstatus < 2 and ifnull(c.customer, '') != '' and c.card_direction in %(directions)s
		and not exists (select 1 from `tabCard Equipment Customer` r where r.name = c.customer)
		""",
		{"directions": list(CUSTOMER_BILLING_DIRECTIONS)},
	)
	for customer in customers:
		recompute_customer(customer)
