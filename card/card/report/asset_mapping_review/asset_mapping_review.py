import frappe
from frappe import _

from card.constants import OWNED, THIRD_PARTY
from card.meter_reconciliation import identity_conflict
from card.report_access import _role_reads, readable_links, resolve_company

REPORT = "Asset Mapping Review"
DOCTYPES = ("Asset", "Card Equipment")
ASSET_LINK = "الأصل_في_erpnext"
INACTIVE = ("Scrapped", "Sold")


def get_columns():
	return [
		{"fieldname": "review", "label": _("Review"), "fieldtype": "Data", "width": 300},
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 160},
		{"fieldname": "asset_name", "label": _("Asset name"), "fieldtype": "Data", "width": 220},
		{"fieldname": "asset_category", "label": _("Asset category"), "fieldtype": "Data", "width": 140},
		{"fieldname": "asset_status", "label": _("Asset status"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 120,
		},
		{"fieldname": "ownership", "label": _("Ownership"), "fieldtype": "Data", "width": 100},
		{"fieldname": "equipment_type", "label": _("Equipment type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "suggested_type",
			"label": _("Type for this category"),
			"fieldtype": "Data",
			"width": 140,
		},
		{"fieldname": "note", "label": _("Evidence"), "fieldtype": "Data", "width": 320},
	]


def execute(filters=None):
	# Report: "Asset Mapping Review" (maintenance plan M1). Read-only: classifies every submitted Asset of the
	# company against CARD equipment one by one, so the Owner decides which Assets need a CARD equipment record.
	# It creates, links and changes nothing; rented equipment never gets an Asset.
	filters = frappe._dict(filters or {})
	_assert_access()
	filters.company = resolve_company(filters, *DOCTYPES)
	types = {
		t.asset_category: t.name
		for t in frappe.get_all(
			"Card Equipment Type",
			filters={"asset_category": ["is", "set"]},
			fields=["name", "asset_category"],
		)
	}
	equipment = frappe.get_list(
		"Card Equipment",
		filters={"company": filters.company},
		fields=["name", "ownership", "equipment_type", ASSET_LINK],
		limit_page_length=0,
	)
	by_asset = {e.get(ASSET_LINK): e for e in equipment if e.get(ASSET_LINK)}
	assets = frappe.get_list(
		"Asset",
		filters={"company": filters.company, "docstatus": 1},
		fields=["name", "asset_name", "asset_category", "status", "item_code"],
		order_by="asset_category asc, name asc",
		limit_page_length=0,
	)
	rows = [_asset_row(a, by_asset.get(a.name), types) for a in assets]
	listed = {a.name for a in assets}
	for eq in equipment:
		if eq.ownership == OWNED and not eq.get(ASSET_LINK):
			rows.append(
				_equipment_row(eq, _("Owned equipment without an Asset link: confirm its Asset or ownership"))
			)
		elif eq.get(ASSET_LINK) and eq.get(ASSET_LINK) not in listed:
			rows.append(
				_equipment_row(eq, _("Linked Asset is not a submitted Asset of this company you may read"))
			)
	if filters.get("show") != "All":
		rows = [r for r in rows if r["attention"]]
	return readable_links(get_columns(), rows), rows, None, None, _summary(rows)


def _assert_access():
	if frappe.session.user != "Administrator" and not frappe.get_cached_doc("Report", REPORT).is_permitted():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	for doctype in DOCTYPES:
		if not _role_reads(doctype):
			frappe.throw(
				_("You need read access to {0} to run this report").format(_(doctype)), frappe.PermissionError
			)


def _asset_row(asset, eq, types):
	suggested = types.get(asset.asset_category)
	conflicts = identity_conflict(asset.name, asset.asset_name, asset.item_code)
	notes = []
	if conflicts:
		notes.append(
			_("Possible identity conflict between the Asset ID and its name or item: {0}").format(
				", ".join(conflicts)
			)
		)
	if eq:
		if eq.ownership not in (OWNED, THIRD_PARTY):
			review, attention = (
				_("Linked to equipment that is not owned: review (rented equipment has no Asset)"),
				True,
			)
		elif suggested and eq.equipment_type != suggested:
			review, attention = _("Linked; equipment type differs from the type of this Asset category"), True
		else:
			review, attention = _("Linked"), bool(conflicts)
	elif asset.status in INACTIVE:
		review, attention = _("Sold or scrapped: no CARD equipment needed"), False
	elif suggested:
		review, attention = _("Not in CARD: decide whether it is operated equipment (type available)"), True
	else:
		review, attention = _("Not in CARD: no equipment type for this Asset category yet"), True
	return {
		"attention": int(attention),
		"review": review,
		"asset": asset.name,
		"asset_name": asset.asset_name,
		"asset_category": asset.asset_category,
		"asset_status": _(asset.status) if asset.status else "",
		"equipment": eq.name if eq else None,
		"ownership": eq.ownership if eq else "",
		"equipment_type": eq.equipment_type if eq else "",
		"suggested_type": suggested or "",
		"note": "; ".join(notes),
	}


def _equipment_row(eq, review):
	return {
		"attention": 1,
		"review": review,
		"asset": eq.get(ASSET_LINK),
		"asset_name": "",
		"asset_category": "",
		"asset_status": "",
		"equipment": eq.name,
		"ownership": eq.ownership,
		"equipment_type": eq.equipment_type,
		"suggested_type": "",
		"note": "",
	}


def _summary(rows):
	attention = [r for r in rows if r["attention"]]
	return [
		{"label": _("Assets and equipment reviewed"), "value": len(rows), "datatype": "Int"},
		{
			"label": _("Needs a decision"),
			"value": len(attention),
			"datatype": "Int",
			"indicator": "Orange" if attention else "Green",
		},
	]
