# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-0 (integration plan 2026-10-30; Owner decision 2026-10-30): CARD posting lines carry the
project/equipment cost allocation — the equipment's assignment to the line's project, then the
project's cost center; never the company default or the equipment's own (asset) cost center for
project work. A transport follows its verified cost bearer, not the destination project by
default. An allocation that cannot be determined reliably (no project cost center, different
cost centers in one period, a set but unusable cost center, a move between two projects, or no
recorded payer) refuses the build for review."""

import frappe
from frappe.utils import flt

from card.gl.posting import build_monthly_posting
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_s3_posting import _PostingBase
from card.tests.transport_parties import as_recorded_before_p12, company_paid, paid_by


class TestCostAllocation(_PostingBase):
	def _cc(self, suffix, is_group=0):
		parent = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 1}, "name")
		doc = frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": f"P1-{suffix}-{self.token}",
				"parent_cost_center": parent,
				"company": self.company,
				"is_group": is_group,
			}
		).insert(ignore_permissions=True)
		return doc.name

	def _assign(self, eq, cost_center, from_date="2026-09-01", to_date=None, project=None):
		return frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": eq.name,
				"project": project or self.project,
				"from_date": from_date,
				"to_date": to_date,
				"cost_center": cost_center,
			}
		).insert(ignore_permissions=True)

	def _set_project_cc(self, cc):
		frappe.db.set_value("Project", self.project, "cost_center", cc)

	def _pi(self):
		return frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)

	def test_assignment_cost_center_wins(self):
		eq = self._equipment()
		assigned, project_cc = self._cc("ASSIGN"), self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._assign(eq, assigned)
		self._card(eq, [8], submit=True)
		pi = self._pi()
		self.assertEqual({i.cost_center for i in pi.items}, {assigned})

	def test_adjustment_lines_carry_the_same_cost_center(self):
		eq = self._equipment()
		assigned = self._cc("ASSIGN")
		self._assign(eq, assigned)
		self._card(
			eq,
			[8],
			adjustments=[{"adjustment_type_ref": "Mobilization", "description": "m", "amount": 100}],
			submit=True,
		)
		pi = self._pi()
		self.assertEqual(len(pi.items), 2)
		self.assertEqual({i.cost_center for i in pi.items}, {assigned})

	def test_project_cost_center_without_an_assignment_cost_center(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_equipment_cost_center_without_a_project_cost_center_is_an_exception(self):
		eq = self._equipment(cost_center=self._cc("EQ"))
		self._set_project_cc(None)
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "has no cost center"):
			self._pi()

	def test_project_without_any_cost_center_is_an_exception(self):
		# Owner decision 2026-10-30: the company default is never used for project work
		eq = self._equipment()
		self._set_project_cc(None)
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "has no cost center"):
			self._pi()

	def test_two_assignment_cost_centers_in_the_period_are_an_exception(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		self._assign(eq, self._cc("A1"), "2026-09-01", "2026-09-10")
		self._assign(eq, self._cc("A2"), "2026-09-11")
		self._card(eq, [8] * 12, submit=True)  # worked days 1-12 cover both assignments
		with self.assertRaisesRegex(frappe.ValidationError, "resolve to different cost centers"):
			self._pi()
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))

	def test_two_assignments_with_the_same_cost_center_are_one_allocation(self):
		eq = self._equipment()
		cc = self._cc("SAME")
		self._assign(eq, cc, "2026-09-01", "2026-09-10")
		self._assign(eq, cc, "2026-09-11")
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, cc)

	def test_assignment_without_cost_center_falls_back_to_the_project(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._assign(eq, None)
		self._card(eq, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_a_set_but_unusable_cost_center_is_an_exception_not_a_fallback(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("GROUP", is_group=1))
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot carry a posting"):
			self._pi()

	def test_a_disabled_assignment_cost_center_is_an_exception(self):
		eq = self._equipment()
		cc = self._cc("OFF")
		self._assign(eq, cc)
		frappe.db.set_value("Cost Center", cc, "disabled", 1)
		self._card(eq, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "cannot carry a posting"):
			self._pi()

	def test_assignment_with_and_without_cost_center_in_one_card_is_an_exception(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		self._assign(eq, self._cc("X"), "2026-09-01", "2026-09-05")
		self._assign(eq, None, "2026-09-06")
		self._card(eq, [8, 8, 8, 8, 8, 8, 8], submit=True)  # days 1-7 cover both assignments
		with self.assertRaisesRegex(frappe.ValidationError, "resolve to different cost centers"):
			self._pi()

	def test_assignment_without_cost_center_agreeing_with_the_project_is_one_allocation(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._assign(eq, project_cc, "2026-09-01", "2026-09-05")
		self._assign(eq, None, "2026-09-06")
		self._card(eq, [8, 8, 8, 8, 8, 8, 8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_an_assignment_on_non_working_days_only_is_not_a_conflict(self):
		eq = self._equipment()
		cc = self._cc("WORK")
		self._assign(eq, cc, "2026-09-01", "2026-09-05")
		self._assign(eq, self._cc("IDLE"), "2026-09-20")
		self._card(eq, [8, 8], submit=True)  # worked on the 1st and 2nd only
		self.assertEqual(self._pi().items[0].cost_center, cc)

	def _unit(self, *components):
		unit = frappe.new_doc("Card Equipment")
		unit.update(
			{
				"company": self.company,
				"equipment_type": self._m["etype"],
				"ownership": "إيجار",
				"equipment_name": "TEST-P1-UNIT-" + frappe.generate_hash(length=6),
				"rate_type": "باليوم",
				"rate": 750,
				"daily_hours": 10,
				"supplier": self.supplier,
				"is_unit": 1,
			}
		)
		for c in components:
			unit.append("components", {"component": c.name, "role": "R"})
		unit.insert(ignore_permissions=True)
		return unit

	def test_unit_without_its_own_assignment_uses_its_components(self):
		c1, c2 = self._equipment(), self._equipment()
		cc = self._cc("UNIT")
		self._assign(c1, cc)
		self._assign(c2, cc)
		unit = self._unit(c1, c2)
		self._card(unit, [8], submit=True)
		self.assertEqual(self._pi().items[0].cost_center, cc)

	def test_unit_components_on_different_cost_centers_are_an_exception(self):
		c1, c2 = self._equipment(), self._equipment()
		self._assign(c1, self._cc("U1"))
		self._assign(c2, self._cc("U2"))
		unit = self._unit(c1, c2)
		self._card(unit, [8], submit=True)
		with self.assertRaisesRegex(frappe.ValidationError, "resolve to different cost centers"):
			self._pi()

	def test_diesel_of_an_equipment_follows_its_assignment_cost_center(self):
		eq = self._equipment()
		assigned = self._cc("ASSIGN")
		self._set_project_cc(self._cc("PROJ"))
		self._assign(eq, assigned)
		self._card(eq, [8], submit=True)
		fill = self._fill(card_equipment=eq.name)
		pi = self._pi()
		self.assertEqual({i.cost_center for i in pi.items}, {assigned})
		self.assertTrue(any(fill.name in i.description for i in pi.items))

	def test_equipment_on_two_projects_in_one_month_splits_by_project(self):
		eq = self._equipment()
		other = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-P1-PRJ-B-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		cc_a, cc_b = self._cc("PA"), self._cc("PB")
		self._assign(eq, cc_a, "2026-09-01", "2026-09-15")
		self._assign(eq, cc_b, "2026-09-16", None, project=other.name)
		card_a = self._card(eq, [8, 8], submit=True)  # 1-2 Sep on project A: 1,200
		card_b = frappe.new_doc("Card Monthly Card")
		card_b.update(
			{"equipment": eq.name, "project": other.name, "shift": "نهاري", "month": "09", "year": 2026}
		)
		card_b.append(
			"days", {"operation_date": "2026-09-20", "day_status": "عمل", "working_hours": 4}
		)  # 300
		card_b.insert(ignore_permissions=True)
		card_b.submit()
		pi = self._pi()
		by_card = {}
		for item in pi.items:
			for card in (card_a, card_b):
				if card.name in item.description:
					by_card[card.name] = (
						item.project,
						item.cost_center,
						item.card_equipment,
						flt(item.rate, 2),
					)
		self.assertEqual(by_card[card_a.name], (self.project, cc_a, eq.name, 1200.0))
		self.assertEqual(by_card[card_b.name], (other.name, cc_b, eq.name, 300.0))

	def test_every_line_carries_project_cost_center_and_equipment(self):
		eq = self._equipment()
		cc = self._cc("ALL")
		self._assign(eq, cc)
		self._set_project_cc(self._cc("PROJ"))
		self._card(eq, [8], submit=True)
		self._fill(card_equipment=eq.name)  # direct fill
		pi = self._pi()
		for item in pi.items:
			self.assertEqual(item.project, self.project, item.description)
			self.assertTrue(item.cost_center, item.description)
			self.assertEqual(item.card_equipment, eq.name, item.description)

	def test_fill_keeps_its_equipment_when_it_takes_the_project_cost_center(self):
		eq = self._equipment()
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		self._fill(card_equipment=eq.name)
		item = self._pi().items[0]
		self.assertEqual(
			(item.cost_center, item.card_equipment, item.project), (project_cc, eq.name, self.project)
		)

	def test_signature_protects_the_allocated_cost_center(self):
		from card.gl.integrity import accept_correction

		eq = self._equipment()
		self._assign(eq, self._cc("ASSIGN"))
		self._card(eq, [8], submit=True)
		pi = self._pi()
		other = self._cc("OTHER")
		pi.items[0].cost_center = other
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "differs from what CARD built"):
			pi.submit()
		pi.reload()
		pi.items[0].project = None
		pi.items[0].cost_center = other
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "Only cost center and account changes"):
			accept_correction("Purchase Invoice", pi.name, "try")

	def _fill(self, **kw):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
				**kw,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		return fill

	def test_fill_with_an_unusable_project_cost_center_is_an_exception(self):
		self._set_project_cc(self._cc("GROUP", is_group=1))
		self._fill()
		with self.assertRaisesRegex(frappe.ValidationError, "cannot carry a posting"):
			self._pi()

	def test_fill_without_its_own_cost_center_takes_the_project_cost_center(self):
		project_cc = self._cc("PROJ")
		self._set_project_cc(project_cc)
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		self.assertEqual(self._pi().items[0].cost_center, project_cc)

	def test_gl_carries_the_allocated_cost_center_and_signature_holds(self):
		eq = self._equipment()
		assigned = self._cc("ASSIGN")
		self._assign(eq, assigned)
		self._card(eq, [8], submit=True)
		pi = self._pi()
		pi.submit()
		rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_no": pi.name, "is_cancelled": 0, "account": self.exp_rental},
			fields=["cost_center", "project", "card_equipment"],
		)
		self.assertEqual(
			[(r.cost_center, r.project, r.card_equipment) for r in rows], [(assigned, self.project, eq.name)]
		)

	def test_tank_fill_share_follows_the_assignment_of_the_days_worked(self):
		eq = self._equipment()
		assigned = self._cc("ASSIGN")
		self._set_project_cc(self._cc("PROJ"))
		self._assign(eq, assigned, "2026-09-01", "2026-09-10")
		self._card(eq, [8, 8], submit=True)  # worked 1-2 Sep on the project
		fill = self._fill(date="2026-09-20")  # tank fill, no equipment, after the assignment ended
		pi = self._pi()
		share = [i for i in pi.items if fill.name in i.description]
		self.assertTrue(share)
		self.assertEqual({(i.cost_center, i.card_equipment) for i in share}, {(assigned, eq.name)})

	# ---- transport follows its explicitly verified cost bearer (Owner decisions 2026-10-30) ----
	def _transport(self, eq, destination="Project", project=None, place=None, bearer="Company"):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"date": "2026-09-10",
				"company": self.company,
				"transport_supplier": self.supplier,
				"destination_type": destination,
				"destination_location": place,
				"project": project if destination == "Project" else None,
				"amount": 400,
			}
		)
		t.append("items", {"card_equipment": eq.name})
		if bearer != "Company":
			paid_by(t, bearer, bearer)
		elif destination in ("Workshop", "Storage"):
			company_paid(t, basis="Workshop or storage")
		else:
			company_paid(t)
		t.insert(ignore_permissions=True)
		t.submit()
		# these tests cover the P1-0 rules of transports recorded before P1-2 (P1-2 ones are not posted yet)
		as_recorded_before_p12(t.name, bearer)
		return t

	def _shop(self, cost_center):
		loc = frappe.new_doc("Location")
		loc.location_name = "TEST-P1-SHOP-" + self.token
		loc.insert(ignore_permissions=True)
		settings = frappe.get_single("Card Settings")
		settings.append(
			"location_cost_centers",
			{"company": self.company, "location": loc.name, "cost_center": cost_center},
		)
		settings.save(ignore_permissions=True)
		return loc.name

	def _assert_refused(self, t, pattern):
		with self.assertRaisesRegex(frappe.ValidationError, pattern):
			self._pi()
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))
		# the transport record is kept as it is: still submitted, not linked to any invoice
		kept = frappe.db.get_value(
			"Equipment Transport", t.name, ["docstatus", "purchase_invoice"], as_dict=True
		)
		self.assertEqual(kept.docstatus, 1)
		self.assertFalse(kept.purchase_invoice)

	def _other_project(self):
		other = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-P1-PRJ-SRC-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Project", other.name, "cost_center", self._cc("SRC"))
		return other.name

	# positive
	def test_workshop_move_paid_by_the_company_takes_the_configured_place_cost_center(self):
		eq = self._equipment(cost_center=self._cc("ASSET"))
		shop_cc = self._cc("SHOP")
		place = self._shop(shop_cc)
		self._assign(eq, self._cc("ASSIGN"), "2026-09-01")
		t = self._transport(eq, destination="Workshop", place=place)
		line = next(i for i in self._pi().items if t.name in i.description)
		self.assertEqual((line.cost_center, line.card_equipment), (shop_cc, eq.name))

	def test_move_paid_by_the_equipment_supplier_is_not_billed(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		self._card(eq, [8], submit=True)
		t = self._transport(eq, project=self.project, bearer="Equipment Supplier")
		pi = self._pi()
		self.assertFalse([i for i in pi.items if t.name in i.description])
		self.assertFalse(frappe.db.get_value("Equipment Transport", t.name, "purchase_invoice"))

	def test_move_paid_by_the_customer_is_not_billed_to_the_company(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		self._card(eq, [8], submit=True)
		t = self._transport(eq, project=self.project, bearer="Customer")
		pi = self._pi()
		self.assertFalse([i for i in pi.items if t.name in i.description])
		self.assertFalse(frappe.db.get_value("Equipment Transport", t.name, "purchase_invoice"))

	# negative
	def test_company_paid_move_is_not_charged_to_the_destination_project(self):
		eq = self._equipment(cost_center=self._cc("ASSET"))
		self._set_project_cc(self._cc("DST"))
		t = self._transport(eq, project=self.project)
		self._assert_refused(t, "which project bears this move is not recorded")

	def test_return_to_the_supplier_is_not_charged_to_the_source_project(self):
		eq = self._equipment()
		self._assign(eq, self._cc("LEFT"), "2026-09-01")
		t = self._transport(eq, destination="Supplier")
		self.assertEqual(t.project, self.project)  # the project it leaves, kept for the record only
		self._assert_refused(t, "which project bears this move is not recorded")

	def test_move_between_two_projects_is_charged_to_neither(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("DST"))
		self._assign(eq, None, "2026-09-01", project=self._other_project())
		t = self._transport(eq, project=self.project)
		self.assertTrue(t.items[0].from_project)
		self._assert_refused(t, "which project bears this move is not recorded")

	def test_move_with_no_recorded_payer_is_an_exception(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		t = self._transport(eq, project=self.project)
		frappe.db.set_value("Equipment Transport", t.name, "cost_borne_by", "")
		self._assert_refused(t, "who pays this move is not recorded")

	def test_move_with_a_null_payer_is_an_exception_not_skipped(self):
		# a historical row may hold NULL, not "": it must be refused, never left out silently
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		t = self._transport(eq, project=self.project)
		frappe.db.sql("update `tabEquipment Transport` set cost_borne_by = NULL where name = %s", t.name)
		self.assertIsNone(frappe.db.get_value("Equipment Transport", t.name, "cost_borne_by"))
		self._assert_refused(t, "who pays this move is not recorded")

	def test_historical_move_without_origin_is_reported_and_kept(self):
		eq = self._equipment()
		self._set_project_cc(self._cc("PROJ"))
		t = self._transport(eq, project=self.project)
		frappe.db.set_value(
			"Equipment Transport Item", t.items[0].name, {"from_type": "", "from_project": None}
		)
		frappe.db.set_value("Equipment Transport", t.name, {"source_type": "", "source_project": None})
		self._assert_refused(t, "origin not recorded")
		self.assertEqual(frappe.db.get_value("Equipment Transport Item", t.items[0].name, "from_type"), "")

	def test_workshop_move_without_a_place_cost_center_is_an_exception(self):
		eq = self._equipment(cost_center=self._cc("ASSET"))
		place = self._shop(self._cc("SHOP"))
		t = self._transport(eq, destination="Workshop", place=place)
		frappe.db.set_value("Equipment Transport", t.name, "cost_center", None)
		self._assert_refused(t, "has no cost center for its place")

	def test_workshop_move_whose_place_cost_center_changed_is_an_exception(self):
		eq = self._equipment()
		place = self._shop(self._cc("SHOP"))
		t = self._transport(eq, destination="Workshop", place=place)
		settings = frappe.get_single("Card Settings")
		next(r for r in settings.location_cost_centers if r.location == place).cost_center = self._cc("NEW")
		settings.save(ignore_permissions=True)
		self._assert_refused(t, "not the one now configured")

	def test_workshop_move_with_a_disabled_place_cost_center_is_an_exception(self):
		eq = self._equipment()
		shop_cc = self._cc("SHOP")
		place = self._shop(shop_cc)
		t = self._transport(eq, destination="Workshop", place=place)
		frappe.db.set_value("Cost Center", shop_cc, "disabled", 1)
		self._assert_refused(t, "cannot be used for company")
