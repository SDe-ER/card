# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v1.2.2 A6 + security review: Accounts Manager maintains the per-company
accounting rows of Card Settings (level 0 + 1 write) but not the policy fields
(level 2, System Manager), and only for companies they may see."""

import frappe
from frappe.tests import IntegrationTestCase

from card.tests.test_controllers import _ensure_masters


class TestSettingsPermlevel(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _accounts_manager(self, restrict_to=None):
		email = f"spl-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Settings",
				"send_welcome_email": 0,
				"roles": [{"role": "Accounts Manager"}],
			}
		).insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		return email

	def _ensure_row(self, company):
		settings = frappe.get_doc("Card Settings")
		if not any(r.company == company for r in settings.get("company_settings") or []):
			settings.append("company_settings", {"company": company})
			settings.save(ignore_permissions=True)

	def _other_company(self):
		name = "TEST-SPL-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "S" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _leaf_cost_center(self, company):
		return frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name")

	def test_accounts_manager_saves_accounting_rows_but_not_policy(self):
		self._ensure_row(self.company)
		cost_center = self._leaf_cost_center(self.company)
		tolerance = frappe.db.get_single_value("Card Settings", "reconciliation_tolerance")
		frappe.set_user(self._accounts_manager())
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == self.company)
		row.cost_center = cost_center
		settings.reconciliation_tolerance = (tolerance or 0) + 999  # level 2: reset on save
		settings.save()
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(
				"Card Company Settings", {"parent": "Card Settings", "company": self.company}, "cost_center"
			),
			cost_center,
		)
		self.assertEqual(frappe.db.get_single_value("Card Settings", "reconciliation_tolerance"), tolerance)

	def test_restricted_accounts_manager_cannot_touch_another_companys_row(self):
		"""Refused — by Frappe's User Permission check on the child rows' Company
		links (Frappe 16 checks them on the parent's write) and, as a second
		layer, by CardSettings._validate_company_scope. Known limitation: while
		rows of other companies exist, a company-restricted Accounts Manager
		cannot save Card Settings at all; an unrestricted accountant maintains
		them."""
		other = self._other_company()
		self._ensure_row(self.company)
		self._ensure_row(other)
		before = frappe.db.get_value(
			"Card Company Settings", {"parent": "Card Settings", "company": other}, "cost_center"
		)
		frappe.set_user(self._accounts_manager(restrict_to=self.company))
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == other)
		row.cost_center = self._leaf_cost_center(self.company)
		with self.assertRaises(frappe.PermissionError):
			settings.save()
		settings = frappe.get_doc("Card Settings")
		settings.company_settings = [r for r in settings.company_settings if r.company != other]
		with self.assertRaises(frappe.PermissionError):
			settings.save()
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(
				"Card Company Settings", {"parent": "Card Settings", "company": other}, "cost_center"
			),
			before,
		)

	def test_company_scope_check_is_a_second_layer(self):
		"""CardSettings._validate_company_scope on its own (Frappe's link check
		bypassed with ignore_permissions, as a script or another app might)."""
		other = self._other_company()
		self._ensure_row(other)
		frappe.set_user(self._accounts_manager(restrict_to=self.company))
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == other)
		row.cost_center = self._leaf_cost_center(self.company)
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to change the Card settings"):
			settings.save(ignore_permissions=True)
