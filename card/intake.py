# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Intake provenance of an Equipment Transport (#52, #43; FR-146, closure plan WP-N1), and of
the day rows of a Card Monthly Card (#52, #44; FR-158, closure plan WP-N2).

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

A Card Monthly Card may carry a day row that was typed in from paper, a WhatsApp photo, the mobile app
or an external import; the row records the source, an optional external key, the time the source arrived
in the office and the content SHA-256 of the source document. The fields are optional on every day row
(a hand entry stays "manual" and resembles the current form exactly). A (source, key) pair, when both are
present, uniquely identifies a day row within a company and a month-year: a second day row with the same
pair is refused, whether inside the same card draft or in another live card of the same company-month. A
cancelled card frees its source keys, so an amendment keeps them. Two companies may share a key.
`intake_evidence_hash` is read-only on every route: it is kept from the stored day row, carried from the
amendment's source, or taken from a value the server has written itself (adapter path, WP-N3); a Desk
save, REST PUT, `frappe.client.set_value`, savedocs, child REST and bulk update never change it.

Intake never approves, submits or posts anything; the parent's own validation applies unchanged.
The adapter endpoint (`propose`) is WP-N3."""

import hashlib
import re

import frappe
from frappe import _
from frappe.utils import cstr, get_datetime, now_datetime

from card.attachment_validator import (
	check_attachment_content,
	claim_file,
	new_form_prefix,
	require_record_file,
)
from card.cancel_reason import _differs

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


def keep_transport_evidence(doc, method=None):
	"""File.on_trash: the intake evidence of a submitted or cancelled transport is a record of where the
	movement came from; it is never deleted (also not after it was detached from the transport)."""
	if doc.is_folder or not doc.file_url:
		return
	if frappe.db.exists(TRANSPORT, {EVIDENCE_FIELD: doc.file_url, "docstatus": ["!=", 0]}):
		frappe.throw(_("This file is the intake evidence of a submitted or cancelled transport; it is kept."))


# what identifies the evidence bytes of a File row; frozen on the evidence of a submitted or cancelled transport
FROZEN_FILE_FIELDS = ("file_url", "content_hash", "file_name", "file_size")


def keep_transport_evidence_file(doc, method=None):
	"""File.before_validate, before Frappe moves the disk file: the intake evidence of a submitted or cancelled
	transport (or a file sharing its content, whose public / private state Frappe changes with it) keeps its
	private state, URL, content hash, name and size, and is never detached from or moved off its transport. It may
	be attached again to a transport that names it as evidence (the amendment of a cancelled transport keeps the
	file of the transport it amends, and the file stays protected)."""
	if doc.is_folder or doc.is_new():
		return
	moved = any(
		doc.has_value_changed(f) for f in ("attached_to_doctype", "attached_to_name", "attached_to_field")
	)
	flipped = doc.has_value_changed("is_private")
	rewritten = any(doc.has_value_changed(f) for f in FROZEN_FILE_FIELDS)
	if not (moved or flipped or rewritten):
		return
	before = doc.get_doc_before_save() or doc
	urls = {cstr(before.file_url)}
	if flipped:
		# Frappe moves every row with the same content when one row changes its private state
		for content_hash in {before.content_hash, doc.content_hash} - {None, ""}:
			urls.update(frappe.get_all("File", filters={"content_hash": content_hash}, pluck="file_url"))
	kept = _kept_evidence(urls)
	if not kept:
		return
	if (
		flipped
		or rewritten
		or not (
			doc.attached_to_doctype == TRANSPORT
			and doc.attached_to_field == EVIDENCE_FIELD
			and frappe.db.get_value(TRANSPORT, doc.attached_to_name, EVIDENCE_FIELD) in kept
		)
	):
		frappe.throw(
			_(
				"This file is the intake evidence of a submitted or cancelled transport; it stays private and on its transport."
			)
		)


def keep_evidence_of_deleted_transport(doc):
	"""Equipment Transport `on_trash`, before Frappe deletes the row (and then its attachments): a cancelled
	transport with intake evidence is never deleted, so its evidence File and the file on disk are kept. Frappe
	itself refuses deleting a submitted transport; a draft may be deleted with its evidence."""
	if doc.docstatus != 0 and doc.get(EVIDENCE_FIELD):
		frappe.throw(
			_(
				"Transport {0} has intake evidence and is cancelled; it is kept with its evidence and cannot be deleted."
			).format(doc.name)
		)


def _kept_evidence(urls):
	"""The URLs among `urls` that are the intake evidence of a submitted or cancelled transport."""
	urls = [url for url in urls if url]
	if not urls:
		return set()
	return set(
		frappe.get_all(
			TRANSPORT,
			filters={EVIDENCE_FIELD: ["in", urls], "docstatus": ["!=", 0]},
			pluck=EVIDENCE_FIELD,
		)
	)


def freeze_submitted_intake(doc):
	"""`before_update_after_submit`: the intake fields of a submitted transport never change, also when a
	site customisation (Property Setter) marks one of them "allow on submit"."""
	before = doc.get_doc_before_save()
	if not before:
		return
	for fieldname in (*INPUT_FIELDS, HASH_FIELD):
		df = doc.meta.get_field(fieldname)
		if df and _differs(df, doc.get(fieldname), before.get(fieldname)):
			frappe.throw(
				_("The intake source of a submitted transport cannot be changed ({0}).").format(
					_(df.label or fieldname)
				),
				frappe.UpdateAfterSubmitError,
			)


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


# ---------------------------------------------------------------------------
# FR-158 (WP-N2): Card Monthly Card day row intake provenance.
# ---------------------------------------------------------------------------

MONTHLY_CARD = "Card Monthly Card"
MONTHLY_CARD_DAY = "Card Monthly Card Day"
DAY_DEFAULT_SOURCE = "manual"
DAY_SOURCES = (DAY_DEFAULT_SOURCE, "paper", "whatsapp", "mobile", "import")
DAY_HASH_FIELD = "intake_evidence_hash"
# the user-editable intake fields of a day row; the hash is read-only, never changed by a request
DAY_INPUT_FIELDS = ("intake_source", "intake_source_key", "intake_received_on")
DAY_PROVENANCE_FIELDS = (*DAY_INPUT_FIELDS, DAY_HASH_FIELD)
# a SHA-256 hex string (64 chars, lowercase hex)
_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")


def apply_card_day_intake(doc):
	"""Normalise the intake fields of every day row of a Card Monthly Card in `validate`.

	Runs on draft save and on submit (Frappe calls `validate` on both). The hash is read-only and is
	restored from the stored row, carried from the amendment's source, or kept from a server write; a
	client value is never kept. The dedupe guard within the card and across the company-month runs after
	the per-row normalisation so it sees the final (source, key) pair.
	"""
	stored = _stored_day_rows(doc)
	amended_from_rows = (
		_stored_day_rows_of(doc.doctype, doc.get("amended_from")) if doc.get("amended_from") else {}
	)
	for row in doc.get("days") or []:
		_normalise_day_intake(row, stored.get(row.name), amended_from_rows)
	_check_day_intake_dedupe(doc)


def _normalise_day_intake(row, stored_row, amended_from_rows):
	"""Fill `intake_source` in, validate `intake_received_on`, and lock `intake_evidence_hash` down."""
	# intake_source: the only source that is not optional in the end; every row carries one, "manual" by default
	source = cstr(row.get("intake_source")).strip() or None
	if source and source not in DAY_SOURCES:
		frappe.throw(
			_("Day {0}: select a valid intake source.").format(row.get("operation_date") or row.idx),
			frappe.ValidationError,
		)
	row.intake_source = source or DAY_DEFAULT_SOURCE
	row.intake_source_key = cstr(row.get("intake_source_key")).strip() or None
	if row.get("intake_received_on") and get_datetime(row.intake_received_on) > now_datetime():
		frappe.throw(
			_("Day {0}: the intake received time cannot be in the future.").format(
				row.get("operation_date") or row.idx
			),
			frappe.ValidationError,
		)
	row.set(DAY_HASH_FIELD, _server_day_hash(row, stored_row, amended_from_rows))


def _server_day_hash(row, stored_row, amended_from_rows):
	"""The server's value for `intake_evidence_hash`. A client value is kept only when the server wrote it
	itself (adapter path, see `set_card_day_evidence_hash`); otherwise the stored row's hash, the amendment
	source's hash, or empty for a brand new row."""
	if row.flags.get("card_day_intake_evidence_hash"):
		# server-written on this request (adapter path): kept
		value = cstr(row.flags.get("card_day_intake_evidence_hash")).strip().lower()
		row.flags.card_day_intake_evidence_hash = None
		if not _HEX64.fullmatch(value):
			frappe.throw(
				_("Day {0}: the intake evidence hash must be 64 hex characters.").format(
					row.get("operation_date") or row.idx
				),
				frappe.ValidationError,
			)
		return value
	if stored_row:
		return stored_row.get(DAY_HASH_FIELD) or None
	# a new row in an amendment keeps the hash of its source card's day with the same (source, key) pair,
	# if any; otherwise brand new = empty (never a client value)
	if row.get("intake_source_key") and amended_from_rows:
		pair = (row.get("intake_source"), row.get("intake_source_key"))
		for old in amended_from_rows.values():
			if (old.get("intake_source"), old.get("intake_source_key")) == pair:
				return old.get(DAY_HASH_FIELD) or None
	return None


def set_card_day_evidence_hash(row, value: str):
	"""Server-only setter for the adapter path (WP-N3). The value is validated by `_server_day_hash`."""
	if not value:
		return
	row.flags.card_day_intake_evidence_hash = value


def _stored_day_rows(doc):
	"""Every stored day row of this card, keyed by child row name. Empty for a new draft."""
	if doc.is_new() or not doc.name:
		return {}
	return _stored_day_rows_of(doc.doctype, doc.name)


def _stored_day_rows_of(parent_doctype, parent_name):
	if not parent_name:
		return {}
	rows = frappe.get_all(
		MONTHLY_CARD_DAY,
		filters={"parent": parent_name, "parenttype": parent_doctype, "parentfield": "days"},
		fields=["name", "intake_source", "intake_source_key", "intake_received_on", DAY_HASH_FIELD],
	)
	return {r.name: r for r in rows}


def _check_day_intake_dedupe(doc):
	"""Within one card and across the same company-month, (intake_source, intake_source_key) uniquely
	identifies a day row — when both are present. A cancelled card frees its keys. The check takes a
	parent-level lock on the Card Monthly Card row, then a locking read of the sibling cards' day rows
	through `frappe.qb ... .for_update()`, as FR-146 does for transports: under REPEATABLE READ a plain
	read would not see the sibling committed by a concurrent save."""
	pairs = {}
	for row in doc.get("days") or []:
		key = row.get("intake_source_key")
		source = row.get("intake_source")
		if not key or not source or source == DAY_DEFAULT_SOURCE:
			# no key, no source, or "manual" (the default) → not an adapter-side identity
			continue
		pair = (source, key)
		prior = pairs.get(pair)
		if prior is not None:
			frappe.throw(
				_(
					"Intake source {0} / key {1} is used on day {2} and day {3} of this card; one source key names one day row."
				).format(
					source,
					frappe.bold(key),
					prior.get("operation_date") or prior.idx,
					row.get("operation_date") or row.idx,
				),
				DuplicateIntakeError,
			)
		pairs[pair] = row
	if not pairs or not doc.get("company") or not doc.get("month") or not doc.get("year"):
		return
	# lock the parent Card Monthly Card row (not a company lock: multiple months in the same company may
	# proceed in parallel); cancelled cards never clash because the query filters docstatus < 2
	_lock_card_month(doc)
	clashes = _find_day_pair_clashes(doc, list(pairs))
	if clashes:
		# fire on the first clash: one actionable message is clearer than a list
		pair, name, day_name = clashes[0]
		source, key = pair
		frappe.throw(
			_(
				"Intake source {0} / key {1} is already used on day {2} of card {3} ({4}/{5}, company {6})."
			).format(source, frappe.bold(key), day_name, name, doc.month, doc.year, doc.company),
			DuplicateIntakeError,
		)


def _lock_card_month(doc):
	"""Serialise concurrent saves of cards in the same company-month on the parent `tabCard Monthly Card`
	table: the lock that matters is the one the dedupe search reads from. `for_update()` on the `qb`
	select is enough; nothing is written to the locked rows.

	The locking read is run both when `doc.name` is set and when it is not: on a new draft, Frappe assigns
	`name` before `validate` (standard document flow), but a sibling card of the same company-month also
	needs the second request to see the first request's rows."""
	card = frappe.qb.DocType(MONTHLY_CARD)
	(
		frappe.qb.from_(card)
		.select(card.name)
		.where(card.company == doc.company)
		.where(card.month == doc.month)
		.where(card.year == doc.year)
		.where(card.docstatus < 2)
		.for_update()
	).run()


def _find_day_pair_clashes(doc, pairs):
	"""Return (pair, card_name, day_name) tuples for every clashing day row in another live card of the same
	company-month. The locking read on `tabCard Monthly Card Day` with a join to the parent sees the latest
	committed sibling rows (REPEATABLE READ + for_update)."""
	card = frappe.qb.DocType(MONTHLY_CARD)
	day = frappe.qb.DocType(MONTHLY_CARD_DAY)
	own_name = doc.name or ""
	# build an OR of (source, key) pairs; Frappe qb's `isin` works on one column at a time
	q = (
		frappe.qb.from_(day)
		.join(card)
		.on(day.parent == card.name)
		.select(day.name, day.operation_date, day.intake_source, day.intake_source_key, card.name.as_("card"))
		.where(card.company == doc.company)
		.where(card.month == doc.month)
		.where(card.year == doc.year)
		.where(card.docstatus < 2)
		.where(day.parenttype == MONTHLY_CARD)
		.where(day.parentfield == "days")
		.where(card.name != own_name)
	)
	# any of the pairs this request carries
	or_filter = None
	for source, key in pairs:
		c = (day.intake_source == source) & (day.intake_source_key == key)
		or_filter = c if or_filter is None else (or_filter | c)
	if or_filter is None:
		return []
	q = q.where(or_filter).for_update()
	hits = q.run(as_dict=True)
	clashes = []
	for hit in hits:
		pair = (hit.intake_source, hit.intake_source_key)
		clashes.append((pair, hit.card, hit.operation_date or hit.name))
	return clashes


def freeze_submitted_card_day_intake(doc):
	"""`before_update_after_submit` on Card Monthly Card: the intake fields of a day row of a submitted
	card never change, also when a site customisation (Property Setter) marks one of them "allow on submit".
	The parent itself is `allow_on_submit` is checked field by field."""
	before = doc.get_doc_before_save()
	if not before:
		return
	day_meta = frappe.get_meta(MONTHLY_CARD_DAY)
	before_rows = {row.name: row for row in (before.get("days") or []) if row.name}
	for row in doc.get("days") or []:
		stored_row = before_rows.get(row.name)
		if not stored_row:
			# a new row after submit is refused by Frappe itself; not this hook's concern
			continue
		for fieldname in DAY_PROVENANCE_FIELDS:
			df = day_meta.get_field(fieldname)
			if df and _differs(df, row.get(fieldname), stored_row.get(fieldname)):
				frappe.throw(
					_("The intake provenance of a submitted card day cannot be changed ({0}).").format(
						_(df.label or fieldname)
					),
					frappe.UpdateAfterSubmitError,
				)
