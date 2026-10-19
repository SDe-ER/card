# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Owner 2026-10-19: Card Settings is the only source of the diesel price per litre, so a
test that wants a fill at a given price puts that price in Settings first."""

import frappe


def set_diesel_price(company, price):
	"""Write only the company's price row (rolled back with the test), so unrelated Card
	Settings rules on the site are not re-validated."""
	name = frappe.db.get_value(
		"Card Company Settings",
		{"parent": "Card Settings", "parenttype": "Card Settings", "company": company},
		"name",
	)
	if name:
		frappe.db.set_value("Card Company Settings", name, "diesel_unit_price", price)
		return
	frappe.get_doc(
		{
			"doctype": "Card Company Settings",
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": "company_settings",
			"company": company,
			"diesel_unit_price": price,
		}
	).db_insert()


def use_fill_price(fill):
	"""Put the price typed on a test fill into Settings; returns the fill."""
	set_diesel_price(fill.company, fill.unit_price)
	return fill
