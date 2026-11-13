# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-164 (#31, #47; closure plan WP-I1, owner decision O-11 D1): give every Card Company
Settings row saved before v4.8.0 an explicit ``enable_diesel_tanks = 0``.

The column is materialised by ``bench migrate`` as 0 (default on the JSON), so this patch
is defence-in-depth: it writes the stored value explicitly only on rows whose value is
NULL / empty, so a later form save of such a row does not flip the stored NULL to an
interpreted-as-0 and show a "Version" diff on the first access. No modified time is
touched. Idempotent: a second migrate finds no row with an empty value.
"""

import frappe

from card.card.doctype.diesel_dispense.diesel_dispense import ENABLE_FLAG


def execute():
	if not frappe.db.table_exists("Card Company Settings") or not frappe.db.has_column(
		"Card Company Settings", ENABLE_FLAG
	):
		return
	names = frappe.get_all(
		"Card Company Settings",
		or_filters=[[ENABLE_FLAG, "is", "not set"], [ENABLE_FLAG, "=", ""]],
		pluck="name",
	)
	for name in names:
		frappe.db.set_value("Card Company Settings", name, ENABLE_FLAG, 0, update_modified=False)
