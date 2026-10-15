# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Permission-matrix tests for the CARD app. Read-only: they inspect the
DocType meta permission rows and Report role rows, no records are created."""

import frappe
from frappe.tests import IntegrationTestCase

REPORTS = (
	"Equipment Supplier Statement",
	"Equipment Suppliers Summary",
	"Equipment Customer Statement",
	"Equipment Customers Summary",
	"Equipment Diesel Consumption",
	"Transport Cost by Project",
	"Operating Cost by Project",
)


def _cmc_perms():
	return {p.role: p for p in frappe.get_meta("Card Monthly Card").permissions}


class TestCardPermissions(IntegrationTestCase):
	def test_roles_present_in_card_monthly_card(self):
		roles = set(_cmc_perms())
		self.assertTrue({"System Manager", "Card Manager", "Card User", "Accounts Manager"} <= roles)

	def test_card_user_cannot_submit_cmc(self):
		perms = _cmc_perms()
		self.assertEqual(perms["Card User"].submit or 0, 0)
		self.assertEqual(perms["Card Manager"].submit, 1)
		self.assertEqual(perms["Card Manager"].cancel, 1)

	def test_accounts_manager_readonly_on_cmc(self):
		row = _cmc_perms()["Accounts Manager"]
		self.assertEqual(row.read, 1)
		self.assertEqual(row.write or 0, 0)
		self.assertEqual(row.submit or 0, 0)

	def test_reports_have_card_roles(self):
		for name in REPORTS:
			roles = {r.role for r in frappe.get_doc("Report", name).roles}
			self.assertIn("Card Manager", roles, name)
			self.assertIn("Card User", roles, name)
