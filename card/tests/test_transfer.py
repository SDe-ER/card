# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Equipment Transport as a location transfer (phase A): assignment open/close,
card-day validation against assignment periods, unit/component handling and
cancel reversal. All data is created per test (unique names) and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from card.tests.test_controllers import _ensure_masters


def _past_month_year():
	today = getdate(nowdate())
	year, month = today.year, today.month - 2
	if month < 1:
		month += 12
		year -= 1
	return "%02d" % month, str(year)


class TestEquipmentTransfer(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.month_str, self.year_str = _past_month_year()
		# transports/cards are period-locked when a lock date is set; make sure it is not
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-TR-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _d(self, day):
		return "%s-%s-%02d" % (self.year_str, self.month_str, day)

	def _project(self, label):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-TR-%s-%s" % (label, self.token)
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, name_prefix="TEST-TR-EQ", **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = kw.pop("ownership", "ملك")  # owned: no supplier needed
		d.equipment_name = "%s-%s" % (name_prefix, frappe.generate_hash(length=6))
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		components = kw.pop("components", None)
		for k, v in kw.items():
			setattr(d, k, v)
		for comp in components or []:
			d.append("components", comp)
		d.insert(ignore_permissions=True)
		return d

	def _assign(self, equipment, project, from_day, to_day=None):
		a = frappe.new_doc("Card Equipment Assignment")
		a.equipment = equipment
		a.project = project
		a.from_date = self._d(from_day)
		if to_day:
			a.to_date = self._d(to_day)
		a.insert(ignore_permissions=True)
		return a

	def _transport(self, equipment, project, day, method=None, submit=True):
		t = frappe.new_doc("Equipment Transport")
		t.equipment = equipment
		t.project = project
		t.date = self._d(day)
		t.transport_supplier = self.supplier
		t.company = self.company
		t.amount = 100
		if method:
			t.transport_method = method
		t.insert(ignore_permissions=True)
		if submit:
			t.submit()
			t.reload()
		return t

	def _card(self, equipment, project, work_days, hours=8):
		d = frappe.new_doc("Card Monthly Card")
		d.equipment = equipment
		d.project = project
		d.shift = "نهاري"
		d.month = self.month_str
		d.year = int(self.year_str)
		for day in work_days:
			d.append("days", {"operation_date": self._d(day), "day_status": "عمل", "working_hours": hours})
		return d

	def _assignments(self, equipment, project):
		return frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": equipment, "project": project},
			fields=["name", "from_date", "to_date"],
		)

	# ---- 1. open/close assignments ----
	def test_transfer_opens_and_closes_assignments(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		a_old = self._assign(eq.name, proj_a, 1)
		t = self._transport(eq.name, proj_b, 10)

		self.assertEqual(
			getdate(frappe.db.get_value("Card Equipment Assignment", a_old.name, "to_date")),
			getdate(self._d(10)),
		)
		new_rows = self._assignments(eq.name, proj_b)
		self.assertEqual(len(new_rows), 1)
		self.assertEqual(getdate(new_rows[0].from_date), getdate(add_days(self._d(10), 1)))
		self.assertFalse(new_rows[0].to_date)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "current_project"), proj_b)
		self.assertEqual(t.previous_assignment, a_old.name)
		self.assertEqual(t.created_assignment, new_rows[0].name)

	# ---- 2. no previous assignment ----
	def test_transfer_no_previous_assignment(self):
		proj_b = self._project("B")
		eq = self._equipment()
		t = self._transport(eq.name, proj_b, 10)

		rows = frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": eq.name},
			fields=["name", "project", "from_date", "to_date"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].project, proj_b)
		self.assertEqual(getdate(rows[0].from_date), getdate(self._d(10)))
		self.assertFalse(rows[0].to_date)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "current_project"), proj_b)
		self.assertFalse(t.previous_assignment)
		self.assertEqual(t.created_assignment, rows[0].name)

	# ---- 3. after a transfer the month's card follows the NEW assignment (F.7) ----
	def test_card_follows_covering_assignment_after_transfer(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		self._assign(eq.name, proj_a, 1)
		self._transport(eq.name, proj_b, 10)

		# v3.0.0: the month overlaps both assignments, so the card is per project; days
		# after the move cannot go on A's card
		with self.assertRaises(frappe.ValidationError):
			self._card(eq.name, proj_a, [11, 12]).insert(ignore_permissions=True)
		card = self._card(eq.name, proj_b, [11, 12])
		card.insert(ignore_permissions=True)
		self.assertEqual(card.project, proj_b)
		# days before the equipment arrived on B are rejected
		with self.assertRaises(frappe.ValidationError):
			self._card(eq.name, proj_b, [5, 12]).insert(ignore_permissions=True)

	# ---- 4. new project: days from D+1 accepted ----
	def test_new_project_day_accepted(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		self._assign(eq.name, proj_a, 1)
		self._transport(eq.name, proj_b, 10)

		card = self._card(eq.name, proj_b, [11, 12])
		card.insert(ignore_permissions=True)
		self.assertTrue(card.name)

	# ---- 5. cancel blocked by a later transfer ----
	def test_cancel_blocked_by_later_transfer(self):
		proj_a, proj_b, proj_c = self._project("A"), self._project("B"), self._project("C")
		eq = self._equipment(current_project=proj_a)
		self._assign(eq.name, proj_a, 1)
		t1 = self._transport(eq.name, proj_b, 10)
		self._transport(eq.name, proj_c, 20)

		with self.assertRaises(frappe.ValidationError):
			t1.cancel()
		t1.reload()
		self.assertEqual(t1.docstatus, 1)

	# ---- 6. cancel blocked by a card day on the new project ----
	def test_cancel_blocked_by_new_project_card_day(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		self._assign(eq.name, proj_a, 1)
		t = self._transport(eq.name, proj_b, 10)
		card = self._card(eq.name, proj_b, [12])
		card.insert(ignore_permissions=True)
		card.submit()

		with self.assertRaises(frappe.ValidationError):
			t.cancel()
		t.reload()
		self.assertEqual(t.docstatus, 1)

	# ---- 6b. a backdated transport never cuts an assignment under submitted card days ----
	def test_backdated_transport_refused_under_submitted_card_days(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		a_old = self._assign(eq.name, proj_a, 1)
		card = self._card(eq.name, proj_a, [12, 15])
		card.insert(ignore_permissions=True)
		card.submit()
		shop = frappe.new_doc("Location")
		shop.location_name = "TEST-TR-SHOP-" + self.token
		shop.insert(ignore_permissions=True)

		for destination in ("Project", "Workshop"):
			t = frappe.new_doc("Equipment Transport")
			t.equipment = eq.name
			t.destination_type = destination
			t.project = proj_b if destination == "Project" else None
			t.destination_location = shop.name if destination == "Workshop" else None
			if destination == "Workshop":
				t.cost_borne_by = "Equipment Supplier"  # no charge, so no cost center needed
			t.date = self._d(10)
			t.transport_supplier = self.supplier
			t.company = self.company
			t.amount = 100
			t.insert(ignore_permissions=True)
			with self.assertRaises(frappe.ValidationError):
				t.submit()
			self.assertFalse(frappe.db.get_value("Card Equipment Assignment", a_old.name, "to_date"))
			self.assertFalse(self._assignments(eq.name, proj_b))

		# a transport after the last card day still moves the machine
		self._transport(eq.name, proj_b, 15)
		self.assertEqual(len(self._assignments(eq.name, proj_b)), 1)

	# ---- 7. clean cancel reverses the transfer ----
	def test_cancel_reverses(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		a_old = self._assign(eq.name, proj_a, 1)
		t = self._transport(eq.name, proj_b, 10)
		created = t.created_assignment
		self.assertTrue(frappe.db.exists("Card Equipment Assignment", created))

		t.cancel()

		self.assertFalse(frappe.db.exists("Card Equipment Assignment", created))
		self.assertFalse(frappe.db.get_value("Card Equipment Assignment", a_old.name, "to_date"))
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "current_project"), proj_a)

	# ---- 8. the project is not user-choosable while an assignment covers the month ----
	def test_project_follows_covering_assignment(self):
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a)
		self._assign(eq.name, proj_a, 1)  # open on A, never assigned to B

		# v3.0.0: a project the equipment was not on is refused (also through the API),
		# so one piece can never carry a card on a project it is not assigned to.
		with self.assertRaises(frappe.ValidationError):
			self._card(eq.name, proj_b, [5, 6]).insert(ignore_permissions=True)
		card = self._card(eq.name, None, [5, 6])
		card.insert(ignore_permissions=True)
		self.assertEqual(card.project, proj_a)  # filled in from the assignment

	# ---- 9. unit component takes no card ----
	def test_unit_component_takes_no_card(self):
		proj_a = self._project("A")
		comp = self._equipment(name_prefix="TEST-TR-COMP", is_unit_component=1)
		with self.assertRaises(frappe.ValidationError):
			self._card(comp.name, proj_a, [5]).insert(ignore_permissions=True)

	# ---- 10. unit split: every component must be on the project that day ----
	def test_unit_split_rejects_in_between_days(self):
		p1, p2 = self._project("P1"), self._project("P2")
		crusher = self._equipment(name_prefix="TEST-TR-CRUSHER", is_unit_component=1)
		generator = self._equipment(name_prefix="TEST-TR-GEN", is_unit_component=1)
		unit = self._equipment(
			name_prefix="TEST-TR-UNIT",
			is_unit=1,
			components=[
				{"component": crusher.name, "role": "crusher"},
				{"component": generator.name, "role": "generator"},
			],
		)
		# crusher leaves P1 after day 10 (arrives P2 day 11); generator leaves P1 after day 12 (arrives P2 day 13)
		self._assign(crusher.name, p1, 1, 10)
		self._assign(crusher.name, p2, 11)
		self._assign(generator.name, p1, 1, 12)
		self._assign(generator.name, p2, 13)

		# P1: day 11 -> crusher already left; the error names the missing component + its dates
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._card(unit.name, p1, [11]).insert(ignore_permissions=True)
		msg = str(ctx.exception)
		self.assertIn("TEST-TR-CRUSHER", msg)  # names the missing component
		self.assertIn(self._d(10), msg)  # ... and its assignment end date on this project
		# P2: day 12 -> generator not yet arrived
		with self.assertRaises(frappe.ValidationError):
			self._card(unit.name, p2, [12]).insert(ignore_permissions=True)

		# P1: day 10 -> both still there
		c1 = self._card(unit.name, p1, [10])
		c1.insert(ignore_permissions=True)
		self.assertTrue(c1.name)
		# one card per equipment/month/shift: drop the first to build the P2 card
		frappe.delete_doc("Card Monthly Card", c1.name, force=1, ignore_permissions=True)

		# P2: day 13 -> both arrived
		c2 = self._card(unit.name, p2, [13])
		c2.insert(ignore_permissions=True)
		self.assertTrue(c2.name)

	# ---- 11. transport method ----
	def test_transport_method_stored(self):
		proj_b = self._project("B")
		eq = self._equipment()
		t = self._transport(eq.name, proj_b, 10, method="Winch")
		self.assertEqual(t.docstatus, 1)
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "transport_method"), "Winch")

	# ---- 12. baseline: equipment with no assignment history is unconstrained ----
	def test_baseline_safe_no_assignments(self):
		proj_a = self._project("A")
		eq = self._equipment()
		self.assertFalse(frappe.db.exists("Card Equipment Assignment", {"equipment": eq.name}))
		card = self._card(eq.name, proj_a, [3, 4, 5], hours=10)
		card.insert(ignore_permissions=True)
		card.submit()
		card.reload()
		self.assertEqual(card.docstatus, 1)

	# ---- v1.2.2 A4: assignments are protected and validated ----
	def test_transfer_writes_are_in_the_assignment_history(self):
		eq = self._equipment()
		p1, p2 = self._project("H1"), self._project("H2")
		first = self._assign(eq.name, p1, 1)
		self._transport(eq.name, p2, 10)
		self.assertEqual(
			str(frappe.db.get_value("Card Equipment Assignment", first.name, "to_date")), self._d(10)
		)
		self.assertTrue(
			frappe.get_all(
				"Version", filters={"ref_doctype": "Card Equipment Assignment", "docname": first.name}
			)
		)

	def test_overlapping_assignment_is_refused(self):
		eq = self._equipment()
		p1, p2 = self._project("O1"), self._project("O2")
		self._assign(eq.name, p1, 1, 15)
		with self.assertRaises(frappe.ValidationError):
			self._assign(eq.name, p2, 10)
		self._assign(eq.name, p2, 16)  # adjacent, no overlap

	def test_assignment_dates_and_company_are_checked(self):
		eq = self._equipment()
		p1 = self._project("D1")
		with self.assertRaises(frappe.ValidationError):
			self._assign(eq.name, p1, 10, 5)
		other = "TEST-TR-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": other,
				"abbr": "T" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = other
		co.db_insert()
		foreign = frappe.new_doc("Project")
		foreign.project_name = "TEST-TR-FOREIGN-" + self.token
		foreign.company = other
		foreign.db_insert()
		with self.assertRaises(frappe.ValidationError):
			self._assign(eq.name, foreign.name, 1)

	def test_card_user_cannot_write_assignments(self):
		email = f"tr-cu-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Transfer",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		try:
			frappe.set_user(email)
			self.assertTrue(frappe.has_permission("Card Equipment Assignment", "read"))
			self.assertFalse(frappe.has_permission("Card Equipment Assignment", "write"))
			self.assertFalse(frappe.has_permission("Card Equipment Assignment", "create"))
		finally:
			frappe.set_user("Administrator")

	def test_card_user_cannot_regain_write_by_sharing(self):
		"""security review MEDIUM-3: sharing must not hand out what the role lacks"""
		from frappe.share import add as share_add

		eq = self._equipment()
		a = self._assign(eq.name, self._project("SH"), 1)
		email = f"tr-sh-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Share",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		try:
			frappe.set_user(email)
			with self.assertRaises(frappe.PermissionError):
				share_add("Card Equipment Assignment", a.name, email, write=1)
		finally:
			frappe.set_user("Administrator")

	def test_transfer_closes_a_legacy_overlapping_assignment(self):
		"""security review LOW-2: shortening a period never re-checks overlap, so
		legacy overlapping rows do not block a transfer"""
		eq = self._equipment()
		p1, p2, p3 = self._project("L1"), self._project("L2"), self._project("L3")
		first = self._assign(eq.name, p1, 1)
		legacy = frappe.new_doc("Card Equipment Assignment")
		legacy.update({"equipment": eq.name, "project": p2, "from_date": self._d(3), "to_date": self._d(6)})
		legacy.db_insert()  # pre-1.2.2 data: overlaps `first`
		self._transport(eq.name, p3, 12)
		self.assertEqual(
			str(frappe.db.get_value("Card Equipment Assignment", first.name, "to_date")), self._d(12)
		)
