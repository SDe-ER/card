# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment Partial Margin (#53, #127 P8; WP-16). Read-only.

One row per equipment and project for one company and period:

- revenue: submitted Sales Invoice lines carrying the Card Equipment dimension (posted in
  the period, net of VAT, credit notes included);
- not invoiced yet: the customer net of submitted customer cards of the period that no
  submitted document recognised. Shown apart, NEVER added to revenue or the margin;
- supplier rental: what submitted documents (CARD purchase invoices, linked hand-booked
  invoices, linked accrual journal entries) recognised for the supplier cards of the
  period; the supplier net not recognised yet is shown apart, never added to costs;
- diesel: direct fills at the posting's valuation; project-tank fills are NOT split by
  equipment — they sit on a project-level line, "unallocated tank diesel" (#118 rule 7);
- transport: company-borne transports, by their recorded equipment shares;
- maintenance and other tagged costs: Purchase Invoice and Material Issue lines by the
  Card Equipment dimension (card.analytics.maintenance_lines).

The margin is PARTIAL: it excludes depreciation, labour, insurance and overhead. Ledger
readers only (card.report_access.can_view_ledger)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card import analytics
from card.report_access import can_view_ledger, readable_links, resolve_company

DOCTYPES = (
	analytics.CARD,
	analytics.FILL,
	analytics.TRANSPORT,
	"Sales Invoice",
	"Purchase Invoice",
	"Stock Entry",
	"GL Entry",
)
COST_KEYS = ("rental", "diesel", "tank_diesel", "transport", "maintenance")
AMOUNT_KEYS = ("revenue", "unbilled_revenue", *COST_KEYS, "total_cost", "margin", "unbilled_rental")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	if not can_view_ledger(company):
		frappe.throw(
			_("The equipment partial margin shows financial figures; it needs General Ledger access."),
			frappe.PermissionError,
		)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the partial margin."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))
	project, equipment = filters.get("project"), filters.get("equipment")

	rows = {}
	notes = [_("Partial margin: excludes depreciation, labour, insurance and overhead.")]

	def add(eq, proj, key, amount):
		row = rows.setdefault((eq or "", proj or ""), dict.fromkeys(AMOUNT_KEYS, 0.0))
		row[key] = flt(row[key] + flt(amount), 2)

	if analytics.can_read(analytics.CARD):
		for side, recognised_key, open_key in (
			("Customer", None, "unbilled_revenue"),
			("Supplier", "rental", "unbilled_rental"),
		):
			cards = analytics.side_cards(company, side, start, end, project, equipment)
			held = analytics.card_recognition(cards, side)
			for card in cards:
				doc = held.get(card.name)
				if doc and doc.state == "Submitted":
					if recognised_key:
						add(card.equipment, card.project, recognised_key, doc.amount)
				else:
					add(card.equipment, card.project, open_key, card.net)
	else:
		notes.append(_("Monthly cards are not shown: you cannot read Card Monthly Card."))

	if analytics.can_read(analytics.FILL):
		diesel, diesel_notes = analytics.diesel_costs(company, start, end, project, equipment)
		for eq, proj, amount in diesel:
			add(eq, proj, "diesel" if eq else "tank_diesel", amount)
		notes.extend(diesel_notes)
	else:
		notes.append(_("Diesel is not shown: you cannot read Project Diesel Fill."))

	if analytics.can_read(analytics.TRANSPORT):
		for eq, proj, amount in analytics.transport_costs(company, start, end, project, equipment):
			add(eq, proj, "transport", amount)
	else:
		notes.append(_("Transport is not shown: you cannot read Equipment Transport."))

	if not analytics.dimension_ready():
		notes.append(
			_(
				"The Card Equipment accounting dimension is not set up on this site, so revenue and maintenance cannot be attributed to equipment and are not shown. Ask the system manager to create the dimension."
			)
		)
	else:
		if analytics.can_read("Sales Invoice"):
			for eq, proj, amount in analytics.revenue_lines(company, start, end, project, equipment):
				add(eq, proj, "revenue", amount)
		else:
			notes.append(_("Revenue is not shown: you cannot read Sales Invoice."))
		for line in analytics.maintenance_lines(company, start, end, project, equipment):
			add(line["equipment"], line["project"], "maintenance", line["amount"])
		unread = analytics.unread_maintenance_note()
		if unread:
			notes.append(unread)

	data = []
	totals = dict.fromkeys(AMOUNT_KEYS, 0.0)
	for (eq, proj), row in sorted(rows.items(), key=lambda item: (not item[0][0], item[0][1], item[0][0])):
		row["total_cost"] = flt(sum(row[k] for k in COST_KEYS), 2)
		row["margin"] = flt(row["revenue"] - row["total_cost"], 2)
		row.update(
			{
				"equipment": eq or None,
				"project": proj or None,
				"line": _("Equipment line")
				if eq
				else _("Project level: unallocated tank diesel and shared costs"),
			}
		)
		for key in AMOUNT_KEYS:
			totals[key] = flt(totals[key] + row[key], 2)
		data.append(row)

	notes.append(
		_(
			"Not invoiced yet is the card net that no submitted invoice or journal entry recognised; it is never added to revenue, costs or the margin. Project-tank diesel is never split by equipment."
		)
	)
	notes.append(
		_(
			"Timing: revenue and maintenance follow the posting date of their documents; supplier rental and the not-invoiced columns follow the start date of the card; diesel and transport follow their own date. A card invoiced in a later period shows its revenue in that period."
		)
	)
	summary = [
		{
			"label": _("Equipment revenue"),
			"value": totals["revenue"],
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Customer cards not invoiced yet"),
			"value": totals["unbilled_revenue"],
			"datatype": "Currency",
			"indicator": "Orange" if totals["unbilled_revenue"] else "Grey",
		},
		{
			"label": _("Partial cost"),
			"value": totals["total_cost"],
			"datatype": "Currency",
			"indicator": "Red",
		},
		{
			"label": _("Partial margin"),
			"value": totals["margin"],
			"datatype": "Currency",
			"indicator": "Green" if totals["margin"] >= 0 else "Red",
		},
		{
			"label": _("Unallocated tank diesel"),
			"value": totals["tank_diesel"],
			"datatype": "Currency",
			"indicator": "Grey",
		},
	]
	return readable_links(get_columns(), data), data, " ".join(notes), None, summary


def get_columns():
	def money(fieldname, label, width=120):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": width}

	return [
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 140,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 140,
		},
		{"fieldname": "line", "label": _("Margin line"), "fieldtype": "Data", "width": 160},
		money("revenue", _("Equipment revenue")),
		money("unbilled_revenue", _("Customer cards not invoiced yet (not in revenue)"), 150),
		money("rental", _("Supplier rental")),
		money("diesel", _("Diesel (direct fills)")),
		money("tank_diesel", _("Unallocated tank diesel"), 130),
		money("transport", _("Company transport")),
		money("maintenance", _("Maintenance and other tagged costs"), 150),
		money("total_cost", _("Partial cost")),
		money("margin", _("Partial margin")),
		money("unbilled_rental", _("Supplier cards not invoiced yet (not in costs)"), 150),
	]
