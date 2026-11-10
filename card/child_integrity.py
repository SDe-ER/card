# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-153 (SEC-2): a child row of a CARD document stays on the document it belongs to.

Frappe stores an existing child row with ``UPDATE ... WHERE name=%s`` and writes the row's ``parent``,
``parenttype`` and ``parentfield`` from the document being saved (frappe/model/document.py ``update_child_table``
and ``db_update``; the same in Frappe 16.55.2). It never compares them with the stored row, so a save that carries
the name of a row of another document moves that row to the saved document. The other document is never loaded
or saved, so none of its own checks run.

The checks here refuse that, on every route that stores rows:

- ``check_rows`` (parent ``validate``, ``before_update_after_submit`` and ``before_cancel``; Frappe skips
  validate on a cancel): each row that is not new and whose name is stored in the child table must be stored on
  this document, in this table field. One query per child table field.
- ``check_row`` (child ``validate``, ``before_update_after_submit`` and ``before_cancel``): a child row saved on
  its own (REST ``/api/resource/<child>``, ``frappe.client.save`` or ``bulk_update`` of a child) keeps its stored
  parent, parent type and parent field. Frappe runs a child's own events only when the child is saved on its own,
  never inside its parent's save (a stored row of a submitted document is saved as an update after submit).

New rows (no name, a name that is not stored yet, an amendment or a ``frappe.copy_doc`` copy) are not checked:
Frappe inserts them. Rows removed or reordered on the document are not affected.

The DocTypes come from CARD's own DocType JSON files (``card_doctypes``), so a new CARD DocType with a table is
covered without a change here. No ERPNext or Frappe DocType is hooked."""

import json
import os

import frappe
from frappe import _
from frappe.utils import cstr

EVENTS = ("validate", "before_update_after_submit", "before_cancel")
PARENT_HANDLER = "card.child_integrity.check_rows"
CHILD_HANDLER = "card.child_integrity.check_row"
TABLE_FIELDTYPES = ("Table", "Table MultiSelect")


class ForeignChildRowError(frappe.ValidationError):
	pass


def card_doctypes(app_path=None):
	"""Read CARD's DocType JSON files (no database) and return ``(parents, children)``: the CARD DocTypes with a
	Table or Table MultiSelect field (virtual DocTypes excluded) and the CARD child DocTypes."""
	root = app_path or os.path.dirname(os.path.abspath(__file__))
	parents, children = [], []
	for dirpath, _dirnames, filenames in os.walk(root):
		if os.path.basename(os.path.dirname(dirpath)) != "doctype":
			continue
		filename = os.path.basename(dirpath) + ".json"
		if filename not in filenames:
			continue
		with open(os.path.join(dirpath, filename), encoding="utf-8") as f:
			meta = json.load(f)
		if meta.get("doctype") != "DocType" or meta.get("is_virtual"):
			continue
		if meta.get("istable"):
			children.append(meta["name"])
		elif any(df.get("fieldtype") in TABLE_FIELDTYPES for df in meta.get("fields") or []):
			parents.append(meta["name"])
	return sorted(parents), sorted(children)


def _as_list(value):
	if not value:
		return []
	return list(value) if isinstance(value, list | tuple) else [value]


def extend_doc_events(doc_events, app_path=None):
	"""Append the FR-153 handlers to ``doc_events`` (hooks.py) for the CARD DocTypes only. Existing handlers keep
	their order; a dict or list shared by several DocTypes is copied, never changed in place."""
	parents, children = card_doctypes(app_path)
	for doctype, events, handler in (
		*((dt, EVENTS, PARENT_HANDLER) for dt in parents),
		*((dt, EVENTS, CHILD_HANDLER) for dt in children),
	):
		entry = dict(doc_events.get(doctype) or {})
		for event in events:
			handlers = _as_list(entry.get(event))
			if handler not in handlers:
				entry[event] = [*handlers, handler]
		doc_events[doctype] = entry
	return doc_events


def _refuse(doctype, name, row_doctype, row_name):
	frappe.throw(
		_(
			"{0} {1} cannot store row {2} of {3}: the row belongs to another document. Remove it and add the line as a new row."
		).format(_(doctype), name, row_name, _(row_doctype)),
		ForeignChildRowError,
		title=_("Row of another document"),
	)


def check_rows(doc, method=None):
	"""Parent hook: refuse a stored row of another document (or another table field of this one)."""
	if doc.is_new() or doc.meta.istable:
		# a new document's rows are always inserted with new names (Document.insert -> set_new_name)
		return
	for df in doc.meta.get_table_fields():
		if df.get("is_virtual"):
			continue
		names = {cstr(row.name) for row in doc.get(df.fieldname) or [] if row.name and not row.is_new()}
		if not names:
			continue
		table = frappe.qb.DocType(df.options)
		stored = (
			frappe.qb.from_(table)
			.select(table.name, table.parent, table.parenttype, table.parentfield)
			.where(table.name.isin(sorted(names)))
			.run(as_dict=True)
		)
		for row in stored:
			if (cstr(row.parent), cstr(row.parenttype), cstr(row.parentfield)) != (
				cstr(doc.name),
				doc.doctype,
				df.fieldname,
			):
				_refuse(doc.doctype, doc.name, df.options, row.name)


def check_row(doc, method=None):
	"""Child hook (a child row saved on its own): its parent, parent type and parent field stay the stored ones."""
	if doc.is_new() or not doc.name:
		return
	stored = frappe.db.get_value(doc.doctype, doc.name, ["parent", "parenttype", "parentfield"], as_dict=True)
	if stored and (cstr(stored.parent), cstr(stored.parenttype), cstr(stored.parentfield)) != (
		cstr(doc.parent),
		cstr(doc.parenttype),
		cstr(doc.parentfield),
	):
		_refuse(doc.parenttype or stored.parenttype, doc.parent or stored.parent, doc.doctype, doc.name)
