# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Like-for-like reconciliation for the CARD statements and summaries.

Card nets are amounts BEFORE VAT (what the monthly PI/SI bills as its net
total), while a party's GL credits/debits include VAT. The reconciliation
difference therefore compares the card net with the invoices' net total
(base_net_total, company currency; returns count negative) for the same
company, party and period. The GL figures stay in the reports as the official
balance, VAT included."""

import frappe
from frappe.utils import flt

INVOICE = {"Supplier": ("Purchase Invoice", "supplier"), "Customer": ("Sales Invoice", "customer")}


def invoiced_net(party_type, parties, company, start, end):
	"""{party: Σ base_net_total} of the party's submitted invoices posted in
	[start, end] for ``company``."""
	parties = [p for p in parties or [] if p]
	if not parties:
		return {}
	doctype, field = INVOICE[party_type]
	rows = frappe.db.sql(
		f"""
		select `{field}` as party, sum(base_net_total) as amount
		from `tab{doctype}`
		where docstatus = 1 and company = %(company)s and `{field}` in %(parties)s
			and posting_date between %(start)s and %(end)s
		group by `{field}`
		""",
		{"company": company, "parties": parties, "start": start, "end": end},
		as_dict=True,
	)
	return {r.party: flt(r.amount, 2) for r in rows}
