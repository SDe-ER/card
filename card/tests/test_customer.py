# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Customer side (phase E): card direction model, customer rate snapshot and
submit guards. CARD stores no customer balances — the official Sales Invoice
is created in S3; here only the operational classification and the accrued
customer amount on the card are proven. All data is per-test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.doctype.card_monthly_card.card_monthly_card import (
	DIR_INTERNAL,
	DIR_RENTED_IN,
	DIR_RENTED_OUT,
	DIR_SUBRENTAL,
)
from card.tests.test_controllers import _days, _ensure_masters

OWNED = "ملك"
RENTED = "إيجار"


def _leaf(doctype, name_field, root):
	"""A non-group row of a tree master (Customer needs leaf group/territory)."""
	leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if leaf:
		return leaf
	leaf = "Test " + doctype
	if not frappe.db.exists(doctype, leaf):
		frappe.get_doc(
			{"doctype": doctype, name_field: leaf, "parent_" + frappe.scrub(doctype): root, "is_group": 0}
		).insert(ignore_permissions=True)
	return leaf


class TestCardDirection(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-CUST-PRJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-CUST-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		cust = frappe.new_doc("Customer")
		cust.customer_name = "TEST-CUST-" + self.token
		cust.customer_group = _leaf("Customer Group", "customer_group_name", "All Customer Groups")
		cust.territory = _leaf("Territory", "territory_name", "All Territories")
		cust.insert(ignore_permissions=True)
		self.customer = cust.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _equipment(self, ownership=RENTED, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = ownership
		d.equipment_name = "TEST-CUST-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		if ownership != OWNED:
			d.supplier = self.supplier
		for k, v in kw.items():
			setattr(d, k, v)
		d.insert(ignore_permissions=True)
		return d

	def _card(self, eq, hours_list, customer=None, direction=None,
			customer_rate=None, customer_rate_type=None, submit=False):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		if customer:
			c.customer = customer
		if direction:
			c.card_direction = direction
		if customer_rate is not None:
			c.customer_rate = customer_rate
			c.customer_rate_type = customer_rate_type or "باليوم"
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	# ---- 1. the four directions derive correctly ----
	def test_internal_default_for_owned_without_customer(self):
		card = self._card(self._equipment(OWNED), [10, 10], submit=True)
		self.assertEqual(card.card_direction, DIR_INTERNAL)
		self.assertEqual(flt(card.amount), 0)  # no supplier billing (existing rule)
		self.assertEqual(flt(card.customer_amount), 0)  # no customer billing
		self.assertFalse(card.customer)

	def test_rented_in_default_for_rented_without_customer(self):
		card = self._card(self._equipment(), [10, 10], submit=True)
		self.assertEqual(card.card_direction, DIR_RENTED_IN)
		self.assertEqual(flt(card.net_amount), flt(20 * 75.0, 2))  # supplier side unchanged
		self.assertEqual(flt(card.customer_amount), 0)

	def test_rented_out_bills_customer(self):
		# owned equipment to a customer: 1000/day over 10h = 100/h; 20h -> 2000
		eq = self._equipment(OWNED)
		card = self._card(eq, [10, 10], customer=self.customer, customer_rate=1000, submit=True)
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertEqual(flt(card.amount), 0)  # still no supplier billing
		self.assertEqual(flt(card.customer_amount), 2000.0)
		self.assertEqual(flt(card.customer_rate_used), 100.0)  # snapshot on submit

	def test_sub_rental_bills_both_sides(self):
		# rented at 750/day (75/h), rented out at 1200/day (120/h); 10h
		eq = self._equipment()
		card = self._card(eq, [10], customer=self.customer, customer_rate=1200, submit=True)
		self.assertEqual(card.card_direction, DIR_SUBRENTAL)
		self.assertEqual(flt(card.net_amount), 750.0)  # supplier side (our cost)
		self.assertEqual(flt(card.customer_amount), 1200.0)  # customer side (our price)
		self.assertEqual(flt(card.hourly_rate_used), 75.0)
		self.assertEqual(flt(card.customer_rate_used), 120.0)

	# ---- 2. guards ----
	def test_billing_direction_requires_customer_on_submit(self):
		eq = self._equipment(OWNED)
		card = self._card(eq, [10], direction=DIR_RENTED_OUT)  # draft without customer is fine
		self.assertEqual(card.docstatus, 0)
		with self.assertRaises(frappe.ValidationError):
			card.submit()

	def test_direction_must_match_ownership(self):
		with self.assertRaises(frappe.ValidationError):
			self._card(self._equipment(OWNED), [10], direction=DIR_RENTED_IN)
		with self.assertRaises(frappe.ValidationError):
			self._card(self._equipment(), [10], direction=DIR_INTERNAL)

	def test_non_billing_direction_clears_customer(self):
		# explicitly internal + a customer: the customer is dropped, nothing billed
		card = self._card(self._equipment(OWNED), [10], customer=self.customer, direction=DIR_INTERNAL)
		self.assertFalse(card.customer)
		self.assertEqual(flt(card.customer_amount), 0)

	# ---- 3. customer rate from equipment default ----
	def test_customer_rate_defaults_from_equipment(self):
		eq = self._equipment(OWNED, customer_rate_type="بالساعة", customer_rate=90)
		card = self._card(eq, [10], customer=self.customer, submit=True)
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertEqual(flt(card.customer_amount), 900.0)  # 10h * 90/h fetched from equipment
		self.assertEqual(flt(card.customer_rate_used), 90.0)

	# ---- 4. backfill patch classifies pre-E cards ----
	def test_backfill_patch(self):
		from card.patches.v1_2.backfill_card_direction import execute

		owned = self._card(self._equipment(OWNED), [10])
		rented = self._card(self._equipment(), [10])
		for name in (owned.name, rented.name):  # simulate pre-E rows
			frappe.db.set_value("Card Monthly Card", name, "card_direction", None, update_modified=False)
		execute()
		self.assertEqual(frappe.db.get_value("Card Monthly Card", owned.name, "card_direction"), DIR_INTERNAL)
		self.assertEqual(frappe.db.get_value("Card Monthly Card", rented.name, "card_direction"), DIR_RENTED_IN)
