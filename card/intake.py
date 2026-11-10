# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Intake provenance of an Equipment Transport (#52, #43; FR-146, closure plan WP-N1).

A transport entered from a paper sheet, a WhatsApp message or an email may keep where it came from:
the channel, an external source key, the time it was received and one private evidence file. Every
field is optional and empty by default; a transport saved without them behaves exactly as before.

* Source key: one live transport (draft or submitted) per company and key. A cancelled transport
  frees its key, so the amendment of a cancelled transport keeps it. Two companies may use the same
  key. The check takes a lock on the company row (SELECT ... FOR UPDATE, nothing is written to it) and
  then reads the clashing transports with a locking read: under REPEATABLE READ a locking read returns
  the latest committed rows, not the request's snapshot, so the second of two concurrent saves sees the
  first one (a plain read after the lock would still read the old snapshot).
* Evidence hash: the SHA-256 of the evidence file's bytes, computed here from the private File row of
  this transport. A hash sent by the client is never kept: without evidence the hash is empty, with
  unchanged evidence the stored hash is kept, with new evidence it is computed again.
* The same evidence on another live transport of the company only warns (owner rule 2026-11-10: a new
  rule is opt-in or warn-only); one sheet may legitimately list several moves.

Intake never approves, submits or posts anything; the transport's own validation applies unchanged.
The adapter endpoint (`propose`) is WP-N3."""

import hashlib

import frappe
from frappe import _
from frappe.utils import cstr, get_datetime, now_datetime

from card.attachment_validator import (
	check_attachment_content,
	claim_file,
	new_form_prefix,
	require_record_file,
)

TRANSPORT = "Equipment Transport"
DEFAULT_CHANNEL = "Manual"
CHANNELS = (DEFAULT_CHANNEL, "Paper", "WhatsApp", "Email", "Other")
EVIDENCE_FIELD = "intake_evidence"
HASH_FIELD = "intake_evidence_hash"
# the fields that make a transport an intake record; the hash is derived, never an input
INPUT_FIELDS = ("intake_source_key", "intake_channel", "intake_received_on", EVIDENCE_FIELD)


class DuplicateIntakeError(frappe.ValidationError):
	pass


def apply_transport_intake(doc):
	"""Normalise and check the intake fields of a transport in `validate` (draft save and submit)."""
	doc.intake_source_key = cstr(doc.get("intake_source_key")).strip() or None
	_set_evidence_hash(doc)
	if not any(doc.get(field) for field in INPUT_FIELDS):
		doc.intake_channel = None
		return
	if not doc.intake_channel:
		doc.intake_channel = DEFAULT_CHANNEL
	elif doc.intake_channel not in CHANNELS:
		frappe.throw(_("Select a valid intake channel."))
	if doc.get("intake_received_on") and get_datetime(doc.intake_received_on) > now_datetime():
		frappe.throw(_("The intake received time cannot be in the future."))
	if doc.intake_source_key:
		check_source_key(doc)
	if doc.get(HASH_FIELD):
		warn_reused_evidence(doc)


def claim_transport_evidence(doc):
	"""`on_update`: attach the user's own unattached upload to the transport that uses it."""
	row = doc.flags.get("intake_evidence_row")
	if row:
		claim_file(row, doc.doctype, doc.name, EVIDENCE_FIELD)
		doc.flags.intake_evidence_row = None


def check_source_key(doc):
	"""Refuse a second live transport of the company with the same source key (company lock, locking read)."""
	frappe.db.get_value("Company", doc.company, "name", for_update=True)
	transport = frappe.qb.DocType(TRANSPORT)
	clash = (
		frappe.qb.from_(transport)
		.select(transport.name)
		.where(transport.company == doc.company)
		.where(transport.intake_source_key == doc.intake_source_key)
		.where(transport.docstatus < 2)
		.where(transport.name != (doc.name or ""))
		.orderby(transport.creation)
		.limit(1)
		.for_update()
	).run(pluck=True)
	if clash:
		frappe.throw(
			_("Intake source key {0} is already used by transport {1} of company {2}.").format(
				frappe.bold(doc.intake_source_key), clash[0], doc.company
			),
			DuplicateIntakeError,
		)


def warn_reused_evidence(doc):
	"""Warn (never refuse) when the same evidence is on another live transport of the company; returns them."""
	others = frappe.get_all(
		TRANSPORT,
		filters={
			"company": doc.company,
			HASH_FIELD: doc.get(HASH_FIELD),
			"docstatus": ["<", 2],
			"name": ["!=", doc.name or ""],
		},
		pluck="name",
		order_by="creation asc",
		limit=5,
	)
	if others:
		frappe.msgprint(
			_(
				"The same intake evidence is already attached to transport {0}. Check that it is not entered twice."
			).format(", ".join(others)),
			indicator="orange",
			alert=True,
		)
	return others


def _set_evidence_hash(doc):
	"""The hash is always the server's: computed from the private evidence file, or the stored value."""
	doc.flags.intake_evidence_row = None
	url = doc.get(EVIDENCE_FIELD)
	if not url:
		doc.set(HASH_FIELD, None)
		return
	stored = (
		None
		if doc.is_new()
		else frappe.db.get_value(doc.doctype, doc.name, [EVIDENCE_FIELD, HASH_FIELD], as_dict=True)
	)
	if stored and stored.get(EVIDENCE_FIELD) == url and stored.get(HASH_FIELD):
		doc.set(HASH_FIELD, stored.get(HASH_FIELD))
		return
	if stored and stored.get(EVIDENCE_FIELD) == url:
		# the stored evidence without a stored hash: hash the file already on this transport
		row = require_record_file(url, doc.doctype, doc.name, attached_only=True)
	elif (
		doc.is_new()
		and doc.get("amended_from")
		and url == frappe.db.get_value(doc.doctype, doc.amended_from, EVIDENCE_FIELD)
	):
		# an amendment keeps the evidence of the cancelled transport it amends
		row = require_record_file(url, doc.doctype, doc.amended_from, attached_only=True)
	else:
		row = require_record_file(url, doc.doctype, doc.name, _temporary_name(doc))
		check_attachment_content(url, file_row=row)
		doc.flags.intake_evidence_row = row
	doc.set(HASH_FIELD, file_sha256(row))


def _temporary_name(doc):
	"""The unsaved-form name an upload may be attached to; anything else is dropped so Frappe never relinks
	files of another record."""
	temporary = doc.get("__temporary_name") if doc.is_new() else None
	if temporary and not cstr(temporary).startswith(new_form_prefix(doc.doctype)):
		doc.__dict__.pop("__temporary_name", None)
		return None
	return temporary


def file_sha256(file_row: str) -> str:
	"""SHA-256 hex of a File row's raw bytes (official File API, no text decoding)."""
	try:
		content = frappe.get_doc("File", file_row).get_content(encodings=())
		if not isinstance(content, bytes):
			raise ValueError("not bytes")
	except Exception:
		frappe.throw(_("The attached file could not be read."))
	return hashlib.sha256(content).hexdigest()
