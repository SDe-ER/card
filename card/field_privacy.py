# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Financial privacy of Card Equipment (Owner decision 2026-10-31).

The Asset purchase value, the internal hourly rate and the cost centers (the equipment's and the Asset's) sit at
permlevel 2, read only by System Manager, Card Manager and Accounts Manager (writes as before); the commercial terms
stay at permlevel 1. Frappe applies these levels to the form, the REST API, list and report views and their exports.
One path it does not cover: a document's change history (Version) reaches every reader of the document, at any
level, with the raw values. New Versions of Card Equipment therefore keep who changed a field above level 0 and
when, but not its values. Nothing is deleted; the data stays on the record."""

import json

import frappe
from frappe.utils import cint

RESTRICTED_LEVEL = 2  # financial fields: managers and accountants only
HISTORY_LEVEL = 1  # Versions reach level-0 readers: every field above level 0 is masked there
MASKED = "•••"
PRIVATE_DOCTYPES = ("Card Equipment",)


def restricted_fields(doctype, level=HISTORY_LEVEL):
	return {df.fieldname for df in frappe.get_meta(doctype).fields if cint(df.permlevel) >= level}


def mask_restricted_version(doc, method=None):
	"""Version before_insert: mask the values of every field above level 0 in the change history of a private
	doctype, in its own fields and in its child-table rows."""
	if doc.ref_doctype not in PRIVATE_DOCTYPES or not doc.data:
		return
	meta = frappe.get_meta(doc.ref_doctype)
	restricted = restricted_fields(doc.ref_doctype)
	child = {df.fieldname: restricted_fields(df.options) for df in meta.get_table_fields()}
	data = json.loads(doc.data)
	masked = _mask_changes(data.get("changed"), restricted)
	for table, row in (data.get("added") or []) + (data.get("removed") or []):
		for field in child.get(table, ()):
			if isinstance(row, dict) and field in row:
				row[field] = MASKED
				masked = True
	for entry in data.get("row_changed") or []:
		if len(entry) == 4:
			masked = _mask_changes(entry[3], child.get(entry[0], ())) or masked
	if masked:
		doc.data = frappe.as_json(data, indent=None, separators=(",", ":"))


def _mask_changes(changes, restricted):
	masked = False
	for change in changes or []:
		if change and change[0] in restricted:
			change[1:] = [MASKED, MASKED]
			masked = True
	return masked
