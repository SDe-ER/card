# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Issue #357: the CARD Mobile profile and the role-based home. Operators get no KPI values,
review roles get operational counts, and only Card Manager / System Manager get financial figures
(Owner decision 2026-11-28). The server decides, never the client."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

import card
from card import mobile
from card.tests.test_controllers import _days, _ensure_masters

FINANCIAL_KEYS = ("revenue", "cost", "financial")


class TestMobileHome(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _user(self, prefix, roles, language=None):
		email = f"home-{prefix}-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": prefix,
				"send_welcome_email": 0,
				"language": language,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _employee(self, user):
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"Home {self.token}",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": "Active",
				"user_id": user,
				"cell_number": "0500000000",
			}
		).insert(ignore_permissions=True)

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _equipment(self):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "تشغيل داخلي"
		d.equipment_name = "HOME-EQ-" + self.token
		d.insert(ignore_permissions=True)
		return d

	def _submitted_card(self, equipment):
		doc = frappe.new_doc("Card Monthly Card")
		doc.equipment = equipment.name
		doc.project = self._m["project"]
		doc.shift = "نهاري"
		doc.month = "09"
		doc.year = 2026
		for row in _days([10] * 5):
			doc.append("days", row)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def _home(self, user):
		return self._as(user, mobile.get_home_context)

	# ---------- endpoints are GET for reads and POST for the one write ----------
	def test_endpoint_methods(self):
		self.assertEqual(mobile.get_profile.__dict__.get("allowed_http_methods"), ["GET"])
		self.assertEqual(mobile.get_home_context.__dict__.get("allowed_http_methods"), ["GET"])
		self.assertEqual(mobile.set_language.__dict__.get("allowed_http_methods"), ["POST"])

	# ---------- operator ----------
	def test_operator_gets_no_kpis_and_no_financial_values(self):
		user = self._user("op", ["Card Operator"])
		self._employee(user)
		home = self._home(user)
		self.assertFalse(home["reviewer"])
		self.assertFalse(home["manager"])
		self.assertIsNone(home["kpis"])
		self.assertIsNone(home["financial"])

	# ---------- supervisor ----------
	def test_supervisor_gets_operational_kpis_only(self):
		self._equipment()
		user = self._user("sup", ["Card Supervisor"])
		self._employee(user)
		home = self._home(user)
		self.assertTrue(home["reviewer"])
		self.assertFalse(home["manager"])
		self.assertIsNone(home["financial"])
		kpis = home["kpis"]
		self.assertEqual(set(kpis["equipment"]), {"active", "stopped", "maintenance"})
		self.assertGreaterEqual(kpis["equipment"]["active"], 1)
		self.assertIn("documents_expiring", kpis["alerts"])
		for key in FINANCIAL_KEYS:
			self.assertNotIn(key, str(kpis))

	# ---------- manager ----------
	def test_manager_gets_financial_figures_for_the_current_month(self):
		doc = self._submitted_card(self._equipment())
		user = self._user("mgr", ["Card Manager"])
		self._employee(user)
		with patch("card.mobile.nowdate", return_value="2026-09-15"):
			home = self._home(user)
		self.assertTrue(home["manager"])
		self.assertIsNotNone(home["kpis"])
		financial = home["financial"]
		self.assertEqual((financial["year"], financial["month"]), (2026, 9))
		row = next(r for r in financial["by_company"] if r["company"] == self.company)
		self.assertGreaterEqual(
			row["cost"], frappe.db.get_value("Card Monthly Card", doc.name, "net_amount") or 0
		)

	def test_financial_figures_follow_the_company_scope_of_the_user(self):
		self._submitted_card(self._equipment())
		user = self._user("scoped", ["Card Manager"])
		self._employee(user)
		other = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Other {self.token}",
				"abbr": f"O{self.token[:3]}".upper(),
				"default_currency": "SAR",
				"country": "Saudi Arabia",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": other.name,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)
		with patch("card.mobile.nowdate", return_value="2026-09-15"):
			home = self._home(user)
		self.assertEqual([r for r in home["financial"]["by_company"] if r["company"] == self.company], [])
		self.assertEqual(home["kpis"]["equipment"]["active"], 0)

	def test_financial_figures_use_the_current_month_only(self):
		self._submitted_card(self._equipment())
		user = self._user("mgr2", ["Card Manager"])
		self._employee(user)
		with patch("card.mobile.nowdate", return_value="2026-10-15"):
			financial = self._home(user)["financial"]
		self.assertEqual([r for r in financial["by_company"] if r["company"] == self.company], [])

	def test_system_manager_gets_financial_figures(self):
		user = self._user("sys", ["System Manager"])
		self._employee(user)
		self.assertIsNotNone(self._home(user)["financial"])

	# ---------- access ----------
	def test_users_without_a_card_role_are_refused(self):
		outsider = self._user("out", [])
		self._employee(outsider)
		for fn in (mobile.get_home_context, mobile.get_profile):
			with self.assertRaises(frappe.PermissionError):
				self._as(outsider, fn)

	def test_catalog_only_user_gets_no_kpis(self):
		user = self._user("viewer", ["Card User"])
		home = self._home(user)
		self.assertFalse(home["reviewer"])
		self.assertIsNone(home["kpis"])
		self.assertIsNone(home["financial"])

	# ---------- profile ----------
	def test_profile_shows_live_data_and_only_held_roles(self):
		user = self._user("prof", ["Card Operator", "Card Supervisor"])
		employee = self._employee(user)
		profile = self._as(user, mobile.get_profile)
		self.assertEqual(profile["employee"]["name"], employee.name)
		self.assertEqual(profile["company"], self.company)
		self.assertEqual(profile["phone"], "0500000000")
		self.assertEqual(profile["roles"], ["Card Operator", "Card Supervisor"])
		self.assertEqual(profile["card_version"], card.__version__)
		self.assertTrue(profile["currency"])

	def test_profile_belongs_to_the_caller_only(self):
		a = self._user("pa", ["Card Operator"])
		b = self._user("pb", ["Card Operator"])
		self._employee(a)
		profile = self._as(b, mobile.get_profile)
		self.assertIsNone(profile["employee"])

	# ---------- language ----------
	def test_set_language_changes_the_callers_own_language_only(self):
		user = self._user("lang", ["Card Operator"], language="en")
		other = self._user("lang2", ["Card Operator"], language="en")
		self._employee(user)
		self.assertEqual(self._as(user, mobile.set_language, "ar"), "ar")
		self.assertEqual(frappe.db.get_value("User", user, "language"), "ar")
		self.assertEqual(frappe.db.get_value("User", other, "language"), "en")

	def test_set_language_refuses_other_values_and_administrator(self):
		user = self._user("lang3", ["Card Operator"], language="en")
		self._employee(user)
		with self.assertRaises(frappe.ValidationError):
			self._as(user, mobile.set_language, "fr")
		self.assertEqual(frappe.db.get_value("User", user, "language"), "en")
		before = frappe.db.get_value("User", "Administrator", "language")
		with self.assertRaises(frappe.PermissionError):
			mobile.set_language("ar")
		self.assertEqual(frappe.db.get_value("User", "Administrator", "language"), before)
