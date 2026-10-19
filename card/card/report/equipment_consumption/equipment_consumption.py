# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.utils import flt

from card.materials import DIMENSION_FIELD
from card.report_access import permitted_companies


def get_columns():
	return [
		{
			"fieldname": "card_equipment",
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
			"width": 140,
		},
		{"fieldname": "item_code", "label": _("Item"), "fieldtype": "Link", "options": "Item", "width": 160},
		{"fieldname": "qty", "label": _("Quantity"), "fieldtype": "Float", "width": 100},
		{"fieldname": "amount", "label": _("Cost"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "source", "label": _("Source"), "fieldtype": "Data", "width": 150},
		{"fieldname": "posting_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
	]


def execute(filters=None):
	# Report: "Equipment Consumption" — what each machine actually consumed: stock issued
	# to it (Stock Entry, Material Issue) plus non-stock items bought and used at once
	# (Purchase Invoice lines). A stock item's purchase is never counted: its cost comes
	# only with the issue, so nothing is counted twice.
	filters = frappe._dict(filters or {})
	companies = permitted_companies("Card Equipment")
	if not companies or not frappe.get_meta("Stock Entry Detail").has_field(DIMENSION_FIELD):
		return get_columns(), [], _("The Card Equipment accounting dimension is not set up on this site.")
	params = {"companies": tuple(companies)}
	where = []
	if filters.get("from_date"):
		where.append("posting_date >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		where.append("posting_date <= %(to_date)s")
		params["to_date"] = filters.to_date
	if filters.get("project"):
		where.append("project = %(project)s")
		params["project"] = filters.project
	if filters.get("equipment"):
		where.append("card_equipment = %(equipment)s")
		params["equipment"] = filters.equipment
	extra = (" and " + " and ".join(where)) if where else ""
	rows = frappe.db.sql(
		"""select * from (
			select d.card_equipment, coalesce(d.project, se.project) as project, d.item_code,
				d.qty, d.amount, se.name as source, se.posting_date
			from `tabStock Entry Detail` d join `tabStock Entry` se on se.name = d.parent
			where se.docstatus = 1 and se.purpose = 'Material Issue' and se.company in %(companies)s
				and ifnull(d.card_equipment, '') != ''
			union all
			select i.card_equipment, i.project, i.item_code, i.stock_qty as qty, i.base_net_amount as amount,
				pi.name as source, pi.posting_date
			from `tabPurchase Invoice Item` i join `tabPurchase Invoice` pi on pi.name = i.parent
			join `tabItem` it on it.name = i.item_code
			where pi.docstatus = 1 and pi.company in %(companies)s and it.is_stock_item = 0
				and ifnull(i.card_equipment, '') != ''
		) used where 1 = 1"""
		+ extra
		+ " order by card_equipment, posting_date",
		params,
		as_dict=True,
	)
	data = [dict(r, qty=flt(r.qty), amount=flt(r.amount, 2)) for r in rows]
	return get_columns(), data
