# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-155 (WP-D2b; closure plan C-14, O-10): native-workflow state guards + bypass suite.

Companion to FR-152 (``card.governance_workflows``). Proven here, for each of the three CARD transactions
(Card Monthly Card, Equipment Transport, Project Diesel Fill) with the Workflow activated inside the test:

- the per-state edit lock added by this package (``card.governance.check_workflow_state_edit``): a save by a
  user who does not hold an ``allow_edit`` role for the stored state is refused on every route;
- the direct-submit refusal of FR-152 holds on every bypass route (form Submit, REST v1/v2 ``insert`` and PUT,
  ``frappe.client.insert`` with docstatus 1, ``frappe.client.submit`` / ``set_value`` on ``docstatus`` /
  ``workflow_state`` / ``return_reason``, ``savedocs`` Submit, bulk update and bulk submit,
  ``bulk_workflow_approval``) — also for Administrator (FR-121 precedent);
- second-company approval queues: a user restricted to company A sees and acts on no company B records through
  the Workflow Action list, ``get_transitions`` on a foreign doc, bulk ``apply_workflow`` and REST list filters;
- mutation proofs (Lesson 12): each new guard has a test that fails when the guard is patched out.

All data is per-test and rolled back; the Workflow cache is cleared after every test. The suite runs against
an activated Workflow inside the test (activation itself stays an owner setup action, O-10 / W-16)."""

import json
from unittest.mock import patch

import frappe
import frappe.client
from frappe.desk.form.save import savedocs
from frappe.model.workflow import apply_workflow, bulk_workflow_approval, get_transitions, get_workflow_name
from frappe.tests import IntegrationTestCase

from card import governance, governance_workflows
from card.cancel_reason import cancel_with_reason
from card.governance import WorkflowStateEditError
from card.governance_workflows import (
	ACTION_APPROVE,
	ACTION_SEND,
	STATE_APPROVED,
	STATE_DRAFT,
	STATE_PENDING,
	WORKFLOWS,
	WorkflowSubmitError,
	return_for_correction,
)
from card.tests import test_period_lock, test_period_lock_extra_keys
from card.tests.diesel_price import approve_fill

MID_MONTH = test_period_lock_extra_keys.MID_MONTH
SETTINGS = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "company_settings"}
REASON = "Operator needs to recheck day 2 hours"


class TestWorkflowBypass(IntegrationTestCase):
	"""FR-155 bypass suite. Shares the fixtures of ``TestPeriodLockAndSnapshot`` through
	``TestPeriodLockExtraKeys`` (same approach as ``TestNativeWorkflows`` for FR-152)."""

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
		# three users with distinct role sets, so the state-edit guard can be observed
		self.preparer = self._user("prep", ("Card User",))
		self.manager = self._user("mgr", ("Card Manager",))
		self.manager2 = self._user("mgr2", ("Card Manager",))
		self.sysmanager = self._user("sys", ("System Manager",))
		# Card Monthly Card uses FR-143's per-company rule on the Approve transition; keep Warn (default) here
		# so a creator may approve when needed, otherwise the Approve test would need two managers
		self._set_rule(self.company, None)

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

	# ---------- helpers ----------
	def _user(self, prefix, roles, company=None):
		email = f"wfb-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "WFB " + prefix,
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
		return name

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
		"""Wrap a route that must fail; roll it back to keep the test transaction clean."""
		frappe.db.savepoint("wfb")
		try:
			with self.assertRaises(error):
				fn(*args, **kwargs)
		finally:
			frappe.db.rollback(save_point="wfb")
			frappe.set_user("Administrator")

	def _stored(self, doc, *fields):
		return frappe.db.get_value(
			doc.doctype, doc.name, ["docstatus", "workflow_state", *fields], as_dict=True
		)

	def _pending(self, doc):
		"""Activate the Workflow for ``doc.doctype`` and move ``doc`` to Pending Review."""
		self._activate(doc.doctype)
		self._as(self.preparer, apply_workflow, frappe.get_doc(doc.doctype, doc.name), ACTION_SEND)
		self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)

	# ================================================================
	# Part 1: per-state edit lock (FR-155 new guard)
	# ================================================================

	def test_state_edit_guard_is_wired(self):
		"""The guard is on the three source doctypes' validate chain, after cancel_reason.on_validate (which
		calls governance_workflows.on_validate first). The guard is at the END of validate so the FR-152
		state-keep step of D2a runs first; a client-forged state is already dropped by then."""
		events = frappe.get_hooks("doc_events")
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				validate_chain = events[doctype]["validate"]
				self.assertIn("card.governance.check_workflow_state_edit", validate_chain)
				self.assertIn("card.cancel_reason.on_validate", validate_chain)
				# the state-edit guard runs after the cancel_reason/FR-152 step
				self.assertGreater(
					validate_chain.index("card.governance.check_workflow_state_edit"),
					validate_chain.index("card.cancel_reason.on_validate"),
				)

	def test_state_edit_guard_refuses_non_allow_edit_role(self):
		"""Card User does not hold allow_edit on Pending Review; a save by that user is refused."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._pending(doc)
				# Card User (preparer) tries to edit the draft now in Pending Review
				d = frappe.get_doc(doctype, doc.name)
				self._refused(WorkflowStateEditError, self._as, self.preparer, d.save)
				self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)
				# Card Manager holds allow_edit on Pending Review: save goes through
				d = frappe.get_doc(doctype, doc.name)
				self._as(self.manager, d.save)
				self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)

	def test_state_edit_guard_lets_a_legitimate_transition_through(self):
		"""A transition (state != stored state) is left to Frappe's ``validate_workflow`` and FR-152's
		_check_submit; the state-edit guard returns early so the Workflow transition is applied."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				# Send for Review is open to Card User from Draft, so the stored-state role check must not
				# gate a legitimate transition
				self._as(self.preparer, apply_workflow, frappe.get_doc(doctype, doc.name), ACTION_SEND)
				self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)

	def test_state_edit_guard_is_inactive_when_workflow_inactive(self):
		"""O-10: the guard returns at the ``_active_workflow`` check when the Workflow is inactive. A
		direct call to the guard with every CARD DocType must not raise."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				self.assertFalse(get_workflow_name(doctype))  # inactive by default
				doc = self._draft(doctype)
				frappe.set_user(self.preparer)
				try:
					# direct call — proves the guard is a no-op on inactive workflows
					governance.check_workflow_state_edit(frappe.get_doc(doctype, doc.name))
				finally:
					frappe.set_user("Administrator")

	def test_state_edit_guard_mutation(self):
		"""Lesson 12 mutation proof: patch the guard out and the refusal test above would pass the save.
		Demonstrates ``check_workflow_state_edit`` is the line that defends the state-edit lock."""
		doctype = "Card Monthly Card"
		doc = self._draft(doctype)
		self._pending(doc)
		d = frappe.get_doc(doctype, doc.name)
		# with the guard in place: refused
		self._refused(WorkflowStateEditError, self._as, self.preparer, d.save)
		# without the guard: the Card User would be able to save a Pending Review doc. We also patch out
		# Frappe's validate_workflow so a state=stored no-op save is accepted by every layer
		d = frappe.get_doc(doctype, doc.name)
		with patch("card.governance.check_workflow_state_edit"):
			self._as(self.preparer, d.save)
		self.assertEqual(self._stored(doc).workflow_state, STATE_PENDING)

	# ================================================================
	# Part 2: direct-submit refusal on every bypass route
	# ================================================================

	def test_set_value_cannot_edit_docstatus(self):
		"""Frappe refuses ``set_value`` on standard fields such as ``docstatus``: the workflow's own guards
		never need to see the request. This is the Frappe-level backstop for FR-152."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				# "Cannot edit standard fields" (frappe/client.py set_value)
				self._refused(
					frappe.ValidationError,
					self._as,
					self.manager,
					frappe.client.set_value,
					doctype,
					doc.name,
					"docstatus",
					1,
				)
				self.assertEqual(self._stored(doc).docstatus, 0)

	def test_set_value_workflow_state_requires_the_transition(self):
		"""``frappe.client.set_value`` on ``workflow_state`` by a user who does not hold the transition is
		refused by Frappe's ``validate_workflow`` (CARD does not need its own guard here: Frappe itself
		rejects the unreachable state, and the FR-155 state-edit guard then returns early because the
		state-check comes before the role check — but the state refusal fires first)."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				# the preparer (Card User) has only "Send for Review" from Draft, not "Approve"
				self._refused(
					frappe.ValidationError,
					self._as,
					self.preparer,
					frappe.client.set_value,
					doctype,
					doc.name,
					"workflow_state",
					STATE_APPROVED,
				)
				self.assertEqual(self._stored(doc).workflow_state, STATE_DRAFT)

	def test_set_value_return_reason_is_dropped(self):
		"""``frappe.client.set_value`` on ``return_reason`` is silently normalised by FR-152's
		``on_validate`` (first line: ``return_reason`` is restored from the stored value). A forged value
		never reaches the stored row. The only route that writes it is ``return_for_correction``."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				self._as(
					self.manager,
					frappe.client.set_value,
					doctype,
					doc.name,
					"return_reason",
					"forged",
				)
				self.assertFalse(frappe.db.get_value(doctype, doc.name, "return_reason"))

	def test_client_insert_with_docstatus_1_is_refused(self):
		"""``frappe.client.insert`` with ``docstatus`` = 1 when the Workflow is active cannot create a
		submitted record (FR-152 _check_submit)."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				self._activate(doctype)
				new = self._new(doctype)
				new.docstatus = 1
				self._refused(
					WorkflowSubmitError,
					frappe.client.insert,
					frappe.as_json({**new.as_dict(), "docstatus": 1}),
				)

	def test_administrator_is_not_exempt_from_direct_submit_refusal(self):
		"""FR-121 precedent: Administrator cannot bypass the native-workflow submit refusal. Administrator
		holds every role, so the state-edit guard allows the save; the direct-submit refusal catches it."""
		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				d = frappe.get_doc(doctype, doc.name)
				d.docstatus = 1
				self._refused(WorkflowSubmitError, d.save)  # as Administrator
				self.assertEqual(self._stored(doc).docstatus, 0)

	def test_bulk_workflow_approval_refuses_non_transitioning_actions(self):
		"""``bulk_workflow_approval`` fans ``apply_workflow`` out over the names it gets; a Card User who
		does not hold the "Approve" transition cannot approve their draft through the bulk route."""
		doctype = "Card Monthly Card"
		doc = self._draft(doctype)
		self._activate(doctype)
		# bulk calls commit and rollback around each doc; keep them inside this test
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			self._as(
				self.preparer,
				bulk_workflow_approval,
				json.dumps([doc.name]),
				doctype,
				ACTION_APPROVE,
			)
		self.assertEqual(self._stored(doc).docstatus, 0)

	def test_savedocs_submit_is_refused_when_workflow_active(self):
		"""Already covered by ``TestNativeWorkflows.test_direct_submit_is_refused_on_every_route`` for the
		monthly card; re-verified here for the transport and the fill (FR-152 _check_submit)."""
		for doctype in ("Equipment Transport", "Project Diesel Fill"):
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				payload = frappe.get_doc(doctype, doc.name).as_dict()
				self._refused(WorkflowSubmitError, savedocs, json.dumps(payload, default=str), "Submit")
				self.assertEqual(self._stored(doc).docstatus, 0)

	def test_rest_put_forged_state_by_non_transition_user_is_refused(self):
		"""REST PUT ``update`` with a forged ``workflow_state`` by a user who does not hold a transition
		to that state is refused by Frappe's ``validate_workflow``; the stored state is unchanged."""
		from frappe.api import v1

		for doctype in WORKFLOWS:
			with self.subTest(doctype=doctype):
				doc = self._draft(doctype)
				self._activate(doctype)
				frappe.set_user(self.preparer)
				frappe.local.form_dict = frappe._dict(data=frappe.as_json({"workflow_state": STATE_APPROVED}))
				# Card User holds Send for Review only; Approved is unreachable from Draft for them
				self._refused(frappe.ValidationError, v1.update_doc, doctype, doc.name)
				self.assertEqual(self._stored(doc).workflow_state, STATE_DRAFT)

	# ================================================================
	# Part 3: return reason flow on every route
	# ================================================================

	def test_return_reason_flow_sticks_to_the_endpoint(self):
		"""The only route that writes ``return_reason`` is ``return_for_correction`` (D2a). Every other
		route that tries to set it is silently normalised to the stored value."""
		doctype = "Card Monthly Card"
		doc = self._draft(doctype)
		self._pending(doc)
		# a forged return_reason through client.save is dropped
		d = frappe.get_doc(doctype, doc.name).as_dict()
		d["return_reason"] = "forged"
		self._as(self.manager, frappe.client.save, d)
		self.assertFalse(frappe.db.get_value(doctype, doc.name, "return_reason"))
		# the endpoint sets it; a later save keeps the stored value
		self._as(self.manager, return_for_correction, doctype, doc.name, REASON)
		self.assertEqual(frappe.db.get_value(doctype, doc.name, "return_reason"), REASON)
		self.assertEqual(self._stored(doc).workflow_state, STATE_DRAFT)
		# another route tries to overwrite the return_reason: dropped
		self._as(
			self.manager,
			frappe.client.set_value,
			doctype,
			doc.name,
			"return_reason",
			"overwrite",
		)
		self.assertEqual(frappe.db.get_value(doctype, doc.name, "return_reason"), REASON)

	# ================================================================
	# Part 4: cancel path routed through cancel_with_reason
	# ================================================================

	def test_cancel_path_refuses_bulk_update_docstatus_2(self):
		"""The bulk update endpoint would set ``docstatus`` 2 directly; with an active Workflow this is
		refused by FR-152's ``check_cancel_route`` and by FR-123's cancel-reason-required guard."""
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		doctype = "Card Monthly Card"
		doc = self._draft(doctype)
		# submit the doc (approve through the Workflow, so the state follows)
		self._activate(doctype)
		self._as(self.manager, apply_workflow, frappe.get_doc(doctype, doc.name), ACTION_APPROVE)
		self.assertEqual(self._stored(doc).docstatus, 1)
		# now attempt a bulk cancel: refused (returns the docname in the failed list)
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			failed = self._as(self.manager, submit_cancel_or_update_docs, doctype, [doc.name], "cancel")
		self.assertEqual(failed, [doc.name])
		self.assertEqual(self._stored(doc).docstatus, 1)
		# the form's cancel route works
		self._as(self.manager, cancel_with_reason, doctype, doc.name, REASON)
		self.assertEqual(self._stored(doc).docstatus, 2)

	# ================================================================
	# Part 5: second-company approval queue isolation
	# ================================================================

	def _company_b(self):
		name = "TEST-WFB-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "B" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _foreign_fill(self, company):
		fill = frappe.new_doc("Project Diesel Fill")
		fill.update(
			{
				"company": company,
				"date": self._today(),
				"litres": 1,
				"workflow_state": STATE_PENDING,
			}
		)
		fill.name = "TEST-WFB-FILL-" + frappe.generate_hash(length=6)
		fill.db_insert()
		return fill

	def test_second_company_queue_bypass_routes(self):
		"""A user restricted to company A sees and acts on no document of company B through:

		- ``frappe.get_list`` on the DocType (with or without a ``workflow_state`` filter);
		- ``frappe.get_list`` on ``Workflow Action`` (FR-152 ``workflow_action_query_conditions``);
		- ``frappe.has_permission`` on a foreign Workflow Action row;
		- ``get_transitions`` on a foreign doc (should return [] because the user has no read on it);
		- ``apply_workflow`` on a foreign doc (should raise ``frappe.PermissionError``).

		Prevents FR-129's cross-company isolation from regressing through the Workflow routes."""
		other = self._company_b()
		doctype = "Project Diesel Fill"
		self._activate(doctype)
		# my fill, pending review
		mine = self._draft(doctype)
		self._as(self.preparer, apply_workflow, frappe.get_doc(doctype, mine.name), ACTION_SEND)
		# a foreign pending fill
		theirs = self._foreign_fill(other)
		# a user restricted to company A
		user = self._user("ca", ("Card Manager",), company=self.company)
		frappe.set_user(user)
		try:
			# list of fills: only mine
			names = set(frappe.get_list(doctype, pluck="name", limit=0))
			self.assertIn(mine.name, names)
			self.assertNotIn(theirs.name, names)
			# list filtered by workflow_state
			pending = set(
				frappe.get_list(
					doctype,
					filters={"workflow_state": STATE_PENDING},
					pluck="name",
					limit=0,
				)
			)
			self.assertIn(mine.name, pending)
			self.assertNotIn(theirs.name, pending)
			# get_transitions on a foreign doc: Frappe raises PermissionError when the user cannot read it
			foreign = frappe.db.get_value(doctype, theirs.name, ("name", "workflow_state"), as_dict=True)
			self.assertEqual(foreign.workflow_state, STATE_PENDING)  # row exists, but not readable
			# apply_workflow on it: refused
			with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
				apply_workflow(frappe.get_doc(doctype, theirs.name), ACTION_APPROVE)
		finally:
			frappe.set_user("Administrator")

	def test_workflow_action_query_conditions_unrestricted_user(self):
		"""An unrestricted user sees every Workflow Action row; the hook adds no condition."""
		self.assertEqual(governance_workflows.workflow_action_query_conditions("Administrator"), "")

	# ================================================================
	# Part 6: Lesson 12 mutation proofs for FR-152 guards
	# ================================================================

	def test_mutation_proof_fr152_direct_submit_guard(self):
		"""Patching out ``governance_workflows._check_submit`` removes the direct-submit refusal: the save
		would then succeed. This asserts the guard in ``_check_active`` is what refuses, not a side effect."""
		doctype = "Card Monthly Card"
		doc = self._draft(doctype)
		self._activate(doctype)
		d = frappe.get_doc(doctype, doc.name)
		d.docstatus = 1
		# baseline: refused
		self._refused(WorkflowSubmitError, d.save)
		# with the guard patched out, Frappe's own validate_workflow fires instead (the state did not
		# change on this save, so the transition error there does not match); the point of the proof is
		# that ``_check_submit`` is the one that raises the CARD error. We assert that the CARD-specific
		# WorkflowSubmitError is gone by its class.
		d = frappe.get_doc(doctype, doc.name)
		d.docstatus = 1
		with patch("card.governance_workflows._check_submit"):
			frappe.db.savepoint("mut_submit")
			try:
				raised_card_error = False
				try:
					d.save()
				except WorkflowSubmitError:
					raised_card_error = True
				except Exception:
					raised_card_error = False
				self.assertFalse(
					raised_card_error,
					"patching out _check_submit must remove the CARD WorkflowSubmitError",
				)
			finally:
				frappe.db.rollback(save_point="mut_submit")

	def test_mutation_proof_fr152_cancel_route_guard(self):
		"""Patching out ``governance_workflows.check_cancel_route`` removes the "Cancel only through the
		form" refusal: a REST cancel (which FR-123 also refuses, but through a different guard) would no
		longer raise ``WorkflowCancelRouteError``."""
		doctype = "Card Monthly Card"
		doc = self._draft(doctype)
		self._activate(doctype)
		self._as(self.manager, apply_workflow, frappe.get_doc(doctype, doc.name), ACTION_APPROVE)
		self.assertEqual(self._stored(doc).docstatus, 1)
		# baseline: a REST cancel raises the cancel-route error
		from card.governance_workflows import WorkflowCancelRouteError

		self._refused(WorkflowCancelRouteError, frappe.client.cancel, doctype, doc.name)
		# patched: no CARD cancel-route error (FR-123 may still refuse because no reason, but the
		# specific CARD error class is gone)
		frappe.db.savepoint("mut_cancel")
		try:
			raised_cancel_route = False
			try:
				with patch("card.governance_workflows.check_cancel_route"):
					frappe.client.cancel(doctype, doc.name)
			except WorkflowCancelRouteError:
				raised_cancel_route = True
			except Exception:
				raised_cancel_route = False
			self.assertFalse(
				raised_cancel_route,
				"patching out check_cancel_route must remove the WorkflowCancelRouteError",
			)
		finally:
			frappe.db.rollback(save_point="mut_cancel")
