# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-136 (#53, O-17): CARD reports show money in the report company's currency, labelled.

Every CARD report runs for one company (``card.report_access.resolve_company``) and its figures come
from documents of that company, so they are all in that company's default currency. CARD converts
nothing (O-17: company currency only). Without a currency on a Currency column, Frappe's formatter
shows the site's default currency symbol (``frappe.meta.get_field_currency``), which is wrong for a
second company whose currency differs. ``company_currency_report`` labels the result: each Currency
column without its own ``options`` reads the row field ``currency``; each dict row and each Currency
summary tile carries the company currency. Values, columns order and labels are unchanged."""

import functools

import frappe

from card.report_access import resolve_company

CURRENCY_FIELD = "currency"


def company_currency(company):
	"""The default currency of ``company`` (empty when unknown)."""
	return (frappe.get_cached_value("Company", company, "default_currency") or "") if company else ""


def label_currency(result, currency):
	"""Label a script report result (list or tuple: columns, rows, message, chart, summary, ...)."""
	if not currency or not isinstance(result, list | tuple) or not result:
		return result
	out = list(result)
	columns = out[0] or []
	money = False
	for column in columns:
		if isinstance(column, dict) and column.get("fieldtype") == "Currency":
			money = True
			if not column.get("options"):
				column["options"] = CURRENCY_FIELD
	if money and len(out) > 1:
		for row in out[1] or []:
			if isinstance(row, dict):
				row.setdefault(CURRENCY_FIELD, currency)
	if len(out) > 4:
		for tile in out[4] or []:
			if isinstance(tile, dict) and tile.get("datatype") == "Currency":
				tile.setdefault("currency", currency)
	return type(result)(out) if isinstance(result, tuple) else out


def company_currency_report(*doctypes):
	"""Decorator for a report ``execute``: label its result with the currency of the company it ran for.

	``doctypes`` are the same doctypes the report passes to ``resolve_company`` (the company is resolved
	again with them, so the label is always the company whose data the report read)."""

	def decorator(execute):
		@functools.wraps(execute)
		def wrapper(filters=None):
			result = execute(filters)
			company = resolve_company(frappe._dict(filters or {}), *doctypes)
			return label_currency(result, company_currency(company))

		return wrapper

	return decorator
