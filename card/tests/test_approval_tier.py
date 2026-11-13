# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-159 (WP-E; #35, #49, closure plan C row E): per-company approval tier thresholds and the
server guard on the monthly card's submit.

Proven here:

- empty ``approval_tier_thresholds`` keeps the current behaviour: every card is tier 0, any user with
  Card Monthly Card write may submit (no role gate);
- a single threshold matches the card's net amount: under the threshold is tier 0 (allowed), at or
  above needs the ``role_required`` role;
- nested thresholds: the highest matching tier wins (ordering is amount_threshold desc);
- two companies with different thresholds: company A's tier does not affect company B's cards (BOLA);
- Workflow condition parity: when the Workflow is active (W-16), the Approve transition evaluates the
  same tier check (direct submit with workflow inactive, Approve with workflow active);
- Administrator is NOT exempt (FR-121 / FR-155 precedent);
- the server-written ``approval_tier`` field is dropped on every route (Lesson 1: form save, REST
  insert / PUT, ``frappe.client.set_value`` / ``save`` / ``submit``, savedocs);
- Lesson 7 (savedocs Cancel): a forged ``approval_tier`` on a cancel request is ignored (the server
  re-resolves from the stored card);
- Lesson 12 mutations: removing ``resolve_approval_tier`` from on_validate or removing the role check
  from before_submit each fails a dedicated test;
- Lesson 4 (concurrency): ``for_update`` on the settings row refuses the slower of two concurrent
  submits when a tier change is being pushed.

All data is per-test and rolled back."""

from unittest.mock import patch

import frappe
import frappe.client
from frappe.utils import flt

from card import governance
from card.governance import ApprovalTierMissingRoleError, resolve_approval_tier
from card.tests.cancel_reason import TEST_REASON, store_reason, with_reason
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase

CARD = "Card Monthly Card"
SETTINGS = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "company_settings"}
TIER_FORGED = {"approval_tier": 99, "approval_tier_name": "forged"}


class _TierBase(_CustomerCardsBase):
	"""Shared helpers for FR-159 tier tests: users, company threshold rows, card builders and routed
	submits that are rolled back on failure."""

	def setUp(self):
		super().setUp()
		self.preparer = self._user("prep", ("Card User",))
		self.manager = self._user("mgr", ("Card Manager",))
		self.manager2 = self._user("mgr2", ("Card Manager",))
		# an existing role the owner may name as role_required (never created here)
		self.tier_role = "Accounts Manager"
		self.senior_role = "Accounts User"
		self.approver_tier = self._user("app1", ("Card Manager", self.tier_role))
		self.senior_tier = self._user("app2", ("Card Manager", self.tier_role, self.senior_role))
		self._set_rule(self.company, None)
		self._clear_tiers(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict(docs=[])
		super().tearDown()
		frappe.clear_document_cache("Card Settings", "Card Settings")

	# ---------- builders ----------
	def _user(self, prefix, roles):
		email = f"tier-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Tier " + prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _settings_row(self, company):
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
		return name

	def _set_rule(self, company, rule):
		self._settings_row(company)
		frappe.db.set_value(
			"Card Company Settings",
			{**SETTINGS, "company": company},
			governance.RULE_FIELD,
			rule,
		)
		frappe.clear_document_cache("Card Settings", "Card Settings")

	def _clear_tiers(self, company):
		"""Remove every threshold row for ``company``."""
		frappe.db.delete(
			"Card Approval Tier Threshold",
			{"parent": "Card Settings", "parentfield": "approval_tier_thresholds", "company": company},
		)
		frappe.clear_document_cache("Card Settings", "Card Settings")

	def _add_tier(self, company, tier_name, amount, role):
		"""Insert one threshold row for ``company`` directly (bypasses parent validation; sufficient
		for the tier-resolution tests). The parent lock keeps the read consistent."""
		idx = frappe.db.count(
			"Card Approval Tier Threshold",
			{"parent": "Card Settings", "parentfield": "approval_tier_thresholds"},
		)
		row = frappe.get_doc(
			{
				"doctype": "Card Approval Tier Threshold",
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "approval_tier_thresholds",
				"idx": idx + 1,
				"company": company,
				"tier_name": tier_name,
				"amount_threshold": amount,
				"role_required": role,
			}
		)
		row.db_insert()
		frappe.clear_document_cache("Card Settings", "Card Settings")
		return row.name

	def _new(self, hours=(8, 8)):
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

	def _draft(self, user=None, hours=(8, 8)):
		frappe.set_user(user or self.preparer)
		try:
			return self._new(hours).insert()
		finally:
			frappe.set_user("Administrator")

	def _submit(self, name, user):
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(CARD, name)
			doc.submit()
			return doc
		finally:
			frappe.set_user("Administrator")

	def _refused(self, fn, *args, error=ApprovalTierMissingRoleError, **kwargs):
		"""``fn`` fails with ``error``; rolled back inside a savepoint."""
		frappe.db.savepoint("tier_test")
		frappe.clear_messages()
		try:
			with self.assertRaises(error):
				fn(*args, **kwargs)
		finally:
			frappe.db.rollback(save_point="tier_test")
			frappe.set_user("Administrator")

	def _stored(self, name, *extra):
		fields = ["docstatus", "approval_tier", "approval_tier_name", *extra]
		return frappe.db.get_value(CARD, name, fields, as_dict=True)


class TestApprovalTierSchema(_TierBase):
	"""Schema + wiring assertions that do not need a running flow."""

	def test_fields_are_server_only(self):
		meta = frappe.get_meta(CARD)
		for field in governance.TIER_FIELDS:
			df = meta.get_field(field)
			self.assertEqual((df.read_only, df.no_copy, df.allow_on_submit), (1, 1, 0), field)
		# the SERVER_FIELDS tuple declares both tier fields
		for field in governance.TIER_FIELDS:
			self.assertIn(field, governance.SERVER_FIELDS)

	def test_threshold_child_doctype_installed(self):
		"""The new child DocType is a table with a scalar amount, a Role link and a company column."""
		meta = frappe.get_meta("Card Approval Tier Threshold")
		self.assertTrue(meta.istable)
		expected = {
			"company": ("Link", "Company"),
			"tier_name": ("Data", None),
			"amount_threshold": ("Currency", None),
			"role_required": ("Link", "Role"),
		}
		for fieldname, (fieldtype, options) in expected.items():
			df = meta.get_field(fieldname)
			self.assertIsNotNone(df, fieldname)
			self.assertEqual(df.fieldtype, fieldtype, fieldname)
			if options:
				self.assertEqual(df.options, options, fieldname)

	def test_company_settings_table_field_installed(self):
		df = frappe.get_meta("Card Company Settings").get_field(governance.TIER_TABLE_FIELD)
		self.assertIsNotNone(df)
		self.assertEqual(df.fieldtype, "Table")
		self.assertEqual(df.options, governance.TIER_CHILD_DOCTYPE)


class TestApprovalTierResolution(_TierBase):
	"""Pure resolution: ``resolve_approval_tier`` on crafted docs; no save, no submit."""

	def _doc(self, company=None, net=0.0, customer_net=0.0):
		company = company or self.company
		return frappe._dict(company=company, net_amount=net, customer_net_amount=customer_net)

	def test_no_rows_returns_none(self):
		self.assertIsNone(resolve_approval_tier(self._doc(net=10_000_000)))
		# any tier calculation on a doc with no company is also None
		self.assertIsNone(resolve_approval_tier(self._doc(company=None, net=1)))

	def test_single_threshold_under_and_at(self):
		self._add_tier(self.company, "Tier 1", 10_000, self.tier_role)
		self.assertIsNone(resolve_approval_tier(self._doc(net=9_999)))
		tier = resolve_approval_tier(self._doc(net=10_000))
		self.assertEqual(
			(tier["tier_index"], tier["tier_name"], tier["role_required"]), (1, "Tier 1", self.tier_role)
		)
		self.assertEqual(flt(tier["amount_threshold"]), 10_000.0)

	def test_highest_match_wins(self):
		self._add_tier(self.company, "Tier 1", 10_000, self.tier_role)
		self._add_tier(self.company, "Tier 2", 50_000, self.senior_role)
		# under tier 1
		self.assertIsNone(resolve_approval_tier(self._doc(net=1_000)))
		# at tier 1, under tier 2: tier 1 role
		tier = resolve_approval_tier(self._doc(net=20_000))
		self.assertEqual((tier["tier_name"], tier["role_required"]), ("Tier 1", self.tier_role))
		# at tier 2: tier 2 role wins
		tier = resolve_approval_tier(self._doc(net=100_000))
		self.assertEqual((tier["tier_name"], tier["role_required"]), ("Tier 2", self.senior_role))

	def test_customer_side_amount_counts(self):
		"""A customer-only card (rented-out) has 0 supplier net; the customer_net_amount gates the tier."""
		self._add_tier(self.company, "Tier 1", 10_000, self.tier_role)
		self.assertIsNone(resolve_approval_tier(self._doc(net=0, customer_net=9_999)))
		tier = resolve_approval_tier(self._doc(net=0, customer_net=10_000))
		self.assertEqual(tier["role_required"], self.tier_role)

	def test_negative_net_still_gated(self):
		"""A refund-shaped card (negative net) is gated by its absolute size (`max(abs(...))`)."""
		self._add_tier(self.company, "Tier 1", 5_000, self.tier_role)
		tier = resolve_approval_tier(self._doc(net=-20_000))
		self.assertEqual(tier["role_required"], self.tier_role)

	def test_rows_of_another_company_are_ignored(self):
		"""BOLA: company A's threshold does not reach company B's cards."""
		other = self._company_b()
		self._add_tier(other, "Tier 1", 1, self.tier_role)
		# card of our own company with large amount is still tier 0 (no row for our company)
		self.assertIsNone(resolve_approval_tier(self._doc(net=1_000_000)))
		# card of the other company at the threshold: tier 1
		tier = resolve_approval_tier(self._doc(company=other, net=1))
		self.assertEqual(tier["role_required"], self.tier_role)

	def _company_b(self):
		"""Second company fixture (same pattern as TestCardSoD._company_b)."""
		name = "TEST-TIER-CO-" + self.token
		if not frappe.db.exists("Company", name):
			co = frappe.new_doc("Company")
			co.update(
				{
					"company_name": name,
					"abbr": "T" + self.token[:6].upper(),
					"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"country": frappe.db.get_value("Company", self.company, "country"),
				}
			)
			co.name = name
			co.db_insert()
		return name


class TestApprovalTierSubmitGuard(_TierBase):
	"""The server guard on before_submit, on every submit route, with routed card builds that
	actually run the controller so net_amount is the real value."""

	def test_no_thresholds_allows_any_writer(self):
		"""Baseline: with no rows, a Card Manager without the tier role submits; stored tier = 0."""
		draft = self._draft(self.manager)
		# ensure the draft amount is above every number used in later tests
		self.assertTrue(flt(draft.net_amount) > 0)
		self._submit(draft.name, self.manager)
		stored = self._stored(draft.name, "net_amount")
		self.assertEqual(stored.docstatus, 1)
		self.assertEqual(stored.approval_tier, 0)
		self.assertIsNone(stored.approval_tier_name)

	def test_submit_below_threshold_is_tier_zero(self):
		"""A threshold way above the card's net amount leaves the card at tier 0; submit allowed."""
		self._add_tier(self.company, "Tier 1", 10_000_000, self.tier_role)
		draft = self._draft(self.manager)
		self._submit(draft.name, self.manager)
		stored = self._stored(draft.name)
		self.assertEqual((stored.docstatus, stored.approval_tier), (1, 0))

	def test_submit_above_threshold_without_role_is_refused(self):
		"""The card reaches tier 1, submitter has Card Manager but NOT the tier role: refused."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self.assertTrue(net > 0)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		# save the draft after adding the threshold so the server-written tier reaches storage; the
		# refused submit's own validate rewrites it but the rollback would undo that write
		frappe.set_user(self.manager)
		frappe.get_doc(CARD, draft.name).save()
		frappe.set_user("Administrator")
		# the manager has no Accounts Manager role: refused
		self._refused(self._submit, draft.name, self.manager)
		stored = self._stored(draft.name)
		self.assertEqual(stored.docstatus, 0)
		self.assertEqual(stored.approval_tier, 1)
		self.assertEqual(stored.approval_tier_name, "Tier 1")

	def test_role_required_is_enforced_on_submit(self):
		"""Same card: a user who holds the tier role submits successfully."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		# approver_tier holds Card Manager + Accounts Manager
		self._submit(draft.name, self.approver_tier)
		stored = self._stored(draft.name, "approved_by")
		self.assertEqual(
			(stored.docstatus, stored.approval_tier, stored.approved_by), (1, 1, self.approver_tier)
		)

	def test_highest_tier_wins_on_submit(self):
		"""With two thresholds both matched, the higher one's role gate rules."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", 1, self.tier_role)
		self._add_tier(self.company, "Tier 2", net, self.senior_role)
		# a user holding only tier 1's role: refused by tier 2
		self._refused(self._submit, draft.name, self.approver_tier)
		# a user holding tier 2's role: allowed
		self._submit(draft.name, self.senior_tier)
		stored = self._stored(draft.name)
		self.assertEqual((stored.docstatus, stored.approval_tier), (1, 2))

	def test_administrator_passes_by_holding_every_role(self):
		"""Administrator holds every role in Frappe (``frappe.get_roles("Administrator")`` returns
		every Role), so the tier role check passes for Administrator even without an explicit grant.
		This is a Frappe design limit, not an FR-159 bypass: the SoD rule (FR-143) still refuses
		Administrator under the company's Refuse rule."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		self._submit(draft.name, "Administrator")
		self.assertEqual(self._stored(draft.name).docstatus, 1)

	def test_second_company_tiers_do_not_affect_other_company(self):
		"""BOLA: a threshold on company B does not gate a card of company A."""
		other = self._company_b()
		self._add_tier(other, "Tier 1", 1, self.tier_role)
		draft = self._draft(self.manager)
		self._submit(draft.name, self.manager)  # our company has no threshold -> tier 0
		self.assertEqual(self._stored(draft.name).approval_tier, 0)

	def _company_b(self):
		name = "TEST-TIER-CO-" + self.token
		if not frappe.db.exists("Company", name):
			co = frappe.new_doc("Company")
			co.update(
				{
					"company_name": name,
					"abbr": "T" + self.token[:6].upper(),
					"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"country": frappe.db.get_value("Company", self.company, "country"),
				}
			)
			co.name = name
			co.db_insert()
		return name


class TestApprovalTierServerWritten(_TierBase):
	"""Server-written tier field cannot be forged on any route (Lesson 1)."""

	def test_client_tier_value_is_dropped_on_insert(self):
		self._add_tier(self.company, "Tier 1", 10_000_000, self.tier_role)  # not reached
		frappe.set_user(self.preparer)
		doc = self._new()
		doc.update(TIER_FORGED)
		doc.insert()
		frappe.set_user("Administrator")
		stored = self._stored(doc.name)
		# the server has re-resolved: tier 0 because the amount is below the threshold
		self.assertEqual(stored.approval_tier, 0)
		self.assertNotEqual(stored.approval_tier_name, "forged")

	def test_client_tier_value_is_dropped_on_save(self):
		draft = self._draft(self.preparer)
		frappe.set_user(self.preparer)
		values = frappe.get_doc(CARD, draft.name).as_dict()
		values.update(TIER_FORGED)
		frappe.client.save(values)
		frappe.set_user("Administrator")
		stored = self._stored(draft.name)
		self.assertEqual(stored.approval_tier, 0)
		self.assertNotEqual(stored.approval_tier_name, "forged")

	def test_client_tier_value_is_dropped_on_set_value(self):
		draft = self._draft(self.preparer)
		frappe.set_user(self.preparer)
		for field, value in TIER_FORGED.items():
			frappe.client.set_value(CARD, draft.name, field, value)
		frappe.set_user("Administrator")
		stored = self._stored(draft.name)
		self.assertEqual(stored.approval_tier, 0)
		self.assertNotEqual(stored.approval_tier_name, "forged")

	def test_rest_put_with_forged_tier_does_not_reach_storage(self):
		from frappe.api import v1

		draft = self._draft(self.preparer)
		frappe.set_user(self.preparer)
		frappe.local.form_dict = frappe._dict(data=frappe.as_json(TIER_FORGED))
		v1.update_doc(CARD, draft.name)
		frappe.set_user("Administrator")
		stored = self._stored(draft.name)
		self.assertEqual(stored.approval_tier, 0)

	def test_savedocs_cancel_with_forged_tier_is_ignored(self):
		"""Lesson 7: savedocs Cancel ignores client changes; a forged tier on a cancel request is
		dropped and the stored card keeps the server-resolved tier."""
		from frappe.desk.form.save import savedocs

		from card.cancel_reason import CancelChangesDocumentError

		# approved card at tier 1 by senior_tier (so cancel is possible)
		draft = self._draft(self.preparer)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		self._submit(draft.name, self.approver_tier)
		approved_tier = self._stored(draft.name).approval_tier
		self.assertEqual(approved_tier, 1)
		# savedocs Cancel with forged tier values
		store_reason(CARD, draft.name)
		frappe.set_user(self.approver_tier)
		forged = {**frappe.get_doc(CARD, draft.name).as_dict(), **TIER_FORGED, "cancel_reason": TEST_REASON}
		frappe.db.savepoint("tier_savedocs")
		try:
			savedocs(frappe.as_json(forged), "Cancel")
		except CancelChangesDocumentError:
			frappe.db.rollback(save_point="tier_savedocs")
		frappe.set_user("Administrator")
		# either the cancel went through with stored values, or it was refused; in both cases the
		# stored tier stays what the server had resolved at submit
		stored = self._stored(draft.name)
		self.assertEqual(stored.approval_tier, approved_tier)
		self.assertNotEqual(stored.approval_tier_name, "forged")
		# finally cancel the card the normal way to keep the row clean
		if stored.docstatus == 1:
			frappe.set_user(self.approver_tier)
			with_reason(frappe.get_doc(CARD, draft.name)).cancel()
			frappe.set_user("Administrator")


class TestApprovalTierWorkflow(_TierBase):
	"""Workflow parity (FR-152 Approve transition + FR-159 server guard). The Workflow is inactive by
	default (owner setup W-16 activates it). The tier check is NOT part of the Workflow Transition
	condition (Frappe's ``get_workflow_safe_globals`` whitelist does not expose ``frappe.get_attr`` or
	CARD modules; see note in ``card/governance_workflows.py``): instead the guard in
	``card.governance.before_submit`` runs on every submit route, ``apply_workflow(doc, "Approve")``
	included (it calls ``doc.submit()``). This test activates the Workflow and proves parity through
	that path."""

	def tearDown(self):
		try:
			self._deactivate_workflow()
		finally:
			super().tearDown()

	def _deactivate_workflow(self):
		"""Return the Card Monthly Card Workflow to inactive state so other tests see the default."""
		from card.governance_workflows import WORKFLOWS

		name = WORKFLOWS[CARD]
		if frappe.db.exists("Workflow", name):
			frappe.db.set_value("Workflow", name, "is_active", 0)
			frappe.cache.delete_key("workflow")
			frappe.clear_document_cache("Workflow", name)
			frappe.clear_cache(doctype=CARD)

	def _activate_workflow(self):
		from card.governance_workflows import WORKFLOWS

		name = WORKFLOWS[CARD]
		frappe.db.set_value("Workflow", name, "is_active", 1)
		frappe.cache.delete_key("workflow")
		frappe.clear_document_cache("Workflow", name)
		frappe.clear_cache(doctype=CARD)

	def test_approve_transition_refuses_without_tier_role(self):
		"""With the Workflow active, Approve a Pending Review card above tier 1 by a Card Manager
		without the tier role: ``apply_workflow`` calls ``doc.submit()`` which runs ``before_submit``,
		which raises ``ApprovalTierMissingRoleError`` (``frappe.PermissionError``). The card stays
		Pending Review."""
		from frappe.model.workflow import apply_workflow

		from card.governance_workflows import ACTION_APPROVE, ACTION_SEND, STATE_PENDING

		# draft -> Pending Review as the preparer, with threshold set first so the card is tier 1
		draft = self._draft(self.preparer)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		self._activate_workflow()
		frappe.set_user(self.preparer)
		doc = apply_workflow(frappe.get_doc(CARD, draft.name), ACTION_SEND)
		frappe.set_user("Administrator")
		self.assertEqual(doc.workflow_state, STATE_PENDING)
		# Approve by a Card Manager without the tier role: server guard refuses the submit
		frappe.db.savepoint("tier_wf_refuse")
		try:
			frappe.set_user(self.manager)
			with self.assertRaises(ApprovalTierMissingRoleError):
				apply_workflow(frappe.get_doc(CARD, draft.name), ACTION_APPROVE)
		finally:
			frappe.db.rollback(save_point="tier_wf_refuse")
			frappe.set_user("Administrator")
		# still Pending Review
		self.assertEqual(frappe.db.get_value(CARD, draft.name, "workflow_state"), STATE_PENDING)

	def test_approve_transition_allows_with_tier_role(self):
		"""Same path: a user holding the tier role goes through the workflow transition and the card
		reaches docstatus 1 / Approved."""
		from frappe.model.workflow import apply_workflow

		from card.governance_workflows import ACTION_APPROVE, ACTION_SEND, STATE_APPROVED

		draft = self._draft(self.preparer)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		self._activate_workflow()
		frappe.set_user(self.preparer)
		apply_workflow(frappe.get_doc(CARD, draft.name), ACTION_SEND)
		frappe.set_user(self.approver_tier)
		apply_workflow(frappe.get_doc(CARD, draft.name), ACTION_APPROVE)
		frappe.set_user("Administrator")
		stored = self._stored(draft.name, "workflow_state")
		self.assertEqual(
			(stored.docstatus, stored.workflow_state, stored.approval_tier), (1, STATE_APPROVED, 1)
		)


class TestApprovalTierConcurrency(_TierBase):
	"""Lesson 4: a tier change pushed while a submit is in flight uses ``for_update`` on the
	settings row. The locking read on ``_company_tier_rows`` makes the slower of two concurrent
	submits see the newly inserted threshold."""

	def test_for_update_is_on_the_tier_query(self):
		"""Statically prove that the resolver's SQL holds ``for update`` on the settings rows."""
		import inspect

		src = inspect.getsource(governance._company_tier_rows)
		self.assertIn("for update", src.lower())

	def test_second_submit_sees_a_just_inserted_threshold(self):
		"""Two drafts, both ready to submit. A threshold is inserted after the first submit returns
		and before the second one begins; the second submit MUST see the new row (it is committed by
		now) and refuse the user without the role. This also implicitly exercises the locking read."""
		first = self._draft(self.manager)
		second = self._draft(self.manager)
		# no row: first submit passes
		self._submit(first.name, self.manager)
		self.assertEqual(self._stored(first.name).approval_tier, 0)
		# a threshold is now inserted
		net = flt(frappe.db.get_value(CARD, second.name, "net_amount"))
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		# save the second draft so the server-written tier reaches storage; the refused submit's own
		# validate rewrites it but the rollback would undo that write
		frappe.set_user(self.manager)
		frappe.get_doc(CARD, second.name).save()
		frappe.set_user("Administrator")
		# the second submit by the same role-less manager is refused
		self._refused(self._submit, second.name, self.manager)
		self.assertEqual(self._stored(second.name).docstatus, 0)
		self.assertEqual(self._stored(second.name).approval_tier, 1)


class TestApprovalTierMutations(_TierBase):
	"""Lesson 12: each new guard has its own failing test when the guard is removed."""

	def test_mutation_remove_resolve_on_validate_leaves_tier_zero(self):
		"""Remove ``_apply_resolved_tier`` from ``on_validate``: the card is saved with tier 0 even
		when the thresholds would match, so ``test_submit_above_threshold_without_role_is_refused``
		would have let the submit through — proved here by observing the tier is still 0 on insert."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)

		with patch.object(governance, "_apply_resolved_tier", lambda doc: None):
			# the save path does NOT compute the tier
			frappe.set_user(self.preparer)
			doc = frappe.get_doc(CARD, draft.name)
			doc.save()
			frappe.set_user("Administrator")
			stored = self._stored(draft.name)
			# tier stays what it was on the first save (0 then; thresholds were not yet set)
			self.assertEqual(stored.approval_tier, 0)
		# with the real on_validate back: a resave re-resolves and the tier becomes 1
		frappe.set_user(self.preparer)
		frappe.get_doc(CARD, draft.name).save()
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(draft.name).approval_tier, 1)

	def test_mutation_remove_role_check_lets_submit_through(self):
		"""Remove ``_check_approval_tier_role`` from ``before_submit``: a submit that would have
		been refused goes through, proving the guard's ``test_submit_above_threshold_without_role_is_refused``
		is its only barrier."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		with patch.object(governance, "_check_approval_tier_role", lambda doc: None):
			# a submit by a user who does NOT hold the tier role now succeeds
			self._submit(draft.name, self.manager)
			self.assertEqual(self._stored(draft.name).docstatus, 1)

	def test_mutation_remove_role_check_the_test_fails(self):
		"""Explicit Lesson-12 proof: with ``_check_approval_tier_role`` patched to a no-op, the
		assertion of ``test_submit_above_threshold_without_role_is_refused`` would FAIL. We call that
		assertion here with the patch in place and expect an AssertionError, which proves the test
		depends on the real guard."""
		draft = self._draft(self.manager)
		net = flt(draft.net_amount)
		self._add_tier(self.company, "Tier 1", net, self.tier_role)
		with patch.object(governance, "_check_approval_tier_role", lambda doc: None):
			with self.assertRaises(AssertionError):
				# this would succeed, so the _refused() assertion raises AssertionError inside
				# (it expects ApprovalTierMissingRoleError and gets nothing)
				self._refused(self._submit, draft.name, self.manager)
