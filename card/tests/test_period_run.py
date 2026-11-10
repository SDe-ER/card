# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-147 (#49, WP-S1): the Card Period Run.

Proven here: the build (the billable cards of the company-month, totals per side, version, fingerprints; internal
cards, other months and other companies left out), the mixed month (cards, diesel fills, FR-139 transports) whose
totals per side equal what the posting would bill, a new version on cancel and amend backed by a unique index,
an approval tied to the exact version and snapshot, stale detection (a changed, added or removed source; posting
links and new empty fields excepted), a cancel that changes the run refused, the no-self-approval rule per run
(Warn by default, Refuse when set, never lowered, kept by an amendment, every earlier preparer counts), the
approval fields written by the server on every route (REST insert, ``frappe.client.set_value``, REST PUT,
savedocs, bulk update, bulk cancel), the company isolation (record, list, endpoints, amendment), the money
permlevel, the GET endpoint writing nothing, and the one-active-run guard under two concurrent requests. No GL,
invoice or source document is written by a run. All data is per-test and rolled back, except in the concurrency case."""

from unittest.mock import patch

import frappe
from frappe.client import insert as rest_insert
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.doctype.equipment_transport.equipment_transport import record_financial_decision
from card.company_scope import company_query_conditions, has_company_permission
from card.constants import DIR_RENTED_IN
from card.gl import period_run, preflight
from card.gl.posting import build_monthly_posting, preview_monthly_posting
from card.tests.cancel_reason import with_reason
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase
from card.tests.test_posting_preview import _PreviewBase
from card.tests.test_s3_posting import _leaf_under
from card.tests.transport_parties import as_recorded_before_p12, company_paid

RUN = "Card Period Run"
CARD = "Card Monthly Card"
TRANSPORT = "Equipment Transport"
MONTH, YEAR = "09", 2026


class TestPeriodRun(_CustomerCardsBase):
	def setUp(self):
		super().setUp()
		self.preparer = self._user("prep", ("Card Manager",))
		self.preparer2 = self._user("prep2", ("Card Manager",))
		self.accountant = self._user("acc", ("Accounts Manager",))
		self.accountant2 = self._user("acc2", ("Accounts Manager",))
		self.operator = self._user("op", ("Card Operator",))
		self.rented = self._card(self._equipment(), [10, 10])  # supplier side: 20 h x 75 = 1500
		self.sub = self._card(self._sub_rental(), [10])  # both sides: 750 / 1200
		self.internal = self._card(self._equipment("ملك"), [10])  # not billed: left out

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# ---------- builders ----------
	def _user(self, prefix, roles, company=None):
		email = f"pr-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Period run " + prefix,
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

	def _card(self, eq, hours, month=MONTH, year=YEAR, submit=True):
		c = frappe.new_doc(CARD)
		c.update(
			{"equipment": eq.name, "project": self.project, "shift": "نهاري", "month": month, "year": year}
		)
		for row in _days(hours, year=year, month=int(month)):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		return c.name

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _build(self, user=None, company=None, month=MONTH, year=YEAR):
		name = self._as(
			user or self.preparer, period_run.build_run, company or self.company, month, str(year)
		)
		return frappe.get_doc(RUN, name)

	def _submitted(self, user=None):
		run = self._build(user)
		self._as(user or self.preparer, lambda: frappe.get_doc(RUN, run.name).submit())
		return frappe.get_doc(RUN, run.name)

	def _set_status(self, run, status, user, reason=None):
		def go():
			doc = frappe.get_doc(RUN, run.name)
			doc.approval_status = status
			if reason is not None:
				doc.return_reason = reason
			doc.save()
			return doc

		return self._as(user, go)

	def _approved(self):
		return self._set_status(self._submitted(), period_run.APPROVED, self.accountant)

	def _cancel(self, run, user=None):
		self._as(user or self.preparer, lambda: frappe.get_doc(RUN, run.name).cancel())

	def _amend(self, run, user=None):
		def go():
			doc = frappe.copy_doc(frappe.get_doc(RUN, run.name))
			doc.amended_from = run.name
			doc.docstatus = 0
			return doc.insert()

		return self._as(user or self.preparer, go)

	def _stored(self, name, *fields):
		return frappe.db.get_value(RUN, name, list(fields) or ["docstatus", "approval_status"], as_dict=True)

	def _company_b(self):
		name = "TEST-PR-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "P" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _raw_card(self, company, name, **values):
		doc = frappe.new_doc(CARD)
		doc.update(
			{
				"company": company,
				"month": MONTH,
				"year": YEAR,
				"card_direction": DIR_RENTED_IN,
				"net_amount": 999,
				"docstatus": 1,
				**values,
			}
		)
		doc.name = name
		doc.db_insert()
		return name

	def _change_card(self, name):
		"""A change through the card's own allow-on-submit route is not needed: any stored change counts."""
		frappe.db.set_value(CARD, name, "total_working_hours", 99)

	# ---------- build ----------
	def test_build_snapshots_the_billable_cards_of_the_month(self):
		other_month = self._card(self._equipment(), [5], month="04")
		run = self._build()
		cards = {r.source_name: r for r in run.sources}
		self.assertIn(self.rented, cards)
		self.assertIn(self.sub, cards)
		self.assertNotIn(self.internal, cards)
		self.assertNotIn(other_month, cards)
		self.assertEqual(run.version, 1)
		self.assertEqual(run.docstatus, 0)
		self.assertEqual(run.approval_status, period_run.PENDING)
		self.assertEqual(flt(cards[self.rented].supplier_amount), 1500.0)
		self.assertEqual(flt(cards[self.rented].customer_amount), 0.0)
		self.assertEqual(flt(cards[self.sub].supplier_amount), 750.0)
		self.assertEqual(flt(cards[self.sub].customer_amount), 1200.0)
		self.assertEqual(cards[self.sub].customer, self.customer)
		self.assertEqual(flt(run.supplier_total), flt(sum(flt(r.supplier_amount) for r in run.sources), 2))
		self.assertEqual(flt(run.customer_total), flt(sum(flt(r.customer_amount) for r in run.sources), 2))
		self.assertEqual(run.source_count, len(run.sources))
		self.assertEqual(run.currency, frappe.db.get_value("Company", self.company, "default_currency"))
		for row in run.sources:
			self.assertEqual(len(row.content_hash), 64)
			self.assertEqual(
				row.source_modified, frappe.db.get_value(row.source_doctype, row.source_name, "modified")
			)
		self.assertTrue(period_run.check_current(run).current)

	def test_client_rows_and_totals_are_never_kept(self):
		def go():
			doc = frappe.new_doc(RUN)
			doc.update(
				{
					"company": self.company,
					"month": MONTH,
					"year": YEAR,
					"version": 7,
					"supplier_total": 1,
					"snapshot_hash": "forged",
				}
			)
			doc.append(
				"sources",
				{
					"source_doctype": CARD,
					"source_name": self.internal,
					"supplier_amount": 5,
					"content_hash": "x",
				},
			)
			return doc.insert()

		run = self._as(self.preparer, go)
		self.assertEqual(run.version, 1)
		self.assertNotIn(self.internal, [r.source_name for r in run.sources])
		self.assertNotEqual(run.snapshot_hash, "forged")
		self.assertGreater(flt(run.supplier_total), 1)

	def test_draft_save_rebuilds_the_snapshot(self):
		run = self._build()
		late = self._card(self._equipment(), [3])
		self.assertEqual(period_run.check_current(frappe.get_doc(RUN, run.name)).added, [late])
		again = self._build()  # build_run saves the active draft again
		self.assertEqual(again.name, run.name)
		self.assertEqual(again.version, 1)
		self.assertIn(late, [r.source_name for r in again.sources])
		self.assertTrue(period_run.check_current(again).current)

	def test_a_month_without_billable_cards_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._build(month="05")

	def test_the_run_writes_no_accounting_document(self):
		watched = ("GL Entry", "Purchase Invoice", "Sales Invoice", "Journal Entry", "GL Posting Log")
		before = {d: frappe.db.count(d) for d in watched}
		cards_before = {n: frappe.db.get_value(CARD, n, "modified") for n in (self.rented, self.sub)}
		self._approved()
		self.assertEqual({d: frappe.db.count(d) for d in watched}, before)
		self.assertEqual({n: frappe.db.get_value(CARD, n, "modified") for n in cards_before}, cards_before)

	# ---------- versions ----------
	def test_one_active_run_per_company_and_month(self):
		run = self._submitted()
		with self.assertRaises(frappe.DuplicateEntryError):
			self._build()

		def second():
			return frappe.get_doc(
				{"doctype": RUN, "company": self.company, "month": MONTH, "year": YEAR}
			).insert()

		with self.assertRaises(frappe.DuplicateEntryError):
			self._as(self.preparer, second)
		self._cancel(run)
		self.assertEqual(self._build().version, 2)

	def test_cancel_and_amend_is_a_new_version(self):
		first = self._approved()
		self._change_card(self.rented)
		self._cancel(first)
		second = self._amend(first)
		self.assertEqual(second.amended_from, first.name)
		self.assertEqual(second.version, 2)
		self.assertEqual(second.approval_status, period_run.PENDING)
		self.assertFalse(second.approved_by or second.approved_hash or second.approved_version)
		self.assertTrue(period_run.check_current(second).current)
		# build_run after a cancel amends the latest cancelled run too
		self._as(self.preparer, lambda: frappe.get_doc(RUN, second.name).submit())
		self._cancel(second)
		third = self._build()
		self.assertEqual((third.amended_from, third.version), (second.name, 3))

	def test_company_and_month_of_a_saved_run_cannot_change(self):
		run = self._build()

		def go():
			doc = frappe.get_doc(RUN, run.name)
			doc.month = "04"
			doc.save()

		with self.assertRaises(frappe.ValidationError):
			self._as(self.preparer, go)

	# ---------- approval tied to the version ----------
	def test_approval_records_the_version_and_snapshot(self):
		run = self._approved()
		self.assertEqual(run.approval_status, period_run.APPROVED)
		self.assertEqual(run.approved_by, self.accountant)
		self.assertEqual(run.approved_version, run.version)
		self.assertEqual(run.approved_hash, run.snapshot_hash)
		self.assertEqual(run.self_approved, 0)
		self.assertEqual(period_run.approved_run(self.company, MONTH, YEAR), run.name)
		state = period_run.run_state(run)
		self.assertTrue(state.current and state.approval_valid)

	def test_change_after_approval_voids_the_approval(self):
		run = self._approved()
		self._change_card(self.sub)
		state = period_run.run_state(frappe.get_doc(RUN, run.name))
		self.assertFalse(state.current)
		self.assertFalse(state.approval_valid)
		self.assertEqual(state.changed, [self.sub])
		self.assertIsNone(period_run.approved_run(self.company, MONTH, YEAR))
		# the new version needs its own approval
		self._cancel(run)
		second = self._as(self.preparer, lambda: frappe.get_doc(RUN, self._amend(run).name).submit())
		self.assertIsNone(period_run.approved_run(self.company, MONTH, YEAR))
		approved = self._set_status(second, period_run.APPROVED, self.accountant)
		self.assertEqual((approved.approved_version, approved.version), (2, 2))
		self.assertEqual(period_run.approved_run(self.company, MONTH, YEAR), approved.name)

	def test_approval_is_not_valid_for_another_version(self):
		run = self._approved()
		frappe.db.set_value(RUN, run.name, "approved_version", run.version + 1, update_modified=False)
		self.assertIsNone(period_run.approved_run(self.company, MONTH, YEAR))
		frappe.db.set_value(
			RUN, run.name, {"approved_version": run.version, "approved_hash": "0" * 64}, update_modified=False
		)
		self.assertIsNone(period_run.approved_run(self.company, MONTH, YEAR))

	def test_return_needs_a_reason_and_is_final(self):
		run = self._submitted()
		with self.assertRaises(frappe.ValidationError):
			self._set_status(run, period_run.RETURNED, self.accountant, reason=" ")
		returned = self._set_status(run, period_run.RETURNED, self.accountant, reason="Check card hours")
		self.assertEqual(
			(returned.returned_by, returned.return_reason), (self.accountant, "Check card hours")
		)
		with self.assertRaises(frappe.ValidationError):
			self._set_status(run, period_run.APPROVED, self.accountant2)
		with self.assertRaises(frappe.ValidationError):
			self._set_status(run, period_run.PENDING, self.accountant2)
		self.assertIsNone(period_run.approved_run(self.company, MONTH, YEAR))

	def test_only_an_accountant_approves(self):
		run = self._submitted()
		for user in (self.preparer2, self.operator):
			with self.subTest(user=user), self.assertRaises(frappe.PermissionError):
				self._set_status(run, period_run.APPROVED, user)
		self.assertEqual(self._stored(run.name).approval_status, period_run.PENDING)

	# ---------- stale detection ----------
	def test_stale_detection(self):
		run = self._submitted()
		self.assertTrue(period_run.check_current(run).current)
		# posting the month (the card's invoice links) does not make the run stale
		frappe.db.set_value(CARD, self.rented, {"posted": 1, "gl_posting": None}, update_modified=False)
		self.assertTrue(period_run.check_current(run).current)
		# a changed, an added and a removed card do
		self._change_card(self.rented)
		added = self._card(self._equipment(), [2])
		card = with_reason(frappe.get_doc(CARD, self.sub))
		card.cancel()
		state = period_run.check_current(frappe.get_doc(RUN, run.name))
		self.assertFalse(state.current)
		self.assertEqual((state.changed, state.added, state.removed), ([self.rented], [added], [self.sub]))

	def test_stale_run_is_never_approved(self):
		run = self._submitted()
		self._change_card(self.rented)
		with self.assertRaises(frappe.ValidationError):
			self._set_status(run, period_run.APPROVED, self.accountant)
		self.assertEqual(self._stored(run.name).approval_status, period_run.PENDING)

	def test_fingerprint_covers_the_rows(self):
		before = period_run.document_fingerprint(frappe.get_doc(CARD, self.rented))
		row = frappe.get_all("Card Monthly Card Day", filters={"parent": self.rented}, pluck="name", limit=1)[
			0
		]
		frappe.db.set_value("Card Monthly Card Day", row, "working_hours", 9)
		self.assertNotEqual(period_run.document_fingerprint(frappe.get_doc(CARD, self.rented)), before)

	def test_fingerprint_ignores_unlisted_and_new_empty_fields(self):
		"""A field outside the versioned list (here the operator's name) does not count, and a field added to the
		list (as a later DocType field would be) does not change a fingerprint while it is empty: a migration that
		adds fields never makes an approved run stale."""
		run = self._approved()
		before = period_run.document_fingerprint(frappe.get_doc(CARD, self.rented))
		frappe.db.set_value(CARD, self.rented, "operator_name", "Changed " + self.token)
		doc = frappe.get_doc(CARD, self.rented)
		self.assertEqual(period_run.document_fingerprint(doc), before)
		fields, tables = period_run.FINGERPRINT_FIELDS[1][CARD]
		extended = {
			**period_run.FINGERPRINT_FIELDS[1],
			CARD: (
				(*fields, "new_empty_field"),
				{**tables, "days": (*tables["days"], "new_empty_row_field")},
			),
		}
		with patch.dict(period_run.FINGERPRINT_FIELDS, {1: extended}):
			self.assertEqual(period_run.document_fingerprint(doc), before)
			self.assertTrue(period_run.check_current(frappe.get_doc(RUN, run.name)).current)
		self.assertEqual(period_run.approved_run(self.company, MONTH, YEAR), run.name)

	def test_version_is_unique_per_company_and_month(self):
		indexes = frappe.db.sql(
			f"show index from `tab{RUN}` where Key_name = 'unique_company_month_version'", as_dict=True
		)
		self.assertEqual([i.Column_name for i in indexes], ["company", "month", "year", "version"])
		self.assertTrue(all(not i.Non_unique for i in indexes))
		run = self._build()
		twin = frappe.copy_doc(run)
		twin.name = "TEST-PR-TWIN-" + self.token
		twin.version = run.version
		with self.assertRaises((frappe.UniqueValidationError, frappe.DuplicateEntryError)):
			twin.db_insert()

	# ---------- a cancel changes nothing ----------
	def _snapshot_of(self, name):
		return (
			self._stored(
				name, "version", "snapshot_hash", "source_count", "supplier_total", "approval_status"
			),
			frappe.get_all(
				"Card Period Run Source",
				filters={"parent": name},
				fields=["name", "source_name", "content_hash", "supplier_amount", "customer_amount"],
				order_by="idx",
			),
		)

	def _fresh_run(self):
		"""A new submitted run of the month; the previous one (if any) is cancelled first."""
		active = period_run.active_run(self.company, MONTH, YEAR)
		if active:
			self._cancel(frappe._dict(name=active))
		return self._submitted()

	def test_cancel_that_changes_the_run_is_refused_on_rest_put_and_bulk(self):
		"""REST PUT and bulk update apply the client's values to the stored run, so the guard must refuse them."""
		from frappe.api import v1
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		from card.cancel_reason import CancelChangesDocumentError

		for data in (
			{"docstatus": 2, "version": 9},
			{"docstatus": 2, "snapshot_hash": "0" * 64},
			{"docstatus": 2, "source_count": 1},
		):
			run = self._fresh_run()
			before = self._snapshot_of(run.name)
			with self.subTest(route="PUT", data=data):
				frappe.set_user(self.preparer)
				frappe.local.form_dict = frappe._dict(data=frappe.as_json(data))
				with self.assertRaises(CancelChangesDocumentError):
					v1.update_doc(RUN, run.name)
				frappe.set_user("Administrator")
				self.assertEqual(self._stored(run.name).docstatus, 1)
				self.assertEqual(self._snapshot_of(run.name), before)
		run = self._fresh_run()
		before = self._snapshot_of(run.name)
		frappe.set_user(self.preparer)
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			failed = submit_cancel_or_update_docs(RUN, [run.name], "update", {"docstatus": 2, "version": 9})
		frappe.set_user("Administrator")
		self.assertEqual(failed, [run.name])
		self.assertEqual(self._stored(run.name).docstatus, 1)
		self.assertEqual(self._snapshot_of(run.name), before)
		# an unchanged bulk cancel passes and keeps everything
		frappe.set_user(self.preparer)
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			self.assertEqual(submit_cancel_or_update_docs(RUN, [run.name], "cancel"), [])
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(run.name).docstatus, 2)
		self.assertEqual(self._snapshot_of(run.name)[1], before[1])

	def test_cancel_by_savedocs_never_stores_a_changed_run(self):
		"""savedocs "Cancel": depending on the Frappe version it either applies the client document (the guard
		refuses it) or cancels the stored run and ignores the client's changes. Either way nothing the client
		changed is stored."""
		from frappe.desk.form.save import savedocs

		from card.cancel_reason import CancelChangesDocumentError

		def drop_a_row(forged):
			forged["sources"] = forged["sources"][1:]

		for label, change in (
			("header", lambda f: f.update({"version": 9, "snapshot_hash": "0" * 64, "source_count": 1})),
			("row", lambda f: f["sources"][0].update({"content_hash": "0" * 64})),
			("row removed", drop_a_row),
			("level-1 amount", lambda f: f["sources"][0].update({"supplier_amount": 1})),
		):
			run = self._fresh_run()
			before = self._snapshot_of(run.name)
			with self.subTest(change=label):
				frappe.set_user(self.preparer)
				forged = frappe.get_doc(RUN, run.name).as_dict()
				change(forged)
				try:
					savedocs(frappe.as_json(forged), "Cancel")
					refused = False
				except CancelChangesDocumentError:
					refused = True
				frappe.set_user("Administrator")
				stored, rows = self._snapshot_of(run.name)
				self.assertEqual(self._stored(run.name).docstatus, 1 if refused else 2)
				self.assertEqual(stored, before[0])
				self.assertEqual(rows, before[1])

	# ---------- self-approval ----------
	def test_self_approval_warns_by_default(self):
		admin = self._user("sys", ("System Manager",))
		run = self._submitted(user=admin)
		self.assertEqual(run.self_approval_rule, period_run.RULE_WARN)
		approved = self._set_status(run, period_run.APPROVED, admin)
		self.assertEqual((approved.approval_status, approved.self_approved), (period_run.APPROVED, 1))

	def test_self_approval_refused_under_refuse(self):
		admin = self._user("sys", ("System Manager",))
		run = self._build(user=admin)
		self._as(
			admin,
			lambda: (
				frappe.get_doc(RUN, run.name).update({"self_approval_rule": period_run.RULE_REFUSE}).submit()
			),
		)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(run, period_run.APPROVED, admin)
		# an editor and a submitter are preparers too; another accountant approves
		self.assertEqual(
			self._set_status(run, period_run.APPROVED, self.accountant).approved_by, self.accountant
		)

	def test_editor_is_a_preparer(self):
		run = self._build(user=self.preparer)
		# the accountant saves the draft (an edit): he is a preparer now
		self._as(self.accountant, lambda: frappe.get_doc(RUN, run.name).save())
		self._as(
			self.preparer,
			lambda: (
				frappe.get_doc(RUN, run.name).update({"self_approval_rule": period_run.RULE_REFUSE}).submit()
			),
		)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(run, period_run.APPROVED, self.accountant)

	def test_rule_raised_after_submit_and_never_lowered(self):
		run = self._submitted()
		self._as(
			self.accountant,
			lambda: (
				frappe.get_doc(RUN, run.name).update({"self_approval_rule": period_run.RULE_REFUSE}).save()
			),
		)
		self.assertEqual(
			self._stored(run.name, "self_approval_rule").self_approval_rule, period_run.RULE_REFUSE
		)
		with self.assertRaises(frappe.ValidationError):
			self._as(
				self.accountant,
				lambda: (
					frappe.get_doc(RUN, run.name).update({"self_approval_rule": period_run.RULE_WARN}).save()
				),
			)
		with self.assertRaises(frappe.ValidationError):
			self._as(self.preparer, rest_set_value, RUN, run.name, "self_approval_rule", period_run.RULE_WARN)
		self.assertEqual(
			self._stored(run.name, "self_approval_rule").self_approval_rule, period_run.RULE_REFUSE
		)

	def test_amendment_keeps_the_rule_and_every_earlier_preparer(self):
		admin = self._user("sys", ("System Manager",))
		first = self._build(user=admin)
		self._as(
			self.preparer,
			lambda: (
				frappe.get_doc(RUN, first.name)
				.update({"self_approval_rule": period_run.RULE_REFUSE})
				.submit()
			),
		)
		self._cancel(first, user=self.preparer)
		# a second preparer amends and tries to lower the rule on the draft
		second = self._amend(first, user=self.preparer2)
		self.assertEqual(second.self_approval_rule, period_run.RULE_REFUSE)
		self._as(
			self.preparer2,
			lambda: (
				frappe.get_doc(RUN, second.name).update({"self_approval_rule": period_run.RULE_WARN}).submit()
			),
		)
		self.assertEqual(
			self._stored(second.name, "self_approval_rule").self_approval_rule, period_run.RULE_REFUSE
		)
		self.assertEqual(
			period_run.run_preparers(frappe.get_doc(RUN, second.name)), {admin, self.preparer, self.preparer2}
		)
		# the creator of version 1 (a System Manager, an approver role) cannot approve version 2
		with self.assertRaises(frappe.PermissionError):
			self._set_status(second, period_run.APPROVED, admin)
		self.assertEqual(self._set_status(second, period_run.APPROVED, self.accountant).self_approved, 0)

	def test_a_draft_amendment_keeps_its_chain(self):
		"""Frappe checks amended_from on insert only: a client that clears it on a later save (frappe.client.save
		or set_value) must not drop the earlier versions' preparers or rule."""
		from frappe.client import save as rest_save

		admin = self._user("sys", ("System Manager",))
		first = self._build(user=admin)
		self._as(
			admin,
			lambda: (
				frappe.get_doc(RUN, first.name)
				.update({"self_approval_rule": period_run.RULE_REFUSE})
				.submit()
			),
		)
		self._cancel(first, user=self.preparer)
		second = self._amend(first, user=self.preparer2)
		doc = frappe.get_doc(RUN, second.name).as_dict()
		doc.update({"amended_from": None, "self_approval_rule": period_run.RULE_WARN, "version": 1})
		self._as(self.preparer2, rest_save, frappe.as_json(doc))
		self._as(self.preparer2, rest_set_value, RUN, second.name, "amended_from", None)
		self._as(self.preparer2, rest_set_value, RUN, second.name, {"company": self.company, "month": MONTH})
		stored = self._stored(
			second.name, "amended_from", "self_approval_rule", "version", "company", "month"
		)
		self.assertEqual(
			stored,
			{
				"amended_from": first.name,
				"self_approval_rule": period_run.RULE_REFUSE,
				"version": 2,
				"company": self.company,
				"month": MONTH,
			},
		)
		with self.assertRaises(frappe.ValidationError):
			self._as(self.preparer2, rest_set_value, RUN, second.name, "month", "08")
		self._as(self.preparer2, lambda: frappe.get_doc(RUN, second.name).submit())
		# the creator of version 1 is still a preparer of version 2: refused under Refuse
		with self.assertRaises(frappe.PermissionError):
			self._set_status(second, period_run.APPROVED, admin)
		# after submit the link cannot change at all (not allow on submit)
		with self.assertRaises(frappe.ValidationError):
			self._as(self.accountant, rest_set_value, RUN, second.name, "amended_from", None)
		self.assertEqual(self._stored(second.name, "amended_from").amended_from, first.name)
		# the one-active-run guard still sees the month: no second run can start
		with self.assertRaises(frappe.DuplicateEntryError):
			self._build()

	def test_a_fresh_insert_continues_the_chain_on_every_route(self):
		"""Re-review finding 1: a new run created without amended_from (REST insert, Desk New through savedocs,
		frappe.client.insert with a forged lower rule) is linked by the server to the month's latest cancelled run,
		keeps Refuse, and the earlier versions' preparers still count."""
		from frappe.api import v1
		from frappe.desk.form.save import savedocs

		admin = self._user("sys", ("System Manager",))
		first = self._build(user=admin)
		self._as(
			admin,
			lambda: (
				frappe.get_doc(RUN, first.name)
				.update({"self_approval_rule": period_run.RULE_REFUSE})
				.submit()
			),
		)
		self._cancel(first, user=self.preparer)
		values = {
			"doctype": RUN,
			"company": self.company,
			"month": MONTH,
			"year": YEAR,
			"amended_from": None,
			"self_approval_rule": period_run.RULE_WARN,
		}

		def rest_v1():
			# POST /api/resource/Card Period Run: the request body is the document
			with patch.object(v1, "get_request_form_data", return_value=frappe._dict(values)):
				return v1.create_doc(RUN).name

		def desk_new():
			savedocs(frappe.as_json({**values, "__islocal": 1, "name": "new-card-period-run-1"}), "Save")
			return frappe.get_all(
				RUN, filters={"company": self.company, "docstatus": 0}, pluck="name", limit=1
			)[0]

		def client_insert():
			return rest_insert(frappe.as_json(values))["name"]

		previous = first.name
		for version, (route, create) in enumerate(
			(("REST v1", rest_v1), ("Desk New", desk_new), ("frappe.client.insert", client_insert)), start=2
		):
			with self.subTest(route=route):
				name = self._as(self.preparer2, create)
				stored = self._stored(name, "amended_from", "self_approval_rule", "version")
				self.assertEqual(
					stored,
					{
						"amended_from": previous,
						"self_approval_rule": period_run.RULE_REFUSE,
						"version": version,
					},
				)
				self.assertIn(admin, period_run.run_preparers(frappe.get_doc(RUN, name)))
				self._as(self.preparer2, lambda n=name: frappe.get_doc(RUN, n).submit())
				with self.assertRaises(frappe.PermissionError):
					self._set_status(frappe._dict(name=name), period_run.APPROVED, admin)
				self._cancel(frappe._dict(name=name), user=self.preparer2)
				previous = name

	# ---------- forged approval fields, every route ----------
	def test_rest_insert_with_docstatus_1_stays_pending(self):
		data = {
			"doctype": RUN,
			"company": self.company,
			"month": MONTH,
			"year": YEAR,
			"docstatus": 1,
			"approval_status": period_run.APPROVED,
			"approved_by": self.accountant,
			"approved_version": 1,
			"approved_hash": "x",
			"self_approved": 0,
			"submitted_by": self.accountant,
			"edited_by": "",
		}
		name = self._as(self.preparer, rest_insert, frappe.as_json(data))["name"]
		stored = self._stored(
			name,
			"docstatus",
			"approval_status",
			"approved_by",
			"approved_version",
			"approved_hash",
			"submitted_by",
		)
		self.assertEqual(
			stored,
			{
				"docstatus": 1,
				"approval_status": period_run.PENDING,
				"approved_by": None,
				"approved_version": 0,
				"approved_hash": None,
				"submitted_by": self.preparer,
			},
		)
		self.assertIsNone(period_run.approved_run(self.company, MONTH, YEAR))

	def test_set_value_routes_are_checked(self):
		run = self._submitted()
		with self.assertRaises(frappe.PermissionError):
			self._as(self.preparer, rest_set_value, RUN, run.name, "approval_status", period_run.APPROVED)
		for field, value in (
			("approved_by", self.accountant),
			("approved_hash", run.snapshot_hash),
			("approved_version", 1),
		):
			with self.subTest(field=field):
				self._as(self.preparer, rest_set_value, RUN, run.name, field, value)
				self.assertFalse(self._stored(run.name, field)[field])
		self._as(self.accountant, rest_set_value, RUN, run.name, "approval_status", period_run.APPROVED)
		self.assertEqual(self._stored(run.name, "approved_by").approved_by, self.accountant)

	def test_rest_put_and_savedocs_cannot_forge_the_approval(self):
		from frappe.api import v1
		from frappe.desk.form.save import savedocs

		run = self._submitted()
		frappe.set_user(self.preparer)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json(
				{"approved_by": self.preparer, "approved_hash": run.snapshot_hash, "approved_version": 1}
			)
		)
		v1.update_doc(RUN, run.name)
		forged = frappe.get_doc(RUN, run.name).as_dict()
		forged.update(
			{"approved_by": self.preparer, "approved_version": 1, "approved_hash": run.snapshot_hash}
		)
		savedocs(frappe.as_json(forged), "Update")
		frappe.set_user("Administrator")
		stored = self._stored(run.name, "approval_status", "approved_by", "approved_version", "approved_hash")
		self.assertEqual(
			stored,
			{
				"approval_status": period_run.PENDING,
				"approved_by": None,
				"approved_version": 0,
				"approved_hash": None,
			},
		)

	def test_bulk_update_cannot_approve(self):
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		run = self._submitted()
		frappe.set_user(self.preparer)
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			failed = submit_cancel_or_update_docs(
				RUN, [run.name], "update", {"approval_status": period_run.APPROVED}
			)
		frappe.set_user("Administrator")
		self.assertEqual(failed, [run.name])
		self.assertEqual(self._stored(run.name).approval_status, period_run.PENDING)

	def test_cancel_by_rest_put_savedocs_and_bulk_reads_the_stored_approval(self):
		from frappe.api import v1
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs
		from frappe.desk.form.save import savedocs

		run = self._approved()
		frappe.set_user(self.preparer)
		for data in ({"docstatus": 2, "approval_status": period_run.PENDING}, {"docstatus": 2}):
			with self.subTest(data=data):
				frappe.local.form_dict = frappe._dict(data=frappe.as_json(data))
				with self.assertRaises(frappe.PermissionError):
					v1.update_doc(RUN, run.name)
		forged = frappe.get_doc(RUN, run.name).as_dict()
		forged["approval_status"] = period_run.PENDING
		with self.assertRaises(frappe.PermissionError):
			savedocs(frappe.as_json(forged), "Cancel")
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			for action, data in (
				("update", {"docstatus": 2, "approval_status": period_run.PENDING}),
				("cancel", None),
			):
				with self.subTest(action=action):
					self.assertEqual(submit_cancel_or_update_docs(RUN, [run.name], action, data), [run.name])
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(run.name), {"docstatus": 1, "approval_status": period_run.APPROVED})

	def test_cancel_keeps_the_stored_approval_fields(self):
		from frappe.api import v1

		run = self._approved()
		frappe.set_user(self.accountant)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json(
				{
					"docstatus": 2,
					"approved_by": self.operator,
					"self_approved": 1,
					"submitted_by": self.accountant,
				}
			)
		)
		v1.update_doc(RUN, run.name)
		frappe.set_user("Administrator")
		self.assertEqual(
			self._stored(run.name, "docstatus", "approved_by", "self_approved", "submitted_by"),
			{
				"docstatus": 2,
				"approved_by": self.accountant,
				"self_approved": 0,
				"submitted_by": self.preparer,
			},
		)

	def test_stale_approved_run_is_cancelled_by_its_preparer(self):
		run = self._approved()
		self._change_card(self.rented)
		self._cancel(run)
		self.assertEqual(self._stored(run.name).docstatus, 2)

	# ---------- company isolation and money ----------
	def test_cross_company_is_refused(self):
		other = self._company_b()
		self._raw_card(other, "TEST-PR-CB-" + self.token)
		run_b = frappe.new_doc(RUN)
		run_b.update(
			{
				"company": other,
				"month": MONTH,
				"year": YEAR,
				"version": 1,
				"docstatus": 1,
				"approval_status": "Pending",
			}
		)
		run_b.name = "TEST-PR-RB-" + self.token
		run_b.db_insert()
		run_a = self._submitted()
		user = self._user("restricted-acc", ("Accounts Manager", "Card Manager"), company=self.company)
		self.assertTrue(frappe.has_permission(RUN, "read", run_a.name, user=user))
		self.assertFalse(frappe.has_permission(RUN, "read", run_b.name, user=user))
		self.assertFalse(has_company_permission(frappe.get_doc(RUN, run_b.name), "write", user=user))
		condition = company_query_conditions(user=user, doctype=RUN)
		rows = frappe.db.sql(
			f"select name from `tab{RUN}` where name in %(n)s and {condition}",
			{"n": [run_a.name, run_b.name]},
			pluck=True,
		)
		self.assertEqual(rows, [run_a.name])
		with self.assertRaises(frappe.PermissionError):
			self._as(user, rest_set_value, RUN, run_b.name, "approval_status", period_run.APPROVED)
		with self.assertRaises(frappe.PermissionError):
			self._as(user, period_run.build_run, other, MONTH, str(YEAR))
		with self.assertRaises(frappe.PermissionError):
			self._as(user, period_run.period_run_status, other, MONTH, str(YEAR))
		self.assertEqual(self._stored(run_b.name).approval_status, "Pending")
		# nor amend a cancelled run of the other company into its own
		frappe.db.set_value(RUN, run_b.name, "docstatus", 2, update_modified=False)

		def amend():
			return frappe.get_doc(
				{
					"doctype": RUN,
					"company": self.company,
					"month": MONTH,
					"year": YEAR,
					"amended_from": run_b.name,
				}
			).insert()

		self._cancel(run_a)
		with self.assertRaises(frappe.PermissionError):
			self._as(self.preparer, amend)

	def test_status_endpoint_reads_only_and_hides_money_without_level_1(self):
		run = self._approved()
		before = (
			frappe.db.count(RUN),
			frappe.db.get_value(RUN, run.name, "modified"),
			frappe.db.count("Version"),
		)
		state = self._as(self.accountant, period_run.period_run_status, self.company, MONTH, str(YEAR))
		self.assertEqual((state["run"], state["current"], state["approval_valid"]), (run.name, True, True))
		self.assertEqual(flt(state["supplier_total"]), flt(run.supplier_total))
		self.assertEqual(
			(
				frappe.db.count(RUN),
				frappe.db.get_value(RUN, run.name, "modified"),
				frappe.db.count("Version"),
			),
			before,
		)
		with patch.object(frappe.model.meta.Meta, "get_permlevel_access", return_value=[0]):
			hidden = self._as(self.accountant, period_run.period_run_status, self.company, MONTH, str(YEAR))
		self.assertNotIn("supplier_total", hidden)
		self.assertNotIn("customer_total", hidden)
		none = self._as(self.accountant, period_run.period_run_status, self.company, "07", str(YEAR))
		self.assertIsNone(none["run"])

	def test_card_operator_and_card_user_see_no_run(self):
		run = self._submitted()
		card_user = self._user("cu", ("Card User",))
		for user in (self.operator, card_user):
			with self.subTest(user=user):
				self.assertFalse(frappe.has_permission(RUN, "read", run.name, user=user))
				with self.assertRaises(frappe.PermissionError):
					self._as(user, period_run.period_run_status, self.company, MONTH, str(YEAR))
				with self.assertRaises(frappe.PermissionError):
					self._as(user, period_run.build_run, self.company, MONTH, str(YEAR))

	def test_amounts_are_at_permlevel_1_for_card_amount_readers_only(self):
		meta = frappe.get_meta(RUN)
		row_meta = frappe.get_meta("Card Period Run Source")
		for m, fields in (
			(meta, ("supplier_total", "customer_total")),
			(row_meta, ("supplier_amount", "customer_amount")),
		):
			for field in fields:
				self.assertEqual(m.get_field(field).permlevel, 1, field)
		level_1 = {p.role for p in meta.permissions if p.permlevel == 1 and p.read}
		self.assertEqual(level_1, {"System Manager", "Card Manager", "Accounts Manager"})
		card_readers = {p.role for p in frappe.get_meta(CARD).permissions if p.read}
		self.assertTrue(level_1 <= card_readers)
		self.assertNotIn("Card Operator", {p.role for p in meta.permissions})


class TestPeriodRunMixedMonth(_PreviewBase):
	"""Review finding 1: the run covers every source the monthly posting bills (cards, diesel fills, transports,
	FR-139 Post lines), and its totals per side equal what the posting would bill for a mixed month."""

	def setUp(self):
		super().setUp()
		self.inc_transport = _leaf_under(self.company, "Income", "Test Transport Recharge Income")
		self._mode(preflight.TRANSPORT_POSTING_POST)
		frappe.db.set_value("Project", self.project, "customer", self.customer)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _mode(self, value):
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == self.company)
		row.transport_responsibility_posting = value
		row.transport_recharge_income_account = self.inc_transport
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")

	def _transport(self, amount=400):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"date": "2026-09-10",
				"company": self.company,
				"transport_supplier": self.supplier,
				"destination_type": "Project",
				"project": self.project,
				"amount": amount,
			}
		)
		t.append("items", {"card_equipment": self._equipment().name})
		return t

	def _submitted(self, t):
		t.insert(ignore_permissions=True)
		t.submit()
		return t

	def _legacy_transport(self, amount=300):
		t = self._submitted(company_paid(self._transport(amount)))
		as_recorded_before_p12(t.name)
		return t

	def _decided(self, bearer, decision, **values):
		t = company_paid(self._transport())
		t.cost_bearer = bearer
		self._submitted(t)
		email = f"pr-fin-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "PR", "send_welcome_email": 0}
		)
		user.append("roles", {"role": "Accounts Manager"})
		user.insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			record_financial_decision(t.name, decision, **values)
		finally:
			frappe.set_user("Administrator")
		return frappe.get_doc("Equipment Transport", t.name)

	def _posting_sources(self):
		out = {}
		for party_type, party in (("Supplier", self.supplier), ("Customer", self.customer)):
			preview = preview_monthly_posting(self.company, party_type, party, 9, 2026)
			self.assertFalse(preview.blocked, preview.blocked)
			out[party_type] = {(s["doctype"], s["name"]): flt(s["amount"], 2) for s in preview.sources}
		return out

	def _mixed_month(self):
		rented = self._card(self._equipment(), [8], submit=True)
		sub = self._card(self._sub_rental(), [10], submit=True)
		fill = self._fill()
		company_cost = self._submitted(
			company_paid(self._transport(250), basis="Project", cost_project=self.project)
		)
		billed = self._decided(
			"Customer",
			"Bill customer",
			customer=self.customer,
			billing_project=self.project,
			billing_amount=650,
			billing_mode="Monthly invoice",
			billing_reference="CONTRACT-PR",
			confirmed=1,
		)
		recovered = self._decided(
			"Equipment Supplier",
			"Recover from equipment supplier",
			recovery_mode="Deduct from monthly dues",
			recovery_amount=150,
		)
		return frappe._dict(
			rented=rented.name,
			sub=sub.name,
			fill=fill.name,
			company_cost=company_cost.name,
			billed=billed.name,
			recovered=recovered.name,
		)

	def test_totals_equal_what_posting_would_bill(self):
		"""With a VAT-exclusive diesel basis and a supplier without a tax ID, the gross source amounts are what the
		posting books."""
		docs = self._mixed_month()
		snapshot = period_run.build_snapshot(self.company, "09", 2026)
		posting = self._posting_sources()
		rows = {(r["source_doctype"], r["source_name"]): r for r in snapshot.rows}
		supplier = {k: flt(r["supplier_amount"], 2) for k, r in rows.items() if r["supplier_side"]}
		customer = {k: flt(r["customer_amount"], 2) for k, r in rows.items() if r["customer_side"]}
		self.assertEqual(supplier, posting["Supplier"])
		self.assertEqual(customer, posting["Customer"])
		self.assertEqual(snapshot.supplier_total, flt(sum(posting["Supplier"].values()), 2))
		self.assertEqual(snapshot.customer_total, flt(sum(posting["Customer"].values()), 2))
		names = {name for _doctype, name in rows}
		self.assertTrue(set(docs.values()) <= names, set(docs.values()) - names)
		self.assertEqual(
			rows[(TRANSPORT, docs.recovered)]["supplier_amount"], 250.0
		)  # 400 less 150 recovered
		self.assertEqual(rows[(TRANSPORT, docs.billed)]["customer_amount"], 650.0)
		self.assertTrue(rows[(TRANSPORT, docs.billed)]["supplier_side"])

	def test_selection_matches_the_posting_sources_in_hold_and_post(self):
		"""Re-review finding 4: the run's copied filters select exactly the posting's sources of an unposted month,
		in Hold and in Post, on both sides."""
		from card.gl.posting import _customer_cards, _supplier_sources

		docs = self._mixed_month()
		legacy = self._legacy_transport()
		for mode in (preflight.TRANSPORT_POSTING_HOLD, preflight.TRANSPORT_POSTING_POST):
			with self.subTest(mode=mode):
				self._mode(mode)
				selection = period_run._selection(self.company, "09", 2026)
				cards, fills, transports = _supplier_sources(
					self.company, None, "2026-09-01", "2026-09-30", 9, 2026
				)
				expected_supplier = (
					{(CARD, r.name) for r in cards}
					| {("Project Diesel Fill", r.name) for r in fills}
					| {(TRANSPORT, r.name) for r in transports}
				)
				expected_customer = {(CARD, r.name) for r in _customer_cards(self.company, None, 9, 2026)}
				if mode == preflight.TRANSPORT_POSTING_POST:
					expected_customer |= {(TRANSPORT, docs.billed)}
				self.assertEqual({k for k, v in selection.items() if "Supplier" in v}, expected_supplier)
				self.assertEqual({k for k, v in selection.items() if "Customer" in v}, expected_customer)
				self.assertIn((TRANSPORT, legacy.name), expected_supplier)

	def test_vat_basis_and_supplier_tax_id_are_part_of_the_snapshot(self):
		"""Re-review finding 2: the amounts are gross source amounts; the company's diesel VAT basis and the fill
		supplier's VAT registration are stored and a change of either makes the run stale."""
		docs = self._mixed_month()
		run = self._run()
		self.assertEqual(run.diesel_vat_basis, "Exclusive")
		row = next(r for r in run.sources if r.source_name == docs.fill)
		self.assertEqual(
			(row.supplier_vat_registered, flt(row.supplier_amount)), (0, 200.0)
		)  # gross fill amount
		self._set_basis("Inclusive")
		state = period_run.check_current(frappe.get_doc(RUN, run.name))
		self.assertFalse(state.current)
		self.assertTrue(state.vat_basis_changed)
		self._set_basis("Exclusive")
		self.assertTrue(period_run.check_current(frappe.get_doc(RUN, run.name)).current)
		frappe.db.set_value("Supplier", self.supplier, "tax_id", "300000000000003")
		state = period_run.check_current(frappe.get_doc(RUN, run.name))
		self.assertFalse(state.current)
		self.assertEqual(state.changed, [docs.fill])

	def test_hold_leaves_the_responsibility_transports_out(self):
		docs = self._mixed_month()
		legacy = self._legacy_transport()
		self._mode(preflight.TRANSPORT_POSTING_HOLD)
		names = {r["source_name"] for r in period_run.build_snapshot(self.company, "09", 2026).rows}
		self.assertIn(legacy.name, names)
		self.assertFalse({docs.company_cost, docs.billed, docs.recovered} & names)

	def _run(self):
		run = frappe.new_doc(RUN)
		run.update({"company": self.company, "month": "09", "year": 2026})
		run.insert(ignore_permissions=True)
		run.submit()
		return frappe.get_doc(RUN, run.name)

	def test_a_new_fill_or_transport_makes_the_run_stale(self):
		self._mixed_month()
		run = self._run()
		self.assertTrue(period_run.check_current(run).current)
		fill = self._fill(day="2026-09-12")
		self.assertEqual(period_run.check_current(run).added, [fill.name])
		frappe.db.set_value("Project Diesel Fill", fill.name, "docstatus", 2)
		self.assertTrue(period_run.check_current(run).current)
		transport = self._legacy_transport()
		state = period_run.check_current(run)
		self.assertEqual((state.current, state.added), (False, [transport.name]))

	def test_a_changed_transport_decision_makes_the_run_stale(self):
		docs = self._mixed_month()
		run = self._run()
		frappe.db.set_value("Equipment Transport", docs.billed, "billing_amount", 700)
		self.assertEqual(period_run.check_current(run).changed, [docs.billed])

	def test_posting_the_month_keeps_the_run_current(self):
		docs = self._mixed_month()
		run = self._run()
		row = next(r for r in run.sources if r.source_name == docs.fill)
		self.assertEqual(row.supplier_posted, 0)
		build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		state = period_run.check_current(frappe.get_doc(RUN, run.name))
		self.assertTrue(state.current)
		self.assertIn(f"{docs.fill} (Supplier)", state.posted_since)
		live = {r["source_name"]: r for r in period_run.build_snapshot(self.company, "09", 2026).rows}
		self.assertEqual((live[docs.fill]["supplier_posted"], live[docs.billed]["customer_posted"]), (1, 0))


class TestPeriodRunConcurrency(IntegrationTestCase):
	"""Two requests that build a run of the same company-month at the same time never leave two active runs (the
	Company row lock and the locking read). Modelled on test_daily_log's concurrency case; the records are
	committed and removed in tearDown."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.has_snapshot_isolation = bool(frappe.db.sql("show variables like 'innodb_snapshot_isolation'"))

	def setUp(self):
		from card.tests import test_assignment_overlap_concurrency as model

		self.model = model
		self.token = frappe.generate_hash(length=8)
		# a company-month no other test uses
		self.month, self.year = (
			"%02d" % (int(self.token[:4], 16) % 12 + 1),
			2150 + int(self.token[4:6], 16) % 50,
		)
		self.card = "TEST-PR-RACE-" + self.token
		self.started = self._committed(frappe.utils.now)
		self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)
		self.assertEqual(self._committed(self._leftovers), 0, "synthetic records left behind")

	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	def _make_records(self):
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		doc = frappe.new_doc(CARD)
		doc.update(
			{
				"company": self.company,
				"month": self.month,
				"year": self.year,
				"card_direction": DIR_RENTED_IN,
				"net_amount": 100,
				"docstatus": 1,
			}
		)
		doc.name = self.card
		doc.db_insert()

	def _insert_run(self):
		frappe.get_doc(
			{"doctype": RUN, "company": self.company, "month": self.month, "year": self.year}
		).insert(ignore_permissions=True)

	def _filters(self):
		return {"company": self.company, "month": self.month, "year": self.year}

	def _live_runs(self):
		return self._committed(
			lambda: frappe.get_all(RUN, filters={**self._filters(), "docstatus": ["<", 2]}, pluck="name")
		)

	def _remove_records(self):
		names = frappe.get_all(RUN, filters=self._filters(), pluck="name")
		for name in names:
			self.model._delete(RUN, name)
		frappe.db.delete(CARD, {"name": self.card})
		mine = [*names, self.card]
		since = {"creation": [">=", self.started]}
		frappe.db.delete("Version", {"docname": ["in", mine], **since})
		frappe.db.delete("Comment", {"reference_name": ["in", mine], **since})
		frappe.db.delete("Deleted Document", {"deleted_name": ["in", mine], **since})

	def _leftovers(self):
		return frappe.db.count(RUN, self._filters()) + frappe.db.count(CARD, {"name": self.card})

	def test_two_concurrent_builds_leave_one_active_run(self):
		_one, two = self._race(self._insert_run, self._insert_run)
		self.assertFalse(two.committed, "the second request was not refused")
		self.assertIsInstance(two.error, frappe.DuplicateEntryError, repr(two.error))
		self.assertEqual(len(self._live_runs()), 1)

	def test_with_the_server_snapshot_setting(self):
		_one, two = self._race(self._insert_run, self._insert_run, snapshot_isolation=None)
		self.assertFalse(two.committed)
		self.assertIsInstance(
			two.error, (frappe.DuplicateEntryError, *self.model.SAFE_ERRORS), repr(two.error)
		)
		self.assertEqual(len(self._live_runs()), 1)


def _bind_model_helpers():
	from card.tests import test_assignment_overlap_concurrency as model

	base = model.TestAssignmentOverlapConcurrency
	TestPeriodRunConcurrency._committed = base._committed
	TestPeriodRunConcurrency._race = base._race


_bind_model_helpers()
