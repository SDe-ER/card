# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-131: generic company scope for CARD DocTypes (has_permission, permission_query_conditions, DocShare).

The same isolation the existing CARD hooks give their own DocTypes (``has_card_permission``,
``has_diesel_fill_permission``, ``assignment_query_conditions``, FR-129 ``has_review_permission``), written once
for any DocType. ``card/hooks.py`` registers these functions for every DocType in ``SCOPED_DOCTYPES``, so a later
package that adds one of those DocTypes needs no edit of ``hooks.py``.

A document's companies are:

- its ``company`` field (the value sent and, for a saved document, the value stored);
- the company of each top-level Link field to a DocType in ``COMPANY_SOURCES`` (Card Equipment, Project, Card
  Monthly Card, Warehouse, Card Daily Log): the link sent, for a new document or when it was changed; for a DocType without a
  ``company`` field also the stored link of a saved document (it is what places the record in a company). With a
  ``company`` field an unchanged link is not re-read.

A user limited to some companies (Company User Permissions that apply to that DocType, as the CARD lists use) is
refused a document when any of those companies is outside the limit, and refused a NEW document that has no
company yet (empty ``company`` and no source link that resolves one): the server could set a company the user
may not use. A user without a company restriction is not affected. A controller can only deny (Frappe 16
``has_controller_permissions`` treats a falsy return as a denial), so "no objection" is ``True``.

Only DocTypes of the CARD module (``meta.module == "Card"``) are checked: a DocType of another app is never
affected, even when it is registered by mistake. A DocType of the list that does not exist yet (its package is not
merged) is never called by Frappe: the hooks are inert. A registered DocType without a ``company`` field and
without a source link is not scoped; ``test_company_scope`` refuses such a planned DocType.

Child-table rows are NOT checked here: a company carried by a child row (for example a Card Equipment link on a
line) is the owning package's responsibility to validate, with ``check_child_companies`` in its controller."""

import frappe
from frappe import _

CARD_MODULE = "Card"

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
	"Card Monthly Card": "company",
	"Warehouse": "company",
	# FR-142: a daily log's amended_from (Frappe copies the original's attachments into the amendment)
	"Card Daily Log": "company",
}

HAS_PERMISSION = "card.company_scope.has_company_permission"
QUERY_CONDITIONS = "card.company_scope.company_query_conditions"


def _card_meta(doctype):
	"""The cached meta of ``doctype`` when it exists and belongs to the CARD module, else None."""
	if not doctype:
		return None
	try:
		meta = frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		return None
	return meta if meta.module == CARD_MODULE else None


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


def _source_company(target, name):
	return frappe.db.get_value(target, name, COMPANY_SOURCES[target])


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
			owners.add(_source_company(target, value))
		if old and not with_company:
			# no company field: the stored link is what places the saved document in a company
			owners.add(_source_company(target, old))
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
				owners.add(_source_company(target, row.get(field)))
	owners.discard(None)
	owners.discard("")
	return owners


def has_company_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level check for every path (read, create, REST/Desk save, set_value, submit, cancel, delete):
	every company of the document (sent, stored and of its new or changed source links) must be permitted, so a
	record can be neither read, created in, moved to, nor taken over from another company. A new document of a
	restricted user must already carry a company (field or source link)."""
	if not _card_meta(doc.doctype):
		return True
	companies = _restricted(user, doc.doctype)
	if companies is None:
		return True
	owners = document_companies(doc)
	if not owners and doc.is_new():
		return False  # the server would set a company the user may not be allowed to use
	return all(company in companies for company in owners)


def company_query_conditions(user=None, doctype=None):
	"""List twin of ``has_company_permission``: rows of permitted companies only. A row with an empty company or
	link is shown, as ``has_company_permission`` allows a saved one. Empty for an unrestricted user, a DocType that
	does not exist or is not of the CARD module, or a DocType without a company field or source link."""
	meta = _card_meta(doctype)
	if not meta:
		return ""
	companies = _restricted(user, doctype)
	if companies is None:
		return ""
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
	parts = []
	for field, target in sources:
		subquery = f"select s.`name` from `tab{target}` s where s.`{COMPANY_SOURCES[target]}` in ({values})"
		parts.append(f"(ifnull({table}.`{field}`, '') = '' or {table}.`{field}` in ({subquery}))")
	return "(" + " and ".join(parts) + ")"


def check_child_companies(doc, table_field, link_field):
	"""For a package controller (validate): every row of the child table ``table_field`` whose ``link_field``
	points to a company source must belong to the document's company. Raises ValidationError naming the rows.
	The generic hooks never read child rows; a package that keeps company-bearing links on rows calls this."""
	company = doc.get("company")
	if not company:
		return
	child = frappe.get_meta(doc.meta.get_field(table_field).options)
	field = child.get_field(link_field)
	target = field.options if field and field.fieldtype == "Link" else None
	if target not in COMPANY_SOURCES:
		frappe.throw(
			_("CARD company check: {0} is not a link to a company-owned record.").format(link_field),
			frappe.ValidationError,
		)
	wrong = []
	for row in doc.get(table_field) or []:
		value = row.get(link_field)
		if value:
			other = _source_company(target, value)
			if other and other != company:
				wrong.append(f"{row.idx} ({value}: {other})")
	if wrong:
		frappe.throw(
			_("CARD company check: rows {0} belong to a company other than {1}.").format(
				", ".join(wrong), company
			),
			frappe.ValidationError,
		)


def deny_cross_company_share(doc, method=None):
	"""DocShare validate: Frappe 16 ``has_permission`` falls back to a DocShare after a controller hook denied
	(frappe/permissions.py), so a share would reopen a scoped record of another company. For a CARD DocType of
	``SCOPED_DOCTYPES``: refuse a share with everyone, and a share with a user who is not permitted for every
	stored company of the record. Every other DocType is not affected."""
	if doc.share_doctype not in SCOPED_DOCTYPES or not _card_meta(doc.share_doctype):
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
