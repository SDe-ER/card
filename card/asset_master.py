# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-098: the ERPNext Asset owns the asset master data of a linked Card Equipment.

One map (``MASTER_FIELDS``) says which Card Equipment fields come from the linked Asset.
Every path uses it: the form prefill, the save-time sync, the Asset change hook and the
backfill patch. Rules (Owner decisions D1/D5, 2026-11-01):

* A linked equipment takes each mapped field from its Asset exactly as stored there
  (no trimming, case or format change). The field is then read-only in CARD.
* An empty Asset value (empty string, None, 0 for the manufacture year) is "not known":
  the CARD value is kept and stays editable. Nothing is invented.
* CARD-owned fields (ownership, rates, operator, meter, fuel, maintenance, documents,
  exit, components...) are never written here.
* CARD never writes to the Asset.
* Every value an Asset replaces is recorded: the document Version (track_changes) on a
  save, and an explicit Version + Comment when the Asset hook updates the equipment.

Optional source fields (site custom fields such as ``custom_chassis_no``) are read only
when the Asset DocType has them, so a site without them keeps working.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr

from card.dimension import ASSET_LINK_FIELD

# Card Equipment field <- Asset field (copied as stored)
DIRECT_FIELDS = {
	"equipment_name": "asset_name",
	"serial_no": "custom_chassis_no",
	"manufacture_year": "custom_manufacture_year",
	"image": "image",
}
# Card Equipment fields derived from the Asset (see asset_master_values)
DERIVED_FIELDS = ("brand", "equipment_type")
MASTER_FIELDS = (*DIRECT_FIELDS, *DERIVED_FIELDS)
OWNED_LIST_FIELD = "asset_owned_fields"

# D5: Asset information shown read-only on the equipment, never stored in CARD.
# Labels come from the Asset meta; fields the site does not have are skipped.
VIEW_FIELDS = (
	"status",
	"disposal_date",
	"item_code",
	"location",
	"custom_engine_no",
	"custom_engine_cylinders",
	"custom_country_of_manufacture",
	"custom_vehicle_condition",
	"custom_vehicle_color",
	"custom_vehicle_capacity",
	"custom_vehicle_weight_kg",
	"custom_customs_declaration_no",
	"custom_customs_date",
	"custom_customs_card_no",
	"custom_customs_fees_sar",
)
# Asset values that are financial: shown only to users who may read the equipment's
# level-2 (financial) fields, as for the Asset purchase value (FR-096).
FINANCIAL_VIEW_FIELDS = frozenset({"custom_customs_fees_sar"})
FINANCIAL_PERMLEVEL = 2

# An Asset in one of these states no longer belongs to the company's operating fleet.
OUT_OF_SERVICE_STATUSES = frozenset({"Sold", "Scrapped"})


def _known(fieldname, value):
	"""False for a value that means "not recorded" on the Asset."""
	if value is None:
		return False
	if fieldname == "manufacture_year":
		return cint(value) > 0
	if isinstance(value, str):
		return value != ""
	return True


def _asset_fields_present():
	meta = frappe.get_meta("Asset")
	return {card: source for card, source in DIRECT_FIELDS.items() if meta.has_field(source)}


def asset_master_values(asset):
	"""The Card Equipment master values the Asset knows: {card field: value}, exact,
	without the fields the Asset has no value for. {} for a missing Asset. No
	permission check: callers check the Asset first."""
	if not asset:
		return {}
	direct = _asset_fields_present()
	sources = sorted({"asset_name", "asset_category", "item_code", *direct.values()})
	row = frappe.db.get_value("Asset", asset, sources, as_dict=True)
	if not row:
		return {}
	values = {}
	for card_field, source in direct.items():
		if _known(card_field, row.get(source)):
			values[card_field] = row.get(source)
	if not values.get("equipment_name"):
		values["equipment_name"] = asset  # the Asset name when it has no asset_name (v3.0.0 rule)
	brand = row.item_code and frappe.db.get_value("Item", row.item_code, "brand")
	if _known("brand", brand):
		values["brand"] = brand
	equipment_type = row.asset_category and frappe.db.get_value(
		"Card Equipment Type", {"asset_category": row.asset_category}, "name"
	)
	if equipment_type:
		values["equipment_type"] = equipment_type
	return values


def owned_list(values):
	"""The value stored in ``asset_owned_fields``: the fields the Asset currently fills."""
	return ",".join(field for field in MASTER_FIELDS if field in values)


def apply_asset_master(doc):
	"""Set the Asset-owned fields of a Card Equipment from its linked Asset.

	Returns [(fieldname, old, new)] for every value that changed. Fields the Asset has
	no value for keep the CARD value. Without a link nothing is overwritten and the
	owned list is cleared (the values entered so far stay)."""
	asset = doc.get(ASSET_LINK_FIELD)
	values = asset_master_values(asset) if asset else {}
	changes = []
	for fieldname, value in values.items():
		old = doc.get(fieldname)
		if old != value:
			changes.append((fieldname, old, value))
			doc.set(fieldname, value)
	doc.set(OWNED_LIST_FIELD, owned_list(values))
	doc.equipment_type_from_asset = 1 if values.get("equipment_type") else 0
	return changes


def replaced_values(changes):
	"""The changes that overwrote a value CARD already had (not first fills)."""
	return [(f, old, new) for f, old, new in changes if _known(f, old)]


def comment_replaced(doctype, name, asset, changes):
	"""Audit note on the equipment for each CARD value an Asset value replaced."""
	replaced = replaced_values(changes)
	if not replaced:
		return
	lines = [
		_("{0}: {1} → {2}").format(_(frappe.get_meta(doctype).get_label(f)), cstr(old), cstr(new))
		for f, old, new in replaced
	]
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": doctype,
			"reference_name": name,
			"content": _("Updated from ERPNext Asset {0}:").format(asset) + "<br>" + "<br>".join(lines),
		}
	).insert(ignore_permissions=True)  # an audit note written by the system, not a user action


# ---------- Asset -> Card Equipment (doc_events on Asset) ----------


def on_asset_change(doc, method=None):
	"""Asset doc_events (on_update, on_update_after_submit, on_cancel): bring the one
	linked Card Equipment's Asset-owned fields in line.

	The Asset save is the authorized change; the equipment fields it updates are
	read-only mirrors in CARD, so they are written directly (db.set_value) with an
	explicit Version and Comment for the history, and with CARD's chassis uniqueness
	rule still applied. CARD never blocks an ERPNext Asset save: any failure is logged."""
	if frappe.flags.in_install or frappe.flags.in_migrate:
		return
	equipment = frappe.db.get_value("Card Equipment", {ASSET_LINK_FIELD: doc.name}, "name")
	if not equipment:
		return
	try:
		sync_equipment_from_asset(equipment)
	except Exception:
		frappe.log_error(title=_("CARD: Asset {0} sync to equipment {1} failed").format(doc.name, equipment))


def sync_equipment_from_asset(equipment):
	"""Update one Card Equipment from its Asset (system sync). Returns the changes made."""
	eq = frappe.get_doc("Card Equipment", equipment)
	asset = eq.get(ASSET_LINK_FIELD)
	before = {f: eq.get(f) for f in (*MASTER_FIELDS, OWNED_LIST_FIELD, "equipment_type_from_asset")}
	changes = apply_asset_master(eq)
	changes = _keep_unique_identity(eq, changes)
	updates = {f: eq.get(f) for f in before if eq.get(f) != before[f]}
	if not updates:
		return []
	if "serial_no" in updates:
		from card.card.doctype.card_equipment.card_equipment import identity_key

		updates["serial_no_key"] = identity_key(updates["serial_no"])
	frappe.db.set_value("Card Equipment", equipment, updates)
	if changes:
		frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Card Equipment",
				"docname": equipment,
				"data": frappe.as_json({"changed": [[f, old, new] for f, old, new in changes]}),
			}
		).insert(ignore_permissions=True)  # history row of a system sync
		comment_replaced("Card Equipment", equipment, asset, changes)
	return changes


def _keep_unique_identity(eq, changes):
	"""A chassis number from the Asset that another equipment of the company already uses
	is not copied (CARD's D1 rule); the equipment keeps its value and a Comment says why."""
	from card.card.doctype.card_equipment.card_equipment import identity_key

	for fieldname, old, new in list(changes):
		if fieldname != "serial_no":
			continue
		key = identity_key(new)
		other = key and frappe.db.get_value(
			"Card Equipment",
			{"company": eq.company, "serial_no_key": key, "name": ["!=", eq.name]},
			"name",
		)
		if other:
			eq.set("serial_no", old)
			owned = [f for f in cstr(eq.get(OWNED_LIST_FIELD)).split(",") if f and f != "serial_no"]
			eq.set(OWNED_LIST_FIELD, ",".join(owned))
			changes.remove((fieldname, old, new))
			frappe.get_doc(
				{
					"doctype": "Comment",
					"comment_type": "Info",
					"reference_doctype": "Card Equipment",
					"reference_name": eq.name,
					"content": _(
						"Chassis number {0} from ERPNext Asset {1} was not copied: equipment {2} already uses it."
					).format(new, eq.get(ASSET_LINK_FIELD), other),
				}
			).insert(ignore_permissions=True)  # audit note of a system sync
	return changes


# ---------- disposal / sale ----------


def asset_service_state(asset):
	"""(out_of_service, status, disposal_date) of an Asset: out of service when it is
	cancelled, Sold or Scrapped."""
	row = frappe.db.get_value("Asset", asset, ["docstatus", "status", "disposal_date"], as_dict=True)
	if not row:
		return False, None, None
	out = row.docstatus == 2 or row.status in OUT_OF_SERVICE_STATUSES
	return out, ("Cancelled" if row.docstatus == 2 else row.status), row.disposal_date


def assert_asset_in_service(equipment, worked_dates):
	"""Refuse operating hours recorded for an equipment whose Asset was sold, scrapped or
	cancelled: on or after the disposal date (any date for a cancelled Asset or one
	without a disposal date). ``worked_dates`` are the dates that carry hours."""
	asset = equipment and frappe.db.get_value("Card Equipment", equipment, ASSET_LINK_FIELD)
	if not asset:
		return
	out, status, disposal_date = asset_service_state(asset)
	if not out:
		return
	from frappe.utils import getdate

	blocked = sorted(
		cstr(d) for d in worked_dates if not disposal_date or getdate(d) >= getdate(disposal_date)
	)
	if blocked:
		frappe.throw(
			_(
				"ERPNext Asset {0} of equipment {1} is {2} (disposal date {3}); hours cannot be recorded on {4}."
			).format(asset, equipment, _(status), cstr(disposal_date) or "-", ", ".join(blocked)),
			title=_("Asset out of service"),
		)


# ---------- D5: read-only Asset information on the equipment form ----------


@frappe.whitelist(methods=["GET"])
def get_asset_master_view(equipment: str):
	"""Read-only Asset information for the equipment form: [{fieldname, label, value}].
	Needs read on the equipment and on its Asset; financial values only for users who
	may read the equipment's level-2 fields. Nothing is stored or changed."""
	eq = frappe.get_doc("Card Equipment", equipment)
	eq.check_permission("read")
	asset = eq.get(ASSET_LINK_FIELD)
	if not asset:
		return {"asset": None, "fields": []}
	frappe.has_permission("Asset", "read", asset, throw=True)
	meta = frappe.get_meta("Asset")
	fields = [f for f in VIEW_FIELDS if meta.has_field(f)]
	if FINANCIAL_PERMLEVEL not in eq.get_permlevel_access("read"):
		fields = [f for f in fields if f not in FINANCIAL_VIEW_FIELDS]
	row = frappe.db.get_value("Asset", asset, fields, as_dict=True) or {}
	out_of_service, status, disposal_date = asset_service_state(asset)
	return {
		"asset": asset,
		"out_of_service": out_of_service,
		"status": status,
		"disposal_date": disposal_date,
		"owned_fields": [f for f in cstr(eq.get(OWNED_LIST_FIELD)).split(",") if f],
		"fields": [
			{
				"fieldname": f,
				"label": _(meta.get_label(f)),
				"fieldtype": meta.get_field(f).fieldtype,
				"value": row.get(f),
			}
			for f in fields
			if _known(f, row.get(f)) and row.get(f) != 0
		],
	}
