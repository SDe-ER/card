# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-142 (#44, #123, FR-022): the Card Daily Log rules.

A daily log records, for one company, project and date, the day and night hours, the stopped hours and the stop
reason of each equipment. The operator or the site supervisor enters it and submits it; a Card Manager then
approves it or returns it with a reason. Generating monthly cards from approved logs is a later package (K2).

The rows follow the rules of the monthly card day rows, through the same functions:

- the shift limits only warn (owner 2026-10-14: every recorded hour counts, a day over the limit is reviewed);
- the equipment must be assigned to the project on the log date (``card.transfer.validate_card_days``);
- the equipment status rule of the company (``card.equipment_status.check_equipment_status``);
- a stop reason must be an enabled reason of the log's company (``card.adjustments.validate_downtime_fields``);
- every row's equipment belongs to the log's company (``card.company_scope.check_child_companies``).

Approval (FR-121 style separation of duties): the approval fields are written by the server only. A change of
``approval_status`` on a submitted log, through any route (form, REST, ``frappe.client.set_value``, bulk update),
is checked in ``before_update_after_submit``; a cancel, through any route, reads the stored approval in
``before_cancel``. Only Card Manager or System Manager approves; a return needs a reason; an approved or returned
log is final (cancel and amend). A user who created, edited or submitted the log, or any log it amends, is its
preparer; when a preparer approves, the company's ``self_approval_rule`` (Card Daily Log Settings) decides:
"Warn only" (the default, also with no settings record) approves with a warning and marks the log
``self_approved``; "Refuse" refuses. No role is exempt.

Supervisor step (opt-in per company, ``require_supervisor_verification``, default off = the two-step flow above):
a submitted log is first "Verified by supervisor" by a Card Supervisor who is not its preparer, and only then
approved by a manager; the verifier counts as a preparer for the approval. A Card Supervisor may also return a
Pending log in that mode.

Loads (FR-188, opt-in per company: Card Company Settings ``daily_log_loads``, default off = no row may get
loads, the behaviour before FR-188): a row may record the day shift loads and the night shift loads of equipment
billed to its customer per m³ (FR-166), on a day that is not in the future. A day with loads is checked against
the assignments like a day with hours. The loads reach the monthly card through the generation only.

A load field that a save does not send is kept (``keep_unsent_loads``): a client that does not know the two
fields (CARD Mobile) sends rows without them, and Frappe would store 0. An unsent field is ``None`` on the row
when ``validate`` runs (``frappe.model.document.Document.init_valid_columns`` sets every column that is not in the
data to ``None``; the numeric cast to 0 runs after ``validate``), a sent 0 is 0. An unsent field of a stored row
(matched by its row name inside this log) takes the stored value; on a new log that amends another one (the
corrected draft) it takes the value of the amended log's row of the same equipment. Only loads that are new or
changed are checked against the switch and the per-m³ rule, so a log that holds loads is still saved after the
switch was turned off."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

from card.adjustments import validate_downtime_fields
from card.cancel_reason import _refuse_changes as refuse_cancel_changes
from card.card_value import PER_VOLUME_M3
from card.company_scope import check_child_companies
from card.equipment_status import check_equipment_status
from card.settings import company_setting, setting
from card.transfer import validate_card_days

DOCTYPE = "Card Daily Log"
ROW_DOCTYPE = "Card Daily Log Row"
SETTINGS_DOCTYPE = "Card Daily Log Settings"

PENDING = "Pending"
VERIFIED = "Verified by supervisor"
APPROVED = "Approved"
RETURNED = "Returned for correction"
STATUSES = (PENDING, VERIFIED, APPROVED, RETURNED)

RULE_WARN = "Warn only (daily log)"
RULE_REFUSE = "Refuse (daily log)"

# FR-188: the per-company switch (Card Company Settings) and the two load fields of a daily log row
LOADS_SETTING = "daily_log_loads"
LOAD_FIELDS = ("day_loads", "night_loads")

APPROVER_ROLES = ("Card Manager", "System Manager")
SUPERVISOR_ROLE = "Card Supervisor"

# written by the server only; a client value is never kept
APPROVAL_FIELDS = (
	"approved_by",
	"approved_on",
	"self_approved",
	"return_reason",
	"returned_by",
	"returned_on",
	"verified_by",
	"verified_on",
)
# restored from the database on cancel as well (a cancel may carry a forged document)
SERVER_FIELDS = ("approval_status", *APPROVAL_FIELDS, "submitted_by", "edited_by")


def _has_any_role(roles, user=None):
	return bool(set(roles) & set(frappe.get_roles(user or frappe.session.user)))


def _company_rules(company):
	row = company and frappe.db.get_value(
		SETTINGS_DOCTYPE,
		{"company": company},
		["self_approval_rule", "require_supervisor_verification"],
		as_dict=True,
	)
	return row or frappe._dict()


def self_approval_rule(company):
	"""The company's rule for an approval by the log's own preparer: Refuse, or Warn only (default)."""
	return RULE_REFUSE if _company_rules(company).get("self_approval_rule") == RULE_REFUSE else RULE_WARN


def requires_supervisor_verification(company):
	"""True when the company asks a supervisor to verify a log before a manager approves it (default off)."""
	return bool(cint(_company_rules(company).get("require_supervisor_verification")))


def loads_enabled(company):
	"""True only when the company's Card Company Settings row sets ``daily_log_loads`` (FR-188); no company, no
	row or 0: daily logs carry no loads, as before."""
	return cint(company_setting(company, LOADS_SETTING)) == 1


def _add_preparers(users, row):
	users.update({row.get("owner"), row.get("submitted_by"), row.get("verified_by")})
	users.update((row.get("edited_by") or "").split("\n"))


def log_preparers(doc):
	"""Users who prepared the log, all written by the server: its creator, its submitter and every user who saved
	it as a draft, and the supervisor who verified it, for the log and every log of its amendment chain (an
	amendment never clears a preparer or an earlier verifier). A saved log is read from the database."""
	users = set()
	_add_preparers(users, doc)
	seen = set()
	name = doc.name if not doc.is_new() else doc.get("amended_from")
	while name and name not in seen:
		seen.add(name)
		row = frappe.db.get_value(
			DOCTYPE, name, ["owner", "submitted_by", "edited_by", "verified_by", "amended_from"], as_dict=True
		)
		if not row:
			break
		_add_preparers(users, row)
		name = row.amended_from
	return {u for u in users if u}


# ---------- draft and submit ----------
def prepare(doc):
	"""validate (draft save and submit, REST insert with docstatus 1 included): the approval stays Pending and
	the approval fields empty; the stored submitter and the stored ``amended_from`` are kept and the current user
	is recorded as an editor."""
	doc.approval_status = PENDING
	for field in APPROVAL_FIELDS:
		doc.set(field, None)
	doc.self_approved = 0
	stored = (
		None
		if doc.is_new()
		else frappe.db.get_value(DOCTYPE, doc.name, ["submitted_by", "edited_by", "amended_from"])
	)
	doc.submitted_by = stored[0] if stored else None
	if stored:
		# Frappe checks amended_from on insert only: a save may not clear or change it, so the amendment chain
		# (and its preparers) stays the one the log was created with
		doc.amended_from = stored[2]
	editors = [e for e in ((stored[1] if stored else "") or "").split("\n") if e]
	if frappe.session.user not in editors:
		editors.append(frappe.session.user)
	doc.edited_by = "\n".join(editors)


def validate_log(doc):
	"""The header and row rules of a daily log (see the module docstring)."""
	project_company = frappe.db.get_value("Project", doc.project, "company")
	if project_company != doc.company:
		frappe.throw(
			_("Project {0} belongs to company {1}; the daily log is for company {2}.").format(
				doc.project, project_company, doc.company
			),
			frappe.ValidationError,
		)
	_check_amended_from(doc)
	if not doc.get("rows"):
		frappe.throw(_("Add at least one equipment row to the daily log."))
	check_child_companies(doc, "rows", "equipment")
	log_date = getdate(doc.log_date)
	future = log_date > getdate(nowdate())
	stored_equipment = _stored_equipment(doc)
	seen = set()
	over_limit = []
	# #50: no hard-coded 12; a missing or zero limit is not configured and nothing is checked against it
	max_day = flt(setting("max_day_shift_hours"))
	max_night = flt(setting("max_night_shift_hours"))
	loads_on = loads_enabled(doc.company)
	load_baselines = keep_unsent_loads(doc)
	for row, load_baseline in zip(doc.rows, load_baselines, strict=True):
		if row.equipment in seen:
			frappe.throw(
				_("Equipment {0} is listed twice in the daily log (row {1}).").format(row.equipment, row.idx)
			)
		seen.add(row.equipment)
		day, night, stopped = flt(row.day_hours), flt(row.night_hours), flt(row.stopped_hours)
		if day < 0 or night < 0 or stopped < 0:
			frappe.throw(_("Row {0}: hours cannot be negative.").format(row.idx))
		if future and (day or night or stopped):
			frappe.throw(_("Cannot record hours for a future day: {0}").format(doc.log_date))
		if day + night + stopped > 24:
			frappe.throw(
				_("Row {0} ({1}): day, night and stopped hours together ({2}) exceed 24 hours.").format(
					row.idx, row.equipment, day + night + stopped
				)
			)
		# advisory only (owner 2026-10-14): every recorded hour counts; a row over the limit is reviewed
		if max_day > 0 and day > max_day:
			over_limit.append(f"{row.equipment} ({_('Day shift hours')}: {day})")
		if max_night > 0 and night > max_night:
			over_limit.append(f"{row.equipment} ({_('Night shift hours')}: {night})")
		_check_loads(row, doc, loads_on, future, load_baseline)
		_check_stop_reason(row, doc.company)
		_responsible_party(row, doc.company, log_date)
		if row.equipment not in stored_equipment:
			# FR-122: same rule as a monthly card (a daily log becomes monthly card days)
			check_equipment_status(row.equipment, "monthly card", doc.company, period_start=log_date)
		_check_assignment(doc, row, log_date)
	if over_limit:
		frappe.msgprint(
			_(
				"Rows over the shift limit (day {0} h, night {1} h); the hours are recorded, review them: {2}"
			).format(max_day, max_night, _(", ", context="Card").join(over_limit)),
			title=_("Shift hours exceeded warning"),
			indicator="orange",
		)
	_check_duplicates(doc)


def _load_baselines(doc):
	"""The stored loads each row of ``doc`` starts from, one ``(day_loads, night_loads)`` per row in row order:
	the stored row of this log with the same row name; on a new log that amends another one, the amended log's row
	of the same equipment (a log lists an equipment once); otherwise no loads. A row name of another log matches
	nothing."""
	if doc.is_new():
		parent, key = doc.get("amended_from"), "equipment"
	else:
		parent, key = doc.name, "name"
	stored = {}
	if parent:
		stored = {
			r.get(key): tuple(cint(r.get(field)) for field in LOAD_FIELDS)
			for r in frappe.get_all(
				ROW_DOCTYPE,
				filters={"parent": parent, "parenttype": DOCTYPE},
				fields=["name", "equipment", *LOAD_FIELDS],
			)
		}
	return [stored.get(row.get(key), (0, 0)) for row in doc.rows]


def keep_unsent_loads(doc):
	"""FR-188: a load field the save did not send (``None`` on the row, module docstring) takes its stored value,
	so a client that does not know the load fields cannot erase them; a sent value, 0 included, is kept as sent.
	Returns the stored loads of each row (``_load_baselines``)."""
	baselines = _load_baselines(doc)
	for row, baseline in zip(doc.rows, baselines, strict=True):
		for field, stored in zip(LOAD_FIELDS, baseline, strict=True):
			if row.get(field) is None:
				row.set(field, stored)
	return baselines


def _check_loads(row, doc, loads_on, future, baseline=(0, 0)):
	"""FR-188: the loads of a row follow the monthly card's rules for ``loads_count`` (FR-166): never negative,
	never on a future day, only on equipment billed to its customer per m³. With the company's switch off a row
	gets no loads. The switch and the per-m³ rule are checked only for loads that are new or changed against the
	stored ``baseline``: a row that keeps its loads, or clears them, is saved also after the switch was turned
	off."""
	loads = tuple(cint(row.get(field)) for field in LOAD_FIELDS)
	if min(loads) < 0:
		frappe.throw(_("Row {0}: loads cannot be negative.").format(row.idx))
	if not any(loads):
		return
	if future:
		frappe.throw(_("Cannot record loads for a future day: {0}").format(doc.log_date))
	if not any(value and value != stored for value, stored in zip(loads, baseline, strict=True)):
		return
	if not loads_on:
		frappe.throw(
			_(
				"Row {0}: loads on daily logs are not enabled for company {1}. Enter the loads on the monthly card, or enable Loads on daily logs for the company in Card Settings."
			).format(row.idx, doc.company)
		)
	if frappe.db.get_value("Card Equipment", row.equipment, "customer_rate_type") != PER_VOLUME_M3:
		frappe.throw(
			_(
				"Row {0} ({1}): loads can be recorded only for equipment whose customer rate type is per m³."
			).format(row.idx, row.equipment)
		)


def _stored_equipment(doc):
	if doc.is_new():
		return set()
	return set(
		frappe.get_all(ROW_DOCTYPE, filters={"parent": doc.name, "parenttype": DOCTYPE}, pluck="equipment")
	)


def _check_amended_from(doc):
	"""An amendment copies its original's attachments (Frappe), so the original must be a log of the same company
	that the user may read."""
	original = doc.get("amended_from")
	if not original:
		return
	if frappe.db.get_value(DOCTYPE, original, "company") != doc.company or not frappe.has_permission(
		DOCTYPE, "read", original
	):
		frappe.throw(
			_("A daily log can only amend a cancelled daily log of the same company."), frappe.PermissionError
		)


def _check_stop_reason(row, company):
	"""The monthly card rule for a stop reason: it exists, belongs to the log's company and is enabled."""
	if not row.stop_reason:
		return
	probe = frappe._dict(stop_reason=row.stop_reason, description=row.equipment)
	reason = validate_downtime_fields(probe, company, False)
	if not cint(reason.enabled):
		frappe.throw(_("Stop reason {0} is disabled; choose an enabled reason.").format(row.stop_reason))


def _responsible_party(row, company, log_date):
	"""The monthly card day-row rule (FR-118): an empty party type takes the stop reason's default; a Company party
	is the log's company (empty means the log's company); Other keeps a free-text name only; Supplier and Customer
	keep their record. Through the card's own function, not a copy."""
	from card.card.doctype.card_monthly_card.card_monthly_card import CardMonthlyCard

	if not row.responsible_party_type and row.stop_reason:
		row.responsible_party_type = frappe.db.get_value(
			"Card Stop Reason", row.stop_reason, "default_responsible_party_type"
		)
	# the card's message names the row by its day: a daily log row's day is the log's date (not stored)
	row.operation_date = log_date
	CardMonthlyCard._normalise_responsible_party(row, company)


def _check_assignment(doc, row, log_date):
	"""The monthly card rule: a day with hours (working or stopped) or with loads (FR-188) falls inside an
	assignment period of the equipment (every component for a unit) on the log's project. Equipment without any
	assignment history is not checked, as on a monthly card."""
	hours = flt(row.day_hours) + flt(row.night_hours) + flt(row.stopped_hours)
	loads = sum(cint(row.get(field)) for field in LOAD_FIELDS)
	if hours <= 0 and loads <= 0:
		return
	day = frappe._dict(
		operation_date=log_date, working_hours=hours, loads_count=loads, stopped_hours=0, reason_billable=0
	)
	validate_card_days(frappe._dict(equipment=row.equipment, project=doc.project, days=[day]))


def _check_duplicates(doc):
	"""One daily log per equipment, project and date (cancelled logs excepted). The equipment rows are locked
	first, then the other logs are read with a locking read (the latest committed rows, not the request's
	REPEATABLE READ snapshot), so two logs saved at the same time for the same equipment cannot both pass."""
	equipment = sorted({row.equipment for row in doc.rows})
	for name in equipment:
		frappe.db.get_value("Card Equipment", name, "name", for_update=True)
	row, log = frappe.qb.DocType(ROW_DOCTYPE), frappe.qb.DocType(DOCTYPE)
	listed = (
		frappe.qb.from_(row)
		.join(log)
		.on(log.name == row.parent)
		.select(row.equipment, row.parent)
		.where(row.parenttype == DOCTYPE)
		.where(row.equipment.isin(equipment))
		.where(log.name != (doc.name or ""))
		.where(log.project == doc.project)
		.where(log.log_date == doc.log_date)
		.where(log.docstatus != 2)
		.for_update()
	).run(as_dict=True)
	clashes = sorted({f"{r.equipment} ({r.parent})" for r in listed})
	if clashes:
		frappe.throw(
			_("A daily log for this project and date already lists these equipment: {0}").format(
				_(", ", context="Card").join(clashes)
			),
			frappe.DuplicateEntryError,
		)


def record_submitter(doc):
	"""before_submit: the submitter never approves under the Refuse rule (FR-121 style)."""
	doc.submitted_by = frappe.session.user


# ---------- approval (after submit) ----------
def check_transition(doc):
	"""before_update_after_submit: the only change allowed on a submitted log is the approval, by the server's
	rules (module docstring). Every approval field is taken from the database, then set for the transition."""
	stored = frappe.db.get_value(
		DOCTYPE, doc.name, ["approval_status", *APPROVAL_FIELDS], as_dict=True, for_update=True
	)
	old = stored.approval_status or PENDING
	new = doc.approval_status or PENDING
	reason = (doc.get("return_reason") or "").strip()
	for field in APPROVAL_FIELDS:
		doc.set(field, stored.get(field))
	doc.approval_status = old
	if new == old:
		return
	if new not in STATUSES:
		frappe.throw(_("Invalid daily log approval status: {0}").format(new))
	if old not in (PENDING, VERIFIED):
		frappe.throw(_("This daily log is already approved or returned; cancel and amend it to change it."))
	if new == PENDING:
		frappe.throw(_("A daily log cannot go back to Pending; cancel and amend it instead."))
	verification = requires_supervisor_verification(doc.company)
	if new == VERIFIED:
		_verify(doc, old, verification)
	elif new == APPROVED:
		_approve(doc, old, verification)
	else:
		_return(doc, old, verification, reason)


def _verify(doc, old, verification):
	if not verification:
		frappe.throw(_("Company {0} does not use supervisor verification of daily logs.").format(doc.company))
	if old != PENDING:
		frappe.throw(_("This daily log is already verified."))
	if not _has_any_role((SUPERVISOR_ROLE,)):
		frappe.throw(_("Only a Card Supervisor may verify a daily log."), frappe.PermissionError)
	if frappe.session.user in log_preparers(doc):
		frappe.throw(
			_("You created, edited or submitted this daily log; another supervisor must verify it."),
			frappe.PermissionError,
		)
	doc.update(
		{"approval_status": VERIFIED, "verified_by": frappe.session.user, "verified_on": now_datetime()}
	)


def _approve(doc, old, verification):
	if not _has_any_role(APPROVER_ROLES):
		frappe.throw(_("Only Card Manager may approve or return a daily log."), frappe.PermissionError)
	if verification and old != VERIFIED:
		frappe.throw(_("A supervisor must verify this daily log before it is approved."))
	user = frappe.session.user
	self_approved = user in log_preparers(doc) or user == doc.get("verified_by")
	if self_approved:
		if self_approval_rule(doc.company) == RULE_REFUSE:
			frappe.throw(
				_(
					"You created, edited or submitted this daily log; another approver must approve it (company rule: Refuse)."
				),
				frappe.PermissionError,
			)
		frappe.msgprint(
			_(
				"You created, edited or submitted this daily log and approve it yourself; it is marked for review (company rule: Warn)."
			),
			title=_("Daily log self-approval"),
			indicator="orange",
		)
	doc.update(
		{
			"approval_status": APPROVED,
			"approved_by": user,
			"approved_on": now_datetime(),
			"self_approved": 1 if self_approved else 0,
		}
	)


def _return(doc, old, verification, reason):
	supervisor_return = verification and old == PENDING and _has_any_role((SUPERVISOR_ROLE,))
	if not (_has_any_role(APPROVER_ROLES) or supervisor_return):
		frappe.throw(_("Only Card Manager may approve or return a daily log."), frappe.PermissionError)
	if not reason:
		frappe.throw(_("Enter the reason for returning the daily log."))
	doc.update(
		{
			"approval_status": RETURNED,
			"return_reason": reason,
			"returned_by": frappe.session.user,
			"returned_on": now_datetime(),
		}
	)


def check_cancel(doc):
	"""before_cancel, on every route (form, REST PUT with docstatus 2, savedocs, bulk): the approval and the
	preparers are read from the database (a cancel may carry a forged document) and kept; a cancel that changes any
	other stored field or row is refused (``CancelChangesDocumentError``); an approved log is cancelled by an
	approver only (monthly cards may come from it)."""
	stored = frappe.db.get_value(DOCTYPE, doc.name, list(SERVER_FIELDS), as_dict=True, for_update=True)
	for field in SERVER_FIELDS:
		doc.set(field, stored.get(field))
	# Frappe skips validate on a cancel and stores what the request sends: any other change (header, rows, hours,
	# date) refuses the cancel, through the generic FR-123 guard the monthly card uses
	latest = doc.get_latest()
	if latest:
		refuse_cancel_changes(doc, latest, neutral=True)
	if stored.approval_status == APPROVED and not _has_any_role(APPROVER_ROLES):
		frappe.throw(
			_("An approved daily log can only be cancelled by a Card Manager."), frappe.PermissionError
		)


# ---------- Card Daily Log Settings: company scope ----------
def deny_cross_company_settings_share(doc, method=None):
	"""DocShare validate: Frappe 16 falls back to a DocShare after ``settings_permission`` denied, so a share would
	reopen another company's daily log rules. Refuse a share of Card Daily Log Settings with everyone, and with a
	user limited (for Card Daily Log) to companies other than the record's. Every other DocType is not affected."""
	if doc.share_doctype != SETTINGS_DOCTYPE:
		return
	from card.company_scope import _restricted

	if doc.get("everyone") or not doc.user:
		frappe.throw(
			_("A CARD record of type {0} cannot be shared with everyone.").format(_(doc.share_doctype)),
			frappe.PermissionError,
		)
	companies = _restricted(doc.user, DOCTYPE)
	if companies is None:
		return
	company = frappe.db.get_value(SETTINGS_DOCTYPE, doc.share_name, "company")
	if company and company not in companies:
		frappe.throw(
			_(
				"This CARD record of type {0} belongs to company {1} and cannot be shared with a user outside that company."
			).format(_(doc.share_doctype), company),
			frappe.PermissionError,
		)


def settings_permission(doc, ptype=None, user=None, debug=False):
	"""has_permission of Card Daily Log Settings: a user limited to some companies for Card Daily Log (Company User
	Permissions that apply to Card Daily Log, applicable_for included) sees and changes only those companies'
	records. A controller can only deny (Frappe 16), so "no objection" is True."""
	from card.company_scope import _restricted

	companies = _restricted(user, DOCTYPE)
	if companies is None:
		return True
	owners = {doc.get("company")}
	if not doc.is_new():
		owners.add(frappe.db.get_value(SETTINGS_DOCTYPE, doc.name, "company"))
	owners.discard(None)
	owners.discard("")
	if not owners:
		return not doc.is_new()
	return all(company in companies for company in owners)


def settings_query_conditions(user=None, doctype=None):
	"""List twin of ``settings_permission``."""
	from card.company_scope import _restricted

	companies = _restricted(user, DOCTYPE)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	values = ", ".join(frappe.db.escape(company) for company in companies)
	return f"`tab{SETTINGS_DOCTYPE}`.`company` in ({values})"
