# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-1: read-only reconciliation of CARD diesel sessions (Project Diesel Fill) against the suppliers'
own Purchase Invoices, entered in Desk.

Nothing here writes: no insert, save, submit, cancel, db_set or link. The suppliers' invoices carry the
litres only in the line text (one line per delivery or per project, qty 1), so the litres, the delivery
charge and the fuel kind are read from that text (item name and description), and the VAT basis of each
invoice is derived from its own figures (gross or net per litre against the session price) — never assumed
for the company. Amounts are in the company currency (base fields).

Matching, in order:
0. linked: a session whose `purchase_invoice` is one of the invoices (a CARD posting or a P0 link) belongs
   to it;
1. per delivery: an invoice of the same stream dated -1..+window days from a session (the nearest date
   first), whose diesel litres equal the session's, or equal the session's plus a delivery charge in litres
   folded into the diesel line (when the invoice has no separate delivery line), or — when it states no
   litres — whose gross or net total divided by the session price is the session's litres (+ up to the
   delivery-charge litres) within 1 %;
2. per period: an invoice clearly larger than one delivery takes the sessions left unmatched between the
   previous such invoice and its bill date (aggregated supplier invoices);
3. sessions after the last invoice are "not invoiced yet"; others without an invoice, and invoices without a
   session, are exceptions to review."""

import re

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, strip_html

from card.report_access import _role_reads, assert_report_role, permitted_companies, query_companies

REPORT = "Diesel Invoice Reconciliation"
DOCTYPES = ("Project Diesel Fill", "Purchase Invoice")
# Arabic-Indic / Persian digits, Arabic thousands (٬) and decimal (٫) separators
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٬٫", "01234567890123456789,.")
# a number (thousands separated by commas, decimals by a point) followed by a litre word
LITRES = re.compile(
	r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*(?:لتر|ltr|litres?|liters?|l\b)", re.IGNORECASE
)
DIESEL_WORDS = ("ديزل", "سولار", "diesel")
DELIVERY_WORDS = ("نقل", "توصيل", "transport", "delivery")
OTHER_FUEL_WORDS = ("بنزين", "petrol", "gasoline")
PRICE_TOLERANCE = 0.002  # per litre
AGGREGATE_FACTOR = 1.5  # an invoice above 1.5 x the largest session is an aggregated invoice

# match rules (codes; the report translates them for display)
LINKED, EQUAL, FOLDED, AMOUNT_GROSS, AMOUNT_NET, PERIOD = (
	"linked",
	"equal",
	"folded",
	"amount_gross",
	"amount_net",
	"period",
)


def line_text(line):
	"""The text of an invoice line: its item name and its description (a Desk line on an item keeps the
	item master's name in item_name and the typed text in the description)."""
	parts = [line.get("item_name") or "", strip_html(line.get("description") or "")]
	return " ".join(p for i, p in enumerate(parts) if p and p not in parts[:i])


def line_litres(text):
	"""The litres stated in an invoice line text, or None."""
	m = LITRES.search((text or "").translate(DIGITS))
	return flt(m.group(1).replace(",", "")) if m else None


def line_kind(text):
	"""diesel / delivery / other fuel / other. A line naming diesel is diesel even when it also names the
	delivery ("ديزل شامل التوصيل"); a delivery line names no fuel."""
	text = (text or "").lower()
	if any(w in text for w in DIESEL_WORDS):
		return "diesel"
	if any(w in text for w in DELIVERY_WORDS):
		return "delivery"
	if any(w in text for w in OTHER_FUEL_WORDS):
		return "other fuel"
	return "other"


def invoice_figures(inv, lines, taxes):
	"""Litres, amounts and VAT of one Purchase Invoice (company currency), read from its own lines and tax
	rows."""
	diesel_amount = delivery_amount = other_amount = 0.0
	diesel_litres = delivery_litres = 0.0
	litres_stated = True
	projects = set()
	equipment = set()
	unallocated = 0
	for line in lines:
		text = line_text(line)
		kind = line_kind(text)
		litres = line_litres(text)
		amount = flt(line.get("base_amount") if line.get("base_amount") is not None else line.amount)
		if kind == "diesel":
			diesel_amount += amount
			if litres is None:
				litres_stated = False
			else:
				diesel_litres += litres
		elif kind == "delivery":
			delivery_amount += amount
			delivery_litres += litres or 0
		else:
			other_amount += amount
		if line.get("card_equipment"):
			equipment.add(line.card_equipment)
		if line.project:
			projects.add(line.project)
		else:
			unallocated += 1
	vat = sum(
		flt(t.get("base_tax_amount") if t.get("base_tax_amount") is not None else t.tax_amount)
		for t in taxes
		if t.add_deduct_tax != "Deduct"
	)
	net = flt(inv.get("base_net_total") if inv.get("base_net_total") is not None else inv.net_total)
	gross = flt(inv.get("base_grand_total") if inv.get("base_grand_total") is not None else inv.grand_total)
	return frappe._dict(
		net=flt(net, 2),
		gross=flt(gross, 2),
		diesel_amount=flt(diesel_amount, 2),
		delivery_amount=flt(delivery_amount, 2),
		other_amount=flt(other_amount, 2),
		diesel_litres=diesel_litres if litres_stated and diesel_amount else None,
		delivery_litres=delivery_litres,
		vat=flt(vat, 2),
		vat_pct=flt(100 * vat / net, 2) if net else 0,
		projects=sorted(projects),
		# None when the Card Equipment dimension is not on Purchase Invoice Item (nothing to compare)
		equipment=sorted(equipment) if lines and "card_equipment" in lines[0] else None,
		lines_without_project=unallocated,
	)


def vat_basis(fig, session_price):
	"""Inclusive / Exclusive / Unverified, from this invoice's diesel and delivery lines (other lines left
	out) and its VAT rate, against the session price."""
	litres = (fig.diesel_litres or 0) + (fig.delivery_litres or 0)
	if not fig.diesel_litres or not session_price:
		return _("Unverified (no litres on the invoice)")
	net = (fig.diesel_amount + fig.delivery_amount) / litres
	gross = net * (1 + fig.vat / fig.net) if fig.net else net
	if abs(gross - session_price) <= PRICE_TOLERANCE:
		return _("VAT-inclusive price")
	if abs(net - session_price) <= PRICE_TOLERANCE:
		return _("VAT-exclusive price")
	return _("Unverified (price per litre {0} gross, {1} net)").format(flt(gross, 4), flt(net, 4))


def _bill_date(inv):
	return getdate(inv.bill_date or inv.posting_date)


def _delivery_match(session, inv, fig, window, max_delivery):
	"""(rank, rule, detail) when `inv` can be the delivery invoice of `session`, else None. The rank prefers
	the nearest date, then the later one (a same-day invoice before the day before)."""
	gap = (_bill_date(inv) - getdate(session.date)).days
	if not -1 <= gap <= window:
		return None
	rank = (abs(gap), -gap)
	litres = flt(session.litres)
	if fig.diesel_litres is not None:
		diff = flt(fig.diesel_litres - litres, 3)
		if abs(diff) <= 0.5:
			return (rank, EQUAL, None)
		if 0 < diff <= max_delivery and not fig.delivery_amount:
			return (rank, FOLDED, diff)
		return None
	price = flt(session.unit_price)
	if not price:
		return None
	for rule, total in ((AMOUNT_GROSS, fig.gross), (AMOUNT_NET, fig.net)):
		implied = total / price
		if litres <= implied <= (litres + max_delivery) * 1.01:
			return ((rank[0] + 0.5, rank[1]), rule, flt(implied, 1))
	return None


def reconcile(sessions, invoices, figures, window=3, max_delivery=60):
	"""Pure matching of sessions to invoices. Returns (session_match, invoice_sessions, periods):
	session_match {fill: (invoice, rule, detail)}, invoice_sessions {invoice: [fills]},
	periods [(invoice, [fills], from_date)] for aggregated invoices."""
	sessions = sorted(sessions, key=lambda s: (getdate(s.date), s.name))
	invoices = sorted(invoices, key=lambda i: (_bill_date(i), i.name))
	names = {i.name for i in invoices}
	session_match, invoice_sessions, used = {}, {}, set()
	for s in sessions:
		if s.get("purchase_invoice") in names:
			session_match[s.name] = (s.purchase_invoice, LINKED, None)
			invoice_sessions.setdefault(s.purchase_invoice, []).append(s.name)
			used.add(s.purchase_invoice)
	for exact in (True, False):
		for s in sessions:
			if s.name in session_match:
				continue
			best = None
			for inv in invoices:
				if inv.name in used:
					continue
				m = _delivery_match(s, inv, figures[inv.name], window, max_delivery)
				if m and (not exact or m[1] == EQUAL) and (best is None or m[0] < best[0][0]):
					best = (m, inv)
			if best:
				used.add(best[1].name)
				session_match[s.name] = (best[1].name, best[0][1], best[0][2])
				invoice_sessions[best[1].name] = [s.name]
	largest = max((flt(s.litres) for s in sessions), default=0)
	periods, start = [], None
	for inv in invoices:
		if inv.name in used:
			continue
		fig = figures[inv.name]
		end = _bill_date(inv)
		# the price of the latest session up to the invoice (prices can change during the period)
		before = [s for s in sessions if getdate(s.date) <= end] or sessions
		price = flt(before[-1].unit_price) if before else 0
		litres = fig.diesel_litres if fig.diesel_litres is not None else (fig.gross / price if price else 0)
		if not largest or litres < AGGREGATE_FACTOR * largest:
			continue
		taken = [
			s.name
			for s in sessions
			if s.name not in session_match
			and (start is None or getdate(s.date) > start)
			and getdate(s.date) <= end
		]
		for name in taken:
			session_match[name] = (inv.name, PERIOD, None)
		used.add(inv.name)
		invoice_sessions[inv.name] = taken
		periods.append((inv.name, taken, start))
		start = end
	return session_match, invoice_sessions, periods


def load(company, suppliers, from_date, to_date, window, submitted_only=False):
	"""Sessions and invoices of `suppliers` in `company` for the period (invoice bill dates from the day
	before the period to `window` days after it). Draft sessions are included unless `submitted_only`;
	each row keeps its docstatus. `frappe.get_list` applies the user's permissions (User Permissions on
	Supplier, Project, ... included); child rows follow the invoices the user may read."""
	sessions = frappe.get_list(
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
			"purchase_invoice",
		],
		order_by="date asc, name asc",
		limit_page_length=0,
	)
	first, last = add_days(from_date, -1), add_days(to_date, window)
	fields = [
		"name",
		"supplier",
		"posting_date",
		"bill_no",
		"bill_date",
		"net_total",
		"grand_total",
		"base_net_total",
		"base_grand_total",
		"project",
		"cost_center",
	]
	base = {"company": company, "supplier": ["in", suppliers], "docstatus": 1, "is_return": 0}
	invoices = frappe.get_list(
		"Purchase Invoice",
		filters={**base, "bill_date": ["between", [first, last]]},
		fields=fields,
		limit_page_length=0,
	) + frappe.get_list(
		"Purchase Invoice",
		filters={**base, "bill_date": ["is", "not set"], "posting_date": ["between", [first, last]]},
		fields=fields,
		limit_page_length=0,
	)
	invoices.sort(key=lambda i: (_bill_date(i), i.name))
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
				"base_amount",
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
			fields=["parent", "tax_amount", "base_tax_amount", "add_deduct_tax"],
			limit_page_length=0,
		):
			taxes[row.parent].append(row)
	return sessions, invoices, lines, taxes


def assert_report_access():
	"""The user may run this report: one of its roles, and roles that read both doctypes."""
	if frappe.session.user != "Administrator" and not frappe.get_cached_doc("Report", REPORT).is_permitted():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	for doctype in DOCTYPES:
		if not _role_reads(doctype):
			frappe.throw(
				_("You need read access to {0} to run this report").format(_(doctype)), frappe.PermissionError
			)


@frappe.whitelist(methods=["GET"])
def diesel_supplier_options(txt: str | None = None, company: str | None = None):
	"""Options for the report's supplier filter: suppliers of diesel sessions the user may read, in the
	companies the user may see for both doctypes (a list, not a Link to the Supplier master: report Link
	filters are checked against the user's own permissions)."""
	assert_report_role()
	assert_report_access()
	allowed = set(permitted_companies(*DOCTYPES))
	companies = [
		c for c in query_companies({"company": company} if company else {}, DOCTYPES[0]) if c in allowed
	]
	if not companies:
		return []
	suppliers = frappe.get_list(
		"Project Diesel Fill",
		filters={"company": ["in", companies], "docstatus": ["<", 2], "supplier": ["like", f"%{txt or ''}%"]},
		pluck="supplier",
		distinct=True,
		order_by="supplier asc",
		limit_page_length=50,
	)
	return [{"value": s, "description": ""} for s in suppliers if s]
