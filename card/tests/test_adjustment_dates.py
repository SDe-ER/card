# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Additions/deductions are dated and must fall inside their card's period (Owner, 2026-11-16).

The check is a pure function, so these tests need no site data."""

import frappe
from frappe.tests import UnitTestCase

from card.adjustments import check_adjustment_date

START, END = "2026-09-01", "2026-09-30"


class TestAdjustmentDate(UnitTestCase):
	def test_date_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			check_adjustment_date("standby", None, START, END)

	def test_date_before_the_period_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			check_adjustment_date("standby", "2026-08-31", START, END)

	def test_date_after_the_period_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			check_adjustment_date("standby", "2026-10-01", START, END)

	def test_period_edges_are_accepted(self):
		check_adjustment_date("standby", START, START, END)
		check_adjustment_date("standby", END, START, END)

	def test_mid_period_date_is_accepted(self):
		check_adjustment_date("standby", "2026-09-15", START, END)
