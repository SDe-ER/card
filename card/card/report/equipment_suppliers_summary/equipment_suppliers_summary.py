import frappe
from frappe import _

from card.reconciliation import cards_invoiced, invoices_outside_card, reconciliation_notice
from card.report_access import can_view_ledger, ledger_notice, readable_links, resolve_company, strip_ledger
from card.settings import setting


def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Report: "Equipment Suppliers Summary" (Script Report, non-standard, ref doctype: Card Monthly Card)
	# Read-only. One row per supplier that has submitted cards in the period (automatic, no registration),
	# with card totals and GL reconciliation (supplier credits = accrual, debits = payment).
	# Server Script rules: no "+=", no leading underscores, no nested def/lambda, no tuple unpacking.

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
	company = resolve_company(filters)
	show_ledger = can_view_ledger(company)

	cf = [
		["company", "=", company],
		["from_date", ">=", start],
		["from_date", "<=", end],
		["docstatus", "=", 1],
		["ownership", "!=", "ملك"],
		["supplier", "is", "set"],
	]
	if filters.get("project"):
		cf.append(["project", "=", filters.get("project")])

	cards = frappe.get_all(
		"Card Monthly Card",
		filters=cf,
		fields=[
			"name",
			"supplier",
			"equipment",
			"total_working_hours",
			"net_amount",
		],
		limit_page_length=0,
	)

	# distinct operating dates per supplier+equipment
	card_key = {}
	for c in cards:
		card_key[c.name] = c.supplier + "|" + c.equipment
	eq_dates = {}
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
			k = card_key.get(r.parent)
			if k not in eq_dates:
				eq_dates[k] = set()
			eq_dates[k].add(str(getdate(r.operation_date)))

	agg = {}
	order = []
	for c in cards:
		s = c.supplier
		if s not in agg:
			agg[s] = {"eq": set(), "cards": 0, "hours": 0.0, "net": 0.0}
			order.append(s)
		a = agg[s]
		a["eq"].add(c.equipment)
		a["cards"] = a["cards"] + 1
		a["hours"] = a["hours"] + flt(c.total_working_hours)
		# supplier-side net (the PI's figure): customer-side rows of a sub-rental card are not the supplier's
		a["net"] = a["net"] + flt(c.net_amount)

	# GL per supplier (only suppliers that have cards in the period)
	gl = {}
	for s in order:
		gl[s] = {"opening": 0.0, "accrued": 0.0, "paid": 0.0}
	if order and show_ledger:
		for g in frappe.get_all(
			"GL Entry",
			filters=[
				["company", "=", company],
				["party_type", "=", "Supplier"],
				["party", "in", order],
				["is_cancelled", "=", 0],
				["posting_date", "<=", end],
			],
			fields=["party", "posting_date", "debit", "credit"],
			limit_page_length=0,
		):
			x = gl[g.party]
			if getdate(g.posting_date) < start:
				x["opening"] = x["opening"] + flt(g.credit) - flt(g.debit)
			else:
				x["accrued"] = x["accrued"] + flt(g.credit)
				x["paid"] = x["paid"] + flt(g.debit)

	# like-for-like reconciliation: card nets are before VAT, GL credits include it
	inv_net = (
		cards_invoiced("Supplier", order, company, start, end, cards=[c.name for c in cards])
		if show_ledger
		else {}
	)
	# ERPNext invoices CARD did not create: shown apart, never matched to cards
	outside = invoices_outside_card("Supplier", order, company, start, end) if show_ledger else {}

	names = {}
	if order:
		for s in frappe.get_all(
			"Supplier", filters=[["name", "in", order]], fields=["name", "supplier_name"], limit_page_length=0
		):
			names[s.name] = s.supplier_name or s.name

	result = []
	tot = {
		"eq": 0,
		"cards": 0,
		"days": 0,
		"hours": 0.0,
		"net": 0.0,
		"accrued": 0.0,
		"invoiced_net": 0.0,
		"diff": 0.0,
		"external_net": 0.0,
		"opening": 0.0,
		"paid": 0.0,
		"closing": 0.0,
	}
	pairs = sorted([[-agg[k]["net"], k] for k in order])
	for pr in pairs:
		s = pr[1]
		a = agg[s]
		x = gl[s]
		days = 0
		for e in a["eq"]:
			days = days + len(eq_dates.get(s + "|" + e) or set())
		net = flt(a["net"], 2)
		closing = flt(x["opening"] + x["accrued"] - x["paid"], 2)
		inv = flt(inv_net.get(s), 2)
		diff = flt(net - inv, 2)
		ext = flt(outside.get(s), 2)
		result.append(
			{
				"supplier": s,
				"supplier_name": names.get(s, s),
				"equipment_count": len(a["eq"]),
				"card_count": a["cards"],
				"working_days": days,
				"hours": flt(a["hours"], 2),
				"net": net,
				"accrued": flt(x["accrued"], 2),
				"invoiced_net": inv,
				"diff": diff,
				"external_net": ext,
				"opening": flt(x["opening"], 2),
				"paid": flt(x["paid"], 2),
				"closing": closing,
			}
		)
		tot["eq"] = tot["eq"] + len(a["eq"])
		tot["cards"] = tot["cards"] + a["cards"]
		tot["days"] = tot["days"] + days
		tot["hours"] = tot["hours"] + a["hours"]
		tot["net"] = tot["net"] + net
		tot["accrued"] = tot["accrued"] + x["accrued"]
		tot["invoiced_net"] = tot["invoiced_net"] + inv
		tot["diff"] = tot["diff"] + diff
		tot["external_net"] = tot["external_net"] + ext
		tot["opening"] = tot["opening"] + x["opening"]
		tot["paid"] = tot["paid"] + x["paid"]
		tot["closing"] = tot["closing"] + closing

	if result:
		result.append(
			{
				"supplier": None,
				"supplier_name": _("Total"),
				"is_total": 1,
				"equipment_count": tot["eq"],
				"card_count": tot["cards"],
				"working_days": tot["days"],
				"hours": flt(tot["hours"], 2),
				"net": flt(tot["net"], 2),
				"accrued": flt(tot["accrued"], 2),
				"invoiced_net": flt(tot["invoiced_net"], 2),
				"diff": flt(tot["diff"], 2),
				"external_net": flt(tot["external_net"], 2),
				"opening": flt(tot["opening"], 2),
				"paid": flt(tot["paid"], 2),
				"closing": flt(tot["closing"], 2),
			}
		)

	columns = [
		{"fieldname": "supplier_name", "label": _("Supplier"), "fieldtype": "Data", "width": 240},
		{
			"fieldname": "supplier",
			"label": _("Supplier code"),
			"fieldtype": "Link",
			"options": "Supplier",
			"width": 160,
		},
		{"fieldname": "equipment_count", "label": _("Equipment"), "fieldtype": "Int", "width": 70},
		{"fieldname": "card_count", "label": _("Cards"), "fieldtype": "Int", "width": 70},
		{"fieldname": "working_days", "label": _("Operating days"), "fieldtype": "Int", "width": 90},
		{"fieldname": "hours", "label": _("Hours"), "fieldtype": "Float", "precision": 2, "width": 90},
		{"fieldname": "net", "label": _("Net cards"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "accrued", "label": _("Accrual entries"), "fieldtype": "Currency", "width": 120},
		{
			"fieldname": "invoiced_net",
			"label": _("Invoiced through Card (net before VAT)"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{"fieldname": "diff", "label": _("Not invoiced through Card"), "fieldtype": "Currency", "width": 120},
		{
			"fieldname": "external_net",
			"label": _("ERPNext invoices outside Card — to reconcile (net before VAT)"),
			"fieldtype": "Currency",
			"width": 150,
		},
		{"fieldname": "opening", "label": _("Opening balance"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "paid", "label": _("Paid"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "closing", "label": _("Closing balance"), "fieldtype": "Currency", "width": 130},
	]

	summary = [
		{"label": _("Number of suppliers"), "value": len(order), "datatype": "Int", "indicator": "Blue"},
		{"label": _("Net cards"), "value": flt(tot["net"], 2), "datatype": "Currency", "indicator": "Green"},
		{
			"label": _("Not invoiced through Card"),
			"value": flt(tot["diff"], 2),
			"datatype": "Currency",
			"indicator": "Green" if abs(tot["diff"]) < flt(setting("reconciliation_tolerance")) else "Red",
		},
		{
			"label": _("ERPNext invoices outside Card — to reconcile (net before VAT)"),
			"value": flt(tot["external_net"], 2),
			"datatype": "Currency",
			"indicator": "Orange" if flt(tot["external_net"], 2) else "Green",
		},
		{
			"label": _("Total supplier balances"),
			"value": flt(tot["closing"], 2),
			"datatype": "Currency",
			"indicator": "Orange",
		},
	]
	message = (
		company
		+ " — "
		+ _(
			"Equipment suppliers summary — Period from {0} to {1}. Click on the supplier name to open their statement."
		).format(start, end)
	)

	if not show_ledger:
		columns, summary = strip_ledger(
			columns,
			result,
			summary,
			("accrued", "invoiced_net", "diff", "external_net", "opening", "paid", "closing"),
			(
				_("Not invoiced through Card"),
				_("ERPNext invoices outside Card — to reconcile (net before VAT)"),
				_("Total supplier balances"),
			),
		)
		message = message + " " + ledger_notice()
	else:
		message = message + " " + reconciliation_notice()

	columns = readable_links(columns, result)
	data = [columns, result, message, None, summary, True]
	return data
