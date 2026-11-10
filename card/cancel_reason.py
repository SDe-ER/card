# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-123 (WP-07, issues #35 and #51, governance G0): a CARD transaction (Card Monthly Card,
Equipment Transport, Project Diesel Fill) is cancelled only with a reason, and a cancel changes
nothing else on the document.

- ``cancel_reason`` (Small Text, no copy, read only; not allow on submit, since a cancel stores it
  without Frappe's update-after-submit check) is written only by the cancel
  itself: ``cancel_with_reason`` (the form's Cancel dialog) stores the reason and cancels in one
  request; a REST/API cancel that sends ``docstatus`` 2 may send ``cancel_reason`` with it. A save,
  submit or update after submit never sets it (a copied reason is dropped on save; an update after
  submit that changes it is refused).
- ``before_cancel`` refuses a cancel without a reason and a cancel request that changes any other
  stored field or row (Frappe skips validate on cancel and stores the values a request sends,
  frappe/model/document.py ``_save``; FR-050 open gap "card cancel may rewrite fields").
- ``on_cancel`` records a Comment with the actor, the reason and the date.

Documents cancelled before this change keep an empty reason; nothing is rewritten."""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.model.workflow import get_workflow_name
from frappe.utils import (
	cint,
	cstr,
	escape_html,
	flt,
	get_datetime,
	getdate,
	now_datetime,
	strip_html_tags,
	to_timedelta,
)

FIELD = "cancel_reason"
DOCTYPES = ("Card Monthly Card", "Equipment Transport", "Project Diesel Fill")


class CancelReasonRequiredError(frappe.ValidationError):
	pass


class CancelChangesDocumentError(frappe.ValidationError):
	pass


def _reason(doc):
	# Frappe skips _validate (and so _sanitize_content) on cancel, so the reason is cleaned here: it is
	# plain text: every HTML tag is removed, then any "<" or ">" left (an unclosed tag) is dropped
	# (Report View shows Small Text unescaped)
	return strip_html_tags(cstr(doc.get(FIELD))).replace("<", "").replace(">", "").strip()


@frappe.whitelist(methods=["POST"])
def cancel_with_reason(doctype: str, name: str, reason: str | None = None):
	"""The form's Cancel: store the reason and cancel the stored document in one request (a refused
	cancel rolls the reason back with it). Frappe's own cancel permission and the doctype's
	has_permission hook (company isolation) decide who may cancel."""
	if doctype not in DOCTYPES:
		frappe.throw(_("{0} is not a CARD transaction.").format(doctype), frappe.PermissionError)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("cancel")
	doc.set(FIELD, cstr(reason).strip())
	doc.cancel()
	return {"name": doc.name, "docstatus": doc.docstatus}


# doc_events hook entry points (hooks.py, the three doctypes)
def on_validate(doc, method=None):
	# save and submit: a draft or a newly submitted document never carries a cancel reason
	# (Python copy_doc copies no_copy fields; Desk's amend never copies cancel_reason)
	if doc.get(FIELD):
		doc.set(FIELD, None)


def before_update_after_submit(doc, method=None):
	before = doc.get_doc_before_save()
	if before and cstr(doc.get(FIELD)) != cstr(before.get(FIELD)):
		frappe.throw(
			_("The cancel reason is recorded only when the document is cancelled."),
			CancelChangesDocumentError,
		)


def before_cancel(doc, method=None):
	"""Runs before Frappe stores the cancel, so a refusal keeps the document submitted."""
	stored = doc.get_latest()
	if stored:
		_refuse_changes(doc, stored)
	if not _reason(doc):
		frappe.throw(
			_("A cancel reason is required to cancel {0} {1}.").format(_(doc.doctype), doc.name),
			CancelReasonRequiredError,
		)
	doc.set(FIELD, _reason(doc))


def on_cancel(doc, method=None):
	doc.add_comment(
		"Info",
		_("Cancelled by {0} on {1}. Reason: {2}").format(
			escape_html(frappe.session.user),
			cstr(now_datetime().replace(microsecond=0)),
			escape_html(_reason(doc)),
		),
	)


# ---- a cancel changes nothing but the reason ----
def _skipped(doc):
	skip = {FIELD}
	workflow = get_workflow_name(doc.doctype)
	if workflow:
		# a workflow's cancel action sets its own state field (Workflow is not changed here)
		skip.add(frappe.get_cached_value("Workflow", workflow, "workflow_state_field"))
	return skip


def _norm(df, v):
	ft = df.fieldtype
	# a number column stores an empty value as 0, so an unset number in memory is not a change
	if ft in ("Int", "Check"):
		return cint(v)
	if ft in ("Float", "Currency", "Percent", "Rating"):
		return flt(v, 6)
	if v in (None, ""):
		return ""
	if ft == "Date":
		return str(getdate(v))
	if ft == "Datetime":
		return str(get_datetime(v))
	if ft == "Time":
		return str(to_timedelta(v))
	return cstr(v)


def _differs(df, new, old):
	# no default tolerance: Frappe fills defaults on a save only for a new document or a new child
	# row (Document._set_defaults), and a cancel refuses new rows, so any other difference is the request's
	return _norm(df, new) != _norm(df, old)


def _changed_field(doc, stored, skip):
	for df in doc.meta.fields:
		if df.fieldname in skip:
			continue
		# frappe.model.no_value_fields includes the table fields, so the rows are compared first
		if df.fieldtype in table_fields:
			if _rows_changed(df, doc.get(df.fieldname) or [], stored.get(df.fieldname) or []):
				return df
			continue
		if df.fieldtype in no_value_fields:
			continue
		if _differs(df, doc.get(df.fieldname), stored.get(df.fieldname)):
			return df
	return None


def _rows_changed(table_df, rows, stored_rows):
	if [cstr(r.name) for r in rows] != [cstr(r.name) for r in stored_rows]:
		return True
	child_meta = frappe.get_meta(table_df.options)
	for row, old in zip(rows, stored_rows, strict=True):
		for df in child_meta.fields:
			if df.fieldtype in no_value_fields:
				continue
			if _differs(df, row.get(df.fieldname), old.get(df.fieldname)):
				return True
	return False


def _refuse_changes(doc, stored):
	df = _changed_field(doc, stored, _skipped(doc))
	if df:
		frappe.throw(
			_("{0} {1} is cancelled as approved; {2} cannot be changed when cancelling.").format(
				_(doc.doctype), doc.name, _(df.label or df.fieldname)
			),
			CancelChangesDocumentError,
		)
