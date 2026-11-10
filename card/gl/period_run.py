# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-147 (#49, closure plan WP-S1): the Card Period Run, a versioned review record of one company-month.

A period run holds a snapshot of every source document the monthly posting bills for one company and month, a
total per side and a version number. An accountant approves the run; the approval is tied to that exact version
and snapshot.

Nothing posts from a run yet: WP-S2 adds "an approved, current period run is required before post_month" (opt-in
per company). The run writes no GL entry, no invoice and nothing on any source; it is a review record only.

What the snapshot covers: the WHOLE month, posted and unposted documents alike, selected by the filters
``card.gl.posting`` uses for its sources (``_supplier_sources``, ``_responsibility_transports``,
``_customer_cards``, ``_customer_transports``) without the "no invoice yet" filter:

- Card Monthly Card: submitted, of the company and month, direction billing a supplier (supplier side,
  ``net_amount``) and/or a customer (customer side, ``customer_net_amount``);
- Project Diesel Fill: submitted, dated in the month, not an imported WhatsApp session (supplier side,
  ``amount``, the fill's own amount; with a VAT-inclusive diesel price the invoice books its net part);
- Equipment Transport, supplier side: submitted, dated in the month, recorded before P1-2 (no responsibility, no
  payer, the company bears it: ``amount``); with the company's FR-139 setting Post also the transports with a
  responsibility that the transporter's invoice carries (``amount``, less the recovery deducted on that invoice);
- Equipment Transport, customer side (FR-139 Post only): the approved "Bill customer" monthly-invoice transports
  (``billing_amount``).

One row per document (both sides on one row), with its parties, the amount per side, whether each side is already
posted (an active CARD posting log holds it, or its invoice link is set: ``supplier_posted`` / ``customer_posted``,
so WP-S2 can compare the run with the unposted remainder), its last-modified time and a fingerprint. The posted
flags are information only: posting the month never makes the run stale.

Build and versions:

- The snapshot is built by the server on every draft save and on submit (``prepare_run``); rows, totals and
  fingerprints sent by a client are never kept. A draft is therefore current when it is submitted.
- One active (draft or submitted) run per company and month. A new run takes the next version number of that
  company-month (every earlier run counts, cancelled ones included); a unique index on (company, month, year,
  version) backs it. Both checks hold a lock on the Company row and read the other runs with a locking read, so
  two runs saved at the same time cannot both pass.
- A fingerprint covers an explicit, versioned list of the billing fields of the document and of its rows
  (``FINGERPRINT_FIELDS``; amounts, quantities, parties, project, period, direction, posting eligibility), and
  leaves empty values out, so a field added to a DocType later never changes a stored fingerprint. A change of
  one of these fields makes the run stale, and so does a document that joins or leaves the selection (submitted,
  cancelled, amended, its decision changed) (``check_current``).
- A stale run is never approved; an approved run that became stale is no longer an approval (``approved_run``
  returns nothing). A new version is a cancel and amend of the run.
- A cancel changes nothing on the run: a cancel request that changes any other field or row is refused
  (``card.cancel_reason`` guard, ``CancelChangesDocumentError``).

Approval (the FR-142 daily log pattern, ``card.daily_log``): the approval fields are written by the server only.
On a submitted run a change of ``approval_status`` through any route (form, REST PUT, ``frappe.client.set_value``,
savedocs, bulk update) is checked in ``before_update_after_submit``; a cancel through any route (bulk cancel
included) reads the stored approval in ``before_cancel`` under a lock. Only Accounts Manager or System Manager
approves or returns; a return needs a reason; an approved or returned run is final (cancel and amend). Whoever
created, edited or submitted the run or any run of its amendment chain is its preparer (the preparers of the
source documents are not counted; open owner question). When a preparer approves, the run's
``self_approval_rule`` decides: "Warn only" (the default) approves with a message and marks the run
``self_approved``; "Refuse" refuses. The rule can be raised to Refuse at any time and never lowered, and an
amendment keeps it. No role is exempt. Known limit: the rule is per run; WP-S2 (which owns Card Company Settings)
applies the stricter of a per-company rule and the run's rule.

Company isolation is the generic FR-131 scope (``card.company_scope``, registered for this DocType); the totals
and row amounts sit at permlevel 1, read by the roles that read card amounts (O-20: never Card Operator or
CARD Mobile)."""

import hashlib
import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_last_day, getdate, now_datetime

from card import transport_costs as tc
from card.cancel_reason import _refuse_changes
from card.constants import CUSTOMER_BILLING_DIRECTIONS, SUPPLIER_BILLING_DIRECTIONS
from card.daily_log import _add_preparers, _has_any_role
from card.gl import preflight
from card.gl.posting import _TRANSPORT_SOURCE_FIELDS, _customer_transports, _unheld_batch
from card.report_access import permitted_companies

DOCTYPE = "Card Period Run"
ROW_DOCTYPE = "Card Period Run Source"
CARD = "Card Monthly Card"
FILL = "Project Diesel Fill"
TRANSPORT = "Equipment Transport"
SOURCE_DOCTYPES = (CARD, FILL, TRANSPORT)

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
	"built_on",
	"snapshot_hash",
	"fingerprint_version",
	"currency",
	"source_count",
	"supplier_source_count",
	"supplier_total",
	"customer_source_count",
	"customer_total",
)
# restored from the database on cancel as well (a cancel may carry a forged document)
SERVER_FIELDS = ("approval_status", *APPROVAL_FIELDS, "submitted_by", "edited_by", "self_approval_rule")

# The billing fields of each source document and of its rows, per fingerprint version. A new version is added
# here (never an edit of an existing one); a run keeps the version it was built with.
FINGERPRINT_VERSION = 1
FINGERPRINT_FIELDS = {
	1: {
		CARD: (
			(
				"company",
				"project",
				"equipment",
				"month",
				"year",
				"card_direction",
				"supplier",
				"customer",
				"rate_type",
				"rate",
				"working_days",
				"total_working_hours",
				"billable_stopped_hours",
				"billable_stopped_days",
				"supplier_billable_stopped_hours",
				"customer_billable_stopped_hours",
				"amount",
				"total_additions",
				"total_deductions",
				"net_amount",
				"daily_hours_used",
				"hourly_rate_used",
				"customer_rate_type",
				"customer_rate",
				"customer_amount",
				"customer_rate_used",
				"customer_net_amount",
				"day_billing_basis_used",
			),
			{
				"days": (
					"operation_date",
					"day_status",
					"working_hours",
					"stopped_hours",
					"stop_reason",
					"reason_billable",
					"responsible_party_type",
					"responsible_party",
				),
				"adjustments": (
					"adjustment_type",
					"adjustment_type_ref",
					"side",
					"amount",
					"stop_reason",
					"responsible_party_type",
					"responsible_party",
				),
			},
		),
		FILL: (
			(
				"company",
				"project",
				"supplier",
				"date",
				"card_equipment",
				"litres",
				"unit_price",
				"amount",
				"price_source",
				"company_price",
				"price_currency",
				"cost_center",
				"source_key",
			),
			{"equipment_filled": ("card_equipment",)},
		),
		TRANSPORT: (
			(
				"company",
				"project",
				"date",
				"transport_supplier",
				"amount",
				"cost_center",
				"cost_borne_by",
				"destination_type",
				"destination_location",
				"source_type",
				"source_project",
				"source_location",
				*tc.RESPONSIBILITY_POSTING_FIELDS,
			),
			{"items": ("card_equipment", "amount")},
		),
	}
}
_SIDE_LINK = {"Supplier": "purchase_invoice", "Customer": "sales_invoice"}


# ---------- period ----------
def _month(month) -> str:
	try:
		value = int(month)
	except (TypeError, ValueError):
		value = 0
	if not 1 <= value <= 12:
		frappe.throw(_("Period run month must be between 01 and 12."))
	return "%02d" % value


def _year(year) -> int:
	try:
		value = int(year)
	except (TypeError, ValueError):
		value = 0
	if not 2000 <= value <= 2200:
		frappe.throw(_("Period run year is not valid: {0}").format(year))
	return value


def _bounds(month: str, year: int):
	first = getdate(f"{year:04d}-{month}-01")
	return first, get_last_day(first)


# ---------- fingerprint ----------
def _plain(value):
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, int | float):
		return flt(value, 6)
	return cstr(value)


def _empty(value) -> bool:
	return value in (None, "", 0, 0.0) or value is False


def document_fingerprint(doc: Document, version: int = FINGERPRINT_VERSION) -> str:
	"""SHA-256 of the billing content of a loaded source document (module docstring): the listed fields of the
	document and of its rows, empty values left out."""
	fields, tables = FINGERPRINT_FIELDS[version][doc.doctype]
	content = {"doctype": doc.doctype, "name": doc.name, "docstatus": cint(doc.docstatus)}
	for field in fields:
		value = doc.get(field)
		if not _empty(value):
			content[field] = _plain(value)
	for table, row_fields in tables.items():
		rows = []
		for row in doc.get(table) or []:
			rows.append({f: _plain(row.get(f)) for f in row_fields if not _empty(row.get(f))})
		if rows:
			content[table] = rows
	return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()


# ---------- selection (the posting filters, whole month) ----------
def _supplier_transport_amount(transport) -> float:
	amount = flt(transport.amount, 2)
	if transport.get("posting_kind") == tc.RECOVERED_BY_DEDUCTION:
		amount = flt(amount - flt(transport.recovery_amount, 2), 2)
	return amount


def _selection(company: str, month: str, year: int) -> dict:
	"""{(doctype, name): {"Supplier": (party, amount), "Customer": (party, amount)}} of the company-month."""
	first, last = _bounds(month, year)
	out = {}

	def add(doctype, name, side, party, amount):
		out.setdefault((doctype, name), {})[side] = (party, flt(amount, 2))

	for row in frappe.get_all(
		CARD,
		filters={
			"docstatus": 1,
			"company": company,
			"month": month,
			"year": year,
			"card_direction": [
				"in",
				list(dict.fromkeys((*SUPPLIER_BILLING_DIRECTIONS, *CUSTOMER_BILLING_DIRECTIONS))),
			],
		},
		fields=["name", "card_direction", "supplier", "customer", "net_amount", "customer_net_amount"],
	):
		if row.card_direction in SUPPLIER_BILLING_DIRECTIONS:
			add(CARD, row.name, "Supplier", row.supplier, row.net_amount)
		if row.card_direction in CUSTOMER_BILLING_DIRECTIONS:
			add(CARD, row.name, "Customer", row.customer, row.customer_net_amount)
	for row in frappe.get_all(
		FILL,
		filters={
			"docstatus": 1,
			"company": company,
			"date": ["between", [first, last]],
			"source_key": ["in", ["", None]],
			"source_messages": ["in", ["", None]],
		},
		fields=["name", "supplier", "amount"],
	):
		add(FILL, row.name, "Supplier", row.supplier, row.amount)
	for row in frappe.get_all(
		TRANSPORT,
		filters={
			"docstatus": 1,
			"company": company,
			"date": ["between", [first, last]],
			"cost_borne_by": ["in", ["Company", "", None]],
			"responsibility": ["in", ["", None]],
			"payer": ["in", ["", None]],
		},
		fields=["name", "transport_supplier", "amount"],
	):
		add(TRANSPORT, row.name, "Supplier", row.transport_supplier, row.amount)
	if preflight.posts_transport_responsibility(company):
		for row in frappe.get_all(
			TRANSPORT,
			filters={
				"docstatus": 1,
				"company": company,
				"date": ["between", [first, last]],
				"payer": "Company",
				"responsibility": ["is", "set"],
			},
			fields=list(dict.fromkeys([*_TRANSPORT_SOURCE_FIELDS, *tc.RESPONSIBILITY_POSTING_FIELDS])),
		):
			kind, _reason = tc.supplier_posting_kind(row)
			if kind:
				row.posting_kind = kind
				add(TRANSPORT, row.name, "Supplier", row.transport_supplier, _supplier_transport_amount(row))
		for row in _customer_transports(company, None, first, last):
			add(TRANSPORT, row.name, "Customer", row.customer, row.billing_amount)
	return out


def _posted(selection: dict) -> set:
	"""{(doctype, name, side)} already posted: held by an active CARD posting log of that side (the posting rule),
	or carrying that side's invoice link."""
	posted = set()
	for side in ("Supplier", "Customer"):
		for doctype in SOURCE_DOCTYPES:
			names = [name for (dt, name), sides in selection.items() if dt == doctype and side in sides]
			if not names:
				continue
			rows = [frappe._dict(name=n) for n in names]
			free = {r.name for r in _unheld_batch(rows, doctype, side)}
			link = _SIDE_LINK[side]
			linked = set()
			if frappe.get_meta(doctype).has_field(link):
				linked = set(
					frappe.get_all(
						doctype, filters={"name": ["in", names], link: ["is", "set"]}, pluck="name"
					)
				)
			posted.update((doctype, n, side) for n in names if n not in free or n in linked)
	return posted


def _snapshot_hash(company, month, year, version, rows) -> str:
	content = [company, month, year, version] + [
		[
			r["source_doctype"],
			r["source_name"],
			r["content_hash"],
			cstr(r["supplier"]),
			flt(r["supplier_amount"], 2),
			cstr(r["customer"]),
			flt(r["customer_amount"], 2),
		]
		for r in rows
	]
	return hashlib.sha256(json.dumps(content, default=str).encode()).hexdigest()


def build_snapshot(
	company: str, month: str | int, year: str | int, version: int = FINGERPRINT_VERSION
) -> frappe._dict:
	"""Every source document the monthly posting of ``company`` bills for ``month``/``year`` (the whole month), as a
	period-run snapshot. Reads only; the caller checks the permissions."""
	month, year = _month(month), _year(year)
	currency = frappe.get_cached_value("Company", company, "default_currency")
	selection = _selection(company, month, year)
	posted = _posted(selection)
	order = {doctype: i for i, doctype in enumerate(SOURCE_DOCTYPES)}
	rows = []
	for doctype, name in sorted(selection, key=lambda key: (order[key[0]], key[1])):
		sides = selection[(doctype, name)]
		doc = frappe.get_doc(doctype, name)
		supplier, supplier_amount = sides.get("Supplier", (None, 0.0))
		customer, customer_amount = sides.get("Customer", (None, 0.0))
		rows.append(
			{
				"source_doctype": doctype,
				"source_name": name,
				"equipment": doc.get("equipment") or doc.get("card_equipment"),
				"project": doc.get("project"),
				"supplier": supplier,
				"customer": customer,
				"supplier_side": 1 if "Supplier" in sides else 0,
				"customer_side": 1 if "Customer" in sides else 0,
				"supplier_amount": supplier_amount,
				"customer_amount": customer_amount,
				"supplier_posted": 1 if (doctype, name, "Supplier") in posted else 0,
				"customer_posted": 1 if (doctype, name, "Customer") in posted else 0,
				"currency": currency,
				"source_modified": doc.modified,
				"content_hash": document_fingerprint(doc, version),
			}
		)
	supplier_rows = [r for r in rows if r["supplier_side"]]
	customer_rows = [r for r in rows if r["customer_side"]]
	return frappe._dict(
		company=company,
		month=month,
		year=year,
		currency=currency,
		fingerprint_version=version,
		rows=rows,
		source_count=len(rows),
		supplier_source_count=len(supplier_rows),
		supplier_total=flt(sum(r["supplier_amount"] for r in supplier_rows), 2),
		customer_source_count=len(customer_rows),
		customer_total=flt(sum(r["customer_amount"] for r in customer_rows), 2),
		snapshot_hash=_snapshot_hash(company, month, year, version, rows),
	)


def check_current(run: Document) -> frappe._dict:
	"""Compare a run (a loaded Card Period Run) with the live source documents, with the run's fingerprint
	version. Reads only. Returns ``current`` and the documents ``added`` (now selected, not in the run),
	``removed`` (in the run, no longer selected) and ``changed`` (fingerprint, party or amount differs), by name;
	``posted_since`` lists the sides posted since the run was built (information only)."""
	live = build_snapshot(
		run.company, run.month, run.year, cint(run.fingerprint_version) or FINGERPRINT_VERSION
	)

	def key(r):
		return (r["source_doctype"], r["source_name"])

	def signature(r):
		return (
			r["content_hash"],
			cstr(r["supplier"]),
			flt(r["supplier_amount"], 2),
			cstr(r["customer"]),
			flt(r["customer_amount"], 2),
		)

	stored = {key(r): r for r in (row.as_dict() for row in run.get("sources") or [])}
	now = {key(r): r for r in live.rows}
	added = sorted(name for _dt, name in set(now) - set(stored))
	removed = sorted(name for _dt, name in set(stored) - set(now))
	changed = sorted(k[1] for k in set(now) & set(stored) if signature(now[k]) != signature(stored[k]))
	posted_since = sorted(
		f"{k[1]} ({side})"
		for k in set(now) & set(stored)
		for side, field in (("Supplier", "supplier_posted"), ("Customer", "customer_posted"))
		if cint(now[k][field]) and not cint(stored[k].get(field))
	)
	return frappe._dict(
		current=live.snapshot_hash == run.snapshot_hash and not (added or removed or changed),
		live_hash=live.snapshot_hash,
		snapshot_hash=run.snapshot_hash,
		added=added,
		removed=removed,
		changed=changed,
		posted_since=posted_since,
	)


def _approval_valid(run: Document, state: frappe._dict | None = None) -> bool:
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
def active_run(company: str, month: str | int, year: str | int) -> str | None:
	"""The name of the draft or submitted run of the company-month, or None. Reads only."""
	return frappe.db.get_value(
		DOCTYPE,
		{"company": company, "month": _month(month), "year": _year(year), "docstatus": ["<", 2]},
		"name",
		order_by="version desc",
	)


def approved_run(company: str, month: str | int, year: str | int) -> str | None:
	"""For WP-S2: the name of the company-month's run when it is submitted, approved for its current version and
	still current; otherwise None. Reads only; the caller checks the permissions."""
	name = active_run(company, month, year)
	if not name:
		return None
	run = frappe.get_doc(DOCTYPE, name)
	return name if _approval_valid(run) else None


def run_state(run: Document, with_amounts: bool = False) -> frappe._dict:
	"""The state of a run (a loaded Card Period Run) for a screen or WP-S2. Reads only (it rebuilds the live
	snapshot). ``with_amounts`` adds the totals; the caller decides whether the user may read them."""
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
		source_count=cint(run.source_count),
		current=state.current,
		approval_valid=_approval_valid(run, state),
		added=state.added,
		removed=state.removed,
		changed=state.changed,
		posted_since=state.posted_since,
	)
	if with_amounts:
		out.update(
			currency=run.currency,
			supplier_total=flt(run.supplier_total, 2),
			customer_total=flt(run.customer_total, 2),
		)
	return out


# ---------- preparers and rule ----------
def run_preparers(doc: Document) -> set[str]:
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


def _chain_refuses(name: str | None) -> bool:
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


def _strictest_rule(doc: Document) -> str:
	"""Refuse when the run sends it, stores it, or any run of its amendment chain has it; else Warn only."""
	if doc.get("self_approval_rule") == RULE_REFUSE:
		return RULE_REFUSE
	if _chain_refuses(doc.name if not doc.is_new() else doc.get("amended_from")):
		return RULE_REFUSE
	return RULE_WARN


# ---------- draft and submit ----------
def _lock_and_list(doc: Document) -> list:
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


def _check_amended_from(doc: Document) -> None:
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


def prepare_run(doc: Document) -> None:
	"""validate (draft save and submit, REST insert with docstatus 1 included): the approval stays Pending, the
	approval fields empty, the snapshot is rebuilt from the live source documents, the version is the server's;
	one active run per company-month."""
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
			_("Company {0} has no submitted source documents to bill for {1}/{2}.").format(
				doc.company, doc.month, doc.year
			)
		)
	doc.set("sources", [])
	for row in snapshot.rows:
		doc.append("sources", row)
	for field in SNAPSHOT_FIELDS:
		doc.set(field, snapshot.get(field))
	doc.built_on = now_datetime()


def record_submitter(doc: Document) -> None:
	"""before_submit: the submitter is a preparer."""
	doc.submitted_by = frappe.session.user


# ---------- approval (after submit) ----------
def check_transition(doc: Document) -> None:
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


def _approve(doc: Document) -> None:
	state = check_current(doc)
	if not state.current:
		frappe.throw(
			_(
				"The source documents of this period run changed after it was built (added: {0}; removed: {1}; changed: {2}). Cancel and amend it to build a new version, then approve that version."
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


def _return(doc: Document, reason: str) -> None:
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


def check_cancel(doc: Document) -> None:
	"""before_cancel, on every route (form, REST PUT with docstatus 2, savedocs, bulk cancel; Frappe skips validate
	on a cancel): the approval, the preparers and the rule are read from the database under a lock (a cancel may
	carry a forged document) and kept; any other field or row that differs from the stored run is refused
	(``card.cancel_reason`` guard). A run whose approval is still valid is cancelled by an approver only; a stale
	or pending run by its preparers too (for a new version)."""
	stored = frappe.db.get_value(DOCTYPE, doc.name, list(SERVER_FIELDS), as_dict=True, for_update=True)
	for field in SERVER_FIELDS:
		doc.set(field, stored.get(field))
	_refuse_changes(doc, doc.get_latest())
	if stored.approval_status == APPROVED and not _has_any_role(APPROVER_ROLES):
		run = frappe.get_doc(DOCTYPE, doc.name)
		if _approval_valid(run):
			frappe.throw(
				_("This period run is approved and still current; only Accounts Manager may cancel it."),
				frappe.PermissionError,
			)


# ---------- endpoints ----------
def _check_company(company: str, ptype: str) -> None:
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
	"""The active run of a company-month and whether it is current and validly approved. Reads only (it rebuilds
	the live snapshot on each call). The totals are returned only to a user who may read the run's amounts
	(permlevel 1)."""
	_check_company(company, "read")
	name = active_run(company, month, year)
	if not name:
		return {"run": None, "company": company, "month": _month(month), "year": _year(year)}
	run = frappe.get_doc(DOCTYPE, name)
	run.check_permission("read")
	with_amounts = 1 in frappe.get_meta(DOCTYPE).get_permlevel_access("read")
	return run_state(run, with_amounts=with_amounts)
