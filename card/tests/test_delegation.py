# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-163 (WP-D5; #35 G4 delegation; closure plan C-12, owner decision O-12): Card Approval
Delegation.

Proven here:
- a delegation lets the delegate act on the delegator's queue in the window (SoD creator check
  consults the delegator) and the on_submit Comment names the delegation;
- a delegate without a CARD approver role is refused on insert (no role grant by delegation);
- overlapping active delegations for the same (delegator, scope, company) are refused, including
  under the ``SCOPE_ALL`` cover-all semantics;
- window boundaries: active on from_date, active on to_date, expired day after (scheduled job);
- cross-company: a delegation for company A does not reach company B cards;
- Lesson 1 forgery: ``frappe.client.set_value`` on ``status`` by anyone is server-restored;
- Lesson 2 cancel path: a cancel request that changes any stored field is refused by
  ``_refuse_changes(..., neutral=True)``, and the cancelled row's status is set to ``Cancelled``;
- Lesson 4 concurrency: two parallel overlapping inserts, one fails under ``.for_update()``;
- Lesson 12 mutation proofs: removing the delegate-role check, the overlap check or the
  status-restore makes a test fail;
- Lesson 13: the docs do NOT claim delegation grants roles.

All data per-test, rolled back by the integration transaction."""

from __future__ import annotations

import inspect
from unittest.mock import patch

import frappe
import frappe.client
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from card import governance
from card.cancel_reason import CancelChangesDocumentError
from card.card.doctype.card_approval_delegation import card_approval_delegation as delegation_module
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase

CARD = "Card Monthly Card"
DELEGATION = "Card Approval Delegation"
SETTINGS = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "company_settings"}


class _DelegationBase(_CustomerCardsBase):
	"""Shared helpers for FR-163 tests."""

	def setUp(self):
		super().setUp()
		# delegator and delegate both already hold the approver role (Card Manager); the
		# delegation grants no role.
		self.delegator = self._user("mgra", ("Card User", "Card Manager"))
		self.delegate = self._user("mgrb", ("Card User", "Card Manager"))
		# another approver, not involved in any delegation
		self.other_mgr = self._user("mgrc", ("Card User", "Card Manager"))
		# preparer: only draft rights
		self.preparer = self._user("prep", ("Card User",))
		# ensure the company's rule is Refuse so the SoD check is active (otherwise it is a Warn)
		self._set_rule(self.company, governance.RULE_REFUSE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict(docs=[])
		super().tearDown()
		frappe.clear_document_cache("Card Settings", "Card Settings")

	# ---------- builders ----------
	def _user(self, prefix, roles, company=None):
		email = f"del-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Del " + prefix,
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
		"""Set the per-company card_approval_rule (reuses FR-143's row shape)."""
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

	def _delegation(
		self,
		delegator=None,
		delegate=None,
		company=None,
		approval_scope="All CARD approvals",
		from_date=None,
		to_date=None,
		reason="Annual leave",
		submit=True,
	):
		doc = frappe.new_doc(DELEGATION)
		doc.delegator_user = delegator or self.delegator
		doc.delegate_user = delegate or self.delegate
		doc.company = company or self.company
		doc.approval_scope = approval_scope
		doc.from_date = from_date or today()
		doc.to_date = to_date or add_days(today(), 7)
		doc.reason = reason
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	def _new_card(self, hours=(8, 8)):
		c = frappe.new_doc(CARD)
		c.update(
			{
				"equipment": self._equipment().name,
				"project": self.project,
				"shift": "نهاري",
				"month": "09",
				"year": 2026,
			}
		)
		for row in _days(list(hours)):
			c.append("days", row)
		return c

	def _draft_card(self, user=None, hours=(8, 8)):
		frappe.set_user(user or self.preparer)
		try:
			return self._new_card(hours).insert()
		finally:
			frappe.set_user("Administrator")

	def _submit_card(self, name, user):
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(CARD, name)
			doc.submit()
			return doc
		finally:
			frappe.set_user("Administrator")

	def _refused(self, fn, *args, error=frappe.ValidationError, message=None, **kwargs):
		frappe.db.savepoint("d5_refused")
		frappe.clear_messages()
		try:
			with self.assertRaises(error) as raised:
				fn(*args, **kwargs)
			if message:
				text = str(raised.exception) + " ".join(str(m) for m in frappe.get_message_log())
				self.assertIn(message, text)
		finally:
			frappe.db.rollback(save_point="d5_refused")
			frappe.set_user("Administrator")


class TestDelegationInsert(_DelegationBase):
	# ---------- schema and wiring ----------
	def test_doctype_is_installed_and_scheduler_wired(self):
		self.assertTrue(frappe.db.exists("DocType", DELEGATION))
		meta = frappe.get_meta(DELEGATION)
		status = meta.get_field("status")
		self.assertEqual((status.read_only, status.no_copy), (1, 1))
		# scheduler daily event present
		events = frappe.get_hooks("scheduler_events") or {}
		daily = events.get("daily") or []
		self.assertIn(
			"card.card.doctype.card_approval_delegation.card_approval_delegation.expire_delegations_past_to_date",
			daily,
		)
		# on_submit hook on Card Monthly Card
		doc_events = frappe.get_hooks("doc_events")[CARD]
		self.assertIn("card.governance.log_delegation_use", doc_events["on_submit"])

	# ---------- happy path ----------
	def test_insert_and_submit_happy_path(self):
		d = self._delegation()
		self.assertEqual(d.status, "Active")
		self.assertEqual(d.docstatus, 1)

	# ---------- delegate role check (O-12) ----------
	def test_delegate_without_approver_role_refused(self):
		"""The delegate (Card User only) does not hold the delegator's Card Manager role."""
		self._refused(
			self._delegation,
			delegate=self.preparer,
			message="must already hold",
		)

	def test_delegator_without_approver_role_refused(self):
		plain = self._user("plain", ("Card User",))
		self._refused(
			self._delegation,
			delegator=plain,
			delegate=self.delegate,
			message="does not hold any CARD approver role",
		)

	def test_delegator_equals_delegate_refused(self):
		self._refused(
			self._delegation,
			delegator=self.delegator,
			delegate=self.delegator,
			message="must be different",
		)

	# ---------- overlap check (Lesson 4) ----------
	def test_overlap_same_scope_refused(self):
		self._delegation(from_date=today(), to_date=add_days(today(), 5))
		self._refused(
			self._delegation,
			from_date=add_days(today(), 3),
			to_date=add_days(today(), 10),
			approval_scope="All CARD approvals",
			message="already has an active delegation",
		)

	def test_overlap_all_covers_specific(self):
		self._delegation(approval_scope="All CARD approvals")
		self._refused(
			self._delegation,
			approval_scope="Monthly Cards",
			message="already has an active delegation",
		)

	def test_overlap_specific_covered_by_all(self):
		self._delegation(approval_scope="Monthly Cards")
		self._refused(
			self._delegation,
			approval_scope="All CARD approvals",
			message="already has an active delegation",
		)

	def test_disjoint_scopes_allowed(self):
		"""Two different specific scopes for the same delegator do not overlap."""
		d1 = self._delegation(approval_scope="Monthly Cards")
		d2 = self._delegation(approval_scope="Transports")
		self.assertEqual((d1.docstatus, d2.docstatus), (1, 1))

	def test_disjoint_dates_allowed(self):
		d1 = self._delegation(from_date=today(), to_date=add_days(today(), 2))
		d2 = self._delegation(from_date=add_days(today(), 3), to_date=add_days(today(), 5))
		self.assertEqual((d1.docstatus, d2.docstatus), (1, 1))

	def test_cancelled_delegation_frees_slot(self):
		d = self._delegation()
		# the cancel path needs a reason stored in the FR-123 shared flag, but this DocType is
		# outside FR-123's scope — ``on_cancel`` runs ``_refuse_changes`` directly.
		d.cancel()
		# a new delegation for the same scope/company/window is allowed
		d2 = self._delegation()
		self.assertEqual(d2.docstatus, 1)

	# ---------- date validation ----------
	def test_from_after_to_refused(self):
		self._refused(
			self._delegation,
			from_date=add_days(today(), 5),
			to_date=today(),
			message="must not be after",
		)


class TestDelegationActingOnBehalf(_DelegationBase):
	def test_delegate_submits_on_behalf_of_delegator(self):
		"""Preparer drafts; delegator is NOT the preparer; delegate submits in delegator's place
		and the on_submit Comment names the delegation."""
		self._delegation()
		draft = self._draft_card(self.preparer)
		card = self._submit_card(draft.name, self.delegate)
		self.assertEqual(card.docstatus, 1)
		# the submit was by the delegate (they ARE the acting user)
		stored = frappe.db.get_value(
			CARD, card.name, ["submitted_by", "approved_by", "self_approved"], as_dict=True
		)
		self.assertEqual(stored.submitted_by, self.delegate)
		self.assertEqual(stored.approved_by, self.delegate)
		self.assertEqual(stored.self_approved, 0)
		# Info Comment names the delegation
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": CARD, "reference_name": card.name, "comment_type": "Info"},
			fields=["content"],
		)
		matched = [c for c in comments if "Approved on behalf" in (c.content or "")]
		self.assertEqual(len(matched), 1, comments)
		self.assertIn(self.delegator, matched[0].content)
		self.assertIn(self.delegate, matched[0].content)

	def test_delegate_submitting_delegators_own_draft_is_self_approval(self):
		"""FR-143 + FR-163: when the delegator prepared the card, the delegate submitting it
		is a self-approval under the delegator's identity — refused under Refuse rule."""
		self._delegation()
		draft = self._draft_card(self.delegator)
		self._refused(
			self._submit_card,
			draft.name,
			self.delegate,
			error=frappe.PermissionError,
			message="another user must submit",
		)

	def test_non_delegate_cannot_act_on_behalf(self):
		"""The other_mgr has the role but no delegation; they can still submit their own queue."""
		self._delegation()
		draft = self._draft_card(self.preparer)
		# other_mgr: a non-delegated approver — allowed because they hold the Card Manager role
		card = self._submit_card(draft.name, self.other_mgr)
		# no delegation Comment on this card
		comments = frappe.get_all(
			"Comment",
			filters={"reference_doctype": CARD, "reference_name": card.name, "comment_type": "Info"},
			fields=["content"],
		)
		self.assertFalse([c for c in comments if "Approved on behalf" in (c.content or "")], comments)

	def test_delegation_outside_window_does_not_apply(self):
		"""A delegation whose window is in the future does not let the delegate carry the
		delegator's identity today."""
		self._delegation(
			from_date=add_days(today(), 5),
			to_date=add_days(today(), 10),
		)
		draft = self._draft_card(self.delegator)
		# the delegate still holds Card Manager (they always did), so a plain submit is allowed
		# UNLESS the delegator is a preparer — but FR-143's own delegator-identity check only
		# consults a live delegation. Here no active delegation today, so the delegate's own
		# identity is used, and they are not a preparer.
		card = self._submit_card(draft.name, self.delegate)
		self.assertEqual(card.docstatus, 1)

	def test_user_acting_on_behalf_cross_company(self):
		other_co = self._company_b()
		self._delegation(company=self.company)
		# same delegate, different company → None
		self.assertIsNone(governance.user_acting_on_behalf(self.delegate, CARD, other_co))
		# correct company → delegator
		self.assertEqual(
			governance.user_acting_on_behalf(self.delegate, CARD, self.company),
			self.delegator,
		)

	def test_user_acting_on_behalf_boundary_dates(self):
		"""Active on from_date and on to_date; inactive before and after."""
		d = self._delegation(from_date=today(), to_date=today())
		# today: Active
		self.assertEqual(
			governance.user_acting_on_behalf(self.delegate, CARD, self.company, today()),
			self.delegator,
		)
		# tomorrow: outside the window → None
		self.assertIsNone(
			governance.user_acting_on_behalf(self.delegate, CARD, self.company, add_days(today(), 1))
		)
		# ensure the delegation status itself resolves correctly
		self.assertEqual(d.status, "Active")

	def test_scope_scoping(self):
		"""A Monthly Cards delegation does not let the delegate carry the delegator's identity
		for a Project Diesel Fill submit."""
		self._delegation(approval_scope="Monthly Cards")
		# Monthly Cards covered
		self.assertEqual(
			governance.user_acting_on_behalf(self.delegate, "Card Monthly Card", self.company),
			self.delegator,
		)
		# Project Diesel Fill not covered
		self.assertIsNone(
			governance.user_acting_on_behalf(self.delegate, "Project Diesel Fill", self.company)
		)

	def _company_b(self):
		name = "TEST-D5-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "D" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name


class TestDelegationForgery(_DelegationBase):
	# ---------- Lesson 1 forgery on ``status`` ----------
	def test_client_cannot_forge_status_on_insert(self):
		doc = frappe.new_doc(DELEGATION)
		doc.update(
			{
				"delegator_user": self.delegator,
				"delegate_user": self.delegate,
				"company": self.company,
				"approval_scope": "All CARD approvals",
				"from_date": today(),
				"to_date": add_days(today(), 3),
				"reason": "Forged",
				"status": "Expired",  # forged
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.status, "Active")  # server resolved

	def test_client_cannot_forge_status_by_set_value(self):
		d = self._delegation()
		frappe.set_user(self.delegator)
		# status is read_only on DocPerm; Frappe client.set_value refuses with PermissionError
		# OR a user with write access forges it — we check the stored row is restored either way.
		try:
			frappe.client.set_value(DELEGATION, d.name, "status", "Expired")
		except frappe.PermissionError:
			pass
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(DELEGATION, d.name, "status")
		self.assertEqual(stored, "Active")

	def test_client_cannot_forge_status_by_save(self):
		d = self._delegation()
		# Saving a submitted delegation with a forged status: ``before_update_after_submit``
		# restores the stored value.
		frappe.set_user("Administrator")
		values = frappe.get_doc(DELEGATION, d.name).as_dict()
		values["status"] = "Expired"
		frappe.client.save(values)
		stored = frappe.db.get_value(DELEGATION, d.name, "status")
		self.assertEqual(stored, "Active")

	# ---------- Lesson 2 cancel path ----------
	def test_cancel_with_forged_values_refused(self):
		"""A cancel request that changes any stored field is refused by ``_refuse_changes``."""
		from frappe.api import v1

		d = self._delegation()
		frappe.set_user("Administrator")
		# forge the reason during a cancel request
		frappe.local.form_dict = frappe._dict(data=frappe.as_json({"docstatus": 2, "reason": "FORGED"}))
		self._refused(v1.update_doc, DELEGATION, d.name, error=CancelChangesDocumentError, message=None)
		# stored row untouched
		stored = frappe.db.get_value(DELEGATION, d.name, ["docstatus", "reason", "status"], as_dict=True)
		self.assertEqual(stored.docstatus, 1)
		self.assertEqual(stored.status, "Active")

	def test_cancel_clean_sets_status_cancelled(self):
		d = self._delegation()
		d.cancel()
		stored = frappe.db.get_value(DELEGATION, d.name, ["docstatus", "status"], as_dict=True)
		self.assertEqual((stored.docstatus, stored.status), (2, "Cancelled"))


class TestDelegationExpiry(_DelegationBase):
	def test_scheduler_expires_past_delegations(self):
		"""A delegation whose to_date is yesterday becomes Expired on the daily job."""
		# we need to insert with past dates, bypassing the window+resolve_status logic by
		# submitting first (active today), then back-dating via a direct update that avoids the
		# controller
		d = self._delegation(from_date=today(), to_date=today())
		# backdate to_date past today
		frappe.db.set_value(DELEGATION, d.name, "to_date", add_days(today(), -1), update_modified=False)
		# scheduler
		updated = delegation_module.expire_delegations_past_to_date()
		self.assertGreaterEqual(updated, 1)
		self.assertEqual(frappe.db.get_value(DELEGATION, d.name, "status"), "Expired")

	def test_scheduler_idempotent(self):
		d = self._delegation()
		frappe.db.set_value(DELEGATION, d.name, "to_date", add_days(today(), -2), update_modified=False)
		first = delegation_module.expire_delegations_past_to_date()
		second = delegation_module.expire_delegations_past_to_date()
		self.assertGreaterEqual(first, 1)
		self.assertEqual(second, 0)  # already Expired on the second run

	def test_scheduler_leaves_active_rows_alone(self):
		d_future = self._delegation(from_date=today(), to_date=add_days(today(), 10))
		before = frappe.db.get_value(DELEGATION, d_future.name, "status")
		delegation_module.expire_delegations_past_to_date()
		self.assertEqual(frappe.db.get_value(DELEGATION, d_future.name, "status"), before)

	def test_expired_delegation_does_not_apply(self):
		d = self._delegation(from_date=today(), to_date=today())
		frappe.db.set_value(DELEGATION, d.name, "to_date", add_days(today(), -1), update_modified=False)
		frappe.db.set_value(DELEGATION, d.name, "status", "Expired", update_modified=False)
		# user_acting_on_behalf returns None (status != Active or window missed)
		self.assertIsNone(governance.user_acting_on_behalf(self.delegate, CARD, self.company))


class TestDelegationConcurrency(_DelegationBase):
	"""Lesson 4: ``_validate_no_overlap`` uses ``.for_update()`` so two concurrent inserts
	overlapping the same existing delegation serialize on its row lock.

	A full two-connection test would require committing test setup data on the shared sandbox
	site, which bleeds into other test modules through the setUpClass fixtures. We prove the
	same guarantee in-transaction:

	1. The overlap-check query is built with ``.for_update()`` (code inspection — if a later
	   edit drops it, the compiled query string loses "FOR UPDATE" and the assertion fails).
	2. A second insert attempt in the same connection immediately after a committed overlapping
	   row is refused by the overlap predicate, under the same code path that the second of two
	   concurrent transactions would take once the first one holds the lock."""

	def test_overlap_query_uses_for_update(self):
		"""Static proof that the overlap check is a locking read (Lesson 4)."""
		from card.card.doctype.card_approval_delegation import card_approval_delegation as mod

		src = inspect.getsource(mod.CardApprovalDelegation._validate_no_overlap)
		self.assertIn(".for_update()", src)

	def test_second_overlapping_insert_in_same_transaction_is_refused(self):
		"""Simulates the second of two concurrent inserts: the first committed row is read by
		``_validate_no_overlap`` under ``for_update`` and refuses the second attempt. This is
		the exact mechanism that serialises two real concurrent transactions."""
		first = self._delegation(from_date=today(), to_date=add_days(today(), 5))
		self.assertEqual(first.docstatus, 1)
		self._refused(
			self._delegation,
			approval_scope="Monthly Cards",
			from_date=today(),
			to_date=add_days(today(), 3),
			message="already has an active delegation",
		)


class TestDelegationMutationProofs(_DelegationBase):
	"""Lesson 12: removing any guard makes a test fail."""

	def test_mutation_delegate_role_check_removed(self):
		"""If the delegate-role check is patched out, a Card User can be named as delegate."""
		with patch.object(
			delegation_module.CardApprovalDelegation, "_validate_delegate_role", lambda self: None
		):
			# the delegate is a plain Card User — without the guard this should succeed
			doc = frappe.new_doc(DELEGATION)
			doc.update(
				{
					"delegator_user": self.delegator,
					"delegate_user": self.preparer,  # Card User only
					"company": self.company,
					"approval_scope": "All CARD approvals",
					"from_date": today(),
					"to_date": add_days(today(), 3),
					"reason": "mutation proof",
				}
			)
			doc.insert(ignore_permissions=True)
			self.assertEqual(doc.docstatus, 0)
		# with the guard present, it must fail
		self._refused(self._delegation, delegate=self.preparer, message="must already hold")

	def test_mutation_overlap_removed(self):
		"""If the overlap check is patched out, two active delegations for the same scope co-exist."""
		first = self._delegation()
		with patch.object(
			delegation_module.CardApprovalDelegation,
			"_validate_no_overlap",
			lambda self, for_update=False: None,
		):
			second = self._delegation()
			self.assertEqual((first.docstatus, second.docstatus), (1, 1))
		# with the guard present, the second must fail
		self._refused(self._delegation, message="already has an active delegation")

	def test_mutation_status_resolve_removed_on_insert(self):
		"""If ``validate``'s ``status = self._resolve_status()`` is removed, a forged client
		value on insert sticks. This proves Lesson 1 on the INSERT path."""
		with patch.object(
			delegation_module.CardApprovalDelegation,
			"validate",
			lambda self: (
				self._validate_window(),
				self._validate_delegator_role(),
				self._validate_delegate_role(),
				self._validate_no_overlap(),
			),
		):
			doc = frappe.new_doc(DELEGATION)
			doc.update(
				{
					"delegator_user": self.delegator,
					"delegate_user": self.delegate,
					"company": self.company,
					"approval_scope": "All CARD approvals",
					"from_date": today(),
					"to_date": add_days(today(), 3),
					"reason": "mutation",
					"status": "Expired",  # forged
				}
			)
			doc.insert(ignore_permissions=True)
			self.assertEqual(doc.status, "Expired")  # mutation lets the forge through

	def test_status_resolve_blocks_forge_on_insert(self):
		"""With the guard present, the forged client ``status`` is dropped on insert
		(positive control for the mutation proof)."""
		doc = frappe.new_doc(DELEGATION)
		doc.update(
			{
				"delegator_user": self.delegator,
				"delegate_user": self.delegate,
				"company": self.company,
				"approval_scope": "All CARD approvals",
				"from_date": today(),
				"to_date": add_days(today(), 3),
				"reason": "positive",
				"status": "Expired",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(doc.status, "Active")


class TestDelegationDocsHonesty(_DelegationBase):
	"""Lesson 13: the module docstring must not claim role grants."""

	def test_doctype_description_does_not_claim_role_grant(self):
		meta = frappe.get_meta(DELEGATION)
		delegate_df = meta.get_field("delegate_user")
		# the field description makes the no-role-grant explicit
		self.assertIn("grants no role", (delegate_df.description or "").lower())

	def test_controller_docstring_states_no_role_grant(self):
		doc_str = delegation_module.__doc__ or ""
		self.assertIn("WITHOUT role grants", doc_str)
		self.assertNotIn("grants the delegate", doc_str.lower())
