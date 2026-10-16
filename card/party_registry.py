# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Keep the CARD party registries (Card Equipment Supplier / Customer, each
named by its party) aligned with ERPNext Supplier / Customer renames and
merges. Report filters link to the registries by name, so a registry row must
always carry its party's current name.

- rename A -> A': Frappe rewrites the registry's ``supplier`` link to A'; the
  row itself is then renamed to A'.
- merge A into B: the A row is dropped BEFORE Frappe rewrites links (its
  ``supplier`` would become B and collide with B's row on the unique index,
  blocking the ERPNext merge); B's row is recomputed afterwards."""

import frappe
from frappe.model.rename_doc import rename_doc

REGISTRIES = {
	"Supplier": "Card Equipment Supplier",
	"Customer": "Card Equipment Customer",
}


def before_rename(doc, method, old, new, merge=False):
	registry = REGISTRIES[doc.doctype]
	if merge and frappe.db.exists(registry, old):
		frappe.delete_doc(registry, old, ignore_permissions=True, force=True)


def after_rename(doc, method, old, new, merge=False):
	registry = REGISTRIES[doc.doctype]
	if old != new and frappe.db.exists(registry, old):
		rename_doc(registry, old, new, force=True, ignore_permissions=True, show_alert=False)
	if merge:
		recompute(doc.doctype, new)


def recompute(party_type, party):
	from card.api import recompute_customer, recompute_supplier

	if party_type == "Supplier":
		recompute_supplier(party)
	else:
		recompute_customer(party)


def registry_row(registry, field, party):
	"""The registry row of ``party``: by name, else by its link field (a row left
	misnamed by a rename that happened before these hooks existed)."""
	if frappe.db.exists(registry, party):
		return party
	return frappe.db.get_value(registry, {field: party})
