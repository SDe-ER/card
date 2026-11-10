# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-145 (#44, #123; WP-K2): two concurrent card generations for the same equipment never create the same card
twice.

Each request runs in its own thread with its own database connection and commits, as two web requests do: its
first read fixes its REPEATABLE READ snapshot, and both requests take their snapshot before either writes. The
first request generates the cards and keeps its transaction open; the second waits on the equipment lock, then its
locking read sees the first request's cards, which its snapshot cannot see, so it skips the equipment and reports a
conflict. The synthetic records are committed (a race needs two real transactions) and removed in tearDown.
Modelled on test_agreements_concurrency (same MariaDB 10.6 / 11.8 snapshot-isolation handling)."""

import frappe
from frappe.utils import add_months, get_first_day, nowdate

from card.daily_log_generation import generate_monthly_cards
from card.tests import test_agreements_concurrency as base
from card.tests.test_agreements_concurrency import GRACE, SAFE_ERRORS, WAIT, _Request, _wait_any

CARD = "Card Monthly Card"
LOG = "Card Daily Log"


class _Generation(_Request):
	"""One generation request; its result is kept."""

	def __init__(self, test, snapshot_isolation):
		self.result = None
		super().__init__(test, self._generate, snapshot_isolation)

	def _generate(self):
		self.result = generate_monthly_cards(
			company=self.test.company, project=self.test.project, month=self.test.month
		)


class TestDailyLogGenerationConcurrency(base.TestRateAgreementConcurrency):
	# the parent's agreement tests are not repeated here
	test_two_overlapping_submits = None
	test_two_overlapping_submits_with_the_server_snapshot_setting = None
	test_two_submits_that_do_not_overlap = None

	def _make_records(self):
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		if not self.company:
			self.skipTest("test company missing (card.install.before_tests)")
		first = get_first_day(add_months(nowdate(), -1))
		self.month, self.day = str(first)[:7], first
		self.project = self._raw(
			"Project", "K2-RACE-P-" + self.token, project_name="K2" + self.token, company=self.company
		)
		self.equipment = self._raw(
			"Card Equipment",
			"K2-RACE-E-" + self.token,
			company=self.company,
			equipment_name="K2" + self.token,
			ownership="ملك",
		)
		self.log = self._raw(
			LOG,
			"K2-RACE-L-" + self.token,
			company=self.company,
			project=self.project,
			log_date=first,
			docstatus=1,
			approval_status="Approved",
		)
		self._raw(
			"Card Daily Log Row",
			"K2-RACE-R-" + self.token,
			parent=self.log,
			parenttype=LOG,
			parentfield="rows",
			idx=1,
			equipment=self.equipment,
			day_hours=8,
			night_hours=4,
		)

	def _cards(self):
		return frappe.get_all(
			CARD, filters={"equipment": self.equipment, "docstatus": ["!=", 2]}, fields=["name", "shift"]
		)

	def _remove_records(self):
		cards = frappe.get_all(CARD, filters={"equipment": self.equipment}, pluck="name")
		for name in cards:
			frappe.db.delete("Card Monthly Card Day", {"parent": name, "parenttype": CARD})
			frappe.db.delete("Card Monthly Card Adjustment", {"parent": name, "parenttype": CARD})
			frappe.db.delete(CARD, {"name": name})
		frappe.db.delete("Card Daily Log Row", {"parent": self.log, "parenttype": LOG})
		for doctype, name in ((LOG, self.log), ("Card Equipment", self.equipment), ("Project", self.project)):
			frappe.db.delete(doctype, {"name": name})
		since = {"creation": [">=", self.started]}
		for name in [*cards, self.log, self.equipment, self.project]:
			frappe.db.delete("Version", {"docname": name, **since})
			frappe.db.delete("Comment", {"reference_name": name, **since})

	def _leftovers(self):
		counts = {
			CARD: frappe.db.count(CARD, {"equipment": self.equipment}),
			LOG: frappe.db.count(LOG, {"name": self.log}),
			"Card Equipment": frappe.db.count("Card Equipment", {"name": self.equipment}),
			"Project": frappe.db.count("Project", {"name": self.project}),
		}
		return {key: value for key, value in counts.items() if value}

	def _generations(self, snapshot_isolation=False):
		one, two = _Generation(self, snapshot_isolation), _Generation(self, snapshot_isolation)
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

	def test_two_concurrent_generations_create_each_card_once(self):
		one, two = self._generations()
		self.assertEqual(len(one.result["created"]), 2, one.result)
		self.assertIsNone(two.error, repr(two.error))
		self.assertEqual(two.result["created"], [], two.result)
		self.assertEqual([c["equipment"] for c in two.result["conflicts"]], [self.equipment])
		cards = self._committed(self._cards)
		self.assertEqual(sorted(c.shift for c in cards), sorted(["نهاري", "ليلي"]), cards)

	def test_two_concurrent_generations_with_the_server_snapshot_setting(self):
		# MariaDB 11.8 default (snapshot isolation ON) may refuse the locking read with error 1020 instead; either
		# way each card exists once
		_one, two = self._generations(snapshot_isolation=None)
		if two.error is not None:
			self.assertIsInstance(two.error, SAFE_ERRORS, repr(two.error))
		self.assertEqual(len(self._committed(self._cards)), 2)

	def test_a_run_after_the_other_committed_is_not_a_conflict(self):
		# positive control: a request that starts after the first one committed sees its cards and changes nothing
		def run():
			return generate_monthly_cards(company=self.company, project=self.project, month=self.month)

		first = self._committed(run)
		second = self._committed(run)
		self.assertEqual(len(first["created"]), 2)
		self.assertEqual((second["created"], second["conflicts"]), ([], []))
		self.assertEqual(len(second["unchanged"]), 2)
