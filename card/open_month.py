# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-191: a submitted monthly card of a month that has not ended can be reopened on its ORIGINAL name, edited
through the month, and approved only after the month ends. No cancel, no amendment, no new card.

States (``workflow_state``, docstatus 1 in every case):

- "Approved – before governance" / "Approved": the card is approved; its operation data is frozen as before.
- "Open – month not ended" (``STATE_OPEN_MONTH``): the card is submitted but not finally approved. Its day rows,
  additions/deductions and site location can be changed with Frappe's Update After Submit (the fields are
  ``allow_on_submit`` in the DocType JSON). Each such save runs the card's own calculation again, so the hours,
  days, amounts, additions, deductions and nets follow the rows. Rates, equipment, project, supplier, customer,
  company, direction and period are not ``allow_on_submit`` and stay frozen (Frappe refuses a change).

Transitions (only through the whitelisted methods below; a ``workflow_state`` sent by a client is refused):

- reopen (``reopen_card``, ``reopen_open_month_cards``): approved -> open, System Manager only, only while the
  card's month has not ended (Riyadh), only for a card with no posting and no linked financial document.
- final approval (``approve_open_month_card``): open -> "Approved", manual only, refused before the month ends
  (``card.approval_period``), with the same separation-of-duties and approval-tier checks as a submit.

The guard ``before_update_after_submit`` runs on every update-after-submit route (form Update, REST PUT,
``frappe.client.set_value`` / ``save``, ``bulk_update``): a change of the open-month fields is accepted only on an
open card; on an approved card those fields keep their stored values exactly as before this feature. No role,
Administrator included, and no client flag bypasses it."""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, cstr, escape_html, now_datetime

from card.approval_period import check_card_approval_allowed, month_ended
from card.cancel_reason import _differs

DOCTYPE = "Card Monthly Card"
STATE_OPEN_MONTH = "Open – month not ended"
STATE_APPROVED = "Approved"
STATE_BEFORE_GOVERNANCE = "Approved – before governance"
REOPENABLE_STATES = (STATE_BEFORE_GOVERNANCE, STATE_APPROVED)
REOPEN_ROLE = "System Manager"

# parent fields a user edits on an open card (the tables are compared row by row)
EDIT_FIELDS = ("site_location",)
TABLE_FIELDS = ("days", "adjustments")
# parent fields the card's calculation writes (recomputed on an open card, restored on any other card)
COMPUTED_FIELDS = (
	"working_days",
	"total_working_hours",
	"total_loads",
	"total_volume_m3",
	"billable_stopped_hours",
	"billable_stopped_days",
	"supplier_billable_stopped_hours",
	"customer_billable_stopped_hours",
	"amount",
	"total_additions",
	"total_deductions",
	"net_amount",
	"customer_amount",
	"customer_net_amount",
)
# server-written by the reopen / final approval (not allow-on-submit; Frappe's check is off for these two saves)
TRANSITION_FIELDS = (
	"workflow_state",
	"approved_by",
	"approved_on",
	"submitted_by",
	"self_approved",
	"approval_tier",
	"approval_tier_name",
	"edited_by",
)
# child-row fields that are not business data (Frappe bookkeeping)
_ROW_META = {
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"parent",
	"parenttype",
	"parentfield",
}


class OpenMonthStateError(frappe.UpdateAfterSubmitError):
	pass


class OpenMonthEditError(frappe.UpdateAfterSubmitError):
	pass


class ReopenRefusedError(frappe.ValidationError):
	pass


# ---------- helpers ----------
def _transition_token():
	return frappe.flags.get("card_open_month_transition") or {}


def _set_token(name, target):
	token = dict(_transition_token())
	token[name] = target
	frappe.flags.card_open_month_transition = token


def _clear_token(name):
	token = dict(_transition_token())
	token.pop(name, None)
	frappe.flags.card_open_month_transition = token


def _row_fields(child_doctype):
	"""The value fields of a child row (layout fields have no value)."""
	return [
		df
		for df in frappe.get_meta(child_doctype).fields
		if df.fieldname not in _ROW_META and df.fieldtype not in no_value_fields
	]


def _same(a, b):
	return cstr(a if a is not None else "") == cstr(b if b is not None else "")


def open_fields_changed(doc, before) -> bool:
	"""True when the request changes the site location, adds, removes or reorders a day or adjustment row, or
	changes any field of one (read-only row fields included, so a forged computed value is seen too)."""
	if not before:
		return False
	for field in EDIT_FIELDS:
		if _differs(doc.meta.get_field(field), doc.get(field), before.get(field)):
			return True
	for table in TABLE_FIELDS:
		rows = doc.get(table) or []
		stored = before.get(table) or []
		if [r.name for r in rows] != [r.name for r in stored] or any(r.is_new() for r in rows):
			return True
		child = doc.meta.get_field(table).options
		fields = _row_fields(child)
		for row, old in zip(rows, stored, strict=True):
			# typed comparison (8 and 8.0 are equal), as the FR-123 cancel guard compares
			if any(_differs(df, row.get(df.fieldname), old.get(df.fieldname)) for df in fields):
				return True
	return False


def financial_links(name) -> dict:
	"""Every financial or posting record that refers to the card (any docstatus)."""
	links = {
		"Journal Entry": frappe.get_all(
			"Journal Entry Account", filters={"reference_name": name}, pluck="parent", distinct=True
		),
		"Payment Entry": frappe.get_all(
			"Payment Entry Reference", filters={"reference_name": name}, pluck="parent", distinct=True
		),
		"GL Posting Log": frappe.get_all(
			"GL Posting Source",
			filters={"source_doctype": DOCTYPE, "source_name": name},
			pluck="parent",
			distinct=True,
		),
		"Card Period Run": frappe.get_all(
			"Card Period Run Source",
			filters={"source_doctype": DOCTYPE, "source_name": name},
			pluck="parent",
			distinct=True,
		),
		"Card Cash Disbursement": frappe.get_all(
			"Card Cash Disbursement", filters={"card": name}, pluck="name"
		),
	}
	return {k: v for k, v in links.items() if v}


def financial_holders(doc) -> list:
	"""The posting or financial records that hold the card (empty list = none): an open card that is held is not
	edited, so the card and its accounting never diverge."""
	from card.gl.events import active_log_holding

	reasons = []
	if (
		cint(doc.get("posted"))
		or doc.get("gl_posting")
		or doc.get("purchase_invoice")
		or doc.get("sales_invoice")
	):
		reasons.append(_("it is posted or linked to an invoice"))
	for side in ("Supplier", "Customer"):
		holder = active_log_holding(DOCTYPE, doc.name, side)
		if holder:
			reasons.append(_("it is held by {0}").format(holder.posting_doc))
	links = financial_links(doc.name)
	if links:
		reasons.append(
			_("it is referenced by {0}").format(
				", ".join(f"{dt} {', '.join(sorted(names))}" for dt, names in sorted(links.items()))
			)
		)
	return reasons


def reopen_blockers(doc, today=None) -> list:
	"""Why ``doc`` cannot be reopened (empty list = it can)."""
	reasons = []
	if cint(doc.docstatus) != 1:
		reasons.append(_("the card is not submitted"))
	if doc.get("workflow_state") not in REOPENABLE_STATES:
		reasons.append(_("its state is {0}").format(_(doc.get("workflow_state") or "")))
	if month_ended(doc.year, doc.month, today):
		reasons.append(_("its month has ended"))
	return reasons + financial_holders(doc)


def _require_role(role):
	if role not in frappe.get_roles():
		frappe.throw(
			_("Only a {0} can reopen a monthly card for its open month.").format(_(role)),
			frappe.PermissionError,
		)


def _locked(name):
	"""Locking read of the stored state (the committed value, serialises reopen, edit and approval)."""
	return frappe.db.get_value(
		DOCTYPE, name, ["docstatus", "workflow_state", "modified"], as_dict=True, for_update=True
	)


# ---------- doc_events: before_update_after_submit (last CARD handler, after governance._restore) ----------
def _frozen_field_changed(doc, before):
	"""During a reopen or final approval Frappe's own allow-on-submit check is off (the state and approval fields
	are server-written there); this repeats it for every other parent field, so nothing else can change."""
	for df in doc.meta.fields:
		if (
			df.allow_on_submit
			or df.fieldtype in no_value_fields
			or df.fieldtype in table_fields
			or df.fieldname in TRANSITION_FIELDS
		):
			continue
		if _differs(df, doc.get(df.fieldname), before.get(df.fieldname)):
			return df
	return None


def before_update_after_submit(doc, method=None):
	from card import governance, intake, period_lock

	before = doc.get_doc_before_save()
	if not before:
		return
	stored = _locked(doc.name) or frappe._dict()
	stored_state = stored.get("workflow_state") or before.get("workflow_state")
	target = _transition_token().get(doc.name)
	requested = doc.get("workflow_state")
	if not _same(requested, stored_state) and requested != target:
		frappe.throw(
			_("The state of monthly card {0} changes only through its Reopen or Approve action.").format(
				doc.name
			),
			OpenMonthStateError,
		)
	if target and requested != target:
		frappe.throw(_("Invalid state change for monthly card {0}.").format(doc.name), OpenMonthStateError)
	if doc.flags.get("ignore_validate_update_after_submit") and not target:
		# only the two transitions below switch Frappe's check off
		frappe.throw(_("Invalid state change for monthly card {0}.").format(doc.name), OpenMonthStateError)

	changed = open_fields_changed(doc, before)
	is_open = stored_state == STATE_OPEN_MONTH
	if changed and (not is_open or target == STATE_OPEN_MONTH):
		frappe.throw(
			_(
				"Monthly card {0} is approved; its days, additions/deductions and location cannot be changed. Only a card in the state {1} can be edited after submit."
			).format(doc.name, _(STATE_OPEN_MONTH)),
			OpenMonthEditError,
			title=_("Cannot Update After Submit"),
		)

	if is_open and changed:
		held = financial_holders(doc)
		if held:
			frappe.throw(
				_("Monthly card {0} cannot be changed: {1}.").format(doc.name, "; ".join(held)),
				OpenMonthEditError,
				title=_("Cannot Update After Submit"),
			)
	if is_open and (changed or target == STATE_APPROVED):
		# the card's own calculation, as on a draft save; Frappe then refuses a change of any frozen field (rates,
		# equipment, project, parties, direction, period) that the calculation would bring from the equipment
		doc.before_validate()
		period_lock.enforce(doc, "save", before)
		intake.apply_card_day_intake(doc)
		# the snapshot, the editor and the registries are written after the save (on_update_after_submit)
		doc.flags.card_open_month_recomputed = True
		if changed:
			doc.flags.card_open_month_editor = frappe.session.user
	else:
		# not recomputed: a computed value sent by a client is refused, as Frappe refused it before FR-191
		for field in COMPUTED_FIELDS:
			if _differs(doc.meta.get_field(field), doc.get(field), before.get(field)):
				frappe.throw(
					_("{0} Not allowed to change {1} after submission from {2} to {3}").format(
						"", _(doc.meta.get_label(field)), before.get(field), doc.get(field)
					),
					OpenMonthEditError,
					title=_("Cannot Update After Submit"),
				)

	if target == STATE_OPEN_MONTH:
		doc.update({"approved_by": None, "approved_on": None, "self_approved": 0})
	elif target == STATE_APPROVED:
		if not is_open:
			frappe.throw(
				_("Only a card in the state {0} is approved this way.").format(_(STATE_OPEN_MONTH)),
				OpenMonthStateError,
			)
		check_card_approval_allowed(doc)
		governance._apply_resolved_tier(doc)
		# separation of duties (FR-143), approval tier (FR-159) and the approval fields, as on a submit
		governance.before_submit(doc)
	if target:
		frozen = _frozen_field_changed(doc, before)
		if frozen:
			frappe.throw(
				_("{0} Not allowed to change {1} after submission from {2} to {3}").format(
					"",
					_(frozen.label or frozen.fieldname),
					before.get(frozen.fieldname),
					doc.get(frozen.fieldname),
				),
				OpenMonthEditError,
				title=_("Cannot Update After Submit"),
			)


def on_update_after_submit(doc, method=None):
	"""After an open-month edit or the final approval: the submit-time snapshot of the rates and settings follows
	the recalculation (as ``on_submit`` writes it), an edit records its editor (separation of duties at the final
	approval) and the card's approval tier, and the party registries are refreshed. Server fields are written
	without changing ``modified``."""
	from card import governance

	if not doc.flags.get("card_open_month_recomputed"):
		return
	doc.flags.card_open_month_recomputed = None
	doc._snapshot_settings_used()
	editor = doc.flags.get("card_open_month_editor")
	if editor:
		doc.flags.card_open_month_editor = None
		editors = [line for line in cstr(doc.get("edited_by")).splitlines() if line.strip()]
		if editor not in editors:
			editors.append(editor)
			doc.db_set("edited_by", chr(10).join(editors), update_modified=False)
		tier = {f: doc.get(f) for f in governance.TIER_FIELDS}
		governance._apply_resolved_tier(doc)
		for field in governance.TIER_FIELDS:
			if doc.get(field) != tier[field]:
				doc.db_set(field, doc.get(field), update_modified=False)
	doc._sync_supplier()
	doc._sync_customer()


# ---------- actions ----------
def _reopen(doc, reason):
	before_state = doc.workflow_state
	before_approval = (doc.get("approved_by"), cstr(doc.get("approved_on")))
	_set_token(doc.name, STATE_OPEN_MONTH)
	try:
		doc.workflow_state = STATE_OPEN_MONTH
		doc.flags.ignore_version = False
		# the state and approval fields are not allow-on-submit; the guard checks every other field itself
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()
	finally:
		_clear_token(doc.name)
	doc.add_comment(
		"Info",
		_(
			"Reopened for its open month by {0} on {1}: state {2} -> {3} (approval by {4} on {5} withdrawn). Reason: {6}"
		).format(
			escape_html(frappe.session.user),
			cstr(now_datetime().replace(microsecond=0)),
			escape_html(_(before_state or "")),
			escape_html(_(STATE_OPEN_MONTH)),
			escape_html(before_approval[0] or ""),
			escape_html(before_approval[1] or ""),
			escape_html(reason),
		),
	)
	return doc


def _clean_reason(reason):
	from frappe.utils import strip_html_tags

	text = strip_html_tags(cstr(reason)).strip()
	if not text:
		frappe.throw(_("A reason is required to reopen a monthly card."))
	return text


@frappe.whitelist(methods=["POST"])
def reopen_card(name: str, reason: str):
	"""Reopen one approved card of an unfinished month on its own name (System Manager)."""
	_require_role(REOPEN_ROLE)
	text = _clean_reason(reason)
	_locked(name)
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	blockers = reopen_blockers(doc)
	if blockers:
		frappe.throw(
			_("Monthly card {0} cannot be reopened: {1}.").format(name, "; ".join(blockers)),
			ReopenRefusedError,
		)
	_reopen(doc, text)
	return {"name": doc.name, "workflow_state": doc.workflow_state}


@frappe.whitelist(methods=["POST"])
def approve_open_month_card(name: str):
	"""Final approval of an open-month card (manual only; refused before the card's month ends)."""
	from card import governance

	_locked(name)
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("submit")
	if doc.get("workflow_state") != STATE_OPEN_MONTH:
		frappe.throw(
			_("Only a card in the state {0} is approved this way.").format(_(STATE_OPEN_MONTH)),
			OpenMonthStateError,
		)
	check_card_approval_allowed(doc)
	_set_token(doc.name, STATE_APPROVED)
	try:
		doc.workflow_state = STATE_APPROVED
		doc.flags.ignore_version = False
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()
	finally:
		_clear_token(doc.name)
	# FR-163: a delegate's approval is logged as on a submit (on_submit does not run for this save)
	governance.log_delegation_use(doc)
	doc.add_comment(
		"Info",
		_("Finally approved by {0} on {1} after the end of its month.").format(
			escape_html(frappe.session.user), cstr(now_datetime().replace(microsecond=0))
		),
	)
	return {"name": doc.name, "workflow_state": doc.workflow_state}


@frappe.whitelist(methods=["POST"])
def reopen_open_month_cards(year: int, month: str, dry_run: int = 1, reason: str | None = None):
	"""Recovery (System Manager): reopen every submitted card of (year, month) on its ORIGINAL name. Never creates,
	cancels or amends a card. A card with a posting or a linked financial document is refused and reported; a card
	already open is a no-op. Each card is reopened in its own savepoint (an error rolls that card back only).
	``dry_run`` (default) returns the plan and changes nothing."""
	_require_role(REOPEN_ROLE)
	dry = cint(dry_run)
	text = None if dry else _clean_reason(reason)
	month = cstr(month).zfill(2)
	names = frappe.get_all(
		DOCTYPE,
		filters={"year": cint(year), "month": month, "docstatus": 1},
		pluck="name",
		order_by="name asc",
	)
	result = {"year": cint(year), "month": month, "dry_run": dry, "cards": [], "counts": {}}
	for name in names:
		doc = frappe.get_doc(DOCTYPE, name)
		entry = {"name": name, "state_before": doc.workflow_state}
		if doc.workflow_state == STATE_OPEN_MONTH:
			entry["action"] = "already open"
		elif not doc.has_permission("write"):
			entry.update(action="refused", reasons=[_("no write permission")])
		else:
			blockers = reopen_blockers(doc)
			if blockers:
				entry.update(action="refused", reasons=blockers)
			elif dry:
				entry["action"] = "would reopen"
			else:
				savepoint = "card_reopen_" + frappe.generate_hash(length=8)
				frappe.db.savepoint(savepoint)
				try:
					_locked(name)
					locked_doc = frappe.get_doc(DOCTYPE, name)
					# re-checked under the lock: a posting committed after the first read is seen here
					late = reopen_blockers(locked_doc)
					if late:
						frappe.db.rollback(save_point=savepoint)
						entry.update(action="refused", reasons=late)
					else:
						_reopen(locked_doc, text)
						entry["action"] = "reopened"
				except Exception as e:
					frappe.db.rollback(save_point=savepoint)
					entry.update(action="error", reasons=[cstr(e)])
		entry["state_after"] = frappe.db.get_value(DOCTYPE, name, "workflow_state")
		result["cards"].append(entry)
	for entry in result["cards"]:
		result["counts"][entry["action"]] = result["counts"].get(entry["action"], 0) + 1
	result["new_cards"] = 0
	return result


# ---------- install and patch ----------
OPEN_STATE_EDIT_ROLES = ("Card User", "Card Manager", "System Manager")


def ensure_open_month_state():
	"""Create the Workflow State "Open – month not ended" and add it as a submitted state of the CARD monthly card
	Workflow when it is missing. Idempotent; nothing that exists is changed or removed, and the Workflow's
	``is_active`` is never touched (an inactive Workflow stays inactive). No Workflow transition is added: the
	reopen and the final approval are CARD actions (``reopen_card``, ``approve_open_month_card``), because a native
	transition between two submitted states would need ``workflow_state`` to be allow-on-submit, which CARD keeps
	closed (FR-152/FR-155). With an active Workflow, Frappe refuses these two state changes (no transition), so
	activating the Workflow needs a follow-up decision for the open-month path."""
	from card.governance_workflows import WORKFLOWS

	if not frappe.db.exists("Workflow State", STATE_OPEN_MONTH):
		frappe.get_doc(
			{"doctype": "Workflow State", "workflow_state_name": STATE_OPEN_MONTH, "style": "Warning"}
		).insert()
	name = WORKFLOWS[DOCTYPE]
	if not frappe.db.exists("Workflow", name):
		return
	wf = frappe.get_doc("Workflow", name)
	changed = False
	have_states = {(s.state, s.allow_edit) for s in wf.states}
	for role in OPEN_STATE_EDIT_ROLES:
		if (STATE_OPEN_MONTH, role) not in have_states:
			wf.append("states", {"state": STATE_OPEN_MONTH, "doc_status": "1", "allow_edit": role})
			changed = True
	if changed:
		wf.save()


# ---------- reports ----------
def provisional_suffix(card) -> str:
	"""Label suffix of a submitted card that is not finally approved (its month is open): the statements show it as
	provisional, never as approved. A draft keeps its own "(Draft)" label."""
	if cint(card.get("docstatus")) == 1 and card.get("workflow_state") == STATE_OPEN_MONTH:
		return " " + _("(Provisional – month open, not approved)")
	return ""
