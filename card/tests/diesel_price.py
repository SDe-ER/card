# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Owner 2026-10-19: Card Settings is the only source of the diesel price per litre, so a
test that wants a fill at a given price puts that price in Settings first."""

import frappe
from frappe.utils import flt


def approve_fill(fill):
	"""Owner 2026-10-26 (Phase 1): a fill is submitted only after the operations review, which needs a
	closing meter photo and reading. Gives a saved draft that evidence and the approval, as a reviewer
	would; returns the fill."""
	user = frappe.session.user
	frappe.set_user("Administrator")
	try:
		if not fill.closing_photo:
			photo = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": f"meter-{frappe.generate_hash(length=10)}.txt",
					"is_private": 1,
					"content": frappe.generate_hash(length=32),
					"attached_to_doctype": fill.doctype,
					"attached_to_name": fill.name,
					"attached_to_field": "closing_photo",
				}
			).insert(ignore_permissions=True)
			fill.closing_photo = photo.file_url
		if not flt(fill.closing_reading):
			fill.closing_reading = flt(fill.opening_reading) + flt(fill.litres)
		fill.review_status = "Operations Approved"
		fill.save(ignore_permissions=True)
	finally:
		frappe.set_user(user)
	return fill


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
