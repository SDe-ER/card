# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment Location History report (FR-130, #53, #127): segments from assignments and
transports, both move-day rules (FR-117), the initial place (FR-116), the date-range clip,
company isolation, report roles and no writes. Data is per test and rolled back."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from card.card.report.equipment_location_history.equipment_location_history import execute
from card.constants import MOVE_DAY_NEXT, MOVE_DAY_SAME
from card.location_history import _History
from card.tests import test_transfer as _transfer
from card.tests import test_transport_company_rules as _rules
from card.tests.test_controllers import _ensure_masters

REPORT = "Equipment Location History"


class TestEquipmentLocationHistory(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	setUp = _transfer.TestEquipmentTransfer.setUp
	_d = _transfer.TestEquipmentTransfer._d
	_project = _transfer.TestEquipmentTransfer._project
	_equipment = _transfer.TestEquipmentTransfer._equipment
	_assign = _transfer.TestEquipmentTransfer._assign
	_transport = _transfer.TestEquipmentTransfer._transport
	_move = _transfer.TestEquipmentTransfer._move
	_company_row = _rules.TestTransportCompanyRules._company_row
	_place = _rules.TestTransportCompanyRules._place
	_other_company = _rules.TestTransportCompanyRules._other_company

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _run(self, equipment=None, start=1, end=28, company=None):
		filters = {"company": company or self.company, "from_date": self._d(start), "to_date": self._d(end)}
		if equipment:
			filters["equipment"] = equipment
		_columns, rows, _message = execute(filters)
		return rows

	def _segments(self, equipment, start=1, end=28):
		return [
			(r["location_type"], r.get("project") or r.get("location"), r["from_date"], r["to_date"])
			for r in self._run(equipment, start, end)
		]

	def _day(self, day):
		return getdate(self._d(day))

	def _user(self, roles, restrict_to=None):
		email = f"loc-history-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Location History",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _between_projects(self, rule):
		self._company_row(move_day_rule=rule)
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a).name
		old = self._assign(eq, proj_a, 1)
		t = self._transport(eq, proj_b, 10)
		return eq, proj_a, proj_b, old, t

	# ---- the report ----
	def test_report_roles_match_the_statements(self):
		roles = {r.role for r in frappe.get_doc("Report", REPORT).roles}
		statement = {r.role for r in frappe.get_doc("Report", "Equipment Customer Statement").roles}
		self.assertEqual(roles, statement)
		self.assertEqual(frappe.db.get_value("Report", REPORT, "report_type"), "Script Report")

	def test_columns(self):
		columns, _rows, _message = execute(
			{"company": self.company, "from_date": self._d(1), "to_date": self._d(2)}
		)
		names = [c["fieldname"] for c in columns]
		for field in ("equipment", "from_date", "to_date", "location_type", "location", "source_document"):
			self.assertIn(field, names)
		source = next(c for c in columns if c["fieldname"] == "source_document")
		self.assertEqual((source["fieldtype"], source["options"]), ("Dynamic Link", "source_doctype"))

	def test_segments_from_assignment_and_transport_next_day_rule(self):
		eq, proj_a, proj_b, old, t = self._between_projects(MOVE_DAY_NEXT)
		rows = self._run(eq)
		self.assertEqual(
			[(r["location_type"], r["project"], r["from_date"], r["to_date"]) for r in rows],
			[
				("Project", proj_a, self._day(1), self._day(10)),
				("Project", proj_b, self._day(11), self._day(28)),
			],
		)
		self.assertEqual(
			(rows[0]["source_doctype"], rows[0]["source_document"]), ("Card Equipment Assignment", old.name)
		)
		self.assertEqual(
			(rows[1]["source_doctype"], rows[1]["source_document"]), ("Equipment Transport", t.name)
		)

	def test_same_day_rule_gives_the_move_day_to_the_new_project(self):
		eq, proj_a, proj_b, _old, t = self._between_projects(MOVE_DAY_SAME)
		self.assertEqual(t.move_day_rule, MOVE_DAY_SAME)
		self.assertEqual(
			self._segments(eq),
			[
				("Project", proj_a, self._day(1), self._day(9)),
				("Project", proj_b, self._day(10), self._day(28)),
			],
		)

	def test_rule_recorded_on_the_transport_wins_over_a_later_setting(self):
		eq, _proj_a, proj_b, _old, _t = self._between_projects(MOVE_DAY_SAME)
		self._company_row(move_day_rule=MOVE_DAY_NEXT)
		self.assertEqual(self._segments(eq)[1], ("Project", proj_b, self._day(10), self._day(28)))

	def test_workshop_move_then_back_to_a_project(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a).name
		self._assign(eq, proj_a, 1)
		shop_move = self._move(eq, 10, destination="Workshop")
		back = self._transport(eq, proj_b, 20)
		rows = self._run(eq)
		self.assertEqual(
			[(r["location_type"], r["from_date"], r["to_date"]) for r in rows],
			[
				("Project", self._day(1), self._day(10)),
				("Workshop", self._day(11), self._day(19)),
				("Project", self._day(20), self._day(28)),
			],
		)
		self.assertEqual(rows[1]["location"], shop_move.destination_location)
		self.assertEqual(rows[1]["source_document"], shop_move.name)
		self.assertEqual((rows[2]["project"], rows[2]["source_document"]), (proj_b, back.name))

	def test_initial_place_until_the_first_move(self):
		place = self._place("YARD")
		self._company_row(initial_location=place)
		eq = self._equipment().name
		self.assertEqual(self._segments(eq), [("Initial place", place, self._day(1), self._day(28))])
		proj = self._project("A")
		self._transport(eq, proj, 10)
		rows = self._run(eq)
		self.assertEqual(
			[
				(r["location_type"], r.get("project") or r["location"], r["from_date"], r["to_date"])
				for r in rows
			],
			[
				("Initial place", place, self._day(1), self._day(9)),
				("Project", proj, self._day(10), self._day(28)),
			],
		)
		self.assertIsNone(rows[0]["source_document"])

	def test_initial_place_empty_without_a_setting(self):
		self._company_row(initial_location=None)
		eq = self._equipment().name
		self.assertEqual(self._segments(eq), [("Initial place", None, self._day(1), self._day(28))])

	def test_date_range_clip(self):
		eq, proj_a, proj_b, _old, _t = self._between_projects(MOVE_DAY_NEXT)
		self.assertEqual(
			self._segments(eq, 5, 15),
			[
				("Project", proj_a, self._day(5), self._day(10)),
				("Project", proj_b, self._day(11), self._day(15)),
			],
		)
		# a window before the move shows only the first project; one after it only the second
		self.assertEqual(self._segments(eq, 2, 6), [("Project", proj_a, self._day(2), self._day(6))])
		self.assertEqual(self._segments(eq, 12, 14), [("Project", proj_b, self._day(12), self._day(14))])

	def test_end_before_start_and_missing_period_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._run(start=10, end=5)
		with self.assertRaises(frappe.ValidationError):
			execute({"company": self.company})

	def test_company_isolation(self):
		other = self._other_company()
		mine = self._equipment().name
		theirs = self._equipment().name
		frappe.db.set_value("Card Equipment", theirs, "company", other, update_modified=False)
		listed = {r["equipment"] for r in self._run()}
		self.assertIn(mine, listed)
		self.assertNotIn(theirs, listed)
		# an equipment of another company is refused, not read
		with self.assertRaises(frappe.PermissionError):
			self._run(theirs)
		# a user restricted to this company may not ask for the other one
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		with self.assertRaises(frappe.PermissionError):
			self._run(company=other)
		self.assertIn(mine, {r["equipment"] for r in self._run(mine)})

	def test_transport_of_another_company_is_not_read(self):
		eq, _a, _b, _old, t = self._between_projects(MOVE_DAY_NEXT)
		frappe.db.set_value(
			"Equipment Transport", t.name, "company", self._other_company(), update_modified=False
		)
		sources = {r["source_document"] for r in self._run(eq)}
		self.assertNotIn(t.name, sources)

	def test_permission_checked_before_reading(self):
		frappe.set_user(self._user(["Projects User"]))
		with (
			patch(
				"card.card.report.equipment_location_history.equipment_location_history.company_segments",
				side_effect=AssertionError("read"),
			),
			self.assertRaises(frappe.PermissionError),
		):
			self._run()

	def test_nothing_is_written(self):
		eq, *_rest = self._between_projects(MOVE_DAY_NEXT)
		self._move(eq, 15, destination="Workshop")
		with (
			patch.object(frappe.db, "set_value", side_effect=AssertionError("write")),
			patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql,
		):
			self._run(eq)
			self._run()
		for call in sql.call_args_list:
			statement = str(call.args[0]).lstrip().lower() if call.args else ""
			self.assertFalse(statement.startswith(("insert", "update", "delete")), statement)

	# ---- units (components count only on their member days) ----
	def _unit(self, *members):
		return self._equipment(
			"TEST-LH-UNIT",
			is_unit=1,
			components=[
				{"component": c, "role": "R", "from_date": self._d(f), "to_date": self._d(t) if t else None}
				for c, f, t in members
			],
		).name

	def test_unit_built_only_from_components(self):
		self._company_row(initial_location=None)
		proj = self._project("U")
		c1, c2 = self._equipment().name, self._equipment().name
		a1 = self._assign(c1, proj, 5)
		a2 = self._assign(c2, proj, 5)
		unit = self._unit((c1, 1, None), (c2, 1, None))
		rows = self._run(unit)
		self.assertEqual(
			[
				(r["location_type"], r.get("project") or r["location"], r["from_date"], r["to_date"])
				for r in rows
			],
			[
				("Initial place", None, self._day(1), self._day(4)),
				("Project", proj, self._day(5), self._day(28)),
			],
		)
		# one row per project, not one per component
		self.assertIn(rows[1]["source_document"], {a1.name, a2.name})
		self.assertFalse(rows[1]["overlap"])

	def test_unit_history_does_not_depend_on_the_date_range(self):
		self._company_row(initial_location=None)
		own, theirs = self._project("OWN"), self._project("COMP")
		c1 = self._equipment().name
		unit = self._unit((c1, 1, None))
		self._assign(unit, own, 1, 10)
		self._assign(c1, theirs, 15)
		full = self._segments(unit)
		self.assertEqual(
			full,
			[
				("Project", own, self._day(1), self._day(10)),
				("Initial place", None, self._day(11), self._day(14)),
				("Project", theirs, self._day(15), self._day(28)),
			],
		)

		def clipped(start, end):
			result = []
			for kind, place, first, last in full:
				first, last = max(first, self._day(start)), min(last, self._day(end))
				if first <= last:
					result.append((kind, place, first, last))
			return result

		for start, end in ((12, 20), (5, 12), (9, 16)):
			self.assertEqual(self._segments(unit, start, end), clipped(start, end), (start, end))

	def test_component_that_left_the_unit_no_longer_counts(self):
		self._company_row(initial_location=None)
		proj = self._project("U")
		c1, c2 = self._equipment().name, self._equipment().name
		self._assign(c1, proj, 1)
		unit = self._unit((c1, 1, 10), (c2, 1, None))
		shop = self._move(c2, 15, destination="Workshop")  # a member's move counts
		self._move(c1, 20, destination="Workshop")  # c1 left on day 10: its move does not
		rows = self._run(unit)
		self.assertEqual(
			[(r["location_type"], r["from_date"], r["to_date"]) for r in rows],
			[
				("Project", self._day(1), self._day(10)),
				("Initial place", self._day(11), self._day(14)),
				("Workshop", self._day(15), self._day(28)),
			],
		)
		self.assertEqual(rows[2]["source_document"], shop.name)

	def test_overlapping_projects_are_marked(self):
		# one machine cannot hold two overlapping assignments; a unit and its piece can
		self._company_row(initial_location=None)
		proj_a, proj_b = self._project("A"), self._project("B")
		c1 = self._equipment().name
		unit = self._unit((c1, 1, None))
		self._assign(unit, proj_a, 1, 20)
		self._assign(c1, proj_b, 10, 25)
		_columns, rows, message = execute(
			{"company": self.company, "from_date": self._d(1), "to_date": self._d(28), "equipment": unit}
		)
		self.assertEqual(
			[(r["location_type"], r["project"], r["from_date"], r["to_date"], r["overlap"]) for r in rows],
			[
				("Project", proj_a, self._day(1), self._day(9), 0),
				("Project", proj_a, self._day(10), self._day(20), 1),
				("Project", proj_b, self._day(10), self._day(20), 1),
				("Project", proj_b, self._day(21), self._day(25), 0),
				("Initial place", None, self._day(26), self._day(28), 0),
			],
		)
		self.assertTrue(message)

	def test_supplier_segment_shows_the_equipment_supplier(self):
		move = frappe._dict(
			name="ET-TEST",
			date=self._d(5),
			creation="2026-01-01 00:00:00",
			destination_type="Supplier",
			destination_location=None,
			equipment_supplier=self.supplier,
			created_assignment=None,
		)
		history = _History("EQ-TEST", [], {}, {"EQ-TEST": [move]}, {}, None)
		rows = history.segments(self._day(1), self._day(10))
		self.assertEqual(
			[(r["location_type"], r["location"], r["from_date"]) for r in rows],
			[("Initial", None, self._day(1)), ("Supplier", self.supplier, self._day(5))],
		)
