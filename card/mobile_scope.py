# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Server-side scope of the CARD Mobile KPI and management reads (issues #357, #358).

A reviewer (Card Supervisor, Card Manager, System Manager) sees the machines, requests and cards of his
permitted companies, narrowed by his Project User Permissions. ``frappe.get_list`` would also apply every
other Link User Permission, among them the Employee permission that ERPNext creates for the user's own
Employee: through the ``operator`` link it would hide every machine operated by someone else and the counts
would be too low. These helpers apply the two scopes that define a reviewer's view, explicitly:

- the read right of the role on the DocType (``frappe.has_permission``);
- the permitted companies (``card.report_access.permitted_companies``, as the CARD reports do);
- the Project User Permissions, with an empty project allowed as in Frappe's own list filter.

They use ``frappe.get_all`` after those three checks, so no other row rule applies: not the Employee permission (the point
of this module), not other Link User Permissions (Cost Center and the like) and not DocType hooks. Checked for the five
DocTypes the KPIs and the management view read (Card Equipment, Card Monthly Card, Card Daily Log, Equipment Needs
Request): no review role has an ``if_owner`` DocPerm on them, and their hooks only limit operators or apply the same
company scope. A DocType with a row rule for reviewers must not use these helpers. A user without read on the DocType,
or without a permitted company, gets nothing."""

import frappe

from card.report_access import permitted_companies


def permitted_projects(doctype, user=None):
	"""The projects the user is limited to for ``doctype``, or None when no Project User Permission applies."""
	entries = frappe.permissions.get_user_permissions(user or frappe.session.user).get("Project") or []
	allowed = {
		entry.get("doc")
		for entry in entries
		if not entry.get("applicable_for") or entry.get("applicable_for") == doctype
	}
	return allowed or None


def scoped_rows(doctype, fields, filters=None, project_field=None):
	"""Rows of ``doctype`` in the user's permitted companies and projects (see the module docstring).

	``project_field`` names the Project link used for the Project User Permission; it is read with the rows."""
	if not frappe.has_permission(doctype, "read"):
		return []
	companies = permitted_companies(doctype)
	if not companies:
		return []
	where = {**(filters or {}), "company": ["in", companies]}
	read = list(dict.fromkeys([*fields, *([project_field] if project_field else [])]))
	rows = frappe.get_all(doctype, filters=where, fields=read, limit_page_length=0)
	projects = permitted_projects(doctype) if project_field else None
	if projects is None:
		return rows
	return [row for row in rows if not row.get(project_field) or row.get(project_field) in projects]
