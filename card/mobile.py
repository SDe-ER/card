# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD Mobile (/cdms): who may open the phone app, and the signed-in user's context.

Same model as the Frappe HR mobile app (hrms/www/hrms.py, hrms.api.get_current_employee_info,
hrms.hr.utils.check_app_permission): Frappe login, session and CSRF; an Active Employee linked to the
user; every CARD endpoint keeps its own permission checks.
"""

from collections import Counter

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

import card
from card.materials import APPROVER_ROLES, ENDED_STATUS, PORTAL_ROLES, REVIEW_ROLES, has_any_role


def active_employee(user=None):
	"""The Active Employee linked to the user (standard Employee.user_id)."""
	return frappe.db.get_value(
		"Employee",
		{"user_id": user or frappe.session.user, "status": "Active"},
		["name", "employee_name", "company"],
		as_dict=True,
	)


def catalog_only(user=None):
	"""A read-only catalog viewer of CARD Mobile (phase 2b, Owner decision A): a Card User
	without a portal role. He opens only the catalog; request endpoints still refuse him."""
	from card.catalog import CATALOG_VIEW_ROLES

	return has_any_role(CATALOG_VIEW_ROLES, user) and not has_any_role(PORTAL_ROLES, user)


def has_app_permission(require_employee=True):
	"""Apps screen entry and page gate for CARD Mobile: a CARD portal role and, unless told
	otherwise, an Active Employee; or a catalog viewer (no Employee needed)."""
	if frappe.session.user == "Guest":
		return False
	if catalog_only():
		return True
	if not has_any_role(PORTAL_ROLES):
		return False
	return bool(active_employee()) if require_employee else True


# Reading any of these is working in CARD Desk; an operator reads none of them. Employee Tool
# Custody keeps stock users (custody, materials reports) on the Card app and its dock.
DESK_DOCTYPES = (
	"Card Equipment",
	"Card Monthly Card",
	"Card Equipment Supplier",
	"Card Equipment Customer",
	"Equipment Transport",
	"Project Diesel Fill",
	"Equipment Needs Review",
	"Employee Tool Custody",
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
		"catalog_only": catalog_only(user),
		"card_version": card.__version__,
	}


# ---------- profile and role-based home (FR-196, issue #357) ----------

# Every CARD role a profile may name. Only roles the user really holds are returned (never a picker).
PROFILE_ROLES = (*PORTAL_ROLES, "Card User", "Card Reviewer")
LANGUAGES = ("ar", "en")
EXPIRY_FIELDS = ("registration_expiry", "inspection_expiry", "insurance_expiry", "tuv_expiry")
EXPIRY_WARNING_DAYS = 30
ACTIVE_STATUS = "نشطة"
STOPPED_STATUS = "متوقفة"
MAINTENANCE_STATUS = "في الصيانة"


def user_roles(user=None):
	"""The CARD roles the user holds, in a fixed order."""
	held = set(frappe.get_roles(user or frappe.session.user))
	return [role for role in PROFILE_ROLES if role in held]


def _require_app_access():
	if not has_app_permission(require_employee=False):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def get_profile():
	"""The signed-in user's own profile: the Employee linked to the account, the CARD roles actually
	held, language, currency and number format. Reads only, and only the caller's own records:
	nothing here takes a name from the client. Personal data stops at what the profile shows."""
	_require_app_access()
	user = frappe.session.user
	employee = frappe.db.get_value(
		"Employee",
		{"user_id": user, "status": "Active"},
		[
			"name",
			"employee_name",
			"designation",
			"company",
			"branch",
			"cell_number",
			"company_email",
			"personal_email",
			"image",
		],
		as_dict=True,
	)
	account = frappe.db.get_value(
		"User", user, ["email", "user_image", "language", "mobile_no"], as_dict=True
	)
	company = employee.company if employee else None
	return {
		"user": user,
		"full_name": frappe.utils.get_fullname(user),
		"email": (employee and (employee.company_email or employee.personal_email)) or account.email,
		"phone": (employee and employee.cell_number) or account.mobile_no,
		"image": (employee and employee.image) or account.user_image,
		"employee": employee
		and {"name": employee.name, "designation": employee.designation, "branch": employee.branch},
		"company": company,
		"currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
		"number_format": frappe.get_system_settings("number_format"),
		"language": account.language or frappe.local.lang or "en",
		"roles": user_roles(user),
		"card_version": card.__version__,
	}


@frappe.whitelist(methods=["POST"])
def set_language(language: str):
	"""Switch the signed-in user's own interface language between Arabic and English. Self only; the
	Administrator account's language is never changed."""
	_require_app_access()
	user = frappe.session.user
	if user == "Administrator":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if language not in LANGUAGES:
		frappe.throw(_("Unsupported language"), frappe.ValidationError)
	frappe.db.set_value("User", user, "language", language)
	frappe.clear_cache(user=user)
	return language


def _count(doctype, filters=None, or_filters=None):
	"""Row count under the caller's own permissions (role matrix, User Permissions, company scope)."""
	return len(
		frappe.get_list(doctype, filters=filters, or_filters=or_filters, pluck="name", limit_page_length=0)
	)


def operational_kpis():
	"""Fleet, review queue and alert counts for a review role. Permission-scoped reads: a user sees
	only the records (and companies) the DocPerm and User Permission rules already give him."""
	today = getdate(nowdate())
	# plain fields, summed here: a fleet is hundreds of rows and the read stays under the user's rights
	rows = frappe.get_list(
		"Card Equipment",
		filters={"status": ["!=", ENDED_STATUS]},
		fields=["status", "current_project"],
		limit_page_length=0,
	)
	by_status = Counter(row.status for row in rows)
	by_project = Counter(row.current_project for row in rows)
	fleet_by_project = sorted(
		({"project": project, "count": count} for project, count in by_project.items()),
		key=lambda row: (-row["count"], row["project"] or ""),
	)[:6]
	soon = add_days(today, EXPIRY_WARNING_DAYS)
	expiring = _count(
		"Card Equipment",
		filters={"status": ["!=", ENDED_STATUS]},
		or_filters=[[field, "<=", soon] for field in EXPIRY_FIELDS],
	)
	return {
		"equipment": {
			"active": by_status.get(ACTIVE_STATUS, 0),
			"stopped": by_status.get(STOPPED_STATUS, 0),
			"maintenance": by_status.get(MAINTENANCE_STATUS, 0),
		},
		"fleet_by_project": fleet_by_project,
		"requests_to_review": _count(
			"Equipment Needs Request", {"review_status": ["in", ["Pending", "In review"]]}
		),
		"logs_to_review": _count(
			"Card Daily Log",
			{"docstatus": 1, "approval_status": ["in", ["Pending", "Verified by supervisor"]]},
		),
		"alerts": {"documents_expiring": expiring},
	}


def financial_kpis():
	"""Current-month revenue and supplier cost of submitted monthly cards, per company. Managers
	only (Owner 2026-11-28): the caller checks the role, and the money permlevel must also read."""
	today = getdate(nowdate())
	cards = frappe.get_list(
		"Card Monthly Card",
		filters={"docstatus": 1, "year": today.year, "month": f"{today.month:02d}"},
		fields=["company", "customer_net_amount", "net_amount"],
		limit_page_length=0,
	)
	totals = {}
	for row in cards:
		total = totals.setdefault(row.company, {"revenue": 0.0, "cost": 0.0})
		total["revenue"] += flt(row.customer_net_amount)
		total["cost"] += flt(row.net_amount)
	return {
		"month": today.month,
		"year": today.year,
		"by_company": [
			{
				"company": company,
				"currency": frappe.get_cached_value("Company", company, "default_currency"),
				"revenue": flt(total["revenue"]),
				"cost": flt(total["cost"]),
			}
			for company, total in sorted(totals.items())
		],
	}


@frappe.whitelist(methods=["GET"])
def get_home_context():
	"""What the home screen shows, by role. Operators get no KPI values at all; review roles get
	operational counts; only Card Manager and System Manager also get financial figures, and the
	server leaves them out for everyone else (the client is never the authority). Reads only."""
	_require_app_access()
	from card.field_privacy import can_view_money

	user = frappe.session.user
	reviewer = has_any_role(REVIEW_ROLES, user)
	manager = has_any_role(APPROVER_ROLES, user)
	home = {"reviewer": reviewer, "manager": manager, "kpis": None, "financial": None}
	if reviewer:
		home["kpis"] = operational_kpis()
	if manager and can_view_money(user=user):
		home["financial"] = financial_kpis()
	return home
