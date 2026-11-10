# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-147 (#49, closure plan WP-S1): the Card Period Run, a versioned review record of one company-month.

A period run holds a snapshot of what the monthly posting would bill for one company and month: every submitted
Card Monthly Card of that month whose direction bills a supplier or a customer, with its last-modified time and a
fingerprint of its content, the total per side (supplier: the card's ``net_amount``; customer: its
``customer_net_amount``, in the company currency) and a version number. An accountant approves the run; the
approval is tied to that exact version and snapshot.

Nothing posts from a run yet: WP-S2 adds "an approved, current period run is required before post_month" (opt-in
per company). The run writes no GL entry, no invoice and nothing on any card; it is a review record only.

Build and versions:

- The snapshot is built by the server on every draft save and on submit (``prepare_run``); rows, totals and
  fingerprints sent by a client are never kept. A draft is therefore current when it is submitted.
- One active (draft or submitted) run per company and month. A new run takes the next version number of that
  company-month (every earlier run counts, cancelled ones included). Both checks hold a lock on the Company row
  and read the other runs with a locking read, so two runs saved at the same time cannot both pass.
- A card fingerprint covers the card's own fields and rows, except its links to the posting documents (Purchase
  Invoice, Sales Invoice, Journal Entry, GL Posting Log, ``posted``) and the cancel reason: posting a month never
  makes its run stale; any other change does, and so does a card that is submitted, cancelled or amended in that
  month (``check_current``).
- A stale run is never approved; an approved run that became stale is no longer an approval
  (``approved_run`` returns nothing). A new version is a cancel and amend of the run.

Approval (the FR-142 daily log pattern, ``card.daily_log``): the approval fields are written by the server only.
On a submitted run a change of ``approval_status`` through any route (form, REST PUT, ``frappe.client.set_value``,
savedocs, bulk update) is checked in ``before_update_after_submit``; a cancel through any route (bulk cancel
included) reads the stored approval in ``before_cancel`` under a lock. Only Accounts Manager or System Manager
approves or returns; a return needs a reason; an approved or returned run is final (cancel and amend). Whoever
created, edited or submitted the run or any run of its amendment chain is its preparer. When a preparer approves,
the run's ``self_approval_rule`` decides: "Warn only" (the default) approves with a message and marks the run
``self_approved``; "Refuse" refuses. The rule can be raised to Refuse at any time and never lowered, and an
amendment keeps it. No role is exempt.

Company isolation is the generic FR-131 scope (``card.company_scope``, registered for this DocType); the totals
and row amounts sit at permlevel 1, read by the roles that read card amounts (O-20: never Card Operator or
CARD Mobile)."""

import hashlib
import json

import frappe
from frappe import _
from frappe.model import default_fields, no_value_fields, table_fields
from frappe.utils import cint, cstr, flt, now_datetime

from card.constants import CUSTOMER_BILLING_DIRECTIONS, SUPPLIER_BILLING_DIRECTIONS
from card.daily_log import _add_preparers, _has_any_role
from card.report_access import permitted_companies

DOCTYPE = "Card Period Run"
ROW_DOCTYPE = "Card Period Run Card"
CARD = "Card Monthly Card"

PENDING = "Pending"
APPROVED = "Approved"
RETURNED = "Returned for correction"
STATUSES = (PENDING, APPROVED, RETURNED)

RULE_WARN = "Warn only (period run)"
RULE_REFUSE = "Refuse (period run)"

PREPARER_ROLES = ("Card Manager", "System Manager")
APPROVER_ROLES = ("Accounts Manager", "System Manager")

# written by the server only; a client value is never kept
APPROVAL_FIELDS = (
	"approved_by",
	"approved_on",
	"approved_version",
	"approved_hash",
	"self_approved",
	"return_reason",
	"returned_by",
	"returned_on",
)
SNAPSHOT_FIELDS = (
	"version",
	"built_on",
	"snapshot_hash",
	"currency",
	"card_count",
	"supplier_card_count",
	"supplier_total",
	"customer_card_count",
	"customer_total",
)
# restored from the database on cancel as well (a cancel may carry a forged document)
SERVER_FIELDS = ("approval_status", *APPROVAL_FIELDS, "submitted_by", "edited_by", "self_approval_rule")

# a card's links to the documents its posting creates: posting the month does not change what was reviewed
_POSTING_LINKS = frozenset({"Purchase Invoice", "Sales Invoice", "Journal Entry", "GL Posting Log"})
_IGNORED_CARD_FIELDS = frozenset({"posted", "cancel_reason"})
_NUMERIC = frozenset({"Currency", "Float", "Percent", "Int", "Check", "Rating", "Duration"})
_BILLING_DIRECTIONS = tuple(dict.fromkeys((*SUPPLIER_BILLING_DIRECTIONS, *CUSTOMER_BILLING_DIRECTIONS)))


# ---------- snapshot ----------
def _month(month):
	try:
		value = int(month)
	except (TypeError, ValueError):
		value = 0
	if not 1 <= value <= 12:
		frappe.throw(_("Period run month must be between 01 and 12."))
	return "%02d" % value


def _year(year):
	try:
		value = int(year)
	except (TypeError, ValueError):
		value = 0
	if not 2000 <= value <= 2200:
		frappe.throw(_("Period run year is not valid: {0}").format(year))
	return value


def _value(df, value):
	if df.fieldtype in _NUMERIC:
		return flt(value, 6)
	return cstr(value)


def _content(doc):
	"""The reviewed content of a card (or of one of its rows), as plain values."""
	out = {}
	for df in doc.meta.fields:
		if df.fieldname in default_fields or df.fieldname in _IGNORED_CARD_FIELDS:
			continue
		if df.fieldtype in table_fields:
			out[df.fieldname] = [_content(row) for row in doc.get(df.fieldname) or []]
		elif df.fieldtype in no_value_fields:
			continue
		elif df.fieldtype == "Link" and df.options in _POSTING_LINKS:
			continue
		else:
			out[df.fieldname] = _value(df, doc.get(df.fieldname))
	return out


def card_fingerprint(card):
	"""SHA-256 of a card's reviewed content (``card`` is a loaded Card Monthly Card); see the module docstring."""
	content = {"name": card.name, "docstatus": cint(card.docstatus), **_content(card)}
	return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


def _included_cards(company, month, year):
	return frappe.get_all(
		CARD,
		filters={
			"docstatus": 1,
			"company": company,
			"month": month,
			"year": year,
			"card_direction": ["in", list(_BILLING_DIRECTIONS)],
		},
		pluck="name",
		order_by="name asc",
	)


def _snapshot_hash(company, month, year, rows):
	content = [company, month, year] + [
		[r["card"], r["content_hash"], flt(r["supplier_amount"], 2), flt(r["customer_amount"], 2)]
		for r in rows
	]
	return hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest()


def build_snapshot(company: str, month: str | int, year: str | int) -> frappe._dict:
	"""What the monthly posting of ``company`` for ``month``/``year`` would bill, as a period-run snapshot. Reads
	only; the caller checks the permissions."""
	month, year = _month(month), _year(year)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	rows = []
	for name in _included_cards(company, month, year):
		card = frappe.get_doc(CARD, name)
		supplier_side = card.card_direction in SUPPLIER_BILLING_DIRECTIONS
		customer_side = card.card_direction in CUSTOMER_BILLING_DIRECTIONS
		rows.append(
			{
				"card": card.name,
				"equipment": card.equipment,
				"project": card.project,
				"card_direction": card.card_direction,
				"supplier": card.supplier if supplier_side else None,
				"customer": card.customer if customer_side else None,
				"supplier_amount": flt(card.net_amount, 2) if supplier_side else 0.0,
				"customer_amount": flt(card.customer_net_amount, 2) if customer_side else 0.0,
				"currency": currency,
				"card_modified": card.modified,
				"content_hash": card_fingerprint(card),
			}
		)
	supplier_rows = [r for r in rows if r["card_direction"] in SUPPLIER_BILLING_DIRECTIONS]
	customer_rows = [r for r in rows if r["card_direction"] in CUSTOMER_BILLING_DIRECTIONS]
	return frappe._dict(
		company=company,
		month=month,
		year=year,
		currency=currency,
		rows=rows,
		card_count=len(rows),
		supplier_card_count=len(supplier_rows),
		supplier_total=flt(sum(r["supplier_amount"] for r in supplier_rows), 2),
		customer_card_count=len(customer_rows),
		customer_total=flt(sum(r["customer_amount"] for r in customer_rows), 2),
		snapshot_hash=_snapshot_hash(company, month, year, rows),
	)


def check_current(run) -> frappe._dict:
	"""Compare a run (a loaded Card Period Run) with the live cards. Reads only. Returns ``current`` and the cards
	``added`` (now included, not in the run), ``removed`` (in the run, no longer included) and ``changed`` (their
	fingerprint differs)."""
	live = build_snapshot(run.company, run.month, run.year)
	stored = {r.card: r.content_hash for r in run.get("cards") or []}
	now = {r["card"]: r["content_hash"] for r in live.rows}
	added = sorted(set(now) - set(stored))
	removed = sorted(set(stored) - set(now))
	changed = sorted(c for c in set(now) & set(stored) if now[c] != stored[c])
	return frappe._dict(
		current=live.snapshot_hash == run.snapshot_hash and not (added or removed or changed),
		live_hash=live.snapshot_hash,
		snapshot_hash=run.snapshot_hash,
		added=added,
		removed=removed,
		changed=changed,
	)


def _approval_valid(run, state=None):
	state = state or check_current(run)
	return bool(
		run.docstatus == 1
		and run.approval_status == APPROVED
		and cint(run.approved_version) == cint(run.version)
		and run.approved_hash
		and run.approved_hash == run.snapshot_hash
		and state.current
	)


# ---------- read (WP-S2) ----------
def active_run(company: str, month: str | int, year: str | int):
	"""The name of the draft or submitted run of the company-month, or None. Reads only."""
	return frappe.db.get_value(
		DOCTYPE,
		{"company": company, "month": _month(month), "year": _year(year), "docstatus": ["<", 2]},
		"name",
		order_by="version desc",
	)


def approved_run(company: str, month: str | int, year: str | int):
	"""For WP-S2: the name of the company-month's run when it is submitted, approved for its current version and
	still current; otherwise None. Reads only; the caller checks the permissions."""
	name = active_run(company, month, year)
	if not name:
		return None
	run = frappe.get_doc(DOCTYPE, name)
	return name if _approval_valid(run) else None


def run_state(run, with_amounts: bool = False) -> frappe._dict:
	"""The state of a run (a loaded Card Period Run) for a screen or WP-S2. Reads only. ``with_amounts`` adds the
	totals; the caller decides whether the user may read them."""
	state = check_current(run)
	out = frappe._dict(
		run=run.name,
		company=run.company,
		month=run.month,
		year=cint(run.year),
		version=cint(run.version),
		docstatus=run.docstatus,
		approval_status=run.approval_status,
		approved_version=cint(run.approved_version) or None,
		self_approval_rule=run.self_approval_rule,
		card_count=cint(run.card_count),
		current=state.current,
		approval_valid=_approval_valid(run, state),
		added=state.added,
		removed=state.removed,
		changed=state.changed,
	)
	if with_amounts:
		out.update(
			currency=run.currency,
			supplier_total=flt(run.supplier_total, 2),
			customer_total=flt(run.customer_total, 2),
		)
	return out


# ---------- preparers and rule ----------
def run_preparers(doc) -> set:
	"""Users who prepared the run, all written by the server: its creator, its submitter and every user who saved
	it as a draft, for the run and every run of its amendment chain. A saved run is read from the database."""
	users = set()
	_add_preparers(users, doc)
	seen = set()
	name = doc.name if not doc.is_new() else doc.get("amended_from")
	while name and name not in seen:
		seen.add(name)
		row = frappe.db.get_value(
			DOCTYPE, name, ["owner", "submitted_by", "edited_by", "amended_from"], as_dict=True
		)
		if not row:
			break
		_add_preparers(users, row)
		name = row.amended_from
	return {u for u in users if u}


def _chain_refuses(name):
	seen = set()
	while name and name not in seen:
		seen.add(name)
		row = frappe.db.get_value(DOCTYPE, name, ["self_approval_rule", "amended_from"], as_dict=True)
		if not row:
			return False
		if row.self_approval_rule == RULE_REFUSE:
			return True
		name = row.amended_from
	return False


def _strictest_rule(doc):
	"""Refuse when the run sends it, stores it, or any run of its amendment chain has it; else Warn only."""
	if doc.get("self_approval_rule") == RULE_REFUSE:
		return RULE_REFUSE
	if _chain_refuses(doc.name if not doc.is_new() else doc.get("amended_from")):
		return RULE_REFUSE
	return RULE_WARN


# ---------- draft and submit ----------
def _lock_and_list(doc):
	"""Lock the Company row, then read every run of the company-month with a locking read (the latest committed
	rows, not the request's REPEATABLE READ snapshot)."""
	frappe.db.get_value("Company", doc.company, "name", for_update=True)
	run = frappe.qb.DocType(DOCTYPE)
	return (
		frappe.qb.from_(run)
		.select(run.name, run.version, run.docstatus)
		.where(run.company == doc.company)
		.where(run.month == doc.month)
		.where(run.year == doc.year)
		.for_update()
	).run(as_dict=True)


def _check_amended_from(doc):
	original = doc.get("amended_from")
	if not original:
		return
	stored = frappe.db.get_value(DOCTYPE, original, ["company", "month", "year"], as_dict=True)
	if (
		not stored
		or stored.company != doc.company
		or stored.month != doc.month
		or cint(stored.year) != cint(doc.year)
		or not frappe.has_permission(DOCTYPE, "read", original)
	):
		frappe.throw(
			_("A period run can only amend a cancelled period run of the same company and month."),
			frappe.PermissionError,
		)


def prepare_run(doc):
	"""validate (draft save and submit, REST insert with docstatus 1 included): the approval stays Pending, the
	approval fields empty, the snapshot is rebuilt from the live cards, the version is the server's; one active run
	per company-month."""
	doc.month, doc.year = _month(doc.month), _year(doc.year)
	if doc.is_new() or not frappe.db.exists(DOCTYPE, doc.name):
		stored = None
	else:
		stored = frappe.db.get_value(
			DOCTYPE,
			doc.name,
			["submitted_by", "edited_by", "version", "company", "month", "year"],
			as_dict=True,
		)
	if stored and (
		stored.company != doc.company or stored.month != doc.month or cint(stored.year) != doc.year
	):
		frappe.throw(_("The company and month of a saved period run cannot be changed; create a new run."))
	_check_amended_from(doc)
	doc.approval_status = PENDING
	for field in APPROVAL_FIELDS:
		doc.set(field, None)
	doc.self_approved = 0
	doc.self_approval_rule = _strictest_rule(doc)
	doc.submitted_by = stored.submitted_by if stored else None
	editors = [e for e in ((stored.edited_by if stored else "") or "").split("\n") if e]
	if frappe.session.user not in editors:
		editors.append(frappe.session.user)
	doc.edited_by = "\n".join(editors)

	runs = _lock_and_list(doc)
	others = [r for r in runs if r.name != doc.name]
	active = sorted(r.name for r in others if cint(r.docstatus) < 2)
	if active:
		frappe.throw(
			_(
				"Company {0} already has an active period run for {1}/{2}: {3}. Cancel it and amend it for a new version."
			).format(doc.company, doc.month, doc.year, ", ".join(active)),
			frappe.DuplicateEntryError,
		)
	doc.version = (
		cint(stored.version)
		if stored and cint(stored.version)
		else max([cint(r.version) for r in others] or [0]) + 1
	)

	snapshot = build_snapshot(doc.company, doc.month, doc.year)
	if not snapshot.rows:
		frappe.throw(
			_("Company {0} has no submitted billable monthly cards for {1}/{2}.").format(
				doc.company, doc.month, doc.year
			)
		)
	doc.set("cards", [])
	for row in snapshot.rows:
		doc.append("cards", row)
	for field in SNAPSHOT_FIELDS:
		if field != "version":
			doc.set(field, snapshot.get(field))
	doc.built_on = now_datetime()


def record_submitter(doc):
	"""before_submit: the submitter is a preparer."""
	doc.submitted_by = frappe.session.user


# ---------- approval (after submit) ----------
def check_transition(doc):
	"""before_update_after_submit: the only changes allowed on a submitted run are the approval and a raise of the
	self-approval rule, by the server's rules (module docstring). Every approval field is taken from the database,
	then set for the transition."""
	stored = frappe.db.get_value(
		DOCTYPE,
		doc.name,
		["approval_status", "self_approval_rule", *APPROVAL_FIELDS],
		as_dict=True,
		for_update=True,
	)
	old = stored.approval_status or PENDING
	new = doc.approval_status or PENDING
	reason = (doc.get("return_reason") or "").strip()
	rule = doc.get("self_approval_rule") or RULE_WARN
	for field in APPROVAL_FIELDS:
		doc.set(field, stored.get(field))
	doc.approval_status = old
	if rule != stored.self_approval_rule:
		if stored.self_approval_rule == RULE_REFUSE or rule != RULE_REFUSE:
			frappe.throw(_("The self-approval rule of a period run can be raised to Refuse, never lowered."))
		if old != PENDING:
			frappe.throw(_("This period run is already approved or returned; its rule cannot change."))
	doc.self_approval_rule = rule
	if new == old:
		return
	if new not in STATUSES:
		frappe.throw(_("Invalid period run approval status: {0}").format(new))
	if old != PENDING:
		frappe.throw(_("This period run is already approved or returned; cancel and amend it to change it."))
	if not _has_any_role(APPROVER_ROLES):
		frappe.throw(_("Only Accounts Manager may approve or return a period run."), frappe.PermissionError)
	if new == APPROVED:
		_approve(doc)
	elif new == RETURNED:
		_return(doc, reason)
	else:
		frappe.throw(_("A period run cannot go back to Pending; cancel and amend it instead."))


def _approve(doc):
	state = check_current(doc)
	if not state.current:
		frappe.throw(
			_(
				"The cards of this period run changed after it was built (added: {0}; removed: {1}; changed: {2}). Cancel and amend it to build a new version, then approve that version."
			).format(
				", ".join(state.added) or "-",
				", ".join(state.removed) or "-",
				", ".join(state.changed) or "-",
			),
			frappe.ValidationError,
		)
	user = frappe.session.user
	self_approved = user in run_preparers(doc)
	if self_approved:
		if doc.self_approval_rule == RULE_REFUSE:
			frappe.throw(
				_(
					"You prepared, edited or submitted this period run (or an earlier version); another accountant must approve it (rule: Refuse)."
				),
				frappe.PermissionError,
			)
		frappe.msgprint(
			_(
				"You prepared, edited or submitted this period run and approve it yourself; it is marked for review (rule: Warn)."
			),
			title=_("Period run self-approval"),
			indicator="orange",
		)
	doc.update(
		{
			"approval_status": APPROVED,
			"approved_by": user,
			"approved_on": now_datetime(),
			"approved_version": cint(doc.version),
			"approved_hash": doc.snapshot_hash,
			"self_approved": 1 if self_approved else 0,
		}
	)


def _return(doc, reason):
	if not reason:
		frappe.throw(_("Enter the reason for returning the period run."))
	doc.update(
		{
			"approval_status": RETURNED,
			"return_reason": reason,
			"returned_by": frappe.session.user,
			"returned_on": now_datetime(),
		}
	)


def check_cancel(doc):
	"""before_cancel, on every route (form, REST PUT with docstatus 2, savedocs, bulk cancel): the approval, the
	preparers and the rule are read from the database under a lock (a cancel may carry a forged document) and
	kept. A run whose approval is still valid is cancelled by an approver only; a stale or pending run by its
	preparers too (for a new version)."""
	stored = frappe.db.get_value(DOCTYPE, doc.name, list(SERVER_FIELDS), as_dict=True, for_update=True)
	for field in SERVER_FIELDS:
		doc.set(field, stored.get(field))
	if stored.approval_status == APPROVED and not _has_any_role(APPROVER_ROLES):
		run = frappe.get_doc(DOCTYPE, doc.name)
		if _approval_valid(run):
			frappe.throw(
				_("This period run is approved and still current; only Accounts Manager may cancel it."),
				frappe.PermissionError,
			)


# ---------- endpoints ----------
def _check_company(company, ptype):
	if not company or company not in permitted_companies(CARD, DOCTYPE):
		frappe.throw(
			_("You are not permitted to use period runs of company {0}.").format(company),
			frappe.PermissionError,
		)
	if not frappe.has_permission(DOCTYPE, ptype):
		frappe.throw(_("You are not permitted to use period runs."), frappe.PermissionError)


@frappe.whitelist(methods=["POST"])
def build_run(company: str, month: str, year: str) -> str:
	"""Build (or rebuild) the draft period run of a company-month and return its name. A draft is saved again,
	which rebuilds its snapshot; a new run amends the latest cancelled run of the month, so its version and its
	preparers follow on. Card Manager or System Manager; Frappe's create/write permission and the company scope
	apply (no permission is skipped)."""
	if not _has_any_role(PREPARER_ROLES):
		frappe.throw(_("Only Card Manager may build a period run."), frappe.PermissionError)
	_check_company(company, "create")
	month, year = _month(month), _year(year)
	name = active_run(company, month, year)
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.docstatus != 0:
			frappe.throw(
				_(
					"Period run {0} is already submitted. Cancel it and amend it to build a new version."
				).format(name),
				frappe.DuplicateEntryError,
			)
		doc.save()
		return doc.name
	latest = frappe.db.get_value(
		DOCTYPE,
		{"company": company, "month": month, "year": year, "docstatus": 2},
		"name",
		order_by="version desc",
	)
	doc = frappe.new_doc(DOCTYPE)
	doc.update({"company": company, "month": month, "year": year, "amended_from": latest})
	doc.insert()
	return doc.name


@frappe.whitelist(methods=["GET"])
def period_run_status(company: str, month: str, year: str) -> dict:
	"""The active run of a company-month and whether it is current and validly approved. Reads only. The totals are
	returned only to a user who may read the run's amounts (permlevel 1)."""
	_check_company(company, "read")
	name = active_run(company, month, year)
	if not name:
		return {"run": None, "company": company, "month": _month(month), "year": _year(year)}
	run = frappe.get_doc(DOCTYPE, name)
	run.check_permission("read")
	with_amounts = 1 in frappe.get_meta(DOCTYPE).get_permlevel_access("read")
	return run_state(run, with_amounts=with_amounts)
