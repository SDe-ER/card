# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-152 (WP-D2a; #35 G1, #51, #123; closure plan C-14, owner decision O-10): native Frappe approval Workflows
for Card Monthly Card, Equipment Transport and Project Diesel Fill, created INACTIVE.

What is shipped (standard records only, no Frappe core change):

- one Workflow per DocType (``WORKFLOWS``), state field ``workflow_state`` (a standard field of the three DocTypes),
  created by install and by the v4.8.0 patch only when missing and always with ``is_active`` = 0. An existing
  Workflow of that name is never changed: the owner may have edited it. Activating a Workflow is an owner setup
  action on the site (closure plan W-16), not code.
- states and their docstatus: Draft (0) -> Pending Review (0, optional) -> Approved (1); "Approved – before
  governance" (1, records approved before the workflow; no transition leads to it) and Cancelled (2, set by the
  CARD cancel; no transition leads to it, so the form keeps its standard Cancel, which asks for the FR-123 reason).
  Per-state edit (``allow_edit``) uses the existing roles only: Draft = Card User, Card Manager, System Manager;
  Pending Review = Card Manager, System Manager; the submitted and cancelled states = Card Manager. No role or
  DocPerm is added.
- transitions: "Send for Review" (Draft -> Pending Review: Card User, Card Manager), "Approve" (Pending Review ->
  Approved, and Draft -> Approved while the company does not require the review: Card Manager), "Return for
  Correction" (Pending Review -> Draft: Card Manager, with a mandatory reason).

Review toggle: Card Company Settings ``card_review_required`` (default 0) makes the review step mandatory for the
company. The field is added to Card Company Settings by a later package (after WP-S2 merges, or WP-D2b); until then
it does not exist and the review is optional for every company (``review_required`` reads 0 when the field is
missing, also in the Workflow condition, which reads the whole settings row).

Server guards (minimal; the full state-guard bypass suite is WP-D2b in ``card/governance.py``). They run from the
FR-123 doc_events entry points of ``card/cancel_reason.py`` that are already registered for the three DocTypes, so
``card/hooks.py`` gets no new doc_events:

- workflow inactive (the default): the behaviour is unchanged. The server only keeps the hidden ``workflow_state``
  in line with the docstatus (stored state when it fits, else Draft / "Approved – before governance" /
  Cancelled), so a later activation starts from consistent states; a value sent by the client is never kept.
- workflow active: a submit is accepted only as a workflow transition from the stored state to a submitted state
  that the user holds (``frappe.model.workflow.get_transitions``); a direct submit (form Submit, REST insert with
  docstatus 1, ``frappe.client.submit``, REST PUT docstatus 1 without a transition, bulk submit) is refused, and so
  is an approval from Draft when the company requires the review. A return to the first state needs the reason of
  ``return_for_correction`` (no other route can give it). A cancel is accepted only from
  ``card.cancel_reason.cancel_with_reason`` (the form's Cancel): a Workflow cancel action (``apply_workflow`` ->
  ``doc.cancel``), possibly with a state ``update_field`` that fills ``cancel_reason``, a REST cancel and a bulk
  cancel are refused, so FR-123 cannot be bypassed.
- ``return_reason`` is written by the server only (the stored value is kept on every save).

The approval queues are company-scoped: the Workflow Action rows of these DocTypes follow the read permission of
their document (``workflow_action_query_conditions``, ``has_workflow_action_permission``), so a user limited to
company A never sees the queue entries of company B."""

import frappe
from frappe import _
from frappe.model.workflow import get_transitions, get_workflow_name
from frappe.utils import cint, cstr, escape_html, strip_html_tags

from card.settings import company_setting

STATE_FIELD = "workflow_state"
RETURN_REASON_FIELD = "return_reason"
REVIEW_FIELD = "card_review_required"
COMPANY_SETTINGS = "Card Company Settings"

STATE_DRAFT = "Draft"
STATE_PENDING = "Pending Review"
STATE_APPROVED = "Approved"
STATE_BEFORE_GOVERNANCE = "Approved – before governance"
STATE_CANCELLED = "Cancelled"

ACTION_SEND = "Send for Review"
ACTION_APPROVE = "Approve"
ACTION_RETURN = "Return for Correction"

WORKFLOWS = {
	"Card Monthly Card": "CARD Monthly Card Approval",
	"Equipment Transport": "CARD Equipment Transport Approval",
	"Project Diesel Fill": "CARD Project Diesel Fill Approval",
}

# style of a Workflow State created here (an existing Workflow State record is never changed)
STATE_STYLES = {
	STATE_DRAFT: "",
	STATE_PENDING: "Warning",
	STATE_APPROVED: "Success",
	STATE_BEFORE_GOVERNANCE: "Info",
	STATE_CANCELLED: "Danger",
}

# the first state of each docstatus is the default Frappe gives a record with an empty state
# (Workflow.update_default_workflow_status): "Approved – before governance" comes before "Approved"
STATES = (
	(STATE_DRAFT, 0, ("Card User", "Card Manager", "System Manager")),
	(STATE_PENDING, 0, ("Card Manager", "System Manager")),
	(STATE_BEFORE_GOVERNANCE, 1, ("Card Manager",)),
	(STATE_APPROVED, 1, ("Card Manager",)),
	(STATE_CANCELLED, 2, ("Card Manager",)),
)

# the Draft -> Approved transition is offered only while the company does not require the review; the whole
# settings row is read ("*"), so the condition works before the ``card_review_required`` field exists
REVIEW_OFF_CONDITION = (
	'not (frappe.db.get_value("Card Company Settings", {"parent": "Card Settings", "parentfield": '
	'"company_settings", "company": doc.company}, "*", as_dict=True) or {}).get("card_review_required")'
)


def transitions(doctype):
	"""(state, action, next state, role, allow self approval, condition). The monthly card's approval leaves
	self-approval to FR-143 (``card.governance``, per-company Warn/Refuse rule); the transport and the diesel fill
	keep Frappe's native rule (the creator cannot approve)."""
	self_approval = 1 if doctype == "Card Monthly Card" else 0
	return (
		(STATE_DRAFT, ACTION_SEND, STATE_PENDING, "Card User", 1, None),
		(STATE_DRAFT, ACTION_SEND, STATE_PENDING, "Card Manager", 1, None),
		(STATE_DRAFT, ACTION_APPROVE, STATE_APPROVED, "Card Manager", self_approval, REVIEW_OFF_CONDITION),
		(STATE_PENDING, ACTION_APPROVE, STATE_APPROVED, "Card Manager", self_approval, None),
		(STATE_PENDING, ACTION_RETURN, STATE_DRAFT, "Card Manager", 1, None),
	)


class WorkflowSubmitError(frappe.ValidationError):
	pass


class ReturnReasonRequiredError(frappe.ValidationError):
	pass


class WorkflowCancelRouteError(frappe.ValidationError):
	pass


# ---------- install and patch ----------
def ensure_workflows():
	"""Create the Workflow States, Workflow Action Masters and the three Workflows when missing; a new Workflow is
	always inactive. Idempotent; an existing record is never changed."""
	for state, style in STATE_STYLES.items():
		if not frappe.db.exists("Workflow State", state):
			frappe.get_doc(
				{"doctype": "Workflow State", "workflow_state_name": state, "style": style}
			).insert()
	for action in (ACTION_SEND, ACTION_APPROVE, ACTION_RETURN):
		if not frappe.db.exists("Workflow Action Master", action):
			frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}).insert()
	for doctype, name in WORKFLOWS.items():
		if frappe.db.exists("Workflow", name):
			continue
		wf = frappe.new_doc("Workflow")
		wf.update(
			{
				"workflow_name": name,
				"document_type": doctype,
				"workflow_state_field": STATE_FIELD,
				"is_active": 0,
				"send_email_alert": 0,
				"override_status": 0,
			}
		)
		for state, docstatus, roles in STATES:
			for role in roles:
				wf.append("states", {"state": state, "doc_status": str(docstatus), "allow_edit": role})
		for state, action, next_state, role, self_approval, condition in transitions(doctype):
			wf.append(
				"transitions",
				{
					"state": state,
					"action": action,
					"next_state": next_state,
					"allowed": role,
					"allow_self_approval": self_approval,
					"condition": condition,
				},
			)
		wf.insert()


def remove_duplicate_state_custom_fields():
	"""A Workflow saved earlier on a site may have created a Custom Field ``workflow_state`` on these DocTypes;
	the DocTypes now carry it as a standard field. Deleting the Custom Field keeps the column and its values."""
	for doctype in WORKFLOWS:
		name = frappe.db.get_value("Custom Field", {"dt": doctype, "fieldname": STATE_FIELD}, "name")
		if name:
			frappe.delete_doc("Custom Field", name)
			frappe.clear_cache(doctype=doctype)


def backfill_states():
	"""Set ``workflow_state`` on existing records from their docstatus, without touching docstatus or
	``modified``: drafts -> Draft, submitted -> "Approved – before governance", cancelled -> Cancelled. A record
	that already holds a state of its Workflow with the same docstatus keeps it, so a second run changes nothing."""
	for doctype in WORKFLOWS:
		if not frappe.db.has_column(doctype, STATE_FIELD):
			continue
		workflow = _card_workflow(doctype)
		if not workflow:
			continue
		table = frappe.qb.DocType(doctype)
		field = table[STATE_FIELD]
		for docstatus in (0, 1, 2):
			valid = [s.state for s in workflow.states if cint(s.doc_status) == docstatus]
			default = _default_state(workflow, docstatus)
			if not default:
				continue
			(
				frappe.qb.update(table)
				.set(field, default)
				.where(table.docstatus == docstatus)
				.where(field.isnull() | (field == "") | field.notin(valid))
			).run()


# ---------- reading the workflow ----------
def _card_workflow(doctype):
	name = WORKFLOWS.get(doctype)
	if not name or not frappe.db.exists("Workflow", name):
		return None
	return frappe.get_cached_doc("Workflow", name)


def _active_workflow(doctype):
	"""The active Workflow of the DocType (the CARD one or another the owner activated), or None."""
	name = get_workflow_name(doctype)
	return frappe.get_cached_doc("Workflow", name) if name else None


def _default_state(workflow, docstatus):
	return next((s.state for s in workflow.states if cint(s.doc_status) == docstatus), None)


def _state_docstatus(workflow, state):
	return next((cint(s.doc_status) for s in workflow.states if s.state == state), None)


def review_required(company):
	"""The company requires the review step (Card Company Settings ``card_review_required``). 0 when the company
	has no row, the value is empty or the field does not exist yet (it is added by a later package)."""
	if not company or not frappe.get_meta(COMPANY_SETTINGS).has_field(REVIEW_FIELD):
		return False
	return bool(cint(company_setting(company, REVIEW_FIELD)))


# ---------- doc_events (called from card.cancel_reason, registered in card/hooks.py) ----------
def on_validate(doc, method=None):
	"""validate (save and submit, insert with docstatus 1 included)."""
	if doc.doctype not in WORKFLOWS or not doc.meta.has_field(STATE_FIELD):
		return
	before = None if doc.is_new() else doc.get_doc_before_save()
	# server-written: the stored value on every save; only a return for correction writes it
	doc.set(RETURN_REASON_FIELD, before.get(RETURN_REASON_FIELD) if before else None)
	workflow = _active_workflow(doc.doctype)
	if workflow:
		_check_active(doc, before, workflow)
	else:
		_keep_state_in_line(doc, before)


def _keep_state_in_line(doc, before):
	"""Workflow inactive: the stored state when it fits the docstatus, else the default state of the docstatus
	(the client's value is never read)."""
	workflow = _card_workflow(doc.doctype)
	if not workflow:
		return
	stored = before.get(STATE_FIELD) if before else None
	if stored and _state_docstatus(workflow, stored) == cint(doc.docstatus):
		doc.set(STATE_FIELD, stored)
	else:
		doc.set(STATE_FIELD, _default_state(workflow, cint(doc.docstatus)))


def _check_active(doc, before, workflow):
	field = workflow.workflow_state_field
	state = doc.get(field)
	stored = before.get(field) if before else None
	if cint(doc.docstatus) == 1:
		_check_submit(doc, before, workflow, stored, state)
	elif before and cint(before.docstatus) == 0 and stored and state != stored:
		first = workflow.states[0].state
		if state == first:
			reason = _pending_return_reason(doc)
			if not reason:
				frappe.throw(
					_("A reason is required to return {0} {1} for correction.").format(
						_(doc.doctype), doc.name
					),
					ReturnReasonRequiredError,
				)
			doc.set(RETURN_REASON_FIELD, reason)


def _check_submit(doc, before, workflow, stored, state):
	"""A submit with an active Workflow is only a transition the user holds, from the stored state."""
	message = _("{0} {1} is approved through its workflow action, not by a direct submit.").format(
		_(doc.doctype), doc.name or ""
	)
	if not before or cint(before.docstatus) != 0 or not state or state == stored:
		frappe.throw(message, WorkflowSubmitError)
	if _state_docstatus(workflow, state) != 1:
		frappe.throw(message, WorkflowSubmitError)
	allowed = [t for t in get_transitions(before, workflow) if t.next_state == state]
	if not allowed:
		frappe.throw(message, WorkflowSubmitError)
	if stored == workflow.states[0].state and review_required(doc.company):
		frappe.throw(
			_("Company {0} requires the review: send {1} {2} for review before approving it.").format(
				doc.company, _(doc.doctype), doc.name
			),
			WorkflowSubmitError,
		)


def check_cancel_route(doc):
	"""before_cancel (first): with an active Workflow a cancel is accepted only from ``cancel_with_reason``."""
	if doc.doctype not in WORKFLOWS or not get_workflow_name(doc.doctype):
		return
	if not doc.flags.get("card_cancel_with_reason"):
		frappe.throw(
			_(
				"{0} {1} is cancelled only with the Cancel button of its form, which asks for the reason."
			).format(_(doc.doctype), doc.name),
			WorkflowCancelRouteError,
		)


def set_cancelled_state(doc):
	"""before_cancel (last, after the FR-123 comparison): the state follows the cancel, set by the server."""
	if doc.doctype not in WORKFLOWS or not doc.meta.has_field(STATE_FIELD):
		return
	workflow = _active_workflow(doc.doctype) or _card_workflow(doc.doctype)
	if not workflow:
		return
	cancelled = _default_state(workflow, 2)
	if cancelled:
		doc.set(workflow.workflow_state_field, cancelled)


# ---------- return for correction ----------
def _clean(text):
	return strip_html_tags(cstr(text)).replace("<", "").replace(">", "").strip()


def _pending_return_reason(doc):
	return (frappe.flags.get("card_return_reasons") or {}).get((doc.doctype, doc.name))


@frappe.whitelist(methods=["POST"])
def return_for_correction(doctype: str, name: str, reason: str | None = None):
	"""The form's "Return for Correction": apply the Workflow action with its mandatory reason in one request.
	Frappe's ``apply_workflow`` checks the transition, the role and the document permission."""
	from frappe.model.workflow import apply_workflow

	if doctype not in WORKFLOWS:
		frappe.throw(_("{0} is not a CARD transaction.").format(doctype), frappe.PermissionError)
	text = _clean(reason)
	if not text:
		frappe.throw(
			_("A reason is required to return {0} {1} for correction.").format(_(doctype), name),
			ReturnReasonRequiredError,
		)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("write")
	reasons = frappe.flags.get("card_return_reasons") or {}
	reasons[(doctype, doc.name)] = text
	frappe.flags.card_return_reasons = reasons
	try:
		doc = apply_workflow(doc, ACTION_RETURN)
	finally:
		reasons.pop((doctype, name), None)
	doc.add_comment(
		"Info",
		_("Returned for correction by {0}. Reason: {1}").format(
			escape_html(frappe.session.user), escape_html(text)
		),
	)
	return {"name": doc.name, STATE_FIELD: doc.get(STATE_FIELD)}


# ---------- company-scoped approval queues (Workflow Action) ----------
def workflow_action_query_conditions(user=None, doctype=None):
	"""Workflow Action list: a row of a CARD DocType is listed only when its document's company is permitted to
	the user for that DocType (Company User Permissions, as the CARD lists use)."""
	from card.party_registry import _restricted_companies

	user = user or frappe.session.user
	restricted, allowed = [], []
	for dt in WORKFLOWS:
		companies = _restricted_companies(user, dt)
		if companies is None:
			continue
		restricted.append(frappe.db.escape(dt))
		if companies:
			values = ", ".join(frappe.db.escape(c) for c in companies)
			allowed.append(
				f"(`tabWorkflow Action`.`reference_doctype` = {frappe.db.escape(dt)} and "
				f"`tabWorkflow Action`.`reference_name` in (select `name` from `tab{dt}` where `company` in ({values})))"
			)
	if not restricted:
		return ""
	return (
		"("
		+ " or ".join(
			[f"`tabWorkflow Action`.`reference_doctype` not in ({', '.join(restricted)})", *allowed]
		)
		+ ")"
	)


def has_workflow_action_permission(doc, ptype=None, user=None, debug=False):
	"""A Workflow Action of a CARD DocType needs the read permission of its document (company isolation)."""
	if doc.get("reference_doctype") not in WORKFLOWS or not doc.get("reference_name"):
		return True
	if not frappe.db.exists(doc.reference_doctype, doc.reference_name):
		return True
	return bool(frappe.has_permission(doc.reference_doctype, "read", doc=doc.reference_name, user=user))
