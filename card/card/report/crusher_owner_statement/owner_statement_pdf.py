# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""A4 PDF of the Crusher Owner Statement, on the build path of the Equipment Supplier Statement A4:
the server runs the report with the user's permissions, builds the page itself with the approved
statement design (the same style block: Frappe grays, label/value grid, totals table under the amount
columns, signatures, RTL) and renders it with ``frappe.utils.pdf.get_chrome_pdf``.

The endpoint never accepts HTML from the browser (see ``statement_pdf``). Empty optional columns are
not printed; the system's name is never printed."""

import math

import frappe
from frappe import _
from frappe.core.doctype.access_log.access_log import make_access_log
from frappe.desk.query_report import get_report_doc, run
from frappe.utils import flt, formatdate, today
from frappe.utils.jinja_globals import is_rtl

from card import owner_statement as os_
from card.card.report.equipment_supplier_statement.statement_pdf import (
	PAGE_MARGINS,
	_meta_row,
	_num,
	_num_css,
	template_style,
)
from card.report_access import resolve_company

REPORT = "Crusher Owner Statement"
# (fieldname, width weight, kind, optional)
ROW_FIELDS = (
	("label", 22, "text", False),
	("cards", 14, "text", False),
	("customer_net", 9, "num", False),
	("conditional_gross", 8, "num", True),
	("approved_amount", 8, "num", True),
	("confirmed_revenue", 9, "num", False),
	("pending_potential", 8, "num", True),
	("company_rows", 8, "num", True),
	("expenses", 8, "num", True),
	("wages", 8, "num", True),
	("shared_expenses", 8, "num", True),
	("paid_on_behalf", 8, "num", True),
	("other_deductions", 8, "num", True),
	("deductions", 9, "num", False),
	("entitlement", 9, "num", False),
)
LEDGER_FIELDS = (
	("label", 34, "text"),
	("voucher_no", 24, "text"),
	("account", 26, "text"),
	("ledger_amount", 16, "num"),
)
TOTAL_KEYS = ("confirmed", "pending", "deductions", "entitlement", "opening", "paid", "duplicates", "closing")
LINK_FILTERS = [
	{"fieldname": "owner", "fieldtype": "Link", "options": "Card Equipment Supplier"},
	{"fieldname": "family", "fieldtype": "Link", "options": "Supplier Group"},
	{"fieldname": "equipment", "fieldtype": "Link", "options": "Card Equipment"},
]


@frappe.whitelist(methods=["POST"])
def download_pdf(filters: str | dict | None = None):
	"""Send the statement as an A4 PDF (Chrome generator); same permissions as running and printing
	the report. The company is checked by the report."""
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	if any(isinstance(value, list | dict) for value in filters.values()):
		frappe.throw(_("Invalid filters"))
	report = get_report_doc(REPORT)
	if not frappe.has_permission(report.ref_doctype, "print"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters.company = resolve_company(filters)
	result = run(
		REPORT, filters=frappe.as_json(filters), ignore_prepared_report=True, js_filters=LINK_FILTERS
	)
	html = build_html(filters, result.get("columns"), result.get("result"), result.get("report_summary"))
	make_access_log(report_name=REPORT, file_type="PDF", method="PDF", filters=frappe.as_json(filters))

	from frappe.utils.pdf import get_chrome_pdf

	pdf = get_chrome_pdf(None, html, dict(PAGE_MARGINS), None, pdf_generator="chrome")
	if not pdf:
		frappe.throw(_("The PDF could not be created. Check the Chrome PDF generator."))
	frappe.local.response.filename = _(REPORT) + ".pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def build_html(filters, columns, data, summary):
	esc = frappe.utils.escape_html
	label_of = {c.get("fieldname"): c.get("label") for c in columns or [] if c and c.get("fieldname")}
	rows = [r for r in data or [] if r]
	statement_rows = [r for r in rows if "|L|" not in (r.get("row_id") or "")]
	ledger_rows = [r for r in rows if "|L|" in (r.get("row_id") or "")]
	fields = _shown(ROW_FIELDS, statement_rows, label_of)
	company = filters.get("company") or ""
	direction = "rtl" if is_rtl() else "ltr"
	start, end = os_.period(
		filters.get("from_month"), filters.get("from_year"), filters.get("to_month"), filters.get("to_year")
	)

	out = [f'<div class="ess" dir="{direction}">']
	out.append(f'<div class="ess-co">{esc(company)}</div>')
	out.append(f'<div class="ess-title"><h2>{esc(_(REPORT))}</h2></div>')
	out.append('<table class="ess-meta">')
	out.append(_meta_row(_("Company"), company, _("Issue date"), formatdate(today())))
	family = filters.get("family") or ""
	out.append(
		_meta_row(
			_("Owner"), filters.get("owner") or "", _("Family settlement group") if family else "", family
		)
	)
	out.append(_meta_row(_("From"), formatdate(start), _("To"), formatdate(end)))
	out.append("</table>")
	note = _(
		"Amounts before VAT; VAT is the company's. Draft months and pending or disputed amounts are not in the dues."
	)
	out.append(f'<p class="ess-note">{esc(note)}</p>')

	out.append('<table class="ess-rows"><thead><tr><th style="width: 3%">#</th>')
	for fieldname, width, _kind in fields:
		out.append(f'<th style="width: {_num_css(width)}%">{esc(label_of.get(fieldname) or "")}</th>')
	out.append("</tr></thead><tbody>")
	n = 0
	for row in statement_rows:
		month = "|M|" in (row.get("row_id") or "")
		css = "ess-card" if month else ("ess-group" if not row.get("indent") else "ess-eq")
		if month:
			n += 1
		out.append(f'<tr class="{css}"><td class="ess-c">{n if month else ""}</td>')
		for fieldname, _width, kind in fields:
			value = row.get(fieldname)
			cell = _num(value) if kind == "num" else esc("" if value is None else str(value))
			out.append(f'<td class="{"ess-num" if kind == "num" else "ess-t"}">{cell}</td>')
		out.append("</tr>")
	out.append("</tbody></table>")

	if ledger_rows:
		out.append('<table class="ess-rows"><thead><tr><th style="width: 3%">#</th>')
		for fieldname, width, _kind in _spread(LEDGER_FIELDS):
			out.append(f'<th style="width: {_num_css(width)}%">{esc(label_of.get(fieldname) or "")}</th>')
		out.append("</tr></thead><tbody>")
		for i, row in enumerate(ledger_rows, start=1):
			out.append(f'<tr class="ess-card"><td class="ess-c">{i}</td>')
			for fieldname, _width, kind in LEDGER_FIELDS:
				value = row.get(fieldname)
				cell = _num(value) if kind == "num" else esc("" if value is None else str(value))
				out.append(f'<td class="{"ess-num" if kind == "num" else "ess-t"}">{cell}</td>')
			out.append("</tr>")
		out.append("</tbody></table>")

	totals = [s for key in TOTAL_KEYS for s in summary or [] if s and s.get("key") == key]
	if totals:
		width = max(
			35, min(60, math.floor(sum(w for f, w, _k in fields if f not in ("label", "cards")) + 0.5))
		)
		out.append(f'<table class="ess-totals" style="width: {_num_css(width)}%">')
		out.append(f'<thead><tr><th colspan="2">{esc(_("Statement totals"))}</th></tr></thead><tbody>')
		for item in totals:
			out.append(
				f'<tr><td class="ess-k">{esc(item.get("label") or "")}</td><td class="ess-v">{_num(item.get("value"))}</td></tr>'
			)
		out.append("</tbody></table>")

	out.append('<div class="ess-end"><table class="ess-signs"><tr>')
	for sign in (_("Accountant signature"), _("Reviewer signature"), _("Owner signature")):
		out.append(f'<td><span class="ess-line"></span>{esc(sign)}</td>')
	out.append("</tr></table>")
	issued = _("Issued by the electronic system of {0}").format(company)
	out.append(f'<p class="ess-issued">{esc(issued)}</p></div></div>')

	lang = esc(frappe.local.lang or "en")
	return (
		f'<!DOCTYPE html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
		f"<title>{esc(_(REPORT))}</title>{template_style()}</head><body>{''.join(out)}</body></html>"
	)


def _shown(fields, rows, label_of):
	"""Optional amount columns print only when a row has a value, and only columns the report
	returned (a user without ledger access gets no ledger column); widths share 97% of the table."""
	shown = [
		(f, w, k)
		for f, w, k, optional in fields
		if f in label_of and (not optional or any(flt(r.get(f)) for r in rows))
	]
	return _spread(shown)


def _spread(fields):
	total = sum(f[1] for f in fields) or 1
	return [(f[0], math.floor(f[1] * 9700 / total + 0.5) / 100, f[2]) for f in fields]
