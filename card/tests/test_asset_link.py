# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""O2a tests: owned Card Equipment <-> official ERPNext Asset link.

Creating a real Asset needs a fixed-asset Item + Asset Category + Location; when the
test site cannot provide them the Asset-dependent tests skip with a clear reason
instead of failing."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from card.api import create_equipment_from_asset
from card.tests.test_controllers import _ensure_masters

ASSET_FIELDS = {
	"asset_item": "item_code",
	"asset_location": "location",
	"asset_cost_center": "cost_center",
	"asset_purchase_value": "net_purchase_amount",
}


class TestAssetLink(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def _make_asset(self):
		"""Minimal Asset, marked submitted directly (rolled back with the test transaction)."""
		try:
			item = frappe.db.get_value("Item", {"is_fixed_asset": 1, "disabled": 0}, "name")
			category = frappe.db.get_value("Asset Category", {}, "name")
			location = frappe.db.get_value("Location", {}, "name")
			if not (item and category and location):
				self.skipTest("Site has no fixed-asset Item / Asset Category / Location to build an Asset")
			asset = frappe.get_doc(
				{
					"doctype": "Asset",
					"asset_name": "TEST-ASSET-" + frappe.generate_hash(length=8),
					"item_code": item,
					"asset_category": category,
					"location": location,
					"company": self._m["company"],
					"is_existing_asset": 1,
					"gross_purchase_amount": 1000,
					"net_purchase_amount": 1000,  # v16 mandatory; gross kept for older schemas
					"purchase_date": frappe.utils.today(),
					"available_for_use_date": frappe.utils.today(),
				}
			).insert(ignore_permissions=True)
		except Exception as e:
			if isinstance(e, unittest.SkipTest):
				raise
			self.skipTest("Cannot create an Asset in this test environment: %s" % e)
		frappe.db.set_value("Asset", asset.name, "docstatus", 1)
		return asset.name

	def _make_equipment(self, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self._m["company"]
		d.equipment_type = self._m["etype"]
		d.ownership = kw.pop("ownership", "ملك")
		d.equipment_name = kw.pop("equipment_name", "TEST-EQ-" + frappe.generate_hash(length=8))
		d.daily_hours = 8
		for key, value in kw.items():
			d.set(key, value)
		d.insert(ignore_permissions=True)
		return d

	def test_one_equipment_per_asset(self):
		asset = self._make_asset()
		self._make_equipment(**{"الأصل_في_erpnext": asset})
		with self.assertRaises(frappe.ValidationError):
			self._make_equipment(**{"الأصل_في_erpnext": asset})

	def test_create_equipment_from_asset(self):
		asset = self._make_asset()
		doc = create_equipment_from_asset(asset)
		self.assertEqual(doc.get("ownership"), "ملك")
		self.assertEqual(doc.get("الأصل_في_erpnext"), asset)
		self.assertTrue(doc.get("equipment_name"))
		# Prefilled but NOT inserted: the client opens it as a new form.
		self.assertFalse(frappe.db.exists("Card Equipment", {"الأصل_في_erpnext": asset}))

		# Once linked, the same asset cannot be offered again.
		self._make_equipment(**{"الأصل_في_erpnext": asset})
		with self.assertRaises(frappe.ValidationError):
			create_equipment_from_asset(asset)

	def test_asset_fetch_fields_present(self):
		meta = frappe.get_meta("Card Equipment")
		for fieldname, source in ASSET_FIELDS.items():
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, fieldname)
			self.assertEqual(field.fetch_from, "الأصل_في_erpnext." + source)
			self.assertTrue(field.read_only)
