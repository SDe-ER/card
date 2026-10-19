# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD Mobile (/cdms): who may open the phone app, and the signed-in user's context.

Same model as the Frappe HR mobile app (hrms/www/hrms.py, hrms.api.get_current_employee_info,
hrms.hr.utils.check_app_permission): Frappe login, session and CSRF; an Active Employee linked to the
user; every CARD endpoint keeps its own permission checks.
"""

import frappe
from frappe import _

import card
from card.materials import PORTAL_ROLES, has_any_role


def active_employee(user=None):
	"""The Active Employee linked to the user (standard Employee.user_id)."""
	return frappe.db.get_value(
		"Employee",
		{"user_id": user or frappe.session.user, "status": "Active"},
		["name", "employee_name", "company"],
		as_dict=True,
	)


def has_app_permission(require_employee=True):
	"""Apps screen entry and page gate for CARD Mobile: a CARD portal role and, unless told
	otherwise, an Active Employee."""
	if frappe.session.user == "Guest" or not has_any_role(PORTAL_ROLES):
		return False
	return bool(active_employee()) if require_employee else True


# Reading any of these is working in CARD Desk; an operator reads none of them.
DESK_DOCTYPES = (
	"Card Equipment",
	"Card Monthly Card",
	"Card Equipment Supplier",
	"Card Equipment Customer",
	"Equipment Transport",
	"Project Diesel Fill",
	"Equipment Needs Review",
)


def has_desk_app_permission():
	"""Apps screen entry for CARD Desk (G4), as hrms.hr.utils.check_app_permission: hidden from
	Website Users and from users who cannot read any CARD Desk document (e.g. operators)."""
	if frappe.session.user == "Administrator":
		return True
	if frappe.get_cached_value("User", frappe.session.user, "user_type") == "Website User":
		return False
	return any(frappe.has_permission(doctype, "read") for doctype in DESK_DOCTYPES)


@frappe.whitelist(methods=["GET"])
def get_session_context():
	"""The signed-in user's CARD Mobile context. Reads only."""
	if not has_app_permission(require_employee=False):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	user = frappe.session.user
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"roles": sorted(set(frappe.get_roles(user)) & set(PORTAL_ROLES)),
		"employee": active_employee(user),
		"card_version": card.__version__,
	}
