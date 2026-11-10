# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-143 (FR-006, WP-D1; #35, #51, #123): separation of duties on the monthly card.

What "approval" means here: a monthly card has no review step and no Workflow today (the Workflow states are WP-D2,
owner decision O-10). Its approval is its submit (docstatus 0 -> 1): the submitted card is final, is billed and
only changes by cancel and amend. So the user who submits a card approves it, and D1 adds only the guard on that
step: the approver must not be a preparer of the card.

Server-written fields (read only, no copy; a client value is never kept on any route):

- ``edited_by``: every user who saved the card as a draft (creation included), one per line. A submit request
  that also changes an editable field or row (REST PUT or ``frappe.client.submit`` with changed values, a REST
  insert with docstatus 1) records its user as an editor too; a plain submit does not.
- ``submitted_by``, ``approved_by``, ``approved_on``: the user who submitted (approved) the card and when.
  Without a review step they name the same user; WP-D2 keeps ``approved_by`` = the user of the transition that
  submits the card.
- ``self_approved``: the approver was a preparer and the company rule let it through (Warn only).

Preparers: the creator (``owner``, read from the database) and every editor of the card and of every card of its
amendment chain (``amended_from``, read from the database as well). A card saved before FR-143 has no editor list:
the user who last saved the draft (``modified_by``) is taken as its editor at its next save or submit, and an
older card of the chain counts with its creator only. The approver of an earlier card of the chain is not a
preparer of the amendment (it is the normal approver of the correction).

Rule per company (Card Company Settings ``card_approval_rule``, owner decision O-07): "Warn only (card approval)"
(the default, also when the company has no row or the value is empty) submits with a warning and marks the card
``self_approved``; "Refuse (card approval)" refuses the submit. No role is exempt, Administrator and System
Manager included. Existing cards are never changed: the fields stay empty on cards submitted before FR-143.

Routes: the checks are ``doc_events`` (card/hooks.py) on validate, before_submit, before_update_after_submit and
before_cancel, so the form, REST v1/v2 (insert with docstatus 1, PUT), ``frappe.client.insert/save/submit/
set_value``, ``savedocs``, bulk update and bulk submit/cancel and Data Import all pass through them. Concurrent
saves of one card are serialized by Frappe's locking read of the stored card (``check_if_latest``); the stored
editors and creator are read here with a locking read too (never the request's REPEATABLE READ snapshot).

The Card Daily Log keeps its own rule (Card Daily Log Settings ``self_approval_rule``, FR-142); the two are not
merged (decision recorded with FR-143)."""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import now_datetime

from card.cancel_reason import _differs
from card.settings import company_setting

DOCTYPE = "Card Monthly Card"
RULE_FIELD = "card_approval_rule"
RULE_WARN = "Warn only (card approval)"
RULE_REFUSE = "Refuse (card approval)"

# written at the submit only (every other save clears them)
APPROVAL_FIELDS = ("submitted_by", "approved_by", "approved_on", "self_approved")
# written by the server only; restored from the database after the submit (update after submit, cancel)
SERVER_FIELDS = (*APPROVAL_FIELDS, "edited_by")


def approval_rule(company):
	"""The company's rule for a submit by the card's own preparer: Refuse, or Warn only (default)."""
	return RULE_REFUSE if company_setting(company, RULE_FIELD) == RULE_REFUSE else RULE_WARN


def _lines(value):
	return [u for u in (value or "").split("\n") if u]


def _stored(doc, fields):
	"""A locking read of the stored card: the latest committed values, not the request's snapshot."""
	return frappe.db.get_value(DOCTYPE, doc.name, list(fields), as_dict=True, for_update=True)


def card_preparers(doc):
	"""Users who prepared the card: its creator and every editor, for the card and every card of its amendment
	chain. The values of ``doc`` itself are the server's (``on_validate`` set them from the database)."""
	users = {doc.get("owner"), *_lines(doc.get("edited_by"))}
	seen = {doc.name}
	pending = [doc.get("amended_from"), getattr(doc.flags, "card_stored_amended_from", None)]
	while pending:
		name = pending.pop()
		if not name or name in seen:
			continue
		seen.add(name)
		row = frappe.db.get_value(DOCTYPE, name, ["owner", "edited_by", "amended_from"], as_dict=True)
		if not row:
			continue
		users.add(row.owner)
		users.update(_lines(row.edited_by))
		pending.append(row.amended_from)
	return {u for u in users if u}


# ---------- doc_events (card/hooks.py) ----------
def on_validate(doc, method=None):
	"""validate (draft save and submit, insert with docstatus 1 included): the approval fields stay empty, the
	creator and the editors are taken from the database and the current user is recorded as an editor."""
	for field in APPROVAL_FIELDS:
		doc.set(field, None)
	doc.self_approved = 0
	stored = None if doc.is_new() else _stored(doc, ("owner", "edited_by", "modified_by", "amended_from"))
	editors = []
	if stored:
		# the creator is the stored one (Frappe writes a sent ``owner`` on an update)
		doc.owner = stored.owner
		doc.flags.card_stored_amended_from = stored.amended_from
		# a card saved before FR-143: its last draft editor
		editors = _lines(stored.edited_by) or _lines(stored.modified_by)
	user = frappe.session.user
	if user not in editors and (doc.docstatus == 0 or doc.is_new() or _inputs_changed(doc)):
		editors.append(user)
	doc.edited_by = "\n".join(editors)


def _editable(df):
	return not (
		df.read_only
		or df.get("fetch_from")
		or df.fieldtype in no_value_fields
		or df.fieldname in SERVER_FIELDS
		or df.fieldname == "amended_from"
	)


def _inputs_changed(doc):
	"""True when a submit request changes an editable field or row of the stored draft (computed and read-only
	values are left out: the card recomputes them on every save)."""
	before = doc.get_doc_before_save()
	if not before:
		return True
	for df in doc.meta.fields:
		if df.fieldtype in table_fields:
			if df.read_only:
				continue
			if _rows_changed(df, doc.get(df.fieldname) or [], before.get(df.fieldname) or []):
				return True
		elif _editable(df) and _differs(df, doc.get(df.fieldname), before.get(df.fieldname)):
			return True
	return False


def _rows_changed(table_df, rows, stored_rows):
	if [r.name for r in rows] != [r.name for r in stored_rows]:
		return True
	fields = [df for df in frappe.get_meta(table_df.options).fields if _editable(df)]
	for row, old in zip(rows, stored_rows, strict=True):
		if any(_differs(df, row.get(df.fieldname), old.get(df.fieldname)) for df in fields):
			return True
	return False


def before_submit(doc, method=None):
	"""The submit is the card's approval: a preparer approves only under the company's Warn rule."""
	user = frappe.session.user
	self_approved = user in card_preparers(doc)
	if self_approved:
		if approval_rule(doc.company) == RULE_REFUSE:
			frappe.throw(
				_(
					"You created or edited this monthly card; another user must submit (approve) it (company rule: Refuse)."
				),
				frappe.PermissionError,
				title=_("Monthly card self-approval"),
			)
		frappe.msgprint(
			_(
				"You created or edited this monthly card and submit (approve) it yourself; it is marked for review (company rule: Warn)."
			),
			title=_("Monthly card self-approval"),
			indicator="orange",
		)
	doc.update(
		{
			"submitted_by": user,
			"approved_by": user,
			"approved_on": now_datetime(),
			"self_approved": 1 if self_approved else 0,
		}
	)


def _restore(doc):
	stored = _stored(doc, SERVER_FIELDS)
	if stored:
		for field in SERVER_FIELDS:
			doc.set(field, stored.get(field))


def before_update_after_submit(doc, method=None):
	"""An update after submit (form, REST PUT, ``frappe.client.set_value``, bulk update) keeps the stored
	approval and editors; a value sent by the client is dropped."""
	_restore(doc)


def before_cancel(doc, method=None):
	"""A cancel (form, REST PUT with docstatus 2, savedocs, bulk cancel) keeps the stored approval and editors.
	FR-123 (``card.cancel_reason.before_cancel``, which runs first) already refuses a cancel request that changes
	a stored field; this read is the second layer."""
	_restore(doc)
