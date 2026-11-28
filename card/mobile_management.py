# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD Mobile management view (issue #358): all equipment, projects and monthly cards for a review role.

Card Supervisor, Card Manager and System Manager see every machine, project and card of their permitted
companies and projects, whoever operates it. A Card Operator or Card User never passes the role check. Money
(revenue, cost, result) is returned to Card Manager and System Manager only, and only when they can read the
money permlevel (Owner decision 2026-11-28); everyone else receives operational figures. Reads only."""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from card.field_privacy import can_view_money
from card.materials import APPROVER_ROLES, ENDED_STATUS, REVIEW_ROLES, has_any_role
from card.mobile_scope import scoped_rows

# a fleet or a month of cards is hundreds of rows; the cap only protects the phone from a runaway list
MAX_ROWS = 2000


def _require_reviewer():
	from card.mobile import has_app_permission

	if (
		frappe.session.user == "Guest"
		or not has_any_role(REVIEW_ROLES)
		or not has_app_permission(require_employee=False)
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def sees_money():
	"""Card Manager or System Manager with read on the money permlevel."""
	return has_any_role(APPROVER_ROLES) and can_view_money()


def _select_options(doctype, fieldname):
	return [o for o in (frappe.get_meta(doctype).get_field(fieldname).options or "").split("\n") if o]


@frappe.whitelist(methods=["GET"])
def get_management_context():
	"""The ownership and status choices of the fleet filters, and whether money figures are shown."""
	_require_reviewer()
	return {
		"ownership": _select_options("Card Equipment", "ownership"),
		"status": _select_options("Card Equipment", "status"),
		"money": sees_money(),
		# a Card Supervisor has no read right on Card Monthly Card: the cards screen says so
		"cards": bool(frappe.has_permission("Card Monthly Card", "read")),
	}


@frappe.whitelist(methods=["GET"])
def list_all_equipment(ownership: str | None = None, project: str | None = None, status: str | None = None):
	"""Every machine in the user's permitted companies and projects, with its filters. No money."""
	_require_reviewer()
	filters = {"status": ["!=", ENDED_STATUS]}
	for field, value in (("ownership", ownership), ("current_project", project), ("status", status)):
		if value:
			filters[field] = value
	if ownership and ownership not in _select_options("Card Equipment", "ownership"):
		frappe.throw(_("Unsupported filter value"), frappe.ValidationError)
	if status and status not in _select_options("Card Equipment", "status"):
		frappe.throw(_("Unsupported filter value"), frappe.ValidationError)
	if status:
		filters["status"] = status
	rows = scoped_rows(
		"Card Equipment",
		["name", "equipment_name", "ownership", "status", "operator_name", "plate_no"],
		filters,
		project_field="current_project",
	)
	rows.sort(key=lambda row: (row.get("current_project") or "", row.get("equipment_name") or row.name))
	return rows[:MAX_ROWS]


def _period(year, month):
	today = getdate(nowdate())
	try:
		year = today.year if year in (None, "") else int(year)
		month = today.month if month in (None, "") else int(month)
	except (TypeError, ValueError):
		frappe.throw(_("Invalid period"), frappe.ValidationError)
	if not (1 <= month <= 12 and 2000 <= year <= 2100):
		frappe.throw(_("Invalid period"), frappe.ValidationError)
	return year, f"{month:02d}"


def _card_fields():
	fields = [
		"name",
		"equipment",
		"equipment_name",
		"project",
		"docstatus",
		"working_days",
		"total_working_hours",
	]
	return [*fields, "company", "net_amount", "customer_net_amount"] if sees_money() else [*fields, "company"]


@frappe.whitelist(methods=["GET"])
def list_monthly_cards(year: int | None = None, month: int | None = None):
	"""Monthly cards of a period (default: the current month), draft and submitted. Amounts only for
	Card Manager and System Manager."""
	_require_reviewer()
	year, month = _period(year, month)
	rows = scoped_rows(
		"Card Monthly Card",
		_card_fields(),
		{"docstatus": ["<", 2], "year": year, "month": month},
		project_field="project",
	)
	rows.sort(key=lambda row: (row.get("project") or "", row.get("equipment_name") or row.name))
	return rows[:MAX_ROWS]


@frappe.whitelist(methods=["GET"])
def list_projects(year: int | None = None, month: int | None = None):
	"""One row per project of the permitted scope: machines now on it and the period's working hours
	and cards. Revenue, cost and result (revenue minus supplier cost of the submitted cards) only for
	Card Manager and System Manager."""
	_require_reviewer()
	year, month = _period(year, month)
	money = sees_money()
	fleet = scoped_rows(
		"Card Equipment",
		["name"],
		{"status": ["!=", ENDED_STATUS]},
		project_field="current_project",
	)
	projects = {}
	for row in fleet:
		entry = projects.setdefault(row.current_project or "", _empty_project(money))
		entry["equipment"] += 1
	fields = ["project", "docstatus", "total_working_hours"] + (
		["net_amount", "customer_net_amount"] if money else []
	)
	for card in scoped_rows(
		"Card Monthly Card",
		fields,
		{"docstatus": ["<", 2], "year": year, "month": month},
		project_field="project",
	):
		entry = projects.setdefault(card.project or "", _empty_project(money))
		entry["cards"] += 1
		entry["hours"] += flt(card.total_working_hours)
		if money and card.docstatus == 1:
			entry["revenue"] += flt(card.customer_net_amount)
			entry["cost"] += flt(card.net_amount)
	out = []
	for project, entry in sorted(projects.items()):
		if money:
			entry["result"] = entry["revenue"] - entry["cost"]
		out.append({"project": project or None, **entry})
	return out


def _empty_project(money):
	base = {"equipment": 0, "cards": 0, "hours": 0.0}
	return {**base, "revenue": 0.0, "cost": 0.0} if money else base
