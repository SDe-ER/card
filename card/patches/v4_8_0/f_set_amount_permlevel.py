# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-162 (Owner decision O-20): confirm that bench migrate has applied the new permlevel of the Card Monthly Card
and Card Monthly Card Adjustment money fields and that the matching DocPerm rows exist.

``bench migrate`` loads the DocType JSON and the field/DocPerm changes are applied as part of the standard sync; this
patch does not alter JSON data. It clears the DocType cache (so the next request sees the new meta) and raises if a
level-1 field or the level-1 DocPerm rows are missing, which marks a rehearsal (second migrate) as having failed. The
patch is safe to run twice: the assertions and the cache clear are idempotent."""

import frappe
from frappe.utils import cint

from card.field_privacy import CARD_MONEY_FIELDS

LEVEL1_READERS = {"System Manager", "Card Manager", "Card User", "Accounts Manager"}


def execute():
	# refresh DocType meta after the JSON sync
	frappe.clear_cache(doctype="Card Monthly Card")
	frappe.clear_cache(doctype="Card Monthly Card Adjustment")

	parent = frappe.get_meta("Card Monthly Card")
	for fieldname in CARD_MONEY_FIELDS:
		field = parent.get_field(fieldname)
		if not field:
			continue  # a later release may rename or remove a field; the patch does not re-introduce it
		if cint(field.permlevel) != 1:
			frappe.throw(
				"FR-162: Card Monthly Card.{0} is still at permlevel {1}; bench migrate did not apply the "
				"DocType JSON change. Re-run bench migrate.".format(fieldname, field.permlevel)
			)

	child = frappe.get_meta("Card Monthly Card Adjustment")
	amount = child.get_field("amount")
	if amount and cint(amount.permlevel) != 1:
		frappe.throw(
			"FR-162: Card Monthly Card Adjustment.amount is at permlevel {0}, expected 1. Re-run bench migrate.".format(
				amount.permlevel
			)
		)

	readers = {p.role for p in parent.permissions if cint(p.permlevel) == 1 and p.read}
	missing = LEVEL1_READERS - readers
	if missing:
		frappe.throw(
			"FR-162: Card Monthly Card is missing the permlevel-1 read rows for {0}. "
			"Re-run bench migrate.".format(", ".join(sorted(missing)))
		)
