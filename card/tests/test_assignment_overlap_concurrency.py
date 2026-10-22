# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""D4: two requests that write Card Equipment Assignments of one machine at the same time
never leave two overlapping periods.

Each request runs in its own thread with its own database connection and commits, as two
web requests do: its first read fixes its REPEATABLE READ snapshot, and both requests take
their snapshot before either writes. The synthetic records are committed too (a race needs
two real transactions) and are removed in tearDown, together with the Version, Comment and
Deleted Document rows they produced.

MariaDB 10.6 (Production) answers a locking read with the latest committed row. MariaDB 11.8
with innodb_snapshot_isolation ON refuses a locking read of a row changed after the snapshot
(error 1020, a deadlock error in Frappe) instead. The strict cases therefore set the variable
OFF in their own sessions only (10.6 behaviour); the server setting is never changed."""

import contextvars
import json
import threading
import time
from unittest.mock import patch

import frappe
from frappe.exceptions import QueryDeadlockError, QueryTimeoutError
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from card.card.doctype.card_equipment_assignment.card_equipment_assignment import OPEN_END

WAIT = 30  # seconds; a stuck step fails the test instead of hanging the run
GRACE = 1  # seconds the second request gets to reach the first one's lock before it commits
LOCK_WAIT = 10  # innodb_lock_wait_timeout of the two requests (session only)
# what a refused or rolled-back request may raise; anything else fails the test
SAFE_ERRORS = (frappe.ValidationError, QueryDeadlockError, QueryTimeoutError)
CLEANED = ("Card Equipment Assignment", "Equipment Transport", "Card Equipment", "Project", "Supplier")


def _wait_any(*events, timeout=WAIT):
	deadline = time.monotonic() + timeout
	while time.monotonic() < deadline:
		if any(event.is_set() for event in events):
			return True
		events[0].wait(0.05)
	return False


def _overlaps(rows):
	def end(row):
		return getdate(row.to_date or OPEN_END)

	rows = [row for row in rows if row.from_date]
	return [
		(a.name, b.name)
		for i, a in enumerate(rows)
		for b in rows[i + 1 :]
		if getdate(a.from_date) <= end(b) and getdate(b.from_date) <= end(a)
	]


def _delete(doctype, name):
	# test data: no Deleted Document and no "Deleted" feed comment is kept
	frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)


class _Request(threading.Thread):
	"""One web request: its own connection and snapshot; it runs `action` when told, keeps
	its transaction open until released, then commits, or rolls back on an error."""

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
			frappe.db.sql("select count(*) from `tabCard Equipment Assignment`")
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


class TestAssignmentOverlapConcurrency(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.has_snapshot_isolation = bool(frappe.db.sql("show variables like 'innodb_snapshot_isolation'"))

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.created = {doctype: [] for doctype in CLEANED}
		self.started = self._committed(frappe.utils.now)
		self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)
		left = self._committed(self._leftovers)
		self.assertEqual(left, {}, "synthetic records left behind")

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
		"""Both requests take their snapshot; `first` writes and keeps its transaction open
		while `second` runs, then commits. snapshot_isolation=False is MariaDB 10.6
		behaviour, None keeps the server setting."""
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

	# ---- records ----
	def _d(self, day):
		return str(add_days(self.base, day - 1))

	def _make_records(self):
		company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		etype = frappe.db.get_value("Card Equipment Type", {}, "name", order_by="creation asc")
		self.supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
		if not (company and etype and self.supplier_group):
			self.skipTest("test masters missing (card.install.before_tests)")
		self.company = company
		# far from today and from any period lock date: no other record uses these days
		self.base = getdate(add_days(nowdate(), 60))
		self.p1, self.p2, self.p3 = (
			self._new("Project", self._project(label)) for label in ("P1", "P2", "P3")
		)
		self.e1, self.e2 = (self._new("Card Equipment", self._equipment(etype)) for _ in range(2))

	def _new(self, doctype, values):
		doc = frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
		self.created[doctype].append(doc.name)
		return doc.name

	def _project(self, label):
		return {"project_name": "D4-%s-%s" % (label, self.token), "company": self.company}

	def _equipment(self, etype):
		return {
			"company": self.company,
			"equipment_type": etype,
			"equipment_name": "D4-EQ-%s" % frappe.generate_hash(length=8),
			"ownership": "ملك",
			"rate_type": "باليوم",
			"rate": 750,
			"daily_hours": 10,
		}

	def _insert(self, equipment, project, from_day, to_day=None):
		values = {"equipment": equipment, "project": project, "from_date": self._d(from_day)}
		if to_day:
			values["to_date"] = self._d(to_day)
		return frappe.get_doc({"doctype": "Card Equipment Assignment", **values}).insert(
			ignore_permissions=True
		)

	def _reopen(self, name):
		doc = frappe.get_doc("Card Equipment Assignment", name)
		doc.to_date = None
		doc.save(ignore_permissions=True)

	def _transport(self, equipment, project, day, submit=True):
		if not self.created["Supplier"]:
			self._new(
				"Supplier",
				{"supplier_name": "D4-SUP-" + self.token, "supplier_group": self.supplier_group},
			)
		values = {
			"equipment": equipment,
			"project": project,
			"date": self._d(day),
			"transport_supplier": self.created["Supplier"][0],
			"company": self.company,
			"amount": 100,
		}
		name = self._new("Equipment Transport", values)
		if submit:
			frappe.get_doc("Equipment Transport", name).submit()
		return name

	def _rows(self, equipment):
		return self._committed(
			lambda: frappe.get_all(
				"Card Equipment Assignment",
				filters={"equipment": equipment},
				fields=["name", "project", "from_date", "to_date"],
				order_by="from_date asc",
			)
		)

	def _periods(self, equipment):
		rows = self._rows(equipment)
		self.assertEqual(_overlaps(rows), [], "overlapping assignments: %s" % rows)
		return [(r.project, str(r.from_date), str(r.to_date) if r.to_date else None) for r in rows]

	def _assert_refused(self, request, equipment):
		self.assertFalse(request.committed, "the second request was not refused")
		self.assertIsInstance(request.error, frappe.ValidationError, repr(request.error))
		self.assertIn(equipment, str(request.error))

	def _remove_records(self):
		frappe.flags.card_defer_location_sync = True
		transports = frappe.get_all(
			"Equipment Transport",
			filters={"name": ["in", self.created["Equipment Transport"] or [""]]},
			fields=["name", "docstatus"],
			order_by="date desc, creation desc",
		)
		for transport in transports:
			if transport.docstatus == 1:
				frappe.get_doc("Equipment Transport", transport.name).cancel()
			_delete("Equipment Transport", transport.name)
		self.created["Card Equipment Assignment"] = frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": ["in", self.created["Card Equipment"] or [""]]},
			pluck="name",
		)
		for doctype in CLEANED:
			if doctype != "Equipment Transport":
				for name in self.created[doctype]:
					_delete(doctype, name)
		# assignments a transport cancel deleted itself (reverse_transfer) are known only
		# from their Deleted Document
		self.created["Card Equipment Assignment"] += self._deleted_assignments()
		for filters in self._trail():
			frappe.db.delete(filters.pop("doctype"), filters)

	def _deleted_assignments(self):
		equipment = set(self.created["Card Equipment"])
		rows = frappe.get_all(
			"Deleted Document",
			filters={"deleted_doctype": "Card Equipment Assignment", "creation": [">=", self.started]},
			fields=["deleted_name", "data"],
		)
		return [row.deleted_name for row in rows if json.loads(row.data).get("equipment") in equipment]

	def _trail(self):
		"""Filters of the rows the test records left: Versions, Comments, Deleted Documents
		and the "Deleted" feed comment Frappe writes for every delete. Only rows created by
		this test: a name can repeat an older record's name."""
		since = {"creation": [">=", self.started]}
		mine = [name for names in self.created.values() for name in names] or [""]
		trail = [
			{"doctype": "Version", "docname": ["in", mine], **since},
			{"doctype": "Comment", "reference_name": ["in", mine], **since},
		]
		for doctype in CLEANED:
			for name in self.created[doctype]:
				trail.append(
					{"doctype": "Deleted Document", "deleted_doctype": doctype, "deleted_name": name, **since}
				)
				trail.append(
					{
						"doctype": "Comment",
						"comment_type": "Deleted",
						"reference_doctype": doctype,
						"subject": ["like", "% " + name],
						**since,
					}
				)
		return trail

	def _leftovers(self):
		counts = {
			doctype: frappe.db.count(doctype, {"name": ["in", self.created[doctype] or [""]]})
			for doctype in CLEANED
		}
		counts["Card Equipment Assignment"] += frappe.db.count(
			"Card Equipment Assignment", {"equipment": ["in", self.created["Card Equipment"] or [""]]}
		)
		for filters in self._trail():
			doctype = filters.pop("doctype")
			counts[doctype] = counts.get(doctype, 0) + frappe.db.count(doctype, filters)
		return {key: value for key, value in counts.items() if value}

	# ---- R2: two new assignments of one machine ----
	def test_r2_two_new_assignments_of_one_machine(self):
		_one, two = self._race(
			lambda: self._insert(self.e1, self.p1, 1), lambda: self._insert(self.e1, self.p2, 1)
		)
		self._assert_refused(two, self.e1)
		self.assertEqual(self._periods(self.e1), [(self.p1, self._d(1), None)])

	def test_r2_with_the_server_snapshot_setting(self):
		# MariaDB 11.8 default (snapshot isolation ON) may refuse with error 1020 instead of
		# the validation message; either way nothing overlaps and the refused request wrote nothing
		_one, two = self._race(
			lambda: self._insert(self.e1, self.p1, 1),
			lambda: self._insert(self.e1, self.p2, 1),
			snapshot_isolation=None,
		)
		self.assertFalse(two.committed)
		self.assertIsInstance(two.error, SAFE_ERRORS, repr(two.error))
		self.assertEqual(self._periods(self.e1), [(self.p1, self._d(1), None)])

	# ---- R4: reopen (what a transport cancel does) against a new assignment ----
	def test_r4_reopen_then_new_assignment(self):
		closed = self._committed(lambda: self._insert(self.e1, self.p1, 1, 10).name)
		_one, two = self._race(lambda: self._reopen(closed), lambda: self._insert(self.e1, self.p2, 11))
		self._assert_refused(two, self.e1)
		self.assertEqual(self._periods(self.e1), [(self.p1, self._d(1), None)])

	def test_r4_new_assignment_then_reopen(self):
		closed = self._committed(lambda: self._insert(self.e1, self.p1, 1, 10).name)
		_one, two = self._race(lambda: self._insert(self.e1, self.p2, 11), lambda: self._reopen(closed))
		self._assert_refused(two, self.e1)
		self.assertEqual(
			self._periods(self.e1), [(self.p1, self._d(1), self._d(10)), (self.p2, self._d(11), None)]
		)

	# ---- R4-T: transport cancel against the submit of the machine's next move ----
	def _transport_race(self, cancel_first):
		def setup():
			self._insert(self.e1, self.p1, 1)
			moved = self._transport(self.e1, self.p2, 10)  # P1 closes on day 10, P2 opens on day 11
			return moved, self._transport(self.e1, self.p3, 20, submit=False)

		moved, next_move = self._committed(setup)

		def cancel():
			frappe.get_doc("Equipment Transport", moved).cancel()

		def submit():
			frappe.get_doc("Equipment Transport", next_move).submit()

		one, two = self._race(*((cancel, submit) if cancel_first else (submit, cancel)))
		cancelled, submitted = (one, two) if cancel_first else (two, one)
		for request in (one, two):
			if not request.committed:
				self.assertIsInstance(request.error, SAFE_ERRORS, repr(request.error))
		status = self._committed(
			lambda: {
				name: frappe.db.get_value("Equipment Transport", name, "docstatus")
				for name in (moved, next_move)
			}
		)
		self.assertEqual(
			status, {moved: 2 if cancelled.committed else 1, next_move: 1 if submitted.committed else 0}
		)
		expected = {
			(True, False): [(self.p1, self._d(1), None)],
			(False, True): [
				(self.p1, self._d(1), self._d(10)),
				(self.p2, self._d(11), self._d(20)),
				(self.p3, self._d(21), None),
			],
			(True, True): [(self.p1, self._d(1), self._d(20)), (self.p3, self._d(21), None)],
		}
		self.assertEqual(self._periods(self.e1), expected[(cancelled.committed, submitted.committed)])

	def test_r4t_cancel_then_next_move_submit(self):
		self._transport_race(cancel_first=True)

	def test_r4t_next_move_submit_then_cancel(self):
		self._transport_race(cancel_first=False)

	# ---- two machines at the same time: both are written ----
	def test_two_machines_are_both_assigned(self):
		_one, two = self._race(
			lambda: self._insert(self.e1, self.p1, 1), lambda: self._insert(self.e2, self.p2, 1)
		)
		self.assertTrue(two.committed, repr(two.error))
		self.assertEqual(self._periods(self.e1), [(self.p1, self._d(1), None)])
		self.assertEqual(self._periods(self.e2), [(self.p2, self._d(1), None)])


class TestOverlapCheckLocking(IntegrationTestCase):
	"""The check itself, without a database write: machine lock first, then a locking read."""

	def test_overlap_check_locks_the_machine_then_reads_with_a_lock(self):
		doc = frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": "D4-EQ-X",
				"project": "D4-P",
				"from_date": "2026-01-01",
			}
		)
		calls = []
		db_class = type(frappe.local.db)
		with (
			patch.object(
				db_class, "get_value", side_effect=lambda *a, **k: calls.append(("get_value", a, k))
			),
			patch.object(db_class, "sql", side_effect=lambda *a, **k: calls.append(("sql", a, k)) or []),
		):
			doc.validate_no_overlap()
		self.assertEqual([call[0] for call in calls], ["get_value", "sql"])
		self.assertEqual(calls[0][1][:3], ("Card Equipment", "D4-EQ-X", "name"))
		self.assertTrue(calls[0][2].get("for_update"))
		self.assertTrue(" ".join(calls[1][1][0].lower().split()).endswith("limit 1 for update"))
