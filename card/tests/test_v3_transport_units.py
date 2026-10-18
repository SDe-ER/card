# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v3.0.0: a transport moving several machines (equal, editable cost split) and dated
unit components (replace / move between units). Data is per test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate

from card.card.doctype.card_equipment.card_equipment import move_component, replace_component
from card.gl.posting import _transport_shares
from card.tests import test_transfer as _transfer
from card.tests.test_controllers import _ensure_masters


class TestV3TransportAndUnits(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	# the transfer suite's helpers, without inheriting (and re-running) its tests
	setUp = _transfer.TestEquipmentTransfer.setUp
	tearDown = _transfer.TestEquipmentTransfer.tearDown
	_d = _transfer.TestEquipmentTransfer._d
	_project = _transfer.TestEquipmentTransfer._project
	_equipment = _transfer.TestEquipmentTransfer._equipment
	_assign = _transfer.TestEquipmentTransfer._assign
	_card = _transfer.TestEquipmentTransfer._card

	def _trip(self, project, day, rows, amount=1000, submit=False):
		t = frappe.new_doc("Equipment Transport")
		t.project = project
		t.date = self._d(day)
		t.transport_supplier = self.supplier
		t.company = self.company
		t.amount = amount
		for row in rows:
			t.append("items", row if isinstance(row, dict) else {"card_equipment": row})
		t.insert(ignore_permissions=True)
		if submit:
			t.submit()
			t.reload()
		return t

	# ---- transport cost split ----
	def test_equal_split_with_rounding(self):
		p = self._project("S")
		eqs = [self._equipment().name for _ in range(3)]
		t = self._trip(p, 5, eqs, amount=1000)
		self.assertEqual([flt(r.amount, 2) for r in t.items], [333.33, 333.33, 333.34])
		self.assertEqual(t.equipment, eqs[0])  # header mirrors the first row

	def test_edited_share_rebalances_the_others(self):
		p = self._project("S")
		a, b = self._equipment().name, self._equipment().name
		t = self._trip(p, 5, [a, b], amount=1200)
		t.items[0].amount = 700
		t.save(ignore_permissions=True)
		self.assertEqual([flt(r.amount, 2) for r in t.items], [700, 500])
		t.amount = 1500  # trip cost changed; the untouched share takes the difference
		t.save(ignore_permissions=True)
		self.assertEqual([flt(r.amount, 2) for r in t.items], [700, 800])

	def test_shares_must_add_up(self):
		p = self._project("S")
		a, b = self._equipment().name, self._equipment().name
		with self.assertRaises(frappe.ValidationError):
			self._trip(
				p,
				5,
				[{"card_equipment": a, "amount": 700}, {"card_equipment": b, "amount": 700}],
				amount=1000,
			)

	def test_same_equipment_twice_is_refused(self):
		p = self._project("S")
		a = self._equipment().name
		with self.assertRaises(frappe.ValidationError):
			self._trip(p, 5, [a, a])

	def test_posting_shares_follow_rows(self):
		p = self._project("S")
		a, b = self._equipment().name, self._equipment().name
		t = self._trip(p, 5, [{"card_equipment": a, "amount": 700}, b], amount=1200)
		lone = self._trip(p, 6, [], amount=300)
		self.assertEqual(
			_transport_shares([t, lone]), {t.name: [(a, 700.0), (b, 500.0)], lone.name: [(None, 300.0)]}
		)

	# ---- multi-machine transfer ----
	def test_trip_moves_every_machine_and_cancel_reverses(self):
		pa, pb = self._project("A"), self._project("B")
		a = self._equipment(current_project=pa).name
		b = self._equipment(current_project=pa).name
		old_a, old_b = self._assign(a, pa, 1), self._assign(b, pa, 1)
		t = self._trip(pb, 10, [a, b], submit=True)
		for eq, old in ((a, old_a), (b, old_b)):
			self.assertEqual(frappe.db.get_value("Card Equipment", eq, "current_project"), pb)
			self.assertEqual(
				getdate(frappe.db.get_value("Card Equipment Assignment", old.name, "to_date")),
				getdate(self._d(10)),
			)
		self.assertTrue(all(r.created_assignment and r.previous_assignment for r in t.items))
		t.cancel()
		for eq, old in ((a, old_a), (b, old_b)):
			self.assertFalse(frappe.db.get_value("Card Equipment Assignment", old.name, "to_date"))
			self.assertEqual(frappe.db.get_value("Card Equipment", eq, "current_project"), pa)

	# ---- dated unit components ----
	def _unit(self, project, *components):
		return self._equipment(
			"TEST-TR-UNIT",
			is_unit=1,
			current_project=project,
			components=[{"component": c, "role": "R"} for c in components],
		)

	def test_replace_component_keeps_history(self):
		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		unit = self._unit(p, a)
		replace_component(unit.name, a, b, self._d(15), "breakdown")
		rows = frappe.get_doc("Card Equipment", unit.name).components
		self.assertEqual([(r.component, str(r.to_date or "")) for r in rows], [(a, self._d(14)), (b, "")])
		self.assertEqual(str(rows[1].from_date), self._d(15))

	def test_move_component_between_units(self):
		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		u1, u2 = self._unit(p, a), self._unit(p, b)
		move_component(u1.name, a, u2.name, self._d(12))
		self.assertEqual(
			frappe.get_doc("Card Equipment", u1.name).components[0].to_date, getdate(self._d(11))
		)
		self.assertIn(a, [r.component for r in frappe.get_doc("Card Equipment", u2.name).components])

	def test_change_refused_inside_an_approved_period(self):
		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		unit = self._unit(p, a)
		card = self._card(unit.name, p, [3, 4])
		card.insert(ignore_permissions=True)
		card.db_set("docstatus", 1)  # an approved card of the month (submit flow is tested elsewhere)
		with self.assertRaises(frappe.ValidationError):
			replace_component(unit.name, a, b, self._d(20))

	def test_card_days_check_only_current_components(self):
		pa = self._project("A")
		a, b = self._equipment().name, self._equipment().name
		self._assign(a, pa, 1, 9)  # a left the project on day 9
		self._assign(b, pa, 1)
		unit = self._unit(pa, a)
		replace_component(unit.name, a, b, self._d(10))
		self._assign(unit.name, pa, 1)
		# day 12: only b is in the unit and b is on the project -> valid
		self._card(unit.name, pa, [12]).insert(ignore_permissions=True)

	def test_card_user_cannot_change_components(self):
		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		unit = self._unit(p, a)
		email = f"v3-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "V3",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				replace_component(unit.name, a, b, self._d(15))
		finally:
			frappe.set_user("Administrator")
		self.assertEqual([r.component for r in frappe.get_doc("Card Equipment", unit.name).components], [a])

	def test_draft_cannot_carry_assignment_links(self):
		p = self._project("S")
		a = self._equipment().name
		other = self._assign(self._equipment().name, p, 1)
		t = self._trip(p, 5, [{"card_equipment": a, "created_assignment": other.name}])
		self.assertFalse(t.items[0].created_assignment)
