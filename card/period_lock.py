# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Server-side period lock for CARD transactions (Card Monthly Card, Project
Diesel Fill, Equipment Transport). Enforced on save/submit/amend/import
(validate), cancel and delete (trash). A configurable override role may bypass
the lock; every override is logged (and optionally notified). No lock date =
no-op, so behaviour is unchanged by default."""

import json

import frappe
from frappe import _
from frappe.utils import getdate

from card.notifications import notify
from card.settings import setting

_DATE_FIELDS = ("to_date", "date", "posting_date")


def _doc_date(doc):
	for f in _DATE_FIELDS:
		v = doc.get(f)
		if v:
			return getdate(v)
	return None


def enforce(doc, action):
	lock = setting("period_lock_date")
	if not lock:
		return
	d = _doc_date(doc)
	if not d or d > getdate(lock):
		return
	override_role = setting("period_lock_override_role")
	if override_role and override_role in frappe.get_roles():
		_log_override(doc, action, lock, override_role)
		return
	frappe.throw(
		_("Period is locked up to {0}; {1} of a {2} dated on or before that date is not allowed.").format(
			getdate(lock), _(action), _(doc.doctype)
		)
	)


def _log_override(doc, action, lock, override_role):
	payload = {
		"user": frappe.session.user,
		"action": action,
		"doctype": doc.doctype,
		"name": doc.get("name"),
		"doc_date": str(_doc_date(doc)),
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
	enforce(doc, "save")


def on_cancel(doc, method=None):
	enforce(doc, "cancel")


def on_trash(doc, method=None):
	enforce(doc, "delete")
