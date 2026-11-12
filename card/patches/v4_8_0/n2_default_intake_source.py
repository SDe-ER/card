# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-158 (#52, #44; WP-N2): give every Card Monthly Card Day saved before v4.8.0 the default intake
source "manual".

"manual" is the behaviour every day row had before FR-158 (a hand entry on the form). The controller and
the `apply_card_day_intake` validator both treat an empty value as "manual", so this patch only makes the
stored value explicit for the Desk form and for reports that read the column. No card is touched,
repriced, submitted or cancelled; `modified` is not updated. Idempotent: a second migrate finds no empty
row and writes nothing.
"""

import frappe

from card.intake import DAY_DEFAULT_SOURCE

DOCTYPE = "Card Monthly Card Day"
FIELD = "intake_source"


def execute():
	if not frappe.db.table_exists(DOCTYPE) or not frappe.db.has_column(DOCTYPE, FIELD):
		return
	# `is not set` matches both NULL and the empty string: both are "no explicit value"
	names = frappe.get_all(
		DOCTYPE,
		filters=[[FIELD, "is", "not set"]],
		pluck="name",
		limit_page_length=0,
	)
	for name in names:
		frappe.db.set_value(DOCTYPE, name, FIELD, DAY_DEFAULT_SOURCE, update_modified=False)
