# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""H-CARD-4: record-level company permission of Project Diesel Fill, same pattern as the
Card Monthly Card and Equipment Transport hooks. A user limited to company A must be
refused read, write and create on a company-B fill and allowed on a company-A fill.
Everything is rolled back."""

import frappe
from frappe.tests import IntegrationTestCase

from card.card.doctype.project_diesel_fill.project_diesel_fill import has_diesel_fill_permission
from card.tests.test_controllers import _ensure_masters

DOCTYPE = "Project Diesel Fill"


class TestDieselFillCompanyPermission(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.other = self._other_company()
		self.fill_a = self._fill(self.company)
		self.fill_b = self._fill(self.other)
		self.user = self._user(["Card User"], restrict=self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def _other_company(self):
		name = "TEST-DFPERM-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "D" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _fill(self, company):
		doc = frappe.new_doc(DOCTYPE)
		doc.company = company
		doc.name = "TEST-DFPERM-%s-%s" % (company[-4:], self.token)
		doc.db_insert()  # no validation: only the stored company matters here
		return doc.name

	def _user(self, roles, restrict):
		email = f"dfperm-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Diesel Fill Permission",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Company",
				"for_value": restrict,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _plain_user(self, roles):
		email = f"dfperm-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Diesel Fill Permission",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _allowed(self, ptype, doc):
		return bool(frappe.has_permission(DOCTYPE, ptype, doc=doc, user=self.user))

	def test_hook_is_registered(self):
		hooks = frappe.get_hooks("has_permission").get(DOCTYPE) or []
		self.assertIn(
			"card.card.doctype.project_diesel_fill.project_diesel_fill.has_diesel_fill_permission", hooks
		)

	def test_same_company_fill_allowed(self):
		for ptype in ("read", "write"):
			with self.subTest(ptype=ptype):
				self.assertTrue(self._allowed(ptype, self.fill_a))

	def test_other_company_fill_denied_read_and_write(self):
		for ptype in ("read", "write"):
			with self.subTest(ptype=ptype):
				self.assertFalse(self._allowed(ptype, self.fill_b))

	def test_create_in_other_company_denied_same_company_allowed(self):
		self.assertTrue(self._allowed("create", frappe.new_doc(DOCTYPE, company=self.company)))
		self.assertFalse(self._allowed("create", frappe.new_doc(DOCTYPE, company=self.other)))

	def test_takeover_by_sending_own_company_denied(self):
		"""Company A sent on top of B's stored fill: the stored company still decides."""
		doc = frappe.get_doc(DOCTYPE, self.fill_b)
		doc.company = self.company
		self.assertFalse(has_diesel_fill_permission(doc, "write", self.user))

	def test_unrestricted_user_allowed_everywhere(self):
		for name in (self.fill_a, self.fill_b):
			self.assertTrue(frappe.has_permission(DOCTYPE, "read", doc=name, user="Administrator"))

	def test_unrestricted_non_admin_allowed_everywhere(self):
		email = self._plain_user(["Card Manager"])
		for name in (self.fill_a, self.fill_b):
			with self.subTest(name=name):
				self.assertTrue(frappe.has_permission(DOCTYPE, "read", doc=name, user=email))

	def test_company_permission_not_applied_to_all_doctypes_still_denies(self):
		"""A Company User Permission limited to this doctype (apply_to_all_doctypes=0)."""
		email = self._plain_user(["Card User"])
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Company",
				"for_value": self.company,
				"apply_to_all_doctypes": 0,
				"applicable_for": DOCTYPE,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		self.assertTrue(frappe.has_permission(DOCTYPE, "read", doc=self.fill_a, user=email))
		self.assertFalse(frappe.has_permission(DOCTYPE, "read", doc=self.fill_b, user=email))

	def test_takeover_b_to_a_by_save_or_check_permission_denied(self):
		frappe.set_user(self.user)
		doc = frappe.get_doc(DOCTYPE, self.fill_b)
		doc.company = self.company
		with self.assertRaises(frappe.PermissionError):
			doc.check_permission("write")
		with self.assertRaises(frappe.PermissionError):
			doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, self.fill_b, "company"), self.other)

	def test_cross_company_share_is_refused_so_it_cannot_bypass_the_hook(self):
		"""frappe 16 consults DocShare after a controller denial (frappe/permissions.py)."""
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{
					"doctype": "DocShare",
					"user": self.user,
					"share_doctype": DOCTYPE,
					"share_name": self.fill_b,
					"read": 1,
				}
			).insert(ignore_permissions=True)
		self.assertFalse(self._allowed("read", self.fill_b))
		# a share inside the user's own company is not blocked by this guard
		frappe.get_doc(
			{
				"doctype": "DocShare",
				"user": self.user,
				"share_doctype": DOCTYPE,
				"share_name": self.fill_a,
				"read": 1,
			}
		).insert(ignore_permissions=True)

	def test_everyone_share_of_any_fill_is_refused(self):
		"""An everyone-share reaches users of every company: refused for both companies' fills,
		with or without a user, on insert and when an allowed share is edited into one."""
		for name in (self.fill_a, self.fill_b):
			for extra in ({"everyone": 1}, {"everyone": 1, "user": self.user}):
				with self.subTest(fill=name, extra=extra), self.assertRaises(frappe.PermissionError):
					frappe.get_doc(
						{
							"doctype": "DocShare",
							"share_doctype": DOCTYPE,
							"share_name": name,
							"read": 1,
							**extra,
						}
					).insert(ignore_permissions=True)
		self.assertFalse(self._allowed("read", self.fill_b))
		share = frappe.get_doc(
			{
				"doctype": "DocShare",
				"user": self.user,
				"share_doctype": DOCTYPE,
				"share_name": self.fill_a,
				"read": 1,
			}
		).insert(ignore_permissions=True)
		share.everyone = 1
		with self.assertRaises(frappe.PermissionError):
			share.save(ignore_permissions=True)
