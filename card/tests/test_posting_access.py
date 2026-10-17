# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#36: the monthly-posting endpoints build drafts only for a company the caller
may see. They insert invoices with ignore_permissions, so the company scope must
be enforced at the entry point (same rule as the reports: User Permission on
Company, card.report_access.permitted_companies)."""

import frappe

from card.gl.posting import post_month, rebuild_month
from card.tests.test_s3_posting import _PostingBase


class TestPostingEndpointCompanyAccess(_PostingBase):
	def setUp(self):
		super().setUp()
		self.other = "TEST-PACC-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": self.other,
				"abbr": "P" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = self.other
		co.db_insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _manager(self, restrict_to=None, roles=None):
		email = f"pacc-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Posting Access",
				"send_welcome_email": 0,
				# a realistic poster: building a PI/SI reads accounts and items
				"roles": [
					{"role": role}
					for role in roles or ("Card Manager", "Accounts Manager", "Purchase User", "Sales User")
				],
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
		frappe.clear_cache(user=email)
		return email

	def _submitted_card(self):
		eq = self._equipment(rate_type="بالساعة", rate=100)
		return self._card(eq, [8, 8], submit=True)

	def test_restricted_manager_cannot_post_another_company(self):
		self._submitted_card()
		frappe.set_user(self._manager(restrict_to=self.other))
		for endpoint in (post_month, rebuild_month):
			# refused by CARD's own gate, before any build work — not by a later
			# incidental ERPNext account check
			with self.assertRaisesRegex(frappe.PermissionError, "not permitted to build postings"):
				endpoint(self.company, "Supplier", self.supplier, "9", "2026")
		frappe.set_user("Administrator")
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))
		self.assertFalse(
			frappe.get_all("Purchase Invoice", filters={"supplier": self.supplier, "docstatus": 0})
		)

	def test_permitted_manager_still_posts(self):
		self._submitted_card()
		frappe.set_user(self._manager(restrict_to=self.company))
		invoice = post_month(self.company, "Supplier", self.supplier, "9", "2026")
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Purchase Invoice", invoice))

	def test_party_user_permission_is_honoured(self):
		self._submitted_card()
		other_supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "TEST-PACC-OTHER-" + self.token,
				"supplier_group": self._m["supplier_group"],
			}
		).insert(ignore_permissions=True)
		email = self._manager()
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Supplier",
				"for_value": other_supplier.name,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		frappe.set_user(email)
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to build postings"):
			post_month(self.company, "Supplier", self.supplier, "9", "2026")

	def test_poster_without_item_read_gets_a_clear_message(self):
		"""D2 (functional tests 2026-10-17): ERPNext prices the invoice lines
		through get_item_details, which checks that the CALLER may read Item. A
		Card Manager whose only ERPNext role is Accounts Manager is refused up
		front with CARD's own message: no draft, no log, no rights widened."""
		self._submitted_card()
		email = self._manager(roles=("Card Manager", "Accounts Manager"))
		frappe.set_user(email)
		self.assertFalse(frappe.has_permission("Item", "read"))
		for endpoint in (post_month, rebuild_month):
			with self.assertRaisesRegex(frappe.PermissionError, "do not allow reading Items"):
				endpoint(self.company, "Supplier", self.supplier, "9", "2026")
		self.assertFalse(frappe.has_permission("Item", "read"))  # nothing was granted
		frappe.set_user("Administrator")
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))
		self.assertFalse(
			frappe.get_all("Purchase Invoice", filters={"supplier": self.supplier, "docstatus": 0})
		)

	def test_poster_with_item_read_still_posts(self):
		"""D2 positive control: the same Card Manager plus a standard role that
		reads Item (Purchase User) builds the draft."""
		self._submitted_card()
		frappe.set_user(self._manager(roles=("Card Manager", "Accounts Manager", "Purchase User")))
		invoice = post_month(self.company, "Supplier", self.supplier, "9", "2026")
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Purchase Invoice", invoice))

	def test_unknown_company_is_refused(self):
		frappe.set_user(self._manager())
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to build postings"):
			post_month("TEST-NO-SUCH-CO-" + self.token, "Supplier", self.supplier, "9", "2026")
