# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""The signed tool-custody receipt stays a private file of its own custody record (#113).

Frappe shares one disk file between File rows with the same content and URL, and making ANY of
those rows public makes all of them public (File.handle_is_private_changed ->
update_existing_file_docs). Its owner may also make it public, and anybody who can read it may
attach it to another record. These File hooks refuse that for receipts only; every other file
keeps Frappe's behaviour. No Frappe setting or core code changes."""

import frappe
from frappe import _

CUSTODY = "Employee Tool Custody"


def _receipts(doc):
	"""Custody records whose receipt shares this file's content or URL."""
	shared = [value for value in (doc.content_hash, doc.file_url) if value]
	if not shared:
		return set()
	rows = frappe.get_all(
		"File",
		filters={"attached_to_doctype": CUSTODY, "name": ["!=", doc.name or ""]},
		or_filters={"content_hash": doc.content_hash or "-", "file_url": doc.file_url or "-"},
		pluck="attached_to_name",
	)
	if doc.attached_to_doctype == CUSTODY and not doc.is_new():
		rows.append(doc.attached_to_name)  # the receipt itself
	return set(rows)


def keep_private(doc, method=None):
	"""File.before_validate (before Frappe moves the disk file): a receipt, or a file sharing its
	content, never becomes public."""
	if doc.is_folder or doc.is_new() or doc.is_private or not doc.has_value_changed("is_private"):
		return
	if _receipts(doc):
		frappe.throw(_("This file is a signed tool-custody receipt; it stays private."))


def keep_on_its_record(doc, method=None):
	"""File.before_insert: the receipt's content is not attached to any other record."""
	if doc.is_folder:
		return
	receipts = _receipts(doc)
	if receipts and not (doc.attached_to_doctype == CUSTODY and doc.attached_to_name in receipts):
		frappe.throw(_("This file is a signed tool-custody receipt; it stays on its custody record only."))
