# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Read-only helpers of the analytics reports (#53, #127 P8): Equipment Partial Margin,
Unbilled Card Work and Equipment Maintenance Cost.

Nothing here writes. Every business document is read with ``frappe.get_list`` (the
user's own permissions and User Permissions apply); child rows are read only for the
parents that query returned. The GL Posting Log (CARD's own audit record) is read
directly, as the existing settlement report does; the reports that use it are gated on
the server (``report_access``) before anything is read.

Rules (owner, #118 rule 7 and #53):
- money is the company currency, net of VAT (``base_net_amount`` on invoice lines);
- a project-tank diesel fill is never split by equipment here: it stays on a project
  line ("unallocated tank diesel");
- revenue and maintenance are attributed to equipment only through the Card Equipment
  accounting dimension; without it they are not shown (never guessed)."""

import frappe
from frappe import _
from frappe.utils import flt

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.constants import CUSTOMER_BILLING_DIRECTIONS, SUPPLIER_BILLING_DIRECTIONS
from card.dimension import DIMENSION_FIELD
from card.transport_costs import TRANSPORT_COST_FIELDS, company_cost_project

CARD = "Card Monthly Card"
FILL = "Project Diesel Fill"
TRANSPORT = "Equipment Transport"
DIMENSION_DOCTYPES = ("Sales Invoice Item", "Purchase Invoice Item", "Stock Entry Detail")
CHUNK = 500

SIDES = {
	"Supplier": {
		"field": "supplier",
		"net": "net_amount",
		"invoice_field": "purchase_invoice",
		"invoice_doctype": "Purchase Invoice",
		"directions": SUPPLIER_BILLING_DIRECTIONS,
	},
	"Customer": {
		"field": "customer",
		"net": "customer_net_amount",
		"invoice_field": "sales_invoice",
		"invoice_doctype": "Sales Invoice",
		"directions": CUSTOMER_BILLING_DIRECTIONS,
	},
}


def dimension_ready():
	"""True when the Card Equipment accounting dimension field exists on every invoice and
	stock line these reports read (the dimension is a manual setup step, FR-031)."""
	return all(frappe.get_meta(doctype).has_field(DIMENSION_FIELD) for doctype in DIMENSION_DOCTYPES)


def can_read(doctype):
	return bool(frappe.has_permission(doctype, "read"))


MAINTENANCE_DOCTYPES = ("Purchase Invoice", "Stock Entry")


def unread_maintenance_note():
	"""The message for maintenance sources the user cannot read (so they are not counted), or None."""
	missing = [doctype for doctype in MAINTENANCE_DOCTYPES if not can_read(doctype)]
	if not missing:
		return None
	return _("Maintenance from these documents is not shown, you cannot read them: {0}.").format(
		", ".join(_(doctype) for doctype in missing)
	)


def _chunks(names):
	names = list(names)
	for i in range(0, len(names), CHUNK):
		yield names[i : i + CHUNK]


def _children(child_doctype, parent_doctype, parents, fields, extra=None):
	"""Child rows of parents the user already read through get_list."""
	rows = []
	for chunk in _chunks(parents):
		filters = [["parenttype", "=", parent_doctype], ["parent", "in", chunk]]
		rows.extend(
			frappe.get_all(
				child_doctype,
				filters=filters + (extra or []),
				fields=["parent", *fields],
				order_by="parent asc, idx asc",
				limit_page_length=0,
			)
		)
	return rows


def _sources(source_doctype, names):
	"""{source_name: [(log name, amount)]} of the GL Posting Source rows of these sources."""
	result = {}
	for chunk in _chunks(names):
		for row in frappe.get_all(
			"GL Posting Source",
			filters={
				"parenttype": "GL Posting Log",
				"source_doctype": source_doctype,
				"source_name": ["in", chunk],
			},
			fields=["parent", "source_name", "amount"],
			limit_page_length=0,
		):
			result.setdefault(row.source_name, []).append((row.parent, flt(row.amount, 2)))
	return result


def _logs(names, party_type=None):
	"""{log: row} of the ACTIVE (Draft or Submitted) GL Posting Logs among ``names``."""
	result = {}
	for chunk in _chunks(set(names)):
		filters = {"name": ["in", chunk], "status": ["in", list(ACTIVE_STATES)]}
		if party_type:
			filters["party_type"] = party_type
		for log in frappe.get_all(
			"GL Posting Log",
			filters=filters,
			fields=["name", "status", "party_type", "posting_doctype", "posting_doc"],
			limit_page_length=0,
		):
			result[log.name] = log
	return result


def side_cards(company, side, start, end, project=None, equipment=None, party=None):
	"""Submitted cards of one billing side whose period starts in [start, end], as the user may
	read them (get_list)."""
	spec = SIDES[side]
	filters = [
		["company", "=", company],
		["docstatus", "=", 1],
		["from_date", "between", [start, end]],
		["card_direction", "in", list(spec["directions"])],
		[spec["field"], "is", "set"],
	]
	if project:
		filters.append(["project", "=", project])
	if equipment:
		filters.append(["equipment", "=", equipment])
	if party:
		filters.append([spec["field"], "=", party])
	return frappe.get_list(
		CARD,
		filters=filters,
		fields=[
			"name",
			"month",
			"year",
			"project",
			"equipment",
			"from_date",
			spec["field"] + " as party",
			spec["net"] + " as net",
			spec["invoice_field"] + " as invoice",
		],
		order_by="from_date asc, name asc",
		limit_page_length=0,
	)


def card_recognition(cards, side):
	"""{card: {"state": "Submitted" | "Draft", "doctype", "doc", "amount"}} for the cards of
	``side`` held by a live document of that side: an active GL Posting Log (a CARD invoice,
	a linked hand-booked invoice or a linked accrual journal entry, card/gl/journal_link.py),
	or else the side's own invoice link. A card missing from the result is not recognised.
	``amount`` is what the document recognised for the card: the log's source amount, or the
	card's net when only the invoice link is known."""
	spec = SIDES[side]
	names = [c.name for c in cards]
	members = _sources(CARD, names)
	logs = _logs([parent for rows in members.values() for parent, _a in rows], side)
	result = {}
	for name, rows in members.items():
		held = [(logs[parent], amount) for parent, amount in rows if parent in logs]
		if not held:
			continue
		# a submitted document wins over a draft one of the same side
		log, amount = sorted(held, key=lambda h: h[0].status != "Submitted")[0]
		result[name] = frappe._dict(
			state=log.status, doctype=log.posting_doctype, doc=log.posting_doc, amount=amount
		)
	linked = {c.invoice for c in cards if c.invoice and c.name not in result}
	# Only the docstatus of the invoices these readable cards already link to is read (no amounts):
	# it tells a draft from a submitted or cancelled invoice. The card itself was permission-checked.
	docstatus = {}
	for chunk in _chunks(linked):
		docstatus.update(
			dict(
				frappe.get_all(
					spec["invoice_doctype"],
					filters={"name": ["in", chunk]},
					fields=["name", "docstatus"],
					as_list=True,
				)
			)
		)
	for card in cards:
		if card.name in result or not card.invoice:
			continue
		state = {0: "Draft", 1: "Submitted"}.get(docstatus.get(card.invoice))
		if state:
			result[card.name] = frappe._dict(
				state=state, doctype=spec["invoice_doctype"], doc=card.invoice, amount=flt(card.net, 2)
			)
	return result


def diesel_costs(company, start, end, project=None, equipment=None):
	"""([(equipment or None, project, net amount)], notes) of submitted diesel fills dated in
	[start, end]. A direct fill is the equipment's; a project-tank fill (no equipment) stays on
	its project with equipment None — never split here.

	The amount is the posting's valuation: the net booked on a submitted CARD posting, or, for a
	fill not posted yet, the fill amount converted to net by the posting's own rule
	(card.gl.posting._apply_diesel_vat_basis, the configured diesel price VAT basis for a
	VAT-registered supplier). No VAT is inferred beyond that basis; where the basis is not
	verified the fill amount is kept and ``notes`` says so."""
	filters = [["company", "=", company], ["docstatus", "=", 1], ["date", "between", [start, end]]]
	if project:
		filters.append(["project", "=", project])
	fills = frappe.get_list(
		FILL,
		filters=filters,
		fields=["name", "project", "card_equipment", "supplier", "amount"],
		order_by="date asc, name asc",
		limit_page_length=0,
	)
	if equipment:
		fills = [f for f in fills if f.card_equipment == equipment]
	members = _sources(FILL, [f.name for f in fills])
	posted = _logs([parent for rows in members.values() for parent, _a in rows], "Supplier")
	valued, pending = {}, []
	for fill in fills:
		valuations = [
			a
			for parent, a in members.get(fill.name, [])
			if posted.get(parent, {}).get("status") == "Submitted"
		]
		if valuations:
			valued[fill.name] = valuations[0]
		else:
			pending.append(fill)
	net, notes = _unposted_fill_net(company, pending)
	valued.update(net)
	result = [(f.card_equipment or None, f.project, valued[f.name]) for f in fills]
	return result, notes


def _unposted_fill_net(company, fills):
	"""({fill: net amount}, notes) for fills not posted yet, through the posting's VAT basis rule,
	one supplier at a time. A refusal of that rule (basis not verified, no single VAT rate, no
	Card Settings row) keeps the fill amounts and is reported instead of raised."""
	from card.gl.posting import _apply_diesel_vat_basis
	from card.gl.preflight import company_settings_row

	result = {f.name: flt(f.amount, 2) for f in fills}
	if not fills:
		return result, []
	by_supplier = {}
	for fill in fills:
		by_supplier.setdefault(fill.supplier or "", []).append(fill)
	unverified = []
	log = frappe.local.message_log
	kept = len(log)
	try:
		row = company_settings_row(company)
	except frappe.ValidationError:
		del log[kept:]
		return result, [
			_("Diesel not posted yet is shown at the fill amount: Card Settings has no row for this company.")
		]
	tax_ids = dict(
		frappe.get_all(
			"Supplier",
			filters={"name": ["in", [s for s in by_supplier if s]] or [""]},
			fields=["name", "tax_id"],
			as_list=True,
		)
	)
	for supplier, group in by_supplier.items():
		# the posting adds VAT only for a VAT-registered supplier (card.gl.posting: tax_id set)
		template = row.purchase_tax_template if tax_ids.get(supplier) else None
		lines = [{"fill": f.name, "rate": flt(f.amount, 2), "description": ""} for f in group]
		sources = {FILL: [(f.name, flt(f.amount, 2)) for f in group]}
		try:
			_apply_diesel_vat_basis(row, lines, sources, template, supplier)
		except frappe.ValidationError:
			del log[kept:]
			unverified.append(supplier)
			continue
		result.update(dict(sources[FILL]))
	notes = []
	if unverified:
		notes.append(
			_(
				"The diesel price VAT basis is not verified for these suppliers, so their fills not posted yet are shown at the fill amount: {0}."
			).format(", ".join(sorted(unverified)))
		)
	return result, notes


def transport_costs(company, start, end, project=None, equipment=None):
	"""[(equipment or None, cost project, amount)] of submitted transports dated in
	[start, end] whose cost the company bears (card.transport_costs rule), one entry per
	recorded equipment share; a transport without shares stays on its project."""
	transports = frappe.get_list(
		TRANSPORT,
		filters=[["company", "=", company], ["docstatus", "=", 1], ["date", "between", [start, end]]],
		fields=["name", *TRANSPORT_COST_FIELDS],
		order_by="date asc, name asc",
		limit_page_length=0,
	)
	keyed = {}
	for t in transports:
		key = company_cost_project(t)
		if key and (not project or key == project):
			keyed[t.name] = (key, flt(t.amount, 2))
	shares = {}
	for row in _children("Equipment Transport Item", TRANSPORT, keyed, ["card_equipment", "amount"]):
		shares.setdefault(row.parent, []).append((row.card_equipment or None, flt(row.amount, 2)))
	result = []
	for name, (key, amount) in keyed.items():
		for eq, share in shares.get(name) or [(None, amount)]:
			if not equipment or eq == equipment:
				result.append((eq, key, share))
	return result


def revenue_lines(company, start, end, project=None, equipment=None):
	"""[(equipment, project, amount)] of submitted Sales Invoice lines (returns included, so
	credit notes reduce revenue) posted in [start, end] that carry the Card Equipment
	dimension; amounts in company currency, net of VAT. Needs ``dimension_ready()``."""
	invoices = {
		r.name: r
		for r in frappe.get_list(
			"Sales Invoice",
			filters=[
				["company", "=", company],
				["docstatus", "=", 1],
				["posting_date", "between", [start, end]],
			],
			fields=["name", "project"],
			limit_page_length=0,
		)
	}
	extra = [[DIMENSION_FIELD, "is", "set"]]
	if equipment:
		extra = [[DIMENSION_FIELD, "=", equipment]]
	result = []
	for row in _children(
		"Sales Invoice Item",
		"Sales Invoice",
		invoices,
		[DIMENSION_FIELD, "project", "base_net_amount"],
		extra,
	):
		line_project = row.project or invoices[row.parent].project
		if project and line_project != project:
			continue
		result.append((row.get(DIMENSION_FIELD), line_project, flt(row.base_net_amount, 2)))
	return result


def _card_recognised_invoices(company, invoices):
	"""The purchase invoices among ``invoices`` that recognise CARD sources (rental cards,
	diesel fills, transports): documents of active GL Posting Logs and the sources' own invoice
	links. Their lines are rental, diesel or transport cost, never maintenance. Reads only the
	given invoices (the report period's invoices and the invoices they return)."""
	names = set()
	for chunk in _chunks(invoices):
		names.update(
			frappe.get_all(
				"GL Posting Log",
				filters={
					"company": company,
					"posting_doctype": "Purchase Invoice",
					"posting_doc": ["in", chunk],
					"status": ["in", list(ACTIVE_STATES)],
				},
				pluck="posting_doc",
			)
		)
		for doctype in (CARD, FILL, TRANSPORT):
			names.update(
				frappe.get_all(
					doctype,
					filters={"company": company, "purchase_invoice": ["in", chunk]},
					pluck="purchase_invoice",
				)
			)
	names.discard(None)
	names.discard("")
	return names


def _stock_items(item_codes):
	"""The stock items among ``item_codes`` (one batched read per chunk)."""
	result = set()
	for chunk in _chunks({code for code in item_codes if code}):
		result.update(
			frappe.get_all("Item", filters={"name": ["in", chunk], "is_stock_item": 1}, pluck="name")
		)
	return result


def maintenance_lines(company, start, end, project=None, equipment=None):
	"""Maintenance and other direct costs tagged to an equipment through the Card Equipment
	dimension, dated in [start, end], company currency, net of VAT:

	- submitted Purchase Invoice lines (debit notes included), except invoices that recognise
	  CARD sources (and their returns), fixed-asset lines, and lines of stock items whether or
	  not the invoice updates stock (a stock item reaches the equipment when it is issued, so
	  counting the purchase as well would count it twice);
	- submitted Material Issue Stock Entry lines, at their valuation.

	Depreciation, labour and insurance are not read. Needs ``dimension_ready()``. Returns a
	list of dicts."""
	extra = [[DIMENSION_FIELD, "is", "set"]]
	if equipment:
		extra = [[DIMENSION_FIELD, "=", equipment]]
	result = []
	if can_read("Purchase Invoice"):
		period = frappe.get_list(
			"Purchase Invoice",
			filters=[
				["company", "=", company],
				["docstatus", "=", 1],
				["posting_date", "between", [start, end]],
			],
			fields=["name", "posting_date", "project", "return_against"],
			limit_page_length=0,
		)
		excluded = _card_recognised_invoices(
			company, {r.name for r in period} | {r.return_against for r in period if r.return_against}
		)
		invoices = {r.name: r for r in period if r.name not in excluded and r.return_against not in excluded}
		lines = _children(
			"Purchase Invoice Item",
			"Purchase Invoice",
			invoices,
			[
				DIMENSION_FIELD,
				"project",
				"item_code",
				"expense_account",
				"base_net_amount",
				"is_fixed_asset",
			],
			extra,
		)
		stock_items = _stock_items(row.item_code for row in lines)
		for row in lines:
			head = invoices[row.parent]
			if row.is_fixed_asset or row.item_code in stock_items:
				continue
			result.append(
				{
					"posting_date": head.posting_date,
					"voucher_type": "Purchase Invoice",
					"voucher_no": row.parent,
					"equipment": row.get(DIMENSION_FIELD),
					"project": row.project or head.project,
					"item_code": row.item_code,
					"account": row.expense_account,
					"amount": flt(row.base_net_amount, 2),
				}
			)
	if can_read("Stock Entry"):
		entries = {
			r.name: r
			for r in frappe.get_list(
				"Stock Entry",
				filters=[
					["company", "=", company],
					["docstatus", "=", 1],
					["purpose", "=", "Material Issue"],
					["posting_date", "between", [start, end]],
				],
				fields=["name", "posting_date", "project"],
				limit_page_length=0,
			)
		}
		for row in _children(
			"Stock Entry Detail",
			"Stock Entry",
			entries,
			[DIMENSION_FIELD, "project", "item_code", "expense_account", "amount"],
			extra,
		):
			head = entries[row.parent]
			result.append(
				{
					"posting_date": head.posting_date,
					"voucher_type": "Stock Entry",
					"voucher_no": row.parent,
					"equipment": row.get(DIMENSION_FIELD),
					"project": row.project or head.project,
					"item_code": row.item_code,
					"account": row.expense_account,
					"amount": flt(row.amount, 2),
				}
			)
	if project:
		result = [r for r in result if r["project"] == project]
	result.sort(key=lambda r: (str(r["posting_date"]), r["voucher_type"], r["voucher_no"]))
	return result
