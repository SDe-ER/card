import frappe
from frappe import _

from card.adjustments import sided_adjustments
from card.card.doctype.card_stop_reason.card_stop_reason import side_stopped_hours
from card.card_value import DAY_BASIS_FULL_DAY, PER_DAY, PER_VOLUME_M3, day_billing_basis
from card.constants import CUSTOMER_BILLING_DIRECTIONS
from card.reconciliation import cards_invoiced, invoices_outside_card, reconciliation_notice
from card.report_access import can_view_ledger, ledger_notice, readable_links, resolve_company
from card.report_currency import company_currency_report
from card.settings import setting
from card.transfer import billed_day_rows, with_stopped_hours_column


@company_currency_report()
def execute(filters=None):
	filters = frappe._dict(filters or {})
	# Report: "Equipment Customer Statement" (Script Report, standard, ref doctype: Card Monthly Card)
	# Read-only. Groups customer-billing monthly cards (rented-out + sub-rental) by Project > Equipment > Card
	# for one customer, and reconciles the accrued customer amount with the customer's official AR
	# (GL Entry on the Customer party: debit = invoiced, credit = received).
	# Customer-side mirror of "Equipment Supplier Statement": CARD stores no customer balance, so every money
	# number below comes from GL Entry only (zero until Sales Invoices are posted).
	# Server Script rules: no "+=", no leading underscores, no nested def (exec locals are not visible inside functions).

	flt = frappe.utils.flt
	cint = frappe.utils.cint
	getdate = frappe.utils.getdate

	customer = filters.get("customer")
	no_customer = not customer
	company = resolve_company(filters)
	prefix = company + " — "
	show_ledger = can_view_ledger(company)

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
		["company", "=", company],
		["from_date", ">=", start],
		["from_date", "<=", end],
		["docstatus", "in", statuses],
		["card_direction", "in", list(CUSTOMER_BILLING_DIRECTIONS)],
	]
	if customer:
		cf.append(["customer", "=", customer])
	if filters.get("project"):
		cf.append(["project", "=", filters.get("project")])
	if filters.get("equipment"):
		cf.append(["equipment", "=", filters.get("equipment")])

	cards = (
		[]
		if no_customer
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
				"customer_rate_type",
				"customer_rate",
				"customer_rate_used",
				"total_loads",
				"total_volume_m3",
				"day_billing_basis",
				"day_billing_basis_used",
				"customer_amount",
				"total_working_hours",
				"billable_stopped_hours",
				"supplier_billable_stopped_hours",
				"customer_billable_stopped_hours",
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

	# customer-side additions/deductions: the Sales Invoice bills the customer net
	sided = sided_adjustments([c.name for c in cards], "Customer")

	# operating dates per card (hours > 0) -> distinct days per equipment, first/last date
	card_dates = {}
	if cards:
		# FR-118: a day bills with operating hours or billable stopped hours (is_billed_day)
		rows = billed_day_rows([c.name for c in cards], include_loads=True)
		for r in rows:
			k = r.parent
			if k not in card_dates:
				card_dates[k] = []
			card_dates[k].append(str(getdate(r.operation_date)))

	data_rows = []
	grand = {
		"days": 0,
		"loads": None,
		"volume": None,
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
			"customer_amount": 0.0,
			"total_loads": None,
			"total_volume_m3": None,
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
			# FR-166: loads and m³ of the per-m³ cards only (a per-m³ row shows no hourly rate)
			loads = 0
			volume = 0.0
			bases = set()
			card_rows = []
			for c in be["cards"]:
				cd = card_dates.get(c.name) or []
				for d in cd:
					dates.add(d)
				c_hours = flt(c.total_working_hours)
				c_stopped = side_stopped_hours(c, "Customer")
				c_amount = flt(c.customer_amount, 2)
				c_add, c_ded = sided.get(c.name, (0.0, 0.0))
				hours = hours + c_hours
				stopped = stopped + c_stopped
				amount = amount + c_amount
				add = add + c_add
				ded = ded + c_ded
				rates.add(flt(c.customer_rate))
				if c.customer_rate_type == PER_VOLUME_M3:
					loads = loads + cint(c.total_loads)
					volume = volume + flt(c.total_volume_m3)
				rtypes.add(c.customer_rate_type or "")
				# FR-138: the day billing basis of a per-day customer rate: a submitted card shows the basis it
				# was priced with, a draft the equipment's current one (a card saved before FR-138: prorated)
				if c.customer_rate_type == PER_DAY:
					c_basis = day_billing_basis(
						c.day_billing_basis_used
						if c.docstatus == 1 and c.day_billing_basis_used
						else c.day_billing_basis
					)
				else:
					c_basis = None
				bases.add(c_basis)
				# submitted cards carry the hourly-rate snapshot taken at submit; a draft has none yet,
				# so its effective hourly rate is derived from the accrued amount (same value, any rate type).
				# FR-138: a "Full day" card was not priced by an hourly rate, so (as on the supplier
				# statement) its effective rate is its amount over every billed hour
				if c.customer_rate_type == PER_VOLUME_M3:
					# FR-166: a per-m³ card has no hourly rate; its customer rate is SAR per m³
					c_hourly = None
				elif c.docstatus == 1 and flt(c.customer_rate_used) and c_basis != DAY_BASIS_FULL_DAY:
					c_hourly = flt(c.customer_rate_used)
				elif c_hours + c_stopped:
					# FR-118: billable stopped hours are billed hours too
					c_hourly = flt(c_amount / (c_hours + c_stopped), 2)
				else:
					c_hourly = None
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
						"period": str(cint(c.year)) + "-" + str(c.month).zfill(2),
						"first_date": min(cd) if cd else None,
						"last_date": max(cd) if cd else None,
						"working_days": len(set(cd)),
						"hours": c_hours,
						"stopped_hours": c_stopped,
						"customer_rate_type": c.customer_rate_type,
						"day_billing_basis": _(c_basis) if c_basis else None,
						"customer_rate": flt(c.customer_rate),
						"total_loads": cint(c.total_loads) if c.customer_rate_type == PER_VOLUME_M3 else None,
						"total_volume_m3": flt(c.total_volume_m3)
						if c.customer_rate_type == PER_VOLUME_M3
						else None,
						"hourly_rate": c_hourly,
						"customer_amount": c_amount,
						"additions": c_add,
						"deductions": c_ded,
						"net": flt(c_amount + c_add - c_ded, 2),
					}
				)
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
				"customer_rate_type": next(iter(rtypes)) if len(rtypes) == 1 else "متعدد",
				"day_billing_basis": None
				if not any(bases)
				else (_(next(iter(bases))) if len(bases) == 1 else "متعدد"),
				"customer_rate": next(iter(rates)) if len(rates) == 1 else None,
				"total_loads": loads if PER_VOLUME_M3 in rtypes else None,
				"total_volume_m3": flt(volume, 2) if PER_VOLUME_M3 in rtypes else None,
				# a per-m³ row has no hourly rate (no hours-divided figure either)
				"hourly_rate": None
				if PER_VOLUME_M3 in rtypes or not (hours + stopped)
				else flt(amount / (hours + stopped), 2),
				"customer_amount": flt(amount, 2),
				"additions": flt(add, 2),
				"deductions": flt(ded, 2),
				"net": flt(amount + add - ded, 2),
				"bold": 1,
			}
			data_rows.append(e_row)
			data_rows.extend(card_rows)
			p_row["working_days"] = p_row["working_days"] + len(dates)
			p_row["hours"] = flt(p_row["hours"] + hours, 2)
			p_row["stopped_hours"] = flt(p_row["stopped_hours"] + stopped, 2)
			p_row["customer_amount"] = flt(p_row["customer_amount"] + amount, 2)
			p_row["additions"] = flt(p_row["additions"] + add, 2)
			p_row["deductions"] = flt(p_row["deductions"] + ded, 2)
			p_row["net"] = flt(p_row["net"] + amount + add - ded, 2)
			if PER_VOLUME_M3 in rtypes:
				p_row["total_loads"] = (p_row["total_loads"] or 0) + loads
				p_row["total_volume_m3"] = flt((p_row["total_volume_m3"] or 0) + volume, 2)
				grand["loads"] = (grand["loads"] or 0) + loads
				grand["volume"] = flt((grand["volume"] or 0) + volume, 2)
			grand["eq"].add(e)
		grand["days"] = grand["days"] + p_row["working_days"]
		grand["hours"] = grand["hours"] + p_row["hours"]
		grand["stopped"] = grand["stopped"] + p_row["stopped_hours"]
		grand["amount"] = grand["amount"] + p_row["customer_amount"]
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
				"customer_amount": flt(grand["amount"], 2),
				"additions": flt(grand["add"], 2),
				"deductions": flt(grand["ded"], 2),
				"total_loads": grand["loads"],
				"total_volume_m3": grand["volume"],
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
		{"fieldname": "period", "label": _("Period"), "fieldtype": "Data", "width": 80},
		{"fieldname": "first_date", "label": _("First operation"), "fieldtype": "Date", "width": 100},
		{"fieldname": "last_date", "label": _("Last operation"), "fieldtype": "Date", "width": 100},
		{"fieldname": "working_days", "label": _("Working days"), "fieldtype": "Int", "width": 80},
		{"fieldname": "hours", "label": _("Hours"), "fieldtype": "Float", "precision": 2, "width": 90},
		{
			"fieldname": "customer_rate_type",
			"label": _("Customer rate type"),
			"fieldtype": "Data",
			"width": 90,
		},
		{
			"fieldname": "day_billing_basis",
			"label": _("Day billing basis"),
			"fieldtype": "Data",
			"width": 110,
		},
		{"fieldname": "customer_rate", "label": _("Customer rate"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "total_loads", "label": _("Total loads"), "fieldtype": "Int", "width": 90},
		{
			"fieldname": "total_volume_m3",
			"label": _("Total volume (m³)"),
			"fieldtype": "Float",
			"precision": 2,
			"width": 110,
		},
		{"fieldname": "hourly_rate", "label": _("Hourly rate"), "fieldtype": "Currency", "width": 100},
		{
			"fieldname": "customer_amount",
			"label": _("Customer amount"),
			"fieldtype": "Currency",
			"width": 120,
		},
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
	if no_customer:
		message = _("Select a customer to display the statement.")
	elif not show_ledger:
		summary = [
			*summary,
			{
				"label": _("Total accrued (cards)"),
				"value": flt(grand["net"], 2),
				"datatype": "Currency",
				"indicator": "Green",
			},
		]
		message = (
			prefix
			+ _("Equipment customer statement: {0} — Period from {1} to {2} — Issue date {3}.").format(
				customer, start, end, frappe.utils.nowdate()
			)
			+ " "
			+ ledger_notice()
		)
	else:
		# customer GL (official AR): debit = invoice (receivable up), credit = receipt (receivable down)
		gl_open = frappe.get_all(
			"GL Entry",
			filters=[
				["company", "=", company],
				["party_type", "=", "Customer"],
				["party", "=", customer],
				["is_cancelled", "=", 0],
				["posting_date", "<", start],
			],
			fields=["debit", "credit"],
			limit_page_length=0,
		)
		gl_period = frappe.get_all(
			"GL Entry",
			filters=[
				["company", "=", company],
				["party_type", "=", "Customer"],
				["party", "=", customer],
				["is_cancelled", "=", 0],
				["posting_date", ">=", start],
				["posting_date", "<=", end],
			],
			fields=["debit", "credit"],
			limit_page_length=0,
		)
		opening = 0.0
		for g in gl_open:
			opening = opening + flt(g.debit) - flt(g.credit)
		invoiced = 0.0
		received = 0.0
		for g in gl_period:
			invoiced = invoiced + flt(g.debit)
			received = received + flt(g.credit)
		closing = opening + invoiced - received
		# like-for-like: card nets are before VAT; the invoiced debits include it
		inv = flt(
			cards_invoiced("Customer", [customer], company, start, end, cards=[c.name for c in cards]).get(
				customer
			),
			2,
		)
		diff = flt(grand["net"] - inv, 2)
		outside = flt(invoices_outside_card("Customer", [customer], company, start, end).get(customer), 2)
		summary = [
			*summary,
			{
				"label": _("Total accrued (cards)"),
				"value": flt(grand["net"], 2),
				"datatype": "Currency",
				"indicator": "Green",
			},
			{
				"label": _("Invoiced entries (Debit)"),
				"value": flt(invoiced, 2),
				"datatype": "Currency",
				"indicator": "Blue",
			},
			{
				"label": _("Invoiced through Card (net before VAT)"),
				"value": inv,
				"datatype": "Currency",
				"indicator": "Blue",
			},
			{
				"label": _("Not invoiced through Card"),
				"value": diff,
				"datatype": "Currency",
				"indicator": "Green" if abs(diff) < flt(setting("reconciliation_tolerance")) else "Red",
			},
			{
				"label": _("ERPNext invoices outside Card — to reconcile (net before VAT)"),
				"value": outside,
				"datatype": "Currency",
				"indicator": "Orange" if outside else "Green",
			},
			{
				"label": _("Opening balance"),
				"value": flt(opening, 2),
				"datatype": "Currency",
				"indicator": "Grey",
			},
			{
				"label": _("Received (Credit)"),
				"value": flt(received, 2),
				"datatype": "Currency",
				"indicator": "Orange",
			},
			{
				"label": _("Customer closing balance"),
				"value": flt(closing, 2),
				"datatype": "Currency",
				"indicator": "Orange" if closing > 0 else "Green",
			},
		]
		message = (
			prefix
			+ _(
				"Equipment customer statement: {0} — Period from {1} to {2} — Issue date {3}. Balance from accounting entries only (VAT included)."
			).format(customer, start, end, frappe.utils.nowdate())
			+ " "
			+ reconciliation_notice()
		)

	columns = readable_links(with_stopped_hours_column(columns, data_rows), data_rows)
	data = [columns, data_rows, message, None, summary, True]
	return data
