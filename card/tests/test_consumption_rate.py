# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-144 (#31, #42, #47): effective-dated consumption rates (litres per operating hour).

consumption_rate(equipment, on_date) = the equipment's row valid on the date, else daily_diesel_consumption /
daily_hours (the Equipment Diesel Analysis basis), else the static expected_consumption, else the type row of the
equipment's company, else the type row with no company, else None. The seed patch gives each equipment with only a
static value one row from 2000-01-01, so every date keeps today's value; a second run adds nothing. Equipment rows are
level-1 data on every read path; type rows are changed by Card Manager / System Manager only, within the user's
companies. Rows dated before today are final. Everything is created per test and rolled back."""

import json

import frappe
from frappe.client import get as rest_get
from frappe.client import get_list as rest_get_list
from frappe.client import get_value as rest_get_value
from frappe.desk import reportview
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, flt, getdate

from card.consumption import (
	SOURCE_DAILY,
	SOURCE_EQUIPMENT,
	SOURCE_STATIC,
	SOURCE_TYPE,
	consumption_rate,
	consumption_rate_details,
)
from card.field_privacy import MASKED, mask_restricted_version
from card.patches.v4_8_0 import seed_consumption_rates
from card.tests.test_controllers import _ensure_masters

REFUSED = (frappe.PermissionError, frappe.ValidationError)
REASON = "test rate"


def _rows(rates):
	"""(valid_from, rate[, company]) tuples -> row dicts with a reason (past rows need one)."""
	out = []
	for item in rates:
		row = {"valid_from": item[0], "litres_per_hour": item[1], "reason": REASON}
		if len(item) > 2:
			row["company"] = item[2]
		out.append(row)
	return out


def _report_expected(hours, daily, daily_hours, per_hour):
	"""Equipment Diesel Analysis (FR-033) expected litres, as equipment_diesel_analysis.py computes them."""
	if flt(daily) and flt(daily_hours) > 0:
		return flt(hours * flt(daily) / flt(daily_hours), 3)
	if flt(per_hour):
		return flt(hours * flt(per_hour), 3)
	return None


class TestConsumptionRate(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._type()

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures ----------

	def _type(self, rates=()):
		t = frappe.new_doc("Card Equipment Type")
		t.equipment_type_name = "TEST-CRATE-T-" + frappe.generate_hash(length=6)
		t.equipment_category = frappe.db.get_value(
			"Card Equipment Type", self._m["etype"], "equipment_category"
		)
		for row in _rows(rates):
			t.append("default_consumption_rates", row)
		t.insert(ignore_permissions=True)
		return t.name

	def _equipment(self, static=None, rates=(), company=None, etype=None, daily=None, daily_hours=10):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company or self.company
		eq.equipment_type = etype or self.etype
		eq.equipment_name = "TEST-CRATE-EQ-" + frappe.generate_hash(length=6)
		eq.ownership = "ملك"
		eq.rate_type = "باليوم" if daily_hours else "بالساعة"
		eq.rate = 750
		eq.daily_hours = daily_hours
		if static is not None:
			eq.expected_consumption = static
		if daily is not None:
			eq.daily_diesel_consumption = daily
		for row in _rows(rates):
			eq.append("consumption_rates", row)
		eq.insert(ignore_permissions=True)
		return eq

	def _set_type_rates(self, rates, etype=None):
		t = frappe.get_doc("Card Equipment Type", etype or self.etype)
		t.set("default_consumption_rates", [])
		for row in _rows(rates):
			t.append("default_consumption_rates", row)
		t.save(ignore_permissions=True)
		return t

	def _other_company(self):
		name = "TEST-CRATE-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "R" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _user(self, roles, restrict=None):
		email = f"crate-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Consumption Rate",
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

	def _refused(self, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
		except REFUSED:
			return True
		finally:
			frappe.clear_messages()
		return False

	def _row_name(self, eq):
		return frappe.db.get_value(
			"Card Consumption Rate",
			{"parent": eq, "parenttype": "Card Equipment", "parentfield": "consumption_rates"},
		)

	# ---------- resolution ----------

	def test_order_equipment_row_daily_static_type(self):
		self._set_type_rates([("2026-01-01", 20)])
		eq = self._equipment(static=9, daily=120, rates=[("2026-03-01", 14)])
		self.assertEqual(consumption_rate_details(eq.name, "2026-03-15").source, SOURCE_EQUIPMENT)
		self.assertEqual(consumption_rate(eq.name, "2026-03-15"), 14)
		# before the equipment row: daily standard (120 L / 10 h), not the static value or the type row
		details = consumption_rate_details(eq.name, "2026-02-01")
		self.assertEqual((details.rate, details.source, details.valid_from), (12, SOURCE_DAILY, None))
		# no daily basis: the static value comes before the type row
		eq2 = self._equipment(static=9)
		self.assertEqual(consumption_rate_details(eq2.name, "2026-02-01").source, SOURCE_STATIC)
		self.assertEqual(consumption_rate(eq2.name, "2026-02-01"), 9)
		# nothing on the equipment: the type row
		eq3 = self._equipment()
		details = consumption_rate_details(eq3.name, "2026-02-01")
		self.assertEqual((details.rate, details.source), (20, SOURCE_TYPE))
		self.assertEqual(getdate(details.valid_from), getdate("2026-01-01"))

	def test_type_zero_row_never_hides_static(self):
		self._set_type_rates([("2026-01-01", 0)])
		eq = self._equipment(static=9)
		self.assertEqual(consumption_rate(eq.name, "2026-03-01"), 9)
		bare = self._equipment()
		details = consumption_rate_details(bare.name, "2026-03-01")
		self.assertEqual((details.rate, details.source), (0, SOURCE_TYPE))

	def test_daily_basis_needs_both_fields(self):
		eq = self._equipment(static=9, daily=150, daily_hours=0)
		self.assertEqual(consumption_rate_details(eq.name, "2026-03-01").source, SOURCE_STATIC)
		eq2 = self._equipment(daily=150, daily_hours=12)
		self.assertEqual(consumption_rate(eq2.name, "2026-03-01"), 12.5)

	def test_parity_with_diesel_analysis_formula(self):
		cases = [
			(None, 10, None),
			(None, 10, 9),
			(120, 10, None),
			(120, 10, 9),
			(100, 3, 7.5),
			(150, 0, 9),
			(0, 10, 0),
		]
		for daily, daily_hours, static in cases:
			eq = self._equipment(static=static, daily=daily, daily_hours=daily_hours)
			for hours in (0.5, 7, 233.25):
				rate = consumption_rate(eq.name, "2026-03-01")
				expected = _report_expected(hours, daily, daily_hours, static)
				got = None if rate is None else flt(hours * rate, 3)
				self.assertEqual(got, expected, (daily, daily_hours, static, hours))

	def test_type_rows_per_company(self):
		other = self._other_company()
		self._set_type_rates([("2026-01-01", 20), ("2026-01-01", 30, self.company)])
		eq_a = self._equipment()
		eq_b = self._equipment(company=other)
		self.assertEqual(consumption_rate(eq_a.name, "2026-02-01"), 30)
		# company B ignores company A's row and uses the row with no company
		self.assertEqual(consumption_rate(eq_b.name, "2026-02-01"), 20)
		# a company row that starts later: before it, the row with no company
		later = self._type(rates=[("2026-01-01", 20), ("2026-06-01", 30, self.company)])
		eq_c = self._equipment(etype=later)
		self.assertEqual(consumption_rate(eq_c.name, "2026-02-01"), 20)
		self.assertEqual(consumption_rate(eq_c.name, "2026-06-01"), 30)
		# the same date for two companies is not a duplicate; for one company it is
		self._type(rates=[("2026-01-01", 20, self.company), ("2026-01-01", 21, other)])
		with self.assertRaises(frappe.ValidationError):
			self._type(rates=[("2026-01-01", 20, self.company), ("2026-01-01", 21, self.company)])

	def test_date_boundaries(self):
		eq = self._equipment(rates=[("2026-06-01", 12), ("2026-01-01", 10)])  # rows out of order
		self.assertIsNone(consumption_rate(eq.name, "2025-12-31"))
		self.assertEqual(consumption_rate(eq.name, "2026-01-01"), 10)  # valid_from is inclusive
		self.assertEqual(consumption_rate(eq.name, "2026-05-31"), 10)
		self.assertEqual(consumption_rate(eq.name, "2026-06-01"), 12)
		self.assertEqual(consumption_rate(eq.name, "2030-01-01"), 12)  # no end date
		today = getdate()
		eq2 = self._equipment(rates=[(add_days(today, 1), 30), (add_days(today, -1), 25)])
		self.assertEqual(consumption_rate(eq2.name), 25)  # empty date = today

	def test_no_rate(self):
		eq = self._equipment()
		self.assertIsNone(consumption_rate(eq.name, "2026-03-01"))
		self.assertIsNone(consumption_rate_details(eq.name).source)
		eq0 = self._equipment(static=0)
		self.assertIsNone(consumption_rate(eq0.name, "2026-03-01"))
		self.assertIsNone(consumption_rate(None))
		self.assertIsNone(consumption_rate("TEST-CRATE-MISSING-" + self.token))

	def test_explicit_zero_row_is_a_rate(self):
		eq = self._equipment(static=9, rates=[("2026-01-01", 0)])
		details = consumption_rate_details(eq.name, "2026-02-01")
		self.assertEqual((details.rate, details.source), (0, SOURCE_EQUIPMENT))

	# ---------- validation ----------

	def test_duplicate_and_negative_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(rates=[("2026-01-01", 10), ("2026-01-01", 11)])
		with self.assertRaises(frappe.ValidationError):
			self._set_type_rates([("2026-01-01", 10), ("2026-01-01", 11)])
		with self.assertRaises(frappe.ValidationError):
			self._equipment(rates=[("2026-01-01", -1)])
		self._set_type_rates([("2026-01-01", 10)])
		self._equipment(rates=[("2026-01-01", 11)])  # type and equipment are different tables

	def test_past_rows_are_final(self):
		today = getdate()
		eq = self._equipment(rates=[("2026-01-01", 10), (add_days(today, 30), 12)])
		eq.reload()
		past = next(r for r in eq.consumption_rates if getdate(r.valid_from) < today)
		past.litres_per_hour = 11
		self.assertTrue(self._refused(eq.save, ignore_permissions=True))
		eq.reload()
		next(r for r in eq.consumption_rates if getdate(r.valid_from) < today).valid_from = "2026-01-02"
		self.assertTrue(self._refused(eq.save, ignore_permissions=True))
		eq.reload()
		eq.set("consumption_rates", [r for r in eq.consumption_rates if getdate(r.valid_from) >= today])
		self.assertTrue(self._refused(eq.save, ignore_permissions=True))
		# a future row may still change or go
		eq.reload()
		future = next(r for r in eq.consumption_rates if getdate(r.valid_from) >= today)
		future.litres_per_hour = 13
		eq.save(ignore_permissions=True)
		# a correction is a new row; backdated it needs a reason
		eq.reload()
		eq.append("consumption_rates", {"valid_from": "2026-02-01", "litres_per_hour": 11})
		self.assertTrue(self._refused(eq.save, ignore_permissions=True))
		eq.reload()
		eq.append(
			"consumption_rates", {"valid_from": "2026-02-01", "litres_per_hour": 11, "reason": "meter check"}
		)
		eq.save(ignore_permissions=True)
		self.assertEqual(consumption_rate(eq.name, "2026-02-15"), 11)
		self.assertEqual(consumption_rate(eq.name, "2026-01-15"), 10)
		# the same rules on the type
		t = self._set_type_rates([("2026-01-01", 20)])
		t.reload()
		t.default_consumption_rates[0].litres_per_hour = 21
		self.assertTrue(self._refused(t.save, ignore_permissions=True))

	def test_static_field_kept_and_rows_win(self):
		eq = self._equipment(static=9, rates=[("2026-01-01", 11)])
		eq.reload()
		eq.expected_consumption = 7
		eq.save(ignore_permissions=True)
		frappe.clear_messages()
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "expected_consumption"), 7)
		self.assertEqual(consumption_rate(eq.name, "2026-02-01"), 11)
		self.assertEqual(consumption_rate(eq.name, "2025-12-31"), 7)
		meta = frappe.get_meta("Card Equipment")
		self.assertEqual(
			meta.get_field("consumption_rates").permlevel, meta.get_field("expected_consumption").permlevel
		)
		row_meta = frappe.get_meta("Card Consumption Rate")
		self.assertTrue(all(df.permlevel == 1 for df in row_meta.fields))
		self.assertTrue(all(df.permlevel == 0 for df in frappe.get_meta("Card Type Consumption Rate").fields))

	# ---------- seed patch ----------

	def _parity_dates(self, eq):
		created = getdate(frappe.db.get_value("Card Equipment", eq, "creation"))
		return [
			"1999-12-31",
			"2000-01-01",
			add_days(created, -400),
			created,
			add_days(created, 1),
			"2040-01-01",
		]

	def _seed_rows(self, name):
		return frappe.get_all(
			"Card Consumption Rate",
			filters={"parent": name, "parenttype": "Card Equipment", "parentfield": "consumption_rates"},
			fields=["valid_from", "litres_per_hour", "reason"],
		)

	def test_seed_patch_parity_and_idempotent(self):
		self._set_type_rates([("2026-01-01", 20)])
		with_static = self._equipment(static=9.5)
		without = self._equipment()
		zero = self._equipment(static=0)
		daily = self._equipment(static=9, daily=150)
		already = self._equipment(static=4, rates=[("2026-01-01", 6)])
		subjects = (with_static, without, zero, daily, already)

		def snapshot():
			return {
				eq.name: [consumption_rate(eq.name, d) for d in self._parity_dates(eq.name)]
				for eq in subjects
			}

		before = snapshot()
		modified = frappe.db.get_value("Card Equipment", with_static.name, "modified")
		seed_consumption_rates.execute()
		self.assertEqual(snapshot(), before)

		seeded = self._seed_rows(with_static.name)
		self.assertEqual(len(seeded), 1)
		self.assertEqual(seeded[0].litres_per_hour, 9.5)
		self.assertEqual(getdate(seeded[0].valid_from), getdate("2000-01-01"))
		self.assertTrue(seeded[0].reason)
		self.assertEqual(consumption_rate_details(with_static.name, "2040-01-01").source, SOURCE_EQUIPMENT)
		self.assertEqual(frappe.db.get_value("Card Equipment", with_static.name, "modified"), modified)
		self.assertEqual(frappe.db.get_value("Card Equipment", with_static.name, "expected_consumption"), 9.5)
		self.assertEqual(self._seed_rows(without.name), [])
		self.assertEqual(self._seed_rows(zero.name), [])
		self.assertEqual(self._seed_rows(daily.name), [])  # daily standard basis kept (report parity)
		self.assertEqual(len(self._seed_rows(already.name)), 1)

		seed_consumption_rates.execute()  # second migrate
		self.assertEqual(len(self._seed_rows(with_static.name)), 1)
		self.assertEqual(snapshot(), before)
		doc = frappe.get_doc("Card Equipment", with_static.name)
		doc.save(ignore_permissions=True)  # the seeded row passes validation

	# ---------- permissions and isolation ----------

	def test_company_isolation_by_rest(self):
		other = self._other_company()
		eq_a = self._equipment(rates=[("2026-01-01", 10)])
		eq_b = self._equipment(rates=[("2026-01-01", 20)], company=other)
		row_a, row_b = self._row_name(eq_a.name), self._row_name(eq_b.name)
		frappe.set_user(self._user(["Card Manager"], restrict=self.company))
		self.assertEqual(rest_get("Card Consumption Rate", row_a)["litres_per_hour"], 10)
		self.assertEqual(rest_get("Card Equipment", eq_a.name)["consumption_rates"][0]["litres_per_hour"], 10)
		self.assertTrue(self._refused(rest_get, "Card Consumption Rate", row_b))
		self.assertTrue(self._refused(rest_get, "Card Equipment", eq_b.name))
		listed = rest_get_list(
			"Card Consumption Rate",
			fields=["name", "parent", "litres_per_hour"],
			filters={"parenttype": "Card Equipment"},
			parent="Card Equipment",
			limit_page_length=0,
		)
		names = {r["name"] for r in listed}
		self.assertIn(row_a, names)
		self.assertNotIn(row_b, names)

	def _leaks(self, value, fn, *args, **kwargs):
		"""True when `fn` returns `value` anywhere in its result (a refusal is no leak)."""
		try:
			result = fn(*args, **kwargs)
		except REFUSED:
			return False
		finally:
			frappe.clear_messages()
		return str(value) in json.dumps(result, default=str)

	def test_level_zero_reader_sees_no_rate(self):
		# Card Supervisor reads Card Equipment at level 0 only (as for the static field); 37.25 is unique
		eq = self._equipment(static=9, rates=[("2026-01-01", 37.25)])
		row = self._row_name(eq.name)
		frappe.set_user(self._user(["Card Supervisor"]))
		doc = rest_get("Card Equipment", eq.name)
		self.assertFalse(doc.get("consumption_rates"))
		self.assertFalse(doc.get("expected_consumption"))
		self.assertTrue(self._refused(rest_get, "Card Consumption Rate", row))
		self.assertFalse(
			self._leaks(
				37.25,
				rest_get_list,
				"Card Consumption Rate",
				fields=["parent", "litres_per_hour"],
				filters={"parent": eq.name},
				parent="Card Equipment",
				limit_page_length=0,
			)
		)
		self.assertFalse(
			self._leaks(
				37.25,
				rest_get_value,
				"Card Consumption Rate",
				"litres_per_hour",
				{"parent": eq.name},
				parent="Card Equipment",
			)
		)
		self.assertFalse(
			self._leaks(
				37.25,
				reportview.execute,
				"Card Equipment",
				fields=["name", "`tabCard Consumption Rate`.`litres_per_hour`"],
				filters=[["name", "=", eq.name]],
			)
		)
		self.assertFalse(
			self._leaks(
				37.25,
				frappe.get_list,
				"Card Equipment",
				fields=["name", "consumption_rates.litres_per_hour"],
				filters={"name": eq.name},
			)
		)

		# a filter on the rate is no oracle: the same answer whether the condition is true or false
		def hits(op, value):
			try:
				result = reportview.execute(
					"Card Equipment",
					fields=["name"],
					filters=[["Card Consumption Rate", "litres_per_hour", op, value], ["name", "=", eq.name]],
				)
			except REFUSED:
				return "refused"
			finally:
				frappe.clear_messages()
			return len(result)

		self.assertEqual(hits(">", 37), hits(">", 38))
		self.assertEqual(hits("=", 37.25), hits("=", 1))

	def test_operator_reads_nothing(self):
		eq = self._equipment(rates=[("2026-01-01", 10)])
		row = self._row_name(eq.name)
		frappe.set_user(self._user(["Card Operator"]))
		self.assertTrue(self._refused(rest_get, "Card Consumption Rate", row))
		self.assertTrue(self._refused(rest_get, "Card Equipment", eq.name))

	def test_card_user_cannot_change_rates(self):
		eq = self._equipment(rates=[("2026-01-01", 10)])
		frappe.set_user(self._user(["Card User"]))
		# equipment rows: level 1, Card User has no level-1 write
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.append(
			"consumption_rates", {"valid_from": add_days(getdate(), 10), "litres_per_hour": 50, "reason": "x"}
		)
		try:
			doc.save()
		except REFUSED:
			pass
		frappe.clear_messages()
		frappe.set_user("Administrator")
		self.assertEqual(len(self._seed_rows(eq.name)), 1)
		# type rows: Card User writes the type, but not its rates
		frappe.set_user(self._user(["Card User"]))
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.append("default_consumption_rates", {"valid_from": add_days(getdate(), 10), "litres_per_hour": 50})
		self.assertTrue(self._refused(t.save))
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.description = "changed by Card User"
		t.save()  # other type fields stay writable
		# Card Manager may change them
		frappe.set_user(self._user(["Card Manager"]))
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.append("default_consumption_rates", {"valid_from": add_days(getdate(), 10), "litres_per_hour": 50})
		t.save()

	def test_restricted_manager_type_rows_own_company_only(self):
		other = self._other_company()
		frappe.set_user(self._user(["Card Manager"], restrict=self.company))
		future = add_days(getdate(), 10)
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.append("default_consumption_rates", {"valid_from": future, "litres_per_hour": 5, "company": other})
		self.assertTrue(self._refused(t.save))
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.append(
			"default_consumption_rates", {"valid_from": future, "litres_per_hour": 5, "company": self.company}
		)
		t.save()
		t = frappe.get_doc("Card Equipment Type", self.etype)
		row = t.append("default_consumption_rates", {"valid_from": add_days(future, 1), "litres_per_hour": 6})
		row.company = None
		t.save()
		self.assertEqual(len(t.default_consumption_rates), 2)
		# (Frappe fills an empty company from the user's single permitted company: never another company)
		self.assertLessEqual({r.company or None for r in t.default_consumption_rates}, {self.company, None})

	def test_restricted_manager_cannot_touch_rows_for_every_company(self):
		# a row with no company also sets company B's rate: a user limited to company A may not edit or delete it
		future = add_days(getdate(), 10)
		self._set_type_rates([(future, 20)])
		other = self._other_company()
		eq_b = self._equipment(company=other)
		self.assertEqual(consumption_rate(eq_b.name, future), 20)
		manager = self._user(["Card Manager"], restrict=self.company)

		def edit(change):
			frappe.set_user(manager)
			try:
				t = frappe.get_doc("Card Equipment Type", self.etype)
				change(t)
				return self._refused(t.save)
			finally:
				frappe.set_user("Administrator")

		def set_rate(t):
			t.default_consumption_rates[0].litres_per_hour = 0

		def move_to_own_company(t):
			t.default_consumption_rates[0].company = self.company

		def delete(t):
			t.set("default_consumption_rates", [])

		self.assertTrue(edit(set_rate))
		self.assertTrue(edit(move_to_own_company))
		self.assertTrue(edit(delete))
		self.assertEqual(consumption_rate(eq_b.name, future), 20)
		# an unrestricted Card Manager may
		frappe.set_user(self._user(["Card Manager"]))
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.set("default_consumption_rates", [])
		t.save()
		frappe.set_user("Administrator")
		self.assertIsNone(consumption_rate(eq_b.name, future))

	def test_known_limit_child_list_filter_reveals_rate(self):
		"""KNOWN LIMIT (Frappe v16, tracked as FR-148): frappe/database/query.py checks no field permission on
		filters and order_by of a child DocType without permissions of its own, so a level-0 reader of the
		equipment can still infer a rate by filtering the child list. Field values stay closed. When FR-148 closes
		the gap this test must change (the asserted inference no longer works)."""
		eq = self._equipment(rates=[("2026-01-01", 37.25)])
		frappe.set_user(self._user(["Card Supervisor"]))

		def count(filters=None, order_by=None):
			try:
				rows = rest_get_list(
					"Card Consumption Rate",
					fields=["name"],
					filters={"parent": eq.name, **(filters or {})},
					parent="Card Equipment",
					order_by=order_by,
					limit_page_length=0,
				)
			except REFUSED:
				return "refused"
			finally:
				frappe.clear_messages()
			return rows

		# the values themselves never come back
		self.assertFalse(self._leaks(37.25, count))
		# but a filter on the rate answers differently whether the guess is true or false
		self.assertEqual(len(count({"litres_per_hour": [">", 37]})), 1)
		self.assertEqual(len(count({"litres_per_hour": [">", 38]})), 0)
		self.assertEqual(len(count({"litres_per_hour": 37.25})), 1)
		self.assertNotEqual(count(order_by="litres_per_hour asc"), "refused")

	def test_change_history_masks_rates(self):
		eq = self._equipment()
		version = frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Card Equipment",
				"docname": eq.name,
				"data": json.dumps(
					{
						"changed": [],
						"added": [["consumption_rates", {"valid_from": "2026-01-01", "litres_per_hour": 10}]],
						"removed": [],
						"row_changed": [["consumption_rates", 0, "x", [["litres_per_hour", 10, 12]]]],
					}
				),
			}
		)
		mask_restricted_version(version)
		data = json.loads(version.data)
		self.assertEqual(data["added"][0][1]["litres_per_hour"], MASKED)
		self.assertEqual(data["added"][0][1]["valid_from"], MASKED)
		self.assertEqual(data["row_changed"][0][3][0][1:], [MASKED, MASKED])
