# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v1.2.2 A6: Card Settings grants Accounts Manager permlevel-1 write (the
per-company accounting fields of Card Company Settings) but only level-0 read.
Prove what an Accounts Manager can actually save, and that policy fields
(level 0) stay out of reach."""

import frappe
from frappe.tests import IntegrationTestCase

from card.tests.test_controllers import _ensure_masters


class TestSettingsPermlevel(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _accounts_manager(self):
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
		return email

	def _row(self, settings):
		company = self._m["company"]
		row = next((r for r in settings.get("company_settings") or [] if r.company == company), None)
		if row is None:
			row = settings.append("company_settings", {"company": company})
			settings.save(ignore_permissions=True)
			settings.reload()
			row = next(r for r in settings.company_settings if r.company == company)
		return row

	def test_accounts_manager_saves_company_accounting_fields(self):
		settings = frappe.get_doc("Card Settings")
		row = self._row(settings)
		cost_center = frappe.db.get_value("Cost Center", {"company": row.company, "is_group": 0}, "name")
		frappe.set_user(self._accounts_manager())
		settings = frappe.get_doc("Card Settings")
		row = self._row(settings)
		row.cost_center = cost_center
		settings.save()
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(
				"Card Company Settings", {"parent": "Card Settings", "company": row.company}, "cost_center"
			),
			cost_center,
		)

	def test_accounts_manager_cannot_change_policy_fields(self):
		before = frappe.db.get_single_value("Card Settings", "reconciliation_tolerance")
		frappe.set_user(self._accounts_manager())
		settings = frappe.get_doc("Card Settings")
		settings.reconciliation_tolerance = (before or 0) + 999
		try:
			settings.save()
		except frappe.PermissionError:
			pass
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_single_value("Card Settings", "reconciliation_tolerance"), before)
