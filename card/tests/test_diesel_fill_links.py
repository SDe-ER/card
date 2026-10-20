# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""P0 (Owner 2026-10-20): a Card User picks Project, Cost Center and Supplier on a diesel fill through
fill_link_query — only what the user may pick for the fill's company — and the save refuses other
companies' values, also through the API. No permission on the ERPNext masters is granted."""

import frappe
from frappe.client import insert as rest_insert
from frappe.desk.search import search_link, search_widget
from frappe.tests import IntegrationTestCase

from card.card.doctype.project_diesel_fill.project_diesel_fill import fill_link_query
from card.tests.diesel_price import set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _role_user, _set

QUERY = "card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query"


class TestDieselFillLinks(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		_set("period_lock_date", None)
		_set("diesel_supplier", None)
		_set("diesel_supplier_policy", "متغير")
		_set("diesel_supplier_editor_role", "Card Manager")
		set_diesel_price(self.company, 2)
		self.project = self._project(self.company)
		self.supplier = self._supplier()
		self.cost_center = frappe.get_cached_value("Company", self.company, "cost_center")
		other = frappe.new_doc("Company")
		other.company_name = "TEST-DFL-OTHER-" + self.token
		other.abbr = "DF" + self.token[:4]
		other.default_currency = "SAR"
		other.country = "Saudi Arabia"
		self.other = other.insert(ignore_permissions=True).name
		set_diesel_price(self.other, 3)
		self.other_project = self._project(self.other)
		self.other_cost_center = frappe.get_cached_value("Company", self.other, "cost_center")
		self.card_user = _role_user("Card User")

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _project(self, company):
		p = frappe.new_doc("Project")
		p.project_name = "TEST-DFL-PRJ-" + frappe.generate_hash(length=8)
		p.company = company
		return p.insert(ignore_permissions=True).name

	def _supplier(self, disabled=0):
		s = frappe.new_doc("Supplier")
		s.supplier_name = "TEST-DFL-SUP-" + frappe.generate_hash(length=8)
		s.supplier_group = self._m["supplier_group"]
		s.disabled = disabled
		return s.insert(ignore_permissions=True).name

	def _cost_center(self, company, **extra):
		root = frappe.db.get_value(
			"Cost Center", {"company": company, "is_group": 1, "parent_cost_center": ["is", "not set"]}
		)
		cc = frappe.new_doc("Cost Center")
		cc.cost_center_name = "TEST-DFL-CC-" + frappe.generate_hash(length=6)
		cc.parent_cost_center = root
		cc.company = company
		cc.update(extra)
		return cc.insert(ignore_permissions=True).name

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _names(self, user, doctype, company=None, txt=""):
		rows = self._as(
			user,
			fill_link_query,
			doctype,
			txt,
			"name",
			0,
			500,
			{"company": company} if company else {},
		)
		return {r[0] for r in rows}

	def _data(self, **extra):
		data = {
			"doctype": "Project Diesel Fill",
			"date": "2026-09-15",
			"project": self.project,
			"supplier": self.supplier,
			"company": self.company,
			"litres": 100,
		}
		data.update(extra)
		return data

	# ---------- the cause (unchanged ERPNext permissions) ----------

	def test_card_user_has_no_master_permission(self):
		"""Why the scoped query exists: the standard link search refuses a Card User, and this fix
		grants nothing on the masters."""
		frappe.set_user(self.card_user)
		try:
			for doctype in ("Project", "Cost Center", "Supplier"):
				self.assertFalse(frappe.has_permission(doctype, "select"), doctype)
				self.assertFalse(frappe.has_permission(doctype, "read"), doctype)
			with self.assertRaises(frappe.PermissionError):
				search_link(doctype="Cost Center", txt="", reference_doctype="Project Diesel Fill")
		finally:
			frappe.set_user("Administrator")

	# ---------- listing ----------

	def test_card_user_lists_own_company_projects_only(self):
		names = self._names(self.card_user, "Project", self.company)
		self.assertIn(self.project, names)
		self.assertNotIn(self.other_project, names)
		self.assertIn(self.other_project, self._names(self.card_user, "Project", self.other))

	def test_cost_centers_are_enabled_leaves_of_the_company(self):
		group = self._cost_center(self.company, is_group=1)
		disabled = self._cost_center(self.company, disabled=1)
		names = self._names(self.card_user, "Cost Center", self.company)
		self.assertIn(self.cost_center, names)
		self.assertNotIn(group, names)
		self.assertNotIn(disabled, names)
		self.assertNotIn(self.other_cost_center, names)

	def test_company_not_permitted_or_missing_lists_nothing(self):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": self.card_user,
				"allow": "Company",
				"for_value": self.company,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(self._names(self.card_user, "Project", self.other), set())
		self.assertEqual(self._names(self.card_user, "Cost Center", self.other), set())
		self.assertEqual(self._names(self.card_user, "Project"), set())
		self.assertIn(self.project, self._names(self.card_user, "Project", self.company))

	def test_user_permission_on_project_limits_the_list(self):
		second = self._project(self.company)
		frappe.get_doc(
			{"doctype": "User Permission", "user": self.card_user, "allow": "Project", "for_value": second}
		).insert(ignore_permissions=True)
		self.assertEqual(self._names(self.card_user, "Project", self.company), {second})

	def _permit_supplier(self, user, supplier):
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Supplier", "for_value": supplier}
		).insert(ignore_permissions=True)

	def test_supplier_user_permission_limits_the_forced_settings_supplier(self):
		default = self._supplier()
		_set("diesel_supplier", default)
		# a Supplier User Permission that leaves out the Settings supplier leaves nothing to pick
		self._permit_supplier(self.card_user, self.supplier)
		self.assertEqual(self._names(self.card_user, "Supplier"), set())
		# one that includes it keeps exactly that supplier
		self._permit_supplier(self.card_user, default)
		self.assertEqual(self._names(self.card_user, "Supplier"), {default})

	def test_supplier_user_permission_limits_the_list_of_a_supplier_editor(self):
		editor = _role_user("Card User", "Card Manager")
		_set("diesel_supplier", self._supplier())
		self.assertGreater(len(self._names(editor, "Supplier")), 1)
		self._permit_supplier(editor, self.supplier)
		self.assertEqual(self._names(editor, "Supplier"), {self.supplier})

	def test_search_text_filters_by_title(self):
		title = frappe.db.get_value("Project", self.project, "project_name")
		self.assertEqual(self._names(self.card_user, "Project", self.company, txt=title), {self.project})

	def test_supplier_list_follows_the_supplier_policy(self):
		disabled = self._supplier(disabled=1)
		# no Settings supplier: any enabled supplier
		names = self._names(self.card_user, "Supplier")
		self.assertIn(self.supplier, names)
		self.assertNotIn(disabled, names)
		# a Settings supplier the user may not change: that supplier only
		default = self._supplier()
		_set("diesel_supplier", default)
		self.assertEqual(self._names(self.card_user, "Supplier"), {default})
		_set("diesel_supplier_policy", "ثابت")
		self.assertEqual(self._names(self.card_user, "Supplier"), {default})
		# Variable policy + editor role: any enabled supplier
		_set("diesel_supplier_policy", "متغير")
		editor = _role_user("Card User", "Card Manager")
		names = self._names(editor, "Supplier")
		self.assertTrue({default, self.supplier} <= names)
		self.assertNotIn(disabled, names)

	def test_typed_value_is_validated_through_the_query(self):
		"""The Desk validates a typed-in value with the form's query (validate_link_and_fetch)."""
		frappe.set_user(self.card_user)
		try:
			ok = search_widget(
				doctype="Project",
				txt=self.project,
				query=QUERY,
				filters={"company": self.company},
				for_link_validation=True,
			)
			self.assertIn(self.project, [r[0] for r in ok])
			other = search_widget(
				doctype="Project",
				txt=self.other_project,
				query=QUERY,
				filters={"company": self.company},
				for_link_validation=True,
			)
			self.assertNotIn(self.other_project, [r[0] for r in other])
		finally:
			frappe.set_user("Administrator")

	def test_manager_with_master_permission_keeps_company_rule(self):
		manager = _role_user("Card Manager", "Projects Manager", "Accounts Manager")
		self.assertIn(self.project, self._names(manager, "Project", self.company))
		self.assertNotIn(self.other_project, self._names(manager, "Project", self.company))
		self.assertIn(self.cost_center, self._names(manager, "Cost Center", self.company))

	def test_select_only_role_gets_the_same_company_list(self):
		"""Employee holds select (not read) on Cost Center: the list is the same company-scoped one."""
		user = _role_user("Card User", "Employee")
		names = self._names(user, "Cost Center", self.company)
		self.assertIn(self.cost_center, names)
		self.assertNotIn(self.other_cost_center, names)

	def test_direct_api_call_with_json_filters(self):
		"""/api/method sends filters as a JSON string; a list in place of the object lists nothing."""
		names = self._names(self.card_user, "Project", None)
		self.assertEqual(names, set())
		rows = self._as(
			self.card_user, fill_link_query, "Project", "", "name", 0, 500, f'{{"company": "{self.company}"}}'
		)
		self.assertIn(self.project, {r[0] for r in rows})
		rows = self._as(
			self.card_user, fill_link_query, "Project", "", "name", 0, 500, '[["company", "=", "x"]]'
		)
		self.assertEqual(rows, [])

	def test_form_default_supplier_for_a_user_who_cannot_change_it(self):
		"""The form takes the first row of the Supplier query: the Settings supplier only."""
		default = self._supplier()
		_set("diesel_supplier", default)
		rows = self._as(self.card_user, fill_link_query, "Supplier", "", "name", 0, 1, None)
		self.assertEqual([r[0] for r in rows], [default])

	# ---------- refusals ----------

	def test_user_without_fill_rights_is_refused(self):
		reader = _role_user("Accounts Manager")  # reads fills, cannot create or edit them
		with self.assertRaises(frappe.PermissionError):
			self._names(reader, "Project", self.company)
		nobody = _role_user()
		with self.assertRaises(frappe.PermissionError):
			self._names(nobody, "Cost Center", self.company)

	def test_other_doctypes_are_refused(self):
		for doctype in ("Account", "User", "Company", "Card Settings"):
			with self.assertRaises(frappe.PermissionError):
				self._names(self.card_user, doctype, self.company)

	def test_endpoint_is_get_only(self):
		from card.card.doctype.project_diesel_fill import project_diesel_fill as m

		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[m.fill_link_query], ["GET"])

	# ---------- save (also through the API) ----------

	def test_card_user_saves_with_own_company_values(self):
		f = self._as(self.card_user, frappe.get_doc(self._data(cost_center=self.cost_center)).insert)
		self.assertEqual((f.project, f.cost_center), (self.project, self.cost_center))

	def test_other_company_project_refused_on_save_and_rest(self):
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to company"):
			self._as(self.card_user, frappe.get_doc(self._data(project=self.other_project)).insert)
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to company"):
			self._as(self.card_user, rest_insert, self._data(project=self.other_project))

	def test_bad_cost_center_refused_on_save_and_rest(self):
		group = self._cost_center(self.company, is_group=1)
		disabled = self._cost_center(self.company, disabled=1)
		for cc in (self.other_cost_center, group, disabled):
			with self.assertRaisesRegex(frappe.ValidationError, "non-group cost center", msg=cc):
				self._as(self.card_user, rest_insert, self._data(cost_center=cc))

	def test_moving_a_draft_to_another_company_keeps_its_links_checked(self):
		f = self._as(self.card_user, frappe.get_doc(self._data(cost_center=self.cost_center)).insert)
		f.company = self.other
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to company"):
			self._as(self.card_user, f.save)

	def test_disabled_supplier_refused_only_when_chosen(self):
		disabled = self._supplier(disabled=1)
		with self.assertRaisesRegex(frappe.ValidationError, "is disabled"):
			self._as(self.card_user, rest_insert, self._data(supplier=disabled))
		# a draft whose supplier was disabled later still saves while its supplier is unchanged
		f = frappe.get_doc(self._data()).insert()
		frappe.db.set_value("Supplier", self.supplier, "disabled", 1)
		f.reload()
		f.litres = 120
		self._as(self.card_user, f.save)
		self.assertEqual(f.litres, 120)
