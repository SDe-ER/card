# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""F2: the stock hint of the needs review is read with the user's own ERPNext rights and is
never stored on the review, so a reader without stock rights (Card User) cannot see stock in
the form, REST, report view or the Equipment Needs Summary report."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from card import materials
from card.tests import test_v4_materials as v4
from card.tests.test_controllers import _ensure_masters

CHILD = "Equipment Needs Review Item"


class TestF2StockHint(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	# the v4 materials builders (functions, not the test class, so its tests do not run twice)
	setUp = v4.TestV4Materials.setUp
	tearDown = v4.TestV4Materials.tearDown
	_user = v4.TestV4Materials._user
	_operator = v4.TestV4Materials._operator
	_equipment = v4.TestV4Materials._equipment
	_item = v4.TestV4Materials._item
	_ask = v4.TestV4Materials._ask
	_review = v4.TestV4Materials._review

	def _bin(self, item_code, warehouse, qty):
		frappe.get_doc(
			{"doctype": "Bin", "item_code": item_code, "warehouse": warehouse, "actual_qty": qty}
		).insert(ignore_permissions=True)

	def _pulled_review(self):
		self._bin(self.filter, self.store, 5)
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 2}])
		review = self._review()
		line = next(row for row in review.items if row.item_code == self.filter)
		return review, line

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def test_stock_hint_needs_stock_permission(self):
		self._bin(self.filter, self.store, 5)
		self.assertEqual(materials.stock_qty(self.filter, self.store), 5)
		card_user = self._user("cu", ["Card User"])
		self.assertIsNone(self._as(card_user, materials.stock_qty, self.filter, self.store))
		self.assertIsNone(self._as(card_user, materials.stock_qty, self.filter))

	def test_stock_hint_keeps_warehouse_user_permissions(self):
		self._bin(self.filter, self.store, 5)
		self._bin(self.filter, self.custody, 7)
		stock_user = self._user("su", ["Card User", "Stock User"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": stock_user, "allow": "Warehouse", "for_value": self.store}
		).insert(ignore_permissions=True)
		self.assertEqual(self._as(stock_user, materials.stock_qty, self.filter), 5)
		# a warehouse he may not see has no hint (not a false 0)
		self.assertIsNone(self._as(stock_user, materials.stock_qty, self.filter, self.custody))

	def test_stock_hint_stays_in_the_users_companies(self):
		other = frappe.db.get_value(
			"Warehouse", {"company": ["!=", self.company], "is_group": 0}, ["name", "company"], as_dict=True
		)
		if not other:
			self.skipTest("the test site needs a warehouse of a second company")
		self._bin(self.filter, self.store, 5)
		self._bin(self.filter, other.name, 7)
		self.assertEqual(materials.stock_qty(self.filter), 12)
		self.assertEqual(materials.stock_qty(self.filter, companies=[self.company]), 5)
		stock_user = self._user("sc", ["Card User", "Stock User"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": stock_user, "allow": "Company", "for_value": self.company}
		).insert(ignore_permissions=True)
		self.assertEqual(self._as(stock_user, materials.stock_qty, self.filter), 5)
		self.assertIsNone(self._as(stock_user, materials.stock_qty, self.filter, other.name))

	def test_shared_bin_does_not_open_stock(self):
		self._bin(self.filter, self.store, 5)
		card_user = self._user("sh", ["Card User"])
		bin_name = frappe.db.get_value("Bin", {"item_code": self.filter, "warehouse": self.store})
		frappe.share.add("Bin", bin_name, card_user, read=1, notify=0)
		self.assertIsNone(self._as(card_user, materials.stock_qty, self.filter))

	def test_review_line_does_not_store_stock(self):
		review, line = self._pulled_review()
		self.assertEqual(frappe.db.get_value(CHILD, line.name, "stock_qty"), 0)
		card_user = self._user("cu", ["Card User"])

		def rest():
			return frappe.client.get("Equipment Needs Review", review.name)

		def desk():
			from frappe.desk.form.load import getdoc

			frappe.response.docs = []
			getdoc("Equipment Needs Review", review.name)
			return frappe.response.docs[0].as_dict()

		def report_view():
			return frappe.get_list(
				"Equipment Needs Review",
				filters={"name": review.name},
				fields=[f"`tab{CHILD}`.stock_qty as stock_qty"],
			)

		for got in (self._as(card_user, rest), self._as(card_user, desk)):
			row = next(r for r in got.get("items") if r.get("name") == line.name)
			self.assertFalse(row.get("stock_qty"))
		self.assertTrue(all(not r.stock_qty for r in self._as(card_user, report_view)))

	def test_review_stock_is_live_with_the_readers_rights(self):
		review, line = self._pulled_review()
		self.assertEqual(materials.review_stock(review.name)[line.name], 5)
		card_user = self._user("cu", ["Card User"])
		self.assertEqual(self._as(card_user, materials.review_stock, review.name), {})
		operator = self._user("opx", ["Card Operator"])
		with self.assertRaises(frappe.PermissionError):
			self._as(operator, materials.review_stock, review.name)

	def test_needs_summary_shows_stock_only_with_stock_rights(self):
		from card.card.report.equipment_needs_summary.equipment_needs_summary import execute

		review, _line = self._pulled_review()
		review.submit()

		def stock_in_report():
			rows = execute({"project": self.project})[1]
			return next(r["stock_qty"] for r in rows if r["item_code"] == self.filter)

		self.assertEqual(stock_in_report(), 5)
		card_user = self._user("cu", ["Card User"])
		columns, rows = self._as(card_user, execute, {"project": self.project})
		# the column and every value are removed, not only hidden
		self.assertNotIn("stock_qty", [c["fieldname"] for c in columns])
		self.assertTrue(rows and all("stock_qty" not in r for r in rows))

	def test_patch_clears_stored_stock_and_counts_history(self):
		from card.patches.v4_0_0 import clear_review_stock_qty as patch

		_review, line = self._pulled_review()
		frappe.db.set_value(CHILD, line.name, "stock_qty", 9, update_modified=False)
		patch.execute()
		self.assertEqual(frappe.db.get_value(CHILD, line.name, "stock_qty"), 0)
		patch.execute()  # idempotent
		self.assertEqual(frappe.db.get_value(CHILD, line.name, "stock_qty"), 0)
		changed = {"row_changed": [["items", 1, "x", [["stock_qty", 0, 5]]]]}
		added = {"added": [["items", {"name": "x", "stock_qty": 5}]]}
		other = {"row_changed": [["items", 1, "x", [["found_qty", 0, 1]]]]}
		self.assertTrue(patch.version_carries_stock(json.dumps(changed)))
		self.assertTrue(patch.version_carries_stock(json.dumps(added)))
		self.assertFalse(patch.version_carries_stock(json.dumps(other)))
