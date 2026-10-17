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
	# a case-only rename resolves under the collation already: nothing to move
	if row and row.lower() != new.lower():
		if frappe.db.get_value(registry, new, field) not in (None, new):
			# a stale row (left by a pre-hook rename) holds the name; it is regenerable
			frappe.delete_doc(registry, new, ignore_permissions=True, force=True)
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


def _restricted_companies(user):
	"""The companies ``user`` is limited to for monthly cards, or None when the
	user is not restricted (sees every company) — then no extra condition."""
	from card.report_access import permitted_companies

	if user == "Administrator":
		return None
	allowed = permitted_companies(user=user)
	if set(allowed) >= set(frappe.get_all("Company", pluck="name")):
		return None
	return allowed


def _query_conditions(user, registry, field):
	companies = _restricted_companies(user or frappe.session.user)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	values = ", ".join(frappe.db.escape(c) for c in companies)
	return (
		f"exists (select 1 from `tabCard Monthly Card` c where c.`{field}` = `tab{registry}`.`name`"
		f" and c.docstatus < 2 and c.company in ({values}))"
	)


def supplier_query_conditions(user=None):
	return _query_conditions(user, "Card Equipment Supplier", "supplier")


def customer_query_conditions(user=None):
	return _query_conditions(user, "Card Equipment Customer", "customer")


def has_registry_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level twin of the query conditions: a restricted user may open
	only a party that has a draft or submitted card in one of their companies.
	Frappe 16 (permissions.has_controller_permissions) treats ANY falsy return as
	a denial — a controller can only deny — so "no objection" must be True."""
	companies = _restricted_companies(user or frappe.session.user)
	if companies is None or doc.is_new():
		return True
	_registry, field = REGISTRIES["Supplier" if doc.doctype == "Card Equipment Supplier" else "Customer"]
	return bool(
		companies
		and frappe.db.exists(
			"Card Monthly Card",
			{field: doc.name, "docstatus": ["<", 2], "company": ["in", companies]},
		)
	)
