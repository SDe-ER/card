# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-191: a monthly operation card is approved only after the end of its own month.

Saving records the month's operation as it happens (draft, or a submitted card in the state "Open – month not
ended"); the approval is the month's final closing. The first permitted approval day is the first day of the month
after the card's month (December -> 1 January of the next year). The business "today" is the current UTC time
converted to Asia/Riyadh with ``zoneinfo``; the site's System Settings time zone is not read. Only the card's
``month`` and ``year`` fields count, never its creation or modified date. The end of a month never approves a card
by itself: the approval stays a manual action.

The check runs on every approval route (``check_card_approval_allowed``): the card's ``before_submit`` hook (form
Submit, ``frappe.client.submit``, REST insert/update with docstatus 1, bulk submit, ``apply_workflow``), and the
final approval of an open-month card (``card.open_month``). No role is exempt, Administrator included, and no flag
skips it."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import cint

BUSINESS_TZ = ZoneInfo("Asia/Riyadh")


class ApprovalBeforeMonthEndError(frappe.ValidationError):
	pass


def riyadh_today(now_utc: datetime | None = None) -> date:
	"""The business date in Riyadh. ``now_utc`` is for tests; a naive value is read as UTC."""
	now = now_utc or datetime.now(UTC)
	if now.tzinfo is None:
		now = now.replace(tzinfo=UTC)
	return now.astimezone(BUSINESS_TZ).date()


def earliest_approval_date(year, month) -> date:
	"""The first day of the month after (year, month)."""
	y, m = cint(year), cint(month)
	if not y or not 1 <= m <= 12:
		frappe.throw(_("Month and year are required"))
	return date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)


def month_ended(year, month, today: date | None = None) -> bool:
	return (today or riyadh_today()) >= earliest_approval_date(year, month)


def approval_refused_message(year, month) -> str:
	return (
		_(
			"Equipment operation cards cannot be approved before the end of their accounting month. You may continue recording operations and payments and saving the card until the month ends."
		)
		+ " "
		+ _("Earliest permitted approval date: {0}").format(
			frappe.utils.formatdate(earliest_approval_date(year, month))
		)
	)


def check_card_approval_allowed(doc, today: date | None = None):
	"""Refuse an approval of ``doc`` (a Card Monthly Card) before its month has ended in Riyadh."""
	if not month_ended(doc.year, doc.month, today):
		frappe.throw(
			approval_refused_message(doc.year, doc.month),
			ApprovalBeforeMonthEndError,
			title=_("Approval before month end"),
		)


def before_submit(doc, method=None):
	"""doc_events ``before_submit`` of Card Monthly Card (first in the list): every submit is an approval."""
	check_card_approval_allowed(doc)


def eligibility(year, month, today: date | None = None) -> dict:
	today = today or riyadh_today()
	earliest = earliest_approval_date(year, month)
	return {
		"eligible": today >= earliest,
		"earliest_approval_date": str(earliest),
		"today_riyadh": str(today),
		"message": "" if today >= earliest else approval_refused_message(year, month),
	}


@frappe.whitelist(methods=["GET"])
def get_approval_eligibility(name: str):
	"""Read-only: whether the card may be approved now and its earliest approval date (the form shows this; the
	rule itself is always enforced on the server)."""
	doc = frappe.get_doc("Card Monthly Card", name)
	doc.check_permission("read")
	from card.open_month import STATE_OPEN_MONTH

	out = eligibility(doc.year, doc.month)
	out["open_month_state"] = doc.get("workflow_state") == STATE_OPEN_MONTH
	return out
