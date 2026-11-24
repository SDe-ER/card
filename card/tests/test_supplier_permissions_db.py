# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-171 security (owner decisions 2026-11-17): the historical supplier of a card is protected at the
database level, for real users with restricted roles. An ordinary CARD user cannot assign an arbitrary
supplier or change the stored one; a Card Manager corrects a Draft only with a reason (kept in the Version
history); a submitted card's beneficiary cannot be changed by anyone through normal CARD editing."""

import frappe

from card.constants import DIR_RENTED_IN
from card.tests.test_controllers import _days
from card.tests.test_s3_config import _AdjBase


class TestSupplierPermissionsDB(_AdjBase):
	def setUp(self):
		super().setUp()
		group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
		self.other = (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": "Test Other Owner " + frappe.generate_hash(length=6),
					"supplier_group": group,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.card_user = self._user("Card User")
		self.manager = self._user("Card Manager")

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _user(self, role):
		email = "card-%s-%s@example.com" % (role.lower().replace(" ", "-"), frappe.generate_hash(length=6))
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Test",
				"send_welcome_email": 0,
				"user_type": "System User",
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		return user.name

	def _draft(self, eq, supplier=None):
		"""A Draft September 2026 card for the equipment, inserted as the current user."""
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		if supplier:
			c.supplier = supplier
		for row in _days([8, 8]):
			c.append("days", row)
		c.insert()
		return c

	def test_card_user_cannot_assign_an_arbitrary_supplier(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		frappe.set_user(self.card_user)
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			self._draft(eq, supplier=self.other)

	def test_card_user_cannot_change_the_historical_supplier(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._draft(eq)  # created as Administrator: the equipment's owner is the historical supplier
		original = card.supplier
		frappe.set_user(self.card_user)
		card = frappe.get_doc("Card Monthly Card", card.name)
		card.supplier = self.other
		card.supplier_correction_reason = "trying to change the owner"
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			card.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "supplier"), original)

	def test_card_manager_corrects_a_draft_with_a_reason_and_the_change_is_in_its_history(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._draft(eq)
		frappe.set_user(self.manager)
		card = frappe.get_doc("Card Monthly Card", card.name)
		card.supplier = self.other
		card.supplier_correction_reason = "Owner entered wrongly on the equipment"
		card.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "supplier"), self.other)
		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Card Monthly Card",
				"reference_name": card.name,
				"comment_type": "Info",
			},
			pluck="content",
		)
		self.assertTrue(any("Owner entered wrongly on the equipment" in (c or "") for c in comments))

	def test_manager_correction_without_a_reason_is_refused(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._draft(eq)
		frappe.set_user(self.manager)
		card = frappe.get_doc("Card Monthly Card", card.name)
		card.supplier = self.other
		with self.assertRaises(frappe.ValidationError):
			card.save()
		frappe.set_user("Administrator")

	def test_nobody_changes_the_beneficiary_of_a_submitted_card(self):
		eq = self._equipment(direction=DIR_RENTED_IN)
		card = self._draft(eq)
		card.submit()
		original = frappe.db.get_value("Card Monthly Card", card.name, "supplier")
		frappe.set_user(self.manager)
		card = frappe.get_doc("Card Monthly Card", card.name)
		card.supplier = self.other
		card.supplier_correction_reason = "posted card"
		with self.assertRaises(frappe.ValidationError):
			card.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "supplier"), original)
