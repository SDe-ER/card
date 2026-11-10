# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-131: generic company scope for CARD DocTypes (has_permission, permission_query_conditions, DocShare).

The same isolation the existing CARD hooks give their own DocTypes (``has_card_permission``,
``has_diesel_fill_permission``, ``assignment_query_conditions``, FR-129 ``has_review_permission``), written once
for any DocType. ``card/hooks.py`` registers these functions for every DocType in ``SCOPED_DOCTYPES``, so a later
package that adds one of those DocTypes needs no edit of ``hooks.py``.

A document's companies are:

- its ``company`` field (the value sent and, for a saved document, the value stored);
- the company of each top-level Link field to a DocType in ``COMPANY_SOURCES`` (Card Equipment, Project): the
  link sent, for a new document or when it was changed; for a DocType without a ``company`` field also the
  stored link of a saved document (it is what places the record in a company). With a ``company`` field an
  unchanged link is not re-read.

A user limited to some companies (Company User Permissions that apply to that DocType, as the CARD lists use) is
refused a document when any of those companies is outside the limit; a user without a company restriction is not
affected. A controller can only deny (Frappe 16 ``has_controller_permissions`` treats a falsy return as a denial),
so "no objection" is ``True``. An empty company or link adds no company (the mandatory field stops the save).

A DocType of the list that does not exist yet (its package is not merged) is never called by Frappe: the hooks
are inert. A registered DocType without a ``company`` field and without a source link is not scoped; the test
``test_company_scope`` refuses such a DocType, so its package must add one of them."""

import frappe
from frappe import _

# The DocTypes the close-all plan adds (closure-plan section C). Only these use the generic functions; a DocType
# that already has its own hook keeps it.
SCOPED_DOCTYPES = (
	"Equipment Meter Reading",
	"Card Daily Log",
	"Card Rate Agreement",
	"Card Period Run",
	"Card Approval Delegation",
	"Diesel Dispense",
	"Tank Dip Reading",
	"Equipment Operating Group",
	"Card Intake Record",
)

# Link target DocType -> its company field: a link to one of these carries that record's company.
COMPANY_SOURCES = {
	"Card Equipment": "company",
	"Project": "company",
}

HAS_PERMISSION = "card.company_scope.has_company_permission"
QUERY_CONDITIONS = "card.company_scope.company_query_conditions"


def _has_company_field(meta):
	field = meta.get_field("company")
	return bool(field and field.fieldtype == "Link" and field.options == "Company")


def _source_fields(meta):
	"""Top-level Link fields of ``meta`` that point to a company source, as (fieldname, target)."""
	return [
		(field.fieldname, field.options)
		for field in meta.fields
		if field.fieldtype == "Link" and field.options in COMPANY_SOURCES and field.fieldname != "company"
	]


def is_scoped(doctype):
	"""True when ``doctype`` has a Company ``company`` field or a link to a company source."""
	meta = frappe.get_meta(doctype)
	return _has_company_field(meta) or bool(_source_fields(meta))


def _restricted(user, doctype):
	from card.party_registry import _restricted_companies

	return _restricted_companies(user or frappe.session.user, doctype)


def document_companies(doc):
	"""The companies ``doc`` belongs to or would belong to after this save (see the module docstring)."""
	meta = frappe.get_meta(doc.doctype)
	with_company = _has_company_field(meta)
	sources = _source_fields(meta)
	stored = None
	if not doc.is_new():
		columns = (["company"] if with_company else []) + [field for field, _target in sources]
		if columns:
			stored = frappe.db.get_value(doc.doctype, doc.name, columns, as_dict=True)
	owners = set()
	if with_company:
		owners.add(doc.get("company"))
		if stored:
			owners.add(stored.get("company"))
	for field, target in sources:
		value = doc.get(field)
		old = stored.get(field) if stored else None
		if value and (not stored or value != old):
			owners.add(frappe.db.get_value(target, value, COMPANY_SOURCES[target]))
		if old and not with_company:
			# no company field: the stored link is what places the saved document in a company
			owners.add(frappe.db.get_value(target, old, COMPANY_SOURCES[target]))
	owners.discard(None)
	owners.discard("")
	return owners


def stored_companies(doctype, name):
	"""The companies of the saved document ``doctype``/``name``, read from the database only."""
	meta = frappe.get_meta(doctype)
	if _has_company_field(meta):
		company = frappe.db.get_value(doctype, name, "company")
		return {company} if company else set()
	owners = set()
	sources = _source_fields(meta)
	if sources:
		row = frappe.db.get_value(doctype, name, [field for field, _target in sources], as_dict=True) or {}
		for field, target in sources:
			if row.get(field):
				owners.add(frappe.db.get_value(target, row.get(field), COMPANY_SOURCES[target]))
	owners.discard(None)
	owners.discard("")
	return owners


def has_company_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level check for every path (read, create, REST/Desk save, set_value, submit, cancel, delete):
	every company of the document (sent, stored and of its new or changed source links) must be permitted, so a
	record can be neither read, created in, moved to, nor taken over from another company."""
	companies = _restricted(user, doc.doctype)
	if companies is None:
		return True
	return all(company in companies for company in document_companies(doc))


def company_query_conditions(user=None, doctype=None):
	"""List twin of ``has_company_permission``: rows of permitted companies only. A row with an empty company or
	link is shown, as ``has_company_permission`` allows it. Empty for an unrestricted user, a DocType that does
	not exist, or a DocType without a company field or source link."""
	if not doctype or not frappe.db.exists("DocType", doctype):
		return ""
	companies = _restricted(user, doctype)
	if companies is None:
		return ""
	meta = frappe.get_meta(doctype)
	with_company = _has_company_field(meta)
	sources = _source_fields(meta)
	if not with_company and not sources:
		return ""
	if not companies:
		return "1=0"
	values = ", ".join(frappe.db.escape(company) for company in companies)
	table = f"`tab{doctype}`"
	if with_company:
		return f"(ifnull({table}.`company`, '') = '' or {table}.`company` in ({values}))"
	parts = [
		f"(ifnull({table}.`{field}`, '') = '' or {table}.`{field}` in"
		f" (select s.`name` from `tab{target}` s where s.`{COMPANY_SOURCES[target]}` in ({values})))"
		for field, target in sources
	]
	return "(" + " and ".join(parts) + ")"


def deny_cross_company_share(doc, method=None):
	"""DocShare validate: Frappe 16 ``has_permission`` falls back to a DocShare after a controller hook denied
	(frappe/permissions.py), so a share would reopen a scoped record of another company. For a DocType of
	``SCOPED_DOCTYPES``: refuse a share with everyone, and a share with a user who is not permitted for every
	stored company of the record. Every other DocType is not affected."""
	if doc.share_doctype not in SCOPED_DOCTYPES or not frappe.db.exists("DocType", doc.share_doctype):
		return
	if doc.get("everyone") or not doc.user:
		frappe.throw(
			_("A CARD record of type {0} cannot be shared with everyone.").format(_(doc.share_doctype)),
			frappe.PermissionError,
		)
	companies = _restricted(doc.user, doc.share_doctype)
	if companies is None:
		return
	outside = sorted(stored_companies(doc.share_doctype, doc.share_name) - set(companies))
	if outside:
		frappe.throw(
			_(
				"This CARD record of type {0} belongs to company {1} and cannot be shared with a user outside that company."
			).format(_(doc.share_doctype), ", ".join(outside)),
			frappe.PermissionError,
		)
