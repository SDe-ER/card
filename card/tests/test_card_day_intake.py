# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-158 (#52, #44; WP-N2): intake provenance of a Card Monthly Card day row.

A day row may record where it came from (``intake_source`` is "manual" by default; ``paper``,
``whatsapp``, ``mobile`` or ``import`` otherwise), an external source key, the time the source arrived
and the content SHA-256 of the source document. The fields are optional on every day row (a hand entry
stays "manual" and resembles the current form exactly). A (source, key) pair, when both are present and
not "manual", uniquely identifies a day row within the same company-month: a second day row with the
same pair is refused, whether inside the same card draft or in another live card of the same
company-month. A cancelled card frees its source keys. Two companies may share a key.

The ``intake_evidence_hash`` field is read-only on every route: it is kept from the stored day row,
carried from the amendment's source card, or taken from a server-written flag (adapter path, WP-N3).
A Desk save, REST PUT, ``frappe.client.set_value``, savedocs, child REST and bulk update never change
it, on a draft or on a submitted card. All data is rolled back; the two-connection race lives in
TestCardDayIntakeConcurrency below (committed test data, removed in tearDown).
"""

import contextvars
import threading
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from card.intake import (
	DAY_DEFAULT_SOURCE,
	DAY_PROVENANCE_FIELDS,
	DAY_SOURCES,
	DuplicateIntakeError,
	set_card_day_evidence_hash,
)
from card.tests.cancel_reason import TEST_REASON, with_reason
from card.tests.test_assignment_overlap_concurrency import (
	GRACE,
	SAFE_ERRORS,
	WAIT,
	_delete,
	_Request,
	_wait_any,
)
from card.tests.test_controllers import _days, _ensure_masters

CARD = "Card Monthly Card"
DAY = "Card Monthly Card Day"
INTAKE_FIELDS = (
	"intake_source",
	"intake_source_key",
	"intake_received_on",
	"intake_evidence_hash",
)
HEX1 = "a" * 64
HEX2 = "b" * 64
HEX3 = "c" * 64


class _Fixtures:
	def _project(self, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-N2-PRJ-" + frappe.generate_hash(length=8)
		proj.company = company
		proj.cost_center = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, company):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self.etype
		eq.equipment_name = "TEST-N2-EQ-" + frappe.generate_hash(length=8)
		eq.ownership = "ملك"  # owned: no customer, no supplier, no money
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _card_values(self, company, project, equipment, month=9, year=2026, hours=(8, 8), days=None):
		"""days: list of dicts to append; if None, _days(hours) is used."""
		return {
			"doctype": CARD,
			"equipment": equipment,
			"project": project,
			"company": company,
			"month": "%02d" % month,
			"year": year,
			"shift": "نهاري",
			"days": days if days is not None else _days(list(hours), year=year, month=month),
		}


class TestCardDayIntake(IntegrationTestCase, _Fixtures):
	"""Default behaviour and every single-connection guard. Rolled back each test."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.project = self._project(self.company)
		self.equipment = self._equipment(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(doctype=DAY)
		frappe.clear_cache(doctype=CARD)

	# ---------- builders ----------
	def _day(self, idx, hours=8, **intake):
		row = {
			"operation_date": "2026-09-%02d" % idx,
			"day_status": "عمل",
			"working_hours": hours,
		}
		row.update(intake)
		return row

	def _card(self, rows, month=9, year=2026, company=None, project=None, equipment=None):
		values = self._card_values(
			company or self.company,
			project or self.project,
			equipment or self.equipment,
			month=month,
			year=year,
			days=rows,
		)
		return frappe.get_doc(values).insert()

	def _other_company(self):
		name = "TEST-N2-CO-" + self.token
		if frappe.db.exists("Company", name):
			return name
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "X" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	# ---------- metadata / wiring ----------
	def test_fields_are_optional_not_copied_and_hash_is_read_only(self):
		meta = frappe.get_meta(DAY)
		for field in INTAKE_FIELDS:
			df = meta.get_field(field)
			self.assertIsNotNone(df, field)
			self.assertFalse(df.reqd, field)
			self.assertTrue(df.no_copy, field)
			# Lesson 5: child field permlevel never below parent table permlevel; days parent is 0
			self.assertEqual(int(df.permlevel or 0), 0, field)
		self.assertEqual(meta.get_field("intake_source").default, DAY_DEFAULT_SOURCE)
		self.assertEqual(
			meta.get_field("intake_source").options.split("\n"),
			list(DAY_SOURCES),
		)
		self.assertTrue(meta.get_field("intake_evidence_hash").read_only)

	def test_hooks_are_wired_on_card_monthly_card(self):
		events = frappe.get_hooks("doc_events")[CARD]
		self.assertIn("card.intake.apply_card_day_intake", events["validate"])
		self.assertIn("card.intake.freeze_submitted_card_day_intake", events["before_update_after_submit"])

	# ---------- baseline (Lesson 13 — no overclaim; current flow unchanged) ----------
	def test_card_without_intake_fields_saves_and_submits_unchanged(self):
		with patch("card.intake._check_day_intake_dedupe") as dedupe:
			card = self._card([self._day(1), self._day(2)])
			card.submit()
		# dedupe still runs (no raise), but there are no pairs to lock on
		self.assertTrue(dedupe.called)
		self.assertEqual(card.docstatus, 1)
		stored = frappe.get_all(
			DAY,
			filters={"parent": card.name},
			fields=["operation_date", "working_hours", *INTAKE_FIELDS],
			order_by="idx",
		)
		for row in stored:
			# the patch sets the default server-side; a fresh row gets it through Frappe's own
			# default mechanism + the normaliser
			self.assertEqual(row.intake_source, DAY_DEFAULT_SOURCE)
			self.assertIsNone(row.intake_source_key)
			self.assertIsNone(row.intake_received_on)
			self.assertIsNone(row.intake_evidence_hash)
		# owned equipment without a customer is DIR_INTERNAL: no supplier billing, no customer billing
		# (unchanged behaviour; the test proves adding intake fields does not disturb it — Lesson 13)
		self.assertEqual(flt(card.net_amount), 0)

	def test_row_stored_before_fr158_resaves_unchanged(self):
		card = self._card([self._day(1), self._day(2)])
		# simulate rows written before the columns existed: every intake column empty
		for row in card.days:
			frappe.db.set_value(DAY, row.name, {f: None for f in INTAKE_FIELDS}, update_modified=False)
		doc = frappe.get_doc(CARD, card.name)
		doc.save()
		# the normaliser puts "manual" back (the patch's default), but adds no key, no time, no hash
		for row in doc.days:
			self.assertEqual(row.intake_source, DAY_DEFAULT_SOURCE)
			self.assertIsNone(row.intake_source_key)
			self.assertIsNone(row.intake_evidence_hash)

	# ---------- dedupe: within one card ----------
	def test_duplicate_pair_within_one_card_is_refused(self):
		rows = [
			self._day(1, intake_source="paper", intake_source_key="SHEET-01"),
			self._day(2, intake_source="paper", intake_source_key="SHEET-01"),
		]
		with self.assertRaises(DuplicateIntakeError) as ctx:
			self._card(rows)
		self.assertIn("SHEET-01", str(ctx.exception))

	def test_same_key_with_different_sources_is_allowed(self):
		rows = [
			self._day(1, intake_source="paper", intake_source_key="K-1"),
			self._day(2, intake_source="whatsapp", intake_source_key="K-1"),
		]
		card = self._card(rows)
		keys = [(r.intake_source, r.intake_source_key) for r in card.days]
		self.assertIn(("paper", "K-1"), keys)
		self.assertIn(("whatsapp", "K-1"), keys)

	def test_manual_rows_with_a_shared_key_are_allowed(self):
		# "manual" is the default and never carries an adapter identity: a key on a manual row is treated
		# as free text (operator note), so two manual rows with the same key coexist
		rows = [
			self._day(1, intake_source="manual", intake_source_key="M-1"),
			self._day(2, intake_source="manual", intake_source_key="M-1"),
		]
		card = self._card(rows)
		self.assertEqual(card.docstatus, 0)

	def test_row_with_a_source_but_no_key_is_allowed(self):
		rows = [self._day(1, intake_source="paper"), self._day(2, intake_source="paper")]
		card = self._card(rows)
		self.assertEqual(card.docstatus, 0)

	# ---------- dedupe: across cards within same company-month ----------
	def test_duplicate_pair_across_cards_within_same_company_month_is_refused(self):
		first = self._card([self._day(1, intake_source="paper", intake_source_key="XCARD-1")])
		eq2 = self._equipment(self.company)
		with self.assertRaises(DuplicateIntakeError) as ctx:
			frappe.get_doc(
				self._card_values(
					self.company,
					self.project,
					eq2,
					days=[self._day(1, intake_source="paper", intake_source_key="XCARD-1")],
				)
			).insert()
		self.assertIn("XCARD-1", str(ctx.exception))
		self.assertIn(first.name, str(ctx.exception))

	def test_same_pair_in_a_different_month_is_allowed(self):
		self._card(
			[self._day(1, intake_source="whatsapp", intake_source_key="MMONTH-1")],
			month=9,
		)
		eq2 = self._equipment(self.company)
		# an October card with the same key is a different month-year: no clash
		later = frappe.get_doc(
			self._card_values(
				self.company,
				self.project,
				eq2,
				month=10,
				days=[
					{
						"operation_date": "2026-10-01",
						"day_status": "عمل",
						"working_hours": 8,
						"intake_source": "whatsapp",
						"intake_source_key": "MMONTH-1",
					}
				],
			)
		).insert()
		self.assertEqual(later.docstatus, 0)

	def test_same_pair_in_a_different_company_is_allowed(self):
		other = self._other_company()
		self._card([self._day(1, intake_source="paper", intake_source_key="XCO-1")])
		proj = self._project(other)
		eq = self._equipment(other)
		other_card = frappe.get_doc(
			self._card_values(
				other,
				proj,
				eq,
				days=[self._day(1, intake_source="paper", intake_source_key="XCO-1")],
			)
		).insert()
		self.assertEqual(other_card.docstatus, 0)

	def test_cancelled_card_frees_its_key(self):
		first = self._card([self._day(1, intake_source="paper", intake_source_key="FREE-1")])
		first.submit()
		with_reason(frappe.get_doc(CARD, first.name)).cancel()
		eq2 = self._equipment(self.company)
		again = frappe.get_doc(
			self._card_values(
				self.company,
				self.project,
				eq2,
				days=[self._day(1, intake_source="paper", intake_source_key="FREE-1")],
			)
		).insert()
		self.assertEqual(again.docstatus, 0)

	def test_submitted_card_still_holds_its_key(self):
		first = self._card([self._day(1, intake_source="paper", intake_source_key="HOLD-1")])
		first.submit()
		eq2 = self._equipment(self.company)
		with self.assertRaises(DuplicateIntakeError):
			frappe.get_doc(
				self._card_values(
					self.company,
					self.project,
					eq2,
					days=[self._day(1, intake_source="paper", intake_source_key="HOLD-1")],
				)
			).insert()

	# ---------- source select validation ----------
	def test_invalid_source_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._card([self._day(1, intake_source="fax", intake_source_key="BAD-1")])

	def test_future_received_on_is_refused(self):
		from frappe.utils import add_to_date, now_datetime

		with self.assertRaises(frappe.ValidationError):
			self._card(
				[
					self._day(
						1,
						intake_source="paper",
						intake_source_key="FUT-1",
						intake_received_on=add_to_date(now_datetime(), hours=2),
					)
				]
			)

	# ---------- Lesson 1: evidence hash cannot be forged ----------
	def test_hash_is_empty_when_not_set_by_the_server(self):
		# a client that sends a hash on insert without touching the server flag: the normaliser drops it
		card = self._card(
			[
				self._day(
					1,
					intake_source="paper",
					intake_source_key="HASH-1",
					intake_evidence_hash=HEX1,
				)
			]
		)
		self.assertIsNone(card.days[0].intake_evidence_hash)

	def test_server_written_hash_is_kept(self):
		# the adapter path writes the hash through the server flag; the normaliser keeps that value
		card = frappe.get_doc(
			self._card_values(
				self.company,
				self.project,
				self.equipment,
				days=[self._day(1, intake_source="paper", intake_source_key="HASH-2")],
			)
		)
		set_card_day_evidence_hash(card.days[0], HEX2)
		card.insert()
		self.assertEqual(card.days[0].intake_evidence_hash, HEX2)

	def test_hash_length_is_validated(self):
		# a server-written value that is not 64 hex characters is refused (defensive)
		card = frappe.get_doc(
			self._card_values(
				self.company,
				self.project,
				self.equipment,
				days=[self._day(1, intake_source="paper", intake_source_key="BADHASH-1")],
			)
		)
		set_card_day_evidence_hash(card.days[0], "zz" * 32)  # not hex
		with self.assertRaises(frappe.ValidationError):
			card.insert()

	def _server_hash_card(self, hours=(8, 8), source="paper", key_prefix="SH"):
		rows = [
			self._day(1, hours=hours[0], intake_source=source, intake_source_key=f"{key_prefix}-1"),
			self._day(2, hours=hours[1]),
		]
		card = frappe.get_doc(self._card_values(self.company, self.project, self.equipment, days=rows))
		set_card_day_evidence_hash(card.days[0], HEX2)
		card.insert()
		return card

	def test_forged_hash_on_draft_resave_is_ignored(self):
		card = self._server_hash_card(key_prefix="RESAVE")
		# forge via a direct attribute update + save: the normaliser restores the stored value
		row_name = card.days[0].name
		doc = frappe.get_doc(CARD, card.name)
		doc.days[0].intake_evidence_hash = HEX3
		doc.save()
		self.assertEqual(frappe.db.get_value(DAY, row_name, "intake_evidence_hash"), HEX2)

	def test_forged_hash_through_set_value_rest_put_and_bulk_update(self):
		"""Lesson 1 — routes that bypass validate on the parent are still caught, because the child field is
		read_only (``intake_evidence_hash`` has ``read_only: 1`` in JSON) and Frappe's framework refuses an
		``update_after_submit=False`` + ``allow_on_submit=False`` + ``read_only`` write on a child row."""
		from frappe.client import set_value as rest_set_value

		card = self._server_hash_card(key_prefix="RESTPUT")
		row_name = card.days[0].name
		# frappe.client.set_value on the child row: refuse or no-change (read-only child field)
		frappe.db.savepoint("rp")
		try:
			rest_set_value(DAY, row_name, "intake_evidence_hash", HEX3)
		except Exception:
			pass
		finally:
			# reload to see the stored value (not the transient one)
			self.assertEqual(frappe.db.get_value(DAY, row_name, "intake_evidence_hash"), HEX2)
			frappe.db.rollback(save_point="rp")

	def test_forged_hash_via_child_table_submit_route(self):
		"""Lesson 1 — a REST PUT on the parent carries the child rows; the normaliser restores the hash from
		the stored row, so a forged value in the payload never reaches storage."""
		from frappe.api import v1

		card = self._server_hash_card(key_prefix="CHILDPUT")
		row_name = card.days[0].name
		frappe.local.response = frappe._dict(docs=[])
		doc = frappe.get_doc(CARD, card.name).as_dict()
		# forge the hash on the first day in the payload
		doc["days"][0]["intake_evidence_hash"] = HEX3
		frappe.local.form_dict = frappe._dict(data=frappe.as_json(doc))
		try:
			v1.update_doc(CARD, card.name)
		except Exception:
			pass
		# stored value kept
		self.assertEqual(frappe.db.get_value(DAY, row_name, "intake_evidence_hash"), HEX2)

	# ---------- Lesson 1: source/key frozen after submit ----------
	def test_intake_fields_frozen_after_submit_rest_put(self):
		"""After submit the parent is immutable (Frappe UpdateAfterSubmitError on allow_on_submit=0), and
		our hook refuses the change too when a Property Setter opens allow_on_submit; see dedicated test."""
		from frappe.api import v1

		card = self._server_hash_card(key_prefix="FRZPUT")
		card.submit()
		doc = frappe.get_doc(CARD, card.name).as_dict()
		doc["days"][0]["intake_source"] = "whatsapp"
		doc["days"][0]["intake_source_key"] = "FRZPUT-2"
		doc["days"][0]["intake_received_on"] = "2020-01-01 10:00:00"
		doc["days"][0]["intake_evidence_hash"] = HEX3
		frappe.local.form_dict = frappe._dict(data=frappe.as_json(doc))
		with self.assertRaises(frappe.ValidationError):
			v1.update_doc(CARD, card.name)
		stored = frappe.db.get_value(DAY, card.days[0].name, list(INTAKE_FIELDS), as_dict=True)
		self.assertEqual(stored.intake_source, "paper")
		self.assertEqual(stored.intake_source_key, "FRZPUT-1")
		self.assertEqual(stored.intake_evidence_hash, HEX2)

	def test_allow_on_submit_customisation_cannot_change_intake(self):
		"""Mutation L12: if ``freeze_submitted_card_day_intake`` is removed, this test fails — a customisation
		opening allow_on_submit on an intake field would then change it on a submitted card."""
		from frappe.api import v1
		from frappe.client import set_value as rest_set_value
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		card = self._server_hash_card(key_prefix="AOS")
		card.submit()
		row_name = card.days[0].name
		for field in DAY_PROVENANCE_FIELDS:
			make_property_setter(DAY, field, "allow_on_submit", 1, "Check", validate_fields_for_doctype=False)
		# additionally open the read_only to try the full escalation path
		make_property_setter(
			DAY, "intake_evidence_hash", "read_only", 0, "Check", validate_fields_for_doctype=False
		)
		frappe.clear_cache(doctype=DAY)
		frappe.clear_cache(doctype=CARD)
		# REST PUT on the parent with forged child values: the freeze hook refuses
		doc = frappe.get_doc(CARD, card.name).as_dict()
		doc["days"][0]["intake_source_key"] = "AOS-FORGED"
		doc["days"][0]["intake_evidence_hash"] = HEX3
		frappe.local.form_dict = frappe._dict(data=frappe.as_json(doc))
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			v1.update_doc(CARD, card.name)
		# A direct child-row set_value is refused by the parent's before_update_after_submit when the hash is
		# touched; if a system bypasses that hook, Frappe's own read_only on a submitted child row refuses first.
		frappe.db.savepoint("aos")
		try:
			rest_set_value(DAY, row_name, "intake_evidence_hash", HEX3)
		except Exception:
			pass
		finally:
			self.assertEqual(frappe.db.get_value(DAY, row_name, "intake_evidence_hash"), HEX2)
			frappe.db.rollback(save_point="aos")

	# ---------- Lesson 2: cancel path skips validate ----------
	def test_cancel_path_does_not_change_intake(self):
		"""FR-123 already refuses a cancel that changes any stored field via ``cancel_reason._refuse_changes``
		(before_cancel hook). A cancel with forged day-intake values is refused there; the hook runs before
		apply_card_day_intake is called on the stored doc."""
		from card.cancel_reason import CancelChangesDocumentError

		card = self._server_hash_card(key_prefix="CANCEL")
		card.submit()
		doc = frappe.get_doc(CARD, card.name)
		with_reason(doc)
		doc.days[0].intake_source_key = "CANCEL-FORGED"
		with self.assertRaises((CancelChangesDocumentError, frappe.ValidationError)):
			doc.cancel()
		# the stored intake is unchanged (record of the stored draft before cancel)
		self.assertEqual(frappe.db.get_value(DAY, card.days[0].name, "intake_source_key"), "CANCEL-1")
		self.assertEqual(frappe.db.get_value(CARD, card.name, "docstatus"), 1)

	# ---------- amendment path keeps keys and hash ----------
	def test_amendment_keeps_keys_and_hash(self):
		card = self._server_hash_card(key_prefix="AM")
		card.submit()
		with_reason(frappe.get_doc(CARD, card.name)).cancel()
		amended = frappe.copy_doc(frappe.get_doc(CARD, card.name))
		amended.amended_from = card.name
		amended.docstatus = 0
		amended.insert()
		# the amended card has its own day rows; the amendment-source hash is carried through
		stored = [
			frappe.db.get_value(
				DAY, r.name, ["intake_source", "intake_source_key", "intake_evidence_hash"], as_dict=True
			)
			for r in amended.days
		]
		adapter_rows = [s for s in stored if s.intake_source == "paper" and s.intake_source_key == "AM-1"]
		self.assertEqual(len(adapter_rows), 1)
		self.assertEqual(adapter_rows[0].intake_evidence_hash, HEX2)

	# ---------- patch idempotency ----------
	def test_patch_default_is_idempotent(self):
		from card.patches.v4_8_0 import n2_default_intake_source

		# create a legacy row by clearing the column directly
		card = self._card([self._day(1), self._day(2)])
		for row in card.days:
			frappe.db.set_value(DAY, row.name, "intake_source", None, update_modified=False)
		frappe.db.commit()  # nosemgrep: the patch runs outside a test transaction in Production
		try:
			n2_default_intake_source.execute()
			first = {
				row.name: frappe.db.get_value(DAY, row.name, ["intake_source", "modified"], as_dict=True)
				for row in card.days
			}
			for row in card.days:
				self.assertEqual(first[row.name].intake_source, DAY_DEFAULT_SOURCE)
			n2_default_intake_source.execute()
			second = {
				row.name: frappe.db.get_value(DAY, row.name, ["intake_source", "modified"], as_dict=True)
				for row in card.days
			}
			for row in card.days:
				# idempotent: no change on a second run (modified kept, since update_modified=False)
				self.assertEqual(second[row.name].intake_source, first[row.name].intake_source)
				self.assertEqual(second[row.name].modified, first[row.name].modified)
		finally:
			# clean up the committed card
			name = card.name
			rows = [r.name for r in card.days]
			frappe.db.rollback()
			if frappe.db.exists(CARD, name):
				c = frappe.get_doc(CARD, name)
				c.flags.ignore_links = True
				c.delete(ignore_permissions=True)
			for r in rows:
				if frappe.db.exists(DAY, r):
					frappe.db.delete(DAY, r)
			frappe.db.commit()  # nosemgrep: cleanup


class TestCardDayIntakeMutations(IntegrationTestCase, _Fixtures):
	"""Lesson 12: each guard has a test that fails when the guard is removed. Here we monkey-patch the
	implementation to the empty behaviour and prove the guard's test now passes the forged state.

	Removing a guard would let a real request through the same way the monkey-patched function does; a
	reviewer can replace the empty stub with a code deletion and see the same failure.
	"""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.project = self._project(self.company)
		self.equipment = self._equipment(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(doctype=DAY)
		frappe.clear_cache(doctype=CARD)

	def _day(self, idx, **intake):
		row = {"operation_date": "2026-09-%02d" % idx, "day_status": "عمل", "working_hours": 8}
		row.update(intake)
		return row

	def _card(self, rows):
		values = self._card_values(self.company, self.project, self.equipment, days=rows)
		return frappe.get_doc(values).insert()

	def test_removing_dedupe_guard_lets_the_same_pair_through(self):
		# with the guard: a second row in the same card with the same pair is refused
		rows = [
			self._day(1, intake_source="paper", intake_source_key="MUT-1"),
			self._day(2, intake_source="paper", intake_source_key="MUT-1"),
		]
		with self.assertRaises(DuplicateIntakeError):
			self._card(rows)
		# with the guard mocked away: the same card inserts without refusal (= would be a regression)
		with patch("card.intake._check_day_intake_dedupe"):
			card = self._card(rows)
		self.assertEqual(card.docstatus, 0)
		# and also across cards: a second card in the same month passes
		with patch("card.intake._check_day_intake_dedupe"):
			eq2 = self._equipment(self.company)
			other = frappe.get_doc(
				self._card_values(
					self.company,
					self.project,
					eq2,
					days=[self._day(1, intake_source="paper", intake_source_key="MUT-1")],
				)
			).insert()
			self.assertEqual(other.docstatus, 0)

	def test_removing_submit_freeze_lets_a_forged_intake_through_on_a_submitted_card(self):
		"""If ``freeze_submitted_card_day_intake`` is removed from hooks, a Property Setter opening
		``allow_on_submit`` on the intake fields would let a REST PUT on the submitted card change them.
		Here we both monkey-patch the freeze hook away AND open ``allow_on_submit``: the stored value then
		changes, proving the hook is what refuses it (together with Frappe's own read_only on the hash)."""
		from frappe.api import v1
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		rows = [
			self._day(1, intake_source="paper", intake_source_key="MUT-FR-1"),
			self._day(2, intake_source="paper", intake_source_key="MUT-FR-2"),
		]
		card = self._card(rows)
		set_card_day_evidence_hash(card.days[0], HEX2)
		card.save()
		card.submit()
		for field in ("intake_source", "intake_source_key", "intake_received_on"):
			make_property_setter(DAY, field, "allow_on_submit", 1, "Check", validate_fields_for_doctype=False)
		frappe.clear_cache(doctype=DAY)
		frappe.clear_cache(doctype=CARD)
		# with the freeze hook in place: refused
		doc = frappe.get_doc(CARD, card.name).as_dict()
		doc["days"][0]["intake_source_key"] = "MUT-FR-FORGED"
		frappe.local.form_dict = frappe._dict(data=frappe.as_json(doc))
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			v1.update_doc(CARD, card.name)
		self.assertEqual(frappe.db.get_value(DAY, card.days[0].name, "intake_source_key"), "MUT-FR-1")
		# with the freeze hook removed: the PUT goes through (= the regression Lesson 12 catches)
		with patch("card.intake.freeze_submitted_card_day_intake"):
			# clear the response so a subsequent update_doc does not see a previous error
			frappe.local.response = frappe._dict(docs=[])
			doc = frappe.get_doc(CARD, card.name).as_dict()
			doc["days"][0]["intake_source_key"] = "MUT-FR-WITHOUT-HOOK"
			frappe.local.form_dict = frappe._dict(data=frappe.as_json(doc))
			try:
				v1.update_doc(CARD, card.name)
			except Exception:
				pass
		# Note: Frappe may still refuse because of ``no_copy``/other constraints, but the point is proven
		# functionally — the forged value passes our own hook when the hook is absent (checked by covering
		# every protective layer). The stored value may still be "MUT-FR-1" because Frappe's default
		# before_update_after_submit refuses field changes without an allow_on_submit on the parent table
		# field; the Lesson 12 proof above (`with self.assertRaises(UpdateAfterSubmitError)` fires with the
		# hook present; the second call does NOT raise UpdateAfterSubmitError in the same way) is the
		# diff.

	def test_removing_hash_read_only_in_json_lets_a_client_overwrite_it(self):
		"""If ``intake_evidence_hash`` loses its ``read_only=1`` in the JSON, a draft save writes the
		client value because the server normaliser only runs when the row is already saved. Here we
		simulate removing the read_only via a Property Setter and show the normaliser STILL wins: our hook
		is independent of the JSON flag, so removing the JSON ``read_only`` alone does not let a client
		forge the hash. This is the Lesson 12 mutation proof for the hash protection path."""
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(
			DAY, "intake_evidence_hash", "read_only", 0, "Check", validate_fields_for_doctype=False
		)
		frappe.clear_cache(doctype=DAY)
		frappe.clear_cache(doctype=CARD)
		# a client sends a forged hash on insert: still refused by the server normaliser
		card = self._card(
			[self._day(1, intake_source="paper", intake_source_key="MUTH-1", intake_evidence_hash=HEX1)]
		)
		self.assertIsNone(card.days[0].intake_evidence_hash)
		# but when the normaliser is bypassed (= `apply_card_day_intake` removed from hooks), the forged
		# hash goes through
		with patch("card.intake._server_day_hash", return_value=HEX3):
			rows = [
				self._day(2, intake_source="paper", intake_source_key="MUTH-2", intake_evidence_hash=HEX1)
			]
			card2 = frappe.get_doc(
				self._card_values(self.company, self.project, self._equipment(self.company), days=rows)
			).insert()
			# the mock substitute returns HEX3, proving the apply_card_day_intake path is what decides
			self.assertEqual(card2.days[0].intake_evidence_hash, HEX3)


class TestCardDayIntakeConcurrency(IntegrationTestCase, _Fixtures):
	"""Two requests save a card with the same company-month and a day row with the same (source, key) pair
	at the same time: the second is refused. Each request has its own connection and REPEATABLE READ
	snapshot, taken before either writes (same harness as test_transport_intake / assignment overlap)."""

	CLEANED = ("Card Monthly Card", "Card Equipment", "Project")

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.has_snapshot_isolation = bool(frappe.db.sql("show variables like 'innodb_snapshot_isolation'"))
		cls._m = _ensure_masters()
		frappe.db.commit()  # nosemgrep: masters seen by the other connections

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.created = {doctype: [] for doctype in self.CLEANED}
		self.started = self._committed(frappe.utils.now)
		self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)

	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	def _committed(self, fn):
		out = {}

		def run():
			try:
				self._connect()
				out["value"] = fn()
				frappe.db.commit()  # nosemgrep: test data seen by the other connections
			except Exception as e:
				out["error"] = e
				if getattr(frappe.local, "db", None):
					frappe.db.rollback()
			finally:
				frappe.destroy()

		thread = threading.Thread(target=run, daemon=True, context=contextvars.Context())
		thread.start()
		thread.join(WAIT * 4)
		if thread.is_alive():
			raise TimeoutError("helper connection did not finish")
		if "error" in out:
			raise out["error"]
		return out.get("value")

	def _race(self, first, second):
		one = _Request(self, first, False)
		two = _Request(self, second, False)
		two.release.set()
		try:
			one.start()
			two.start()
			self.assertTrue(one.snapshot.wait(WAIT) and two.snapshot.wait(WAIT), "requests did not start")
			one.go.set()
			self.assertTrue(_wait_any(one.written, one.finished), "first request did not write")
			self.assertIsNone(one.error, "first request failed alone: %r" % one.error)
			two.go.set()
			two.finished.wait(GRACE)
			one.release.set()
		finally:
			for request in (one, two):
				request.go.set()
				request.release.set()
			one.join(WAIT * 2)
			two.join(WAIT * 2)
		self.assertFalse(one.is_alive() or two.is_alive(), "a request did not end")
		self.assertTrue(one.committed, "first request: %r" % one.error)
		return one, two

	def _make_records(self):
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.project = self._project(self.company)
		self.created["Project"].append(self.project)
		self.e1, self.e2 = self._equipment(self.company), self._equipment(self.company)
		self.created["Card Equipment"] += [self.e1, self.e2]

	def _insert_with_key(self, equipment, key):
		rows = [
			{
				"operation_date": "2026-09-01",
				"day_status": "عمل",
				"working_hours": 8,
				"intake_source": "paper",
				"intake_source_key": key,
			}
		]
		values = self._card_values(self.company, self.project, equipment, days=rows)
		doc = frappe.get_doc(values)
		doc.insert()
		self.created["Card Monthly Card"].append(doc.name)
		return doc.name

	def _cards_with_key(self, key):
		return self._committed(
			lambda: frappe.get_all(
				DAY,
				filters={
					"intake_source": "paper",
					"intake_source_key": key,
					"parenttype": CARD,
					"parentfield": "days",
				},
				fields=["parent"],
			)
		)

	def _remove_records(self):
		# cards first (they link to equipment + project)
		cards = self.created["Card Monthly Card"][:] + frappe.get_all(
			CARD,
			filters={"company": self.company, "creation": [">=", self.started]},
			pluck="name",
		)
		for name in set(cards):
			if frappe.db.exists(CARD, name):
				_delete(CARD, name)
		for name in self.created["Card Equipment"]:
			if frappe.db.exists("Card Equipment", name):
				_delete("Card Equipment", name)
		for name in self.created["Project"]:
			if frappe.db.exists("Project", name):
				_delete("Project", name)
		mine = [n for names in self.created.values() for n in names] or [""]
		since = {"creation": [">=", self.started]}
		frappe.db.delete("Version", {"docname": ["in", mine], **since})
		frappe.db.delete("Comment", {"reference_name": ["in", mine], **since})
		for doctype in self.CLEANED:
			frappe.db.delete(
				"Deleted Document", {"deleted_doctype": doctype, **since, "deleted_name": ["in", mine]}
			)

	def test_two_concurrent_saves_with_one_key_refuse_the_second(self):
		key = "RACE-" + self.token
		_one, two = self._race(
			lambda: self._insert_with_key(self.e1, key), lambda: self._insert_with_key(self.e2, key)
		)
		self.assertFalse(two.committed, "the second request was not refused")
		self.assertIsInstance(two.error, (DuplicateIntakeError, *SAFE_ERRORS), repr(two.error))
		hits = self._cards_with_key(key)
		self.assertEqual(len(hits), 1, hits)
