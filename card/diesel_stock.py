# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-164 (#31, #47; closure plan WP-I1, owner decision O-11 D1): Stock-side helpers for
the Diesel Dispense DocType.

One Diesel Dispense on submit creates one DRAFT Stock Entry of purpose Material Issue
that consumes ``dispensed_litres`` of the company's diesel item (``Card Company
Settings.diesel_item``) from the dispense's tank Warehouse to the project. ``Material
Issue`` fits the semantics (the fuel leaves the tank, is not moved to another tracked
stock location) and is the closest ERPNext standard to the "tank → project" movement
the brief describes; a Material Transfer would require a per-project target Warehouse
that CARD does not configure (and auto-creating one for every project is out of
scope for I1). The Stock Entry is NEVER auto-submitted (FR-004): an accountant reviews
and submits it, at which point ERPNext writes the Stock Ledger and GL postings itself.

FR-100 is preserved: the resulting Stock Entry stays at project level — one line per
dispense — and never splits per equipment at GL. The dispense's optional ``card_equipment``
flows through to the detail row's ``card_equipment`` custom field for reports (set only
when the equipment field exists on Stock Entry Detail on this site; absent in default
ERPNext), but the posting dimension used for GL costing stays the project / project cost
center. The per-equipment information is served by G1's allocation rows and G2's reader
(wave 8), not by this Stock Entry.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from card.settings import company_setting

#: the UOM every CARD diesel line uses; the Stock Entry Detail's ``uom`` and
#: ``conversion_factor`` fall through to this; the Item on the company setting is
#: expected to carry stock_uom Litre (CARD does not set it — that is a Production step).
DIESEL_UOM = "Litre"
#: the Warehouse Type name that marks a Warehouse as a diesel fuel tank. Shared with the
#: controller for the fuel-tank check.
FUEL_TANK_WAREHOUSE_TYPE = "Fuel Tank"


def is_fuel_tank_warehouse(warehouse: str | None) -> bool:
	"""True iff ``warehouse`` is an existing Warehouse whose ``warehouse_type`` equals
	``"Fuel Tank"`` (O-11 D1). An empty or unknown warehouse returns False."""
	if not warehouse:
		return False
	wtype = frappe.db.get_value("Warehouse", warehouse, "warehouse_type")
	return (wtype or "") == FUEL_TANK_WAREHOUSE_TYPE


def check_warehouse_company(warehouse: str, company: str) -> None:
	"""Refuse a warehouse that belongs to another company. The cross-company hook
	(``card.company_scope``) already registers Warehouse as a company source, but a
	direct read here gives a clearer message and runs before Frappe's hook kicks in on
	insert-time Link validation."""
	if not warehouse:
		return
	wh_company = frappe.db.get_value("Warehouse", warehouse, "company")
	if wh_company and company and wh_company != company:
		frappe.throw(
			_("Tank warehouse {0} belongs to company {1}, not to {2}.").format(
				warehouse, wh_company, company
			),
			frappe.ValidationError,
		)


def _diesel_item(company: str) -> str:
	"""Return the diesel Item for the company, from Card Company Settings. The item is
	what Stock Entry Detail needs as ``item_code``; CARD never hardcodes it."""
	item = company_setting(company, "diesel_item")
	if not item:
		frappe.throw(
			_(
				"The company {0} has no Diesel item configured in Card Company Settings. Set it before entering a Diesel Dispense."
			).format(company)
		)
	return item


def build_stock_entry_for_dispense(dispense):
	"""Build (do not insert) the draft Stock Entry that records one Diesel Dispense.

	The returned document carries ``docstatus = 0`` so the caller inserts it as a draft.
	FR-004: never auto-submit. The accountant submits it after review, at which point
	ERPNext writes the Stock Ledger and GL postings itself.
	"""
	company = dispense.company
	item = _diesel_item(company)
	litres = flt(dispense.dispensed_litres)

	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Material Issue"
	se.purpose = "Material Issue"
	se.company = company
	se.posting_date = dispense.date
	se.set_posting_time = 1
	# FR-100: the line carries the project so the GL dimension (and any per-project
	# costing when the Stock Entry is submitted) is at project level, never per
	# equipment. The project also flows through to the detail row (see below).
	se.project = dispense.project
	se.is_opening = "No"

	detail = {
		"item_code": item,
		"qty": litres,
		"uom": DIESEL_UOM,
		"conversion_factor": 1.0,
		"s_warehouse": dispense.tank_warehouse,
		# Material Issue: no ``t_warehouse`` — the litres leave the tank to the project
		# (consumption). FR-100 one project-level line; the accountant can edit the
		# draft to change accounts or add dimensions before submitting it.
		"project": dispense.project,
		# A freshly inserted tank that has no valuation history would trip ERPNext's
		# "Valuation Rate is required" check at draft insert. The accountant typically
		# sets the real basic_rate (or runs a diesel-receipt that seeds the valuation)
		# before submitting; CARD leaves the draft in a shape that inserts cleanly.
		"allow_zero_valuation_rate": 1,
	}
	# Optional: pass the Card Equipment through to the detail row when Stock Entry
	# Detail carries the custom field on this site. A plain ERPNext install does not,
	# and we do not create the Custom Field here (a later wave owns that).
	if frappe.get_meta("Stock Entry Detail").has_field("card_equipment") and dispense.card_equipment:
		detail["card_equipment"] = dispense.card_equipment
	se.append("items", detail)
	return se


def post_dispense(dispense):
	"""Create the draft Stock Entry for a submitted Diesel Dispense and link it on the
	dispense through ``db_set`` (skips validate and update_modified). FR-004: not
	submitted; the accountant submits the draft itself after review.

	A Diesel Dispense that is being amended keeps no link to its predecessor's Stock
	Entry: the predecessor was cancelled before the amendment (Frappe's own cancel
	path runs ``on_cancel`` here, which deletes the draft), and this call creates a
	fresh draft for the new dispense.
	"""
	se = build_stock_entry_for_dispense(dispense)
	# ``insert`` runs Stock Entry's own validate: the warehouse company check, the item
	# existence, the UOM, etc. are all ERPNext's responsibility. CARD adds nothing of
	# its own there (AGENTS.md: standard Frappe/ERPNext mechanisms first). The draft is
	# inserted ignoring permissions because the submitting user holds Diesel Dispense
	# rights, not necessarily Stock Entry create — the resulting draft then shows up
	# in Stock Entry queues under ERPNext's own permissions.
	se.insert(ignore_permissions=True)
	dispense.db_set("stock_entry", se.name, update_modified=False)


def drop_stock_entry_by_name(se_name: str | None) -> None:
	"""Delete the given draft Stock Entry on cancel of its Diesel Dispense. The caller
	clears the Dispense's ``stock_entry`` back-reference BEFORE calling this, else
	Frappe's ``LinkExistsError`` refuses the delete (forward links are still live on
	the stored Dispense row).

	A Stock Entry that the accountant has already submitted (docstatus 1) is NOT
	deleted — the accountant cancels that one through ERPNext's own Cancel first,
	and only then may the Dispense be cancelled. A missing or already-cancelled
	draft is ignored.
	"""
	if not se_name:
		return
	if not frappe.db.exists("Stock Entry", se_name):
		return
	se = frappe.get_doc("Stock Entry", se_name)
	if se.docstatus == 1:
		frappe.throw(
			_(
				"Cannot cancel Diesel Dispense: its Stock Entry {0} has been submitted. Cancel the Stock Entry first."
			).format(se_name),
			frappe.ValidationError,
		)
	if se.docstatus == 0:
		# A draft Stock Entry is removed without going through its own cancel (there is
		# nothing posted to reverse); frappe.delete_doc honours DocPerm, so ignore it:
		# the user holds Diesel Dispense cancel but not necessarily Stock Entry delete.
		frappe.delete_doc("Stock Entry", se_name, ignore_permissions=True, force=0)
	# docstatus 2 (already cancelled): nothing to do


def drop_linked_stock_entry(dispense) -> None:
	"""Deprecated: deprecated-style convenience wrapper preserved for callers that
	want both the back-reference clear and the SE delete in one call. Prefer
	``drop_stock_entry_by_name`` in a flow that first clears the Dispense's
	``stock_entry`` back-reference via ``db_set``.
	"""
	se_name = dispense.get("stock_entry")
	dispense.db_set("stock_entry", None, update_modified=False)
	drop_stock_entry_by_name(se_name)
