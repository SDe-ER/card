# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Project Invoice Profitability (FR-193, #53; owner decision 2026-11-25). Read-only.

One row per project for one company and period:

- revenue: the net amount of submitted Sales Invoice lines posted in the period (credit notes
  are negative lines, so they reduce revenue);
- expenses: the net amount of submitted Purchase Invoice lines posted in the period (debit
  notes reduce expenses);
- a line without a project takes the project of its invoice; a line with no project at all
  sits on the row "No project", so the totals reconcile to the invoices.

Amounts are in the company currency, net of VAT (card.analytics.invoice_project_totals).
Journal Entries and GL Entries are not read and nothing is estimated. The margin is revenue
minus purchase-invoice expenses, NOT the full net profit: payroll, depreciation, overhead and
journal-entry costs are not included. Ledger readers only
(card.report_access.can_view_ledger)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card import analytics
from card.report_access import can_view_ledger, readable_links, resolve_company
from card.report_currency import company_currency_report

DOCTYPES = ("Sales Invoice", "Purchase Invoice")
AMOUNT_KEYS = ("revenue", "expenses", "margin")


@company_currency_report(*DOCTYPES)
def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	if not can_view_ledger(company):
		frappe.throw(
			_("The project profitability shows financial figures; it needs General Ledger access."),
			frappe.PermissionError,
		)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the project profitability."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))

	notes = [
		_(
			'Read only. Revenue is the net amount of submitted Sales Invoice lines and expenses are the net amount of submitted Purchase Invoice lines, by posting date, in the company currency. A line without a project takes the project of its invoice; lines with no project at all are on the row "No project". Journal entries and the general ledger are not read, and nothing is estimated. The margin is revenue minus purchase-invoice expenses, not the full net profit: payroll, depreciation, overhead and journal-entry costs are not included.'
		)
	]
	unreadable = {
		"Sales Invoice": _("Revenue is not shown: you cannot read Sales Invoice."),
		"Purchase Invoice": _("Expenses are not shown: you cannot read Purchase Invoice."),
	}
	rows = {}
	for key, doctype in (("revenue", "Sales Invoice"), ("expenses", "Purchase Invoice")):
		if not analytics.can_read(doctype):
			notes.append(unreadable[doctype])
			continue
		totals = analytics.invoice_project_totals(doctype, company, start, end, filters.get("project"))
		for project, amount in totals.items():
			rows.setdefault(project, dict.fromkeys(AMOUNT_KEYS, 0.0))[key] = amount

	names = analytics.project_names([project for project in rows if project])
	data = []
	total = dict.fromkeys(AMOUNT_KEYS, 0.0)
	for project, row in sorted(rows.items(), key=lambda item: (not item[0], item[0])):
		row["margin"] = flt(row["revenue"] - row["expenses"], 2)
		for key in AMOUNT_KEYS:
			total[key] = flt(total[key] + row[key], 2)
		row.update(
			{
				"project": project or None,
				"project_name": names.get(project) if project else _("No project"),
				"margin_percent": _margin_percent(row),
			}
		)
		data.append(row)
	total.update(
		{
			"project": None,
			"project_name": _("Total of all projects"),
			"margin_percent": _margin_percent(total),
			"is_total": 1,
			"bold": 1,
		}
	)
	data.append(total)

	summary = [
		{
			"label": _("Project revenue"),
			"value": total["revenue"],
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"label": _("Project expenses"),
			"value": total["expenses"],
			"datatype": "Currency",
			"indicator": "Red",
		},
		{
			"label": _("Project margin"),
			"value": total["margin"],
			"datatype": "Currency",
			"indicator": "Green" if total["margin"] >= 0 else "Red",
		},
	]
	return readable_links(get_columns(), data), data, " ".join(notes), None, summary


def _margin_percent(row):
	"""The margin as a percentage of revenue; None without revenue."""
	if not row["revenue"]:
		return None
	return flt(row["margin"] / row["revenue"] * 100, 2)


def get_columns():
	def money(fieldname, label):
		return {"fieldname": fieldname, "label": label, "fieldtype": "Currency", "width": 150}

	return [
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 150,
		},
		{"fieldname": "project_name", "label": _("Project name"), "fieldtype": "Data", "width": 220},
		money("revenue", _("Project revenue")),
		money("expenses", _("Project expenses")),
		money("margin", _("Project margin")),
		{"fieldname": "margin_percent", "label": _("Project margin %"), "fieldtype": "Percent", "width": 130},
	]
