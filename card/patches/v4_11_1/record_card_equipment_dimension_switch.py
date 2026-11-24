# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Owner decision 2026-11-24: Card Settings "Enable Card Equipment accounting dimension" (default off) decides whether
a site may have the dimension. A site that already has it enabled (created by v4.11.0 or by the manual command) keeps
it: this patch only records that fact in the switch. A site without the dimension is left with the switch off.

Writes: one Card Settings value. Never creates, enables or changes the dimension or its fields."""

import frappe

from card.dimension import SWITCH_FIELD, _is_disabled, has_dimension


def execute():
	if has_dimension() and not _is_disabled():
		frappe.db.set_single_value("Card Settings", SWITCH_FIELD, 1)
