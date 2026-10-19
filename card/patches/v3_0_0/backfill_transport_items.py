# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v3.0.0: an Equipment Transport moves the equipment listed in its `items` table.

Every transport saved before v3.0.0 holds at most one equipment, on the header. Give it
the matching single row (whole transport cost as its share, and the assignments the
transfer created/closed) so cancel, posting and the equipment links read one source.
Drafts, submitted and cancelled documents are all covered; nothing is re-validated or
re-submitted, and amounts and posted invoices are untouched. Idempotent: a transport
that already has rows is skipped.
"""

import frappe
from frappe.utils import flt, now


def execute():
	frappe.reload_doc("card", "doctype", "equipment_transport_item")
	frappe.reload_doc("card", "doctype", "equipment_transport")
	with_rows = set(
		frappe.get_all(
			"Equipment Transport Item", filters={"parenttype": "Equipment Transport"}, pluck="parent"
		)
	)
	for t in frappe.get_all(
		"Equipment Transport",
		filters={"equipment": ["is", "set"]},
		fields=["name", "equipment", "amount", "previous_assignment", "created_assignment", "docstatus"],
	):
		if t.name in with_rows:
			continue
		row = frappe.new_doc("Equipment Transport Item")
		row.update(
			{
				"parent": t.name,
				"parenttype": "Equipment Transport",
				"parentfield": "items",
				"idx": 1,
				"docstatus": t.docstatus,
				"card_equipment": t.equipment,
				"equipment_name": frappe.db.get_value("Card Equipment", t.equipment, "equipment_name"),
				"amount": flt(t.amount, 2),
				"previous_assignment": t.previous_assignment,
				"created_assignment": t.created_assignment,
			}
		)
		row.name = frappe.generate_hash(length=10)
		row.owner = row.modified_by = "Administrator"
		row.creation = row.modified = now()
		row.db_insert()
