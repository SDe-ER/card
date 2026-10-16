# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Access rules shared by every CARD report and its link-filter queries.

Script reports read with ``frappe.get_all`` / SQL, which apply no document
permissions, so each report must scope itself:

- every report runs for ONE company, validated against the companies the user
  may see (standard Frappe multi-company rule: User Permissions on Company
  restrict the set; with none, every company is visible);
- ledger figures (GL Entry aggregates) are computed only for users who can read
  GL Entry through their own roles — operational roles see card figures only.

Nothing here grants an ERPNext permission: link filters use the CARD-owned
whitelisted queries in ``card.api`` (Frappe calls a whitelisted ``query``
instead of checking the target doctype), each of which calls
``assert_report_role`` and stays inside ``permitted_companies``."""

import frappe
from frappe import _

REPORT_ROLES = ("System Manager", "Card Manager", "Card User", "Accounts Manager")


def assert_report_role():
	if frappe.session.user == "Administrator":
		return
	if not set(frappe.get_roles()) & set(REPORT_ROLES):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def permitted_companies():
	"""Companies the session user may see in CARD reports, sorted."""
	restricted = frappe.permissions.get_user_permissions(frappe.session.user).get("Company")
	if restricted:
		return sorted({entry.get("doc") for entry in restricted})
	return frappe.get_all("Company", pluck="name", order_by="name")


def resolve_company(filters):
	"""The single company a report runs for; refuses one the user may not see."""
	allowed = permitted_companies()
	company = (
		(filters or {}).get("company")
		or frappe.defaults.get_user_default("Company")
		or frappe.defaults.get_global_default("company")
	)
	if not company and len(allowed) == 1:
		company = allowed[0]
	if not company:
		frappe.throw(_("Select a company"))
	if company not in allowed:
		frappe.throw(
			_("You are not permitted to view data of company {0}").format(company),
			frappe.PermissionError,
		)
	return company


def can_view_ledger():
	"""True when the user's own roles grant GL Entry read."""
	return bool(frappe.has_permission("GL Entry", "read"))


def query_companies(filters):
	"""Companies a link-filter query may draw from: the requested one when the
	user may see it (else none), otherwise every permitted company."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	allowed = permitted_companies()
	company = filters.get("company") if isinstance(filters, dict) else None
	if company:
		return [company] if company in allowed else []
	return allowed


def strip_ledger(columns, rows, summary, keys, tile_labels):
	"""Remove ledger columns, row values and summary tiles in place of hiding
	them, so the figures never reach the browser."""
	columns = [c for c in columns if c.get("fieldname") not in keys]
	for row in rows:
		for key in keys:
			row.pop(key, None)
	summary = [t for t in summary if t.get("label") not in tile_labels]
	return columns, summary


def ledger_notice():
	return _("Ledger balances are shown only to users with General Ledger access.")
