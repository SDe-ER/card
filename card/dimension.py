# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Accounting Dimension "Card Equipment" (O3).

The dimension is the official ERPNext mechanism that lets every GL-bearing
document (and so the GL/TB/P&L/BS reports) carry the equipment. Creating it
adds a `card_equipment` custom field to ~53 ERPNext doctypes (an ALTER TABLE
on each), so it is an EXPLICIT, MANUAL step:

        bench --site <site> execute card.dimension.ensure_card_equipment_dimension

It is never run by migrate/patches, and on production only after the owner's
deploy approval. Everything else in this module is a no-op until the
dimension exists, so a site without it (v1.1 behaviour) keeps working.
"""

import frappe

DIMENSION_DOCTYPE = "Card Equipment"
DIMENSION_FIELD = "card_equipment"
ASSET_LINK_FIELD = "الأصل_في_erpnext"


def has_dimension():
	"""Does this site have the Card Equipment accounting dimension?"""
	return bool(frappe.db.exists("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE}))


def gl_has_dimension_field():
	return frappe.get_meta("GL Entry").has_field(DIMENSION_FIELD)


def ensure_card_equipment_dimension():
	"""Create the dimension (idempotent, non-mandatory for BS/PL).

	MANUAL OPERATION ONLY (see module docstring): it commits, so it must never
	be called from controllers, patches or tests."""
	if has_dimension():
		return "exists"
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		make_dimension_in_accounting_doctypes,
	)

	doc = frappe.new_doc("Accounting Dimension")
	doc.document_type = DIMENSION_DOCTYPE
	for company in frappe.get_all("Company", pluck="name"):
		doc.append(
			"dimension_defaults",
			{"company": company, "mandatory_for_bs": 0, "mandatory_for_pl": 0},
		)
	doc.insert(ignore_permissions=True)
	# ERPNext normally creates the custom fields in a background job; create them
	# synchronously so this manual run is complete when it returns (the queued
	# job finds them existing and is a no-op).
	make_dimension_in_accounting_doctypes(doc=doc)
	frappe.db.commit()
	return doc.name


def sync_asset_dimension(equipment):
	"""Keep the linked Asset's card_equipment dimension pointing at the equipment
	(owner amendment 2: automatic Asset <-> equipment dimension sync). The Asset's
	dimension value flows into its depreciation entries' GL. No-op while the
	dimension does not exist."""
	if not frappe.get_meta("Asset").has_field(DIMENSION_FIELD):
		return
	asset = equipment.get(ASSET_LINK_FIELD)
	before = equipment.get_doc_before_save()
	prev = before.get(ASSET_LINK_FIELD) if before else None
	if (
		prev
		and prev != asset
		and frappe.db.exists("Asset", prev)
		and frappe.db.get_value("Asset", prev, DIMENSION_FIELD) == equipment.name
	):
		frappe.db.set_value("Asset", prev, DIMENSION_FIELD, None, update_modified=False)
	if asset and frappe.db.exists("Asset", asset):
		if frappe.db.get_value("Asset", asset, DIMENSION_FIELD) != equipment.name:
			frappe.db.set_value("Asset", asset, DIMENSION_FIELD, equipment.name, update_modified=False)
