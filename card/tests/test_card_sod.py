# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-143 (FR-006, WP-D1; #35, #51, #123): separation of duties on the monthly card.

The card's approval is its submit. Proven here: the server-written fields (``edited_by``, ``submitted_by``,
``approved_by``, ``approved_on``, ``self_approved``) on every route (form save and submit, REST insert with
docstatus 1, ``frappe.client.submit``/``set_value``, REST PUT, savedocs, bulk update, bulk submit and bulk
cancel); the per-company ``card_approval_rule`` (Warn only by default, Refuse when set, no role exempt,
Administrator included); the amendment chain; the legacy card without an editor list; the rule per company and its
company scope in Card Settings; the default flow is unchanged. All data is per-test and rolled back."""

from unittest.mock import patch

import frappe
import frappe.client
from frappe.utils import flt

from card import governance
from card.cancel_reason import CancelChangesDocumentError
from card.tests.cancel_reason import TEST_REASON, store_reason, with_reason
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase

CARD = "Card Monthly Card"
SETTINGS = {"parent": "Card Settings", "parenttype": "Card Settings", "parentfield": "company_settings"}
SELF_APPROVAL = "another user must submit (approve) it"
FORGED = {"approved_by": "Guest", "submitted_by": "Guest", "self_approved": 1, "edited_by": "Guest"}


class TestCardSoD(_CustomerCardsBase):
	def setUp(self):
		super().setUp()
		self.preparer = self._user("prep", ("Card User",))
		self.manager = self._user("mgr", ("Card Manager",))
		self.manager2 = self._user("mgr2", ("Card Manager",))
		self._set_rule(self.company, None)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict(docs=[])
		super().tearDown()
		frappe.clear_document_cache("Card Settings", "Card Settings")

	# ---------- builders ----------
	def _user(self, prefix, roles, company=None):
		email = f"sod-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "SoD " + prefix,
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
		"""The company's row in Card Settings > Company settings, with ``rule`` (None = empty)."""
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

	def _stored(self, name):
		return frappe.db.get_value(
			CARD,
			name,
			[
				"docstatus",
				"owner",
				"edited_by",
				"submitted_by",
				"approved_by",
				"approved_on",
				"self_approved",
			],
			as_dict=True,
		)

	def _refused(self, fn, *args, error=frappe.PermissionError, message=SELF_APPROVAL, **kwargs):
		"""``fn`` fails with ``error``; a separation-of-duties refusal by default (its message is checked, so a
		missing permission elsewhere never passes for it)."""
		frappe.db.savepoint("card_sod")
		frappe.clear_messages()
		try:
			with self.assertRaises(error) as raised:
				fn(*args, **kwargs)
			if message:
				text = str(raised.exception) + " ".join(str(m) for m in frappe.get_message_log())
				self.assertIn(message, text)
		finally:
			frappe.db.rollback(save_point="card_sod")
			frappe.set_user("Administrator")

	# ---------- schema and wiring ----------
	def test_fields_are_server_only_and_hooks_are_wired(self):
		meta = frappe.get_meta(CARD)
		for field in governance.SERVER_FIELDS:
			df = meta.get_field(field)
			self.assertEqual((df.read_only, df.no_copy, df.allow_on_submit), (1, 1, 0), field)
		events = frappe.get_hooks("doc_events")[CARD]
		self.assertIn("card.governance.on_validate", events["validate"])
		self.assertIn("card.governance.before_submit", events["before_submit"])
		self.assertIn("card.governance.before_update_after_submit", events["before_update_after_submit"])
		self.assertIn("card.governance.before_cancel", events["before_cancel"])
		# the source events are kept, in their order, before the new ones
		self.assertEqual(events["before_cancel"][0], "card.cancel_reason.before_cancel")
		self.assertIn("card.period_lock.on_validate", events["validate"])
		df = frappe.get_meta("Card Company Settings").get_field(governance.RULE_FIELD)
		self.assertEqual(df.default, governance.RULE_WARN)
		self.assertEqual(df.options.split("\n"), [governance.RULE_WARN, governance.RULE_REFUSE])

	# ---------- default: Warn only ----------
	def test_default_flow_unchanged_and_recorded(self):
		draft = self._draft()
		self.assertEqual(self._stored(draft.name).edited_by, self.preparer)
		card = self._submit(draft.name, self.manager)
		stored = self._stored(card.name)
		self.assertEqual(stored.docstatus, 1)
		self.assertEqual((stored.submitted_by, stored.approved_by), (self.manager, self.manager))
		self.assertTrue(stored.approved_on)
		self.assertEqual(stored.self_approved, 0)
		self.assertEqual(stored.edited_by, self.preparer)  # a plain submit is not an edit
		self.assertEqual(flt(card.net_amount), flt(16 * 75.0, 2))  # amounts unchanged

	def test_no_rule_row_and_empty_rule_are_warn(self):
		frappe.db.delete("Card Company Settings", {**SETTINGS, "company": self.company})
		self.assertEqual(governance.approval_rule(self.company), governance.RULE_WARN)
		self.assertEqual(governance.approval_rule(None), governance.RULE_WARN)
		self._set_rule(self.company, "")
		self.assertEqual(governance.approval_rule(self.company), governance.RULE_WARN)

	def test_warn_lets_the_creator_submit_and_marks_it(self):
		draft = self._draft(self.manager)
		frappe.clear_messages()
		self._submit(draft.name, self.manager)
		stored = self._stored(draft.name)
		self.assertEqual((stored.docstatus, stored.self_approved, stored.approved_by), (1, 1, self.manager))
		self.assertTrue(
			any("marked for review" in str(m) for m in frappe.get_message_log()), frappe.get_message_log()
		)

	# ---------- Refuse ----------
	def test_refuse_stops_the_creator_and_the_editor(self):
		self._set_rule(self.company, governance.RULE_REFUSE)
		own = self._draft(self.manager)
		self._refused(self._submit, own.name, self.manager)
		self.assertEqual(self._stored(own.name).docstatus, 0)
		# an editor of another user's draft
		edited = self._draft()
		frappe.set_user(self.manager)
		doc = frappe.get_doc(CARD, edited.name)
		doc.days[0].working_hours = 6
		doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(edited.name).edited_by.split("\n"), [self.preparer, self.manager])
		self._refused(self._submit, edited.name, self.manager)
		# another manager approves both
		for name in (own.name, edited.name):
			self._submit(name, self.manager2)
			stored = self._stored(name)
			self.assertEqual(
				(stored.docstatus, stored.approved_by, stored.self_approved), (1, self.manager2, 0)
			)

	def test_administrator_is_not_exempt(self):
		self._set_rule(self.company, governance.RULE_REFUSE)
		draft = self._draft("Administrator")
		self._refused(self._submit, draft.name, "Administrator")
		self._submit(draft.name, self.manager)
		self.assertEqual(self._stored(draft.name).docstatus, 1)

	# ---------- REST and frappe.client routes ----------
	def test_rest_insert_with_docstatus_1(self):
		values = {**self._new().as_dict(), "docstatus": 1, **FORGED}
		self._set_rule(self.company, governance.RULE_REFUSE)
		frappe.set_user(self.manager)
		self._refused(frappe.client.insert, frappe.as_json(values))
		self._set_rule(self.company, None)
		frappe.set_user(self.manager)
		reply = frappe.client.insert(frappe.as_json({**self._new().as_dict(), "docstatus": 1, **FORGED}))
		frappe.set_user("Administrator")
		stored = self._stored(reply["name"])
		self.assertEqual(stored.docstatus, 1)
		self.assertEqual(
			(stored.edited_by, stored.approved_by, stored.self_approved), (self.manager,) * 2 + (1,)
		)

	def test_rest_v1_insert_with_docstatus_1(self):
		from frappe.api import v1

		self._set_rule(self.company, governance.RULE_REFUSE)
		frappe.set_user(self.manager)
		frappe.local.form_dict = frappe._dict(data=frappe.as_json({**self._new().as_dict(), "docstatus": 1}))
		self._refused(v1.create_doc, CARD)

	def test_submit_request_that_changes_the_draft_is_an_edit(self):
		self._set_rule(self.company, governance.RULE_REFUSE)
		draft = self._draft()
		frappe.set_user(self.manager)
		values = frappe.get_doc(CARD, draft.name).as_dict()
		values["days"][1]["working_hours"] = 3
		self._refused(frappe.client.submit, values)
		frappe.set_user(self.manager)
		values = frappe.get_doc(CARD, draft.name).as_dict()
		values["days"].append(_days([0, 0, 5])[2])
		self._refused(frappe.client.submit, values)
		# the unchanged draft through the same route is an approval by a non-preparer
		frappe.set_user(self.manager)
		frappe.client.submit(frappe.get_doc(CARD, draft.name).as_dict())
		frappe.set_user("Administrator")
		stored = self._stored(draft.name)
		self.assertEqual(
			(stored.docstatus, stored.approved_by, stored.edited_by), (1, self.manager, self.preparer)
		)

	def test_rest_put_submit_by_the_creator(self):
		from frappe.api import v1

		self._set_rule(self.company, governance.RULE_REFUSE)
		draft = self._draft(self.manager)
		frappe.set_user(self.manager)
		frappe.local.form_dict = frappe._dict(data=frappe.as_json({"docstatus": 1, **FORGED}))
		self._refused(v1.update_doc, CARD, draft.name)
		self.assertEqual(self._stored(draft.name).docstatus, 0)

	def test_client_values_are_never_kept_on_a_draft(self):
		draft = self._draft()
		frappe.set_user(self.manager)
		for field, value in FORGED.items():
			frappe.client.set_value(CARD, draft.name, field, value)
		values = frappe.get_doc(CARD, draft.name).as_dict()
		values.update({**FORGED, "owner": self.manager2, "approved_on": "2026-01-01 00:00:00"})
		frappe.client.save(values)
		frappe.set_user("Administrator")
		stored = self._stored(draft.name)
		self.assertEqual(stored.owner, self.preparer)  # the creator is the stored one
		self.assertEqual(stored.edited_by.split("\n"), [self.preparer, self.manager])
		self.assertFalse(
			stored.approved_by or stored.submitted_by or stored.approved_on or stored.self_approved
		)

	def test_savedocs_submit_by_an_editor(self):
		from frappe.desk.form.save import savedocs

		self._set_rule(self.company, governance.RULE_REFUSE)
		draft = self._draft()
		frappe.set_user(self.manager)
		savedocs(frappe.as_json(frappe.get_doc(CARD, draft.name).as_dict()), "Save")
		self._refused(savedocs, frappe.as_json(frappe.get_doc(CARD, draft.name).as_dict()), "Submit")
		frappe.set_user(self.manager2)
		savedocs(frappe.as_json({**frappe.get_doc(CARD, draft.name).as_dict(), **FORGED}), "Submit")
		frappe.set_user("Administrator")
		stored = self._stored(draft.name)
		self.assertEqual((stored.docstatus, stored.approved_by, stored.self_approved), (1, self.manager2, 0))

	# ---------- after submit: update and cancel on every route ----------
	def _approved(self):
		draft = self._draft()
		return self._submit(draft.name, self.manager)

	def _approval(self, name):
		s = self._stored(name)
		return (s.submitted_by, s.approved_by, str(s.approved_on), s.self_approved, s.edited_by)

	def test_update_after_submit_keeps_the_approval(self):
		from frappe.api import v1

		card = self._approved()
		before = self._approval(card.name)
		frappe.set_user(self.manager)
		for field, value in FORGED.items():
			frappe.client.set_value(CARD, card.name, field, value)
		frappe.local.form_dict = frappe._dict(data=frappe.as_json(FORGED))
		v1.update_doc(CARD, card.name)
		frappe.set_user("Administrator")
		self.assertEqual(self._approval(card.name), before)

	def test_bulk_routes(self):
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		self._set_rule(self.company, governance.RULE_REFUSE)
		card = self._approved()
		before = self._approval(card.name)
		own = self._draft(self.manager)
		frappe.set_user(self.manager)
		# the bulk action commits after each document and rolls back a failure: kept inside the test transaction
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			# bulk update of the approval fields on a submitted card: kept
			self.assertEqual(submit_cancel_or_update_docs(CARD, [card.name], "update", FORGED), [])
			# bulk submit of his own draft: refused (reported as failed)
			self.assertEqual(submit_cancel_or_update_docs(CARD, [own.name], "submit"), [own.name])
			# bulk cancel without a reason (FR-123) or with forged approval values: refused
			self.assertEqual(submit_cancel_or_update_docs(CARD, [card.name], "cancel"), [card.name])
			self.assertEqual(
				submit_cancel_or_update_docs(CARD, [card.name], "update", {"docstatus": 2, **FORGED}),
				[card.name],
			)
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(own.name).docstatus, 0)
		self.assertEqual(self._stored(card.name).docstatus, 1)
		self.assertEqual(self._approval(card.name), before)
		# a bulk cancel of a card with its reason stored keeps the approval
		store_reason(CARD, card.name)
		frappe.set_user(self.manager)
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			self.assertEqual(submit_cancel_or_update_docs(CARD, [card.name], "cancel"), [])
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(card.name).docstatus, 2)
		self.assertEqual(self._approval(card.name), before)

	def test_cancel_by_rest_put_and_savedocs_with_forged_values(self):
		from frappe.api import v1
		from frappe.desk.form.save import savedocs

		card = self._approved()
		before = self._approval(card.name)
		frappe.set_user(self.manager)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json({"docstatus": 2, "cancel_reason": TEST_REASON, **FORGED})
		)
		self._refused(v1.update_doc, CARD, card.name, error=CancelChangesDocumentError, message=None)
		self.assertEqual(self._stored(card.name).docstatus, 1)
		self.assertEqual(self._approval(card.name), before)
		# the Desk cancel (savedocs "Cancel") with forged approval values: the reason is stored first, as for a
		# Desk cancel request built from the stored record (FR-123 helper). Depending on the Frappe version,
		# savedocs either applies the sent values (FR-123 then refuses the change) or cancels the stored record
		# (the sent values never reach it); either way the stored approval is kept
		store_reason(CARD, card.name)
		frappe.set_user(self.manager)
		forged = {**frappe.get_doc(CARD, card.name).as_dict(), **FORGED, "cancel_reason": TEST_REASON}
		frappe.db.savepoint("card_sod_savedocs")
		try:
			savedocs(frappe.as_json(forged), "Cancel")
		except CancelChangesDocumentError:
			frappe.db.rollback(save_point="card_sod_savedocs")
		frappe.set_user("Administrator")
		self.assertEqual(self._approval(card.name), before)
		# a plain cancel keeps the approval and its preparers
		if self._stored(card.name).docstatus == 1:
			frappe.set_user(self.manager)
			with_reason(frappe.get_doc(CARD, card.name)).cancel()
			frappe.set_user("Administrator")
		self.assertEqual(self._stored(card.name).docstatus, 2)
		self.assertEqual(self._approval(card.name), before)

	# ---------- amendment chain and legacy cards ----------
	def _amend(self, name, user):
		frappe.set_user(user)
		try:
			original = frappe.get_doc(CARD, name)
			amended = frappe.copy_doc(original)
			amended.amended_from = name
			amended.docstatus = 0
			return amended.insert()
		finally:
			frappe.set_user("Administrator")

	def test_amendment_chain_preparers(self):
		self._set_rule(self.company, governance.RULE_REFUSE)
		# the first card: created by manager2 (a preparer), approved by manager
		first = self._draft(self.manager2)
		self._submit(first.name, self.manager)
		frappe.set_user(self.manager)
		with_reason(frappe.get_doc(CARD, first.name)).cancel()
		# amended by a Card User; amended again after a cancel
		second = self._amend(first.name, self.preparer)
		self.assertFalse(self._stored(second.name).approved_by)  # no copy
		self.assertEqual(self._stored(second.name).edited_by, self.preparer)
		self.assertEqual(
			governance.card_preparers(frappe.get_doc(CARD, second.name)), {self.manager2, self.preparer}
		)
		self._refused(self._submit, second.name, self.manager2)
		# the approver of the original is not a preparer of the correction
		self._submit(second.name, self.manager)
		frappe.set_user(self.manager)
		with_reason(frappe.get_doc(CARD, second.name)).cancel()
		third = self._amend(second.name, self.preparer)
		self._refused(self._submit, third.name, self.manager2)  # two levels up
		self._submit(third.name, self.manager)
		self.assertEqual(self._stored(third.name).docstatus, 1)

	def test_legacy_draft_without_editors(self):
		self._set_rule(self.company, governance.RULE_REFUSE)
		draft = self._draft()
		# a draft saved before FR-143: no editor list, last saved by manager
		frappe.db.set_value(
			CARD, draft.name, {"edited_by": None, "modified_by": self.manager}, update_modified=False
		)
		self._refused(self._submit, draft.name, self.manager)
		self._submit(draft.name, self.manager2)
		self.assertEqual(self._stored(draft.name).edited_by, self.manager)

	# ---------- the rule is per company ----------
	def _company_b(self):
		name = "TEST-SOD-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "S" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def test_rule_is_per_company(self):
		other = self._company_b()
		self._set_rule(other, governance.RULE_REFUSE)
		self.assertEqual(governance.approval_rule(other), governance.RULE_REFUSE)
		self.assertEqual(governance.approval_rule(self.company), governance.RULE_WARN)
		draft = self._draft(self.manager)
		self._submit(draft.name, self.manager)  # company A keeps Warn
		self.assertEqual(self._stored(draft.name).self_approved, 1)

	def test_a_company_user_cannot_change_another_companys_rule(self):
		other = self._company_b()
		mine = self._set_rule(self.company, None)
		theirs = self._set_rule(other, None)
		user = self._user("acc", ("Accounts Manager",), company=self.company)
		frappe.set_user(user)
		self._refused(
			frappe.client.set_value,
			"Card Company Settings",
			theirs,
			governance.RULE_FIELD,
			governance.RULE_REFUSE,
			message="not permitted to change the Card settings of company",
		)
		frappe.set_user(user)
		doc = frappe.client.get("Card Settings")
		self.assertNotIn(other, {r["company"] for r in doc["company_settings"]})  # not even shown
		frappe.set_user(user)
		frappe.client.set_value("Card Company Settings", mine, governance.RULE_FIELD, governance.RULE_REFUSE)
		frappe.set_user("Administrator")
		self.assertEqual(governance.approval_rule(self.company), governance.RULE_REFUSE)
		self.assertEqual(governance.approval_rule(other), governance.RULE_WARN)
