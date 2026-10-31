# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.1.2: an Equipment Transport saved without ownership (or, for a rented machine, without
the equipment supplier) takes them from its first machine; values the user picked are kept.
Display only: neither field feeds the posting. Everything is rolled back."""

import frappe
from frappe.tests import IntegrationTestCase

from card.constants import OWNED
from card.tests.test_controllers import _ensure_masters

RENTED = "إيجار"


class TestTransportOwnershipDefault(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.sup = self._supplier("EQ")

	def tearDown(self):
		frappe.db.rollback()

	def _supplier(self, suffix):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = f"TEST-OWNDEF-SUP-{suffix}-{self.token}"
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _equipment(self, ownership, supplier=None):
		eq = frappe.new_doc("Card Equipment")
		eq.company = self.company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = f"TEST-OWNDEF-EQ-{frappe.generate_hash(length=6)}"
		eq.ownership = ownership
		eq.supplier = supplier
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _transport(self, equipment, **values):
		return frappe.get_doc(
			{
				"doctype": "Equipment Transport",
				"company": self.company,
				"destination_type": "Workshop",
				"payer": "Equipment Supplier",
				"cost_bearer": "Equipment Supplier",
				"items": [{"card_equipment": equipment}],
				**values,
			}
		)

	def _validated(self, doc):
		doc.run_method("validate")
		return doc

	def test_rented_machine_fills_ownership_and_supplier(self):
		doc = self._validated(self._transport(self._equipment(RENTED, self.sup)))
		self.assertEqual((doc.ownership, doc.equipment_supplier), (RENTED, self.sup))

	def test_owned_machine_fills_ownership_only(self):
		doc = self._validated(self._transport(self._equipment(OWNED)))
		self.assertEqual((doc.ownership, doc.equipment_supplier), (OWNED, None))

	def test_values_picked_by_the_user_are_kept(self):
		other = self._supplier("OTHER")
		doc = self._validated(
			self._transport(self._equipment(RENTED, self.sup), ownership=RENTED, equipment_supplier=other)
		)
		self.assertEqual(doc.equipment_supplier, other)
