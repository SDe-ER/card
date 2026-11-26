import frappe
from frappe import _

from card.adjustments import sided_adjustments
from card.card.doctype.card_stop_reason.card_stop_reason import side_stopped_hours
from card.card.report.equipment_supplier_statement.statement_period import (
	date_range,
	previous_work,
	range_work,
	scoped_month_ledger,
	supplier_ledger,
)
from card.card_value import PER_DAY, day_billing_basis
from card.open_month import provisional_suffix
from card.reconciliation import cards_invoiced, invoices_outside_card, reconciliation_notice
from card.report_access import (
	can_view_ledger,
	ledger_notice,
	readable_links,
	resolve_company,
	role_reads_money,
)
from card.report_currency import company_currency_report
from card.settings import setting
from card.transfer import billed_day_rows, with_stopped_hours_column

PAYMENTS_ROW = "PAYMENTS"


@company_currency_report()
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
	_company = resolve_company(filters)
	_prefix = _company + " — "
	show_ledger = can_view_ledger(_company)

	# interim settlement (Owner 2026-11-22): a from/to date pair overrides the months; without it the
	# month filters work exactly as before
	period = date_range(filters)
	if period:
		start, end = period
	else:
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
		["company", "=", _company],
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
	# the filters without the period: the balance also reads the cards before the range
	base_filters = list(cf)
	if period:
		# a card counts when its period overlaps the range; only its days inside the range are counted
		cf = [*cf, ["from_date", "<=", end], ["to_date", ">=", start]]
	else:
		cf = [*cf, ["from_date", ">=", start], ["from_date", "<=", end]]

	cards = (
		[]
		if no_supplier
		else frappe.get_all(
			"Card Monthly Card",
			filters=cf,
			fields=[
				"card_direction",
				"daily_hours_used",
				"hourly_rate_used",
				"to_date",
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
				"day_billing_basis",
				"day_billing_basis_used",
				"working_days",
				"total_working_hours",
				"billable_stopped_hours",
				"supplier_billable_stopped_hours",
				"customer_billable_stopped_hours",
				"amount",
				"docstatus",
				"workflow_state",
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

	work = None
	if period:
		# date range: each card counts only its days and its dated additions/deductions inside the range
		work = range_work(cards, start, end)
		cards = [c for c in cards if c.name in work]

	# supplier-side rows only: a sub-rental card's customer rows belong to the Sales Invoice
	if work is not None:
		sided = {n: (w["additions"], w["deductions"]) for n, w in work.items()}
	else:
		sided = sided_adjustments([c.name for c in cards], "Supplier")

	# operating dates per card (hours > 0) -> distinct days per equipment, first/last date
	card_dates = {}
	if work is not None:
		card_dates = {n: sorted(w["dates"]) for n, w in work.items()}
	elif cards:
		# FR-118: a day bills with operating hours or billable stopped hours (is_billed_day)
		rows = billed_day_rows([c.name for c in cards], include_loads=False)
		for r in rows:
			k = r.parent
			if k not in card_dates:
				card_dates[k] = []
			card_dates[k].append(str(getdate(r.operation_date)))

	owned = stype != "مورد"

	data_rows = []
	grand = {
		"days": 0,
		"hours": 0.0,
		"stopped": 0.0,
		"amount": 0.0,
		"add": 0.0,
		"ded": 0.0,
		"net": 0.0,
		"eq": set(),
	}

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
			"stopped_hours": 0.0,
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
			stopped = 0.0
			amount = 0.0
			add = 0.0
			ded = 0.0
			rates = set()
			rtypes = set()
			bases = set()
			card_rows = []
			for c in be["cards"]:
				cd = card_dates.get(c.name) or []
				for d in cd:
					dates.add(d)
				w = work.get(c.name) if work is not None else None
				c_amount = 0 if owned else flt(w["amount"] if w else c.amount, 2)
				c_add, c_ded = sided.get(c.name, (0.0, 0.0))
				c_net = 0 if owned else flt(c_amount + c_add - c_ded, 2)
				c_hours = w["hours"] if w else flt(c.total_working_hours)
				c_stopped = w["stopped"] if w else side_stopped_hours(c, "Supplier")
				hours = hours + c_hours
				stopped = stopped + c_stopped
				amount = amount + c_amount
				# FR-118: the card's amount over every billed hour (operating + billable stopped); with no
				# billable stop this is the earlier amount / operating hours, unchanged
				if owned or not (c_hours + c_stopped):
					c_hourly = None
				else:
					c_hourly = flt(c_amount / (c_hours + c_stopped), 2)
				add = add + c_add
				ded = ded + c_ded
				rates.add(flt(c.rate))
				rtypes.add(c.rate_type or "")
				# FR-138: the day billing basis of a per-day rate: a submitted card shows the basis it was
				# priced with, a draft the equipment's current one (a card saved before FR-138: prorated)
				if c.rate_type == PER_DAY:
					c_basis = day_billing_basis(
						c.day_billing_basis_used
						if c.docstatus == 1 and c.day_billing_basis_used
						else c.day_billing_basis
					)
				else:
					c_basis = None
				bases.add(c_basis)
				card_rows.append(
					{
						"row_id": e_id + "|C|" + c.name,
						"parent_row": e_id,
						"indent": 2,
						"label": c.name
						+ (" " + _("(Draft)") if c.docstatus == 0 else "")
						+ provisional_suffix(c),
						"card": c.name,
						"equipment": c.equipment,
						"project": c.project,
						"shift": c.shift,
						"first_date": min(cd) if cd else None,
						"last_date": max(cd) if cd else None,
						"working_days": len(set(cd)),
						"hours": c_hours,
						"stopped_hours": c_stopped,
						"rate_type": c.rate_type,
						"day_billing_basis": None if owned or not c_basis else _(c_basis),
						"rate": None if owned else flt(c.rate),
						"hourly_rate": c_hourly,
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
				"stopped_hours": flt(stopped, 2),
				"rate_type": next(iter(rtypes)) if len(rtypes) == 1 else "متعدد",
				"day_billing_basis": None
				if owned or not any(bases)
				else (_(next(iter(bases))) if len(bases) == 1 else "متعدد"),
				"rate": None if owned else (next(iter(rates)) if len(rates) == 1 else None),
				"hourly_rate": None if owned or not (hours + stopped) else flt(amount / (hours + stopped), 2),
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
			p_row["stopped_hours"] = flt(p_row["stopped_hours"] + stopped, 2)
			p_row["amount"] = flt(p_row["amount"] + amount, 2)
			p_row["additions"] = flt(p_row["additions"] + add, 2)
			p_row["deductions"] = flt(p_row["deductions"] + ded, 2)
			p_row["net"] = flt(p_row["net"] + net, 2)
			grand["eq"].add(e)
		grand["days"] = grand["days"] + p_row["working_days"]
		grand["hours"] = grand["hours"] + p_row["hours"]
		grand["stopped"] = grand["stopped"] + p_row["stopped_hours"]
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
				"stopped_hours": flt(grand["stopped"], 2),
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
			{
				"fieldname": "day_billing_basis",
				"label": _("Day billing basis"),
				"fieldtype": "Data",
				"width": 110,
			},
			{"fieldname": "rate", "label": _("Rate"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "hourly_rate", "label": _("Hourly rate"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "amount", "label": _("Operating amount"), "fieldtype": "Currency", "width": 120},
			{"fieldname": "additions", "label": _("Additions"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "deductions", "label": _("Deductions"), "fieldtype": "Currency", "width": 100},
			{"fieldname": "net", "label": _("Net"), "fieldtype": "Currency", "width": 120},
		]

	summary = [
		{
			"key": "equipment",
			"label": _("Number of equipment"),
			"value": len(grand["eq"]),
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"key": "days",
			"label": _("Operating days"),
			"value": grand["days"],
			"datatype": "Int",
			"indicator": "Blue",
		},
		{
			"key": "hours",
			"label": _("Operating hours"),
			"value": flt(grand["hours"], 2),
			"datatype": "Float",
			"indicator": "Blue",
		},
	]

	message = None
	if no_supplier:
		message = _("Select a supplier to display the statement.")
	elif period and not owned:
		summary, message, payment_rows = range_balance(
			summary,
			grand,
			show_ledger,
			_company,
			supplier,
			start,
			end,
			filters,
			base_filters,
			eq_type,
		)
		data_rows.extend(payment_rows)
		message = _prefix + message
	elif not owned and not show_ledger:
		summary = [
			*summary,
			{
				"key": "net_cards",
				"label": _("Net cards"),
				"value": flt(grand["net"], 2),
				"datatype": "Currency",
				"indicator": "Green",
			},
		]
		message = (
			_prefix
			+ _("Equipment supplier statement: {0} — Period from {1} to {2} — Issue date {3}.").format(
				supplier, start, end, frappe.utils.nowdate()
			)
			+ " "
			+ ledger_notice()
		)
	elif not owned:
		# FR-176 (Owner 2026-11-22): an equipment / project filter applies the date-range statement's rules to the
		# ledger lines too; without these filters the lines stay the whole supplier's, as before
		scoped_ledger = None
		if filters.get("equipment") or filters.get("project"):
			scoped_ledger = scoped_month_ledger(
				_company, supplier, start, end, filters.get("equipment"), filters.get("project")
			)
			opening = scoped_ledger["opening"]
			accrued = scoped_ledger["accrued"]
			paid = scoped_ledger["paid"]
		else:
			# supplier GL: credit = accrual (liability up), debit = payment (liability down)
			gl_open = frappe.get_all(
				"GL Entry",
				filters=[
					["company", "=", _company],
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
					["company", "=", _company],
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
		# rounded from the rounded parts so the printed opening + charges - payments = closing to the cent
		closing = flt(opening, 2) + flt(accrued, 2) - flt(paid, 2)
		# like-for-like: card nets are before VAT; the accrual credits include it
		inv = flt(
			cards_invoiced("Supplier", [supplier], _company, start, end, cards=[c.name for c in cards]).get(
				supplier
			),
			2,
		)
		diff = flt(grand["net"] - inv, 2)
		outside = flt(invoices_outside_card("Supplier", [supplier], _company, start, end).get(supplier), 2)
		summary = [
			*summary,
			{
				"key": "net_cards",
				"label": _("Net cards"),
				"value": flt(grand["net"], 2),
				"datatype": "Currency",
				"indicator": "Green",
			},
			{
				"key": "accrued",
				"label": _("Accrual entries (Credit)"),
				"value": flt(accrued, 2),
				"datatype": "Currency",
				"indicator": "Blue",
			},
			{
				"key": "invoiced",
				"label": _("Invoiced through Card (net before VAT)"),
				"value": inv,
				"datatype": "Currency",
				"indicator": "Blue",
			},
			{
				"key": "not_invoiced",
				"label": _("Not invoiced through Card"),
				"value": diff,
				"datatype": "Currency",
				"indicator": "Green" if abs(diff) < flt(setting("reconciliation_tolerance")) else "Red",
			},
			{
				"key": "outside",
				"label": _("ERPNext invoices outside Card — to reconcile (net before VAT)"),
				"value": outside,
				"datatype": "Currency",
				"indicator": "Orange" if outside else "Green",
			},
			{
				"key": "opening",
				"label": _("Opening balance"),
				"value": flt(opening, 2),
				"datatype": "Currency",
				"indicator": "Grey",
			},
			{
				"key": "paid",
				"label": _("Paid (Debit)"),
				"value": flt(paid, 2),
				"datatype": "Currency",
				"indicator": "Orange",
			},
			{
				"key": "closing",
				"label": _("Supplier closing balance"),
				"value": flt(closing, 2),
				"datatype": "Currency",
				"indicator": "Red" if closing > 0 else "Green",
			},
		]
		month_notes = []
		if scoped_ledger is not None:
			if scoped_ledger["unallocated_paid"]:
				summary.append(
					{
						"key": "unallocated_paid",
						"label": unallocated_paid_label(filters),
						"value": scoped_ledger["unallocated_paid"],
						"datatype": "Currency",
						"indicator": "Orange",
					}
				)
			if scoped_ledger["unallocated_other"]:
				summary.append(
					{
						"key": "unallocated_other",
						"label": _("Other supplier credits without the equipment or project (not added)"),
						"value": scoped_ledger["unallocated_other"],
						"datatype": "Currency",
						"indicator": "Grey",
					}
				)
			month_notes.append(scoped_ledger_note(scoped_ledger["dimension_missing"], filters))
		message = (
			_prefix
			+ _(
				"Equipment supplier statement: {0} — Period from {1} to {2} — Issue date {3}. Balance from accounting entries only (VAT included)."
			).format(supplier, start, end, frappe.utils.nowdate())
			+ " "
			+ reconciliation_notice()
			+ "".join(" " + note for note in month_notes)
		)
	else:
		message = _prefix + _(
			"Operating owned equipment by project — Period from {0} to {1} — Hours only until internal rates are defined."
		).format(start, end)

	# #295 (Owner decision 2026-11-24, option A): a user whose roles do not read the Monthly Card money level
	# (permlevel 1) gets no figure derived from card amounts (see strip_card_money)
	if not role_reads_money():
		columns, summary = strip_card_money(columns, data_rows, summary)

	columns = readable_links(with_stopped_hours_column(columns, data_rows), data_rows)
	data = [columns, data_rows, message, None, summary, True]
	return data


# #295: the card-money values of the statement rows and the summary items computed from card amounts
CARD_MONEY_ROW_KEYS = ("rate", "hourly_rate", "amount", "additions", "deductions", "net")
CARD_MONEY_SUMMARY_KEYS = ("net_cards", "not_invoiced", "period_net", "previous_due", "current_due")


def strip_card_money(columns, rows, summary):
	"""#295 (option A): remove every value derived from card amounts, so it never reaches the browser.

	- Card, equipment, project and total rows lose their rate, amount, additions, deductions and net.
	- Payment rows (date-range statement) are accounting entries (gate: can_view_ledger). Their amount moves to its
	  own "Payment amount" column; the Net column goes, so the prints use the hours layout (they pick the money
	  layout by the Net column) and still list the payments with their amounts.
	- Summary items built on card amounts go: net cards, not invoiced through Card, and in the date-range statement
	  the net work, the balance carried from before the period and the current due (both add card work). The pure
	  accounting items (VAT, other credits, payments, GL balances, invoices) stay under can_view_ledger."""
	has_payments = False
	for row in rows or ():
		if row.get("payment"):
			has_payments = True
			row["payment_amount"] = row.get("net")
			continue
		for key in CARD_MONEY_ROW_KEYS:
			row.pop(key, None)
	columns = [c for c in columns if c.get("fieldname") not in CARD_MONEY_ROW_KEYS]
	if has_payments:
		columns.append(
			{
				"fieldname": "payment_amount",
				"label": _("Payment amount"),
				"fieldtype": "Currency",
				"width": 120,
			}
		)
	summary = [t for t in summary or () if t.get("key") not in CARD_MONEY_SUMMARY_KEYS]
	return columns, summary


def range_balance(summary, grand, show_ledger, company, supplier, start, end, filters, base_filters, eq_type):
	"""Summary, message and payment rows of a supplier statement for a date range (Owner 2026-11-22).

	The balance rule and its double-count guard are documented in statement_period. Card work follows the
	report's filters; the ledger side (payments, VAT, other credits) follows the equipment / project filter through
	the entries' Card Equipment dimension and project (FR-176), and is the whole supplier's otherwise."""
	flt = frappe.utils.flt
	period_net = flt(grand["net"], 2)
	summary = [
		*summary,
		{
			"key": "period_net",
			"label": _("Net work for the period"),
			"value": period_net,
			"datatype": "Currency",
			"indicator": "Green",
		},
	]
	head = _("Equipment supplier statement: {0} — Period from {1} to {2} — Issue date {3}.").format(
		supplier, start, end, frappe.utils.nowdate()
	)
	if not show_ledger:
		return summary, head + " " + ledger_notice(), []

	before_cards = frappe.get_all(
		"Card Monthly Card",
		filters=[*base_filters, ["from_date", "<", start]],
		fields=[
			"name",
			"equipment",
			"rate_type",
			"rate",
			"day_billing_basis",
			"day_billing_basis_used",
			"daily_hours_used",
			"hourly_rate_used",
			"card_direction",
			"amount",
			"docstatus",
			"workflow_state",
			"from_date",
			"to_date",
		],
		limit_page_length=0,
	)
	if filters.get("equipment_type"):
		types = dict(eq_type)
		missing = list({c.equipment for c in before_cards if c.equipment not in types})
		if missing:
			for e in frappe.get_all(
				"Card Equipment",
				filters=[["name", "in", missing]],
				fields=["name", "equipment_type"],
				limit_page_length=0,
			):
				types[e.name] = e.equipment_type or ""
		before_cards = [c for c in before_cards if types.get(c.equipment) == filters.get("equipment_type")]

	# FR-176: with an equipment/project filter the ledger side follows the entries' equipment dimension / project
	ledger = supplier_ledger(
		company, supplier, start, end, equipment=filters.get("equipment"), project=filters.get("project")
	)
	before, period = ledger["before"], ledger["period"]
	previous_due = flt(
		previous_work(before_cards, start) + before["vat"] + before["other"] - before["paid"], 2
	)
	current_due = flt(previous_due + period_net + period["vat"] + period["other"] - period["paid"], 2)

	items = [
		("previous_due", _("Balance carried from before the period"), previous_due, "Grey"),
		("period_vat", _("VAT on CARD purchase invoices"), period["vat"], "Blue"),
		("period_other", _("Other supplier credits (outside CARD)"), period["other"], "Orange"),
		("period_paid", _("Payments in the period (submitted entries only)"), period["paid"], "Orange"),
		("current_due", _("Current due to the supplier"), current_due, "Red" if current_due > 0 else "Green"),
	]
	# FR-176: untagged supplier entries never change an equipment/project balance; shown apart, not counted
	scoped = filters.get("equipment") or filters.get("project")
	if scoped and ledger["unallocated_paid"]:
		items.append(
			("unallocated_paid", unallocated_paid_label(filters), ledger["unallocated_paid"], "Orange")
		)
	if scoped and ledger["unallocated_other"]:
		items.append(
			(
				"unallocated_other",
				_("Other supplier credits without the equipment or project (not added)"),
				ledger["unallocated_other"],
				"Grey",
			)
		)
	if scoped and ledger["unallocated_vat"]:
		items.append(
			(
				"unallocated_vat",
				_("VAT of CARD invoice lines without the equipment or project (not added)"),
				ledger["unallocated_vat"],
				"Grey",
			)
		)
	for key, label, value, indicator in items:
		summary.append(
			{"key": key, "label": label, "value": value, "datatype": "Currency", "indicator": indicator}
		)

	rows = []
	if ledger["payments"]:
		rows.append(
			{
				"row_id": PAYMENTS_ROW,
				"parent_row": None,
				"indent": 0,
				"label": _("Payments in the period"),
				"net": period["paid"],
				"payment": 1,
				"bold": 1,
			}
		)
		for i, p in enumerate(ledger["payments"]):
			remark = (p["remarks"] or "").strip()
			if len(remark) > 120:
				remark = remark[:117] + "..."
			rows.append(
				{
					"row_id": PAYMENTS_ROW + "|" + str(i),
					"parent_row": PAYMENTS_ROW,
					"indent": 1,
					# the work columns do not fit a payment: its date leads the label on screen
					"label": frappe.utils.formatdate(p["posting_date"])
					+ " — "
					+ p["voucher_no"]
					+ (" — " + remark if remark else ""),
					"voucher_type": p["voucher_type"],
					"voucher_no": p["voucher_no"],
					"remarks": remark,
					"posting_date": p["posting_date"],
					"net": p["amount"],
					"payment": 1,
				}
			)

	notes = [_("Payments are submitted accounting entries only; draft journal entries are not counted.")]
	# a supplier invoice booked outside CARD is an "other credit"; when it bills card work too, the
	# accountant reconciles it (the month statement's check, kept for the range)
	outside = flt(invoices_outside_card("Supplier", [supplier], company, start, end).get(supplier), 2)
	if outside:
		summary.append(
			{
				"key": "outside",
				"label": _("ERPNext invoices outside Card — to reconcile (net before VAT)"),
				"value": outside,
				"datatype": "Currency",
				"indicator": "Orange",
			}
		)
		notes.append(reconciliation_notice())
	if filters.get("project") or filters.get("equipment"):
		notes.append(scoped_ledger_note(ledger["dimension_missing"], filters))
	elif filters.get("equipment_type"):
		notes.append(
			_("The work follows the filters; payments, VAT and other credits are for the whole supplier.")
		)
	return summary, head + " " + " ".join(notes), rows


def unallocated_paid_label(filters):
	"""FR-176: the warning line of the supplier payments that carry no selected equipment / project."""
	if filters.get("equipment") and filters.get("project"):
		return _("Payments without the selected equipment and project (not deducted)")
	if filters.get("equipment"):
		return _("Payments not allocated to an equipment (not deducted)")
	return _("Payments not allocated to a project (not deducted)")


def scoped_ledger_note(dimension_missing, filters):
	"""FR-176: the statement note of an equipment / project filter (both statement modes)."""
	note = _(
		"Payments, VAT and other credits count only when their accounting entry carries the selected equipment or project; entries without one are shown apart and not counted."
	)
	if dimension_missing and not filters.get("project"):
		# no scope applies: the ledger lines are the whole supplier's
		return _(
			"The Card Equipment accounting dimension is missing on this site: payments, VAT and other credits are not split by equipment."
		)
	if dimension_missing:
		note = (
			_(
				"The Card Equipment accounting dimension is missing on this site: payments, VAT and other credits are not split by equipment."
			)
			+ " "
			+ note
		)
	return note
