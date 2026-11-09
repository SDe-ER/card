# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-122 (Owner 2026-11-10): every monthly card shows its value on the CARD dashboard, whether the equipment
is owned, rented or managed. Supplier cost, customer value and internal value are separate series; an internal
card without a rate still counts (missing-rate card and hours); company User Permissions and the level-2
internal rate are respected; drafts are left out unless the chart's filter asks for them."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card import card_value as cv
from card.card.dashboard_chart_source.card_monthly_values import card_monthly_values as source
from card.constants import DIR_INTERNAL, DIR_RENTED_IN, DIR_RENTED_OUT, DIR_SUBRENTAL, OWNED, THIRD_PARTY
from card.tests.test_customer import RENTED, _CustomerCardsBase

SEPT = ("2026-09-01", "2026-09-30")
CHART = "مبالغ الكروت الشهرية"


def _card(direction, ownership=OWNED, net=0, customer=0, hours=0, days=0):
	return frappe._dict(
		card_direction=direction,
		ownership=ownership,
		net_amount=net,
		customer_net_amount=customer,
		total_working_hours=hours,
		working_days=days,
	)


class TestCardValueMath(IntegrationTestCase):
	"""The value of one card in each direction (no database)."""

	def test_rented_from_supplier_is_cost(self):
		v = cv.card_value(_card(DIR_RENTED_IN, RENTED, net=9000, hours=100))
		self.assertEqual((v["supplier"], v["customer"], v["internal"]), (9000.0, 0.0, 0.0))
		self.assertFalse(v["missing_rate"])

	def test_rented_to_customer_is_billing_value(self):
		v = cv.card_value(_card(DIR_RENTED_OUT, net=0, customer=12125, hours=97))
		self.assertEqual((v["supplier"], v["customer"], v["internal"]), (0.0, 12125.0, 0.0))
		self.assertFalse(v["missing_rate"], "a card with a customer value is not missing a rate")

	def test_sub_rental_has_both_sides(self):
		v = cv.card_value(_card(DIR_SUBRENTAL, RENTED, net=7500, customer=12000, hours=100))
		self.assertEqual((v["supplier"], v["customer"]), (7500.0, 12000.0))

	def test_internal_per_hour_and_per_day(self):
		card = _card(DIR_INTERNAL, hours=120, days=12)
		hourly = frappe._dict(internal_rate=150, internal_rate_basis="بالساعة")
		daily = frappe._dict(internal_rate=1400, internal_rate_basis="باليوم")
		self.assertEqual(cv.card_value(card, hourly)["internal"], 18000.0)
		self.assertEqual(cv.card_value(card, daily)["internal"], 16800.0)

	def test_older_internal_hourly_rate_is_used_when_no_internal_rate(self):
		v = cv.card_value(_card(DIR_INTERNAL, hours=10), frappe._dict(internal_hourly_rate=90))
		self.assertEqual(v["internal"], 900.0)
		v = cv.card_value(
			_card(DIR_INTERNAL, hours=10), frappe._dict(internal_rate=100, internal_hourly_rate=90)
		)
		self.assertEqual(v["internal"], 1000.0, "internal_rate wins over internal_hourly_rate")

	def test_missing_internal_rate_still_counts_hours(self):
		for equipment in (None, frappe._dict(internal_rate=0, internal_hourly_rate=0)):
			v = cv.card_value(_card(DIR_INTERNAL, hours=55), equipment)
			self.assertEqual(v["internal"], 0.0)
			self.assertTrue(v["missing_rate"])
			self.assertEqual(v["hours"], 55.0)

	def test_owned_rented_out_with_rate_keeps_both_values_apart(self):
		v = cv.card_value(_card(DIR_RENTED_OUT, customer=56250, hours=225), frappe._dict(internal_rate=200))
		self.assertEqual((v["customer"], v["internal"]), (56250.0, 45000.0))
		self.assertFalse(v["missing_rate"])

	def test_managed_equipment_has_internal_value_rented_does_not(self):
		rate = frappe._dict(internal_rate=100)
		managed = cv.card_value(_card(DIR_RENTED_IN, THIRD_PARTY, net=500, hours=10), rate)
		self.assertEqual((managed["supplier"], managed["internal"]), (500.0, 1000.0))
		rented = cv.card_value(_card(DIR_RENTED_IN, RENTED, net=500, hours=10), rate)
		self.assertEqual(rented["internal"], 0.0, "a rented machine has no internal value")

	def test_legacy_card_without_direction_derives_it(self):
		v = cv.card_value(_card(None, OWNED, hours=8))
		self.assertTrue(v["missing_rate"], "owned without a direction is internal operation")
		v = cv.card_value(_card(None, RENTED, net=300))
		self.assertEqual(v["supplier"], 300.0)

	def test_without_access_to_the_rate_no_internal_value(self):
		v = cv.card_value(_card(DIR_INTERNAL, hours=10), frappe._dict(internal_rate=100), with_internal=False)
		self.assertIsNone(v["internal"])
		self.assertFalse(v["missing_rate"])

	def test_buckets_per_month(self):
		cards = [
			frappe._dict(from_date="2026-09-01", supplier=10.0, customer=0.0, internal=5.0),
			frappe._dict(from_date="2026-10-01", supplier=0.0, customer=12125.0, internal=0.0),
			frappe._dict(from_date="2026-10-01", supplier=0.0, customer=56250.0, internal=None),
		]
		labels, values = cv.bucket_by_period(cards, "2026-09-01", "2026-10-31")
		self.assertEqual(labels, ["Sep 2026", "Oct 2026"])
		self.assertEqual(values["supplier"], [10.0, 0.0])
		self.assertEqual(values["customer"], [0.0, 68375.0])
		self.assertEqual(values["internal"], [5.0, 0.0])

	def test_chart_and_cards_methods_accept_post_only(self):
		methods = frappe.allowed_http_methods_for_whitelisted_func
		for fn in (
			source.get,
			cv.supplier_cost_last_month,
			cv.customer_value_last_month,
			cv.internal_value_last_month,
			cv.cards_without_internal_rate_last_month,
			cv.hours_without_internal_rate_last_month,
		):
			self.assertEqual(methods[fn], ["POST"], fn.__name__)


class TestCardValueDashboard(_CustomerCardsBase):
	"""Cards stored in the database, read as the dashboard reads them."""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _values(self, names, **kw):
		cards, with_internal = cv.get_card_values(*SEPT, **kw)
		return {c.name: c for c in cards if c.name in names}, with_internal

	def _internal(self, **kw):
		return self._equipment(OWNED, direction=DIR_INTERNAL, **kw)

	def test_each_direction_from_stored_cards(self):
		rented_in = self._card(self._equipment(RENTED, direction=DIR_RENTED_IN), [10, 10], submit=True)
		rented_out = self._card(self._rented_out(internal_rate=40), [10], submit=True)
		internal = self._card(self._internal(internal_rate=60), [8, 7], submit=True)
		no_rate = self._card(self._internal(), [5], submit=True)
		rows, with_internal = self._values({rented_in.name, rented_out.name, internal.name, no_rate.name})
		self.assertTrue(with_internal)
		self.assertEqual(rows[rented_in.name].supplier, flt(rented_in.net_amount, 2))
		self.assertGreater(rows[rented_in.name].supplier, 0)
		self.assertEqual(rows[rented_out.name].customer, flt(rented_out.customer_net_amount, 2))
		self.assertEqual(rows[rented_out.name].internal, 400.0)  # 10 h x 40, its own series
		self.assertEqual(rows[internal.name].internal, 900.0)  # 15 h x 60
		self.assertTrue(rows[no_rate.name].missing_rate)
		self.assertEqual(rows[no_rate.name].hours, 5.0)

	def test_chart_month_is_never_empty_and_series_are_separate(self):
		chart = frappe.get_doc("Dashboard Chart", CHART)
		self.assertEqual((chart.chart_type, chart.source), ("Custom", "Card Monthly Values"))
		kw = {"from_date": SEPT[0], "to_date": SEPT[1], "timespan": "Select Date Range"}
		before = source.get(chart_name=CHART, filters={"company": self.company}, **kw)
		self._card(self._rented_out(internal_rate=40), [10], submit=True)
		after = source.get(chart_name=CHART, filters={"company": self.company}, **kw)
		self.assertEqual(after["labels"], ["Sep 2026"])
		names = [d["name"] for d in after["datasets"]]
		self.assertEqual(names, [cv.series_labels()[k] for k in cv.SERIES])
		delta = [
			round(a["values"][0] - b["values"][0], 2)
			for a, b in zip(after["datasets"], before["datasets"], strict=True)
		]
		self.assertEqual(delta[0], 0.0)  # no supplier
		self.assertGreater(delta[1], 0.0)  # customer value
		self.assertEqual(delta[2], 400.0)  # internal value, not added to the customer value

	def test_drafts_follow_the_filter(self):
		draft = self._card(self._internal(internal_rate=10), [3])
		rows, _w = self._values({draft.name})
		self.assertNotIn(draft.name, rows, "submitted cards only by default")
		rows, _w = self._values({draft.name}, include_drafts=True)
		self.assertEqual(rows[draft.name].internal, 30.0)

	def test_number_cards_for_last_month(self):
		internal = self._card(self._internal(internal_rate=50), [4], submit=True)
		no_rate = self._card(self._internal(), [6], submit=True)
		with patch.object(cv, "_last_month", return_value=SEPT):
			before = {
				"internal": cv.internal_value_last_month({"company": self.company})["value"],
				"cards": cv.cards_without_internal_rate_last_month({"company": self.company})["value"],
				"hours": cv.hours_without_internal_rate_last_month({"company": self.company})["value"],
			}
			rows, _w = self._values({internal.name, no_rate.name})
			self.assertEqual(rows[internal.name].internal, 200.0)
			self.assertGreaterEqual(before["internal"], 200.0)
			self.assertGreaterEqual(before["cards"], 1)
			self.assertGreaterEqual(before["hours"], 6.0)
			result = cv.supplier_cost_last_month("{}")
			self.assertEqual(result["fieldtype"], "Currency")
			self.assertEqual(result["route"], ["List", "Card Monthly Card"])

	def test_other_company_cards_are_not_counted(self):
		other = self._other_company()
		own = self._card(self._internal(internal_rate=10), [2], submit=True)
		foreign = self._foreign_card(other)
		frappe.set_user(self._user(["Card User"], restrict=self.company))
		rows, _w = self._values({own.name, foreign})
		self.assertIn(own.name, rows)
		self.assertNotIn(foreign, rows, "a card of another company never reaches the dashboard")
		rows, _w = self._values({own.name, foreign}, company=other)
		self.assertFalse(rows, "a company filter cannot widen the user's companies")

	def test_internal_rate_needs_level_2(self):
		card = self._card(self._internal(internal_rate=70), [3], submit=True)
		frappe.set_user(self._user(["Card User"]))
		rows, with_internal = self._values({card.name})
		self.assertFalse(with_internal)
		self.assertIsNone(rows[card.name].internal)
		chart = cv.chart_data(frappe._dict(timespan="Select Date Range"), {}, *SEPT)
		self.assertEqual(len(chart["datasets"]), 2, "no internal series without access to the rate")
		self.assertIsNone(cv.internal_value_last_month()["value"])
		self.assertIsNone(cv.cards_without_internal_rate_last_month()["value"])
		frappe.set_user(self._user(["Card Manager"]))
		rows, with_internal = self._values({card.name})
		self.assertTrue(with_internal)
		self.assertEqual(rows[card.name].internal, 210.0)

	def test_no_read_permission_on_cards_is_refused(self):
		frappe.set_user(self._user([]))
		with self.assertRaises(frappe.PermissionError):
			cv.get_card_values(*SEPT)

	# ---- helpers ----
	def _other_company(self):
		name = "TEST-CRDVAL-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "V" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _foreign_card(self, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-CRDVAL-PRJ-" + self.token
		proj.company = company
		proj.insert(ignore_permissions=True)
		eq = frappe.new_doc("Card Equipment")
		eq.update(
			{
				"company": company,
				"equipment_type": self._m["etype"],
				"equipment_name": "TEST-CRDVAL-EQ-" + self.token,
				"ownership": OWNED,
				"rate_type": "باليوم",
				"rate": 750,
				"daily_hours": 10,
				"internal_rate": 10,
			}
		)
		eq.insert(ignore_permissions=True)
		card = frappe.new_doc("Card Monthly Card")
		card.update(
			{"equipment": eq.name, "project": proj.name, "shift": "نهاري", "month": "09", "year": 2026}
		)
		card.append("days", {"operation_date": "2026-09-02", "day_status": "عمل", "working_hours": 4})
		card.insert(ignore_permissions=True)
		card.submit()
		return card.name

	def _user(self, roles, restrict=None):
		email = f"crdval-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Card Value",
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
