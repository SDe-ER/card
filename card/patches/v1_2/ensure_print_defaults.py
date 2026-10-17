# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Make the professional CARD print formats the automatic print defaults and
ship a system Letter Head built from the Company record.

Everything here is idempotent and safe to re-run:

1. ``default_print_format`` Property Setters — one per CARD transaction
   doctype, pointing at the app's standard print formats ("Card Monthly Card
   Print", "Project Diesel Fill Print", "Equipment Transport Print"). This
   part needs no Company, so it always runs. A setter is created when missing
   and filled when its value is empty; any non-empty value is kept — including
   the legacy Card Monthly Card format ("كارت تشغيل شهري"), which stays the
   default on sites that have it (Owner decision 2026-10-17, until a real
   Arabic PDF of the new format is approved). The new formats stay selectable.

2. "CARD" Letter Head — created ONLY when the site has no Letter Head at
   all, built from the default/first Company entirely out of system data
   (company name, tax id, phone, logo — every optional column guarded with
   ``frappe.db.has_column``). If any Letter Head already exists it is left
   untouched. On a site without a Company this step is skipped (the patch
   never throws).
"""

import html

import frappe

PRINT_FORMAT_DEFAULTS = {
	"Card Monthly Card": "Card Monthly Card Print",
	"Project Diesel Fill": "Project Diesel Fill Print",
	"Equipment Transport": "Equipment Transport Print",
}

LETTER_HEAD_NAME = "CARD"
FONT_STACK = "'Segoe UI', Tahoma, Arial, sans-serif"


def execute():
	_ensure_default_print_formats()
	company = _get_company()
	if not company:
		# Site without a Company: nothing to build a Letter Head from.
		return
	_ensure_letter_head(company)


def _ensure_default_print_formats():
	"""Point each CARD doctype's default print format at the app's standard
	format via the Customize-Form mechanism (DocType-level Property Setter)."""
	for doctype, print_format in PRINT_FORMAT_DEFAULTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		existing = frappe.db.get_value(
			"Property Setter",
			{
				"doc_type": doctype,
				"doctype_or_field": "DocType",
				"property": "default_print_format",
			},
			["name", "value"],
			as_dict=True,
		)
		if existing:
			if not (existing.value or "").strip():
				frappe.db.set_value(
					"Property Setter", existing.name, "value", print_format, update_modified=False
				)
				frappe.clear_cache(doctype=doctype)
			continue
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocType",
				"doc_type": doctype,
				"property": "default_print_format",
				"property_type": "Data",
				"value": print_format,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype=doctype)


def _get_company():
	"""The site's default company, else the first company by creation."""
	default_company = frappe.defaults.get_global_default("default_company")
	if default_company and frappe.db.exists("Company", default_company):
		return default_company
	companies = frappe.get_all("Company", pluck="name", order_by="creation asc", limit=1)
	return companies[0] if companies else None


def _company_value(company, fieldname):
	"""A Company column's trimmed string value, or None (column guarded)."""
	if not frappe.db.has_column("Company", fieldname):
		return None
	value = frappe.db.get_value("Company", company, fieldname)
	value = str(value).strip() if value is not None else ""
	return value or None


def _ensure_letter_head(company):
	if frappe.db.count("Letter Head"):
		# A Letter Head already exists (any name): do nothing to it.
		return

	display_name = _company_value(company, "company_name") or company
	tax_id = _company_value(company, "tax_id")
	phone = _company_value(company, "phone_no")
	logo = _company_value(company, "company_logo")

	letter_head = frappe.get_doc(
		{
			"doctype": "Letter Head",
			"letter_head_name": LETTER_HEAD_NAME,
			"disabled": 0,
			"is_default": 1,
			"content": _header_html(display_name, tax_id, phone, logo),
		}
	)
	meta = frappe.get_meta("Letter Head")
	if meta.has_field("source"):
		letter_head.source = "HTML"
	footer = _footer_html(display_name, tax_id, phone)
	if footer and meta.has_field("footer"):
		letter_head.footer = footer
		if meta.has_field("footer_source"):
			letter_head.footer_source = "HTML"
	letter_head.insert(ignore_permissions=True)


def _header_html(display_name, tax_id, phone, logo):
	"""Simple RTL letter-head header: logo right, name + tax id left.
	Static HTML built once from system data (no Jinja needed at render)."""
	esc = html.escape
	lines = [
		f'<div style="font-size:20px;font-weight:bold;color:#24364a;line-height:1.3;">{esc(display_name)}</div>'
	]
	sub = []
	if tax_id:
		sub.append("الرقم الضريبي: " + esc(tax_id))
	if phone:
		sub.append("هاتف: " + esc(phone))
	if sub:
		joined = " &nbsp;|&nbsp; ".join(sub)
		lines.append(f'<div style="font-size:11px;color:#5f6b7a;margin-top:2px;">{joined}</div>')
	text_block = "".join(lines)

	if logo:
		body = (
			'<table style="width:100%;border-collapse:collapse;"><tr>'
			'<td style="width:170px;text-align:right;vertical-align:middle;border:0;">'
			f'<img src="{esc(logo)}" style="max-height:64px;max-width:160px;border:0;"></td>'
			f'<td style="text-align:left;vertical-align:middle;border:0;">{text_block}</td>'
			"</tr></table>"
		)
	else:
		body = text_block

	return (
		f'<div style="direction:rtl;text-align:right;font-family:{FONT_STACK};'
		f'border-bottom:2px solid #0f766e;padding-bottom:6px;margin-bottom:6px;">{body}</div>'
	)


def _footer_html(display_name, tax_id, phone):
	"""One-line centered letter-head footer from the same system data."""
	esc = html.escape
	parts = [esc(display_name)]
	if tax_id:
		parts.append("الرقم الضريبي: " + esc(tax_id))
	if phone:
		parts.append("هاتف: " + esc(phone))
	joined = " &middot; ".join(parts)
	return (
		f'<div style="direction:rtl;text-align:center;font-family:{FONT_STACK};'
		f'font-size:10px;color:#5f6b7a;border-top:1px solid #dde4ec;padding-top:4px;">{joined}</div>'
	)
