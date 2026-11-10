# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-144 (#31, #42, #47): effective-dated consumption rates (litres per operating hour).

consumption_rate(equipment, on_date) = the equipment's row valid on the date, else the type default valid on the
date, else the static expected_consumption, else None. The seed patch gives each equipment with a static value one
row with that value, so every date keeps today's value; a second run adds nothing. Rows are reachable by REST only
through the parent's permission (company User Permission, level-1 table), and the change history of a level-0
reader never shows a rate. Everything is created per test and rolled back."""

import json

import frappe
from frappe.client import get as rest_get
from frappe.client import get_list as rest_get_list
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from card.consumption import (
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
		for valid_from, rate in rates:
			t.append("default_consumption_rates", {"valid_from": valid_from, "litres_per_hour": rate})
		t.insert(ignore_permissions=True)
		return t.name

	def _equipment(self, static=None, rates=(), company=None, etype=None):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company or self.company
		eq.equipment_type = etype or self.etype
		eq.equipment_name = "TEST-CRATE-EQ-" + frappe.generate_hash(length=6)
		eq.ownership = "ملك"
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		if static is not None:
			eq.expected_consumption = static
		for valid_from, rate in rates:
			eq.append("consumption_rates", {"valid_from": valid_from, "litres_per_hour": rate})
		eq.insert(ignore_permissions=True)
		return eq

	def _set_type_rates(self, rates):
		t = frappe.get_doc("Card Equipment Type", self.etype)
		t.set("default_consumption_rates", [])
		for valid_from, rate in rates:
			t.append("default_consumption_rates", {"valid_from": valid_from, "litres_per_hour": rate})
		t.save(ignore_permissions=True)

	# ---------- resolution ----------

	def test_equipment_override_beats_type_default(self):
		self._set_type_rates([("2026-01-01", 20)])
		eq = self._equipment(static=9, rates=[("2026-03-01", 14)])
		self.assertEqual(consumption_rate(eq.name, "2026-03-15"), 14)
		self.assertEqual(consumption_rate_details(eq.name, "2026-03-15").source, SOURCE_EQUIPMENT)
		# before the override starts the type default applies, not the static field
		details = consumption_rate_details(eq.name, "2026-02-01")
		self.assertEqual((details.rate, details.source), (20, SOURCE_TYPE))
		self.assertEqual(getdate(details.valid_from), getdate("2026-01-01"))
		# before every dated row the static field is the fallback
		details = consumption_rate_details(eq.name, "2025-12-31")
		self.assertEqual((details.rate, details.source, details.valid_from), (9, SOURCE_STATIC, None))

	def test_type_default_without_override(self):
		self._set_type_rates([("2026-01-01", 20), ("2026-06-01", 22)])
		eq = self._equipment()
		self.assertEqual(consumption_rate(eq.name, "2026-05-31"), 20)
		self.assertEqual(consumption_rate(eq.name, "2026-06-01"), 22)
		self.assertIsNone(consumption_rate(eq.name, "2025-12-31"))

	def test_date_boundaries(self):
		eq = self._equipment(rates=[("2026-06-01", 12), ("2026-01-01", 10)])  # rows out of order
		self.assertIsNone(consumption_rate(eq.name, "2025-12-31"))
		self.assertEqual(consumption_rate(eq.name, "2026-01-01"), 10)  # valid_from is inclusive
		self.assertEqual(consumption_rate(eq.name, "2026-05-31"), 10)
		self.assertEqual(consumption_rate(eq.name, "2026-06-01"), 12)
		self.assertEqual(consumption_rate(eq.name, "2030-01-01"), 12)  # no end date
		# empty date = today
		today = getdate()
		eq2 = self._equipment(rates=[(add_days(today, 1), 30), (add_days(today, -1), 25)])
		self.assertEqual(consumption_rate(eq2.name), 25)

	def test_no_rate(self):
		eq = self._equipment()
		self.assertIsNone(consumption_rate(eq.name, "2026-03-01"))
		self.assertEqual(consumption_rate_details(eq.name).source, None)
		# a static 0 is "not set" (as the diesel analysis reads it), never a rate of 0
		eq0 = self._equipment(static=0)
		self.assertIsNone(consumption_rate(eq0.name, "2026-03-01"))
		self.assertIsNone(consumption_rate(None))
		self.assertIsNone(consumption_rate("TEST-CRATE-MISSING-" + self.token))

	def test_explicit_zero_row_is_a_rate(self):
		# a dated 0 (e.g. an unpowered trailer) is a stated rate and overrides the type default
		self._set_type_rates([("2026-01-01", 20)])
		eq = self._equipment(rates=[("2026-01-01", 0)])
		details = consumption_rate_details(eq.name, "2026-02-01")
		self.assertEqual((details.rate, details.source), (0, SOURCE_EQUIPMENT))

	# ---------- validation ----------

	def test_duplicate_valid_from_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(rates=[("2026-01-01", 10), ("2026-01-01", 11)])
		with self.assertRaises(frappe.ValidationError):
			self._set_type_rates([("2026-01-01", 10), ("2026-01-01", 11)])
		# the same date on the type and on the equipment is not a duplicate (different tables)
		self._set_type_rates([("2026-01-01", 10)])
		self._equipment(rates=[("2026-01-01", 11)])

	def test_negative_rate_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(rates=[("2026-01-01", -1)])

	def test_static_field_kept_and_rows_win(self):
		# the static field is not removed or changed; a change after dated rows exist only warns
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
		self.assertTrue(meta.get_field("expected_consumption").read_only_depends_on)

	# ---------- seed patch ----------

	def _parity_dates(self, eq):
		created = getdate(frappe.db.get_value("Card Equipment", eq, "creation"))
		return [add_days(created, -400), add_days(created, -1), created, add_days(created, 1), "2040-01-01"]

	def test_seed_patch_parity_and_idempotent(self):
		with_static = self._equipment(static=9.5)
		without = self._equipment()
		zero = self._equipment(static=0)
		already = self._equipment(static=4, rates=[("2026-01-01", 6)])
		subjects = (with_static, without, zero, already)
		before = {
			eq.name: [consumption_rate(eq.name, d) for d in self._parity_dates(eq.name)] for eq in subjects
		}

		seed_consumption_rates.execute()

		after = {
			eq.name: [consumption_rate(eq.name, d) for d in self._parity_dates(eq.name)] for eq in subjects
		}
		self.assertEqual(before, after)

		def rows(name):
			return frappe.get_all(
				"Card Consumption Rate",
				filters={"parent": name, "parenttype": "Card Equipment", "parentfield": "consumption_rates"},
				fields=["valid_from", "litres_per_hour", "idx"],
			)

		seeded = rows(with_static.name)
		self.assertEqual(len(seeded), 1)
		self.assertEqual(seeded[0].litres_per_hour, 9.5)
		self.assertEqual(
			getdate(seeded[0].valid_from),
			getdate(frappe.db.get_value("Card Equipment", with_static.name, "creation")),
		)
		self.assertEqual(consumption_rate_details(with_static.name, "2040-01-01").source, SOURCE_EQUIPMENT)
		self.assertEqual(rows(without.name), [])
		self.assertEqual(rows(zero.name), [])
		self.assertEqual(len(rows(already.name)), 1)  # an equipment with rows is skipped
		# the static field is unchanged
		self.assertEqual(frappe.db.get_value("Card Equipment", with_static.name, "expected_consumption"), 9.5)

		# second run (second migrate): nothing added, same values
		seed_consumption_rates.execute()
		self.assertEqual(len(rows(with_static.name)), 1)
		again = {
			eq.name: [consumption_rate(eq.name, d) for d in self._parity_dates(eq.name)] for eq in subjects
		}
		self.assertEqual(before, again)
		# the seeded equipment still saves (the row passes validation)
		doc = frappe.get_doc("Card Equipment", with_static.name)
		self.assertEqual(len(doc.consumption_rates), 1)
		doc.save(ignore_permissions=True)

	# ---------- permissions and isolation ----------

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

	def test_company_isolation_by_rest(self):
		other = self._other_company()
		eq_a = self._equipment(rates=[("2026-01-01", 10)])
		eq_b = self._equipment(rates=[("2026-01-01", 20)], company=other)
		row_a, row_b = self._row_name(eq_a.name), self._row_name(eq_b.name)
		frappe.set_user(self._user(["Card Manager"], restrict=self.company))
		# own company: the row and the parent's table are readable
		self.assertEqual(rest_get("Card Consumption Rate", row_a)["litres_per_hour"], 10)
		self.assertEqual(rest_get("Card Equipment", eq_a.name)["consumption_rates"][0]["litres_per_hour"], 10)
		# other company: refused on the row, on its parent, and absent from lists
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

	def test_level_zero_reader_sees_no_rate(self):
		# Card Supervisor reads Card Equipment at level 0 only (as for the static field)
		eq = self._equipment(static=9, rates=[("2026-01-01", 10)])
		row = self._row_name(eq.name)
		frappe.set_user(self._user(["Card Supervisor"]))
		doc = rest_get("Card Equipment", eq.name)
		self.assertFalse(doc.get("consumption_rates"))
		self.assertFalse(doc.get("expected_consumption"))
		self.assertTrue(self._refused(rest_get, "Card Consumption Rate", row))

	def test_operator_reads_nothing(self):
		# O-20: Card Operator (CARD Mobile) has no read on the equipment, so none on its rates
		eq = self._equipment(rates=[("2026-01-01", 10)])
		row = self._row_name(eq.name)
		frappe.set_user(self._user(["Card Operator"]))
		self.assertTrue(self._refused(rest_get, "Card Consumption Rate", row))
		self.assertTrue(self._refused(rest_get, "Card Equipment", eq.name))

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
