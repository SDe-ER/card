import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from card.diesel_reconciliation import (
	AMOUNT_GROSS,
	AMOUNT_NET,
	DOCTYPES,
	EQUAL,
	FOLDED,
	LINKED,
	assert_report_access,
	invoice_figures,
	load,
	reconcile,
	vat_basis,
)
from card.report_access import readable_links, resolve_company


def get_columns():
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 230},
		{"fieldname": "confidence", "label": _("Match confidence"), "fieldtype": "Data", "width": 230},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Data", "width": 180},
		{"fieldname": "sessions", "label": _("Diesel sessions"), "fieldtype": "Data", "width": 170},
		{"fieldname": "session_state", "label": _("Session state"), "fieldtype": "Data", "width": 150},
		{"fieldname": "session_litres", "label": _("Session litres"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "invoice",
			"label": _("Purchase Invoice"),
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 170,
		},
		{"fieldname": "bill_no", "label": _("Supplier invoice no."), "fieldtype": "Data", "width": 120},
		{
			"fieldname": "invoice_litres",
			"label": _("Invoiced diesel litres"),
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname": "physical_litres",
			"label": _("Physical diesel litres"),
			"fieldtype": "Float",
			"width": 120,
		},
		{
			"fieldname": "delivery_litres",
			"label": _("Delivery charge litres"),
			"fieldtype": "Float",
			"width": 110,
		},
		{"fieldname": "litre_difference", "label": _("Litre difference"), "fieldtype": "Float", "width": 110},
		{"fieldname": "grand_total", "label": _("Invoice gross"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "net_total", "label": _("Invoice net"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "vat", "label": _("VAT"), "fieldtype": "Currency", "width": 100},
		{"fieldname": "vat_pct", "label": _("VAT %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "vat_basis", "label": _("Price VAT basis"), "fieldtype": "Data", "width": 200},
		{"fieldname": "session_projects", "label": _("Session projects"), "fieldtype": "Data", "width": 160},
		{"fieldname": "invoice_projects", "label": _("Invoice projects"), "fieldtype": "Data", "width": 160},
		{"fieldname": "allocation", "label": _("Allocation check"), "fieldtype": "Data", "width": 200},
		{"fieldname": "note", "label": _("Evidence"), "fieldtype": "Data", "width": 360},
	]


def execute(filters=None):
	# Report: "Diesel Invoice Reconciliation" (P1-1). Read-only: compares CARD diesel sessions with the
	# suppliers' own Purchase Invoices; it creates, changes or links nothing. A difference it shows is a
	# point to review, never a confirmed over-billing, missing invoice or missing payment. Amounts are in the
	# company currency.
	filters = frappe._dict(filters or {})
	assert_report_access()
	filters.company = resolve_company(filters, *DOCTYPES)
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Select the period"))
	if getdate(filters.to_date) < getdate(filters.from_date):
		frappe.throw(_("Invalid period: end is before start"))
	window = max(
		0, cint(filters.get("date_window_days")) if filters.get("date_window_days") is not None else 3
	)
	max_delivery = max(
		0, flt(filters.get("max_delivery_litres")) if filters.get("max_delivery_litres") is not None else 60
	)
	submitted_only = filters.get("session_status") == "Submitted only"
	suppliers = (
		frappe.parse_json(filters.get("suppliers"))
		if isinstance(filters.get("suppliers"), str)
		else filters.get("suppliers")
	)
	suppliers = [s for s in (suppliers or []) if s]
	if suppliers:
		# the selected suppliers are one delivery stream (one delegate, combined invoices)
		streams = [suppliers]
	else:
		found = frappe.get_list(
			"Project Diesel Fill",
			filters={
				"company": filters.company,
				"docstatus": ["<", 2],
				"date": ["between", [filters.from_date, filters.to_date]],
			},
			pluck="supplier",
			distinct=True,
			limit_page_length=0,
		)
		streams = [[s] for s in sorted(set(found)) if s]

	rows = []
	for stream in streams:
		rows.extend(_stream_rows(filters, stream, window, max_delivery, submitted_only))
	columns = get_columns()
	columns = readable_links(columns, rows)
	return columns, rows, None, None, _summary(rows)


def _rule_label(rule, detail):
	return {
		LINKED: _("Linked: the session names this invoice"),
		EQUAL: _("Litres equal"),
		FOLDED: _("Invoice litres = session + {0} L delivery charge inside the diesel line").format(detail),
		AMOUNT_GROSS: _("Amount only: gross / session price = {0} L").format(detail),
		AMOUNT_NET: _("Amount only: net / session price = {0} L").format(detail),
	}.get(rule, "")


def _stream_rows(filters, stream, window, max_delivery, submitted_only):
	sessions, invoices, lines, taxes = load(
		filters.company, stream, filters.from_date, filters.to_date, window, submitted_only
	)
	by_name = {s.name: s for s in sessions}
	figures = {i.name: invoice_figures(i, lines[i.name], taxes[i.name]) for i in invoices}
	session_match, invoice_sessions, periods = reconcile(sessions, invoices, figures, window, max_delivery)
	period_of = {inv: (taken, start) for inv, taken, start in periods}
	period_end = getdate(filters.to_date)
	rows = []
	for inv in invoices:
		fig = figures[inv.name]
		bill_date = getdate(inv.bill_date or inv.posting_date)
		taken = [by_name[n] for n in invoice_sessions.get(inv.name, [])]
		s_litres = flt(sum(flt(s.litres) for s in taken), 3)
		# the price of this invoice's own sessions, else the latest session up to its date
		near = taken or [s for s in sessions if getdate(s.date) <= bill_date] or sessions
		inv_price = flt(near[-1].unit_price) if near else 0
		inv_litres = fig.diesel_litres
		estimate = inv_litres is None and inv_price
		if estimate:
			inv_litres = flt(fig.gross / inv_price - fig.delivery_litres, 1)
		delivery = fig.delivery_litres  # a separate delivery-charge line, in litre-equivalent
		physical = inv_litres
		notes = []
		if inv.name in period_of:
			start = period_of[inv.name][1]
			diff = flt((inv_litres or 0) - s_litres, 1)
			tolerance = max(1.0, 0.005 * s_litres)
			agree = abs(diff) <= tolerance
			status = (
				_("Period: litres agree")
				if agree
				else (
					_("Period: difference to review (invoice above sessions)")
					if diff > 0
					else _("Period: difference to review (sessions above invoice)")
				)
			)
			confidence = (
				_("Estimated: period match, litres estimated from the amount")
				if estimate
				else _("Estimated: period match on stated litres")
			)
			exception = not agree
			notes.append(
				_("Aggregated invoice: sessions after {0} up to the bill date").format(
					start or _("the start of the period")
				)
			)
			if start is None:
				notes.append(_("The first invoice of the period may include deliveries before the period"))
			if not agree:
				notes.append(
					_(
						"Unexplained difference: not a confirmed over-billing, missing invoice or missing payment"
					)
				)
		elif taken:
			_inv, rule, detail = session_match[taken[0].name]
			diff = flt((inv_litres or 0) - s_litres, 1) if inv_litres is not None else None
			exception = False
			status = _("Matched") if rule == EQUAL else _("Matched: {0}").format(_rule_label(rule, detail))
			if rule == LINKED:
				confidence = _("Confirmed: linked in CARD")
			elif rule == EQUAL:
				confidence = _("Confirmed: stated litres equal the session")
			elif rule == FOLDED:
				# the delivery charge is folded into the diesel line: physical diesel = the session
				confidence = _("Confirmed: stated litres = session + delivery charge")
				delivery = flt(delivery + detail, 1)
				physical = s_litres
				notes.append(
					_(
						"Physical diesel = session litres; the difference is a delivery charge booked as diesel"
					)
				)
			else:
				confidence = _("Estimated: amount only, the invoice states no litres")
			if any(s.docstatus != 1 for s in taken):
				confidence = _("{0} (draft session, not yet approved)").format(confidence)
		elif bill_date > period_end:
			status, diff, exception = _("After the period end: to review with the next period"), None, False
			confidence = _("No match")
		else:
			status, diff, exception = _("Invoice without session"), None, True
			confidence = _("No match")
		if estimate:
			notes.append(
				_("Invoice states no litres: estimated as gross / session price {0} (unverified)").format(
					inv_price
				)
			)
		if fig.delivery_amount:
			notes.append(_("Separate delivery charge line {0}").format(fig.delivery_amount))
		if fig.other_amount:
			notes.append(_("Other lines (not diesel) {0}").format(fig.other_amount))
		if fig.lines_without_project:
			notes.append(_("{0} invoice line(s) without project").format(fig.lines_without_project))
		notes.append(_("VAT as booked on the invoice"))
		rows.append(
			{
				"status": status,
				"confidence": confidence,
				"date": bill_date,
				"supplier": inv.supplier,
				"sessions": _sessions_label(taken),
				"session_state": _session_state(taken),
				"session_litres": s_litres,
				"invoice": inv.name,
				"bill_no": (inv.bill_no or "").strip(),
				"invoice_litres": inv_litres,
				"physical_litres": physical,
				"delivery_litres": delivery,
				"litre_difference": diff,
				"grand_total": fig.gross,
				"net_total": fig.net,
				"vat": fig.vat,
				"vat_pct": fig.vat_pct,
				"vat_basis": vat_basis(fig, inv_price),
				"session_projects": _projects(taken),
				"invoice_projects": ", ".join(fig.projects) or _("none"),
				"allocation": _allocation(taken, fig),
				"note": "; ".join(notes),
				"exception": int(exception),
				"estimated": int(bool(estimate)),
				"submitted_litres": flt(sum(flt(s.litres) for s in taken if s.docstatus == 1), 3),
			}
		)
	last = max((getdate(i.bill_date or i.posting_date) for i in invoices), default=None)
	for s in sessions:
		if s.name in session_match:
			continue
		late = last is None or getdate(s.date) > last
		rows.append(
			{
				"status": _("Not invoiced yet") if late else _("Session without invoice"),
				"confidence": _("No match"),
				"date": s.date,
				"supplier": s.supplier,
				"sessions": s.name,
				"session_state": _session_state([s]),
				"session_litres": flt(s.litres, 3),
				"session_projects": s.project,
				"note": _draft_note(s),
				"exception": 0 if late else 1,
				"submitted_litres": flt(s.litres, 3) if s.docstatus == 1 else 0,
			}
		)
	return rows


def _draft_note(session):
	"""A draft session's review state; a plain "Draft" state needs no repetition."""
	if session.docstatus:
		return ""
	if session.review_status in (None, "", "Draft"):
		return _("Draft session")
	return _("Draft session ({0})").format(_(session.review_status))


def _sessions_label(sessions):
	if len(sessions) <= 3:
		return ", ".join(s.name for s in sessions)
	return _("{0} sessions ({1} .. {2})").format(len(sessions), sessions[0].name, sessions[-1].name)


def _session_state(sessions):
	if not sessions:
		return ""
	submitted = sum(1 for s in sessions if s.docstatus == 1)
	return _("Submitted {0}, draft {1}").format(submitted, len(sessions) - submitted)


def _projects(sessions):
	litres = {}
	for s in sessions:
		litres[s.project] = litres.get(s.project, 0) + flt(s.litres)
	total = sum(litres.values()) or 1
	return ", ".join(
		f"{p} {flt(100 * v / total, 1)}%" for p, v in sorted(litres.items(), key=lambda x: -x[1])
	)


def _allocation(sessions, fig):
	"""Project/equipment allocation of the invoice lines against the matched sessions. Reported only:
	nothing is reallocated."""
	if not sessions:
		return ""
	found = []
	s_projects = {s.project for s in sessions if s.project}
	if fig.lines_without_project and not fig.projects:
		found.append(_("Invoice has no project"))
	elif fig.projects and s_projects and set(fig.projects) != s_projects:
		found.append(_("Project conflict"))
	s_equipment = {s.card_equipment for s in sessions if s.get("card_equipment")}
	if fig.equipment and s_equipment and set(fig.equipment) != s_equipment:
		found.append(_("Equipment conflict"))
	return ", ".join(found) or _("Consistent")


def _summary(rows):
	session_rows = [r for r in rows if r.get("sessions")]
	invoices = [r for r in rows if r.get("invoice")]
	exceptions = [r for r in rows if r.get("exception")]
	all_litres = flt(sum(flt(r.get("session_litres")) for r in session_rows), 1)
	submitted = flt(sum(flt(r.get("submitted_litres")) for r in session_rows), 1)
	return [
		{"label": _("Submitted session litres"), "value": submitted, "datatype": "Float"},
		{"label": _("Draft session litres"), "value": flt(all_litres - submitted, 1), "datatype": "Float"},
		{
			"label": _("Invoiced physical diesel litres (stated)"),
			"value": flt(sum(flt(r.get("physical_litres")) for r in invoices if not r.get("estimated")), 1),
			"datatype": "Float",
		},
		{
			"label": _("Invoiced litres estimated from amounts"),
			"value": flt(sum(flt(r.get("invoice_litres")) for r in invoices if r.get("estimated")), 1),
			"datatype": "Float",
		},
		{"label": _("Invoices"), "value": len(invoices), "datatype": "Int"},
		{
			"label": _("Exceptions"),
			"value": len(exceptions),
			"datatype": "Int",
			"indicator": "Red" if exceptions else "Green",
		},
	]
