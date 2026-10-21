# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Server-side period lock for CARD transactions (Card Monthly Card, Project
Diesel Fill, Equipment Transport). Enforced on save/submit/amend/import
(validate), cancel and delete (trash). A save or submit is judged by both the stored
date and the new date, so a document cannot be moved out of (or into) the locked
period; a cancel is judged by the stored date and may not change it. A configurable
override role may bypass the lock; every override is logged (and optionally notified).
No lock date = no lock check; a cancel request still may not change a period-lock date field."""

import json

import frappe
from frappe import _
from frappe.utils import getdate

from card.notifications import notify
from card.settings import setting

_DATE_FIELDS = ("to_date", "date", "posting_date")


class PeriodLockDateChangeError(frappe.ValidationError):
	pass


def _doc_date(doc):
	# a request can carry keys that are not fields (Frappe keeps them as attributes); read real fields only
	for f in _DATE_FIELDS:
		if not doc.meta.has_field(f):
			continue
		v = doc.get(f)
		if v:
			return getdate(v)
	return None


def enforce(doc, action, stored=None):
	"""Refuse when the document's date, or the date stored before this request, is in the locked period."""
	lock = setting("period_lock_date")
	if not lock:
		return
	dates = [d for d in (_doc_date(doc), _doc_date(stored) if stored else None) if d]
	d = min(dates, default=None)
	if not d or d > getdate(lock):
		return
	override_role = setting("period_lock_override_role")
	if override_role and override_role in frappe.get_roles():
		_log_override(doc, action, lock, override_role, d)
		return
	frappe.throw(
		_("Period is locked up to {0}; {1} of a {2} dated on or before that date is not allowed.").format(
			getdate(lock), _(action), _(doc.doctype)
		)
	)


def _log_override(doc, action, lock, override_role, doc_date):
	payload = {
		"user": frappe.session.user,
		"action": action,
		"doctype": doc.doctype,
		"name": doc.get("name"),
		"doc_date": str(doc_date),
		"lock_date": str(getdate(lock)),
	}
	frappe.logger("card.period_lock_override").warning(json.dumps(payload, ensure_ascii=False))
	recipients = frappe.get_all(
		"Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent"
	)
	notify(
		"notify_on_period_lock_override",
		recipients,
		_("CARD period lock override"),
		json.dumps(payload, ensure_ascii=False),
		doc if doc.get("name") else None,
	)


# doc_events hook entry points (registered in hooks.py for the three doctypes)
def on_validate(doc, method=None):
	# Frappe loads the stored copy (for_update) before validate; None for a new document
	enforce(doc, "save", doc.get_doc_before_save())


def on_cancel(doc, method=None):
	# Frappe skips validate on cancel and stores the request's values before on_cancel, so judge the
	# stored date and refuse a cancel request that changes it (the refusal rolls the request back)
	stored = doc.get_doc_before_save()
	if stored:
		_refuse_date_change(doc, stored)
	enforce(stored or doc, "cancel")


def _refuse_date_change(doc, stored):
	for f in _DATE_FIELDS:
		if doc.meta.has_field(f) and _as_date(doc.get(f)) != _as_date(stored.get(f)):
			frappe.throw(
				_("{0} of a {1} cannot be changed when it is cancelled.").format(
					_(doc.meta.get_label(f)), _(doc.doctype)
				),
				PeriodLockDateChangeError,
			)


def _as_date(v):
	return getdate(v) if v else None


def on_trash(doc, method=None):
	enforce(doc, "delete")
