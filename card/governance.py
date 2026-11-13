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
amendment chain (``amended_from``: a saved card keeps its stored value, a sent change is dropped). A card saved
before FR-143 has no editor list: the user who last saved the draft (``modified_by``) is taken as its editor at
its next save or submit, and an older card of the chain counts with its creator only. The approver of an earlier card of the chain is not a
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
from frappe.utils import escape_html, getdate, now_datetime, today

from card.cancel_reason import _differs
from card.settings import company_setting

DOCTYPE = "Card Monthly Card"
RULE_FIELD = "card_approval_rule"
RULE_WARN = "Warn only (card approval)"
RULE_REFUSE = "Refuse (card approval)"

# FR-163 (WP-D5; #35 G4; closure plan C-12, owner decision O-12): CARD approval delegation.
# The delegate IS the acting user; they just inherit the delegator's authority within the
# scope / company / window of a submitted Card Approval Delegation. A delegation grants no role
# (the delegate must already hold the delegator's CARD approver roles, enforced on the delegation
# save). ``user_acting_on_behalf`` resolves the active delegation for ``(user, doctype, company)``;
# the SoD creator check (FR-143), tier role check (FR-159) and the submit comment all consult it.
DELEGATION_DOCTYPE = "Card Approval Delegation"
DELEGATION_SCOPE_ALL = "All CARD approvals"
DELEGATION_DOCTYPE_TO_SCOPE = {
	"Card Monthly Card": "Monthly Cards",
	"Equipment Transport": "Transports",
	"Project Diesel Fill": "Diesel Fills",
}

# written at the submit only (every other save clears them)
APPROVAL_FIELDS = ("submitted_by", "approved_by", "approved_on", "self_approved")
# FR-159 (WP-E): resolved tier is server-written on validate (every save, submit included),
# restored on update-after-submit and cancel; a client value is never kept.
TIER_FIELDS = ("approval_tier", "approval_tier_name")
# written by the server only; restored from the database after the submit (update after submit, cancel)
SERVER_FIELDS = (*APPROVAL_FIELDS, "edited_by", *TIER_FIELDS)

# FR-159: per-company threshold child table on Card Company Settings
TIER_TABLE_FIELD = "approval_tier_thresholds"
TIER_CHILD_DOCTYPE = "Card Approval Tier Threshold"


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
	pending = [doc.get("amended_from")]
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


# ---------- FR-163 (WP-D5): CARD approval delegation ----------
def user_acting_on_behalf(user, doctype, company, date=None):
	"""Return the delegator on whose queue ``user`` acts today for ``(doctype, company)``, or None.

	Looks up a submitted, non-cancelled ``Card Approval Delegation`` in which ``user`` is the
	``delegate_user``, ``company`` is the delegation's company, ``date`` is inside [from_date,
	to_date], and ``approval_scope`` is ``SCOPE_ALL`` or the scope matching ``doctype``. The newest
	matching delegation wins (by ``creation`` desc); a locking read (``for update``) is used so a
	parallel update to the delegation does not slip through during an in-flight submit (Lesson 4).

	Returns ``None`` when the DocType is not installed (second-migrate safety), when no delegation
	exists, or when ``user`` is Guest / unset.

	FR-121 precedent: Administrator holds every role already and is never exempt from a server
	guard; this function does NOT special-case Administrator either — if a delegation names
	Administrator as delegate, Administrator acts on behalf of its delegator too."""
	if not user or user in ("Guest", ""):
		return None
	if not frappe.db.exists("DocType", DELEGATION_DOCTYPE):
		return None
	scope = DELEGATION_DOCTYPE_TO_SCOPE.get(doctype)
	if not scope:
		return None
	date = getdate(date or today())
	rows = frappe.db.sql(
		"""
		select name, delegator_user, approval_scope
		from `tabCard Approval Delegation`
		where delegate_user = %s
		  and company = %s
		  and docstatus = 1
		  and status = 'Active'
		  and approval_scope in (%s, %s)
		  and from_date <= %s
		  and to_date >= %s
		order by creation desc
		for update
		""",
		(user, company, DELEGATION_SCOPE_ALL, scope, date, date),
		as_dict=True,
	)
	if not rows:
		return None
	return rows[0].delegator_user


def _acting_on_behalf_delegation(user, doctype, company, date=None):
	"""Variant of :func:`user_acting_on_behalf` that returns the full delegation row (name,
	delegator) when one exists, for use by the submit-time comment."""
	if not user or user in ("Guest", ""):
		return None
	if not frappe.db.exists("DocType", DELEGATION_DOCTYPE):
		return None
	scope = DELEGATION_DOCTYPE_TO_SCOPE.get(doctype)
	if not scope:
		return None
	date = getdate(date or today())
	rows = frappe.db.sql(
		"""
		select name, delegator_user
		from `tabCard Approval Delegation`
		where delegate_user = %s
		  and company = %s
		  and docstatus = 1
		  and status = 'Active'
		  and approval_scope in (%s, %s)
		  and from_date <= %s
		  and to_date >= %s
		order by creation desc
		""",
		(user, company, DELEGATION_SCOPE_ALL, scope, date, date),
		as_dict=True,
	)
	return rows[0] if rows else None


# ---------- doc_events (card/hooks.py) ----------
def on_validate(doc, method=None):
	"""validate (draft save and submit, insert with docstatus 1 included): the approval fields stay empty, the
	creator and the editors are taken from the database and the current user is recorded as an editor. FR-159
	also computes ``approval_tier`` from the company's Approval tier thresholds (server-written; a client value
	is dropped). The tier is kept in sync with the card's current net amount on every save."""
	for field in APPROVAL_FIELDS:
		doc.set(field, None)
	doc.self_approved = 0
	stored = None if doc.is_new() else _stored(doc, ("owner", "edited_by", "modified_by", "amended_from"))
	editors = []
	if stored:
		# the creator and the amended card are the stored ones: Frappe writes a sent ``owner`` or ``amended_from``
		# on an update (it checks ``amended_from`` on insert only), which would drop preparers
		doc.owner = stored.owner
		doc.amended_from = stored.amended_from
		# a card saved before FR-143: its last draft editor
		editors = _lines(stored.edited_by) or _lines(stored.modified_by)
	user = frappe.session.user
	if user not in editors and (doc.docstatus == 0 or doc.is_new() or _inputs_changed(doc)):
		editors.append(user)
	doc.edited_by = "\n".join(editors)
	_apply_resolved_tier(doc)


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
	"""The submit is the card's approval: a preparer approves only under the company's Warn rule
	(FR-143), and the submitter must hold the role required by the card's resolved approval tier
	(FR-159). The tier field is server-written on validate; this re-resolves it under a locking
	read on the company's settings row so a tier change pushed in parallel does not slip through
	(Lesson 4). Administrator is NOT exempt (FR-121 precedent).

	FR-163 (WP-D5): when the submitting user is a delegate acting on behalf of ``delegator`` for
	this doctype / company today, both the SoD creator check and the tier role check also consider
	the delegator's identity. The delegate inherits the delegator's authority within the window;
	the delegate IS the submitter (``submitted_by`` / ``approved_by`` stay the delegate), so an
	Info Comment on the card records the delegation."""
	user = frappe.session.user
	delegator = user_acting_on_behalf(user, doc.doctype, doc.get("company"))
	preparers = card_preparers(doc)
	# FR-163: both the acting user and (when acting on behalf) the delegator count as preparers
	# of the card for the SoD check — a delegate submitting the delegator's own card is still
	# a self-approval.
	self_approved = user in preparers or (delegator is not None and delegator in preparers)
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
	# FR-159 / FR-163: refuse a submit when neither the user nor the delegator holds the tier's role.
	_check_approval_tier_role(doc)
	doc.update(
		{
			"submitted_by": user,
			"approved_by": user,
			"approved_on": now_datetime(),
			"self_approved": 1 if self_approved else 0,
		}
	)
	# FR-163: flag for the post-submit log comment; Comments created in ``before_submit`` are not
	# persisted because the document itself is still unsaved — the actual comment is added from
	# ``after_submit`` / ``on_submit`` by ``log_delegation_use``.
	if delegator:
		frappe.flags.card_delegation_use = (doc.name, delegator, user)


def log_delegation_use(doc, method=None):
	"""FR-163: on_submit hook. If the submit was performed through a Card Approval Delegation
	(flag set by ``before_submit``), record an Info Comment on the approved card naming the
	delegator, the delegate and the delegation. The comment is the auditable "every use logged"
	trail required by owner decision O-12.

	Falls back to a live lookup when the flag is absent (e.g. a background submit route that
	cleared ``frappe.flags`` between ``before_submit`` and ``on_submit``)."""
	flag = frappe.flags.get("card_delegation_use") if hasattr(frappe, "flags") else None
	delegator = delegate = delegation_name = None
	if flag and flag[0] == doc.name:
		delegator, delegate = flag[1], flag[2]
		frappe.flags.card_delegation_use = None
		row = _acting_on_behalf_delegation(delegate, doc.doctype, doc.get("company"))
		delegation_name = row.name if row else ""
	else:
		user = frappe.session.user
		row = _acting_on_behalf_delegation(user, doc.doctype, doc.get("company"))
		if not row:
			return
		delegate = user
		delegator = row.delegator_user
		delegation_name = row.name
	doc.add_comment(
		"Info",
		_("Approved on behalf of {0} by {1} per delegation {2}.").format(
			escape_html(delegator), escape_html(delegate), escape_html(delegation_name or "")
		),
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


# ---------- FR-159 (WP-E; closure plan C row E; #35, #49): approval tiers ----------
"""FR-159 adds per-company net-amount thresholds that gate a monthly card's submit by role. An empty
``approval_tier_thresholds`` child table on the company's Card Company Settings row means every card is
tier 0: current behaviour, any user with Card Monthly Card write may submit. With rows, each threshold
names a ``role_required`` (an existing Role); a card whose net amount reaches the threshold is at that
tier, and the submitter must already hold that Role. The highest matching threshold wins. The row grants
no DocPerm of its own: it only names a required role, so no permission is widened.

Both the net amount and the thresholds use the company currency (O-17). The amount is the larger of the
card's absolute supplier net and absolute customer net, so a refund-shaped card (negative net) is still
gated by its size. The thresholds row is read with a locking read (``for_update``) so a tier change
pushed in parallel to an in-flight submit does not slip through (Lesson 4).

The guard runs in ``before_submit`` so every submit route goes through it: form Submit, REST v1/v2
insert with docstatus 1, REST PUT docstatus 1, ``frappe.client.submit``, savedocs Submit, bulk submit
and ``bulk_workflow_approval``. Administrator is NOT exempt (FR-121 precedent); the Workflow approve
transition composed by FR-152 reads the same tier through ``user_holds_approval_tier_role`` (see
``card.governance_workflows``) so the Approve action is also gated once the Workflow is activated
(W-16)."""


class ApprovalTierMissingRoleError(frappe.PermissionError):
	"""Raised when a user who does not hold the card's resolved tier role tries to submit (FR-159)."""

	pass


def _card_net_amount(doc):
	"""The card's resolved net amount for tier matching: the larger of the absolute supplier net
	(``net_amount``) and absolute customer net (``customer_net_amount``). A draft that has not run
	the card controller yet (test harness, bulk insert) falls back to the stored values."""
	from frappe.utils import flt

	supplier = flt(doc.get("net_amount"))
	customer = flt(doc.get("customer_net_amount"))
	return max(abs(supplier), abs(customer))


def _company_tier_rows(company):
	"""Read the company's threshold rows with a locking read on the settings child table, sorted by
	amount_threshold descending (highest first). Returns an empty list when the company has no row,
	no thresholds or the child DocType is not installed yet (second-migrate safety). Lesson 4: the
	``for_update`` locks the committed rows so a parallel edit cannot change tier for an in-flight
	submit."""
	if not company:
		return []
	if not frappe.db.exists("DocType", TIER_CHILD_DOCTYPE):
		return []
	rows = frappe.db.sql(
		"""
		select tier_name, amount_threshold, role_required
		from `tabCard Approval Tier Threshold`
		where parenttype = %s and parentfield = %s and parent = %s and company = %s
		order by amount_threshold desc, idx asc
		for update
		""",
		("Card Settings", TIER_TABLE_FIELD, "Card Settings", company),
		as_dict=True,
	)
	# drop rows missing a role (defensive; required= on the JSON refuses them at save time)
	return [
		r for r in rows if (r.get("role_required") or "").strip() and r.get("amount_threshold") is not None
	]


def resolve_approval_tier(doc):
	"""The highest matching tier for ``doc`` (dict with ``tier_index``, ``tier_name``,
	``amount_threshold``, ``role_required``), or None when no threshold matches. Tier 1 is the lowest
	threshold, tier N the highest; a card under every threshold is tier 0 (None here). The read is
	locking (``for_update``) so concurrent settings edits do not change the tier of an in-flight
	submit (Lesson 4)."""
	from frappe.utils import flt

	rows = _company_tier_rows(doc.get("company"))
	if not rows:
		return None
	net = _card_net_amount(doc)
	# rows are sorted amount_threshold desc; the first one the net reaches wins
	for position, row in enumerate(rows):
		if net >= flt(row.amount_threshold):
			# tier_index: 1 = lowest threshold (last in the sorted desc list), N = highest (first)
			tier_index = len(rows) - position
			return {
				"tier_index": tier_index,
				"tier_name": row.tier_name or "",
				"amount_threshold": flt(row.amount_threshold),
				"role_required": row.role_required,
			}
	return None


def _apply_resolved_tier(doc):
	"""Server-write ``approval_tier`` / ``approval_tier_name`` on validate from the live net amount
	and the company's thresholds. A client value is dropped. Called from ``on_validate`` only."""
	tier = resolve_approval_tier(doc)
	if tier:
		doc.set("approval_tier", int(tier["tier_index"]))
		doc.set("approval_tier_name", tier["tier_name"])
	else:
		doc.set("approval_tier", 0)
		doc.set("approval_tier_name", None)


def user_holds_approval_tier_role(doc, user=None):
	"""True when ``user`` (the current session user by default) may submit ``doc`` at its resolved
	tier: tier 0 (no threshold matched, or no rows) always passes; otherwise the user must hold the
	tier's ``role_required`` role, OR a delegator the user acts on behalf of holds it (FR-163).
	Exposed for the Workflow approve-transition condition (FR-152; see ``card.governance_workflows``)
	through ``frappe.get_attr``; also used by the server guard."""
	user = user or frappe.session.user
	tier = resolve_approval_tier(doc)
	if not tier:
		return True
	role = tier["role_required"]
	if role in set(frappe.get_roles(user)):
		return True
	delegator = user_acting_on_behalf(user, doc.get("doctype") or DOCTYPE, doc.get("company"))
	if delegator and role in set(frappe.get_roles(delegator)):
		return True
	return False


def _check_approval_tier_role(doc):
	"""FR-159: refuse a submit when the running user does not hold the tier's ``role_required``.
	Administrator is NOT exempt (FR-121 precedent). Called from ``before_submit`` only; the tier is
	re-resolved here under the locking read so a forged client value is ignored.

	FR-163 (WP-D5): when the user acts on behalf of a delegator (an active Card Approval
	Delegation for the user / doctype / company today), the tier check passes if EITHER the user
	or the delegator holds ``role_required``. The delegation itself stays without role grants:
	the delegate's DocPerm is unchanged, only the server-side tier gate consults the delegator.
	Discovered through ``user_acting_on_behalf`` so the existing single-argument signature is
	kept — test mocks ``lambda doc: None`` still work."""
	tier = resolve_approval_tier(doc)
	if not tier:
		return
	user = frappe.session.user
	role = tier["role_required"]
	if role in set(frappe.get_roles(user)):
		return
	delegator = user_acting_on_behalf(user, doc.doctype, doc.get("company"))
	if delegator and role in set(frappe.get_roles(delegator)):
		return
	frappe.throw(
		_(
			"{0} needs the role {1} to submit this monthly card (approval tier {2}: net amount at or above {3}, company rule)."
		).format(
			user,
			role,
			tier["tier_name"] or tier["tier_index"],
			tier["amount_threshold"],
		),
		ApprovalTierMissingRoleError,
		title=_("Monthly card approval tier"),
	)


# ---------- FR-155 (WP-D2b; closure plan C-14, O-10): native-workflow state guards ----------
"""FR-155 extends FR-152 (``card.governance_workflows``) with the state-edit guard that Frappe enforces in the form
only. When an active Workflow is attached to a CARD transaction (Card Monthly Card, Equipment Transport, Project
Diesel Fill), a save by any route (form, REST v1/v2 ``update`` and ``insert``, ``frappe.client.set_value`` /
``save`` / ``submit`` / ``insert``, ``savedocs``, ``bulk_update``) is accepted only when the current user holds a
role listed in the stored state's ``allow_edit`` (Workflow Document State) or is making a declared state transition
(which Frappe's ``validate_workflow`` and FR-152's ``_check_submit`` already check). Administrator is NOT exempt
(FR-121 precedent). Inactive Workflow (the default, O-10): no change. The companion bypass suite
(``card/tests/test_workflow_bypass.py``) proves that no route can forge ``workflow_state``, ``return_reason`` or
the approver fields, skip a transition, or reach another company's queue."""


class WorkflowStateEditError(frappe.PermissionError):
	pass


def _stored_state(doctype, name, state_field):
	"""Locking read of the stored ``workflow_state`` and ``docstatus``; the committed values, not the request's
	snapshot. Returns (state, docstatus) or (None, None) when the record is gone."""
	row = frappe.db.get_value(doctype, name, (state_field, "docstatus"), as_dict=True, for_update=True)
	if not row:
		return None, None
	return row.get(state_field), row.get("docstatus")


def _state_edit_roles(workflow, state):
	"""Every role listed in ``allow_edit`` for ``state`` (one state has one row per role in Frappe)."""
	return {s.allow_edit for s in workflow.states if s.state == state and s.allow_edit}


def check_workflow_state_edit(doc, method=None):
	"""FR-155: state-edit guard on every save. Runs after ``card.cancel_reason.on_validate`` (which calls
	``governance_workflows.on_validate``): when an active Workflow is attached, the saving user must hold a role
	in the stored state's ``allow_edit``. A state transition (``doc`` state != stored state) is left to Frappe's
	``validate_workflow`` and FR-152's ``_check_submit``; a plain draft save, an update of a draft and an update
	after submit all run through here. Administrator is NOT exempt."""
	from card import governance_workflows as _gw

	if doc.doctype not in _gw.WORKFLOWS:
		return
	workflow = _gw._active_workflow(doc.doctype)
	if not workflow:
		return
	state_field = workflow.workflow_state_field
	if doc.is_new():
		stored_state = _gw._default_state(workflow, 0)
		if stored_state is None:
			return
	else:
		stored_state, stored_docstatus = _stored_state(doc.doctype, doc.name, state_field)
		if stored_state is None:
			stored_state = _gw._default_state(workflow, stored_docstatus or 0)
		if stored_state is None:
			return
	current_state = doc.get(state_field) or stored_state
	if current_state != stored_state:
		# transition: Frappe's validate_workflow checks who may transition; D2a's _check_submit handles docstatus 1
		return
	allow_edit = _state_edit_roles(workflow, stored_state)
	if not allow_edit:
		return
	user_roles = set(frappe.get_roles(frappe.session.user))
	if not (allow_edit & user_roles):
		frappe.throw(
			_("{0} {1} is in state {2}; editing requires one of these roles: {3}.").format(
				_(doc.doctype),
				doc.name or _("(new)"),
				_(stored_state),
				", ".join(sorted(allow_edit)),
			),
			WorkflowStateEditError,
			title=_("Workflow state edit refused"),
		)
