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
balance, VAT included."""

import frappe
from frappe.utils import cint, flt, getdate

POSTING_TYPE = {"Supplier": "Purchase Invoice", "Customer": "Sales Invoice"}


def cards_invoiced(party_type, parties, company, start, end):
	"""{party: Σ card net billed by SUBMITTED monthly invoices} for the card
	months from ``start`` to ``end`` (inclusive)."""
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
	result = {}
	for row in frappe.get_all(
		"GL Posting Source",
		filters={
			"parent": ["in", list(party_of)],
			"parenttype": "GL Posting Log",
			"source_doctype": "Card Monthly Card",
		},
		fields=["parent", "amount"],
		limit_page_length=0,
	):
		party = party_of[row.parent]
		result[party] = flt(result.get(party, 0) + flt(row.amount), 2)
	return result
