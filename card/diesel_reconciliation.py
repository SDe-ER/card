# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-1: read-only reconciliation of CARD diesel sessions (Project Diesel Fill) against the suppliers'
own Purchase Invoices, entered in Desk.

Nothing here writes: no insert, save, submit, cancel, db_set or link. The suppliers' invoices carry the
litres only in the line text (one line per delivery or per project, qty 1), so the litres, the delivery
charge and the fuel kind are read from that text, and the VAT basis of each invoice is derived from its own
figures (gross or net per litre against the session price) — never assumed for the company.

Matching, in order:
1. per delivery: an invoice of the same supplier dated -1..+window days from a session, whose diesel litres
   equal the session's, or equal the session's plus a delivery charge in litres folded into the diesel line
   (when the invoice has no separate delivery line), or — when it states no litres — whose gross total
   divided by the session price is the session's litres (+ up to the delivery-charge litres) within 1 %;
2. per period: an invoice clearly larger than one delivery takes the sessions left unmatched between the
   previous such invoice and its bill date (aggregated supplier invoices);
3. sessions after the last invoice are "not invoiced yet"; others without an invoice, and invoices without a
   session, are exceptions."""

import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.report_access import _role_reads, assert_report_role, query_companies

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# a number (thousands separated by commas, decimals by a point) followed by a litre word
LITRES = re.compile(
	r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:لتر|ltr|litres?|liters?|l\b)", re.IGNORECASE
)
DELIVERY_WORDS = ("نقل", "توصيل", "transport", "delivery")
OTHER_FUEL_WORDS = ("بنزين", "petrol", "gasoline")
DIESEL_WORDS = ("ديزل", "سولار", "diesel")
PRICE_TOLERANCE = 0.002  # per litre
AGGREGATE_FACTOR = 1.5  # an invoice above 1.5 x the largest session is an aggregated invoice


def line_litres(text):
	"""The litres stated in an invoice line text, or None."""
	m = LITRES.search((text or "").translate(DIGITS))
	return flt(m.group(1).replace(",", "")) if m else None


def line_kind(text):
	text = (text or "").lower()
	if any(w in text for w in DELIVERY_WORDS):
		return "delivery"
	if any(w in text for w in OTHER_FUEL_WORDS):
		return "other fuel"
	if any(w in text for w in DIESEL_WORDS):
		return "diesel"
	return "other"


def invoice_figures(inv, lines, taxes):
	"""Litres, amounts and VAT of one Purchase Invoice, read from its own lines and tax rows."""
	diesel_amount = delivery_amount = other_amount = 0.0
	diesel_litres = delivery_litres = 0.0
	litres_stated = True
	projects = set()
	equipment = set()
	unallocated = 0
	for line in lines:
		text = line.item_name or line.description or ""
		kind = line_kind(text)
		litres = line_litres(text)
		if kind == "diesel":
			diesel_amount += flt(line.amount)
			if litres is None:
				litres_stated = False
			else:
				diesel_litres += litres
		elif kind == "delivery":
			delivery_amount += flt(line.amount)
			delivery_litres += litres or 0
		else:
			other_amount += flt(line.amount)
		if line.get("card_equipment"):
			equipment.add(line.card_equipment)
		if line.project:
			projects.add(line.project)
		else:
			unallocated += 1
	vat = sum(flt(t.tax_amount) for t in taxes if t.add_deduct_tax != "Deduct")
	net = flt(inv.net_total)
	return frappe._dict(
		diesel_amount=flt(diesel_amount, 2),
		delivery_amount=flt(delivery_amount, 2),
		other_amount=flt(other_amount, 2),
		diesel_litres=diesel_litres if litres_stated and diesel_amount else None,
		delivery_litres=delivery_litres,
		vat=flt(vat, 2),
		vat_pct=flt(100 * vat / net, 2) if net else 0,
		vat_included=any(t.included_in_print_rate for t in taxes),
		projects=sorted(projects),
		# None when the Card Equipment dimension is not on Purchase Invoice Item (nothing to compare)
		equipment=sorted(equipment) if lines and "card_equipment" in lines[0] else None,
		lines_without_project=unallocated,
	)


def vat_basis(inv, fig, session_price):
	"""Inclusive / Exclusive / Unverified, from this invoice's own figures against the session price."""
	litres = (fig.diesel_litres or 0) + (fig.delivery_litres or 0)
	if not fig.diesel_litres or not session_price:
		return _("Unverified (no litres on the invoice)")
	gross, net = flt(inv.grand_total) / litres, flt(inv.net_total) / litres
	if abs(gross - session_price) <= PRICE_TOLERANCE:
		return _("VAT-inclusive price")
	if abs(net - session_price) <= PRICE_TOLERANCE:
		return _("VAT-exclusive price")
	return _("Unverified (price per litre {0} gross, {1} net)").format(flt(gross, 4), flt(net, 4))


def _delivery_match(session, inv, fig, window, max_delivery):
	gap = (getdate(inv.bill_date or inv.posting_date) - getdate(session.date)).days
	if not -1 <= gap <= window:
		return None
	litres = flt(session.litres)
	if fig.diesel_litres is not None:
		diff = fig.diesel_litres - litres
		if abs(diff) <= 0.5:
			return (gap, _("Litres equal"))
		if 0 < diff <= max_delivery and not fig.delivery_amount:
			return (
				gap,
				_("Invoice litres = session + {0} L delivery charge inside the diesel line").format(
					flt(diff, 1)
				),
			)
		return None
	price = flt(session.unit_price)
	if not price:
		return None
	implied = flt(inv.grand_total) / price
	if litres <= implied <= (litres + max_delivery) * 1.01:
		return (gap + 0.5, _("Amount only: gross / session price = {0} L").format(flt(implied, 1)))
	return None


def reconcile(sessions, invoices, figures, window=3, max_delivery=60):
	"""Pure matching of sessions to invoices. Returns (session_match, invoice_sessions, periods):
	session_match {fill: (invoice, rule)}, invoice_sessions {invoice: [fills]},
	periods [(invoice, [fills], from_date)] for aggregated invoices."""
	sessions = sorted(sessions, key=lambda s: (getdate(s.date), s.name))
	invoices = sorted(invoices, key=lambda i: (getdate(i.bill_date or i.posting_date), i.name))
	session_match, invoice_sessions, used = {}, {}, set()
	for exact in (True, False):
		for s in sessions:
			if s.name in session_match:
				continue
			best = None
			for inv in invoices:
				if inv.name in used:
					continue
				m = _delivery_match(s, inv, figures[inv.name], window, max_delivery)
				if m and (not exact or m[1] == _("Litres equal")) and (best is None or m[0] < best[0][0]):
					best = (m, inv)
			if best:
				used.add(best[1].name)
				session_match[s.name] = (best[1].name, best[0][1])
				invoice_sessions[best[1].name] = [s.name]
	largest = max((flt(s.litres) for s in sessions), default=0)
	periods, start = [], None
	for inv in invoices:
		if inv.name in used:
			continue
		fig = figures[inv.name]
		price = flt(sessions[0].unit_price) if sessions else 0
		litres = (
			fig.diesel_litres
			if fig.diesel_litres is not None
			else (flt(inv.grand_total) / price if price else 0)
		)
		if not largest or litres < AGGREGATE_FACTOR * largest:
			continue
		end = getdate(inv.bill_date or inv.posting_date)
		taken = [
			s.name
			for s in sessions
			if s.name not in session_match
			and (start is None or getdate(s.date) > start)
			and getdate(s.date) <= end
		]
		for name in taken:
			session_match[name] = (inv.name, _("Period"))
		used.add(inv.name)
		invoice_sessions[inv.name] = taken
		periods.append((inv.name, taken, start))
		start = end
	return session_match, invoice_sessions, periods


def load(company, suppliers, from_date, to_date, window, submitted_only=False):
	"""Sessions and invoices of `suppliers` in `company` for the period (invoices up to `window` days later).
	Draft sessions are included unless `submitted_only`; each row keeps its docstatus."""
	from frappe.utils import add_days

	sessions = frappe.get_all(
		"Project Diesel Fill",
		filters={
			"company": company,
			"supplier": ["in", suppliers],
			"docstatus": 1 if submitted_only else ["<", 2],
			"date": ["between", [from_date, to_date]],
		},
		fields=[
			"name",
			"date",
			"supplier",
			"project",
			"card_equipment",
			"litres",
			"unit_price",
			"amount",
			"docstatus",
			"review_status",
		],
		order_by="date asc, name asc",
		limit_page_length=0,
	)
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={
			"company": company,
			"supplier": ["in", suppliers],
			"docstatus": 1,
			"is_return": 0,
			"posting_date": ["between", [add_days(from_date, -window), add_days(to_date, 62)]],
		},
		fields=[
			"name",
			"supplier",
			"posting_date",
			"bill_no",
			"bill_date",
			"net_total",
			"grand_total",
			"project",
			"cost_center",
		],
		order_by="posting_date asc, name asc",
		limit_page_length=0,
	)
	# an invoice belongs to the period by its bill date (falls back to the posting date)
	invoices = [
		i
		for i in invoices
		if getdate(from_date) <= getdate(i.bill_date or i.posting_date) <= getdate(add_days(to_date, window))
	]
	names = [i.name for i in invoices]
	lines, taxes = {n: [] for n in names}, {n: [] for n in names}
	if names:
		for row in frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": ["in", names], "parenttype": "Purchase Invoice"},
			fields=[
				"parent",
				"item_name",
				"description",
				"amount",
				"project",
				"cost_center",
				"expense_account",
				*(
					["card_equipment"]
					if frappe.get_meta("Purchase Invoice Item").has_field("card_equipment")
					else []
				),
			],
			order_by="parent asc, idx asc",
			limit_page_length=0,
		):
			lines[row.parent].append(row)
		for row in frappe.get_all(
			"Purchase Taxes and Charges",
			filters={"parent": ["in", names], "parenttype": "Purchase Invoice"},
			fields=["parent", "tax_amount", "add_deduct_tax", "included_in_print_rate"],
			limit_page_length=0,
		):
			taxes[row.parent].append(row)
	return sessions, invoices, lines, taxes


@frappe.whitelist(methods=["GET"])
def diesel_supplier_options(txt: str | None = None, company: str | None = None):
	"""Options for the report's supplier filter: suppliers of diesel sessions in the companies the user may
	see (a list, not a Link to the Supplier master: report Link filters are checked against the user's own
	permissions)."""
	assert_report_role()
	if not _role_reads("Project Diesel Fill"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	companies = query_companies({"company": company} if company else {}, "Project Diesel Fill")
	if not companies:
		return []
	suppliers = frappe.get_all(
		"Project Diesel Fill",
		filters={"company": ["in", companies], "docstatus": ["<", 2], "supplier": ["like", f"%{txt or ''}%"]},
		pluck="supplier",
		distinct=True,
		order_by="supplier asc",
		limit_page_length=50,
	)
	return [{"value": s, "description": ""} for s in suppliers if s]
