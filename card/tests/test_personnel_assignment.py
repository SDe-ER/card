# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""R1 (CARD 4.5.0): Card Personnel Assignment, day resolution Employee → Equipment →
Project → Cost Center, equipment-assignment fixes and the per-company period lock."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from card.personnel import employee_days, resolve_day
from card.tests import test_asset_link as _link
from card.tests.test_controllers import _ensure_masters

PA = "Card Personnel Assignment"
EA = "Card Equipment Assignment"


class TestPersonnelAssignment(IntegrationTestCase):
	_user = _link.TestAssetLink._user
	_as = _link.TestAssetLink._as
	_make_equipment = _link.TestAssetLink._make_equipment
	_other_company = _link.TestAssetLink._other_company

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.company = self._m["company"]
		self.cc = self._leaf_cost_center(self.company)
		self.project = self._project(self.cc)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- helpers ----------

	def _leaf_cost_center(self, company):
		cc = frappe.db.get_value("Cost Center", {"company": company, "is_group": 0, "disabled": 0}, "name")
		if cc:
			return cc
		parent = frappe.db.get_value("Cost Center", {"company": company, "is_group": 1}, "name")
		return (
			frappe.get_doc(
				{
					"doctype": "Cost Center",
					"cost_center_name": "TEST-CC-" + frappe.generate_hash(length=5),
					"parent_cost_center": parent,
					"company": company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _project(self, cost_center, company=None):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-PRJ-" + frappe.generate_hash(length=6),
					"company": company or self.company,
					"cost_center": cost_center,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _employee(self, company=None, **kw):
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": "R1 " + frappe.generate_hash(length=6),
					"gender": "Male",
					"date_of_birth": "1990-01-01",
					"date_of_joining": kw.pop("date_of_joining", "2020-01-01"),
					"company": company or self.company,
					"status": "Active",
					**kw,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _ea(self, equipment, project, start, end=None, **kw):
		return frappe.get_doc(
			{
				"doctype": EA,
				"equipment": equipment,
				"project": project,
				"from_date": start,
				"to_date": end,
				**kw,
			}
		).insert(ignore_permissions=True)

	def _pa(self, employee, submit=True, **kw):
		doc = frappe.get_doc({"doctype": PA, "employee": employee, **kw})
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()  # Administrator: System Manager may submit own rows
		return doc

	# ---------- assignment ----------

	def test_equipment_assignment_resolves_the_project_day_by_day(self):
		eq = self._make_equipment()
		other_project = self._project(self.cc)
		self._ea(eq.name, self.project, "2026-01-01", "2026-01-15")
		self._ea(eq.name, other_project, "2026-01-16")
		emp = self._employee()
		self._pa(emp, assignment_type="Equipment", card_equipment=eq.name, from_date="2026-01-01")
		self.assertEqual(resolve_day(emp, "2026-01-10")[0].project, self.project)
		self.assertEqual(resolve_day(emp, "2026-01-20")[0].project, other_project)
		self.assertEqual(resolve_day(emp, "2026-01-20")[0].cost_center, self.cc)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "operator"), emp)

	def test_days_without_assignment_or_equipment_project_need_review(self):
		eq = self._make_equipment()
		emp = self._employee()
		self._pa(emp, assignment_type="Equipment", card_equipment=eq.name, from_date="2026-02-01")
		days = {d["date"]: d for d in employee_days(emp, "2026-01-31", "2026-02-02")}
		self.assertTrue(days["2026-01-31"]["issue"])  # no assignment
		self.assertTrue(days["2026-02-01"]["entries"][0].issue)  # equipment on no project

	def test_shares_of_one_day_cannot_exceed_100(self):
		emp = self._employee()
		p2 = self._project(self.cc)
		self._pa(
			emp, assignment_type="Project", project=self.project, from_date="2026-03-01", share_percent=60
		)
		self._pa(emp, assignment_type="Project", project=p2, from_date="2026-03-10", share_percent=40)
		with self.assertRaisesRegex(frappe.ValidationError, "at most 100"):
			self._pa(
				emp,
				assignment_type="Project",
				project=p2,
				from_date="2026-03-20",
				to_date="2026-03-25",
				share_percent=10,
			)
		# a later, non-overlapping period is fine once the first is closed
		first = frappe.get_all(PA, filters={"employee": emp, "share_percent": 60}, pluck="name")[0]
		doc = frappe.get_doc(PA, first)
		doc.to_date = "2026-03-31"
		doc.save(ignore_permissions=True)
		self._pa(emp, assignment_type="Project", project=p2, from_date="2026-04-01", share_percent=60)

	def test_only_the_end_date_changes_after_submit(self):
		emp = self._employee()
		doc = self._pa(emp, assignment_type="Project", project=self.project, from_date="2026-05-01")
		doc.reload()
		doc.from_date = "2026-04-01"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		doc.reload()
		doc.to_date = "2026-05-31"
		doc.save(ignore_permissions=True)
		self.assertEqual(str(frappe.db.get_value(PA, doc.name, "to_date")), "2026-05-31")

	def test_company_dates_and_target_are_validated(self):
		other = self._other_company()
		emp = self._employee()
		foreign_eq = self._make_equipment(company=other)
		with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
			self._pa(
				emp,
				submit=False,
				assignment_type="Equipment",
				card_equipment=foreign_eq.name,
				from_date="2026-01-01",
			)
		late = self._employee(date_of_joining="2026-06-01")
		with self.assertRaisesRegex(frappe.ValidationError, "joining date"):
			self._pa(
				late, submit=False, assignment_type="Project", project=self.project, from_date="2026-05-01"
			)
		with self.assertRaisesRegex(frappe.ValidationError, "share"):
			self._pa(
				emp,
				submit=False,
				assignment_type="Project",
				project=self.project,
				from_date="2026-01-01",
				share_percent=0,
			)

	def test_creator_cannot_submit_and_card_user_cannot_create(self):
		emp = self._employee()
		manager = self._user(["Card Manager"])
		frappe.set_user(manager)
		doc = frappe.get_doc(
			{
				"doctype": PA,
				"employee": emp,
				"assignment_type": "Project",
				"project": self.project,
				"from_date": "2026-01-01",
			}
		).insert()
		with self.assertRaises(frappe.PermissionError):
			doc.submit()
		self._as(["Card User"])
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{
					"doctype": PA,
					"employee": emp,
					"assignment_type": "Project",
					"project": self.project,
					"from_date": "2026-01-01",
				}
			).insert()

	def test_restricted_user_cannot_see_another_companys_assignment(self):
		other = self._other_company()
		project = self._project(None, company=other)  # the test company has no cost centers
		emp = self._employee(company=other)
		doc = self._pa(emp, assignment_type="Project", project=project, from_date="2026-01-01")
		self._as(["Card Manager"], restrict=self.company)
		self.assertFalse(frappe.has_permission(PA, "read", doc.name))
		self.assertNotIn(doc.name, frappe.get_list(PA, pluck="name"))
		with self.assertRaises(frappe.PermissionError):
			employee_days(emp, "2026-01-01", "2026-01-05")

	# ---------- equipment assignment fixes ----------

	def test_equipment_assignment_needs_a_start_and_gets_company_and_cost_center(self):
		eq = self._make_equipment()
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": EA, "equipment": eq.name, "project": self.project}).insert(
				ignore_permissions=True
			)
		row = self._ea(eq.name, self.project, "2026-01-01")
		self.assertEqual((row.company, row.cost_center), (self.company, self.cc))

	# ---------- period lock per company ----------

	def test_company_period_lock_covers_assignments(self):
		settings = frappe.get_single("Card Settings")
		row = next((r for r in settings.company_settings if r.company == self.company), None)
		if not row:
			row = settings.append("company_settings", {"company": self.company})
		row.period_lock_date = "2026-01-31"
		settings.save(ignore_permissions=True)
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "locked"):
			self._ea(eq.name, self.project, "2026-01-15")
		ea = self._ea(eq.name, self.project, "2026-02-01")
		emp = self._employee()
		with self.assertRaisesRegex(frappe.ValidationError, "locked"):
			self._pa(emp, assignment_type="Project", project=self.project, from_date="2026-01-20")
		pa = self._pa(emp, assignment_type="Project", project=self.project, from_date="2026-02-01")
		pa.reload()
		pa.to_date = "2026-02-28"
		pa.save(ignore_permissions=True)  # changes days after the lock: allowed
		ea.reload()
		ea.from_date = "2026-01-20"
		with self.assertRaisesRegex(frappe.ValidationError, "locked"):
			ea.save(ignore_permissions=True)

	def test_seed_from_the_legacy_employee_project_is_a_dry_run_first(self):
		from card.personnel import seed_from_employee_project

		out = seed_from_employee_project(today(), dry_run=1)
		self.assertEqual(out["created"], [])
		self.assertEqual(out["dry_run"], 1)
		self._as(["Card Manager"])
		with self.assertRaises(frappe.PermissionError):
			seed_from_employee_project(today(), dry_run=1)

	def test_transport_gives_the_new_assignment_a_cost_center(self):
		from card.transfer import apply_transfer

		eq = self._make_equipment()
		self._ea(eq.name, self.project, add_days(getdate(today()), -30))
		target = self._project(self.cc)
		txn = frappe._dict(date=today(), project=target, destination_type="Project", items=[])
		row = frappe._dict(card_equipment=eq.name, idx=2, db_set=lambda *a, **k: None)
		txn.items = [row]
		txn.db_set = lambda *a, **k: None
		apply_transfer(txn)
		new = frappe.get_all(EA, filters={"equipment": eq.name, "project": target}, fields=["cost_center"])
		self.assertEqual(new[0].cost_center, self.cc)

	# ---------- review fixes ----------

	def _company_lock(self, day):
		settings = frappe.get_single("Card Settings")
		row = next((r for r in settings.company_settings if r.company == self.company), None)
		if not row:
			row = settings.append("company_settings", {"company": self.company})
		row.period_lock_date = day
		settings.save(ignore_permissions=True)

	def test_closing_an_old_row_without_cost_center_is_not_blocked_by_the_lock(self):
		eq = self._make_equipment()
		row = self._ea(eq.name, self.project, "2026-01-01")
		frappe.db.set_value(EA, row.name, "cost_center", None)  # a row made before R1
		self._company_lock("2026-01-31")
		row = frappe.get_doc(EA, row.name)
		row.to_date = "2026-03-15"  # what a transport does
		row.save(ignore_permissions=True)
		self.assertEqual(str(frappe.db.get_value(EA, row.name, "to_date")), "2026-03-15")

	def test_operator_is_cleared_when_its_assignment_is_cancelled(self):
		eq = self._make_equipment()
		emp = self._employee()
		doc = self._pa(emp, assignment_type="Equipment", card_equipment=eq.name, from_date="2026-01-01")
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "operator"), emp)
		doc.cancel()
		self.assertFalse(frappe.db.get_value("Card Equipment", eq.name, "operator"))

	def test_only_a_card_manager_changes_a_submitted_assignment(self):
		emp = self._employee()
		doc = self._pa(emp, assignment_type="Project", project=self.project, from_date="2026-05-01")
		self._as(["Card Supervisor"])
		doc = frappe.get_doc(PA, doc.name)
		doc.to_date = "2026-05-02"
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)

	def test_seed_dry_run_fails_closed(self):
		from card.personnel import seed_from_employee_project

		self.assertEqual(seed_from_employee_project(today(), dry_run="true")["dry_run"], 1)

	def test_history_stays_with_the_company_it_was_made_in(self):
		other = self._other_company()
		emp = self._employee()
		doc = self._pa(emp, assignment_type="Project", project=self.project, from_date="2026-01-01")
		frappe.db.set_value("Employee", emp, "company", other)  # the employee moved
		self._as(["Card Manager"], restrict=self.company)
		self.assertTrue(frappe.has_permission(PA, "read", doc.name))
		self.assertIn(doc.name, frappe.get_list(PA, pluck="name"))

	def test_back_to_back_full_assignments_are_allowed(self):
		emp = self._employee()
		p2 = self._project(self.cc)
		self._pa(
			emp, assignment_type="Project", project=self.project, from_date="2026-06-01", to_date="2026-06-15"
		)
		self._pa(emp, assignment_type="Project", project=p2, from_date="2026-06-16")
		self.assertEqual(resolve_day(emp, "2026-06-16")[0].project, p2)
