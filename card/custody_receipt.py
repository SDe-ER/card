# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""The signed tool-custody receipt stays a private file of its own custody record (#113).

Frappe shares one disk file between File rows with the same content and URL, and making ANY of
those rows public makes all of them public (File.handle_is_private_changed ->
update_existing_file_docs). A file's owner may also make it public, detach it or delete it, and
anybody who can read it may attach it to another record. These File hooks refuse that for receipts
only; every other file keeps Frappe's behaviour. No Frappe setting or core code changes.

A file is a receipt when a custody record names its URL in `handover_receipt` (the record decides,
not the File row's own attached_to fields, which its owner can edit), or when it shares its disk
content with such a file."""

import frappe
from frappe import _

CUSTODY = "Employee Tool Custody"
RECEIPT_FIELD = "handover_receipt"


def _receipt_urls(urls):
	urls = [url for url in urls if url]
	if not urls:
		return set()
	return set(frappe.get_all(CUSTODY, filters={RECEIPT_FIELD: ["in", urls]}, pluck=RECEIPT_FIELD))


def _shared_receipts(doc):
	"""Receipt URLs this File row is, was, or shares its disk content with."""
	urls = {doc.file_url}
	before = None if doc.is_new() else doc.get_doc_before_save()
	if before:
		urls.add(before.file_url)
	if doc.content_hash:
		urls.update(frappe.get_all("File", filters={"content_hash": doc.content_hash}, pluck="file_url"))
	return _receipt_urls(urls)


def _receipt_of(record, url):
	"""True when custody `record` names `url` as its receipt."""
	return bool(record) and frappe.db.get_value(CUSTODY, record, RECEIPT_FIELD) == url


def _uploaded_by_user(url):
	"""The session user uploaded a File row of this receipt (a scan reused on his own drafts)."""
	return bool(frappe.db.exists("File", {"file_url": url, "owner": frappe.session.user}))


def keep_private(doc, method=None):
	"""File.before_validate, before Frappe moves the disk file: a receipt, or a file sharing its
	content, never becomes public, and a receipt is never detached from its custody record."""
	if doc.is_folder or doc.is_new():
		return
	moved = any(
		doc.has_value_changed(f) for f in ("attached_to_doctype", "attached_to_name", "attached_to_field")
	)
	if not (moved or (doc.has_value_changed("is_private") and not doc.is_private)):
		return  # nothing that could expose or detach a receipt
	receipts = _shared_receipts(doc)
	if not receipts:
		return
	if not doc.is_private:
		frappe.throw(_("This file is a signed tool-custody receipt; it stays private."))
	if (
		moved
		and doc.file_url in receipts
		and not (doc.attached_to_doctype == CUSTODY and _receipt_of(doc.attached_to_name, doc.file_url))
	):
		frappe.throw(_("This file is a signed tool-custody receipt; it stays on its custody record only."))


def keep_on_its_record(doc, method=None):
	"""File.before_insert: a copy of a receipt's content stays private, on a custody record that
	names it (its own record, an amending record, another draft of the same uploader), or
	unattached when its uploader adds the same scan again."""
	if doc.is_folder:
		return
	receipts = _shared_receipts(doc)
	if not receipts:
		return
	if not doc.is_private:
		frappe.throw(_("This file is a signed tool-custody receipt; it stays private."))
	if doc.attached_to_doctype == CUSTODY and _receipt_of(doc.attached_to_name, doc.file_url):
		return
	if not doc.attached_to_doctype and any(_uploaded_by_user(url) for url in receipts):
		return
	frappe.throw(_("This file is a signed tool-custody receipt; it stays on its custody record only."))


def keep_while_recorded(doc, method=None):
	"""File.on_trash: a receipt of a confirmed or cancelled custody record is evidence; it is never
	deleted (also not after it was detached from the record)."""
	if doc.is_folder or not doc.file_url:
		return
	if frappe.db.exists(CUSTODY, {RECEIPT_FIELD: doc.file_url, "docstatus": ["!=", 0]}):
		frappe.throw(_("This file is a signed tool-custody receipt of a confirmed movement; it is kept."))
