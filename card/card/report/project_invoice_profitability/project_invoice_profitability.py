# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Project Invoice Profitability (FR-193, #53; owner decision 2026-11-25). Read-only.

One row per project for one company and period:

- revenue: the net amount of submitted Sales Invoice lines posted in the period (credit notes
  are negative lines, so they reduce revenue);
- expenses: the net amount of the submitted Purchase Invoice lines posted in the period that
  are booked to an Expense account and are neither a stock item nor a fixed asset (debit notes
  reduce expenses);
- not_in_expenses: the net amount of the other Purchase Invoice lines (stock items, fixed
  assets, lines on an account that is not an Expense account). Information only: it is not in
  the margin. Expenses plus this column are the net total of the purchase invoice lines
  (owner decision 2026-11-26);
- a line without a project takes the project of its invoice; a line with no project at all
  sits on the row "No project", so the totals reconcile to the invoices;
- opening invoices are not read.

Amounts are in the company currency, net of VAT (card.analytics.invoice_project_totals and
card.analytics.purchase_project_totals), summed unrounded and rounded once at the precision of
the company currency.
Journal Entries and GL Entries are not read and nothing is estimated. The margin is revenue
minus purchase-invoice expenses, NOT the full net profit: payroll, depreciation, overhead and
journal-entry costs are not included. Ledger readers only
(card.report_access.can_view_ledger) who read both invoice types: a margin built from one side
only would mislead, so the report is refused instead."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card import analytics
from card.report_access import can_view_ledger, readable_links, resolve_company
from card.report_currency import company_currency, company_currency_report, currency_precision

DOCTYPES = ("Sales Invoice", "Purchase Invoice")
AMOUNTS = ("revenue", "expenses", "not_in_expenses")


@company_currency_report(*DOCTYPES)
def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	if not can_view_ledger(company):
		frappe.throw(
			_("The project profitability shows financial figures; it needs General Ledger access."),
			frappe.PermissionError,
		)
	unreadable = [doctype for doctype in DOCTYPES if not analytics.can_read(doctype)]
	if unreadable:
		frappe.throw(
			_("The project profitability needs read access to {0}.").format(
				", ".join(_(doctype) for doctype in unreadable)
			),
			frappe.PermissionError,
		)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the project profitability."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))

	message = _(
		'Read only. Revenue is the net amount of submitted Sales Invoice lines, by posting date, in the company currency. Expenses are the net amount of the submitted Purchase Invoice lines that are booked to an Expense account and are neither a stock item nor a fixed asset. The other Purchase Invoice lines are in the column "Purchases not in expenses (stock, assets)": it is information only and is not in the margin. Opening invoices are not read. A line without a project takes the project of its invoice; lines with no project at all are on the row "No project". Journal entries and the general ledger are not read, and nothing is estimated. The margin is revenue minus purchase-invoice expenses, not the full net profit: payroll, depreciation, overhead and journal-entry costs are not included.'
	)
	period = (company, start, end, filters.get("project"))
	sums = {}
	for project, amount in analytics.invoice_project_totals("Sales Invoice", *period).items():
		sums.setdefault(project, dict.fromkeys(AMOUNTS, 0.0))["revenue"] = amount
	for project, split in analytics.purchase_project_totals(*period).items():
		sums.setdefault(project, dict.fromkeys(AMOUNTS, 0.0)).update(split)

	precision = currency_precision(company_currency(company))

	def amounts(side):
		"""Unrounded sums rounded once, at the precision of the company currency. The margin is
		revenue minus expenses: the purchases not in expenses are not part of it."""
		row = {key: flt(side[key], precision) for key in AMOUNTS}
		row["margin"] = flt(row["revenue"] - row["expenses"], precision)
		row["margin_percent"] = flt(row["margin"] / row["revenue"] * 100, 2) if row["revenue"] else None
		return row

	names = analytics.project_names([project for project in sums if project], company)
	data = []
	for project, side in sorted(sums.items(), key=lambda item: (not item[0], item[0])):
		row = amounts(side)
		row.update(
			{
				"project": project or None,
				"project_name": names.get(project) if project else _("No project"),
			}
		)
		data.append(row)
	total = amounts({key: sum(side[key] for side in sums.values()) for key in AMOUNTS})
	total.update({"project": None, "project_name": _("Total of all projects"), "is_total": 1, "bold": 1})
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
		{  # information only: not part of the three tiles above
			"label": _("Purchases not in expenses (stock, assets)"),
			"value": total["not_in_expenses"],
			"datatype": "Currency",
			"indicator": "Grey",
		},
	]
	# no rows passed: the Project column keeps the record name, the name has its own column
	return readable_links(get_columns()), data, message, None, summary


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
		{**money("not_in_expenses", _("Purchases not in expenses (stock, assets)")), "width": 220},
		money("margin", _("Project margin")),
		{"fieldname": "margin_percent", "label": _("Project margin %"), "fieldtype": "Percent", "width": 130},
	]
