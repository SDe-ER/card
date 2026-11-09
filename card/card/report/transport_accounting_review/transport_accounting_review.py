import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.report_access import _role_reads, readable_links, resolve_company


def get_columns():
	return [
		{"fieldname": "review", "label": _("Review"), "fieldtype": "Data", "width": 300},
		{
			"fieldname": "transport",
			"label": _("Equipment Transport"),
			"fieldtype": "Link",
			"options": "Equipment Transport",
			"width": 130,
		},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "route", "label": _("Route"), "fieldtype": "Data", "width": 220},
		{
			"fieldname": "responsibility",
			"label": _("Transport responsibility"),
			"fieldtype": "Data",
			"width": 220,
		},
		{"fieldname": "cost_bearer", "label": _("Cost borne by"), "fieldtype": "Data", "width": 140},
		{"fieldname": "charged_to", "label": _("Cost charged to"), "fieldtype": "Data", "width": 200},
		{"fieldname": "transport_supplier", "label": _("Transporter"), "fieldtype": "Data", "width": 170},
		{"fieldname": "amount", "label": _("Transporter cost"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "financial_status", "label": _("Financial status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "financial_decision", "label": _("Cost decision"), "fieldtype": "Data", "width": 170},
		{"fieldname": "customer", "label": _("Customer"), "fieldtype": "Data", "width": 170},
		{
			"fieldname": "billing_amount",
			"label": _("Agreed billing amount (before VAT)"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"fieldname": "recovery_amount",
			"label": _("Recovery amount"),
			"fieldtype": "Currency",
			"width": 120,
		},
		{
			"fieldname": "purchase_invoice",
			"label": _("Purchase Invoice"),
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 150,
		},
		{"fieldname": "note", "label": _("Evidence"), "fieldtype": "Data", "width": 320},
	]


def execute(filters=None):
	# Report: "Transport Accounting Review" (P1-2). Read-only: lists submitted transports whose accounting
	# needs a person — recorded before P1-2 without payer/bearer/cost project, financial decisions pending or
	# rejected, and decisions whose billing, recovery or posting waits for the accountant's and the tax
	# adviser's decisions. It changes, links and posts nothing.
	filters = frappe._dict(filters or {})
	for doctype in ("Equipment Transport", "Purchase Invoice"):
		if not _role_reads(doctype):
			frappe.throw(
				_("You need read access to {0} to run this report").format(_(doctype)), frappe.PermissionError
			)
	filters.company = resolve_company(filters, "Equipment Transport")
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Select the period"))
	if getdate(filters.to_date) < getdate(filters.from_date):
		frappe.throw(_("Invalid period: end is before start"))
	transports = frappe.get_list(
		"Equipment Transport",
		filters={
			"company": filters.company,
			"docstatus": 1,
			"date": ["between", [filters.from_date, filters.to_date]],
		},
		fields=[
			"name",
			"date",
			"responsibility",
			"payer",
			"cost_bearer",
			"cost_borne_by",
			"cost_basis",
			"cost_project",
			"cost_center",
			"overhead_cost_center",
			"transport_supplier",
			"amount",
			"financial_status",
			"financial_decision",
			"customer",
			"billing_amount",
			"recovery_amount",
			"purchase_invoice",
			"destination_type",
			"project",
			"destination_location",
			"source_project",
			"source_location",
		],
		order_by="date asc, name asc",
		limit_page_length=0,
	)
	rows = [_row(t) for t in transports]
	if filters.get("show", "Needs attention") != "All":
		rows = [r for r in rows if r["attention"]]
	columns = readable_links(get_columns(), rows)
	return columns, rows, None, None, _summary(rows)


def _row(t):
	review, attention, notes = _review(t)
	charged_to = ""
	if t.payer == "Company":
		charged_to = {
			"Project": t.cost_project,
			"Workshop or storage": _("Place {0}").format(t.destination_location or ""),
			"Company overhead": t.overhead_cost_center,
		}.get(t.cost_basis) or ""
	return {
		"review": review,
		"attention": int(attention),
		"transport": t.name,
		"date": t.date,
		"route": "{0} → {1}".format(
			t.source_project or t.source_location or "",
			t.project if (t.destination_type or "Project") == "Project" else (t.destination_location or ""),
		),
		"responsibility": _(t.responsibility) if t.responsibility else "",
		"cost_bearer": _(t.cost_bearer or t.cost_borne_by or ""),
		"charged_to": charged_to,
		"transport_supplier": t.transport_supplier,
		"amount": flt(t.amount, 2),
		"financial_status": _(t.financial_status) if t.financial_status else "",
		"financial_decision": _(t.financial_decision) if t.financial_decision else "",
		"customer": t.customer,
		"billing_amount": flt(t.billing_amount, 2) or None,
		"recovery_amount": flt(t.recovery_amount, 2) or None,
		"purchase_invoice": t.purchase_invoice,
		"note": "; ".join(notes),
	}


def _review(t):
	"""(label, needs attention, evidence notes) of one submitted transport."""
	if not t.responsibility:
		notes = [_("Recorded before P1-2: payer, cost bearer and cost project not recorded")]
		if t.cost_borne_by:
			notes.append(_("Old field: cost borne by {0}").format(_(t.cost_borne_by)))
		if t.purchase_invoice:
			# already booked on a supplier invoice: listed under "All", not as an open point
			notes.append(_("Already on Purchase Invoice {0}").format(t.purchase_invoice))
		return _("Recorded before P1-2 — review"), not t.purchase_invoice, notes
	if t.responsibility == "Responsibility needs review":
		return _("Responsibility needs review — cancel and amend with the verified responsibility"), True, []
	if t.financial_status == "Pending":
		return _("Financial decision pending (Accounts Manager)"), True, []
	if t.financial_status == "Rejected":
		return _("Financial decision rejected — cancel and amend the transport"), True, []
	if t.financial_decision == "Bill customer":
		return (
			_("Customer billing recorded — invoicing waits for the accountant and the tax adviser"),
			True,
			[],
		)
	if t.financial_decision == "Recover from equipment supplier":
		return _("Recovery recorded — not posted until the accountant decides"), True, []
	if t.financial_decision == "Company absorbs":
		return _("Absorbed by the company — approved exception"), True, []
	if t.payer == "Company":
		return _("Company cost recorded — Purchase Invoice posting waits for the accountant"), True, []
	return _("Record only (no company cost)"), False, []


def _summary(rows):
	attention = [r for r in rows if r["attention"]]
	return [
		{"label": _("Transports"), "value": len(rows), "datatype": "Int"},
		{
			"label": _("Needs attention"),
			"value": len(attention),
			"datatype": "Int",
			"indicator": "Red" if attention else "Green",
		},
	]
