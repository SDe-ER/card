import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from card.diesel_reconciliation import invoice_figures, load, reconcile, vat_basis
from card.report_access import _role_reads, readable_links, resolve_company

DOCTYPES = ("Project Diesel Fill", "Purchase Invoice")


def get_columns():
	return [
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 230},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "supplier", "label": _("Supplier"), "fieldtype": "Data", "width": 180},
		{"fieldname": "sessions", "label": _("Diesel sessions"), "fieldtype": "Data", "width": 170},
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
		{"fieldname": "note", "label": _("Evidence"), "fieldtype": "Data", "width": 360},
	]


def execute(filters=None):
	# Report: "Diesel Invoice Reconciliation" (P1-1). Read-only: compares CARD diesel sessions with the
	# suppliers' own Purchase Invoices; it creates, changes or links nothing.
	filters = frappe._dict(filters or {})
	for doctype in DOCTYPES:
		if not _role_reads(doctype):
			frappe.throw(
				_("You need read access to {0} to run this report").format(_(doctype)), frappe.PermissionError
			)
	filters.company = resolve_company(filters, *DOCTYPES)
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Select the period"))
	if getdate(filters.to_date) < getdate(filters.from_date):
		frappe.throw(_("Invalid period: end is before start"))
	window = cint(filters.get("date_window_days")) if filters.get("date_window_days") is not None else 3
	max_delivery = (
		flt(filters.get("max_delivery_litres")) if filters.get("max_delivery_litres") is not None else 60
	)
	suppliers = (
		frappe.parse_json(filters.get("suppliers"))
		if isinstance(filters.get("suppliers"), str)
		else filters.get("suppliers")
	)
	suppliers = [s for s in (suppliers or []) if s]
	if suppliers:
		streams = [
			suppliers
		]  # the selected suppliers are one delivery stream (one delegate, combined invoices)
	else:
		found = frappe.get_all(
			"Project Diesel Fill",
			filters={
				"company": filters.company,
				"docstatus": ["<", 2],
				"date": ["between", [filters.from_date, filters.to_date]],
			},
			pluck="supplier",
			distinct=True,
		)
		streams = [[s] for s in sorted(set(found)) if s]

	rows = []
	for stream in streams:
		rows.extend(_stream_rows(filters, stream, window, max_delivery))
	columns = get_columns()
	columns = readable_links(columns, rows)
	return columns, rows, None, None, _summary(rows)


def _stream_rows(filters, stream, window, max_delivery):
	sessions, invoices, lines, taxes = load(
		filters.company, stream, filters.from_date, filters.to_date, window
	)
	by_name = {s.name: s for s in sessions}
	figures = {i.name: invoice_figures(i, lines[i.name], taxes[i.name]) for i in invoices}
	session_match, invoice_sessions, periods = reconcile(sessions, invoices, figures, window, max_delivery)
	period_of = {inv: (taken, start) for inv, taken, start in periods}
	price = flt(sessions[0].unit_price) if sessions else 0
	rows = []
	for inv in sorted(invoices, key=lambda i: (getdate(i.bill_date or i.posting_date), i.name)):
		fig = figures[inv.name]
		taken = [by_name[n] for n in invoice_sessions.get(inv.name, [])]
		s_litres = flt(sum(flt(s.litres) for s in taken), 3)
		# the price of this invoice's own sessions (the price can change during the period)
		inv_price = flt(taken[-1].unit_price) if taken else price
		inv_litres = fig.diesel_litres
		estimate = inv_litres is None and inv_price
		if estimate:
			inv_litres = flt(flt(inv.grand_total) / inv_price - fig.delivery_litres, 1)
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
					_("Period: invoiced more than sessions")
					if diff > 0
					else _("Period: sessions more than invoiced")
				)
			)
			exception = not agree
			notes.append(
				_("Aggregated invoice: sessions after {0} up to the bill date").format(
					start or _("the start of the period")
				)
			)
		elif taken:
			rule = session_match[taken[0].name][1]
			diff = flt((inv_litres or 0) - s_litres, 1)
			status = _("Matched") if rule == _("Litres equal") else _("Matched: {0}").format(rule)
			exception = False
			if fig.diesel_litres and fig.diesel_litres > s_litres and not fig.delivery_amount:
				notes.append(
					_(
						"Physical diesel = session litres; the difference is a delivery charge booked as diesel"
					)
				)
		else:
			status, diff, exception = _("Invoice without session"), None, True
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
		rows.append(
			{
				"status": status,
				"date": inv.bill_date or inv.posting_date,
				"supplier": inv.supplier,
				"sessions": _sessions_label(taken),
				"session_litres": s_litres,
				"invoice": inv.name,
				"bill_no": (inv.bill_no or "").strip(),
				"invoice_litres": inv_litres,
				"delivery_litres": fig.delivery_litres,
				"litre_difference": diff,
				"grand_total": flt(inv.grand_total, 2),
				"net_total": flt(inv.net_total, 2),
				"vat": fig.vat,
				"vat_pct": fig.vat_pct,
				"vat_basis": vat_basis(inv, fig, inv_price),
				"session_projects": _projects(taken),
				"invoice_projects": ", ".join(fig.projects) or _("none"),
				"note": "; ".join(notes),
				"exception": int(exception),
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
				"date": s.date,
				"supplier": s.supplier,
				"sessions": s.name,
				"session_litres": flt(s.litres, 3),
				"session_projects": s.project,
				"note": _("Draft session ({0})").format(_(s.review_status)) if not s.docstatus else "",
				"exception": 0 if late else 1,
			}
		)
	return rows


def _sessions_label(sessions):
	if len(sessions) <= 3:
		return ", ".join(s.name for s in sessions)
	return _("{0} sessions ({1} .. {2})").format(len(sessions), sessions[0].name, sessions[-1].name)


def _projects(sessions):
	litres = {}
	for s in sessions:
		litres[s.project] = litres.get(s.project, 0) + flt(s.litres)
	total = sum(litres.values()) or 1
	return ", ".join(
		f"{p} {flt(100 * v / total, 1)}%" for p, v in sorted(litres.items(), key=lambda x: -x[1])
	)


def _summary(rows):
	session_rows = [r for r in rows if r.get("sessions")]
	invoices = [r for r in rows if r.get("invoice")]
	exceptions = [r for r in rows if r.get("exception")]
	return [
		{
			"label": _("Session litres"),
			"value": flt(sum(flt(r.get("session_litres")) for r in session_rows), 1),
			"datatype": "Float",
		},
		{
			"label": _("Invoiced diesel litres"),
			"value": flt(sum(flt(r.get("invoice_litres")) for r in invoices), 1),
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
