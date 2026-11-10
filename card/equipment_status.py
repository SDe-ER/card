# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-122 (#42, #120): an ended Card Equipment gets no NEW assignment, transport or monthly card.

The rule is per company (Card Company Settings `equipment_status_rule`): "Warn only" (the default,
also when the company has no row or the value is empty) shows a message and saves; "Refuse" stops it.
Only new records, or a record whose equipment changes, are checked, and a transport again on
submit; existing records are never changed. Exempt: a transport to the supplier, a move of an
owned machine to storage or a workshop (how it is retired), and a monthly card whose period starts
on or before the equipment's exit date (else its rental end, once passed)."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from card.constants import EQUIPMENT_STATUS_ENDED, STATUS_RULE_ENFORCE, STATUS_RULE_WARN
from card.settings import company_setting

# Card Equipment.status values that stop new use. "متوقفة" (Stopped) and "في الصيانة"
# (Under Maintenance) are temporary and still allowed: a stopped or repaired machine moves again.
BLOCKED_STATUSES = (EQUIPMENT_STATUS_ENDED,)


def status_rule(company):
	"""Refuse or Warn only for the company; anything but Refuse warns."""
	return company_setting(company, "equipment_status_rule") or STATUS_RULE_WARN


def _messages():
	# whole CARD sentences (no generic msgid such as "transport" in card/locale)
	return {
		"assignment": _("Equipment {0} has status {1}; it should get no new assignment."),
		"transport": _("Equipment {0} has status {1}; it should get no new transport."),
		"monthly card": _("Equipment {0} has status {1}; it should get no new monthly card."),
	}


def _last_work_day(eq):
	"""The exit date when set; else the rental end, only once it has passed (a contract end years
	ahead is no exit); else None (no final-month allowance)."""
	if eq.exit_date:
		return getdate(eq.exit_date)
	if eq.rental_end_date and getdate(eq.rental_end_date) <= getdate(nowdate()):
		return getdate(eq.rental_end_date)
	return None


def check_equipment_status(equipment, use, company=None, period_start=None):
	"""Warn or refuse a new `use` ("assignment", "transport" or "monthly card") of an equipment
	whose status stops new use. The equipment's own company decides the rule when no company is
	given. With `period_start` (a monthly card), a period that starts on or before the equipment's
	exit date (else its rental end, once passed) is its last work, not a new use: never stopped."""
	if not equipment:
		return
	eq = frappe.db.get_value(
		"Card Equipment", equipment, ["status", "company", "exit_date", "rental_end_date"], as_dict=True
	)
	if not eq or eq.status not in BLOCKED_STATUSES:
		return
	if period_start and (end := _last_work_day(eq)) and getdate(period_start) <= end:
		return
	company = company or eq.company
	message = _messages()[use].format(equipment, _(eq.status))
	if status_rule(company) == STATUS_RULE_ENFORCE:
		frappe.throw(
			message + " " + _("The equipment status rule of company {0} refuses it.").format(company)
		)
	frappe.msgprint(message, indicator="orange", alert=False)


def equipment_is_new_on(doc, fieldname="equipment"):
	"""True when the document is new or its equipment differs from the stored one (read from the
	database, so a re-validation of an existing record is never taken for a new use)."""
	if doc.is_new():
		return True
	return frappe.db.get_value(doc.doctype, doc.name, fieldname) != doc.get(fieldname)
