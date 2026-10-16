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
from frappe.query_builder.functions import Sum
from frappe.utils import flt

INVOICE = {"Supplier": ("Purchase Invoice", "supplier"), "Customer": ("Sales Invoice", "customer")}


def invoiced_net(party_type, parties, company, start, end):
	"""{party: Σ base_net_total} of the party's submitted invoices posted in
	[start, end] for ``company``."""
	parties = [p for p in parties or [] if p]
	if not parties:
		return {}
	doctype, field = INVOICE[party_type]
	inv = frappe.qb.DocType(doctype)
	rows = (
		frappe.qb.from_(inv)
		.select(inv[field].as_("party"), Sum(inv.base_net_total).as_("amount"))
		.where(
			(inv.docstatus == 1)
			& (inv.company == company)
			& (inv[field].isin(parties))
			& (inv.posting_date[start:end])
		)
		.groupby(inv[field])
	).run(as_dict=True)
	return {r.party: flt(r.amount, 2) for r in rows}
