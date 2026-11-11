# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-152 (WP-D2a; #35 G1, #51, #123; C-14): native approval Workflows for Card Monthly Card, Equipment Transport
and Project Diesel Fill, created inactive.

Proven here: install/patch create the records inactive and idempotently (a second migrate changes nothing, an
owner's edit is kept, a duplicate Custom Field is removed with its values kept); the state backfill from the
docstatus; inactive = today's behaviour (direct submit, REST cancel, the state kept in line by the server, a client
state never kept); with a Workflow activated inside the test: transitions, the mandatory return reason, no direct
submit on any route, the review toggle, the cancel route (a Workflow cancel action cannot bypass FR-123, even with a
state ``update_field`` that fills the reason), FR-143 on the approve transition, the company-scoped approval queue
and the Connections data. All data is per-test and rolled back; the Workflow cache is cleared after every test."""

import json
from unittest.mock import patch

import frappe
import frappe.client
from frappe.desk.form.save import savedocs
from frappe.model.workflow import apply_workflow, get_workflow_name, is_transition_condition_satisfied
from frappe.tests import IntegrationTestCase
from frappe.utils import cint

from card import cancel_reason, governance, governance_workflows
from card.cancel_reason import cancel_with_reason
from card.governance_workflows import (
	ACTION_APPROVE,
	ACTION_RETURN,
	ACTION_SEND,
	STATE_APPROVED,
	STATE_BEFORE_GOVERNANCE,
	STATE_CANCELLED,
	STATE_DRAFT,
	STATE_PENDING,
	WORKFLOWS,
	ReturnReasonRequiredError,
	WorkflowCancelRouteError,
	WorkflowSubmitError,
	return_for_correction,
)
from card.patches.v4_8_0 import native_workflows_inactive
from card.tests import test_period_lock, test_period_lock_extra_keys
from card.tests.diesel_price import approve_fill

MID_MONTH = test_period_lock_extra_keys.MID_MONTH
REASON = "Hours of day 2 are wrong"
SETTINGS = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "company_settings"}
EXISTING_ROLES = {"Card User", "Card Manager", "System Manager"}


class TestNativeWorkflows(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = test_period_lock._ensure_masters()

	_base = test_period_lock_extra_keys.TestPeriodLockExtraKeys
	_set = _base._set
	_make_equipment = _base._make_equipment
	_new_card = _base._new_card
	_equip = _base._equip
	_lock = _base._lock
	_unlock = _base._unlock
	_settings = _base._settings
	_fill = _base._fill
	_transport = _base._transport
	_today = _base._today
	_month_days = _base._month_days
	_current_card = _base._current_card

	def setUp(self):
		self.enterContext(self.freeze_time(MID_MONTH))
		test_period_lock.TestPeriodLockAndSnapshot.setUp(self)
		self._unlock()
		self.preparer = self._user("prep", ("Card User",))
		self.manager = self._user("mgr", ("Card Manager",))
		self.manager2 = self._user("mgr2", ("Card Manager",))
		self.sysmanager = self._user("sys", ("System Manager",))

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags.card_return_reasons = None
		frappe.local.response = frappe._dict(docs=[])
		try:
			frappe.db.rollback()
		finally:
			self._clear_workflow_cache()

	@staticmethod
	def _clear_workflow_cache():
		frappe.cache.delete_key("workflow")
		for doctype, name in WORKFLOWS.items():
			frappe.clear_document_cache("Workflow", name)
			frappe.clear_cache(doctype=doctype)

	# ---------- builders ----------
	def _user(self, prefix, roles, company=None):
		email = f"wf-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "WF " + prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if company:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": company,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _new(self, doctype):
		return {
			"Card Monthly Card": self._current_card,
			"Equipment Transport": lambda: self._transport(self._today()),
			"Project Diesel Fill": lambda: self._fill(self._today()),
		}[doctype]()

	def _draft(self, doctype):
		doc = self._new(doctype)
		doc.insert(ignore_permissions=True)
		if doctype == "Project Diesel Fill":
			approve_fill(doc)
		return frappe.get_doc(doctype, doc.name)

	def _activate(self, doctype):
		wf = frappe.get_doc("Workflow", WORKFLOWS[doctype])
		wf.is_active = 1
		wf.save()
		self._clear_workflow_cache()
		self.assertEqual(get_workflow_name(doctype), WORKFLOWS[doctype])
		return wf

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _refused(self, error, fn, *args, **kwargs):
		frappe.db.savepoint("native_wf")
		try:
			with self.assertRaises(error):
				fn(*args, **kwargs)
		finally:
			frappe.db.rollback(save_point="native_wf")
			frappe.set_user("Administrator")

	def _stored(self, doc, *fields):
		return frappe.db.get_value(
			doc.doctype, doc.name, ["docstatus", "workflow_state", *fields], as_dict=True
		)

	def _approve(self, doc, user=None):
		return self._as(
			user or self.manager, apply_workflow, frappe.get_doc(doc.doctype, doc.name), ACTION_APPROVE
		)

	# ---------- install and patch ----------
	def test_workflows_exist_and_are_inactive(self):
		for doctype, name in WORKFLOWS.items():
			with self.subTest(doctype=doctype):
				wf = frappe.get_doc("Workflow", name)
				self.assertEqual(
					(wf.document_type, wf.is_active, wf.workflow_state_field), (doctype, 0, "workflow_state")
				)
				self.assertEqual(wf.send_email_alert, 0)
				self.assertFalse(get_workflow_name(doctype))
				self.assertFalse(frappe.get_meta(doctype).get_workflow())
				self.assertEqual(wf.states[0].state, STATE_DRAFT)
				docstatus = {s.state: int(s.doc_status) for s in wf.states}
				self.assertEqual(
					docstatus,
					{
						STATE_DRAFT: 0,
						STATE_PENDING: 0,
						STATE_BEFORE_GOVERNANCE: 1,
						STATE_APPROVED: 1,
						STATE_CANCELLED: 2,
					},
				)
				# Frappe's default for an empty submitted record is the first submitted state
				self.assertEqual(
					next(s.state for s in wf.states if s.doc_status == "1"), STATE_BEFORE_GOVERNANCE
				)
				# existing roles only; no transition leads to the cancelled or the "before governance" state
				self.assertLessEqual({s.allow_edit for s in wf.states}, EXISTING_ROLES)
				self.assertLessEqual({t.allowed for t in wf.transitions}, EXISTING_ROLES)
				self.assertFalse(
					{t.next_state for t in wf.transitions} & {STATE_CANCELLED, STATE_BEFORE_GOVERNANCE}
				)
				self.assertEqual(
					{(t.state, t.action, t.next_state) for t in wf.transitions},
					{
						(STATE_DRAFT, ACTION_SEND, STATE_PENDING),
						(STATE_DRAFT, ACTION_APPROVE, STATE_APPROVED),
						(STATE_PENDING, ACTION_APPROVE, STATE_APPROVED),
						(STATE_PENDING, ACTION_RETURN, STATE_DRAFT),
					},
				)
				# no role or DocPerm was added
				self.assertEqual(
					{p.role for p in frappe.get_meta(doctype).permissions},
					{"System Manager", "Card Manager", "Card User", "Accounts Manager"},
				)
				df = frappe.get_meta(doctype).get_field("workflow_state")
				self.assertEqual(
					(df.fieldtype, df.options, df.no_copy, df.allow_on_submit),
					("Link", "Workflow State", 1, 0),
				)
				df = frappe.get_meta(doctype).get_field("return_reason")
				self.assertEqual((df.read_only, df.no_copy, df.allow_on_submit), (1, 1, 0))
		for state in (STATE_DRAFT, STATE_PENDING, STATE_APPROVED, STATE_BEFORE_GOVERNANCE, STATE_CANCELLED):
			self.assertTrue(frappe.db.exists("Workflow State", state))
		for action in (ACTION_SEND, ACTION_APPROVE, ACTION_RETURN):
			self.assertTrue(frappe.db.exists("Workflow Action Master", action))

	def test_ensure_is_idempotent_and_keeps_existing_records(self):
		name = WORKFLOWS["Equipment Transport"]
		frappe.db.set_value("Workflow", name, "send_email_alert", 1)  # an owner's edit
		governance_workflows.ensure_workflows()
		governance_workflows.ensure_workflows()
		self.assertEqual(frappe.db.count("Workflow", {"name": ("in", list(WORKFLOWS.values()))}), 3)
		self.assertEqual(frappe.db.get_value("Workflow", name, "send_email_alert"), 1)
		# an owner-activated Workflow is not deactivated by a later migrate
		frappe.db.set_value("Workflow", name, "is_active", 1)
		native_workflows_inactive.execute()
		self.assertEqual(frappe.db.get_value("Workflow", name, "is_active"), 1)
		# a deleted Workflow is created again, inactive
		frappe.delete_doc("Workflow", WORKFLOWS["Project Diesel Fill"])
		native_workflows_inactive.execute()
		self.assertEqual(frappe.db.get_value("Workflow", WORKFLOWS["Project Diesel Fill"], "is_active"), 0)

	def test_after_install_creates_the_workflows(self):
		from card import install

		with (
			patch.object(install, "_reconcile"),
			patch.object(frappe.db, "commit"),
			patch("card.governance_workflows.ensure_workflows") as ensure,
		):
			install.after_install()
		ensure.assert_called_once_with()

	def test_patch_backfills_states_from_docstatus_and_is_idempotent(self):
		docs = []
		for doctype in WORKFLOWS:
			draft = self._draft(doctype)
			submitted = self._draft(doctype)
			submitted.submit()
			cancelled = self._draft(doctype)
			cancelled.submit()
			cancel_with_reason(doctype, cancelled.name, REASON)
			wrong = self._draft(doctype)  # a draft with a submitted state (an older workflow's value)
			docs += [
				(draft, 0, STATE_DRAFT),
				(submitted, 1, STATE_BEFORE_GOVERNANCE),
				(cancelled, 2, STATE_CANCELLED),
			]
			docs.append((wrong, 0, STATE_DRAFT))
			table = frappe.qb.DocType(doctype)
			for doc in (draft, submitted, cancelled):
				frappe.qb.update(table).set(table.workflow_state, None).where(table.name == doc.name).run()
			frappe.qb.update(table).set(table.workflow_state, STATE_APPROVED).where(
				table.name == wrong.name
			).run()
		# a state of the workflow with the same docstatus is kept
		pending = self._draft("Project Diesel Fill")
		frappe.db.set_value(
			pending.doctype, pending.name, "workflow_state", STATE_PENDING, update_modified=False
		)
		docs.append((pending, 0, STATE_PENDING))
		before = {
			(d.doctype, d.name): frappe.db.get_value(d.doctype, d.name, "modified") for d, _ds, _s in docs
		}
		for _run in range(2):
			native_workflows_inactive.execute()
			for doc, docstatus, state in docs:
				with self.subTest(doctype=doc.doctype, state=state):
					stored = self._stored(doc, "modified")
					self.assertEqual((stored.docstatus, stored.workflow_state), (docstatus, state))
					self.assertEqual(stored.modified, before[(doc.doctype, doc.name)])

	def test_patch_removes_a_duplicate_state_custom_field_and_keeps_the_values(self):
		doc = self._draft("Equipment Transport")
		cf = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": "Equipment Transport",
				"fieldname": "workflow_state",
				"label": "Workflow State",
				"fieldtype": "Link",
				"options": "Workflow State",
				"hidden": 1,
				"allow_on_submit": 1,
				"no_copy": 1,
			}
		)
		cf.name = "Equipment Transport-workflow_state"
		cf.db_insert()  # the column already exists: no schema change inside the test
		frappe.clear_cache(doctype="Equipment Transport")
		self.assertEqual(
			[f.fieldname for f in frappe.get_meta("Equipment Transport").fields].count("workflow_state"), 2
		)
		native_workflows_inactive.execute()
		self.assertFalse(frappe.db.exists("Custom Field", cf.name))
		self.assertEqual(
			[f.fieldname for f in frappe.get_meta("Equipment Transport").fields].count("workflow_state"), 1
		)
		self.assertEqual(self._stored(doc).workflow_state, STATE_DRAFT)

	# ---------- inactive: today's behaviour ----------
	def test_hooks_are_wired(self):
		events = frappe.get_hooks("doc_events")
		for doctype in WORKFLOWS:
			self.assertIn("card.cancel_reason.on_validate", events[doctype]["validate"])
			self.assertIn("card.cancel_reason.before_cancel", events[doctype]["before_cancel"])
		self.assertIn(
			"card.governance_workflows.workflow_action_query_conditions",
			frappe.get_hooks("permission_query_conditions")["Workflow Action"],
		)
		self.assertIn(
			"card.governance_workflows.has_workflow_action_permission",
			frappe.get_hooks("has_permission")["Workflow Action"],
		)

	def test_inactive_flow_is_unchanged_and_the_state_follows_docstatus(self):
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self.assertEqual(self._stored(doc).workflow_state, STATE_DRAFT)
				# a client state is never kept while inactive
				for forged in (STATE_PENDING, STATE_APPROVED):
					doc = frappe.get_doc(doctype, doc.name)
					doc.workflow_state = forged
					doc.return_reason = "forged"
					doc.save()
					self.assertEqual(self._stored(doc, "return_reason").workflow_state, STATE_DRAFT)
					self.assertFalse(self._stored(doc, "return_reason").return_reason)
				# direct submit, as today
				doc = frappe.get_doc(doctype, doc.name)
				doc.submit()
				self.assertEqual(
					(self._stored(doc).docstatus, self._stored(doc).workflow_state),
					(1, STATE_BEFORE_GOVERNANCE),
				)
				# a REST cancel with its reason, as today (FR-123)
				doc = frappe.get_doc(doctype, doc.name)
				doc.update({"docstatus": 2, "cancel_reason": REASON})
				doc.save()
				self.assertEqual(
					(self._stored(doc).docstatus, self._stored(doc).workflow_state), (2, STATE_CANCELLED)
				)

	def test_inactive_submit_by_frappe_client_and_cancel_with_reason(self):
		doc = self._draft("Card Monthly Card")
		frappe.client.submit(frappe.get_doc(doc.doctype, doc.name).as_dict())
		self.assertEqual(self._stored(doc).docstatus, 1)
		cancel_with_reason(doc.doctype, doc.name, REASON)
		self.assertEqual(
			(self._stored(doc).docstatus, self._stored(doc).workflow_state), (2, STATE_CANCELLED)
		)

	# ---------- active (inside the test only) ----------
	def test_direct_submit_is_refused_on_every_route(self):
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				self._activate(doctype)
				doc = self._draft(doctype)
				self.assertEqual(self._stored(doc).workflow_state, STATE_DRAFT)
				self._refused(WorkflowSubmitError, frappe.get_doc(doctype, doc.name).submit)
				self._refused(
					WorkflowSubmitError, frappe.client.submit, frappe.get_doc(doctype, doc.name).as_dict()
				)
				d = frappe.get_doc(doctype, doc.name).as_dict()
				self._refused(WorkflowSubmitError, savedocs, json.dumps(d, default=str), "Submit")
				for state in (STATE_DRAFT, STATE_BEFORE_GOVERNANCE, STATE_PENDING, STATE_CANCELLED):
					d = frappe.get_doc(doctype, doc.name)
					d.update({"docstatus": 1, "workflow_state": state})  # REST PUT
					self._refused(WorkflowSubmitError, d.save)
				# a transition the user does not hold: a System Manager may submit (DocPerm) but holds no
				# "Approve" transition (the CARD guard); a Card User may not submit at all (Frappe)
				d = frappe.get_doc(doctype, doc.name)
				d.update({"docstatus": 1, "workflow_state": STATE_APPROVED})
				self._refused(WorkflowSubmitError, self._as, self.sysmanager, d.save)
				d = frappe.get_doc(doctype, doc.name)
				d.update({"docstatus": 1, "workflow_state": STATE_APPROVED})
				self._refused(frappe.PermissionError, self._as, self.preparer, d.save)
				# REST insert with docstatus 1
				for state in (None, STATE_APPROVED):
					new = self._new(doctype)
					new.docstatus = 1
					new.workflow_state = state
					self._refused(WorkflowSubmitError, new.insert, ignore_permissions=True)
				self.assertEqual(self._stored(doc).docstatus, 0)
				# the workflow action approves (no review required by default)
				self._approve(doc)
				self.assertEqual(
					(self._stored(doc).docstatus, self._stored(doc).workflow_state), (1, STATE_APPROVED)
				)

	def test_review_path_and_mandatory_return_reason(self):
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				self._activate(doctype)
				doc = self._draft(doctype)
				self._as(self.preparer, apply_workflow, frappe.get_doc(doctype, doc.name), ACTION_SEND)
				self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)
				# a return without the reason: the workflow action itself, a state change by save, a blank reason
				self._refused(
					ReturnReasonRequiredError,
					self._as,
					self.manager,
					apply_workflow,
					frappe.get_doc(doctype, doc.name),
					ACTION_RETURN,
				)
				d = frappe.get_doc(doctype, doc.name)
				d.update({"workflow_state": STATE_DRAFT, "return_reason": "forged"})
				self._refused(ReturnReasonRequiredError, self._as, self.manager, d.save)
				self._refused(
					ReturnReasonRequiredError,
					self._as,
					self.manager,
					return_for_correction,
					doctype,
					doc.name,
					" <b></b> ",
				)
				self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)
				# the Card User cannot return
				self._refused(
					frappe.ValidationError,
					self._as,
					self.preparer,
					return_for_correction,
					doctype,
					doc.name,
					REASON,
				)
				out = self._as(self.manager, return_for_correction, doctype, doc.name, f" {REASON} ")
				self.assertEqual(out["workflow_state"], STATE_DRAFT)
				self.assertEqual(self._stored(doc, "return_reason").return_reason, REASON)
				self.assertTrue(
					frappe.db.exists(
						"Comment",
						{
							"reference_doctype": doctype,
							"reference_name": doc.name,
							"content": ("like", f"%{REASON}%"),
						},
					)
				)
				# the reason is server-written: a later save keeps the stored one
				d = frappe.get_doc(doctype, doc.name)
				d.return_reason = "forged"
				d.save()
				self.assertEqual(self._stored(doc, "return_reason").return_reason, REASON)
				self._as(self.preparer, apply_workflow, frappe.get_doc(doctype, doc.name), ACTION_SEND)
				self._approve(doc)
				self.assertEqual(
					(self._stored(doc).docstatus, self._stored(doc).workflow_state), (1, STATE_APPROVED)
				)

	def test_review_toggle(self):
		# the field does not exist yet: the review is optional (safe default 0)
		self.assertFalse(frappe.get_meta("Card Company Settings").has_field("card_review_required"))
		self.assertFalse(governance_workflows.review_required(self.company))
		with (
			patch.object(type(frappe.get_meta("Card Company Settings")), "has_field", return_value=True),
			patch("card.governance_workflows.company_setting", return_value=1),
		):
			self.assertTrue(governance_workflows.review_required(self.company))
		with patch("card.governance_workflows.company_setting", return_value=1):
			self.assertFalse(governance_workflows.review_required(self.company))  # field missing wins
		self.assertFalse(governance_workflows.review_required(None))
		# the Workflow condition: no row / a row without the field -> offered; review required -> not offered
		wf = frappe.get_doc("Workflow", WORKFLOWS["Equipment Transport"])
		direct = next(t for t in wf.transitions if t.state == STATE_DRAFT and t.next_state == STATE_APPROVED)
		doc = self._draft("Equipment Transport")
		self.assertTrue(is_transition_condition_satisfied(direct, doc))
		row = frappe._dict(company=doc.company, card_review_required=1)
		with patch.object(frappe.db, "get_value", return_value=row):
			self.assertFalse(is_transition_condition_satisfied(direct, doc))
		# the server refuses an approval from Draft when the company requires the review
		self._activate("Equipment Transport")
		with patch("card.governance_workflows.review_required", return_value=True):
			d = frappe.get_doc(doc.doctype, doc.name)
			d.update({"docstatus": 1, "workflow_state": STATE_APPROVED})
			self._refused(WorkflowSubmitError, self._as, self.manager, d.save)
			self._as(self.preparer, apply_workflow, frappe.get_doc(doc.doctype, doc.name), ACTION_SEND)
			self._approve(doc)
		self.assertEqual(self._stored(doc).workflow_state, STATE_APPROVED)

	def test_cancel_routes_through_cancel_with_reason(self):
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				wf = self._activate(doctype)
				doc = self._draft(doctype)
				self._approve(doc)
				# REST cancel with a reason, frappe.client.cancel, a Python cancel: refused while active
				d = frappe.get_doc(doctype, doc.name)
				d.update({"docstatus": 2, "cancel_reason": REASON})
				self._refused(WorkflowCancelRouteError, d.save)
				self._refused(WorkflowCancelRouteError, frappe.client.cancel, doctype, doc.name)
				# an owner-added Workflow cancel action, even one whose state fills cancel_reason
				if not frappe.db.exists("Workflow Action Master", "Cancel"):
					frappe.get_doc(
						{"doctype": "Workflow Action Master", "workflow_action_name": "Cancel"}
					).insert()
				cancelled = next(s for s in wf.states if s.state == STATE_CANCELLED)
				cancelled.update_field = "cancel_reason"
				cancelled.update_value = "filled by the workflow"
				wf.append(
					"transitions",
					{
						"state": STATE_APPROVED,
						"action": "Cancel",
						"next_state": STATE_CANCELLED,
						"allowed": "Card Manager",
						"allow_self_approval": 1,
					},
				)
				wf.save()
				self._clear_workflow_cache()
				self._refused(
					WorkflowCancelRouteError,
					self._as,
					self.manager,
					apply_workflow,
					frappe.get_doc(doctype, doc.name),
					"Cancel",
				)
				self.assertEqual(self._stored(doc, "cancel_reason").docstatus, 1)
				self.assertFalse(self._stored(doc, "cancel_reason").cancel_reason)
				# the form's Cancel
				self._as(self.manager, cancel_with_reason, doctype, doc.name, REASON)
				stored = self._stored(doc, "cancel_reason")
				self.assertEqual(
					(stored.docstatus, stored.workflow_state, stored.cancel_reason),
					(2, STATE_CANCELLED, REASON),
				)

	def test_cancel_skips_only_the_dedicated_state_field(self):
		"""A Workflow whose state field is a business field (e.g. FR-142's approval_status) never lets a cancel
		change that field; the dedicated workflow_state is skipped as before."""
		fake = frappe._dict(doctype="Card Daily Log")
		with patch("card.cancel_reason.get_workflow_name", return_value="Some Workflow"):
			with patch.object(frappe, "get_cached_value", return_value="approval_status"):
				self.assertEqual(cancel_reason._skipped(fake), {"cancel_reason"})
			with patch.object(frappe, "get_cached_value", return_value="workflow_state"):
				self.assertEqual(cancel_reason._skipped(fake), {"cancel_reason", "workflow_state"})

	def test_approve_transition_allow_self_approval_per_doctype(self):
		"""Owner decision (2026-11-11, reiteration of FR-143 / WP-D2a): only the monthly card may let the
		creator approve (its Approve is still gated by FR-143's per-company Warn/Refuse rule); Equipment
		Transport and Project Diesel Fill keep Frappe's native rule "the creator cannot approve", i.e.
		``allow_self_approval = 0`` on every Approve transition. Send-for-Review and Return-for-Correction
		keep ``allow_self_approval = 1`` because a preparer must be able to send their own draft and a
		Card Manager may return their own request. Each Approve transition is asserted individually, so a
		flip of any one row fails this test (addresses the reviewer finding that a mutation flipping
		``self_approval = 1`` for transport or fill was not caught by the suite)."""
		expected = {
			"Card Monthly Card": 1,
			"Equipment Transport": 0,
			"Project Diesel Fill": 0,
		}
		for doctype, name in WORKFLOWS.items():
			with self.subTest(doctype=doctype):
				# the Python source (so a source mutation is caught before any install)
				rows = governance_workflows.transitions(doctype)
				self.assertTrue(rows, "the transitions table must not be empty")
				for state, action, next_state, role, self_approval, _cond in rows:
					with self.subTest(transition=(state, action, next_state, role), layer="source"):
						if action == ACTION_APPROVE:
							self.assertEqual(
								cint(self_approval),
								expected[doctype],
								msg=(
									f"{doctype} source Approve transition {state} -> {next_state} "
									f"(role {role}) must have allow_self_approval={expected[doctype]}"
								),
							)
						else:
							self.assertEqual(cint(self_approval), 1)
				# the installed Workflow record (so a DB edit that lifts the rule is caught too)
				wf = frappe.get_doc("Workflow", name)
				approve = [t for t in wf.transitions if t.action == ACTION_APPROVE]
				self.assertTrue(approve, "the workflow must ship Approve transitions")
				for t in approve:
					with self.subTest(transition=(t.state, t.next_state, t.allowed), layer="db"):
						self.assertEqual(
							cint(t.allow_self_approval),
							expected[doctype],
							msg=(
								f"{doctype} DB Approve transition {t.state} -> {t.next_state} "
								f"(role {t.allowed}) must have allow_self_approval={expected[doctype]}"
							),
						)
				# Send-for-Review and Return-for-Correction are not approvals: the creator may do both
				for t in wf.transitions:
					if t.action in (ACTION_SEND, ACTION_RETURN):
						with self.subTest(transition=(t.state, t.action, t.next_state, t.allowed)):
							self.assertEqual(cint(t.allow_self_approval), 1)

	def test_rest_put_at_docstatus_1_on_submitted_doc_does_not_re_approve(self):
		"""FR-152: with an active Workflow a REST PUT (or Python save) on an already-submitted record
		that sends ``docstatus = 1`` either (a) is a no-op when the state value matches the stored state
		and no other field changes (Frappe's ``update_after_submit`` path), or (b) is refused with
		``UpdateAfterSubmitError`` when the request would rewrite ``workflow_state`` (hidden, no copy,
		``allow_on_submit = 0``). In both cases the stored record's docstatus and workflow_state stay
		what the approve set them to: no re-submit and no state rewrite slips through at
		``docstatus = 1`` (addresses the reviewer finding on the ``_check_submit`` path and documents
		the intended behaviour)."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				self._activate(doctype)
				doc = self._draft(doctype)
				self._approve(doc)
				baseline = self._stored(doc)
				self.assertEqual((baseline.docstatus, baseline.workflow_state), (1, STATE_APPROVED))
				# state == stored, docstatus unchanged: silently normalized (Frappe's no-op update)
				d = frappe.get_doc(doctype, doc.name)
				d.update({"docstatus": 1, "workflow_state": STATE_APPROVED})
				d.save()
				noop = self._stored(doc)
				self.assertEqual((noop.docstatus, noop.workflow_state), (1, STATE_APPROVED))
				# state != stored: refused (workflow_state has allow_on_submit = 0)
				for state in (STATE_BEFORE_GOVERNANCE, STATE_PENDING, STATE_DRAFT):
					d = frappe.get_doc(doctype, doc.name)
					d.update({"docstatus": 1, "workflow_state": state})
					self._refused(frappe.ValidationError, d.save)
				after = self._stored(doc)
				self.assertEqual((after.docstatus, after.workflow_state), (1, STATE_APPROVED))

	def _set_rule(self, company, rule):
		name = frappe.db.get_value("Card Company Settings", {**SETTINGS, "company": company}, "name")
		if not name:
			row = frappe.get_doc(
				{
					"doctype": "Card Company Settings",
					**SETTINGS,
					"idx": 100 + frappe.db.count("Card Company Settings", SETTINGS),
					"company": company,
				}
			)
			row.db_insert()
			name = row.name
		frappe.db.set_value("Card Company Settings", name, governance.RULE_FIELD, rule)
		frappe.clear_document_cache("Card Settings", "Card Settings")

	def test_fr143_self_approval_guard_on_the_approve_transition(self):
		self._activate("Card Monthly Card")
		self._set_rule(self.company, governance.RULE_REFUSE)
		# the creator (Administrator is not exempt) and an editor cannot approve under Refuse
		doc = self._draft("Card Monthly Card")
		self._refused(
			frappe.PermissionError, apply_workflow, frappe.get_doc(doc.doctype, doc.name), ACTION_APPROVE
		)
		frappe.db.set_value(
			doc.doctype, doc.name, "edited_by", f"Administrator\n{self.manager}", update_modified=False
		)
		self._refused(frappe.PermissionError, self._approve, doc, self.manager)
		self.assertEqual(self._stored(doc).docstatus, 0)
		# another manager approves; the approval is recorded by FR-143
		self._approve(doc, self.manager2)
		stored = self._stored(doc, "approved_by", "self_approved")
		self.assertEqual(
			(stored.docstatus, stored.workflow_state, stored.approved_by, stored.self_approved),
			(1, STATE_APPROVED, self.manager2, 0),
		)
		# Warn (the default): the preparer approves and the card is marked
		self._set_rule(self.company, None)
		doc = self._draft("Card Monthly Card")
		apply_workflow(frappe.get_doc(doc.doctype, doc.name), ACTION_APPROVE)
		self.assertEqual(self._stored(doc, "self_approved").self_approved, 1)

	# ---------- company-scoped approval queues ----------
	def _company_b(self):
		name = "TEST-WF-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "W" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _queue_entry(self, doc):
		wa = frappe.get_doc(
			{
				"doctype": "Workflow Action",
				"reference_doctype": doc.doctype,
				"reference_name": doc.name,
				"workflow_state": STATE_PENDING,
				"status": "Open",
				"permitted_roles": [{"role": "Card Manager"}],
			}
		)
		wa.insert(ignore_permissions=True)
		return wa

	def test_approval_queue_is_company_scoped(self):
		other = self._company_b()
		self._activate("Project Diesel Fill")
		mine = self._draft("Project Diesel Fill")
		self._as(self.preparer, apply_workflow, frappe.get_doc(mine.doctype, mine.name), ACTION_SEND)
		# a pending fill of company B (stored directly: only its company matters for the queue)
		theirs = frappe.new_doc("Project Diesel Fill")
		theirs.update({"company": other, "date": self._today(), "litres": 1, "workflow_state": STATE_PENDING})
		theirs.name = "TEST-WF-FILL-" + self.token
		theirs.db_insert()
		for doc in (mine, theirs):
			if not frappe.db.exists("Workflow Action", {"reference_name": doc.name, "status": "Open"}):
				self._queue_entry(doc)
		ours = frappe.get_value("Workflow Action", {"reference_name": mine.name, "status": "Open"}, "name")
		foreign = frappe.get_value("Workflow Action", {"reference_name": theirs.name}, "name")
		user = self._user("co-a", ("Card Manager",), company=self.company)
		frappe.set_user(user)
		try:
			listed = set(frappe.get_list("Workflow Action", pluck="reference_name", limit_page_length=0))
			self.assertIn(mine.name, listed)
			self.assertNotIn(theirs.name, listed)
			self.assertTrue(frappe.has_permission("Workflow Action", "read", doc=ours, user=user))
			self.assertFalse(frappe.has_permission("Workflow Action", "read", doc=foreign, user=user))
			pending = set(
				frappe.get_list(
					"Project Diesel Fill",
					filters={"workflow_state": STATE_PENDING},
					pluck="name",
					limit_page_length=0,
				)
			)
			self.assertIn(mine.name, pending)
			self.assertNotIn(theirs.name, pending)
		finally:
			frappe.set_user("Administrator")
		# an unrestricted user sees both; the hook adds no condition
		self.assertEqual(governance_workflows.workflow_action_query_conditions("Administrator"), "")

	# ---------- dependents (Connections) ----------
	def test_connections_list_downstream_documents(self):
		from frappe.desk.notifications import get_open_count

		expected = {
			"Card Monthly Card": {"GL Posting Log", "Purchase Invoice", "Sales Invoice"},
			"Equipment Transport": {"GL Posting Log", "Purchase Invoice", "Card Equipment Assignment"},
			"Project Diesel Fill": {"GL Posting Log", "Purchase Invoice"},
		}
		for doctype, links in expected.items():
			with self.subTest(doctype=doctype):
				data = frappe.get_meta(doctype).get_dashboard_data()
				self.assertEqual(set(data.internal_links), links)
				items = {i for group in data.transactions for i in group["items"]}
				self.assertEqual(items, links | {doctype})
				doc = self._draft(doctype)
				doc.submit()
				out = get_open_count(doctype, doc.name)
				self.assertIn("internal_links_found", out["count"])
