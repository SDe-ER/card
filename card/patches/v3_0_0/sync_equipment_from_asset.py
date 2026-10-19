# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v3.0.0 (Owner 2026-10-19): an equipment linked to an ERPNext Asset takes its name,
brand and type from the Asset (read-only on the form, kept in sync on every save).

Bring the equipment linked before this rule in line once: name = Asset name, brand =
the Asset item's brand, type = the equipment type mapped to the Asset category. Values
the Asset does not have are left as they are. Written directly (no save), so no
commercial-change reason is asked and documents that copied the old name keep it.
Idempotent: a second run finds nothing to change.
"""

import frappe

from card.card.doctype.card_equipment.card_equipment import asset_equipment_values

ASSET_LINK_FIELD = "الأصل_في_erpnext"


def execute():
	frappe.reload_doc("card", "doctype", "card_equipment_type")
	frappe.reload_doc("card", "doctype", "card_equipment")
	for eq in frappe.get_all(
		"Card Equipment",
		filters={ASSET_LINK_FIELD: ["is", "set"]},
		fields=[
			"name",
			ASSET_LINK_FIELD,
			"equipment_name",
			"brand",
			"equipment_type",
			"equipment_type_from_asset",
		],
	):
		values = asset_equipment_values(eq.get(ASSET_LINK_FIELD))
		if not values:
			continue
		changes = {field: value for field, value in values.items() if value and value != eq.get(field)}
		from_asset = 1 if values.get("equipment_type") else 0
		if from_asset != (eq.equipment_type_from_asset or 0):
			changes["equipment_type_from_asset"] = from_asset
		if changes:
			frappe.db.set_value("Card Equipment", eq.name, changes, update_modified=False)
