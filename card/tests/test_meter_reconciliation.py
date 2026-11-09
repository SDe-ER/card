# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Maintenance plan R1 (Owner approval 2026-10-31): read-only equipment meter reconciliation. Meter readings
are cumulative: only differences between consecutive plausible readings are hours; resets, backward readings,
duplicates, invalid readings, impossible jumps and cumulative "hours run" values are flagged, never summed; CARD
hours come from submitted cards only; no maintenance baseline is set."""

import datetime

import frappe
from frappe.tests import IntegrationTestCase

from card.meter_reconciliation import (
	BACKWARD,
	CUMULATIVE,
	DUPLICATE,
	FLAG_LABELS,
	INVALID,
	JUMP,
	OK,
	RESET,
	card_hours,
	classify_readings,
	identity_conflict,
	legacy_readings,
	summarize,
)
from card.tests.test_s3_posting import _PostingBase


def _r(day, reading, hours_run=None, hour=8):
	return {
		"source": "test",
		"ref": f"R-{day}-{hour}",
		"at": datetime.datetime(2025, 12, day, hour),
		"reading": reading,
		"hours_run": hours_run,
	}


class TestReadingChecks(IntegrationTestCase):
	def test_only_differences_between_plausible_readings_count(self):
		rows = classify_readings([_r(9, 36105, hours_run=36105), _r(10, 36126, 21), _r(11, 36148, 22)])
		self.assertEqual([r["flag"] for r in rows], [OK, OK, OK])
		self.assertEqual([r["meter_hours"] for r in rows], [0, 21, 22])
		summary = summarize(rows, lambda a, b: 0)
		self.assertEqual(summary["meter_hours"], 43)  # never 36105 + 36126 + 36148 or the cumulative 36105
		self.assertEqual(rows[0]["note"], FLAG_LABELS[CUMULATIVE])
		self.assertEqual(summary["counts"][CUMULATIVE], 1)

	def test_backward_reset_duplicate_invalid_and_jump_are_flagged(self):
		rows = classify_readings(
			[
				_r(14, 22632),
				_r(15, 22638, hour=11),
				_r(15, 22638, hour=12),  # same value the same day
				_r(27, 22696, hour=11),
				_r(27, 22645, hour=15),  # backward
				_r(28, 0),  # invalid
				_r(29, 22700),
				_r(30, 23500),  # 800 h in one day
				_r(31, 40),  # reset: a new meter
				_r(31, 52, hour=20),
			]
		)
		self.assertEqual(
			[r["flag"] for r in rows], [OK, OK, DUPLICATE, OK, BACKWARD, INVALID, OK, JUMP, RESET, OK]
		)
		summary = summarize(rows, lambda a, b: 0)
		# 6 + 58 + 4 before the reset, 12 after it; the backward, jump and reset readings add nothing
		self.assertEqual(summary["meter_hours"], 80)
		self.assertEqual(summary["last"]["reading"], 52)

	def test_card_hours_are_compared_over_the_plausible_period(self):
		calls = []
		rows = classify_readings([_r(9, 100), _r(20, 160)])

		def hours(a, b):
			calls.append((a, b))
			return 55

		summary = summarize(rows, hours)
		self.assertEqual(calls, [(datetime.date(2025, 12, 9), datetime.date(2025, 12, 20))])
		self.assertEqual((summary["meter_hours"], summary["card_hours"]), (60, 55))

	def test_identity_conflicts_are_flagged_for_review_only(self):
		self.assertEqual(
			identity_conflict("C15-1-red-gen", "مولد كتربيلر c13-1 احمر", "C13-1 red"), ["C15 / C13"]
		)
		self.assertEqual(identity_conflict("C15-2-red-gen", "مولد كتربيلر c15-2 احمر", "C15-2 red"), [])
		self.assertEqual(
			identity_conflict("CR-7", "كسارة رقم 7 PF-1315V - الهيكل: CR-IMP-2024-007", "CR-7-ITEM"), []
		)
		self.assertEqual(identity_conflict("Perk-3-Green-Gen", "مولد بركنز 3 اخضر", "PER-3-Green"), [])

	def test_no_legacy_log_means_no_readings(self):
		if frappe.db.exists("DocType", "Fueling Log"):
			self.skipTest("this site has the legacy fuelling log")
		self.assertEqual(legacy_readings({"ANY-ASSET"}), ({}, False))


class TestCardHoursAndReport(_PostingBase):
	def test_card_hours_count_submitted_cards_only(self):
		eq = self._equipment()
		self._card(eq, [8, 8, 6], submit=True)
		draft_eq = self._equipment()
		self._card(draft_eq, [8, 8])
		self.assertEqual(card_hours(eq.name, "2026-09-01", "2026-09-30"), 22)
		self.assertEqual(card_hours(eq.name, "2026-09-02", "2026-09-02"), 8)
		self.assertEqual(card_hours(draft_eq.name, "2026-09-01", "2026-09-30"), 0)

	def test_report_reads_only_and_sets_no_baseline(self):
		from card.card.report.equipment_meter_reconciliation.equipment_meter_reconciliation import execute

		eq = self._equipment()
		before = frappe.db.get_value("Card Equipment", eq.name, "modified")
		_columns, rows, message, _chart, _summary = execute(
			{"company": self.company, "equipment": eq.name, "show": "All"}
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["equipment"], eq.name)
		self.assertIn("250", message)
		self.assertIn("300", message)
		self.assertTrue(rows[0]["baseline"].startswith("Not set"))
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "modified"), before)
		_c, readings, *_ = execute({"company": self.company, "equipment": eq.name, "view": "Readings"})
		self.assertEqual(readings, [])  # no legacy readings for a new machine

	def test_report_needs_its_role(self):
		from card.card.report.equipment_meter_reconciliation.equipment_meter_reconciliation import execute

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": f"r1-{frappe.generate_hash(length=8)}@example.com",
				"first_name": "R1",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(user.name)
		with self.assertRaises(frappe.PermissionError):
			execute({"company": self.company})
