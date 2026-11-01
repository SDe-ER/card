# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""v4.3.0 (FR-098, Owner D1 2026-11-01): fill the Asset-owned master fields of the
equipment linked before this release.

Only EMPTY CARD values are filled; a non-empty CARD value that differs from the Asset is
NOT overwritten here (an unattended migrate must not replace data) — it is listed in the
"CARD asset master backfill" Error Log report for the owner, and the next save of that
equipment applies the Asset value with its history. Chassis numbers another equipment of
the company already uses are not copied. Written directly (no save) like v3.0.0, with a
Version row per changed equipment. Idempotent: a second run changes nothing.
"""

import frappe

from card.asset_master import MASTER_FIELDS, OWNED_LIST_FIELD, _known, asset_master_values, owned_list
from card.dimension import ASSET_LINK_FIELD

REPORT_TITLE = "CARD asset master backfill"


def execute():
	frappe.reload_doc("card", "doctype", "card_equipment")
	from card.card.doctype.card_equipment.card_equipment import identity_key

	report = {"updated": [], "conflicts": [], "skipped_duplicate_chassis": []}
	rows = frappe.get_all(
		"Card Equipment",
		filters={ASSET_LINK_FIELD: ["is", "set"]},
		fields=[
			"name",
			"company",
			ASSET_LINK_FIELD,
			OWNED_LIST_FIELD,
			"equipment_type_from_asset",
			"serial_no_key",
			*MASTER_FIELDS,
		],
	)
	for eq in rows:
		values = asset_master_values(eq.get(ASSET_LINK_FIELD))
		if not values:
			continue
		updates, changed = {}, []
		for field, value in values.items():
			current = eq.get(field)
			if current == value:
				continue
			if _known(field, current):
				report["conflicts"].append(
					{"equipment": eq.name, "field": field, "card": current, "asset": value}
				)
				continue
			if field == "serial_no":
				key = identity_key(value)
				other = frappe.db.get_value(
					"Card Equipment",
					{"company": eq.company, "serial_no_key": key, "name": ["!=", eq.name]},
					"name",
				)
				if other:
					report["skipped_duplicate_chassis"].append(
						{"equipment": eq.name, "chassis": value, "used_by": other}
					)
					continue
				updates["serial_no_key"] = key
			updates[field] = value
			changed.append([field, current, value])
		# read-only in CARD only where CARD now holds the Asset value
		final = {f: updates.get(f, eq.get(f)) for f in MASTER_FIELDS}
		owned = owned_list({f: v for f, v in values.items() if final.get(f) == v})
		if (eq.get(OWNED_LIST_FIELD) or "") != owned:
			updates[OWNED_LIST_FIELD] = owned
		if "equipment_type" in values and final.get("equipment_type") == values["equipment_type"]:
			updates["equipment_type_from_asset"] = 1
		updates = {f: v for f, v in updates.items() if eq.get(f) != v}
		if not updates:
			continue
		frappe.db.set_value("Card Equipment", eq.name, updates, update_modified=False)
		if changed:
			frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": "Card Equipment",
					"docname": eq.name,
					"data": frappe.as_json({"changed": changed}),
				}
			).insert(ignore_permissions=True)  # history row of a patch
			report["updated"].append({"equipment": eq.name, "changed": changed})
	if report["updated"] or report["conflicts"] or report["skipped_duplicate_chassis"]:
		frappe.log_error(message=frappe.as_json(report), title=REPORT_TITLE)
	return report
