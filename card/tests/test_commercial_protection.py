# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v1.2.2 A3: equipment commercial terms (rates, rate basis, daily hours,
direction, parties, contract, fuel) are permlevel 1 — written by Card Manager,
read-only for Card User — and every change needs a new reason, kept in the
document history. Enforced server-side (REST included)."""

import json

import frappe
from frappe.client import set_value

from card.tests.test_customer import RENTED, _CustomerCardsBase


class TestCommercialProtection(_CustomerCardsBase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _login(self, roles):
		email = f"cp-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Commercial",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		return email

	def test_card_user_cannot_change_a_rate_even_through_rest(self):
		eq = self._equipment(RENTED)
		self._login(["Card User"])
		self.assertFalse(frappe.has_permission("Card Equipment", "create"))
		try:
			set_value("Card Equipment", eq.name, "rate", 999)
		except (frappe.PermissionError, frappe.ValidationError):
			pass
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "rate"), 750)

	def test_card_manager_changes_need_a_new_reason(self):
		eq = self._equipment(RENTED)
		self._login(["Card Manager"])
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.rate = 800
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			doc.save()
		# a refused save leaves the in-memory doc stale (timestamp): reload it
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.rate = 800
		doc.commercial_change_reason = "Contract renewal 2026"
		doc.save()
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "rate"), 800)
		version = frappe.get_all(
			"Version",
			filters={"ref_doctype": "Card Equipment", "docname": eq.name},
			fields=["data", "owner"],
			order_by="creation desc",
			limit=1,
		)[0]
		changed = {row[0] for row in json.loads(version.data).get("changed", [])}
		self.assertTrue({"rate", "commercial_change_reason"} <= changed)
		self.assertEqual(version.owner, frappe.session.user)
		# the same reason cannot cover the next change
		doc.reload()
		doc.customer_rate = 1234
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			doc.save()

	def test_non_commercial_change_needs_no_reason(self):
		eq = self._equipment(RENTED)
		self._login(["Card Manager"])
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.equipment_name = doc.equipment_name + "-renamed"
		doc.save()
