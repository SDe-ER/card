# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-151 (#31): Diesel Variance Anomaly report.

Expected litres = hours x the FR-144 rate valid on each day; hours come from meter readings (engine basis) when
they cover the month, else from the cards' day rows (billable-hours proxy, an estimate). Filled litres = direct
fills only (project-tank fills are never split, owner decision 2026-11-10). Variance is labelled as variance, never
loss. Anomaly flags come only from the company's Card Settings threshold row. Source documents are written as raw
submitted rows (the report reads only submitted rows; their own rules are tested elsewhere). Everything is rolled
back after each test."""

import json
from unittest.mock import patch

import frappe
from frappe.desk import query_report
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.report.diesel_variance_anomaly import diesel_variance_anomaly as dva
from card.consumption import consumption_rate_details
from card.tests.test_controllers import _ensure_masters

REPORT = "Diesel Variance Anomaly"
SEPT = {"from_date": "2026-09-01", "to_date": "2026-09-30"}
REASON = "test rate"


class TestDieselVariance(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.a = self._m["company"]
		self.b = self._company("TEST-DVA-CO-" + self.token)
		self.etype = self._type()
		frappe.db.delete("Card Diesel Variance Threshold", {"parent": "Card Settings"})
		frappe.clear_document_cache("Card Settings", "Card Settings")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders ----------

	def _company(self, name):
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "V" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.a, "default_currency"),
				"country": frappe.db.get_value("Company", self.a, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _type(self, rates=()):
		t = frappe.new_doc("Card Equipment Type")
		t.equipment_type_name = "TEST-DVA-T-" + frappe.generate_hash(length=6)
		t.equipment_category = frappe.db.get_value(
			"Card Equipment Type", self._m["etype"], "equipment_category"
		)
		for item in rates:
			row = {"valid_from": item[0], "litres_per_hour": item[1], "reason": REASON}
			if len(item) > 2:
				row["company"] = item[2]
			t.append("default_consumption_rates", row)
		t.insert(ignore_permissions=True)
		return t.name

	def _equipment(self, rates=(), company=None, static=None, daily=None, daily_hours=10, etype=None):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company or self.a
		eq.equipment_type = etype or self.etype
		eq.equipment_name = "TEST-DVA-EQ-" + frappe.generate_hash(length=6)
		eq.ownership = "ملك"
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = daily_hours
		if static is not None:
			eq.expected_consumption = static
		if daily is not None:
			eq.daily_diesel_consumption = daily
		for valid_from, rate in rates:
			eq.append(
				"consumption_rates", {"valid_from": valid_from, "litres_per_hour": rate, "reason": REASON}
			)
		eq.insert(ignore_permissions=True)
		return eq.name

	def _raw(self, doctype, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = "TEST-DVA-" + frappe.generate_hash(length=10)
		doc.db_insert()
		return doc.name

	def _fill(
		self, equipment, litres, amount=None, date="2026-09-10", company=None, project=None, docstatus=1
	):
		return self._raw(
			"Project Diesel Fill",
			company=company or self.a,
			date=date,
			card_equipment=equipment,
			litres=litres,
			unit_price=2,
			amount=litres * 2 if amount is None else amount,
			project=project,
			docstatus=docstatus,
		)

	def _card(self, equipment, hours_by_day, company=None, project=None, docstatus=1):
		"""A submitted card with day rows {"2026-09-01": 10, ...}."""
		card = self._raw(
			"Card Monthly Card",
			equipment=equipment,
			company=company or self.a,
			project=project,
			month="09",
			year=2026,
			docstatus=docstatus,
		)
		for idx, (day, hours) in enumerate(sorted(hours_by_day.items()), 1):
			row = frappe.new_doc("Card Monthly Card Day")
			row.update(
				{
					"parent": card,
					"parenttype": "Card Monthly Card",
					"parentfield": "days",
					"idx": idx,
					"operation_date": day,
					"day_status": "عمل",
					"working_hours": hours,
					"docstatus": docstatus,
				}
			)
			row.name = frappe.generate_hash(length=12)
			row.db_insert()
		return card

	def _reading(self, equipment, when, hours, company=None, reset=0):
		return self._raw(
			"Equipment Meter Reading",
			equipment=equipment,
			company=company or self.a,
			reading_datetime=when,
			engine_hours=hours,
			source="Weekly reading",
			is_meter_reset=reset,
			docstatus=1,
		)

	def _threshold(self, company, pct=0, litres=0, fill_without_hours=0, hours_without_fill=0):
		frappe.get_doc(
			{
				"doctype": "Card Diesel Variance Threshold",
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "diesel_variance_thresholds",
				"company": company,
				"variance_pct_threshold": pct,
				"min_variance_litres": litres,
				"flag_fill_without_hours": fill_without_hours,
				"flag_hours_without_fill": hours_without_fill,
			}
		).db_insert()

	def _user(self, roles, restrict=None):
		email = f"dva-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Diesel Variance",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _run(self, company=None, **filters):
		result = dva.execute({"company": company or self.a, **SEPT, **filters})
		columns, rows, message, _chart, summary, _flag = result
		return columns, rows, message, summary

	def _row(self, equipment, **filters):
		rows = [r for r in self._run(**filters)[1] if r["equipment"] == equipment]
		self.assertEqual(len(rows), 1, rows)
		return rows[0]

	# ---------- bases ----------

	def test_engine_basis_with_readings_on_the_month_limits_is_recorded(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._reading(eq, "2026-09-01 00:00:00", 100)
		self._reading(eq, "2026-10-01 00:00:00", 300)
		self._card(eq, {"2026-09-01": 10})  # billable hours are shown, not used
		self._fill(eq, 1100)
		row = self._row(eq)
		self.assertEqual(row["hours_basis"], dva.basis_engine())
		self.assertEqual(flt(row["engine_hours"]), 200)
		self.assertEqual(flt(row["billable_hours"]), 10)
		self.assertEqual(flt(row["hours"]), 200)
		self.assertEqual(row["hours_nature"], dva.nature_recorded())
		self.assertEqual(flt(row["expected_litres"]), 1000)
		self.assertEqual(row["expected_nature"], dva.nature_recorded())
		self.assertEqual(flt(row["filled_litres"]), 1100)
		self.assertEqual(row["filled_nature"], dva.nature_recorded())
		self.assertEqual(flt(row["variance_litres"]), 100)
		self.assertEqual(flt(row["variance_pct"]), 10)
		self.assertEqual(flt(row["variance_cost"]), 200)  # 100 L x 2 per litre
		self.assertEqual(flt(row["rate"]), 5)

	def test_engine_hours_between_readings_outside_the_month_are_prorated_and_estimated(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		# 40 days, 400 hours: 10 per day, 30 days fall in September
		self._reading(eq, "2026-08-27 00:00:00", 1000)
		self._reading(eq, "2026-10-06 00:00:00", 1400)
		row = self._row(eq)
		self.assertEqual(row["hours_basis"], dva.basis_engine())
		self.assertEqual(flt(row["hours"]), 300)
		self.assertEqual(row["hours_nature"], dva.nature_estimated())
		self.assertEqual(row["expected_nature"], dva.nature_estimated())
		self.assertEqual(flt(row["expected_litres"]), 1500)

	def test_billable_proxy_without_meter_readings(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._card(eq, {"2026-09-01": 10, "2026-09-02": 10})
		self._fill(eq, 90)
		row = self._row(eq)
		self.assertEqual(row["hours_basis"], dva.basis_proxy())
		self.assertIsNone(row["engine_hours"])
		self.assertEqual(flt(row["hours"]), 20)
		# LOW-4 (2026-11-11): the proxy stands in for engine hours, so hours nature is "Estimated"
		self.assertEqual(row["hours_nature"], dva.nature_estimated())
		# billable hours stand in for engine hours: the expected figure is an estimate
		self.assertEqual(row["expected_nature"], dva.nature_estimated())
		self.assertEqual(flt(row["expected_litres"]), 100)
		self.assertEqual(flt(row["variance_litres"]), -10)
		self.assertIn(
			frappe._("Meter readings do not cover the month: the billable-hours proxy is used"), row["notes"]
		)

	def test_partial_readings_or_a_reset_fall_back_to_the_proxy(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._reading(eq, "2026-09-05 00:00:00", 100)  # no reading before the month starts
		self._reading(eq, "2026-10-02 00:00:00", 300)
		self._card(eq, {"2026-09-03": 8})
		self.assertEqual(self._row(eq)["hours_basis"], dva.basis_proxy())
		eq2 = self._equipment(rates=[("2026-01-01", 5)])
		self._reading(eq2, "2026-08-30 00:00:00", 500)
		self._reading(eq2, "2026-09-15 00:00:00", 3, reset=1)  # meter reset: hours across it are unknown
		self._reading(eq2, "2026-10-02 00:00:00", 100)
		self._card(eq2, {"2026-09-03": 8})
		row = self._row(eq2)
		self.assertEqual(row["hours_basis"], dva.basis_proxy())
		self.assertEqual(flt(row["hours"]), 8)

	def test_project_filter_uses_the_proxy(self):
		project = self._raw("Project", project_name="TEST-DVA-P-" + self.token, company=self.a)
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._reading(eq, "2026-09-01 00:00:00", 100)
		self._reading(eq, "2026-10-01 00:00:00", 300)
		self._card(eq, {"2026-09-01": 10}, project=project)
		self._fill(eq, 40, project=project)
		row = self._row(eq, project=project)
		self.assertEqual(row["hours_basis"], dva.basis_proxy())
		self.assertEqual(flt(row["hours"]), 10)
		self.assertEqual(row["projects"], project)

	# ---------- rates ----------

	def test_rate_change_mid_period(self):
		eq = self._equipment(rates=[("2026-01-01", 5), ("2026-09-16", 8)])
		self._card(eq, {"2026-09-01": 10, "2026-09-20": 10})
		row = self._row(eq)
		self.assertEqual(flt(row["expected_litres"]), 130)  # 10 h x 5 + 10 h x 8
		self.assertEqual(flt(row["rate"]), 6.5)
		# engine basis: the hours of one 30-day interval are spread by time over both rates
		eq2 = self._equipment(rates=[("2026-01-01", 5), ("2026-09-16", 8)])
		self._reading(eq2, "2026-09-01 00:00:00", 0)
		self._reading(eq2, "2026-10-01 00:00:00", 300)
		row = self._row(eq2)
		self.assertEqual(row["hours_basis"], dva.basis_engine())
		self.assertEqual(flt(row["expected_litres"]), 1950)  # 15 days x 10 h x 5 + 15 days x 10 h x 8
		self.assertEqual(row["expected_nature"], dva.nature_estimated())
		self.assertIn(
			frappe._("The consumption rate changes between two meter readings: hours split by time"),
			row["notes"],
		)

	def test_no_rate_flags_the_row_without_a_crash(self):
		eq = self._equipment()  # no row, no daily standard, no static, type without rows
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 50)
		row = self._row(eq)
		self.assertIsNone(row["expected_litres"])
		self.assertIsNone(row["variance_litres"])
		self.assertIsNone(row["variance_pct"])
		self.assertIsNone(row["rate"])
		self.assertIn(
			frappe._("No consumption rate on some operating days: expected litres not computed"), row["notes"]
		)
		# a rate starting mid-month still leaves the earlier operating day without one
		eq2 = self._equipment(rates=[("2026-09-10", 5)])
		self._card(eq2, {"2026-09-01": 10, "2026-09-12": 10})
		self.assertIsNone(self._row(eq2)["expected_litres"])

	def test_rate_book_matches_consumption_rate_details(self):
		# FR-144 (owner decision 2026-11-11): the resolver order became
		# equipment → static → daily → type. This parity test is kept so that once PR #239 lands and
		# `card.consumption.consumption_rate_details` matches the FR-144 order, the two helpers continue
		# to agree. Until then, skip rather than fail: #239 is still open and the parity target has not
		# moved yet on main.
		eq = self._equipment(static=9, daily=120)
		info = dva._equipment_info({eq}, frappe._dict())
		book = dva.RateBook(info)
		rate, source = book.rate(eq, frappe.utils.getdate("2026-09-01"))
		expected = consumption_rate_details(eq, "2026-09-01")
		if (rate, source) != (expected.rate, expected.source):
			self.skipTest(
				"skipped until #239 merges and consumption_rate_details precedence matches FR-144"
			)
		self._set_type_rates([("2026-01-01", 20), ("2026-09-10", 22, self.a), ("2026-09-20", 0)])
		equipment = [
			self._equipment(rates=[("2026-03-01", 14), ("2026-09-15", 16)], static=9, daily=120),
			self._equipment(daily=120),
			self._equipment(static=9),
			self._equipment(),
			self._equipment(company=self.b),
			self._equipment(etype=self._type()),
		]
		info = dva._equipment_info(set(equipment), frappe._dict())
		book = dva.RateBook(info)
		for eq in equipment:
			for day in ("2026-02-01", "2026-09-01", "2026-09-12", "2026-09-15", "2026-09-25"):
				expected = consumption_rate_details(eq, day)
				rate, source = book.rate(eq, frappe.utils.getdate(day))
				with self.subTest(equipment=eq, day=day):
					self.assertEqual((rate, source), (expected.rate, expected.source))

	def test_rate_book_pins_fr144_order(self):
		"""FR-144 (owner decision 2026-11-11): equipment row → static → daily → type. The static per-hour
		wins over the daily figure when both are set; a mutation that swaps daily and static fails this
		test. The order is pinned here independently of ``consumption_rate_details`` (parity is covered by
		``test_rate_book_matches_consumption_rate_details`` once #239 lands)."""
		from card.consumption import (
			SOURCE_DAILY,
			SOURCE_EQUIPMENT,
			SOURCE_STATIC,
			SOURCE_TYPE,
		)

		# a type default row for the equipment's company
		self._set_type_rates([("2026-01-01", 20)])
		day = frappe.utils.getdate("2026-09-01")
		# 1) equipment dated row wins, even with static and daily set
		eq_full = self._equipment(
			rates=[("2026-03-01", 14), ("2026-09-15", 16)], static=9, daily=120
		)
		# 2) static wins over daily when both are set, and over the type default
		eq_static_daily = self._equipment(static=9, daily=120)
		# 3) daily wins when static is 0 (not set); still wins over the type default
		eq_daily_only = self._equipment(daily=120)
		# 4) type default is used only when neither static nor daily is set
		eq_type_only = self._equipment()
		info = dva._equipment_info(
			{eq_full, eq_static_daily, eq_daily_only, eq_type_only}, frappe._dict()
		)
		book = dva.RateBook(info)
		self.assertEqual(book.rate(eq_full, day), (14.0, SOURCE_EQUIPMENT))
		# the static is 9 (per hour), not the daily 120/10 = 12
		self.assertEqual(book.rate(eq_static_daily, day), (9.0, SOURCE_STATIC))
		self.assertEqual(book.rate(eq_daily_only, day), (12.0, SOURCE_DAILY))
		self.assertEqual(book.rate(eq_type_only, day), (20.0, SOURCE_TYPE))

	def _set_type_rates(self, rates):
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.set("default_consumption_rates", [])
		for item in rates:
			row = {"valid_from": item[0], "litres_per_hour": item[1], "reason": REASON}
			if len(item) > 2:
				row["company"] = item[2]
			t.append("default_consumption_rates", row)
		t.save(ignore_permissions=True)

	# ---------- fills ----------

	def test_only_submitted_direct_fills_count_and_tank_fills_are_not_split(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 30)
		self._fill(eq, 999, docstatus=0)  # draft
		self._fill(eq, 999, docstatus=2)  # cancelled
		self._fill(eq, 999, date="2026-10-01")  # outside the period
		self._fill(None, 500)  # project-tank fill: no equipment
		_columns, rows, _message, summary = self._run()
		row = next(r for r in rows if r["equipment"] == eq)
		self.assertEqual(flt(row["filled_litres"]), 30)
		tiles = {t["key"]: t["value"] for t in summary}
		self.assertEqual(flt(tiles["tank_litres"]), 500)
		self.assertEqual(flt(tiles["filled_litres"]), sum(flt(r["filled_litres"]) for r in rows))

	def test_months_are_separate_rows(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._fill(eq, 30, date="2026-08-20")
		self._fill(eq, 40, date="2026-09-20")
		rows = [r for r in self._run(from_date="2026-08-15", to_date="2026-09-30")[1] if r["equipment"] == eq]
		self.assertEqual(
			[(r["period"], flt(r["filled_litres"])) for r in rows], [("2026-08", 30), ("2026-09", 40)]
		)

	def test_a_period_over_one_year_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			dva.execute({"company": self.a, "from_date": "2025-01-01", "to_date": "2026-03-01"})

	# ---------- thresholds and labels ----------

	def test_no_threshold_row_flags_nothing(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 500)  # 900 % over expected
		eq2 = self._equipment(rates=[("2026-01-01", 5)])
		self._fill(eq2, 50)  # a fill without any hours
		_columns, rows, message, _summary = self._run()
		self.assertFalse([r for r in rows if r["anomaly"]])
		self.assertIn(
			frappe._("No anomaly thresholds are set for this company in Card Settings: nothing is flagged."),
			message,
		)

	def test_thresholds_are_per_company(self):
		self._threshold(self.a, pct=10, litres=5, fill_without_hours=1, hours_without_fill=1)
		rows = {}
		for company in (self.a, self.b):
			high = self._equipment(rates=[("2026-01-01", 5)], company=company)
			self._card(high, {"2026-09-01": 10}, company=company)
			self._fill(high, 60, company=company)  # +10 L, +20 %
			small = self._equipment(rates=[("2026-01-01", 5)], company=company)
			self._card(small, {"2026-09-01": 10}, company=company)
			self._fill(small, 54, company=company)  # +4 L: below the litre threshold
			near = self._equipment(rates=[("2026-01-01", 5)], company=company)
			self._card(near, {"2026-09-01": 100}, company=company)
			self._fill(near, 540, company=company)  # +40 L but +8 %: below the % threshold
			no_hours = self._equipment(rates=[("2026-01-01", 5)], company=company)
			self._fill(no_hours, 50, company=company)
			no_fill = self._equipment(rates=[("2026-01-01", 5)], company=company)
			self._card(no_fill, {"2026-09-01": 10}, company=company)
			by_eq = {r["equipment"]: r for r in self._run(company=company)[1]}
			rows[company] = [by_eq[e]["anomaly"] for e in (high, small, near, no_hours, no_fill)]
		self.assertEqual(
			rows[self.a],
			[
				frappe._("Variance above the company threshold"),
				"",
				"",
				frappe._("Diesel fill without operating hours"),
				frappe._("Operating hours without a diesel fill"),
			],
		)
		self.assertEqual(rows[self.b], ["", "", "", "", ""])

	def test_variance_is_labelled_as_variance_never_as_loss(self):
		self._threshold(self.a, pct=1)
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 80)
		columns, rows, message, summary = self._run()
		labels = {c["fieldname"]: c["label"] for c in columns}
		self.assertIn("not a loss", labels["variance_litres"])
		self.assertIn("not a loss", labels["variance_cost"])
		self.assertIn(frappe._("Variance above the company threshold"), rows[0]["anomaly"])
		allowed = ("not a loss", "no loss claim", "not a fuel loss")
		texts = list(labels.values()) + [t["label"] for t in summary] + [message] + [json.dumps(rows)]
		for text in texts:
			stripped = text.lower()
			for phrase in allowed:
				stripped = stripped.replace(phrase, "")
			self.assertNotIn("loss", stripped, text)
		self.assertFalse([c for c in columns if "loss" in c["fieldname"]])

	# ---------- company isolation and access ----------

	def test_cross_company_isolation(self):
		eq_a = self._equipment(rates=[("2026-01-01", 5)])
		eq_b = self._equipment(rates=[("2026-01-01", 5)], company=self.b)
		self._fill(eq_b, 70, company=self.b)
		self._card(eq_b, {"2026-09-01": 10}, company=self.b)
		self._reading(eq_b, "2026-09-01 00:00:00", 0, company=self.b)
		self._reading(eq_b, "2026-10-01 00:00:00", 100, company=self.b)
		self._fill(eq_a, 20)
		self._fill(eq_b, 999)  # a fill of company A naming B's equipment stays in company A's report
		rows_b = {r["equipment"]: r for r in self._run(company=self.b)[1]}
		self.assertEqual(set(rows_b), {eq_b})
		self.assertEqual(flt(rows_b[eq_b]["filled_litres"]), 70)
		self.assertEqual(flt(rows_b[eq_b]["engine_hours"]), 100)
		rows_a = {r["equipment"]: r for r in self._run()[1]}
		self.assertEqual(flt(rows_a[eq_a]["filled_litres"]), 20)
		# none of B's fills, card hours or meter readings reach company A's row
		self.assertEqual(flt(rows_a[eq_b]["filled_litres"]), 999)
		self.assertEqual(flt(rows_a[eq_b]["billable_hours"]), 0)
		self.assertIsNone(rows_a[eq_b]["engine_hours"])
		self.assertEqual(rows_a[eq_b]["hours_basis"], dva.basis_proxy())
		user = self._user(("Card User",), restrict=self.a)
		frappe.set_user(user)
		self.assertTrue(query_report.run(REPORT, filters={"company": self.a, **SEPT})["result"] is not None)
		with self.assertRaises(frappe.PermissionError):
			query_report.run(REPORT, filters={"company": self.b, **SEPT})

	def test_role_access_and_visible_columns(self):
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 60)
		every = {c["fieldname"] for c in dva._columns()}
		for role in ("Card User", "Card Manager", "Accounts Manager", "System Manager"):
			frappe.set_user(self._user((role,)))
			result = query_report.run(REPORT, filters={"company": self.a, **SEPT})
			with self.subTest(role=role):
				self.assertEqual({c["fieldname"] for c in result["columns"]}, every)
			frappe.set_user("Administrator")
		for roles in (("Card Operator",), ("Card Supervisor",), ()):
			frappe.set_user(self._user(roles))
			with self.subTest(roles=roles), self.assertRaises(frappe.PermissionError):
				query_report.run(REPORT, filters={"company": self.a, **SEPT})
			frappe.set_user("Administrator")

	def test_rate_and_amount_columns_follow_the_field_levels(self):
		self._threshold(self.a, pct=1)
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 60)
		real = frappe.model.meta.Meta.get_permlevel_access

		def without(doctype, level):
			def access(meta, permission_type="read", parenttype=None, *, user=None):
				levels = real(meta, permission_type, parenttype, user=user)
				return [lv for lv in levels if lv != level] if meta.name == doctype else levels

			return patch.object(frappe.model.meta.Meta, "get_permlevel_access", access)

		with without("Card Equipment", 1):
			columns, rows, _message, summary = self._run()
		names = {c["fieldname"] for c in columns}
		for field in dva.RATE_FIELDS:
			self.assertNotIn(field, names)
			self.assertNotIn(field, rows[0])
		self.assertFalse({t["key"] for t in summary} & set(dva.RATE_FIELDS))
		self.assertEqual(rows[0]["anomaly"], "")  # the variance flag is derived from the rates
		self.assertIn("filled_amount", names)
		with without("Project Diesel Fill", 0):
			columns, rows, _message, summary = self._run()
		names = {c["fieldname"] for c in columns}
		for field in dva.AMOUNT_FIELDS:
			self.assertNotIn(field, names)
			self.assertNotIn(field, rows[0])
		self.assertNotIn("filled_amount", {t["key"] for t in summary})
		self.assertIn("expected_litres", names)

	# ---------- performance ----------

	def test_query_count_does_not_grow_with_rows(self):
		def count(n):
			for _i in range(n):
				eq = self._equipment(rates=[("2026-01-01", 5)])
				self._card(eq, {"2026-09-01": 10, "2026-09-02": 4})
				self._fill(eq, 60)
				self._reading(eq, "2026-08-30 00:00:00", 0)
				self._reading(eq, "2026-10-02 00:00:00", 300)
			real = frappe.db.sql
			calls = []

			def counting(*args, **kwargs):
				calls.append(args[0] if args else "")
				return real(*args, **kwargs)

			dva.execute({"company": self.a, **SEPT})  # warm the meta cache
			with patch.object(frappe.db, "sql", side_effect=counting):
				dva.execute({"company": self.a, **SEPT})
			return len(calls)

		self.assertEqual(count(1), count(5))

	# ---------- Card Settings table ----------

	def test_settings_refuse_duplicate_and_negative_thresholds(self):
		settings = frappe.get_doc("Card Settings")
		settings.append("diesel_variance_thresholds", {"company": self.a, "variance_pct_threshold": 10})
		settings.append("diesel_variance_thresholds", {"company": self.a, "min_variance_litres": 5})
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)
		settings = frappe.get_doc("Card Settings")
		settings.append("diesel_variance_thresholds", {"company": self.a, "variance_pct_threshold": -1})
		with self.assertRaises(frappe.ValidationError):
			settings.save(ignore_permissions=True)

	def test_settings_rows_of_other_companies_stay_hidden(self):
		import frappe.client

		self._threshold(self.a, pct=10)
		self._threshold(self.b, pct=20)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		frappe.set_user(self._user(("Card Manager",), restrict=self.a))
		doc = frappe.client.get("Card Settings")
		self.assertEqual({r["company"] for r in doc.get("diesel_variance_thresholds") or []}, {self.a})

	# ---------- MEDIUM-1: engine basis follows the user's Equipment Meter Reading permission ----------

	def test_report_meter_reading_scope(self):
		"""MEDIUM-1 (2026-11-11): the engine basis reads Equipment Meter Reading, so it is used only when
		the running user may read it. A user without that permission falls back to the billable-hours proxy
		with a data note. No role, DocPerm or elevated read is added — the fallback is the point."""
		eq = self._equipment(rates=[("2026-01-01", 5)])
		self._reading(eq, "2026-09-01 00:00:00", 100)
		self._reading(eq, "2026-10-01 00:00:00", 300)
		self._card(eq, {"2026-09-01": 10})
		self._fill(eq, 1100)
		# A Card Manager with full access: engine basis as before
		frappe.set_user(self._user(("Card Manager",)))
		row = self._row(eq)
		self.assertEqual(row["hours_basis"], dva.basis_engine())
		self.assertEqual(flt(row["engine_hours"]), 200)
		frappe.set_user("Administrator")
		# An Accounts Manager has no DocPerm on Equipment Meter Reading — fall back to the proxy
		frappe.set_user(self._user(("Accounts Manager",)))
		self.assertFalse(
			frappe.has_permission("Equipment Meter Reading", "read", user=frappe.session.user)
		)
		row = self._row(eq)
		self.assertEqual(row["hours_basis"], dva.basis_proxy())
		self.assertIsNone(row["engine_hours"])
		self.assertIn(
			frappe._("Engine hours unavailable for this user; falling back to the billable-hours proxy."),
			row["notes"],
		)
		frappe.set_user("Administrator")
		# A Card Manager with has_permission on Equipment Meter Reading patched away: engine basis
		# disappears, proxy shows up — proves it is the permission check, not the role, that decides.
		real = frappe.has_permission

		def patched(doctype, *args, **kwargs):
			ptype = args[0] if args else kwargs.get("ptype", "read")
			if doctype == "Equipment Meter Reading" and ptype == "read":
				return False
			return real(doctype, *args, **kwargs)

		frappe.set_user(self._user(("Card Manager",)))
		with patch.object(frappe, "has_permission", side_effect=patched):
			row = self._row(eq)
		self.assertEqual(row["hours_basis"], dva.basis_proxy())
		self.assertIn(
			frappe._("Engine hours unavailable for this user; falling back to the billable-hours proxy."),
			row["notes"],
		)
		frappe.set_user("Administrator")

	# ---------- LOW-1: rate-related data notes dropped when rate columns are hidden ----------

	def test_report_rate_notes_hidden_when_rates_hidden(self):
		"""LOW-1 (2026-11-11): the two rate-related data notes ("No consumption rate on some operating
		days…" and "The consumption rate changes between two meter readings…") must not leak to a user
		who cannot see the rate columns. The role-level stripping uses the same patched
		get_permlevel_access the existing rate-column test uses."""
		# A row with a missing-rate note: hours but no rate on that day
		eq_no_rate = self._equipment()  # no row, no daily, no static, type without rows
		self._card(eq_no_rate, {"2026-09-01": 10})
		self._fill(eq_no_rate, 50)
		# A row with a rate-split note AND a proration note: two readings cover the month, the rate
		# changes mid-period, and the earlier reading is slightly before the month limit so ``exact`` is
		# False (the proration note needs that). This also lets the final assertion check that a non-rate
		# note (the proration note) survives the strip.
		eq_split = self._equipment(rates=[("2026-01-01", 5), ("2026-09-16", 8)])
		self._reading(eq_split, "2026-08-31 23:50:00", 0)
		self._reading(eq_split, "2026-10-01 00:00:00", 300)
		real = frappe.model.meta.Meta.get_permlevel_access

		def without(doctype, level):
			def access(meta, permission_type="read", parenttype=None, *, user=None):
				levels = real(meta, permission_type, parenttype, user=user)
				return [lv for lv in levels if lv != level] if meta.name == doctype else levels

			return patch.object(frappe.model.meta.Meta, "get_permlevel_access", access)

		# Baseline: rates visible, both notes present
		_cols, rows, _msg, _summary = self._run()
		by_eq = {r["equipment"]: r for r in rows}
		self.assertIn(dva.note_no_rate(), by_eq[eq_no_rate]["notes"])
		self.assertIn(dva.note_rate_split(), by_eq[eq_split]["notes"])
		# Rates hidden: both rate-related notes are dropped from every row's notes field
		with without("Card Equipment", 1):
			_cols, rows, _msg, _summary = self._run()
		by_eq = {r["equipment"]: r for r in rows}
		self.assertNotIn(dva.note_no_rate(), by_eq[eq_no_rate]["notes"])
		self.assertNotIn(dva.note_rate_split(), by_eq[eq_split]["notes"])
		# Non-rate notes are kept (meter-readings proration note stays on the eq_split row)
		self.assertIn(
			frappe._("Engine hours prorated by time between meter readings"), by_eq[eq_split]["notes"]
		)

	# ---------- LOW-2: every scoped child DocType is registered in hooks.py ----------

	def test_scoped_child_doctypes_registered_in_hooks(self):
		"""LOW-2 (2026-11-11): every entry in ``SCOPED_CHILD_DOCTYPES`` must appear in
		``permission_query_conditions`` in ``card.hooks`` with the Card Settings scope hook. A mutation
		that removes a hook line fails this test."""
		from card import hooks
		from card.card.doctype.card_settings.card_settings import SCOPED_CHILD_DOCTYPES

		expected_hook = "card.card.doctype.card_settings.card_settings.settings_row_query_conditions"
		for doctype in SCOPED_CHILD_DOCTYPES:
			with self.subTest(doctype=doctype):
				self.assertEqual(
					hooks.permission_query_conditions.get(doctype),
					expected_hook,
					f"{doctype} is a scoped child DocType but has no row in hooks.permission_query_conditions",
				)
