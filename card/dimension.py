# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Accounting Dimension "Card Equipment" (O3).

The dimension is the official ERPNext mechanism that lets every GL-bearing
document (and so the GL/TB/P&L/BS reports) carry the equipment. Creating it
adds a `card_equipment` custom field to ~53 ERPNext doctypes (an ALTER TABLE
on each, empty columns).

Owner decisions: 2026-11-22 (FR-176) — the app can create it itself (patch `v4_11_0.ensure_card_equipment_dimension`
on migrate, `after_install` on a fresh install), so supplier payments can be linked to an equipment; 2026-11-24 —
only when Card Settings "Enable Card Equipment accounting dimension" is on (default off). While the switch is off
nothing is created or enabled again, by the patch, the install hook or the manual command. It is never mandatory. On
uninstall it is only disabled (its fields become read-only), never deleted, so the equipment values already in the
ledger are kept. To create it: back up, turn the switch on, then run

        bench --site <site> execute card.dimension.ensure_card_equipment_dimension

Turning the switch off later creates nothing new and removes nothing. card.install.before_tests turns the switch on
and calls it (the committed test bootstrap; its ALTER TABLEs must never run inside a test transaction). GL posting
still refuses to build without it (owner checkpoint B).
"""

import frappe

DIMENSION_DOCTYPE = "Card Equipment"
DIMENSION_FIELD = "card_equipment"
ASSET_LINK_FIELD = "الأصل_في_erpnext"
SWITCH_FIELD = "enable_card_equipment_dimension"


def has_dimension():
	"""Does this site have the Card Equipment accounting dimension?"""
	return bool(frappe.db.exists("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE}))


def gl_has_dimension_field():
	return frappe.get_meta("GL Entry").has_field(DIMENSION_FIELD)


def dimension_switched_on():
	"""Owner decision 2026-11-24: Card Settings decides whether this site may have the dimension (default off)."""
	return bool(frappe.db.get_single_value("Card Settings", SWITCH_FIELD))


def ensure_card_equipment_dimension():
	"""Create the dimension (idempotent, non-mandatory for BS/PL); a disabled one is enabled again. Does nothing
	while the Card Settings switch is off.

	Callers (FR-176): patch v4_11_0.ensure_card_equipment_dimension, after_install, the manual bench command and the
	committed test bootstrap. The caller commits after it returns — this function never commits itself, and its
	ALTER TABLEs must never run from a controller or inside a test transaction."""
	if not dimension_switched_on():
		return "switched off"
	if has_dimension():
		return set_card_equipment_dimension_disabled(False) if _is_disabled() else "exists"
	return _create_dimension()


def _create_dimension():
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		make_dimension_in_accounting_doctypes,
	)

	doc = frappe.new_doc("Accounting Dimension")
	doc.document_type = DIMENSION_DOCTYPE
	for company in frappe.get_all("Company", pluck="name"):
		doc.append(
			"dimension_defaults",
			{"company": company, "mandatory_for_bs": 0, "mandatory_for_pl": 0},
		)
	doc.insert(ignore_permissions=True)
	# ERPNext normally creates the custom fields in a background job; create them
	# synchronously so this manual run is complete when it returns (the queued
	# job finds them existing and is a no-op).
	make_dimension_in_accounting_doctypes(doc=doc)
	return doc.name

def _is_disabled():
	return bool(frappe.db.get_value("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE}, "disabled"))


def set_card_equipment_dimension_disabled(disabled):
	"""Disable (uninstall) or enable again (reinstall) the dimension with ERPNext's own toggle: its custom fields
	become read-only or editable; nothing is deleted. The fields stay Link fields (frappe refuses to change a custom
	field from Link to Data); after an uninstall they point at the deleted Card Equipment DocType — a known
	limitation, checked before any uninstall. A no-op when the dimension is missing or already so."""
	name = frappe.db.get_value("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE}, "name")
	if not name:
		return None
	doc = frappe.get_doc("Accounting Dimension", name)
	if bool(doc.disabled) == bool(disabled):
		return "unchanged"
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import toggle_disabling

	doc.db_set("disabled", 1 if disabled else 0)
	# synchronous (the standard disable_dimension queues it): the uninstall/install hook is complete when it returns
	toggle_disabling(doc=frappe.as_json(doc.as_dict()))
	return "disabled" if disabled else "enabled"


def sync_asset_dimension(equipment):
	"""Keep the linked Asset's card_equipment dimension pointing at the equipment
	(owner amendment 2: automatic Asset <-> equipment dimension sync). The Asset's
	dimension value flows into its depreciation entries' GL. No-op while the
	dimension does not exist."""
	if not frappe.get_meta("Asset").has_field(DIMENSION_FIELD):
		return
	asset = equipment.get(ASSET_LINK_FIELD)
	before = equipment.get_doc_before_save()
	prev = before.get(ASSET_LINK_FIELD) if before else None
	if (
		prev
		and prev != asset
		and frappe.db.exists("Asset", prev)
		and frappe.db.get_value("Asset", prev, DIMENSION_FIELD) == equipment.name
	):
		frappe.db.set_value("Asset", prev, DIMENSION_FIELD, None, update_modified=False)
	if asset and frappe.db.exists("Asset", asset):
		if frappe.db.get_value("Asset", asset, DIMENSION_FIELD) != equipment.name:
			frappe.db.set_value("Asset", asset, DIMENSION_FIELD, equipment.name, update_modified=False)
