import frappe
from frappe import _

from card.diesel import allocate_project_diesel
from card.report_access import resolve_company
from card.settings import setting


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.company = resolve_company(filters, "Card Monthly Card", "Project Diesel Fill")
	# Report: "Equipment Diesel Analysis" (F.2). Read-only, no accounting.
	# Per equipment x project x month: expected litres = operating hours x
	# (daily_diesel_consumption / daily standard hours) vs the litres actually
	# allocated from submitted Project Diesel Fills (card.diesel allocation),
	# with the variance and variance %. Equipment without a daily consumption
	# figure falls back to the older per-hour expected_consumption; with neither,
	# the expected side is left empty (flagged, never a crash).

	flt = frappe.utils.flt
	cint = frappe.utils.cint
	getdate = frappe.utils.getdate

	fm = cint(filters.get("from_month"))
	fy = cint(filters.get("from_year"))
	tm = cint(filters.get("to_month")) or fm
	ty = cint(filters.get("to_year")) or fy
	if not fm or not fy:
		frappe.throw(_("Select the start month and year"))
	start = getdate(str(fy) + "-" + str(fm).zfill(2) + "-01")
	end = frappe.utils.get_last_day(getdate(str(ty) + "-" + str(tm).zfill(2) + "-01"))
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))

	cf = [
		["company", "=", filters.company],
		["from_date", ">=", start],
		["from_date", "<=", end],
		["docstatus", "=", 1],
	]
	if filters.get("project"):
		cf.append(["project", "=", filters.get("project")])
	if filters.get("equipment"):
		cf.append(["equipment", "=", filters.get("equipment")])
	cards = frappe.get_all(
		"Card Monthly Card",
		filters=cf,
		fields=["equipment", "equipment_name", "project", "month", "year", "total_working_hours"],
		limit_page_length=0,
	)

	# hours per (equipment, project, period); shifts sum up
	agg = {}
	order = []
	for c in cards:
		key = (c.equipment, c.project, str(cint(c.year)), str(c.month).zfill(2))
		if key not in agg:
			agg[key] = {"name": c.equipment_name or c.equipment, "hours": 0.0}
			order.append(key)
		agg[key]["hours"] = agg[key]["hours"] + flt(c.total_working_hours)

	# equipment consumption figures
	eq_names = list({k[0] for k in order})
	eq_info = {}
	if eq_names:
		for e in frappe.get_all(
			"Card Equipment",
			filters=[["name", "in", eq_names]],
			fields=["name", "daily_hours", "daily_diesel_consumption", "expected_consumption"],
			limit_page_length=0,
		):
			eq_info[e.name] = e

	# actual allocated litres per (project, period) -> equipment
	alloc_cache = {}

	def allocated(project, month, year, equipment):
		ck = (project, month, year)
		if ck not in alloc_cache:
			alloc_cache[ck] = allocate_project_diesel(project, month, year, filters.company)
		share = alloc_cache[ck].get(equipment) or {}
		return flt(share.get("litres"))

	rows = []
	tot_expected = 0.0
	tot_actual = 0.0
	for key in order:
		equipment, project, year, month = key
		a = agg[key]
		info = eq_info.get(equipment) or frappe._dict()
		hours = flt(a["hours"], 2)
		# expected: daily figure spread over the standard day; fallback to the per-hour figure
		expected = None
		if flt(info.get("daily_diesel_consumption")) and flt(info.get("daily_hours")) > 0:
			expected = flt(hours * flt(info.daily_diesel_consumption) / flt(info.daily_hours), 3)
		elif flt(info.get("expected_consumption")):
			expected = flt(hours * flt(info.expected_consumption), 3)
		actual = allocated(project, month, year, equipment)
		variance = flt(actual - expected, 3) if expected is not None else None
		variance_pct = flt(variance / expected * 100, 2) if expected else None
		rows.append(
			{
				"equipment": equipment,
				"equipment_name": a["name"],
				"project": project,
				"period": year + "-" + month,
				"hours": hours,
				"daily_consumption": flt(info.get("daily_diesel_consumption")) or None,
				"expected_litres": expected,
				"actual_litres": actual,
				"variance": variance,
				"variance_pct": variance_pct,
			}
		)
		tot_expected = tot_expected + (expected or 0)
		tot_actual = tot_actual + actual

	columns = [
		{"fieldname": "equipment_name", "label": _("Equipment name"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "equipment",
			"label": _("Equipment number"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 110,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 110,
		},
		{"fieldname": "period", "label": _("Operating month"), "fieldtype": "Data", "width": 85},
		{
			"fieldname": "hours",
			"label": _("Operating hours"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 90,
		},
		{
			"fieldname": "daily_consumption",
			"label": _("Daily diesel consumption (litres per standard day)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{
			"fieldname": "expected_litres",
			"label": _("Expected litres"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"fieldname": "actual_litres",
			"label": _("Actual litres"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"fieldname": "variance",
			"label": _("Litres variance"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{"fieldname": "variance_pct", "label": _("Variance %"), "fieldtype": "Percent", "width": 90},
	]

	diff = flt(tot_actual - tot_expected, 3)
	summary = [
		{
			"label": _("Operating hours"),
			"value": flt(sum(r["hours"] for r in rows), 2),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{
			"label": _("Expected litres"),
			"value": flt(tot_expected, 3),
			"datatype": "Float",
			"indicator": "Blue",
		},
		{"label": _("Actual litres"), "value": flt(tot_actual, 3), "datatype": "Float", "indicator": "Blue"},
		{
			"label": _("Litres variance"),
			"value": diff,
			"datatype": "Float",
			"indicator": "Green" if abs(diff) <= flt(setting("reconciliation_tolerance")) else "Orange",
		},
	]
	message = _(
		"Expected = operating hours x (daily diesel consumption / daily standard hours). "
		"Actual = litres allocated from submitted diesel fills. Display only — no accounting."
	)
	return [columns, rows, message, None, summary, True]
