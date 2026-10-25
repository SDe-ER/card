# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""D1: fill the comparable chassis / plate number keys of existing equipment. Writes only
the two key columns (no modified, no Version). Equipment that already share a number in
one company are listed and kept as they are: a later save is refused only when that
number is changed or a new equipment takes it. Idempotent."""

import frappe

from card.card.doctype.card_equipment.card_equipment import IDENTITY_FIELDS, identity_key


def execute():
	fields = ["name", "company"] + [field for pair in IDENTITY_FIELDS for field in pair]
	seen = {}
	for row in frappe.get_all("Card Equipment", fields=fields, order_by="creation asc"):
		values = {}
		for field, key_field in IDENTITY_FIELDS:
			key = identity_key(row.get(field))
			if row.get(key_field) != key:
				values[key_field] = key
			if key:
				seen.setdefault((row.company, field, key), []).append(row.name)
		if values:
			frappe.db.set_value("Card Equipment", row.name, values, update_modified=False)
	for (company, field, key), names in seen.items():
		if len(names) > 1:
			print(f"Card Equipment sharing {field} {key} in {company}: {', '.join(names)}")
