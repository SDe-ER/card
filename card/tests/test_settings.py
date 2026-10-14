# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Tests for the Card Settings container and the first-run guard helper
(app-level so Frappe does not auto-build dependency test records). All
changes are rolled back by the test transaction."""

import frappe
from frappe.tests import IntegrationTestCase

from card.accounting_settings import get_company_settings, is_accounting_enabled
from card.tests.test_controllers import _ensure_masters


class TestCardSettings(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def _settings(self):
		doc = frappe.get_single("Card Settings")
		doc.set("company_settings", [])
		return doc

	def test_guard_throws_when_no_company_settings(self):
		doc = self._settings()
		doc.enable_accounting = 0
		doc.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			get_company_settings(self._m["company"])
		self.assertIsNone(get_company_settings(self._m["company"], throw=False))

	def test_guard_returns_row_when_present(self):
		doc = self._settings()
		doc.append("company_settings", {"company": self._m["company"]})
		doc.save(ignore_permissions=True)
		row = get_company_settings(self._m["company"])
		self.assertEqual(row.company, self._m["company"])

	def test_is_accounting_enabled_default_false(self):
		doc = self._settings()
		doc.enable_accounting = 0
		doc.save(ignore_permissions=True)
		self.assertFalse(is_accounting_enabled())

	def test_duplicate_company_rejected(self):
		doc = self._settings()
		doc.append("company_settings", {"company": self._m["company"]})
		doc.append("company_settings", {"company": self._m["company"]})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
