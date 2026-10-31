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
from card.tests.transport_parties import as_recorded_before_p12, company_paid, paid_by


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

	def _trip(self, project, day, rows, amount=1000, submit=False, cost=None):
		t = frappe.new_doc("Equipment Transport")
		t.project = project
		t.date = self._d(day)
		t.transport_supplier = self.supplier
		t.company = self.company
		t.amount = amount
		for row in rows:
			t.append("items", row if isinstance(row, dict) else {"card_equipment": row})
		company_paid(t, **(cost or {})).insert(ignore_permissions=True)
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

	def test_forged_assignment_link_is_dropped_on_submit(self):
		# security review 2026-10-19: links sent with the submit itself are cleared
		pa, pb = self._project("A"), self._project("B")
		victim = self._equipment(current_project=pa).name
		victim_assignment = self._assign(victim, pa, 1)
		eq = self._equipment().name
		t = self._trip(pb, 10, [eq])
		t.items[0].previous_assignment = victim_assignment.name
		t.submit()
		t.reload()
		self.assertNotEqual(t.items[0].previous_assignment, victim_assignment.name)
		t.cancel()
		self.assertTrue(frappe.db.exists("Card Equipment Assignment", victim_assignment.name))
		self.assertFalse(frappe.db.get_value("Card Equipment Assignment", victim_assignment.name, "to_date"))

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

	# ---- simplified transport (Owner 2026-10-19) ----
	def test_movement_is_detected(self):
		pa, pb = self._project("A"), self._project("B")
		new, moved = self._equipment().name, self._equipment().name
		self._assign(moved, pa, 1)
		t = self._trip(pb, 10, [new, moved])
		self.assertEqual(
			[(r.movement, r.from_type, r.from_project) for r in t.items],
			# never assigned: recorded as coming from storage (Owner 2026-10-19)
			[("First entry", "Storage", None), ("Transfer", "Project", pa)],
		)

	def _place(self, label):
		loc = frappe.new_doc("Location")
		loc.location_name = "TEST-V3-%s-%s" % (label, self.token)
		loc.insert(ignore_permissions=True)
		return loc.name

	def _move(self, day, equipment, destination, place=None, project=None, submit=True):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"date": self._d(day),
				"company": self.company,
				"destination_type": destination,
				"destination_location": place,
				"project": project,
				"payer": "Equipment Supplier",
				"cost_bearer": "Equipment Supplier",
			}
		)
		t.append("items", {"card_equipment": equipment})
		t.insert(ignore_permissions=True)
		if submit:
			t.submit()
		return t

	def test_workshop_ends_assignment_and_blocks_later_days(self):
		pa = self._project("A")
		eq = self._equipment().name
		a = self._assign(eq, pa, 1)
		shop = self._place("SHOP")
		t = self._move(10, eq, "Workshop", shop)
		row = t.items[0]
		self.assertEqual(
			(t.project, row.movement, row.from_type, row.from_project), (None, "To workshop", "Project", pa)
		)
		self.assertEqual(
			getdate(frappe.db.get_value("Card Equipment Assignment", a.name, "to_date")), getdate(self._d(10))
		)
		self.assertEqual(frappe.db.count("Card Equipment Assignment", {"equipment": eq}), 1)
		self._card(eq, pa, [5]).insert(ignore_permissions=True)  # before the move: fine
		with self.assertRaises(frappe.ValidationError):
			self._card(eq, pa, [12]).insert(ignore_permissions=True)  # after it: refused

	def test_from_place_follows_the_last_move(self):
		pa, pb = self._project("A"), self._project("B")
		eq = self._equipment().name
		self._assign(eq, pa, 1)
		store = self._place("STORE")
		self._move(10, eq, "Storage", store)
		back = self._move(15, eq, "Project", project=pb, submit=False)
		row = back.items[0]
		self.assertEqual((row.from_type, row.from_location, row.movement), ("Storage", store, "Transfer"))
		with self.assertRaises(frappe.ValidationError):
			self._move(16, eq, "Storage", store, submit=False)  # already there

	def test_same_project_is_refused(self):
		pa = self._project("A")
		eq = self._equipment().name
		self._assign(eq, pa, 1)
		with self.assertRaises(frappe.ValidationError):
			self._trip(pa, 10, [eq])

	def test_header_from_is_automatic(self):
		pa, pb = self._project("A"), self._project("B")
		eq = self._equipment().name
		self._assign(eq, pa, 1)
		t = self._trip(pb, 10, [eq])
		self.assertEqual((t.source_type, t.source_project), ("Project", pa))

	def test_only_rented_equipment_returns_to_supplier(self):
		pa = self._project("A")
		eq = self._equipment().name  # owned
		self._assign(eq, pa, 1)
		with self.assertRaises(frappe.ValidationError):
			self._move(10, eq, "Supplier", submit=False)

	def test_only_company_borne_moves_are_billed(self):
		# transports recorded before P1-2 keep the old rule (P1-2 transports are not posted yet)
		from card.gl.posting import _supplier_sources

		p = self._project("S")
		paid = self._trip(p, 5, [self._equipment().name], amount=400, submit=True)
		as_recorded_before_p12(paid.name, "Company")
		theirs = frappe.new_doc("Equipment Transport")
		theirs.update(
			{
				"date": self._d(6),
				"company": self.company,
				"project": p,
				"transport_supplier": self.supplier,
				"amount": 300,
			}
		)
		paid_by(theirs, "Customer", "Customer").insert(ignore_permissions=True)
		theirs.submit()
		as_recorded_before_p12(theirs.name, "Customer")
		_cards, _fills, transports = _supplier_sources(
			self.company, self.supplier, self._d(1), self._d(28), int(self.month_str), int(self.year_str)
		)
		self.assertEqual({t.name for t in transports}, {paid.name})

	# ---- cost goes where the equipment goes (Owner 2026-10-19) ----
	def _leaf_cost_center(self):
		return frappe.db.get_value(
			"Cost Center", {"company": self.company, "is_group": 0, "disabled": 0}, "name"
		)

	def test_cost_center_follows_the_chosen_cost_project(self):
		# P1-2: the cost project is chosen explicitly (here the destination, chosen by the user)
		cc = self._leaf_cost_center()
		p = self._project("CC")
		frappe.db.set_value("Project", p, "cost_center", cc)
		t = self._trip(p, 5, [self._equipment().name], cost={"basis": "Project", "cost_project": p})
		self.assertEqual(t.cost_center, cc)

	def test_workshop_cost_center_comes_from_settings(self):
		cc = self._leaf_cost_center()
		shop = self._place("SHOP")
		eq = self._equipment().name
		self._assign(eq, self._project("A"), 1)

		def paid_move():
			t = frappe.new_doc("Equipment Transport")
			t.update(
				{
					"date": self._d(10),
					"company": self.company,
					"destination_type": "Workshop",
					"destination_location": shop,
					"transport_supplier": self.supplier,
					"amount": 250,
				}
			)
			t.append("items", {"card_equipment": eq})
			return company_paid(t, basis="Workshop or storage").insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			paid_move()  # no cost center for the place yet
		settings = frappe.get_single("Card Settings")
		settings.append(
			"location_cost_centers", {"company": self.company, "location": shop, "cost_center": cc}
		)
		settings.save(ignore_permissions=True)
		t = paid_move()
		self.assertEqual((t.cost_center, t.project), (cc, None))

	# ---- monthly card follows the approved transports (Owner 2026-10-19) ----
	def _strict(self):
		frappe.flags.card_require_assignment = True
		self.addCleanup(setattr, frappe.flags, "card_require_assignment", False)

	def test_card_needs_a_transport(self):
		self._strict()
		eq = self._equipment().name
		with self.assertRaises(frappe.ValidationError):
			self._card(eq, None, [5]).insert(ignore_permissions=True)

	def test_open_assignment_gives_every_month_and_both_shifts(self):
		self._strict()
		p = self._project("Y")
		eq = self._equipment().name
		self._assign(eq, p, 1)  # stays on the project: an open assignment
		day = self._card(eq, None, [5])
		day.insert(ignore_permissions=True)
		night = self._card(eq, None, [5])
		night.shift = "ليلي"
		night.insert(ignore_permissions=True)
		self.assertEqual((day.project, night.project), (p, p))

	def test_moved_during_the_month_one_card_per_project(self):
		from card.card.doctype.card_monthly_card.card_monthly_card import get_card_context

		self._strict()
		pa, pb = self._project("A"), self._project("B")
		eq = self._equipment().name
		self._assign(eq, pa, 1, 15)
		self._assign(eq, pb, 16)
		with self.assertRaises(frappe.ValidationError):
			self._card(eq, None, [5]).insert(ignore_permissions=True)  # which project?
		first = self._card(eq, pa, [5])
		first.insert(ignore_permissions=True)
		second = self._card(eq, pb, [20])  # same month and shift, other project
		second.insert(ignore_permissions=True)
		ctx = get_card_context(eq, self.month_str, self.year_str, pb)
		self.assertEqual((ctx["projects"], ctx["days"][0]), ([pa, pb], self._d(16)))

	def test_unit_context_days_need_every_piece(self):
		# review 2026-10-19: the form offers only the days the card validation accepts
		from card.card.doctype.card_monthly_card.card_monthly_card import get_card_context

		p = self._project("U")
		a, b = self._equipment().name, self._equipment().name
		self._assign(a, p, 1)
		self._assign(b, p, 15)
		unit = self._unit(p, a, b)
		days = get_card_context(unit.name, self.month_str, self.year_str, p)["days"]
		self.assertEqual(days[0], self._d(15))

	# ---- operators: company workers are Employees (Owner 2026-10-19) ----
	def _employee(self):
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "V3 Operator " + self.token,
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		return emp

	def test_owned_and_company_operated_take_an_employee(self):
		self._strict()
		emp = self._employee()
		p = self._project("OP")
		owned = self._equipment().name  # ملك
		managed = self._equipment().name
		# a rented machine run by our workers ("المدارة"): set directly, as the equipment form does
		frappe.db.set_value("Card Equipment", managed, "operator_on", "الشركة")
		for eq in (owned, managed):
			self._assign(eq, p, 1)
			card = self._card(eq, None, [5])
			card.operator = emp.name
			card.operator_name = "typed by hand"
			card.insert(ignore_permissions=True)
			self.assertEqual((card.operator, card.operator_name), (emp.name, emp.employee_name))
