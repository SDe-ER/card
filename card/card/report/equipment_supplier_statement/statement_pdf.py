# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""PDF of the Equipment Supplier Statement with the Frappe Chrome PDF generator.

The report's PDF action posts only the filters. The server runs the report with
the user's permissions, builds the statement HTML itself (the same markup as the
browser print template, with the CSS read from that template) and renders it with
``frappe.utils.pdf.get_chrome_pdf`` — the generator the CARD print formats use,
which shapes Arabic correctly (the standard report PDF uses wkhtmltopdf).

The endpoint never accepts HTML from the browser: the Chrome generator runs the
page's JavaScript and lets requests to other hosts through, so client HTML could
make the server fetch internal addresses."""

import calendar
import functools
import math
import re

import frappe
from frappe import _
from frappe.core.doctype.access_log.access_log import make_access_log
from frappe.desk.query_report import get_report_doc, run
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, today
from frappe.utils.jinja_globals import is_rtl

from card.report_access import resolve_company
from card.settings import setting

REPORT = "Equipment Supplier Statement"
TEMPLATE = ("card", "card", "report", "equipment_supplier_statement", "equipment_supplier_statement.html")

MONEY_FIELDS = (
	("label", 25, "text"),
	("first_date", 9, "date"),
	("last_date", 9, "date"),
	("working_days", 6, "int"),
	("hours", 8, "num"),
	("hourly_rate", 8, "num"),
	("amount", 9, "num"),
	("additions", 7.5, "num"),
	("deductions", 7.5, "num"),
	("net", 8, "num"),
)
OWNED_FIELDS = (
	("label", 46, "text"),
	("first_date", 13, "date"),
	("last_date", 13, "date"),
	("working_days", 11, "int"),
	("hours", 14, "num"),
)
OPTIONAL_FIELDS = ("additions", "deductions")
KEY_ORDER = {
	11: (
		"equipment",
		"days",
		"hours",
		"net_cards",
		"accrued",
		"invoiced",
		"not_invoiced",
		"outside",
		"opening",
		"paid",
		"closing",
	),
	4: ("equipment", "days", "hours", "net_cards"),
}
# the report's Link filters (script report filters live in its JS): frappe checks the user may read each value
LINK_FILTERS = [
	{"fieldname": "supplier", "fieldtype": "Link", "options": "Card Equipment Supplier"},
	{"fieldname": "equipment", "fieldtype": "Link", "options": "Card Equipment"},
	{"fieldname": "equipment_type", "fieldtype": "Link", "options": "Card Equipment Type"},
]
PAGE_MARGINS = {"margin-top": "10mm", "margin-bottom": "10mm", "margin-left": "10mm", "margin-right": "10mm"}


@frappe.whitelist(methods=["POST"])
def download_pdf(filters: str | dict | None = None):
	"""Send the statement as a PDF file (Chrome generator). Same permissions as
	running and printing the report; the company is checked by the report."""
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	report = get_report_doc(REPORT)
	if not frappe.has_permission(report.ref_doctype, "print"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters.company = resolve_company(filters)

	# the standard report run: report and filter-value permissions, rows filtered by the user's permissions
	result = run(
		REPORT, filters=frappe.as_json(filters), ignore_prepared_report=True, js_filters=LINK_FILTERS
	)
	if filters.get("include_draft") is None:
		# the same fallback as the report, so the print says when draft cards are included
		filters.include_draft = setting("include_draft_in_reports")
	html = build_html(
		filters,
		result.get("columns"),
		result.get("result"),
		result.get("message"),
		result.get("report_summary"),
	)
	make_access_log(report_name=REPORT, file_type="PDF", method="PDF", filters=frappe.as_json(filters))

	from frappe.utils.pdf import get_chrome_pdf

	pdf = get_chrome_pdf(None, html, dict(PAGE_MARGINS), None, pdf_generator="chrome")
	if not pdf:
		frappe.throw(_("The PDF could not be created. Check the Chrome PDF generator."))
	frappe.local.response.filename = _(REPORT) + ".pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


@functools.cache
def template_style():
	"""The <style> block of the browser print template (one source for both paths)."""
	template = frappe.read_file(frappe.get_app_path(*TEMPLATE)) or ""
	match = re.search(r"<style>.*?</style>", template, flags=re.S)
	if not match:
		frappe.throw(_("The statement print template has no style block."))
	return match.group(0)


def build_html(filters, columns, data, message, summary):
	esc = frappe.utils.escape_html
	label_of = {c.get("fieldname"): c.get("label") for c in columns or [] if c and c.get("fieldname")}
	money = bool(label_of.get("net"))
	rows = [r for r in data or [] if r]

	fields = _shown_fields(MONEY_FIELDS if money else OWNED_FIELDS, rows)
	totals_width = _totals_width(fields, "hourly_rate" if money else "last_date")
	totals = _totals(summary or [], money)

	stype = filters.get("statement_type") or ("مورد" if money else "معدات ملك")
	stype = {"مورد": _("Supplier"), "معدات ملك": _("Owned equipment")}.get(stype, stype)
	company = filters.get("company") or ""
	direction = "rtl" if is_rtl() else "ltr"

	out = [f'<div class="ess" dir="{direction}">']
	out.append(f'<div class="ess-co">{esc(company)}</div>')
	out.append(f'<div class="ess-title"><h2>{esc(_(REPORT))}</h2></div>')
	out.append('<table class="ess-meta">')
	out.append(_meta_row(_("Company"), company, _("Statement type"), stype))
	out.append(_meta_row(_("Supplier"), filters.get("supplier") or "", _("Issue date"), formatdate(today())))
	period_from, period_to = _period(filters)
	out.append(_meta_row(_("From"), period_from, _("To"), period_to))
	out.append("</table>")
	if filters.get("include_draft"):
		out.append(f'<p class="ess-note"><b>{esc(_("Includes draft cards"))}</b></p>')
	if message and len(rows) < 2:
		out.append(f'<p class="ess-note">{esc(str(message))}</p>')

	out.append('<table class="ess-rows"><thead><tr><th style="width: 3%">#</th>')
	for fieldname, width, _kind in fields:
		out.append(f'<th style="width: {_num_css(width)}%">{esc(label_of.get(fieldname) or "")}</th>')
	out.append("</tr></thead><tbody>")
	n = 0
	parents = {r.get("parent_row") for r in rows}
	for row in rows:
		is_total = row.get("row_id") == "TOTAL"
		is_group = not is_total and not row.get("indent")
		is_eq = not is_total and row.get("indent") == 1 and row.get("row_id") in parents
		numbered = not is_total and not is_group and not is_eq
		if numbered:
			n += 1
		css = "ess-total" if is_total else ("ess-group" if is_group else ("ess-eq" if is_eq else "ess-card"))
		out.append(f'<tr class="{css}"><td class="ess-c">{n if numbered else ""}</td>')
		for field in fields:
			kind = field[2]
			cell_css = "ess-num" if kind == "num" else ("ess-c" if kind in ("int", "date") else "ess-t")
			out.append(f'<td class="{cell_css}">{_cell(row, field)}</td>')
		out.append("</tr>")
	out.append("</tbody></table>")

	if totals:
		out.append(f'<table class="ess-totals" style="width: {_num_css(totals_width)}%">')
		out.append(f'<thead><tr><th colspan="2">{esc(_("Statement totals"))}</th></tr></thead><tbody>')
		for item in totals:
			value = item.get("value")
			if item.get("datatype") == "Int":
				shown = esc("" if value is None else str(value))
			else:
				shown = _num(value)
			out.append(
				f'<tr><td class="ess-k">{esc(item.get("label") or "")}</td><td class="ess-v">{shown}</td></tr>'
			)
		out.append("</tbody></table>")

	signs = [_("Accountant signature"), _("Reviewer signature")]
	if money:
		signs.append(_("Supplier signature"))
	out.append('<div class="ess-end"><table class="ess-signs"><tr>')
	for sign in signs:
		out.append(f'<td><span class="ess-line"></span>{esc(sign)}</td>')
	out.append("</tr></table>")
	issued = _("Issued by the electronic system of {0}").format(company)
	out.append(f'<p class="ess-issued">{esc(issued)}</p></div></div>')

	lang = esc(frappe.local.lang or "en")
	return (
		f'<!DOCTYPE html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
		f"<title>{esc(_(REPORT))}</title>{template_style()}</head><body>{''.join(out)}</body></html>"
	)


def _shown_fields(fields, rows):
	"""Additions and deductions print only when a row has a value; the other
	columns share the freed width (97% of the table; '#' takes 3%)."""
	shown = [f for f in fields if f[0] not in OPTIONAL_FIELDS or any(flt(r.get(f[0])) for r in rows)]
	total = sum(f[1] for f in shown)
	return [(f[0], math.floor(f[1] * 9700 / total + 0.5) / 100, f[2]) for f in shown]


def _totals_width(fields, start):
	width = 0
	counting = False
	for fieldname, field_width, _kind in fields:
		if fieldname == start:
			counting = True
		if counting:
			width += field_width
	return max(35, min(60, math.floor(width + 0.5)))


def _totals(summary, money):
	by_key = {s["key"]: s for s in summary if s and s.get("key")}
	order = KEY_ORDER.get(len(summary), ("equipment", "days", "hours"))
	for item, key in zip(summary, order, strict=False):
		if item and not item.get("key") and key not in by_key:
			by_key[key] = item
	labels = {
		"net_cards": _("Cards net for the period"),
		"not_invoiced": _("Work done not yet invoiced (before VAT)"),
	}
	totals = []
	for key in ("net_cards", "not_invoiced") if money else ("equipment", "days", "hours"):
		item = by_key.get(key)
		if not item:
			continue
		if key == "not_invoiced" and not flt(item.get("value")) > 0:
			continue
		totals.append(
			{
				"label": labels.get(key) or item.get("label"),
				"value": item.get("value"),
				"datatype": item.get("datatype"),
			}
		)
	return totals or [s for s in summary if s]


def _period(filters):
	"""First day of the start month to the last day of the end month."""

	def day(month, year, last):
		month, year = cint(month), cint(year)
		if not month or not year:
			return ""
		d = calendar.monthrange(year, month)[1] if last else 1
		return formatdate(getdate(f"{year}-{month:02d}-{d:02d}"))

	to_month = filters.get("to_month") or filters.get("from_month")
	to_year = filters.get("to_year") or filters.get("from_year")
	return day(filters.get("from_month"), filters.get("from_year"), False), day(to_month, to_year, True)


def _meta_row(label1, value1, label2, value2):
	esc = frappe.utils.escape_html
	return (
		f'<tr><td class="ess-ml">{esc(label1)}</td><td>{esc(value1)}</td>'
		f'<td class="ess-ml">{esc(label2)}</td><td>{esc(value2)}</td></tr>'
	)


def _cell(row, field):
	fieldname, _width, kind = field
	value = row.get(fieldname)
	if kind == "date":
		return formatdate(value) if value else ""
	if kind == "num":
		return _num(value)
	if kind == "int":
		return "" if value is None else frappe.utils.escape_html(str(value))
	if fieldname == "label" and row.get("card") and row.get("shift"):
		value = (value or "") + " — " + _(row.get("shift"))
	return frappe.utils.escape_html("" if value is None else str(value))


def _num(value):
	return "" if value is None or value == "" else fmt_money(flt(value), precision=2)


def _num_css(value):
	return f"{value:g}"
