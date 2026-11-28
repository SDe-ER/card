# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Server-side scope of the CARD Mobile KPI and management reads (issues #357, #358).

A reviewer (Card Supervisor, Card Manager, System Manager) sees the machines, requests and cards of his
permitted companies, narrowed by his Project User Permissions, whoever operates them. This is the stated goal of
the management view (Owner approval, issue #358) and it is a deliberate difference from Desk: ``frappe.get_list``
also applies the Employee User Permission that ERPNext creates for a user's own Employee, and through the
``operator`` link it would hide every machine operated by someone else. The helpers below therefore read with
``frappe.get_all`` after these checks, in this order:

- the read right of the role on the DocType, ignoring document shares (``frappe.has_permission`` with no document
  returns True as soon as one document of the DocType is shared with the user);
- fail closed: when the user holds a User Permission that applies to the DocType or to one of its Link fields and is
  not one of Company, Project or Employee, the result is empty, because those rules are not applied here;
- the permitted companies (``card.report_access.permitted_companies``, as the CARD reports do);
- the Project User Permissions, with an empty project allowed as in Frappe's own list filter.

Not applied, by design: the Employee User Permission (above), DocType hooks and field levels. Checked for the DocTypes
read here (Card Equipment, Card Monthly Card, Card Daily Log, Equipment Needs Request): no review role has an
``if_owner`` DocPerm on them, and their hooks only limit operators or repeat the company scope. A caller must not
return a field of a higher permlevel than the user reads. A DocType with a row rule for reviewers must not use these
helpers."""

import frappe

from card.report_access import permitted_companies, role_reads

# User Permissions this module applies itself (Company, Project) or bypasses on purpose (Employee)
HANDLED_PERMISSIONS = {"Company", "Project", "Employee"}


def can_read(doctype):
	"""Role read right on ``doctype`` without an owner restriction; a document share never counts, and a role
	that reads only its own documents (``if_owner``) does not pass (``card.report_access.role_reads``)."""
	return role_reads(doctype)


def permitted_projects(doctype, user=None):
	"""The projects the user is limited to for ``doctype``, or None when no Project User Permission applies."""
	entries = frappe.permissions.get_user_permissions(user or frappe.session.user).get("Project") or []
	allowed = {
		entry.get("doc")
		for entry in entries
		if not entry.get("applicable_for") or entry.get("applicable_for") == doctype
	}
	return allowed or None


def has_unhandled_user_permission(doctype, user=None, project_applied=True):
	"""True when a User Permission applies to ``doctype`` or to one of its Link fields and this module does not apply it.
	Project counts as applied only when the caller names a project field (``project_applied``)."""
	handled = HANDLED_PERMISSIONS if project_applied else HANDLED_PERMISSIONS - {"Project"}
	meta = frappe.get_meta(doctype)
	targets = {doctype} | {df.options for df in meta.get_link_fields() if not df.ignore_user_permissions}
	for allow, entries in frappe.permissions.get_user_permissions(user or frappe.session.user).items():
		if allow in handled or allow not in targets:
			continue
		if any(not e.get("applicable_for") or e.get("applicable_for") == doctype for e in entries):
			return True
	return False


def scoped_rows(doctype, fields, filters=None, *, project_field, order_by=None, limit=0):
	"""Rows of ``doctype`` in the user's permitted companies and projects (see the module docstring).

	``project_field`` is required: the Project link used for the Project User Permission, returned with the rows. Pass
	``None`` only for a DocType without a project; a Project User Permission then counts as not applied and the read fails closed. ``limit`` and ``order_by`` run in the
	query; ``limit`` 0 means no limit."""
	if not can_read(doctype) or has_unhandled_user_permission(doctype, project_applied=bool(project_field)):
		return []
	companies = permitted_companies(doctype)
	if not companies:
		return []
	where = {**(filters or {}), "company": ["in", companies]}
	or_filters = None
	projects = permitted_projects(doctype) if project_field else None
	if projects is not None:
		or_filters = [[project_field, "in", sorted(projects)], [project_field, "is", "not set"]]
	return frappe.get_all(
		doctype,
		filters=where,
		or_filters=or_filters,
		fields=list(dict.fromkeys([*fields, *([project_field] if project_field else [])])),
		order_by=order_by,
		limit_page_length=limit,
	)
