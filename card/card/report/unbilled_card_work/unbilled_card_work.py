# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Unbilled Card Work (#53, #127 P8; WP-17). Read-only.

Submitted monthly cards of one company whose period starts in the chosen dates and that
no live document of their side recognises yet: no active GL Posting Log (a CARD invoice,
a linked hand-booked invoice or a linked accrual journal entry, card/gl/journal_link.py)
and no draft or submitted invoice on the side's link. Supplier side (rented-in and
sub-rented cards: their net) and customer side (rented-out and sub-rented cards: their
customer net) are listed apart; a sub-rented card can be open on one side only.

With "Include cards held by a draft posting" the cards whose recognising document is
still a draft are listed too, marked as such. Readers: the roles that read the GL Posting
Log (card.report_access.role_reads)."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from card import analytics
from card.report_access import readable_links, resolve_company, role_reads
from card.report_currency import company_currency_report

SIDES = ("Supplier", "Customer")


@company_currency_report(analytics.CARD, "GL Posting Log")
def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, analytics.CARD, "GL Posting Log")
	if not (role_reads("GL Posting Log") and analytics.can_read(analytics.CARD)):
		frappe.throw(
			_("Unbilled card work needs read access to the monthly cards and to the GL Posting Log."),
			frappe.PermissionError,
		)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the unbilled card work."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))
	side_filter = filters.get("side") or "All"
	if side_filter not in ("All", *SIDES):
		frappe.throw(_("Choose the supplier side, the customer side or both."))
	include_drafts = cint(filters.get("include_drafts"))

	data = []
	totals = {"Supplier": 0.0, "Customer": 0.0}
	for side in SIDES:
		if side_filter not in ("All", side):
			continue
		cards = analytics.side_cards(
			company, side, start, end, filters.get("project"), filters.get("equipment")
		)
		held = analytics.card_recognition(cards, side)
		for card in cards:
			doc = held.get(card.name)
			if doc and (doc.state == "Submitted" or not include_drafts):
				continue
			row = {
				"card": card.name,
				"side": _("Supplier side") if side == "Supplier" else _("Customer side"),
				"party_type": side,
				"party": card.party,
				"month": "{0}/{1}".format(card.month, card.year),
				"project": card.project,
				"equipment": card.equipment,
				"amount": flt(card.net, 2),
				"status": _("Not invoiced") if not doc else _("Held by a draft posting"),
				"document_type": doc.doctype if doc else None,
				"document": doc.doc if doc else None,
			}
			totals[side] = flt(totals[side] + row["amount"], 2)
			data.append(row)

	summary = [
		{
			"label": _("Supplier cards not invoiced"),
			"value": totals["Supplier"],
			"datatype": "Currency",
			"indicator": "Orange" if totals["Supplier"] else "Grey",
		},
		{
			"label": _("Customer cards not invoiced"),
			"value": totals["Customer"],
			"datatype": "Currency",
			"indicator": "Orange" if totals["Customer"] else "Grey",
		},
	]
	message = _(
		"Submitted monthly cards that no invoice or linked journal entry of their side recognises yet. Amounts are the card net (supplier side) or the customer net (customer side), before VAT."
	)
	return readable_links(get_columns(), data), data, message, None, summary


def get_columns():
	return [
		{
			"fieldname": "card",
			"label": _("Card"),
			"fieldtype": "Link",
			"options": analytics.CARD,
			"width": 170,
		},
		{"fieldname": "side", "label": _("Billing side"), "fieldtype": "Data", "width": 110},
		{"fieldname": "party_type", "label": _("Party type"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "party",
			"label": _("Party"),
			"fieldtype": "Dynamic Link",
			"options": "party_type",
			"width": 160,
		},
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 80},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 130,
		},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 130,
		},
		{
			"fieldname": "amount",
			"label": _("Card amount not invoiced"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{"fieldname": "status", "label": _("Billing status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "document_type", "label": _("Document type"), "fieldtype": "Data", "hidden": 1},
		{
			"fieldname": "document",
			"label": _("Draft document"),
			"fieldtype": "Dynamic Link",
			"options": "document_type",
			"width": 160,
		},
	]
