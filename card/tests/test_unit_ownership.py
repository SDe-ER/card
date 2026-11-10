# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#42 (WP-04, WP-05): a combined unit and its components are owned equipment, and the
unit-component flag follows the units' component tables. Existing records that break the
rules are listed, never changed silently. Data is per test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase

from card.card.doctype.card_equipment.card_equipment import (
	get_unit_integrity_issues,
	move_component,
	replace_component,
	resync_unit_component_flag,
	unit_integrity_issues,
)
from card.card.doctype.card_monthly_card.card_monthly_card import get_card_context
from card.patches.v4_6_0 import derive_unit_component_flag
from card.tests import test_transfer as _transfer
from card.tests.test_controllers import _ensure_masters

OWNED = "ملك"
RENTED = "إيجار"
RENTED_IN = "مستأجَرة من مورد"


def _legacy(fn):
	"""Write a record the way it was stored before the rules (validation of a patch)."""
	frappe.flags.in_patch = True
	try:
		return fn()
	finally:
		frappe.flags.in_patch = False


class TestUnitOwnership(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	setUp = _transfer.TestEquipmentTransfer.setUp
	tearDown = _transfer.TestEquipmentTransfer.tearDown
	_d = _transfer.TestEquipmentTransfer._d
	_project = _transfer.TestEquipmentTransfer._project
	_equipment = _transfer.TestEquipmentTransfer._equipment
	_card = _transfer.TestEquipmentTransfer._card
	_assign = _transfer.TestEquipmentTransfer._assign
	_refused = _transfer.TestEquipmentTransfer._refused

	def _refused_with(self, action, pattern):
		frappe.db.savepoint("card_refused")
		with self.assertRaisesRegex(frappe.ValidationError, pattern):
			action()
		frappe.db.rollback(save_point="card_refused")

	def _rented(self, **kw):
		return self._equipment(ownership=RENTED, supplier=self.supplier, **kw)

	def _unit(self, *components, **kw):
		return self._equipment(
			"TEST-UO-UNIT", is_unit=1, components=[{"component": c, "role": "R"} for c in components], **kw
		)

	def _flag(self, name):
		return frappe.db.get_value("Card Equipment", name, "is_unit_component")

	def _issues(self, *names):
		rows = frappe.get_all(
			"Card Equipment",
			filters={"name": ["in", list(names)]},
			fields=["name", "company", "ownership", "is_unit", "is_unit_component"],
		)
		return {(i.equipment, i.issue) for i in unit_integrity_issues(rows)}

	# ---- WP-04: backend rule ----
	def test_owned_unit_with_owned_components_saves(self):
		a, b = self._equipment().name, self._equipment().name
		unit = self._unit(a, b)
		self.assertEqual(len(unit.components), 2)

	def test_rented_equipment_cannot_be_a_unit(self):
		self._refused_with(lambda: self._rented(is_unit=1), "Only owned equipment can be a unit")
		rented = self._rented()
		doc = frappe.get_doc("Card Equipment", rented.name)
		doc.is_unit = 1
		self._refused_with(doc.save, "Only owned equipment can be a unit")

	def test_rented_component_is_refused(self):
		rented = self._rented().name
		self._refused_with(lambda: self._unit(rented), "is not owned equipment")
		unit = self._unit()
		doc = frappe.get_doc("Card Equipment", unit.name)
		doc.append("components", {"component": rented})
		self._refused_with(doc.save, "is not owned equipment")

	def test_replace_with_a_rented_piece_is_refused(self):
		a = self._equipment().name
		unit = self._unit(a)
		rented = self._rented().name
		self._refused_with(
			lambda: replace_component(unit.name, a, rented, self._d(15), "test"), "is not owned equipment"
		)

	def test_unit_cannot_change_to_rented(self):
		unit = self._unit(self._equipment().name)
		doc = frappe.get_doc("Card Equipment", unit.name)
		doc.update({"ownership": RENTED, "rental_direction": RENTED_IN, "supplier": self.supplier})
		doc.commercial_change_reason = "test"
		self._refused_with(doc.save, "Only owned equipment can be a unit")
		self.assertEqual(frappe.db.get_value("Card Equipment", unit.name, "ownership"), OWNED)

	def test_listed_component_cannot_change_to_rented(self):
		piece = self._equipment().name
		self._unit(piece)
		doc = frappe.get_doc("Card Equipment", piece)
		doc.update({"ownership": RENTED, "rental_direction": RENTED_IN, "supplier": self.supplier})
		doc.commercial_change_reason = "test"
		self._refused_with(doc.save, "a unit component must be owned")
		self.assertEqual(frappe.db.get_value("Card Equipment", piece, "ownership"), OWNED)

	def test_legacy_rented_unit_is_reported_not_changed(self):
		piece = self._rented().name
		unit = _legacy(lambda: self._rented(is_unit=1, components=[{"component": piece}]))
		# an unrelated save of the legacy unit is not blocked, nothing is rewritten
		doc = frappe.get_doc("Card Equipment", unit.name)
		doc.site_location = "yard"
		doc.save()
		self.assertEqual(frappe.db.get_value("Card Equipment", unit.name, "ownership"), RENTED)
		self.assertEqual(len(frappe.get_doc("Card Equipment", unit.name).components), 1)
		self.assertEqual(
			self._issues(unit.name, piece),
			{(unit.name, "Unit is not owned"), (piece, "Component is not owned")},
		)
		# ... but no piece may join it
		doc = frappe.get_doc("Card Equipment", unit.name)
		doc.append("components", {"component": self._equipment().name})
		self._refused_with(doc.save, "no component can join it")

	def test_integrity_report_is_company_scoped(self):
		unit = _legacy(lambda: self._rented(is_unit=1))
		self.assertIn(unit.name, {i.equipment for i in get_unit_integrity_issues(self.company)})
		other = self._other_company()
		user = "uo-" + frappe.generate_hash(length=6) + "@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": "UO",
				"send_welcome_email": 0,
				"roles": [{"role": "Card Manager"}],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": other,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			self.assertNotIn(unit.name, {i.equipment for i in get_unit_integrity_issues()})
		finally:
			frappe.set_user("Administrator")

	def _other_company(self):
		name = "TEST-UO-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "U" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	# ---- WP-05: derived flag ----
	def test_flag_follows_the_component_table(self):
		a, b = self._equipment().name, self._equipment().name
		self.assertEqual(self._flag(a), 0)
		unit = self._unit(a)
		self.assertEqual(self._flag(a), 1)
		replace_component(unit.name, a, b, self._d(15), "test")
		self.assertEqual((self._flag(a), self._flag(b)), (0, 1))
		frappe.delete_doc("Card Equipment", unit.name, ignore_permissions=True)
		self.assertEqual(self._flag(b), 0)

	def test_flag_cannot_be_written_by_a_save(self):
		piece = self._equipment().name
		doc = frappe.get_doc("Card Equipment", piece)
		doc.is_unit_component = 1
		doc.save()
		self.assertEqual(self._flag(piece), 0)
		self._unit(piece)
		doc = frappe.get_doc("Card Equipment", piece)
		doc.is_unit_component = 0
		doc.save()
		self.assertEqual(self._flag(piece), 1)

	def test_component_days_belong_on_the_unit_card(self):
		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		unit = self._unit(a)
		replace_component(unit.name, a, b, self._d(15), "test")
		# a left the unit on day 14: its own card may record day 20, not day 10
		self._refused_with(
			lambda: self._card(a, p, [10]).insert(ignore_permissions=True), "is a component of unit"
		)
		self._card(a, p, [20]).insert(ignore_permissions=True)
		# b is a current component from day 15
		self._refused(lambda: self._card(b, p, [20]).insert(ignore_permissions=True))

	def test_legacy_flag_without_a_unit_still_refuses_the_card(self):
		p = self._project("U")
		piece = self._equipment().name
		frappe.db.set_value("Card Equipment", piece, "is_unit_component", 1)
		self._refused(lambda: self._card(piece, p, [10]).insert(ignore_permissions=True))
		self.assertEqual(self._issues(piece), {(piece, "Component flag without a unit")})

	def test_patch_writes_only_unambiguous_flags_and_is_idempotent(self):
		listed, ambiguous, left = (self._equipment().name for _ in range(3))
		unit = self._unit(listed, left)
		row = next(r for r in unit.components if r.component == left)
		frappe.db.set_value("Card Equipment Component", row.name, "to_date", self._d(10))
		frappe.db.set_value("Card Equipment", listed, "is_unit_component", 0)  # stale: listed, open
		frappe.db.set_value("Card Equipment", left, "is_unit_component", 1)  # stale: every row closed
		frappe.db.set_value("Card Equipment", ambiguous, "is_unit_component", 1)  # no unit lists it
		derive_unit_component_flag.execute()
		state = {n: self._flag(n) for n in (listed, ambiguous, left)}
		self.assertEqual(state, {listed: 1, ambiguous: 1, left: 0})
		derive_unit_component_flag.execute()
		self.assertEqual({n: self._flag(n) for n in state}, state)

	def test_resync_resolves_an_ambiguous_flag(self):
		piece = self._equipment().name
		frappe.db.set_value("Card Equipment", piece, "is_unit_component", 1)
		self.assertEqual(resync_unit_component_flag(piece), 0)
		self.assertEqual(self._flag(piece), 0)

	def test_resync_needs_card_manager_level(self):
		piece = self._equipment().name
		user = "uo-" + frappe.generate_hash(length=6) + "@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": "UO",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				resync_unit_component_flag(piece)
		finally:
			frappe.set_user("Administrator")

	def _mixed_card(self, equipment, project, hours_by_day):
		d = frappe.new_doc("Card Monthly Card")
		d.update(
			{
				"equipment": equipment,
				"project": project,
				"shift": "نهاري",
				"month": self.month_str,
				"year": int(self.year_str),
			}
		)
		for day, hours in sorted(hours_by_day.items()):
			d.append("days", {"operation_date": self._d(day), "day_status": "عمل", "working_hours": hours})
		return d

	def test_mid_month_join_and_leave_save_with_zero_hour_rows(self):
		# review MEDIUM-1: the form adds a 0-hour row for every day on the project
		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		self._assign(a, p, 1)
		self._assign(b, p, 1)
		unit = self._unit(a)
		replace_component(unit.name, a, b, self._d(15), "test")  # a leaves after day 14, b joins on 15
		all_days = {day: 0 for day in range(1, 29)}
		# working hours inside the unit period stay refused
		self._refused_with(
			lambda: self._mixed_card(a, p, {**all_days, 10: 8}).insert(ignore_permissions=True),
			"is a component of unit",
		)
		self._refused_with(
			lambda: self._mixed_card(b, p, {**all_days, 20: 8}).insert(ignore_permissions=True),
			"is a component of unit",
		)
		# 0-hour rows inside the unit period pass; the hours are outside it
		self._mixed_card(a, p, {**all_days, 20: 8}).insert(ignore_permissions=True)
		self._mixed_card(b, p, {**all_days, 5: 8}).insert(ignore_permissions=True)
		# the form is not offered the unit days
		days_a = get_card_context(a, self.month_str, self.year_str, p)["days"]
		days_b = get_card_context(b, self.month_str, self.year_str, p)["days"]
		self.assertNotIn(self._d(10), days_a)
		self.assertIn(self._d(20), days_a)
		self.assertIn(self._d(5), days_b)
		self.assertNotIn(self._d(20), days_b)

	def test_component_row_inserted_on_its_own_sets_the_flag(self):
		# review LOW-1: a row saved without its unit re-derives the piece's flag
		piece = self._equipment().name
		unit = self._unit()
		frappe.get_doc(
			{
				"doctype": "Card Equipment Component",
				"parenttype": "Card Equipment",
				"parentfield": "components",
				"parent": unit.name,
				"component": piece,
				"role": "R",
			}
		).insert(ignore_permissions=True)
		self.assertEqual(self._flag(piece), 1)

	def test_move_between_units_keeps_the_flag_with_one_sync(self):
		# review LOW-3: the piece stays a component; no cleared-then-set pair of comments
		piece = self._equipment().name
		source, target = self._unit(piece), self._unit()

		def comments():
			return frappe.get_all(
				"Comment",
				filters={
					"reference_doctype": "Card Equipment",
					"reference_name": piece,
					"comment_type": "Info",
				},
				pluck="content",
			)

		before = len(comments())
		move_component(source.name, piece, target.name, self._d(15), "test")
		self.assertEqual(self._flag(piece), 1)
		self.assertEqual(len(comments()), before)
