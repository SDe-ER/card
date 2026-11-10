# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment Location History (#53, #127; FR-130). Read-only.

For one company, an optional equipment and a period: where each equipment was, in
date-aware segments (a project assignment, the place a transport sent it to, or the
company's initial place). A move to a workshop, storage or supplier on day T shows the
project on T and the new place from T+1. The rules are those of `card.transfer`, applied by
`card.location_history`; this report writes nothing."""

import frappe
from frappe import _
from frappe.utils import getdate

from card.location_history import ASSIGNMENT, INITIAL, PROJECT, TRANSPORT, company_segments
from card.report_access import readable_links, resolve_company, role_reads

EQUIPMENT = "Card Equipment"
DOCTYPES = (EQUIPMENT, ASSIGNMENT, TRANSPORT)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	# the report reads these in bulk: the user's roles must grant read on each of them
	for doctype in DOCTYPES:
		if not role_reads(doctype):
			frappe.throw(
				_("You are not permitted to read {0}, which the location history needs.").format(_(doctype)),
				frappe.PermissionError,
			)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the location history."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))

	equipment_filters = {"company": company}
	if filters.get("equipment"):
		# an equipment of another company is refused, never read
		if frappe.db.get_value(EQUIPMENT, filters.equipment, "company") != company:
			frappe.throw(
				_("Equipment {0} does not belong to company {1}.").format(filters.equipment, company),
				frappe.PermissionError,
			)
		equipment_filters["name"] = filters.equipment
	equipment = frappe.get_list(
		EQUIPMENT, filters=equipment_filters, fields=["name", "is_unit"], order_by="name", limit_page_length=0
	)

	rows = company_segments(company, start, end, equipment)
	message = None
	if any(r.get("overlap") for r in rows):
		message = _(
			"Some equipment is on two projects on the same days (overlapping assignments); see the rows marked as overlapping."
		)
	_label_rows(rows)
	columns = readable_links(_columns(), rows)
	return columns, rows, message


def _label_rows(rows):
	titles = {}
	projects = list({r["project"] for r in rows if r.get("project")})
	if projects:
		titles = dict(
			frappe.get_all(
				"Project", filters={"name": ["in", projects]}, fields=["name", "project_name"], as_list=True
			)
		)
	labels = {INITIAL: _("Initial place", context="Card")}
	for row in rows:
		kind = row["location_type"]
		row["location_type"] = labels.get(kind) or _(kind)
		if kind == PROJECT:
			row["location"] = titles.get(row["project"]) or row["project"]


def _columns():
	return [
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": EQUIPMENT,
			"width": 160,
		},
		{"fieldname": "from_date", "label": _("From date"), "fieldtype": "Date", "width": 110},
		{"fieldname": "to_date", "label": _("To date"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "location_type",
			"label": _("Location type", context="Card"),
			"fieldtype": "Data",
			"width": 120,
		},
		{"fieldname": "location", "label": _("Location"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": PROJECT,
			"width": 140,
		},
		{
			"fieldname": "overlap",
			"label": _("Overlapping projects"),
			"fieldtype": "Check",
			"width": 90,
		},
		{
			"fieldname": "source_doctype",
			"label": _("Source type", context="Card"),
			"fieldtype": "Link",
			"options": "DocType",
			"width": 160,
		},
		{
			"fieldname": "source_document",
			"label": _("Source document", context="Card"),
			"fieldtype": "Dynamic Link",
			"options": "source_doctype",
			"width": 170,
		},
	]
