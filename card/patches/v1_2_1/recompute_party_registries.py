# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""#24: the registry totals are stored and only refresh on a card event, so
rows written before the fix keep the mixed-side supplier net and the gross
customer amount. Recompute every party that has a registry row or a submitted
card (idempotent; registry counters only, no card is touched). Runs after
backfill_customer_net_amount. A failure on one party is logged and counted."""

import frappe

from card.api import recompute_customer, recompute_supplier
from card.constants import CUSTOMER_BILLING_DIRECTIONS
from card.patches.v1_2_1.ensure_party_registries import _safely


def execute():
	suppliers = set(frappe.get_all("Card Equipment Supplier", pluck="supplier", limit_page_length=0)) | set(
		frappe.get_all(
			"Card Monthly Card",
			filters=[["docstatus", "=", 1], ["ownership", "!=", "ملك"], ["supplier", "is", "set"]],
			pluck="supplier",
			limit_page_length=0,
		)
	)
	customers = set(frappe.get_all("Card Equipment Customer", pluck="customer", limit_page_length=0)) | set(
		frappe.get_all(
			"Card Monthly Card",
			filters=[
				["docstatus", "=", 1],
				["card_direction", "in", list(CUSTOMER_BILLING_DIRECTIONS)],
				["customer", "is", "set"],
			],
			pluck="customer",
			limit_page_length=0,
		)
	)
	failed = [s for s in sorted(filter(None, suppliers)) if not _safely(recompute_supplier, s)]
	failed += [c for c in sorted(filter(None, customers)) if not _safely(recompute_customer, c)]
	if failed:
		print(f"CARD registry recompute: {len(failed)} of {len(suppliers) + len(customers)} parties failed")
