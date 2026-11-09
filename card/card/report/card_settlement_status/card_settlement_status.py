# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Card Settlement Status (settlement phase 1, owner decisions 2026-11-09).

Read-only. For every submitted monthly card of one party in the period: the
document that recognised it (CARD invoice, linked hand-booked invoice or linked
accrual journal entry), the card's share of that document, what is paid and what
remains. Nothing is stored in CARD: every amount comes from ERPNext's Payment
Ledger Entry of the recognising document, so a cancelled or reconciled payment
shows at once.

- A document's original amount is its own ledger row (invoice: grand total, VAT
  included; accrual journal entry: the supplier credit); what remains is the sum
  of the ledger rows against it.
- A document that recognised several sources is shared by their amounts, and its
  payments are allocated FIFO (oldest source first) — the owner's default (Q3).
- Payments of the party that are not allocated to any document are shown apart:
  they are settled in ERPNext with Payment Reconciliation, never here.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.constants import CUSTOMER_BILLING_DIRECTIONS, SUPPLIER_BILLING_DIRECTIONS
from card.report_access import can_view_ledger, resolve_company

CARD = "Card Monthly Card"
SIDE = {
	"Supplier": {"field": "supplier", "net": "net_amount", "directions": SUPPLIER_BILLING_DIRECTIONS},
	"Customer": {
		"field": "customer",
		"net": "customer_net_amount",
		"directions": CUSTOMER_BILLING_DIRECTIONS,
	},
}
SOURCE_DATE = {CARD: "from_date", "Project Diesel Fill": "date", "Equipment Transport": "date"}
PAYMENT_VOUCHERS = ("Payment Entry", "Journal Entry")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	party_type = filters.get("party_type") or "Supplier"
	if party_type not in SIDE:
		frappe.throw(_("Choose a supplier or a customer."))
	company = resolve_company(filters, CARD, "Payment Ledger Entry")
	if not can_view_ledger(company):
		frappe.throw(
			_("This report shows ledger balances; it needs General Ledger access."), frappe.PermissionError
		)
	party = filters.get("party")
	if party:
		frappe.has_permission(party_type, "read", party, throw=True)
	start, end = getdate(filters.get("from_date")), getdate(filters.get("to_date"))
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))

	side = SIDE[party_type]
	card_filters = [
		["company", "=", company],
		["docstatus", "=", 1],
		["from_date", "between", [start, end]],
		["card_direction", "in", list(side["directions"])],
		[side["field"], "is", "set"],
	]
	if party:
		card_filters.append([side["field"], "=", party])
	cards = frappe.get_all(
		CARD,
		filters=card_filters,
		fields=[
			"name",
			"month",
			"year",
			"project",
			"equipment",
			"from_date",
			side["field"] + " as party",
			side["net"] + " as net",
		],
		order_by="from_date asc, name asc",
		limit_page_length=0,
	)
	columns = _columns(party_type)
	if not cards:
		return columns, [], None, None, []

	holder = _active_logs(party_type, [c.name for c in cards])
	vouchers = {
		(log.posting_doctype, log.posting_doc) for log in holder.values() if log.status == "Submitted"
	}
	ledger = _ledger(company, party_type, {c.party for c in cards}, vouchers)
	shares = _fifo_shares({log.name: log for log in holder.values()}, ledger)

	data, totals = [], {"net": 0.0, "share": 0.0, "paid": 0.0, "remaining": 0.0}
	for card in cards:
		log = holder.get(card.name)
		row = {
			"card": card.name,
			"party": card.party,
			"month": "{0}/{1}".format(card.month, card.year),
			"project": card.project,
			"equipment": card.equipment,
			"net": flt(card.net, 2),
			"recognised_by": log.posting_doctype if log else None,
			"voucher": log.posting_doc if log else None,
		}
		if not log:
			row["status"] = _("Not recognised yet")
		elif log.status != "Submitted":
			row["status"] = _("Recognising document is a draft")
		else:
			share, paid = shares.get((log.name, card.name), (0.0, 0.0))
			remaining = flt(share - paid, 2)
			row.update({"share": share, "paid": paid, "remaining": remaining})
			if remaining <= 0.01:
				row["status"] = _("Fully settled")
			elif paid > 0:
				row["status"] = _("Partly settled")
			else:
				row["status"] = _("Recognised, not settled")
			for key in ("share", "paid", "remaining"):
				totals[key] = flt(totals[key] + row[key], 2)
		totals["net"] = flt(totals["net"] + row["net"], 2)
		data.append(row)

	unallocated = _unallocated_payments(company, party_type, {c.party for c in cards})
	summary = [
		{"label": _("Cards net"), "value": totals["net"], "datatype": "Currency", "indicator": "Blue"},
		{
			"label": _("Recognised share"),
			"value": totals["share"],
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Paid on the card"),
			"value": totals["paid"],
			"datatype": "Currency",
			"indicator": "Green",
		},
		{
			"label": _("Remaining on the card"),
			"value": totals["remaining"],
			"datatype": "Currency",
			"indicator": "Red",
		},
		{
			"label": _("Payments not allocated to a document"),
			"value": unallocated,
			"datatype": "Currency",
			"indicator": "Orange" if unallocated else "Grey",
		},
	]
	message = _(
		"Amounts come from the ledger of the recognising document (VAT included for invoices). A document that recognised several sources is shared by their amounts and its payments are allocated to the oldest first. Payments not allocated to a document are settled in the accounts with Payment Reconciliation."
	)
	return columns, data, message, None, summary


def _columns(party_type):
	return [
		{"fieldname": "card", "label": _("Card"), "fieldtype": "Link", "options": CARD, "width": 170},
		{
			"fieldname": "party",
			"label": _(party_type),
			"fieldtype": "Link",
			"options": party_type,
			"width": 160,
		},
		{"fieldname": "month", "label": _("Month"), "fieldtype": "Data", "width": 80},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 120,
		},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 120,
		},
		{"fieldname": "net", "label": _("Card net"), "fieldtype": "Currency", "width": 110},
		{
			"fieldname": "recognised_by",
			"label": _("Recognised by"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 120,
		},
		{
			"fieldname": "voucher",
			"label": _("Recognising document"),
			"fieldtype": "Dynamic Link",
			"options": "recognised_by",
			"width": 160,
		},
		{
			"fieldname": "share",
			"label": _("Card share of the document"),
			"fieldtype": "Currency",
			"width": 130,
		},
		{"fieldname": "paid", "label": _("Paid on the card"), "fieldtype": "Currency", "width": 110},
		{
			"fieldname": "remaining",
			"label": _("Remaining on the card"),
			"fieldtype": "Currency",
			"width": 110,
		},
		{"fieldname": "status", "label": _("Settlement status"), "fieldtype": "Data", "width": 150},
	]


def _active_logs(party_type, card_names):
	"""{card: its active GL Posting Log of this side (with the log's sources)}."""
	parents = frappe.get_all(
		"GL Posting Source",
		filters={"parenttype": "GL Posting Log", "source_doctype": CARD, "source_name": ["in", card_names]},
		fields=["parent", "source_name"],
		limit_page_length=0,
	)
	logs = {}
	result = {}
	for row in parents:
		if row.parent not in logs:
			log = frappe.db.get_value(
				"GL Posting Log",
				row.parent,
				["name", "status", "party_type", "party", "posting_doctype", "posting_doc"],
				as_dict=True,
			)
			if log:
				log.sources = frappe.get_all(
					"GL Posting Source",
					filters={"parent": log.name, "parenttype": "GL Posting Log"},
					fields=["source_doctype", "source_name", "amount"],
					limit_page_length=0,
				)
			logs[row.parent] = log
		log = logs[row.parent]
		if log and log.status in ACTIVE_STATES and log.party_type == party_type:
			result[row.source_name] = log
	return result


def _ledger(company, party_type, parties, vouchers):
	"""{(doctype, name): (original, outstanding)} from the Payment Ledger Entry."""
	if not vouchers:
		return {}
	ple = frappe.qb.DocType("Payment Ledger Entry")
	names = [name for _dt, name in vouchers]
	rows = (
		frappe.qb.from_(ple)
		.select(
			ple.voucher_type,
			ple.voucher_no,
			ple.against_voucher_type,
			ple.against_voucher_no,
			Sum(ple.amount).as_("amount"),
		)
		.where(
			(ple.company == company)
			& (ple.party_type == party_type)
			& (ple.party.isin(list(parties)))
			& (ple.against_voucher_no.isin(names))
			& (ple.delinked == 0)
		)
		.groupby(ple.voucher_type, ple.voucher_no, ple.against_voucher_type, ple.against_voucher_no)
	).run(as_dict=True)
	result = {}
	for doctype, name in vouchers:
		own = [r for r in rows if r.against_voucher_type == doctype and r.against_voucher_no == name]
		original = flt(
			sum(flt(r.amount) for r in own if r.voucher_type == doctype and r.voucher_no == name), 2
		)
		outstanding = flt(sum(flt(r.amount) for r in own), 2)
		result[(doctype, name)] = (original, outstanding)
	return result


def _fifo_shares(logs, ledger):
	"""{(log, card): (share, paid)}: the document's original amount shared by its
	sources' amounts; what is paid (original − outstanding) allocated oldest first."""
	result = {}
	for log in logs.values():
		if log.status != "Submitted":
			continue
		original, outstanding = ledger.get((log.posting_doctype, log.posting_doc), (0.0, 0.0))
		sources = list(log.sources or [])
		base = sum(flt(s.amount) for s in sources)
		if not sources or not base:
			continue
		dates = {}
		for s in sources:
			dates[(s.source_doctype, s.source_name)] = frappe.db.get_value(
				s.source_doctype, s.source_name, SOURCE_DATE.get(s.source_doctype, "creation")
			)
		sources.sort(key=lambda s: (str(dates.get((s.source_doctype, s.source_name)) or ""), s.source_name))
		left = max(0.0, flt(original - outstanding, 2))
		allocated = 0.0
		for i, s in enumerate(sources):
			# the last source takes the rounding rest, so the shares add up to the document
			share = (
				flt(original - allocated, 2)
				if i == len(sources) - 1
				else flt(original * flt(s.amount) / base, 2)
			)
			allocated = flt(allocated + share, 2)
			paid = min(share, left) if share > 0 else 0.0
			left = flt(left - paid, 2)
			if s.source_doctype == CARD:
				result[(log.name, s.source_name)] = (share, flt(paid, 2))
	return result


def _unallocated_payments(company, party_type, parties):
	"""Σ of the party's payments (Payment Entry / Journal Entry) still standing
	against themselves — paid, but not allocated to any document."""
	ple = frappe.qb.DocType("Payment Ledger Entry")
	rows = (
		frappe.qb.from_(ple)
		.select(ple.voucher_no, Sum(ple.amount).as_("amount"))
		.where(
			(ple.company == company)
			& (ple.party_type == party_type)
			& (ple.party.isin(list(parties)))
			& (ple.voucher_type.isin(list(PAYMENT_VOUCHERS)))
			& (ple.against_voucher_no == ple.voucher_no)
			& (ple.delinked == 0)
		)
		.groupby(ple.voucher_no)
	).run(as_dict=True)
	return flt(-sum(flt(r.amount) for r in rows if flt(r.amount) < 0), 2)
