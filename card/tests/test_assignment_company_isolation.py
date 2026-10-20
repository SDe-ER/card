# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""P0 company isolation of Card Equipment Assignment (Owner 2026-10-20, defect D1 of
QA-Evidence 2026-10-20-card-p0-tests). An assignment has no Company field, so a
Company User Permission never reached it: users of company A listed, read and found
company-B assignments, and a Card Manager of A created and changed them. The first
five tests are the proofs that failed on main (S2, S4, S6, S7, S8); the rest guard the
authorised paths (unrestricted managers, administrators, transports, standard Project
User Permissions). No role is widened; the second company row is inserted raw;
everything is rolled back."""

import frappe
from frappe.client import get as rest_get
from frappe.client import insert as rest_insert
from frappe.client import save as rest_save
from frappe.desk.search import search_link
from frappe.tests import IntegrationTestCase

from card.tests.test_controllers import _ensure_masters
from card.tests.test_transfer import _past_month_year

DOCTYPE = "Card Equipment Assignment"
REFUSED = (frappe.PermissionError, frappe.ValidationError)


class TestAssignmentCompanyIsolation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.month_str, self.year_str = _past_month_year()
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.other = self._other_company()
		self.proj_a = self._project("A", self.company)
		self.proj_b = self._project("B", self.other)
		self.eq_a = self._equipment("A", self.company)
		self.eq_b = self._equipment("B", self.other)
		self.asg_a = self._assign(self.eq_a, self.proj_a)
		self.asg_b = self._assign(self.eq_b, self.proj_b)

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures (Administrator, rolled back) ----------

	def _d(self, day):
		return "%s-%s-%02d" % (self.year_str, self.month_str, day)

	def _other_company(self):
		name = "TEST-ASGISO-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "G" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _project(self, suffix, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-ASGISO-PRJ-%s-%s" % (suffix, self.token)
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, suffix, company):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-ASGISO-EQ-%s-%s" % (suffix, self.token)
		eq.ownership = "ملك"  # owned: no supplier needed
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _assign(self, equipment, project, from_day=1):
		a = frappe.new_doc(DOCTYPE)
		a.equipment = equipment
		a.project = project
		a.from_date = self._d(from_day)
		a.insert(ignore_permissions=True)
		return a.name

	def _row(self, equipment, project, from_day=1):
		return {
			"doctype": DOCTYPE,
			"equipment": equipment,
			"project": project,
			"from_date": self._d(from_day),
		}

	def _user(self, roles, restrict=None, allow="Company", applicable_for=None):
		email = f"asgiso-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Assignment Isolation",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": allow,
					"for_value": restrict,
					"apply_to_all_doctypes": 0 if applicable_for else 1,
					"applicable_for": applicable_for,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _as(self, roles, **kw):
		frappe.set_user(self._user(roles, **kw))

	def _refused(self, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
		except REFUSED:
			return True
		finally:
			frappe.clear_messages()
		return False

	def _visible(self):
		return set(frappe.get_list(DOCTYPE, filters={"name": ["in", [self.asg_a, self.asg_b]]}, pluck="name"))

	# ---------- D1 proofs (failed on main 66cedea) ----------

	def test_list_shows_only_own_company(self):
		for role in ("Card User", "Card Manager"):
			with self.subTest(role=role):
				self._as([role], restrict=self.company)
				self.assertEqual(self._visible(), {self.asg_a})

	def test_single_read_refused_for_other_company(self):
		for role in ("Card User", "Card Manager"):
			with self.subTest(role=role):
				self._as([role], restrict=self.company)
				self.assertEqual(rest_get(DOCTYPE, self.asg_a)["name"], self.asg_a)
				self.assertTrue(self._refused(rest_get, DOCTYPE, self.asg_b))

	def test_link_search_hides_other_company(self):
		for role in ("Card User", "Card Manager"):
			with self.subTest(role=role):
				self._as([role], restrict=self.company)
				rows = search_link(DOCTYPE, "", filters={"name": ["in", [self.asg_a, self.asg_b]]})
				self.assertEqual({r.get("value") for r in rows}, {self.asg_a})

	def test_manager_cannot_create_for_other_company(self):
		eq_a2, eq_b2 = self._equipment("A2", self.company), self._equipment("B2", self.other)
		self._as(["Card Manager"], restrict=self.company)
		self.assertTrue(rest_insert(self._row(eq_a2, self.proj_a))["name"])  # positive control
		self.assertTrue(self._refused(rest_insert, self._row(eq_b2, self.proj_b)))

	def test_manager_cannot_change_other_company_assignment(self):
		doc = frappe.get_doc(DOCTYPE, self.asg_b).as_dict()  # the row as an API client would send it
		self._as(["Card Manager"], restrict=self.company)
		doc["to_date"] = self._d(20)
		self.assertTrue(self._refused(rest_save, doc))
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value(DOCTYPE, self.asg_b, "to_date"))

	# ---------- moving a row across companies ----------

	def test_other_company_row_cannot_be_moved_into_own_company(self):
		eq_a3 = self._equipment("A3", self.company)
		doc = frappe.get_doc(DOCTYPE, self.asg_b).as_dict()
		self._as(["Card Manager"], restrict=self.company)
		doc.update({"equipment": eq_a3, "project": self.proj_a})
		self.assertTrue(self._refused(rest_save, doc))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, self.asg_b, "equipment"), self.eq_b)

	def test_own_row_cannot_be_moved_to_other_company(self):
		eq_b3 = self._equipment("B3", self.other)
		self._as(["Card Manager"], restrict=self.company)
		doc = rest_get(DOCTYPE, self.asg_a)
		doc.update({"equipment": eq_b3, "project": self.proj_b})
		self.assertTrue(self._refused(rest_save, doc))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, self.asg_a, "equipment"), self.eq_a)

	# ---------- authorised paths keep working ----------

	def test_own_company_manager_edits_own_rows(self):
		self._as(["Card Manager"], restrict=self.company)
		doc = rest_get(DOCTYPE, self.asg_a)
		doc["to_date"] = self._d(25)
		rest_save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(str(frappe.db.get_value(DOCTYPE, self.asg_a, "to_date")), self._d(25))

	def test_unrestricted_roles_see_and_change_every_company(self):
		for roles in (["Card Manager"], ["System Manager"]):
			with self.subTest(roles=roles):
				self._as(roles)
				self.assertEqual(self._visible(), {self.asg_a, self.asg_b})
				doc = rest_get(DOCTYPE, self.asg_b)
				doc["notes"] = "edited " + self.token
				rest_save(doc)
				frappe.set_user("Administrator")
		self.assertEqual(self._visible(), {self.asg_a, self.asg_b})  # Administrator

	def test_permission_for_another_doctype_does_not_restrict_assignments(self):
		# a Company User Permission applies only to the doctypes it names (Frappe semantics)
		self._as(["Card Manager"], restrict=self.company, applicable_for="Card Monthly Card")
		self.assertEqual(self._visible(), {self.asg_a, self.asg_b})

	def test_permission_for_assignments_only_restricts_them(self):
		self._as(["Card Manager"], restrict=self.company, applicable_for=DOCTYPE)
		self.assertEqual(self._visible(), {self.asg_a})

	def test_equipment_permission_also_hides_its_assignments(self):
		# an assignment never shows equipment the user cannot open
		self._as(["Card Manager"], restrict=self.company, applicable_for="Card Equipment")
		self.assertEqual(self._visible(), {self.asg_a})

	def test_set_value_and_report_view_follow_the_same_rule(self):
		from frappe.client import set_value
		from frappe.desk.reportview import get as reportview_get

		self._as(["Card Manager"], restrict=self.company)
		self.assertTrue(self._refused(set_value, DOCTYPE, self.asg_b, "to_date", self._d(20)))
		set_value(DOCTYPE, self.asg_a, "to_date", self._d(20))  # positive control
		frappe.local.form_dict = frappe._dict(
			doctype=DOCTYPE, fields=["name"], filters=[[DOCTYPE, "name", "in", [self.asg_a, self.asg_b]]]
		)
		values = reportview_get()["values"]
		self.assertEqual({row[0] for row in values}, {self.asg_a})

	def test_rename_follows_the_same_rule(self):
		from frappe.client import rename_doc

		self._as(["Card Manager"], restrict=self.company)
		self.assertTrue(self._refused(rename_doc, DOCTYPE, self.asg_b, "TEST-ASGISO-RB-" + self.token))
		renamed = rename_doc(DOCTYPE, self.asg_a, "TEST-ASGISO-RA-" + self.token)  # positive control
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists(DOCTYPE, renamed))
		self.assertTrue(frappe.db.exists(DOCTYPE, self.asg_b))

	def test_list_count_counts_only_own_company(self):
		from frappe.desk.reportview import get_count

		self._as(["Card Manager"], restrict=self.company)
		frappe.local.form_dict = frappe._dict(
			doctype=DOCTYPE, filters=[[DOCTYPE, "name", "in", [self.asg_a, self.asg_b]]]
		)
		self.assertEqual(get_count(), 1)

	def test_connection_counts_need_the_parent_record(self):
		# Frappe counts linked rows without permission checks (desk.notifications.get_doc_count),
		# but only after a READ check on the parent (equipment / project), which is company-scoped
		from frappe.desk.notifications import get_open_count

		def assignment_count(doctype, name):
			found = get_open_count(doctype, name, [DOCTYPE])["count"]["external_links_found"]
			return [d["count"] for d in found if d["doctype"] == DOCTYPE]

		self._as(["Card Manager"], restrict=self.company)
		self.assertEqual(assignment_count("Card Equipment", self.eq_a), [1])  # positive control
		self.assertTrue(self._refused(get_open_count, "Card Equipment", self.eq_b, [DOCTYPE]))
		self._as(["Projects User"], restrict=self.company)
		self.assertEqual(assignment_count("Project", self.proj_a), [1])
		self.assertTrue(self._refused(get_open_count, "Project", self.proj_b, [DOCTYPE]))

	def test_card_user_still_cannot_write_own_company_rows(self):
		# no role is widened: Card User keeps read-only access to assignments
		self._as(["Card User"], restrict=self.company)
		doc = rest_get(DOCTYPE, self.asg_a)
		doc["to_date"] = self._d(25)
		self.assertTrue(self._refused(rest_save, doc))

	def test_project_user_permission_still_applies(self):
		proj_a2 = self._project("A2", self.company)
		asg_a2 = self._assign(self._equipment("A4", self.company), proj_a2)
		self._as(["Card Manager"], restrict=self.proj_a, allow="Project")
		names = set(frappe.get_list(DOCTYPE, filters={"name": ["in", [self.asg_a, asg_a2]]}, pluck="name"))
		self.assertEqual(names, {self.asg_a})

	def test_restricted_manager_transport_still_moves_equipment(self):
		# transports open/close assignments as before (card.transfer is unchanged)
		eq = self._equipment("T", self.company)
		proj_t = self._project("T", self.company)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-ASGISO-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self._as(["Card Manager"], restrict=self.company)
		t = frappe.get_doc(
			{
				"doctype": "Equipment Transport",
				"date": self._d(3),
				"company": self.company,
				"project": proj_t,
				"transport_supplier": sup.name,
				"amount": 100,
				"items": [{"card_equipment": eq}],
			}
		).insert()
		t.submit()
		created = frappe.get_list(DOCTYPE, filters={"equipment": eq}, fields=["project", "from_date"])
		self.assertEqual([(r.project, str(r.from_date)) for r in created], [(proj_t, self._d(3))])
