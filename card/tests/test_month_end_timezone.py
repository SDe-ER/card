# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-136 (#54 test matrix row 4): month end and "today" under a site time zone other than UTC.

Frappe's ``nowdate()`` / ``now_datetime()`` give the date of the site time zone (System Settings ``time_zone``).
The tests freeze one instant, 2026-09-30 22:30 UTC, which is 1 October in Riyadh (UTC+3) and Kiritimati (UTC+14)
but still 30 September in Los Angeles (UTC-7) and Honolulu (UTC-10), and prove:

- "today" in CARD is the site's local date (the future-day check on a monthly card, the "last month" of the
  dashboard number cards);
- the monthly posting is dated the last day of its month (28/29 February, 30/31), whatever the zone and the hour
  the build runs;
- the period lock compares document dates only, so its boundary day does not move with the zone.

CARD stores dates, not times, for every period rule; nothing here changes behaviour."""

from unittest.mock import patch

import frappe
from frappe.utils import getdate, nowdate

from card import period_lock
from card.card_value import _last_month
from card.gl.posting import _month_bounds, build_monthly_posting
from card.tests.test_controllers import _days
from card.tests.test_s3_posting import _PostingBase

INSTANT = "2026-09-30 22:30:00"  # UTC
AHEAD = ("Asia/Riyadh", "Pacific/Kiritimati")  # already 1 October
BEHIND = ("America/Los_Angeles", "Pacific/Honolulu")  # still 30 September


class TestMonthEndTimezone(_PostingBase):
	def _at(self, zone, instant=INSTANT):
		"""Freeze ``instant`` (UTC) with ``zone`` as the site time zone."""
		self.enterContext(patch("frappe.utils.data.get_system_timezone", return_value=zone))
		self.enterContext(self.freeze_time(instant, is_utc=True))

	def _october_card(self, eq):
		card = frappe.new_doc("Card Monthly Card")
		card.equipment = eq.name
		card.project = self.project
		card.shift = "نهاري"
		card.month = "10"
		card.year = 2026
		for row in _days([8], month=10):
			card.append("days", row)
		return card

	def test_today_is_the_site_local_date(self):
		for zone, expected in [(z, "2026-10-01") for z in AHEAD] + [(z, "2026-09-30") for z in BEHIND]:
			with self.subTest(zone=zone):
				with patch("frappe.utils.data.get_system_timezone", return_value=zone):
					with self.freeze_time(INSTANT, is_utc=True):
						self.assertEqual(nowdate(), expected)

	def test_first_of_month_hours_are_accepted_where_it_is_already_that_day(self):
		eq = self._equipment()
		self._at("Asia/Riyadh")
		card = self._october_card(eq)
		card.insert(ignore_permissions=True)
		self.assertEqual(getdate(card.from_date), getdate("2026-10-01"))
		self.assertEqual(getdate(card.to_date), getdate("2026-10-31"))

	def test_first_of_month_hours_are_future_where_it_is_still_the_last_day(self):
		eq = self._equipment()
		self._at("America/Los_Angeles")
		with self.assertRaisesRegex(frappe.ValidationError, "future day"):
			self._october_card(eq).insert(ignore_permissions=True)

	def test_last_month_follows_the_site_zone(self):
		with patch("frappe.utils.data.get_system_timezone", return_value="Asia/Riyadh"):
			with self.freeze_time(INSTANT, is_utc=True):
				self.assertEqual(_last_month(), (getdate("2026-09-01"), getdate("2026-09-30")))
		with patch("frappe.utils.data.get_system_timezone", return_value="America/Los_Angeles"):
			with self.freeze_time(INSTANT, is_utc=True):
				self.assertEqual(_last_month(), (getdate("2026-08-01"), getdate("2026-08-31")))

	def test_month_bounds_end_on_the_last_calendar_day(self):
		for month, year, last in (
			(2, 2026, "2026-02-28"),
			(2, 2028, "2028-02-29"),
			(4, 2026, "2026-04-30"),
			(9, 2026, "2026-09-30"),
			(12, 2026, "2026-12-31"),
		):
			with self.subTest(month=month, year=year):
				first, end = _month_bounds(month, year)
				self.assertEqual(first, getdate("%04d-%02d-01" % (year, month)))
				self.assertEqual(end, getdate(last))

	def test_posting_built_after_local_midnight_is_dated_the_month_end(self):
		eq = self._equipment()
		self._card(eq, [8, 8], submit=True)  # September
		self._at("Asia/Riyadh")  # already 1 October locally, 30 September in UTC
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		self.assertEqual(getdate(pi.posting_date), getdate("2026-09-30"))

	def test_period_lock_boundary_is_a_date_in_every_zone(self):
		frappe.db.set_single_value("Card Settings", "period_lock_date", "2026-09-30")
		frappe.db.set_single_value("Card Settings", "period_lock_override_role", None)
		for zone in AHEAD + BEHIND:
			with self.subTest(zone=zone):
				with patch("frappe.utils.data.get_system_timezone", return_value=zone):
					with self.freeze_time(INSTANT, is_utc=True):
						locked = frappe.get_doc(
							{"doctype": "Project Diesel Fill", "company": self.company, "date": "2026-09-30"}
						)
						with self.assertRaises(frappe.ValidationError):
							period_lock.enforce(locked, "save")
						open_day = frappe.get_doc(
							{"doctype": "Project Diesel Fill", "company": self.company, "date": "2026-10-01"}
						)
						period_lock.enforce(open_day, "save")
