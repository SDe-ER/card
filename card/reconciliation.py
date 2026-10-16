# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Like-for-like reconciliation for the CARD statements and summaries.

The reports' card figures are card nets BEFORE VAT. A party's GL credits/debits
include VAT, and its invoices also carry diesel, transport and purchases CARD
never built — none of which is a card. The invoiced side of the reconciliation
is therefore read from CARD's own posting trail: the GL Posting Source rows of
type Card Monthly Card on logs whose invoice is SUBMITTED, for the company,
party and card months of the period. Each row's amount is exactly the card net
the invoice billed (posting asserts it), so the difference is 0 once every card
of the period is invoiced. The GL figures stay in the reports as the official
balance, VAT included.

Three figures are kept apart (owner decision, PR #39):
- invoiced through CARD — ``cards_invoiced``;
- not invoiced through CARD — card net minus the above (cards in a CARD draft
  invoice stay here until the invoice is submitted);
- ERPNext invoices of the party made outside CARD — ``invoices_outside_card``,
  shown for manual reconciliation. They are never matched to cards by party and
  month, and nothing is relinked or rewritten.

Scope: per company, party and period. "Invoiced through Card" counts only the
posting sources of the cards the report shows, so under a project (or
equipment type) filter a multi-project invoice is split by the cards it billed.
ERPNext invoices outside Card stay per party — an invoice is not per project.
Cancelled invoices are excluded; returns / credit notes count with their sign
(a credit note against Card's own invoice is not Card's, so it shows, negative,
among the invoices outside Card)."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

POSTING_TYPE = {"Supplier": "Purchase Invoice", "Customer": "Sales Invoice"}
PARTY_FIELD = {"Supplier": "supplier", "Customer": "customer"}


def reconciliation_notice():
	return (
		_(
			"Not invoiced through Card = card net − invoiced through Card; a card in a Card draft invoice counts here until the invoice is submitted."
		)
		+ " "
		+ _(
			"ERPNext invoices outside Card are shown for manual reconciliation and are not matched to cards automatically."
		)
		+ " "
		+ _(
			"ERPNext invoices outside Card are per party for the whole period, whatever the project or equipment filter."
		)
	)


def cards_invoiced(party_type, parties, company, start, end, cards=None):
	"""{party: Σ card net billed by SUBMITTED monthly invoices} for the card
	months from ``start`` to ``end`` (inclusive). With ``cards`` (the card names
	a report shows), only those cards' own posting sources count — so a report
	narrowed by project or equipment type compares its cards with what Card
	invoiced for THEM, never with a whole multi-project invoice."""
	parties = [p for p in parties or [] if p]
	if not parties:
		return {}
	first = getdate(start).year * 100 + getdate(start).month
	last = getdate(end).year * 100 + getdate(end).month
	logs = frappe.get_all(
		"GL Posting Log",
		filters={
			"company": company,
			"party_type": party_type,
			"party": ["in", parties],
			"posting_type": POSTING_TYPE[party_type],
			"status": "Submitted",
			"year": ["between", [getdate(start).year, getdate(end).year]],
		},
		fields=["name", "party", "month", "year"],
		limit_page_length=0,
	)
	party_of = {
		log.name: log.party for log in logs if first <= cint(log.year) * 100 + cint(log.month) <= last
	}
	if not party_of:
		return {}
	shown = None if cards is None else set(cards)
	result = {}
	for row in frappe.get_all(
		"GL Posting Source",
		filters={
			"parent": ["in", list(party_of)],
			"parenttype": "GL Posting Log",
			"source_doctype": "Card Monthly Card",
		},
		fields=["parent", "source_name", "amount"],
		limit_page_length=0,
	):
		if shown is not None and row.source_name not in shown:
			continue
		party = party_of[row.parent]
		result[party] = flt(result.get(party, 0) + flt(row.amount), 2)
	return result


def invoices_outside_card(party_type, parties, company, start, end):
	"""{party: Σ net before VAT (company currency) of the SUBMITTED ERPNext
	invoices dated in the period that CARD did not create} — every invoice no
	GL Posting Log points to, whatever it bills. For manual reconciliation only."""
	parties = [p for p in parties or [] if p]
	if not parties:
		return {}
	doctype = POSTING_TYPE[party_type]
	party_field = PARTY_FIELD[party_type]
	invoices = frappe.get_all(
		doctype,
		filters={
			"company": company,
			party_field: ["in", parties],
			"docstatus": 1,
			"posting_date": ["between", [getdate(start), getdate(end)]],
		},
		fields=["name", party_field, "base_net_total"],
		limit_page_length=0,
	)
	if not invoices:
		return {}
	card_made = set(
		frappe.get_all(
			"GL Posting Log",
			filters={"posting_doctype": doctype, "posting_doc": ["in", [i.name for i in invoices]]},
			pluck="posting_doc",
			limit_page_length=0,
		)
	)
	result = {}
	for inv in invoices:
		if inv.name in card_made:
			continue
		party = inv.get(party_field)
		result[party] = flt(result.get(party, 0) + flt(inv.base_net_total), 2)
	return result
