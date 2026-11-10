# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-125: give each company that has a diesel unit price and no Diesel price schedule one schedule
row with that price, valid from the company's earliest diesel fill (today when it has none).

Every fill keeps the price it has today: the row holds the same price as diesel_unit_price, which is
left unchanged and still prices a fill dated before the row. Submitted fills are never touched.
Idempotent: a company that already has a schedule row is skipped, so a second migrate adds nothing.
The row is inserted on its own (no save of Card Settings), so unrelated Settings rows are not
re-validated during migrate."""

import frappe
from frappe.utils import flt, getdate, nowdate

PARENT = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "diesel_price_schedule"}


def execute():
	if not frappe.db.table_exists("Card Diesel Price"):
		return
	companies = frappe.get_all(
		"Card Company Settings",
		filters={
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": "company_settings",
			"diesel_unit_price": [">", 0],
		},
		fields=["company", "diesel_unit_price"],
		order_by="idx asc",
	)
	idx = frappe.db.sql(
		"select coalesce(max(idx), 0) from `tabCard Diesel Price` where parent=%s and parentfield=%s",
		(PARENT["parent"], PARENT["parentfield"]),
	)[0][0]
	added = False
	for row in companies:
		if not row.company or frappe.db.exists("Card Diesel Price", {**PARENT, "company": row.company}):
			continue
		first = frappe.db.sql(
			"select min(date) from `tabProject Diesel Fill` where company=%s and docstatus < 2",
			row.company,
		)[0][0]
		idx += 1
		frappe.get_doc(
			{
				"doctype": "Card Diesel Price",
				**PARENT,
				"idx": idx,
				"company": row.company,
				"valid_from": getdate(first or nowdate()),
				"unit_price": flt(row.diesel_unit_price),
				"currency": frappe.get_cached_value("Company", row.company, "default_currency"),
			}
		).db_insert()
		added = True
	if added:
		frappe.clear_document_cache("Card Settings", "Card Settings")
