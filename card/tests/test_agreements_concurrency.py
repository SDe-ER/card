# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-141 (#41, WP-M1): two concurrent submits of overlapping Card Rate Agreements never both commit.

Each request runs in its own thread with its own database connection and commits, as two web requests do: its
first read fixes its REPEATABLE READ snapshot, and both requests take their snapshot before either writes. The
synthetic records are committed too (a race needs two real transactions) and are removed in tearDown, with the
Version and Comment rows they produced. Modelled on test_assignment_overlap_concurrency.

MariaDB 10.6 (Production) answers a locking read with the latest committed row. MariaDB 11.8 with
innodb_snapshot_isolation ON refuses a locking read of a row changed after the snapshot (error 1020, a deadlock
error in Frappe) instead. The strict case therefore sets the variable OFF in its own sessions only (10.6
behaviour); the server setting is never changed."""

import contextvars
import threading
import time

import frappe
from frappe.exceptions import QueryDeadlockError, QueryTimeoutError
from frappe.tests import IntegrationTestCase

from card.agreements import OverlappingAgreementError

DT = "Card Rate Agreement"
WAIT = 30  # seconds; a stuck step fails the test instead of hanging the run
GRACE = 1  # seconds the second request gets to reach the first one's lock before it commits
LOCK_WAIT = 10  # innodb_lock_wait_timeout of the two requests (session only)
SAFE_ERRORS = (frappe.ValidationError, QueryDeadlockError, QueryTimeoutError)


def _wait_any(*events, timeout=WAIT):
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if any(event.is_set() for event in events):
			return True
		events[0].wait(0.05)
	return False


class _Request(threading.Thread):
	"""One web request: its own connection and snapshot; it runs `action` when told, keeps its transaction open
	until released, then commits, or rolls back on an error."""

	def __init__(self, test, action, snapshot_isolation):
		super().__init__(daemon=True, context=contextvars.Context())
		self.test, self.action, self.snapshot_isolation = test, action, snapshot_isolation
		self.snapshot, self.go, self.written, self.release, self.finished = (
			threading.Event() for _ in range(5)
		)
		self.error = None
		self.committed = False

	def run(self):
		try:
			self.test._connect()
			frappe.db.sql("set session innodb_lock_wait_timeout = %s", LOCK_WAIT)
			if self.snapshot_isolation is not None and self.test.has_snapshot_isolation:
				frappe.db.sql("set session innodb_snapshot_isolation = %s", int(self.snapshot_isolation))
			# request start: the first read fixes the snapshot
			frappe.db.sql(f"select count(*) from `tab{DT}`")
			self.snapshot.set()
			if not self.go.wait(WAIT):
				raise TimeoutError("request was never started")
			self.action()
			self.written.set()
			if not self.release.wait(WAIT):
				raise TimeoutError("request was never released")
			frappe.db.commit()  # nosemgrep: a race needs two committed transactions
			self.committed = True
		except Exception as e:
			self.error = e
			if getattr(frappe.local, "db", None):
				frappe.db.rollback()
		finally:
			self.finished.set()
			frappe.destroy()


class TestRateAgreementConcurrency(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.has_snapshot_isolation = bool(frappe.db.sql("show variables like 'innodb_snapshot_isolation'"))

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.started = self._committed(frappe.utils.now)
		self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)
		self.assertEqual(self._committed(self._leftovers), {}, "synthetic records left behind")

	# ---- connections ----
	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	def _committed(self, fn):
		"""Run `fn` in its own connection and commit (setup, cleanup, fresh reads)."""
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
		"""Both requests take their snapshot; `first` writes and keeps its transaction open while `second` runs,
		then commits. snapshot_isolation=False is MariaDB 10.6 behaviour, None keeps the server setting."""
		one = _Request(self, first, snapshot_isolation)
		two = _Request(self, second, snapshot_isolation)
		two.release.set()  # the second commits as soon as its write is done
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

	# ---- records (raw: no side effects; removed in tearDown) ----
	def _raw(self, doctype, name, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = name
		doc.db_insert()
		return name

	def _make_records(self):
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not self.company:
			self.skipTest("test company missing (card.install.before_tests)")
		self.etype = self._raw(
			"Card Equipment Type", "CRA-RACE-T-" + self.token, equipment_type_name=self.token
		)
		self.equipment = self._raw(
			"Card Equipment", "CRA-RACE-E-" + self.token, company=self.company, equipment_type=self.etype
		)
		self.supplier = self._raw("Supplier", "CRA-RACE-S-" + self.token, supplier_name="S" + self.token)
		self.supplier2 = self._raw("Supplier", "CRA-RACE-S2-" + self.token, supplier_name="S2" + self.token)

	def _submit(self, valid_from, rate, supplier=None):
		def action():
			frappe.get_doc(
				{
					"doctype": DT,
					"company": self.company,
					"equipment": self.equipment,
					"supplier": supplier or self.supplier,
					"valid_from": valid_from,
					"daily_rate": rate,
					"docstatus": 1,
				}
			).insert()

		return action

	def _agreements(self):
		return frappe.get_all(
			DT, filters={"equipment": self.equipment, "docstatus": 1}, fields=["name", "daily_rate"]
		)

	def _remove_records(self):
		names = frappe.get_all(DT, filters={"equipment": self.equipment}, pluck="name")
		for name in names:
			frappe.db.delete("Card Agreement Responsibility", {"parent": name, "parenttype": DT})
			frappe.db.delete(DT, {"name": name})
		for doctype, name in (
			("Card Equipment", self.equipment),
			("Card Equipment Type", self.etype),
			("Supplier", self.supplier),
			("Supplier", self.supplier2),
		):
			frappe.db.delete(doctype, {"name": name})
		since = {"creation": [">=", self.started]}
		for name in [*names, self.equipment, self.etype, self.supplier, self.supplier2]:
			frappe.db.delete("Version", {"docname": name, **since})
			frappe.db.delete("Comment", {"reference_name": name, **since})

	def _leftovers(self):
		counts = {
			DT: frappe.db.count(DT, {"equipment": self.equipment}),
			"Card Equipment": frappe.db.count("Card Equipment", {"name": self.equipment}),
			"Supplier": frappe.db.count("Supplier", {"name": ["in", [self.supplier, self.supplier2]]}),
		}
		return {key: value for key, value in counts.items() if value}

	# ---- the race ----
	def test_two_overlapping_submits(self):
		_one, two = self._race(self._submit("2026-03-01", 500), self._submit("2026-03-15", 600))
		self.assertFalse(two.committed, "the second overlapping submit was not refused")
		self.assertIsInstance(two.error, OverlappingAgreementError, repr(two.error))
		rows = self._committed(self._agreements)
		self.assertEqual([row.daily_rate for row in rows], [500])

	def test_two_overlapping_submits_with_the_server_snapshot_setting(self):
		# MariaDB 11.8 default (snapshot isolation ON) may refuse with error 1020 instead of the validation
		# message; either way only one agreement is submitted and the refused request wrote nothing
		_one, two = self._race(
			self._submit("2026-03-01", 500), self._submit("2026-03-15", 600), snapshot_isolation=None
		)
		self.assertFalse(two.committed)
		self.assertIsInstance(two.error, SAFE_ERRORS, repr(two.error))
		self.assertEqual(len(self._committed(self._agreements)), 1)

	def test_two_submits_that_do_not_overlap(self):
		# positive control: another supplier is another key; the lock queues the second submit, never refuses it
		_one, two = self._race(
			self._submit("2026-03-01", 500), self._submit("2026-03-01", 600, supplier=self.supplier2)
		)
		self.assertTrue(two.committed, repr(two.error))
		self.assertEqual(sorted(row.daily_rate for row in self._committed(self._agreements)), [500, 600])
