# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-146 (#52, #43; WP-N1): intake provenance of an Equipment Transport.

Optional source key, channel, received time and private evidence file; the evidence SHA-256 is the server's.
One live transport per company and source key (company lock plus locking read); the same evidence warns only.
A transport without intake fields behaves as before. Everything here is rolled back; the two-connection race
is in TestTransportIntakeConcurrency below (committed test data, removed in tearDown)."""

import contextvars
import hashlib
import threading
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, getdate, now_datetime, nowdate

from card.intake import DEFAULT_CHANNEL, DuplicateIntakeError
from card.tests.sample_files import pdf, png
from card.tests.test_assignment_overlap_concurrency import (
	GRACE,
	SAFE_ERRORS,
	WAIT,
	_delete,
	_Request,
	_wait_any,
)
from card.tests.test_controllers import _ensure_masters

DOCTYPE = "Equipment Transport"
INTAKE_FIELDS = (
	"intake_source_key",
	"intake_channel",
	"intake_received_on",
	"intake_evidence",
	"intake_evidence_hash",
)


def _sha(content):
	return hashlib.sha256(content).hexdigest()


class _Fixtures:
	def _project(self, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-N1-PRJ-" + frappe.generate_hash(length=8)
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, company):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self.etype
		eq.equipment_name = "TEST-N1-EQ-" + frappe.generate_hash(length=8)
		eq.ownership = "ملك"  # owned: no supplier needed
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _values(self, company, project, equipment, day, **intake):
		return {
			"doctype": DOCTYPE,
			"date": str(add_days(self.base, day)),
			"company": company,
			"project": project,
			"items": [{"card_equipment": equipment}],
			"responsibility": "No transport charge",
			**intake,
		}


class TestTransportIntake(IntegrationTestCase, _Fixtures):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.base = getdate(add_days(nowdate(), -20))
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.project = self._project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(doctype=DOCTYPE)  # a test may have added a Property Setter (rolled back)

	def _transport(self, day=1, company=None, project=None, **intake):
		company = company or self.company
		values = self._values(company, project or self.project, self._equipment(company), day, **intake)
		return frappe.get_doc(values).insert()

	def _file(self, content, name):
		return frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{frappe.generate_hash(length=6)}-{name}",
				"content": content,
				"is_private": 1,
			}
		).insert(ignore_permissions=True)

	def _other_company(self):
		name = "TEST-N1-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "N" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _warnings(self):
		return [str(m) for m in frappe.message_log if "same intake evidence" in str(m)]

	# ---------- existing transports unchanged ----------

	def test_transport_without_intake_fields_is_unchanged(self):
		with (
			patch("card.intake.check_source_key") as key_check,
			patch("card.intake.warn_reused_evidence") as evidence_check,
		):
			t = self._transport()
			t.remarks = "re-saved"
			t.save()
			t.submit()
		key_check.assert_not_called()
		evidence_check.assert_not_called()
		stored = frappe.db.get_value(DOCTYPE, t.name, list(INTAKE_FIELDS), as_dict=True)
		self.assertEqual(stored, {f: None for f in INTAKE_FIELDS})
		self.assertEqual(t.docstatus, 1)
		self.assertTrue(t.created_assignment)

	def test_transport_recorded_before_fr146_resaves_unchanged(self):
		t = self._transport()
		# a row stored before the columns existed: every intake column empty
		frappe.db.set_value(DOCTYPE, t.name, {f: None for f in INTAKE_FIELDS}, update_modified=False)
		doc = frappe.get_doc(DOCTYPE, t.name)
		before = {
			f: doc.get(f) for f in ("payer", "cost_bearer", "amount", "financial_status", "move_day_rule")
		}
		doc.save()
		self.assertEqual({f: doc.get(f) for f in before}, before)
		self.assertEqual({f: doc.get(f) for f in INTAKE_FIELDS}, {f: None for f in INTAKE_FIELDS})

	def test_fields_are_optional_and_not_copied(self):
		meta = frappe.get_meta(DOCTYPE)
		for field in INTAKE_FIELDS:
			df = meta.get_field(field)
			self.assertFalse(df.reqd, field)
			self.assertFalse(df.default, field)
			self.assertTrue(df.no_copy, field)
		self.assertTrue(meta.get_field("intake_evidence_hash").read_only)

	# ---------- source key ----------

	def test_duplicate_source_key_is_refused(self):
		first = self._transport(intake_source_key="WA-0001")
		self.assertEqual(first.intake_channel, DEFAULT_CHANNEL)
		with self.assertRaises(DuplicateIntakeError) as ctx:
			self._transport(day=2, intake_source_key=" WA-0001 ")
		self.assertIn(first.name, str(ctx.exception))
		# the submitted transport still holds the key
		first.submit()
		with self.assertRaises(DuplicateIntakeError):
			self._transport(day=3, intake_source_key="WA-0001")

	def test_resave_keeps_its_own_key(self):
		t = self._transport(intake_source_key="WA-0002", intake_channel="WhatsApp")
		t.remarks = "edited"
		t.save()
		self.assertEqual(t.intake_source_key, "WA-0002")
		self.assertEqual(t.intake_channel, "WhatsApp")

	def test_cancelled_transport_frees_its_key(self):
		from card.tests.cancel_reason import with_reason

		t = self._transport(intake_source_key="WA-0003")
		t.submit()
		with_reason(frappe.get_doc(DOCTYPE, t.name)).cancel()
		self.assertEqual(frappe.db.get_value(DOCTYPE, t.name, "docstatus"), 2)
		again = self._transport(day=2, intake_source_key="WA-0003")
		self.assertEqual(again.intake_source_key, "WA-0003")

	def test_keys_match_case_insensitively(self):
		# the column uses the database's case-insensitive collation: "wa-0004" is the key "WA-0004"
		first = self._transport(intake_source_key="WA-0004")
		with self.assertRaises(DuplicateIntakeError) as ctx:
			self._transport(day=2, intake_source_key="wa-0004")
		self.assertIn(first.name, str(ctx.exception))

	def test_two_companies_may_share_a_key(self):
		self._transport(intake_source_key="SHEET-7")
		other = self._other_company()
		t = self._transport(company=other, project=self._project(other), intake_source_key="SHEET-7")
		self.assertEqual(t.intake_source_key, "SHEET-7")

	def test_key_check_locks_the_company_and_uses_a_locking_read(self):
		queries = []
		real_sql = frappe.db.sql

		def spy(query, *args, **kwargs):
			queries.append(str(query))
			return real_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=spy):
			self._transport(intake_source_key="LOCK-1")
		lock = next(i for i, q in enumerate(queries) if "`tabCompany`" in q and "FOR UPDATE" in q.upper())
		read = next(
			i
			for i, q in enumerate(queries)
			if "intake_source_key" in q and "FOR UPDATE" in q.upper() and "`tabEquipment Transport`" in q
		)
		self.assertLess(lock, read)

	def test_channel_and_received_on(self):
		with self.assertRaises(frappe.ValidationError):
			self._transport(intake_source_key="X-1", intake_channel="Fax")
		with self.assertRaises(frappe.ValidationError):
			self._transport(intake_received_on=add_to_date(now_datetime(), hours=2))
		t = self._transport(intake_received_on=add_to_date(now_datetime(), hours=-2))
		self.assertEqual(t.intake_channel, DEFAULT_CHANNEL)

	# ---------- evidence hash ----------

	def test_hash_is_computed_from_the_private_file_and_the_file_is_claimed(self):
		content = png("n1-a" + self.token)
		f = self._file(content, "sheet.png")
		t = self._transport(intake_evidence=f.file_url, intake_channel="Paper")
		self.assertEqual(t.intake_evidence_hash, _sha(content))
		row = frappe.db.get_value(
			"File", f.name, ["attached_to_doctype", "attached_to_name", "attached_to_field"], as_dict=True
		)
		self.assertEqual((row.attached_to_doctype, row.attached_to_name), (DOCTYPE, t.name))
		self.assertEqual(row.attached_to_field, "intake_evidence")

	def test_forged_client_hash_is_ignored(self):
		forged = "0" * 64
		t = self._transport(intake_evidence_hash=forged)
		self.assertIsNone(t.intake_evidence_hash)
		content = pdf("n1-b" + self.token)
		f = self._file(content, "sheet.pdf")
		t2 = self._transport(day=2, intake_evidence=f.file_url, intake_evidence_hash=forged)
		self.assertEqual(t2.intake_evidence_hash, _sha(content))
		t2.intake_evidence_hash = forged  # unchanged evidence: the stored hash is kept
		t2.save()
		self.assertEqual(t2.intake_evidence_hash, _sha(content))
		self.assertEqual(frappe.db.get_value(DOCTYPE, t2.name, "intake_evidence_hash"), _sha(content))
		# a REST-style update with a forged hash
		frappe.get_doc(DOCTYPE, t2.name).update({"intake_evidence_hash": forged}).save()
		self.assertEqual(frappe.db.get_value(DOCTYPE, t2.name, "intake_evidence_hash"), _sha(content))

	def _with_evidence(self, seed):
		content = png(seed + self.token)
		return self._transport(intake_evidence=self._file(content, "%s.png" % seed).file_url), _sha(content)

	def test_forged_hash_through_set_value_rest_put_and_bulk_update(self):
		from frappe.api import v1
		from frappe.client import set_value as rest_set_value
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		forged = "f" * 64
		t, real = self._with_evidence("routes")
		bare = self._transport(day=2)

		rest_set_value(DOCTYPE, t.name, "intake_evidence_hash", forged)
		rest_set_value(DOCTYPE, bare.name, "intake_evidence_hash", forged)
		self.assertEqual(frappe.db.get_value(DOCTYPE, t.name, "intake_evidence_hash"), real)
		self.assertIsNone(frappe.db.get_value(DOCTYPE, bare.name, "intake_evidence_hash"))

		frappe.local.form_dict = frappe._dict(data=frappe.as_json({"intake_evidence_hash": forged}))
		v1.update_doc(DOCTYPE, t.name)
		self.assertEqual(frappe.db.get_value(DOCTYPE, t.name, "intake_evidence_hash"), real)

		# the bulk action commits after each document and rolls back a failure: kept inside the test transaction
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			failed = submit_cancel_or_update_docs(
				DOCTYPE, [t.name, bare.name], "update", {"intake_evidence_hash": forged}
			)
		self.assertEqual(failed, [])  # both saved; the hash is the server's
		self.assertEqual(frappe.db.get_value(DOCTYPE, t.name, "intake_evidence_hash"), real)
		self.assertIsNone(frappe.db.get_value(DOCTYPE, bare.name, "intake_evidence_hash"))

	def test_intake_fields_are_frozen_after_submit(self):
		from frappe.api import v1
		from frappe.client import set_value as rest_set_value

		t, real = self._with_evidence("frozen")
		t.intake_source_key = "FROZEN-1"
		t.save()
		t.submit()
		other = self._file(png("other" + self.token), "other.png")
		changes = {
			"intake_source_key": "FROZEN-2",
			"intake_channel": "Email",
			"intake_received_on": "2020-01-01 10:00:00",
			"intake_evidence": other.file_url,
			"intake_evidence_hash": "e" * 64,
		}
		for field, value in changes.items():
			with self.subTest(field=field):
				with self.assertRaises(frappe.ValidationError):
					rest_set_value(DOCTYPE, t.name, field, value)
				frappe.local.form_dict = frappe._dict(data=frappe.as_json({field: value}))
				with self.assertRaises(frappe.ValidationError):
					v1.update_doc(DOCTYPE, t.name)
		stored = frappe.db.get_value(DOCTYPE, t.name, list(INTAKE_FIELDS), as_dict=True)
		self.assertEqual(stored.intake_source_key, "FROZEN-1")
		self.assertEqual(stored.intake_evidence_hash, real)
		self.assertNotEqual(stored.intake_evidence, other.file_url)

	def test_evidence_of_a_submitted_or_cancelled_transport_is_kept(self):
		from frappe.client import delete as rest_delete

		from card.tests.cancel_reason import with_reason

		draft, _ = self._with_evidence("draft")
		draft_file = frappe.db.get_value("File", {"file_url": draft.intake_evidence}, "name")
		submitted, _ = self._with_evidence("submitted")
		submitted.submit()
		kept = frappe.db.get_value("File", {"file_url": submitted.intake_evidence}, "name")
		self._as_card_manager()
		with self.assertRaisesRegex(frappe.ValidationError, "intake evidence"):
			rest_delete("File", kept)
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("File", kept, ignore_permissions=True)
		# detached from the transport, still kept
		frappe.db.set_value("File", kept, {"attached_to_doctype": None, "attached_to_name": None})
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("File", kept, ignore_permissions=True)
		with_reason(frappe.get_doc(DOCTYPE, submitted.name)).cancel()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("File", kept, ignore_permissions=True)
		self.assertTrue(frappe.db.exists("File", kept))
		# a draft's evidence may still be removed
		frappe.delete_doc("File", draft_file, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("File", draft_file))

	def _as_card_manager(self):
		email = "n1-manager-%s@example.com" % self.token
		user = frappe.new_doc("User")
		user.update({"email": email, "first_name": "N1 Manager", "send_welcome_email": 0})
		user.insert(ignore_permissions=True)
		user.add_roles("Card Manager")
		frappe.set_user(email)

	def _submitted_with_evidence(self, seed):
		t, real = self._with_evidence(seed)
		t.submit()
		row = frappe.db.get_value("File", {"file_url": t.intake_evidence}, "name")
		return t, real, row

	def _assert_evidence_kept(self, t, real, row):
		stored = frappe.db.get_value(
			DOCTYPE, t.name, ["intake_evidence", "intake_evidence_hash", "docstatus"], as_dict=True
		)
		self.assertEqual((stored.intake_evidence, stored.intake_evidence_hash), (t.intake_evidence, real))
		f = frappe.db.get_value(
			"File", row, ["file_url", "is_private", "attached_to_doctype", "attached_to_name"], as_dict=True
		)
		self.assertEqual((f.file_url, f.is_private), (t.intake_evidence, 1))
		self.assertEqual((f.attached_to_doctype, f.attached_to_name), (DOCTYPE, t.name))
		return stored

	def test_evidence_file_is_not_moved_detached_made_public_or_renamed(self):
		from frappe.client import set_value as rest_set_value

		t, real, row = self._submitted_with_evidence("move")
		other = self._transport(day=5)
		for field, value in (
			("attached_to_name", other.name),
			("attached_to_doctype", "Card Equipment"),
			("attached_to_name", None),
			("is_private", 0),
			("file_url", "/private/files/renamed-%s.png" % self.token),
		):
			with self.subTest(field=field):
				with self.assertRaisesRegex(frappe.ValidationError, "intake evidence"):
					rest_set_value("File", row, field, value)
				self._assert_evidence_kept(t, real, row)
		# a draft's evidence is not protected
		draft, _ = self._with_evidence("move-draft")
		draft_row = frappe.db.get_value("File", {"file_url": draft.intake_evidence}, "name")
		rest_set_value("File", draft_row, "attached_to_name", other.name)
		self.assertEqual(frappe.db.get_value("File", draft_row, "attached_to_name"), other.name)

	def test_allow_on_submit_customisation_cannot_change_the_intake(self):
		from frappe.client import set_value as rest_set_value
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		t, real, row = self._submitted_with_evidence("aos")
		other = self._file(png("aos-other" + self.token), "aos-other.png")
		changes = {
			"intake_evidence": other.file_url,
			"intake_evidence_hash": "a" * 64,
			"intake_source_key": "AOS-2",
			"intake_channel": "Email",
			"intake_received_on": "2020-01-01 10:00:00",
		}
		for field in changes:
			make_property_setter(
				DOCTYPE, field, "allow_on_submit", 1, "Check", validate_fields_for_doctype=False
			)
		frappe.clear_cache(doctype=DOCTYPE)
		for field, value in changes.items():
			with self.subTest(field=field):
				with self.assertRaises(frappe.UpdateAfterSubmitError):
					rest_set_value(DOCTYPE, t.name, field, value)
				self._assert_evidence_kept(t, real, row)
		self.assertIsNone(frappe.db.get_value(DOCTYPE, t.name, "intake_source_key"))

	def test_cancel_cannot_change_the_intake(self):
		from frappe.api import v1
		from frappe.desk.form.save import savedocs

		from card.tests.cancel_reason import TEST_REASON

		t, real, row = self._submitted_with_evidence("cancel")
		other = self._file(png("cancel-other" + self.token), "cancel-other.png")
		forged = {
			"intake_evidence": other.file_url,
			"intake_evidence_hash": "c" * 64,
			"intake_source_key": "CANCEL-2",
		}
		# REST PUT with docstatus 2: refused, nothing changes
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json({"docstatus": 2, "cancel_reason": TEST_REASON, **forged})
		)
		with self.assertRaises(frappe.ValidationError):
			v1.update_doc(DOCTYPE, t.name)
		self.assertEqual(self._assert_evidence_kept(t, real, row).docstatus, 1)
		# savedocs Cancel with a forged document: whatever Frappe does with the request (16.55 ignores the
		# client values on cancel), the stored intake is unchanged
		doc = frappe.get_doc(DOCTYPE, t.name).as_dict()
		doc.update({"cancel_reason": TEST_REASON, **forged})
		try:
			savedocs(frappe.as_json(doc), "Cancel")
		except frappe.ValidationError:
			pass
		self._assert_evidence_kept(t, real, row)

	def test_public_or_foreign_evidence_is_refused(self):
		public = frappe.get_doc(
			{"doctype": "File", "file_name": "pub-%s.png" % self.token, "content": png("p"), "is_private": 0}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			self._transport(intake_evidence=public.file_url)
		owner = self._transport()
		foreign = self._file(png("f" + self.token), "f.png")
		frappe.db.set_value(
			"File", foreign.name, {"attached_to_doctype": DOCTYPE, "attached_to_name": owner.name}
		)
		with self.assertRaises(frappe.ValidationError):
			self._transport(day=2, intake_evidence=foreign.file_url)
		bad = self._file(b"not an image", "x.txt")
		with self.assertRaises(frappe.ValidationError):
			self._transport(day=3, intake_evidence=bad.file_url)

	def test_reused_evidence_warns_within_the_company_only(self):
		content = png("n1-c" + self.token)
		first = self._transport(intake_evidence=self._file(content, "a.png").file_url)
		frappe.clear_messages()
		second = self._transport(day=2, intake_evidence=self._file(content, "b.png").file_url)
		self.assertEqual(second.intake_evidence_hash, first.intake_evidence_hash)
		self.assertTrue(any(first.name in w for w in self._warnings()), frappe.message_log)
		self.assertEqual(second.docstatus, 0)  # saved: warn only
		other = self._other_company()
		frappe.clear_messages()
		self._transport(
			company=other, project=self._project(other), intake_evidence=self._file(content, "c.png").file_url
		)
		self.assertEqual(self._warnings(), [])

	def test_removing_evidence_clears_the_hash(self):
		content = png("n1-d" + self.token)
		t = self._transport(intake_evidence=self._file(content, "d.png").file_url)
		t.intake_evidence = None
		t.save()
		self.assertIsNone(t.intake_evidence_hash)
		self.assertEqual(t.intake_channel, DEFAULT_CHANNEL)  # the channel stays as entered

	def test_amendment_keeps_key_and_evidence(self):
		from card.tests.cancel_reason import with_reason

		content = png("n1-e" + self.token)
		t = self._transport(intake_source_key="AM-1", intake_evidence=self._file(content, "e.png").file_url)
		t.submit()
		with_reason(frappe.get_doc(DOCTYPE, t.name)).cancel()
		amended = frappe.copy_doc(frappe.get_doc(DOCTYPE, t.name))
		amended.amended_from = t.name
		amended.docstatus = 0
		# the links the cancel undid (reverse_transfer) are not carried over
		for row in [amended, *amended.items]:
			row.created_assignment = row.previous_assignment = None
		amended.insert()
		self.assertEqual(amended.intake_source_key, "AM-1")
		self.assertEqual(amended.intake_evidence_hash, _sha(content))


class TestTransportIntakeConcurrency(IntegrationTestCase, _Fixtures):
	"""Two requests save a transport with the same company and source key at the same time: one is refused.
	Each request has its own connection and REPEATABLE READ snapshot, taken before either writes (the same
	harness as test_assignment_overlap_concurrency)."""

	CLEANED = ("Equipment Transport", "Card Equipment", "Project")

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

	def _race(self, first, second, snapshot_isolation=False):
		one = _Request(self, first, snapshot_isolation)
		two = _Request(self, second, snapshot_isolation)
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
		self.base = getdate(add_days(nowdate(), 70))
		self.project = self._project(self.company)
		self.created["Project"].append(self.project)
		self.e1, self.e2 = self._equipment(self.company), self._equipment(self.company)
		self.created["Card Equipment"] += [self.e1, self.e2]

	def _insert(self, equipment, key):
		doc = frappe.get_doc(self._values(self.company, self.project, equipment, 1, intake_source_key=key))
		doc.insert()
		self.created["Equipment Transport"].append(doc.name)
		return doc.name

	def _keyed(self, key):
		return self._committed(
			lambda: frappe.get_all(
				DOCTYPE, filters={"company": self.company, "intake_source_key": key}, pluck="name"
			)
		)

	def _remove_records(self):
		names = frappe.get_all(
			DOCTYPE, filters={"intake_source_key": ["like", "%" + self.token]}, pluck="name"
		)
		for name in set(names) | set(self.created["Equipment Transport"]):
			if frappe.db.exists(DOCTYPE, name):
				_delete(DOCTYPE, name)
		for doctype in ("Card Equipment", "Project"):
			for name in self.created[doctype]:
				if frappe.db.exists(doctype, name):
					_delete(doctype, name)
		mine = [n for names in self.created.values() for n in names] + names or [""]
		since = {"creation": [">=", self.started]}
		frappe.db.delete("Version", {"docname": ["in", mine], **since})
		frappe.db.delete("Comment", {"reference_name": ["in", mine], **since})
		for doctype in self.CLEANED:
			frappe.db.delete(
				"Deleted Document", {"deleted_doctype": doctype, **since, "deleted_name": ["in", mine]}
			)

	def test_two_concurrent_saves_with_one_key(self):
		key = "RACE-" + self.token
		_one, two = self._race(lambda: self._insert(self.e1, key), lambda: self._insert(self.e2, key))
		self.assertFalse(two.committed, "the second request was not refused")
		self.assertIsInstance(two.error, DuplicateIntakeError, repr(two.error))
		self.assertEqual(len(self._keyed(key)), 1)

	def test_two_committed_drafts_take_one_key_concurrently(self):
		key = "RACE4-" + self.token
		d1, d2 = self._committed(lambda: (self._insert(self.e1, None), self._insert(self.e2, None)))

		def set_key(name):
			doc = frappe.get_doc(DOCTYPE, name)
			doc.intake_source_key = key
			doc.save()

		_one, two = self._race(lambda: set_key(d1), lambda: set_key(d2))
		self.assertFalse(two.committed, "the second request was not refused")
		self.assertIsInstance(two.error, DuplicateIntakeError, repr(two.error))
		self.assertEqual(self._keyed(key), [d1])

	def test_two_concurrent_saves_with_the_server_snapshot_setting(self):
		# MariaDB 11.8 (snapshot isolation ON) may refuse with error 1020 instead of the message
		key = "RACE2-" + self.token
		_one, two = self._race(
			lambda: self._insert(self.e1, key), lambda: self._insert(self.e2, key), snapshot_isolation=None
		)
		self.assertFalse(two.committed)
		self.assertIsInstance(two.error, SAFE_ERRORS, repr(two.error))
		self.assertEqual(len(self._keyed(key)), 1)

	def test_a_plain_read_would_not_see_the_first_save(self):
		"""Proof the locking read matters: after the company lock, the second request's plain read (its snapshot)
		does not see the first, committed transport, while its locking read does."""
		key = "RACE3-" + self.token
		seen = {}

		def second():
			frappe.db.get_value("Company", self.company, "name", for_update=True)
			# after the lock the first request has committed; a plain read still reads the snapshot
			plain = frappe.get_all(DOCTYPE, filters={"intake_source_key": key}, pluck="name")
			transport = frappe.qb.DocType(DOCTYPE)
			locking = (
				frappe.qb.from_(transport)
				.select(transport.name)
				.where(transport.intake_source_key == key)
				.for_update()
			).run(pluck=True)
			seen.update(plain=plain, locking=locking)

		_one, two = self._race(lambda: self._insert(self.e1, key), second)
		self.assertIsNone(two.error, repr(two.error))
		self.assertEqual(seen["plain"], [])
		self.assertEqual(len(seen["locking"]), 1)
