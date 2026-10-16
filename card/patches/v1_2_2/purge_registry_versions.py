# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""#23 (security review MEDIUM-1): before 1.2.2 every registry recompute saved
the Card Equipment Supplier / Customer row with track_changes on, so Version
rows hold the old party-wide (cross-company) counts, totals and months — and a
form load returns recent Versions to any user who may open the party. The
registries no longer store figures nor keep history; delete their Versions.
Derived data only (every figure is recomputable from the cards). Idempotent."""

import frappe

REGISTRIES = ("Card Equipment Supplier", "Card Equipment Customer")


def execute():
	frappe.db.delete("Version", {"ref_doctype": ["in", REGISTRIES]})
