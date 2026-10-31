import frappe
from frappe import _
from frappe.utils import flt

from card.meter_reconciliation import (
	ALERT_HOURS,
	FLAG_LABELS,
	OIL_CHANGE_HOURS,
	OK,
	assert_report_access,
	asset_meter_values,
	card_hours,
	classify_readings,
	completed_maintenance,
	identity_conflict,
	legacy_readings,
	summarize,
)
from card.report_access import readable_links, resolve_company

ASSET_LINK = "الأصل_في_erpnext"


def get_columns(detail):
	if detail:
		return [
			{
				"fieldname": "equipment",
				"label": _("Equipment"),
				"fieldtype": "Link",
				"options": "Card Equipment",
				"width": 120,
			},
			{
				"fieldname": "asset",
				"label": _("Asset"),
				"fieldtype": "Link",
				"options": "Asset",
				"width": 150,
			},
			{"fieldname": "at", "label": _("Reading time"), "fieldtype": "Datetime", "width": 160},
			{"fieldname": "reading", "label": _("Meter reading"), "fieldtype": "Float", "width": 110},
			{
				"fieldname": "meter_hours",
				"label": _("Hours since previous plausible reading"),
				"fieldtype": "Float",
				"width": 150,
			},
			{"fieldname": "flag", "label": _("Reading check"), "fieldtype": "Data", "width": 260},
			{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 130},
			{"fieldname": "ref", "label": _("Source record"), "fieldtype": "Data", "width": 160},
			{"fieldname": "note", "label": _("Evidence"), "fieldtype": "Data", "width": 300},
		]
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 160},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 120,
		},
		{"fieldname": "equipment_name", "label": _("Equipment name"), "fieldtype": "Data", "width": 180},
		{"fieldname": "asset", "label": _("Asset"), "fieldtype": "Link", "options": "Asset", "width": 150},
		{"fieldname": "readings", "label": _("Meter readings"), "fieldtype": "Int", "width": 90},
		{
			"fieldname": "first_reading",
			"label": _("First plausible reading"),
			"fieldtype": "Float",
			"width": 120,
		},
		{"fieldname": "first_at", "label": _("First reading date"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "last_reading",
			"label": _("Last plausible reading"),
			"fieldtype": "Float",
			"width": 120,
		},
		{"fieldname": "last_at", "label": _("Last reading date"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "meter_hours",
			"label": _("Meter hours (differences only)"),
			"fieldtype": "Float",
			"width": 130,
		},
		{
			"fieldname": "card_hours",
			"label": _("CARD hours (submitted cards, same period)"),
			"fieldtype": "Float",
			"width": 150,
		},
		{"fieldname": "gap_pct", "label": _("Difference %"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "issues", "label": _("Reading issues"), "fieldtype": "Data", "width": 320},
		{"fieldname": "asset_meter", "label": _("Asset meter fields"), "fieldtype": "Data", "width": 260},
		{"fieldname": "baseline", "label": _("Maintenance baseline"), "fieldtype": "Data", "width": 300},
	]


def execute(filters=None):
	# Report: "Equipment Meter Reconciliation" (R1). Read-only: it reads meter readings and CARD hours and changes,
	# creates or links nothing. Meter readings are cumulative: only differences between consecutive plausible
	# readings are hours. No maintenance baseline is set here (D-M4: verified reading + verified maintenance).
	filters = frappe._dict(filters or {})
	assert_report_access()
	filters.company = resolve_company(filters, "Card Equipment", "Card Monthly Card")
	tolerance = flt(filters.get("tolerance_pct")) if filters.get("tolerance_pct") is not None else 10
	detail = filters.get("view") == "Readings"
	equipment = frappe.get_list(
		"Card Equipment",
		filters={
			"company": filters.company,
			**({"name": filters.equipment} if filters.get("equipment") else {}),
		},
		fields=["name", "equipment_name", "meter_type", ASSET_LINK],
		order_by="name asc",
		limit_page_length=0,
	)
	by_asset = {e.get(ASSET_LINK): e for e in equipment if e.get(ASSET_LINK)}
	readable_assets = set(
		frappe.get_list("Asset", filters={"name": ["in", list(by_asset)]}, pluck="name", limit_page_length=0)
		if by_asset
		else []
	)
	legacy, legacy_available = legacy_readings(readable_assets)
	rows = []
	for eq in equipment:
		asset = eq.get(ASSET_LINK) if eq.get(ASSET_LINK) in readable_assets else None
		readings = classify_readings(legacy.get(asset, [])) if asset else []
		if detail:
			rows.extend(_detail_rows(eq, asset, readings))
			continue
		rows.append(_summary_row(eq, asset, readings, tolerance))
	if not detail and filters.get("show") != "All":
		rows = [r for r in rows if r["attention"]]
	message = _message(legacy_available)
	return readable_links(get_columns(detail), rows), rows, message, None, _summary(rows, detail)


def _detail_rows(eq, asset, readings):
	return [
		{
			"equipment": eq.name,
			"asset": asset,
			"at": r["at"],
			"reading": flt(r.get("reading")),
			"meter_hours": flt(r["meter_hours"], 2),
			"flag": _(FLAG_LABELS[r["flag"]]),
			"source": _(r["source"]),
			"ref": r["ref"],
			"note": _(r["note"]) if r.get("note") else "",
		}
		for r in readings
	]


def _summary_row(eq, asset, readings, tolerance):
	summary = summarize(readings, lambda a, b: card_hours(eq.name, a, b))
	issues = [
		f"{_(FLAG_LABELS[flag])}: {count}"
		for flag, count in summary["counts"].items()
		if count and flag != OK
	]
	asset_doc = (
		frappe.db.get_value("Asset", asset, ["asset_name", "item_code"], as_dict=True) if asset else None
	)
	conflicts = identity_conflict(asset, asset_doc.asset_name, asset_doc.item_code) if asset_doc else []
	if conflicts:
		issues.append(
			_("Possible identity conflict between the Asset ID and its name or item: {0}").format(
				", ".join(conflicts)
			)
		)
	meter_fields = asset_meter_values(asset) if asset else {}
	last = summary["last"]
	differing = [
		f"{field}: {flt(value)}"
		for field, value in meter_fields.items()
		if last
		and flt(value)
		and abs(flt(value) - flt(last["reading"])) > flt(last["reading"]) * tolerance / 100
	]
	if differing:
		issues.append(_("Asset meter fields differ from the last plausible reading"))
	gap_pct = None
	if summary["card_hours"] is not None and summary["meter_hours"]:
		gap_pct = flt((summary["card_hours"] - summary["meter_hours"]) * 100 / summary["meter_hours"], 1)
		if abs(gap_pct) > tolerance:
			issues.append(_("CARD hours differ from the meter hours by more than {0}%").format(tolerance))
	if not readings:
		status = _("No meter readings")
	elif issues:
		status = _("Needs review")
	else:
		status = _("Consistent")
	maintained = completed_maintenance(asset) if asset else None
	baseline = (
		_("Not set: needs a verified meter reading and the completed maintenance of {0} confirmed").format(
			maintained
		)
		if maintained
		else _("Not set: no verified maintenance history")
	)
	return {
		"attention": int(bool(issues) or not readings),
		"status": status,
		"equipment": eq.name,
		"equipment_name": eq.equipment_name,
		"asset": asset,
		"readings": summary["readings"],
		"first_reading": flt(summary["first"]["reading"]) if summary["first"] else None,
		"first_at": summary["first"]["at"] if summary["first"] else None,
		"last_reading": flt(last["reading"]) if last else None,
		"last_at": last["at"] if last else None,
		"meter_hours": summary["meter_hours"] if readings else None,
		"card_hours": summary["card_hours"],
		"gap_pct": gap_pct,
		"issues": "; ".join(issues),
		"asset_meter": ", ".join(f"{k}: {flt(v)}" for k, v in meter_fields.items()),
		"baseline": baseline,
	}


def _message(legacy_available):
	parts = [
		_("Maintenance policy kept: alert at {0} operating hours, oil change due at {1}.").format(
			ALERT_HOURS, OIL_CHANGE_HOURS
		),
		_(
			"Meter readings are cumulative: only differences between consecutive plausible readings count as hours."
		),
		_("This report sets no maintenance baseline and changes nothing."),
	]
	if not legacy_available:
		parts.append(
			_("No legacy fuelling log readings are available on this site (or you may not read them).")
		)
	return "<br>".join(frappe.utils.escape_html(p) for p in parts)


def _summary(rows, detail):
	if detail:
		return [{"label": _("Readings"), "value": len(rows), "datatype": "Int"}]
	attention = [r for r in rows if r["attention"]]
	return [
		{"label": _("Equipment"), "value": len(rows), "datatype": "Int"},
		{
			"label": _("Needs review"),
			"value": len(attention),
			"datatype": "Int",
			"indicator": "Red" if attention else "Green",
		},
	]
