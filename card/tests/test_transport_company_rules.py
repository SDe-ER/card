# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Per-company transport settings in Card Settings > Company settings:
- #42 (WP-06): the initial place of new equipment (no hardcoded place);
- #43/#121/#122 (WP-15): the move-day rule of a project -> project transport. Default (empty) is
  the rule CARD always applied: the new assignment starts the day after the move.
Data is per test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from card.constants import MOVE_DAY_NEXT, MOVE_DAY_SAME
from card.settings import company_setting
from card.tests import test_transfer as _transfer
from card.tests.test_controllers import _ensure_masters
from card.tests.transport_parties import company_paid
from card.transfer import current_location


class TestTransportCompanyRules(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	setUp = _transfer.TestEquipmentTransfer.setUp
	tearDown = _transfer.TestEquipmentTransfer.tearDown
	_d = _transfer.TestEquipmentTransfer._d
	_project = _transfer.TestEquipmentTransfer._project
	_equipment = _transfer.TestEquipmentTransfer._equipment
	_assign = _transfer.TestEquipmentTransfer._assign
	_transport = _transfer.TestEquipmentTransfer._transport
	_card = _transfer.TestEquipmentTransfer._card
	_submitted_card = _transfer.TestEquipmentTransfer._submitted_card
	_assignments = _transfer.TestEquipmentTransfer._assignments
	_refused = _transfer.TestEquipmentTransfer._refused

	# ---- helpers ----
	def _company_row(self, company=None, **values):
		"""Write only the company's settings row (rolled back), so unrelated Card Settings
		rules on the site are not re-validated."""
		company = company or self.company
		name = frappe.db.get_value(
			"Card Company Settings",
			{"parent": "Card Settings", "parenttype": "Card Settings", "company": company},
			"name",
		)
		if name:
			frappe.db.set_value("Card Company Settings", name, values)
			return
		frappe.get_doc(
			{
				"doctype": "Card Company Settings",
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "company_settings",
				"company": company,
				**values,
			}
		).db_insert()

	def _place(self, label):
		loc = frappe.new_doc("Location")
		loc.location_name = "TEST-TCR-%s-%s" % (label, frappe.generate_hash(length=6))
		loc.insert(ignore_permissions=True)
		return loc.name

	def _to(self, assignment):
		value = frappe.db.get_value("Card Equipment Assignment", assignment, "to_date")
		return getdate(value) if value else None

	def _from(self, assignment):
		return getdate(frappe.db.get_value("Card Equipment Assignment", assignment, "from_date"))

	def _other_company(self):
		name = "TEST-TCR-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "T" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	# ---- WP-06: initial place ----
	def test_settings_have_the_company_fields(self):
		meta = frappe.get_meta("Card Company Settings")
		self.assertEqual(meta.get_field("initial_location").options, "Location")
		self.assertEqual(meta.get_field("move_day_rule").options.split("\n"), [MOVE_DAY_NEXT, MOVE_DAY_SAME])

	def test_new_equipment_starts_at_the_company_initial_place(self):
		place = self._place("YARD")
		self._company_row(initial_location=place)
		eq = self._equipment().name
		here = current_location(eq)
		self.assertEqual((here.type, here.location, here.get("initial")), ("Storage", place, 1))
		# the first transport records it as From, and as a first entry
		t = self._transport(eq, self._project("A"), 10, submit=False)
		row = t.items[0]
		self.assertEqual((row.from_type, row.from_location, row.movement), ("Storage", place, "First entry"))
		self.assertEqual((t.source_type, t.source_location), ("Storage", place))

	def test_without_a_setting_the_initial_place_stays_empty(self):
		self._company_row(initial_location=None)
		here = current_location(self._equipment().name)
		self.assertEqual((here.type, here.location), ("Storage", None))

	def test_initial_place_is_per_company(self):
		mine, theirs = self._place("MINE"), self._place("THEIRS")
		other = self._other_company()
		self._company_row(initial_location=mine)
		self._company_row(other, initial_location=theirs)
		self.assertEqual(current_location(self._equipment().name).location, mine)
		self.assertEqual(company_setting(other, "initial_location"), theirs)
		self.assertIsNone(company_setting(None, "initial_location"))

	def test_move_to_the_initial_place_is_no_move(self):
		place = self._place("YARD")
		self._company_row(initial_location=place)
		eq = self._equipment().name
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"company": self.company,
				"date": self._d(10),
				"destination_type": "Storage",
				"destination_location": place,
				"transport_supplier": self.supplier,
				"amount": 100,
			}
		)
		t.append("items", {"card_equipment": eq})
		company_paid(t)
		frappe.db.savepoint("card_refused")
		with self.assertRaisesRegex(frappe.ValidationError, "already there"):
			t.insert(ignore_permissions=True)
		frappe.db.rollback(save_point="card_refused")

	# ---- WP-15: move-day rule ----
	def _move_between_projects(self, day=10):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a).name
		old = self._assign(eq, proj_a, 1)
		return eq, proj_a, proj_b, old

	def test_default_rule_is_the_next_day(self):
		self._company_row(move_day_rule=None)
		eq, _a, proj_b, old = self._move_between_projects()
		t = self._transport(eq, proj_b, 10)
		self.assertEqual(t.move_day_rule, MOVE_DAY_NEXT)
		self.assertEqual(self._to(old.name), getdate(self._d(10)))
		self.assertEqual(self._from(t.created_assignment), getdate(add_days(self._d(10), 1)))

	def test_move_day_rule_gives_the_move_day_to_the_new_project(self):
		self._company_row(move_day_rule=MOVE_DAY_SAME)
		eq, _a, proj_b, old = self._move_between_projects()
		t = self._transport(eq, proj_b, 10)
		self.assertEqual(t.move_day_rule, MOVE_DAY_SAME)
		self.assertEqual(self._to(old.name), getdate(self._d(9)))
		self.assertEqual(self._from(t.created_assignment), getdate(self._d(10)))
		self.assertEqual(frappe.db.get_value("Card Equipment", eq, "current_project"), proj_b)
		# the move day is now a card day of the new project
		self._card(eq, proj_b, [10]).insert(ignore_permissions=True)

	def test_move_day_rule_cancel_restores_and_is_kept_from_submit(self):
		self._company_row(move_day_rule=MOVE_DAY_SAME)
		eq, proj_a, proj_b, old = self._move_between_projects()
		t = self._transport(eq, proj_b, 10)
		created = t.created_assignment
		self._company_row(move_day_rule=MOVE_DAY_NEXT)  # a later change of the setting
		t.reload()
		t.cancel()
		self.assertFalse(frappe.db.exists("Card Equipment Assignment", created))
		self.assertIsNone(self._to(old.name))
		self.assertEqual(frappe.db.get_value("Card Equipment", eq, "current_project"), proj_a)

	def test_move_day_rule_keeps_card_day_protection(self):
		self._company_row(move_day_rule=MOVE_DAY_SAME)
		eq, proj_a, proj_b, old = self._move_between_projects()
		# a submitted card day on the old project on the move day
		self._submitted_card(eq, proj_a, [10])
		self._refused(lambda: self._transport(eq, proj_b, 10))
		self.assertIsNone(self._to(old.name))
		# the next-day rule leaves the move day on the old project, so the same move passes
		self._company_row(move_day_rule=MOVE_DAY_NEXT)
		self._transport(eq, proj_b, 10)
		self.assertEqual(self._to(old.name), getdate(self._d(10)))

	def test_cancel_refused_with_a_card_day_on_the_move_day(self):
		self._company_row(move_day_rule=MOVE_DAY_SAME)
		eq, _a, proj_b, _old = self._move_between_projects()
		t = self._transport(eq, proj_b, 10)
		self._submitted_card(eq, proj_b, [10])
		frappe.db.savepoint("card_refused")
		with self.assertRaisesRegex(frappe.ValidationError, "operation days are recorded"):
			t.cancel()
		frappe.db.rollback(save_point="card_refused")

	def test_move_day_rule_refuses_leaving_on_the_arrival_day(self):
		self._company_row(move_day_rule=MOVE_DAY_SAME)
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment().name
		self._transport(eq, proj_a, 10)  # first entry: on A from day 10
		frappe.db.savepoint("card_refused")
		with self.assertRaisesRegex(
			frappe.ValidationError, "cannot leave for another project on the same day"
		):
			self._transport(eq, proj_b, 10)
		frappe.db.rollback(save_point="card_refused")

	def test_first_entry_starts_on_the_move_day_under_both_rules(self):
		for label, rule in (("F1", MOVE_DAY_NEXT), ("F2", MOVE_DAY_SAME)):
			self._company_row(move_day_rule=rule)
			eq = self._equipment().name
			t = self._transport(eq, self._project(label), 10)
			self.assertEqual(self._from(t.created_assignment), getdate(self._d(10)))

	def test_rule_is_per_company(self):
		other = self._other_company()
		self._company_row(move_day_rule=MOVE_DAY_NEXT)
		self._company_row(other, move_day_rule=MOVE_DAY_SAME)
		eq, _a, proj_b, old = self._move_between_projects()
		t = self._transport(eq, proj_b, 10)
		self.assertEqual(t.move_day_rule, MOVE_DAY_NEXT)
		self.assertEqual(self._to(old.name), getdate(self._d(10)))

	def test_workshop_move_keeps_its_rule(self):
		self._company_row(move_day_rule=MOVE_DAY_SAME)
		eq, _a, _b, old = self._move_between_projects()
		t = _transfer.TestEquipmentTransfer._move(self, eq, 10, destination="Workshop")
		self.assertIsNone(t.move_day_rule)
		self.assertEqual(self._to(old.name), getdate(self._d(10)))
