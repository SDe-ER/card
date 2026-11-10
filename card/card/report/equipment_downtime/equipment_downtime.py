# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment Downtime (#45, #123; WP-09, FR-118). Read-only.

The stopped days and hours of one company's monthly cards in a period, by stop reason,
responsible party, equipment, project or month (or each day). A downtime row is a card day
row with a stop reason, stopped hours, or a non-working day status; a row of an older card
without a reason is shown under its day status, so earlier months are not lost.

Scope: one company the user may see for monthly cards (card.report_access.resolve_company),
and only the cards the user may read (frappe.get_list applies the role and User
Permission rules). Submitted cards by default; drafts on request. Nothing is written."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from card.report_access import readable_links, resolve_company

CARD = "Card Monthly Card"
DAY = "Card Monthly Card Day"
WORK = "عمل"
GROUPS = ("Reason", "Responsible party", "Equipment", "Project", "Month", "Detail")
PARTY_TYPES = ("Company", "Supplier", "Customer", "Other")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, CARD)
	if not frappe.has_permission(CARD, "read"):
		frappe.throw(_("Equipment downtime needs read access to the monthly cards."), frappe.PermissionError)
	if not (filters.get("from_date") and filters.get("to_date")):
		frappe.throw(_("Select the period of the equipment downtime."))
	start, end = getdate(filters.from_date), getdate(filters.to_date)
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))
	group_by = filters.get("group_by") or "Reason"
	if group_by not in GROUPS:
		frappe.throw(_("Invalid grouping: {0}").format(group_by))
	party_type = filters.get("responsible_party_type") or None
	if party_type and party_type not in PARTY_TYPES:
		frappe.throw(_("Invalid responsible party type: {0}").format(party_type))

	rows = downtime_rows(
		company,
		start,
		end,
		project=filters.get("project"),
		equipment=filters.get("equipment"),
		stop_reason=filters.get("stop_reason"),
		party_type=party_type,
		include_drafts=cint(filters.get("include_drafts")),
	)
	if group_by == "Detail":
		columns, data = detail_columns(), rows
	else:
		columns, data = group_columns(group_by), group_rows(rows, group_by)

	summary = [
		{
			"label": _("Stopped days"),
			"value": len(rows),
			"datatype": "Int",
			"indicator": "Orange" if rows else "Grey",
		},
		{
			"label": _("Stopped hours"),
			"value": flt(sum(r["stopped_hours"] for r in rows), 2),
			"datatype": "Float",
			"indicator": "Orange" if rows else "Grey",
		},
		{
			"label": _("Billable stopped hours"),
			"value": flt(sum(r["billable_hours"] for r in rows), 2),
			"datatype": "Float",
			"indicator": "Blue",
		},
	]
	message = _(
		"Stopped days are card days with a stop reason, stopped hours or a non-working status. Stopped hours earn rental only under a billable stop reason."
	)
	return readable_links(columns, data), data, message, None, summary


def downtime_rows(
	company,
	start,
	end,
	project=None,
	equipment=None,
	stop_reason=None,
	party_type=None,
	include_drafts=False,
):
	"""The downtime day rows of the cards the user may read, oldest first."""
	card_filters = [
		["company", "=", company],
		["docstatus", "in", [0, 1] if include_drafts else [1]],
		["from_date", "<=", end],
		["to_date", ">=", start],
	]
	if project:
		card_filters.append(["project", "=", project])
	if equipment:
		card_filters.append(["equipment", "=", equipment])
	cards = {
		c.name: c
		for c in frappe.get_list(
			CARD,
			filters=card_filters,
			fields=["name", "equipment", "equipment_name", "project", "month", "year", "docstatus"],
			limit_page_length=0,
		)
	}
	if not cards:
		return []
	day_filters = [
		["parenttype", "=", CARD],
		["parentfield", "=", "days"],
		["parent", "in", list(cards)],
		["operation_date", "between", [start, end]],
	]
	if stop_reason:
		day_filters.append(["stop_reason", "=", stop_reason])
	if party_type:
		day_filters.append(["responsible_party_type", "=", party_type])
	days = frappe.get_all(
		DAY,
		filters=day_filters,
		fields=[
			"parent",
			"operation_date",
			"day_status",
			"working_hours",
			"stop_reason",
			"stopped_hours",
			"reason_billable",
			"responsible_party_type",
			"responsible_party",
			"responsible_party_name",
			"idle_reason",
		],
		order_by="operation_date asc, parent asc",
		limit_page_length=0,
		parent_doctype=CARD,
	)
	result = []
	for d in days:
		full_stop = (d.day_status or WORK) != WORK
		if not (d.stop_reason or flt(d.stopped_hours) > 0 or full_stop):
			continue
		card = cards[d.parent]
		stopped = flt(d.stopped_hours)
		result.append(
			{
				"card": d.parent,
				"operation_date": d.operation_date,
				"month": "{0}/{1}".format(card.month, card.year),
				"equipment": card.equipment,
				"equipment_name": card.equipment_name,
				"project": card.project,
				"day_status": d.day_status,
				"stop_reason": d.stop_reason,
				"reason": d.stop_reason or (_(d.day_status) if full_stop else _("No reason")),
				"full_stop_days": 1 if full_stop else 0,
				"days": 1,
				"working_hours": flt(d.working_hours),
				"stopped_hours": stopped,
				"billable_hours": stopped if cint(d.reason_billable) and d.stop_reason else 0.0,
				"responsible_party_type": d.responsible_party_type,
				"responsible_type_label": _(d.responsible_party_type) if d.responsible_party_type else None,
				"responsible": d.responsible_party or d.responsible_party_name,
				"notes": d.idle_reason,
				"draft": 1 if card.docstatus == 0 else 0,
			}
		)
	return result


def _group_key(row, group_by):
	if group_by == "Reason":
		return row["reason"]
	if group_by == "Responsible party":
		if not row["responsible_party_type"]:
			return _("Not set")
		party = row["responsible"]
		label = _(row["responsible_party_type"])
		return "{0}: {1}".format(label, party) if party else label
	if group_by == "Equipment":
		return row["equipment"]
	if group_by == "Project":
		return row["project"] or ""
	return row["operation_date"].strftime("%Y-%m") if row["operation_date"] else row["month"]


def group_rows(rows, group_by):
	groups = {}
	for row in rows:
		key = _group_key(row, group_by)
		g = groups.get(key)
		if g is None:
			g = groups[key] = {
				"group": key,
				"equipment_name": row["equipment_name"] if group_by == "Equipment" else None,
				"days": 0,
				"full_stop_days": 0,
				"stopped_hours": 0.0,
				"billable_hours": 0.0,
				"equipment_count": set(),
			}
		g["days"] += 1
		g["full_stop_days"] += row["full_stop_days"]
		g["stopped_hours"] = flt(g["stopped_hours"] + row["stopped_hours"], 2)
		g["billable_hours"] = flt(g["billable_hours"] + row["billable_hours"], 2)
		g["equipment_count"].add(row["equipment"])
	data = []
	for key in sorted(groups, key=lambda k: str(k or "")):
		g = groups[key]
		g["equipment_count"] = len(g["equipment_count"])
		data.append(g)
	return data


def group_columns(group_by):
	labels = {
		"Reason": _("Stop reason"),
		"Responsible party": _("Responsible party"),
		"Equipment": _("Equipment"),
		"Project": _("Project"),
		"Month": _("Month"),
	}
	first = {"fieldname": "group", "label": labels[group_by], "fieldtype": "Data", "width": 200}
	if group_by == "Equipment":
		first.update({"fieldtype": "Link", "options": "Card Equipment"})
	elif group_by == "Project":
		first.update({"fieldtype": "Link", "options": "Project"})
	columns = [first]
	if group_by == "Equipment":
		columns.append(
			{"fieldname": "equipment_name", "label": _("Equipment name"), "fieldtype": "Data", "width": 160}
		)
	columns += [
		{"fieldname": "days", "label": _("Stopped days"), "fieldtype": "Int", "width": 110},
		{"fieldname": "full_stop_days", "label": _("Full stopped days"), "fieldtype": "Int", "width": 120},
		{"fieldname": "stopped_hours", "label": _("Stopped hours"), "fieldtype": "Float", "width": 120},
		{
			"fieldname": "billable_hours",
			"label": _("Billable stopped hours"),
			"fieldtype": "Float",
			"width": 150,
		},
		{"fieldname": "equipment_count", "label": _("Equipment count"), "fieldtype": "Int", "width": 110},
	]
	return columns


def detail_columns():
	return [
		{"fieldname": "operation_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "card", "label": _("Card"), "fieldtype": "Link", "options": CARD, "width": 170},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 130,
		},
		{"fieldname": "equipment_name", "label": _("Equipment name"), "fieldtype": "Data", "width": 150},
		{
			"fieldname": "project",
			"label": _("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"width": 130,
		},
		{"fieldname": "day_status", "label": _("Day status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "reason", "label": _("Stop reason"), "fieldtype": "Data", "width": 150},
		{"fieldname": "stopped_hours", "label": _("Stopped hours"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "billable_hours",
			"label": _("Billable stopped hours"),
			"fieldtype": "Float",
			"width": 140,
		},
		{"fieldname": "working_hours", "label": _("Operating hours"), "fieldtype": "Float", "width": 110},
		{
			"fieldname": "responsible_type_label",
			"label": _("Responsible party"),
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"fieldname": "responsible",
			"label": _("Responsible party record"),
			"fieldtype": "Data",
			"width": 150,
		},
		{"fieldname": "notes", "label": _("Idle reason"), "fieldtype": "Data", "width": 150},
		{"fieldname": "draft", "label": _("Draft card"), "fieldtype": "Check", "width": 90},
	]
