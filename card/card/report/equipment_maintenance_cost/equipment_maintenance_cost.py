# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment Maintenance Cost (#53, #127 P8; WP-17). Read-only.

One row per document line of one company and period tagged to an equipment through the
Card Equipment accounting dimension: submitted Purchase Invoice lines (not the invoices
that recognise CARD cards, diesel fills or transports) and submitted Material Issue Stock
Entry lines at their valuation; purchase lines of stock items are left out because those
items reach the equipment through the material issue. The same lines feed the "maintenance and other tagged
costs" of the Equipment Partial Margin (card.analytics.maintenance_lines). Without the
dimension the report explains it and lists nothing. Ledger readers only."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card import analytics
from card.report_access import can_view_ledger, readable_links, resolve_company

DOCTYPES = ("Purchase Invoice", "Stock Entry", "GL Entry")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	if not can_view_ledger(company):
		frappe.throw(
			_("The equipment maintenance cost shows financial figures; it needs General Ledger access."),
			frappe.PermissionError,
		)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the maintenance cost."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))
	columns = readable_links(get_columns())
	if not analytics.dimension_ready():
		return (
			columns,
			[],
			_(
				"The Card Equipment accounting dimension is not set up on this site, so no cost can be attributed to equipment. Ask the system manager to create the dimension."
			),
			None,
			[],
		)
	data = analytics.maintenance_lines(company, start, end, filters.get("project"), filters.get("equipment"))
	total = flt(sum(row["amount"] for row in data), 2)
	equipment = {row["equipment"] for row in data}
	summary = [
		{
			"label": _("Maintenance and other tagged costs"),
			"value": total,
			"datatype": "Currency",
			"indicator": "Red" if total else "Grey",
		},
		{"label": _("Equipment with tagged costs"), "value": len(equipment), "datatype": "Int"},
	]
	message = _(
		"Purchase invoice lines and material issues tagged with the Card Equipment dimension, net of VAT, in company currency. Invoices that recognise CARD cards, diesel fills or transports, fixed-asset lines and stock items (counted when they are issued) are not counted here; depreciation, labour and insurance are not included."
	)
	unread = analytics.unread_maintenance_note()
	if unread:
		message = message + " " + unread
	return readable_links(get_columns(), data), data, message, None, summary


def get_columns():
	return [
		{"fieldname": "posting_date", "label": _("Posting date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "voucher_type", "label": _("Document type"), "fieldtype": "Data", "width": 130},
		{
			"fieldname": "voucher_no",
			"label": _("Cost document"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 170,
		},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 140,
		},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 130,
		},
		{
			"fieldname": "item_code",
			"label": _("Cost item"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 140,
		},
		{
			"fieldname": "account",
			"label": _("Expense account"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 180,
		},
		{"fieldname": "amount", "label": _("Maintenance cost"), "fieldtype": "Currency", "width": 120},
	]
