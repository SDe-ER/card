# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""PDF of the Equipment Customer Statement with the Frappe Chrome PDF generator.

The customer mirror of the supplier statement's ``statement_pdf`` (issue #324: the
standard report PDF uses wkhtmltopdf, which breaks Arabic letter joins). The
report's PDF action posts only the filters. The server runs the report with the
user's permissions, builds the statement HTML itself (the same markup as the
"Equipment Customer Statement A4" print format, with the CSS read from the
report's print template) and renders it with ``frappe.utils.pdf.get_chrome_pdf``.

The endpoint never accepts HTML from the browser: the Chrome generator runs the
page's JavaScript and lets requests to other hosts through, so client HTML could
make the server fetch internal addresses."""

import functools
import math
import re

import frappe
from frappe import _
from frappe.core.doctype.access_log.access_log import make_access_log
from frappe.desk.query_report import get_report_doc, run
from frappe.utils import flt, formatdate, today
from frappe.utils.jinja_globals import is_rtl

from card.card.report.equipment_supplier_statement.statement_pdf import (
	PAGE_MARGINS,
	_meta_row,
	_num,
	_num_css,
	_period,
	_totals_width,
)
from card.report_access import resolve_company
from card.settings import setting

REPORT = "Equipment Customer Statement"
TEMPLATE = ("card", "card", "report", "equipment_customer_statement", "equipment_customer_statement.html")

# the columns of the "Equipment Customer Statement A4" print format: fieldname, width, kind
FIELDS = (
	("label", 22, "text"),
	("first_date", 8.5, "date"),
	("last_date", 8.5, "date"),
	("working_days", 5, "int"),
	("hours", 7, "num"),
	("customer_rate_type", 7, "type"),
	("customer_rate", 8, "num"),
	("customer_amount", 9, "num"),
	("additions", 7, "num"),
	("deductions", 7, "num"),
	("net", 8, "num"),
)
OPTIONAL_FIELDS = ("additions", "deductions")
STOPPED_HOURS = ("stopped_hours", 7, "num")
# FR-166: a card billed per m3 prints its loads and its volume after the hours
QUANTITY_FIELDS = (("total_loads", 6, "int"), ("total_volume_m3", 7, "num"))
# FR-178: the report sends no money column to a user who cannot read the card amounts; the print follows it
MONEY_FIELDS = ("customer_rate", "customer_amount", "additions", "deductions", "net", "total_volume_m3")
# the printed totals: the cards net and, when positive, the part not yet invoiced through CARD
TOTAL_KEYS = ("net_cards", "not_invoiced")
# the report's Link filters (script report filters live in its JS): frappe checks the user may read each value
LINK_FILTERS = [
	{"fieldname": "customer", "fieldtype": "Link", "options": "Card Equipment Customer"},
	{"fieldname": "equipment", "fieldtype": "Link", "options": "Card Equipment"},
	{"fieldname": "equipment_type", "fieldtype": "Link", "options": "Card Equipment Type"},
]


@frappe.whitelist(methods=["POST"])
def download_pdf(filters: str | dict | None = None):
	"""Send the statement as a PDF file (Chrome generator). Same permissions as
	running and printing the report; the company is checked by the report."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	if not isinstance(filters, dict):
		frappe.throw(_("Invalid filters"))
	filters = frappe._dict(filters)
	# filter values are plain values only: a list or object never reaches the page given to Chrome
	if any(isinstance(value, list | dict) for value in filters.values()):
		frappe.throw(_("Invalid filters"))
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
	html = build_html(filters, result.get("columns"), result.get("result"), result.get("report_summary"))
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


def build_html(filters, columns, data, summary):
	esc = frappe.utils.escape_html
	label_of = {c.get("fieldname"): c.get("label") for c in columns or [] if c and c.get("fieldname")}
	rows = [r for r in data or [] if r]
	fields = _shown_fields(rows, label_of)
	totals_width = _totals_width(fields, "customer_rate")
	totals = _totals(summary or [])

	company = filters.get("company") or ""
	direction = "rtl" if is_rtl() else "ltr"
	draft_mark = _("(Draft)")
	has_draft = bool(filters.get("include_draft")) or any(
		r.get("card") and draft_mark in str(r.get("label") or "") for r in rows
	)

	out = [f'<div class="ess" dir="{direction}">']
	out.append(f'<div class="ess-co">{esc(company)}</div>')
	out.append(f'<div class="ess-title"><h2>{esc(_(REPORT))}</h2></div>')
	out.append('<table class="ess-meta">')
	out.append(_meta_row(_("Company"), company, _("Customer"), filters.get("customer") or ""))
	out.append(_meta_row(_("Issue date"), formatdate(today()), "", ""))
	period_from, period_to = _period(_months_only(filters))
	out.append(_meta_row(_("From"), period_from, _("To"), period_to))
	out.append("</table>")
	if has_draft:
		out.append(f'<p class="ess-note"><b>{esc(_("Includes draft cards"))}</b></p>')
	if not filters.get("customer"):
		note = _("Select a customer to display the statement.")
		out.append(f'<p class="ess-note"><b>{esc(note)}</b></p>')

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
			cell_css = (
				"ess-num" if kind == "num" else ("ess-c" if kind in ("int", "date", "type") else "ess-t")
			)
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

	out.append('<div class="ess-end"><table class="ess-signs"><tr>')
	for sign in (_("Accountant signature"), _("Reviewer signature"), _("Customer signature")):
		out.append(f'<td><span class="ess-line"></span>{esc(sign)}</td>')
	out.append("</tr></table>")
	issued = _("Issued by the electronic system of {0}").format(company)
	out.append(f'<p class="ess-issued">{esc(issued)}</p></div></div>')

	lang = esc(frappe.local.lang or "en")
	return (
		f'<!DOCTYPE html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
		f"<title>{esc(_(REPORT))}</title>{template_style()}</head><body>{''.join(out)}</body></html>"
	)


def _months_only(filters):
	"""The customer statement is by month: a date filter sent by a caller never changes the printed period."""
	return {k: v for k, v in filters.items() if k not in ("from_date", "to_date")}


def _has_value(rows, fieldname):
	return any(flt(r.get(fieldname)) for r in rows)


def _shown_fields(rows, label_of):
	"""The column set of the print format: stopped hours, loads and volume only when a row has them;
	additions and deductions only when used; no money column the report withheld. The shown columns
	share 97% of the table ('#' takes 3%)."""
	fields = []
	for field in FIELDS:
		fields.append(field)
		if field[0] == "hours":
			if _has_value(rows, STOPPED_HOURS[0]):
				fields.append(STOPPED_HOURS)
			fields.extend(q for q in QUANTITY_FIELDS if _has_value(rows, q[0]))
	shown = [
		f
		for f in fields
		if not (f[0] in MONEY_FIELDS and f[0] not in label_of)
		and (f[0] not in OPTIONAL_FIELDS or _has_value(rows, f[0]))
	]
	total = sum(f[1] for f in shown)
	return [(f[0], math.floor(f[1] * 9700 / total + 0.5) / 100, f[2]) for f in shown]


def _totals(summary):
	"""Picked by the stable keys only; the reconciliation and ledger items stay on the screen report."""
	by_key = {s["key"]: s for s in summary if s and s.get("key")}
	labels = {
		"net_cards": _("Cards net for the period"),
		"not_invoiced": _("Work done not yet invoiced (before VAT)"),
	}
	totals = []
	for key in TOTAL_KEYS:
		item = by_key.get(key)
		if not item:
			continue
		if key == "not_invoiced" and not flt(item.get("value")) > 0:
			continue
		totals.append({"label": labels[key], "value": item.get("value"), "datatype": item.get("datatype")})
	return totals


def _cell(row, field):
	fieldname, _width, kind = field
	value = row.get(fieldname)
	if kind == "date":
		return frappe.utils.escape_html(formatdate(value)) if value else ""
	if kind == "num":
		return _num(value)
	if kind == "int":
		return "" if value is None else frappe.utils.escape_html(str(value))
	if kind == "type":
		# the rate type is stored as its Arabic option value; the print shows it in the user's language
		return frappe.utils.escape_html(_(str(value))) if value else ""
	if fieldname == "label" and row.get("card") and row.get("shift"):
		value = (value or "") + " — " + _(row.get("shift"))
	return frappe.utils.escape_html("" if value is None else str(value))
