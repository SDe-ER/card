import frappe
from frappe import _

from card.settings import setting


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Report: "Equipment Supplier Statement" (Script Report, non-standard, ref doctype: Card Monthly Card)
	# Read-only. Groups monthly cards by Project > Equipment > Card for one supplier (or owned equipment),
	# and reconciles card totals with the supplier's GL entries (accrual credits / payment debits).
	# v1.1: no popup when supplier is empty (empty report + hint); "card" column removed (card no. is in "label").
	# Server Script rules: no "+=", no leading underscores, no nested def (exec locals are not visible inside functions).

	flt = frappe.utils.flt
	cint = frappe.utils.cint
	getdate = frappe.utils.getdate

	stype = filters.get("statement_type") or setting("default_statement_type")
	supplier = filters.get("supplier")
	no_supplier = stype == "مورد" and not supplier
	_company = frappe.defaults.get_global_default("company") or ""
	_prefix = (_company + " — ") if _company else ""

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

	include_draft = filters.get("include_draft")
	if include_draft is None:
		include_draft = setting("include_draft_in_reports")
	statuses = [1]
	if include_draft:
		statuses = [0, 1]

	cf = [
		["from_date", ">=", start],
		["from_date", "<=", end],
		["docstatus", "in", statuses],
	]
	if stype == "مورد":
		cf.append(["supplier", "=", supplier])
		cf.append(["ownership", "!=", "ملك"])
	else:
		cf.append(["ownership", "=", "ملك"])
	if filters.get("project"):
		cf.append(["project", "=", filters.get("project")])
	if filters.get("equipment"):
		cf.append(["equipment", "=", filters.get("equipment")])

	cards = (
		[]
		if no_supplier
		else frappe.get_all(
			"Card Monthly Card",
			filters=cf,
			fields=[
				"name",
				"equipment",
				"equipment_name",
				"project",
				"project_name",
				"shift",
				"month",
				"year",
				"rate_type",
				"rate",
				"working_days",
				"total_working_hours",
				"amount",
				"total_additions",
				"total_deductions",
				"docstatus",
				"from_date",
			],
			order_by="project asc, equipment asc, from_date asc, shift asc",
			limit_page_length=0,
		)
	)

	# equipment type map (+ optional filter)
	eq_names = list(set([c.equipment for c in cards]))
	eq_type = {}
	if eq_names:
		for e in frappe.get_all(
			"Card Equipment",
			filters=[["name", "in", eq_names]],
			fields=["name", "equipment_type"],
			limit_page_length=0,
		):
			eq_type[e.name] = e.equipment_type or ""
	if filters.get("equipment_type"):
		cards = [c for c in cards if eq_type.get(c.equipment) == filters.get("equipment_type")]

	# operating dates per card (hours > 0) -> distinct days per equipment, first/last date
	card_dates = {}
	if cards:
		rows = frappe.get_all(
			"Card Monthly Card Day",
			filters=[
				["parent", "in", [c.name for c in cards]],
				["parenttype", "=", "Card Monthly Card"],
				["working_hours", ">", 0],
			],
			fields=["parent", "operation_date"],
			limit_page_length=0,
			parent_doctype="Card Monthly Card",
		)
		for r in rows:
			k = r.parent
			if k not in card_dates:
				card_dates[k] = []
			card_dates[k].append(str(getdate(r.operation_date)))

	owned = stype != "مورد"

	data_rows = []
	grand = {"days": 0, "hours": 0.0, "amount": 0.0, "add": 0.0, "ded": 0.0, "net": 0.0, "eq": set()}

	projects = []
	by_project = {}
	for c in cards:
		p = c.project or "-"
		if p not in by_project:
			by_project[p] = {"name": c.project_name or p, "eqs": [], "by_eq": {}}
			projects.append(p)
		bp = by_project[p]
		if c.equipment not in bp["by_eq"]:
			bp["by_eq"][c.equipment] = {"name": c.equipment_name or c.equipment, "cards": []}
			bp["eqs"].append(c.equipment)
		bp["by_eq"][c.equipment]["cards"].append(c)

	for p in projects:
		bp = by_project[p]
		p_id = "P|" + p
		p_row = {
			"row_id": p_id,
			"parent_row": None,
			"indent": 0,
			"label": bp["name"],
			"project": p if p != "-" else None,
			"working_days": 0,
			"hours": 0.0,
			"amount": 0.0,
			"additions": 0.0,
			"deductions": 0.0,
			"net": 0.0,
			"bold": 1,
		}
		data_rows.append(p_row)
		for e in bp["eqs"]:
			be = bp["by_eq"][e]
			e_id = p_id + "|E|" + e
			dates = set()
			hours = 0.0
			amount = 0.0
			add = 0.0
			ded = 0.0
			rates = set()
			rtypes = set()
			card_rows = []
			for c in be["cards"]:
				cd = card_dates.get(c.name) or []
				for d in cd:
					dates.add(d)
				c_amount = 0 if owned else flt(c.amount, 2)
				c_add = flt(c.total_additions, 2)
				c_ded = flt(c.total_deductions, 2)
				c_net = 0 if owned else flt(c_amount + c_add - c_ded, 2)
				hours = hours + flt(c.total_working_hours)
				amount = amount + c_amount
				add = add + c_add
				ded = ded + c_ded
				rates.add(flt(c.rate))
				rtypes.add(c.rate_type or "")
				card_rows.append(
					{
						"row_id": e_id + "|C|" + c.name,
						"parent_row": e_id,
						"indent": 2,
						"label": c.name + (" " + _("(Draft)") if c.docstatus == 0 else ""),
						"card": c.name,
						"equipment": c.equipment,
						"project": c.project,
						"shift": c.shift,
						"first_date": min(cd) if cd else None,
						"last_date": max(cd) if cd else None,
						"working_days": len(set(cd)),
						"hours": flt(c.total_working_hours),
						"rate_type": c.rate_type,
						"rate": None if owned else flt(c.rate),
						"hourly_rate": None
						if owned or not flt(c.total_working_hours)
						else flt(c_amount / flt(c.total_working_hours), 2),
						"amount": c_amount,
						"additions": c_add,
						"deductions": c_ded,
						"net": c_net,
					}
				)
			net = 0 if owned else flt(amount + add - ded, 2)
			sorted_dates = sorted(dates)
			e_row = {
				"row_id": e_id,
				"parent_row": p_id,
				"indent": 1,
				"label": be["name"],
				"equipment": e,
				"equipment_type": eq_type.get(e),
				"project": p if p != "-" else None,
				"first_date": sorted_dates[0] if sorted_dates else None,
				"last_date": sorted_dates[-1] if sorted_dates else None,
				"working_days": len(dates),
				"hours": flt(hours, 2),
				"rate_type": next(iter(rtypes)) if len(rtypes) == 1 else "متعدد",
				"rate": None if owned else (next(iter(rates)) if len(rates) == 1 else None),
				"hourly_rate": None if owned or not hours else flt(amount / hours, 2),
				"amount": flt(amount, 2),
				"additions": flt(add, 2),
				"deductions": flt(ded, 2),
				"net": net,
				"bold": 1,
			}
			data_rows.append(e_row)
			data_rows.extend(card_rows)
			p_row["working_days"] = p_row["working_days"] + len(dates)
			p_row["hours"] = flt(p_row["hours"] + hours, 2)
			p_row["amount"] = flt(p_row["amount"] + amount, 2)
			p_row["additions"] = flt(p_row["additions"] + add, 2)
			p_row["deductions"] = flt(p_row["deductions"] + ded, 2)
			p_row["net"] = flt(p_row["net"] + net, 2)
			grand["eq"].add(e)
		grand["days"] = grand["days"] + p_row["working_days"]
		grand["hours"] = grand["hours"] + p_row["hours"]
		grand["amount"] = grand["amount"] + p_row["amount"]
		grand["add"] = grand["add"] + p_row["additions"]
		grand["ded"] = grand["ded"] + p_row["deductions"]
		grand["net"] = grand["net"] + p_row["net"]

	if data_rows:
		data_rows.append(
			{
				"row_id": "TOTAL",
				"parent_row": None,
				"indent": 0,
				"label": _("Grand total"),
				"working_days": grand["days"],
				"hours": flt(grand["hours"], 2),
				"amount": flt(grand["amount"], 2),
				"additions": flt(grand["add"], 2),
				"deductions": flt(grand["ded"], 2),
				"net": flt(grand["net"], 2),
				"bold": 1,
			}
		)

	columns = [
		{"fieldname": "label", "label": _("Description"), "fieldtype": "Data", "width": 260},
		{
			"fieldname": "equipment",
			"label": _("Equipment number"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 100,
		},
		{"fieldname": "equipment_type", "label": _("Equipment type"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 100,
		},
		{"fieldname": "shift", "label": _("Shift type"), "fieldtype": "Data", "width": 70},
		{"fieldname": "first_date", "label": _("First operation"), "fieldtype": "Date", "width": 100},
		{"fieldname": "last_date", "label": _("Last operation"), "fieldtype": "Date", "width": 100},
		{"fieldname": "working_days", "label": _("Working days"), "fieldtype": "Int", "width": 80},
		{"fieldname": "hours", "label": _("Hours"), "fieldtype": "Float", "precision": 2, "width": 90},
	]
	if not owned:
		columns = [
			*columns,
			{"fieldname": "rate_type", "label": _("Rate type"), "fieldtype": "Data", "width": 90},
			{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "hourly_rate", "label": _("Hourly rate"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "amount", "label": _("Operating amount"), "fieldtype": "Currency", "width": 120},
			{"fieldname": "additions", "label": _("Additions"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "deductions", "label": _("Deductions"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "net", "label": _("Net"), "fieldtype": "Currency", "width": 120},
		]

	summary = [
		{
			"label": _("Number of equipment"),
			"value": len(grand["eq"]),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{"label": _("Operating days"), "value": grand["days"], "datatype": "Int", "indicator": "Blue"},
		{
			"label": _("Operating hours"),
			"value": flt(grand["hours"], 2),
			"datatype": "Float",
			"indicator": "Blue",
		},
	]

	message = None
	if no_supplier:
		message = _("Select a supplier to display the statement.")
	elif not owned:
		# supplier GL: credit = accrual (liability up), debit = payment (liability down)
		gl_open = frappe.get_all(
			"GL Entry",
			filters=[
				["party_type", "=", "Supplier"],
				["party", "=", supplier],
				["is_cancelled", "=", 0],
				["posting_date", "<", start],
			],
			fields=["debit", "credit"],
			limit_page_length=0,
		)
		gl_period = frappe.get_all(
			"GL Entry",
			filters=[
				["party_type", "=", "Supplier"],
				["party", "=", supplier],
				["is_cancelled", "=", 0],
				["posting_date", ">=", start],
				["posting_date", "<=", end],
			],
			fields=["debit", "credit"],
			limit_page_length=0,
		)
		opening = 0.0
		for g in gl_open:
			opening = opening + flt(g.credit) - flt(g.debit)
		accrued = 0.0
		paid = 0.0
		for g in gl_period:
			accrued = accrued + flt(g.credit)
			paid = paid + flt(g.debit)
		closing = opening + accrued - paid
		diff = flt(grand["net"] - accrued, 2)
		summary = [
			*summary,
			{
				"label": _("Net cards"),
				"value": flt(grand["net"], 2),
				"datatype": "Currency",
				"indicator": "Green",
			},
			{
				"label": _("Accrual entries (Credit)"),
				"value": flt(accrued, 2),
				"datatype": "Currency",
				"indicator": "Blue",
			},
			{
				"label": _("Reconciliation difference"),
				"value": diff,
				"datatype": "Currency",
				"indicator": "Green" if abs(diff) < flt(setting("reconciliation_tolerance")) else "Red",
			},
			{
				"label": _("Opening balance"),
				"value": flt(opening, 2),
				"datatype": "Currency",
				"indicator": "Grey",
			},
			{
				"label": _("Paid (Debit)"),
				"value": flt(paid, 2),
				"datatype": "Currency",
				"indicator": "Orange",
			},
			{
				"label": _("Supplier closing balance"),
				"value": flt(closing, 2),
				"datatype": "Currency",
				"indicator": "Red" if closing > 0 else "Green",
			},
		]
		message = _prefix + _(
			"Equipment supplier statement: {0} — Period from {1} to {2} — Issue date {3}. Balance from accounting entries only; reconciliation difference = net cards − accrual entries."
		).format(supplier, start, end, frappe.utils.nowdate())
	else:
		message = _prefix + _(
			"Operating owned equipment by project — Period from {0} to {1} — Hours only until internal rates are defined."
		).format(start, end)

	data = [columns, data_rows, message, None, summary, True]
	return data
