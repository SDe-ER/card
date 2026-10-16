# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Report filters link to the CARD party registries (Card Equipment Supplier /
Card Equipment Customer). Registry rows used to appear only on card submit, so
a party with draft cards only could not be selected. Create the missing rows
(idempotent; totals come from submitted cards as always), and realign rows a
past party rename left misnamed. A failure on one party is logged and never
stops the migration."""

import frappe

from card.api import recompute_customer, recompute_supplier
from card.constants import CUSTOMER_BILLING_DIRECTIONS


def execute():
	suppliers = frappe.db.sql_list(
		"""
		select distinct c.supplier from `tabCard Monthly Card` c
		where c.docstatus < 2 and ifnull(c.supplier, '') != '' and ifnull(c.ownership, '') != 'ملك'
		and not exists (select 1 from `tabCard Equipment Supplier` r where r.name = c.supplier)
		"""
	)
	failed = [s for s in suppliers if not _safely(recompute_supplier, s)]
	customers = frappe.db.sql_list(
		"""
		select distinct c.customer from `tabCard Monthly Card` c
		where c.docstatus < 2 and ifnull(c.customer, '') != '' and c.card_direction in %(directions)s
		and not exists (select 1 from `tabCard Equipment Customer` r where r.name = c.customer)
		""",
		{"directions": list(CUSTOMER_BILLING_DIRECTIONS)},
	)
	failed += [c for c in customers if not _safely(recompute_customer, c)]
	if failed:
		# visible in the migrate output; each failure also has its own Error Log
		print(f"CARD registry backfill: {len(failed)} of {len(suppliers) + len(customers)} parties failed")


def _safely(recompute, party):
	try:
		recompute(party)
		return True
	except Exception:
		frappe.log_error(title="CARD registry backfill failed: " + str(party))
		return False
