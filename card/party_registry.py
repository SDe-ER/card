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
	"Supplier": ("Card Equipment Supplier", "supplier"),
	"Customer": ("Card Equipment Customer", "customer"),
}


def before_rename(doc, method, old, new, merge=False):
	registry, field = REGISTRIES[doc.doctype]
	# by name or by link: a row a pre-hook rename left misnamed must go too
	row = registry_row(registry, field, old) if merge else None
	if row:
		frappe.delete_doc(registry, row, ignore_permissions=True, force=True)


def after_rename(doc, method, old, new, merge=False):
	registry, field = REGISTRIES[doc.doctype]
	# links are rewritten by now, so the party's row carries ``new`` in its link
	row = frappe.db.get_value(registry, {field: new})
	if row and row != new and not frappe.db.exists(registry, new):
		rename_doc(registry, row, new, force=True, ignore_permissions=True, show_alert=False)
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
