# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""O2a tests: owned Card Equipment <-> official ERPNext Asset link.

Creating a real Asset needs a fixed-asset Item + Asset Category + Location; when the
test site cannot provide them the Asset-dependent tests skip with a clear reason
instead of failing."""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card.api import create_equipment_from_asset, get_asset_prefill, get_only_company
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

	def test_prefill_takes_asset_details(self):
		asset = self._make_asset()
		frappe.db.set_value(
			"Asset",
			asset,
			{"insurer": "TEST-INSURER", "policy_number": "POL-1", "insurance_end_date": "2030-01-31"},
		)
		values = get_asset_prefill(asset)
		self.assertEqual(values["insurance_company"], "TEST-INSURER")
		self.assertEqual(values["insurance_policy_no"], "POL-1")
		self.assertEqual(str(values["insurance_expiry"]), "2030-01-31")
		self.assertEqual(values["company"], self._m["company"])
		doc = create_equipment_from_asset(asset)
		self.assertEqual(doc.get("operator_on"), "الشركة")
		self.assertEqual(doc.get("الوقود_على"), "الشركة")
		self.assertEqual(doc.get("insurance_policy_no"), "POL-1")

	def test_fields_stay_in_their_tabs(self):
		# Owner 2026-10-19: Asset next to ownership, documents second, everything else in its own tab
		meta = frappe.get_meta("Card Equipment")
		order = [f.fieldname for f in meta.fields]
		self.assertEqual(order.index("الأصل_في_erpnext"), order.index("rental_direction") + 1)
		tabs = [f for f in order if meta.get_field(f).fieldtype == "Tab Break"]
		self.assertEqual(tabs[:2], ["basic_tab", "documents_tab"])

		def tab_of(fieldname):
			return [t for t in tabs if order.index(t) < order.index(fieldname)][-1]

		expected = {
			"operator": "operation_tab",
			"cost_center": "operation_tab",
			"daily_hours": "cost_tab",
			"tank_capacity": "meter_tab",
			"daily_diesel_consumption": "meter_tab",
			"service_interval_hours": "meter_tab",
		}
		for fieldname, tab in expected.items():
			self.assertEqual(tab_of(fieldname), tab, fieldname)
		self.assertFalse([f.fieldname for f in meta.fields if f.description])

	def test_only_company_fills_when_single(self):
		with patch("card.company.frappe.get_list", return_value=["A"]):
			self.assertEqual(get_only_company(), "A")
		with patch("card.company.frappe.get_list", return_value=["A", "B"]):
			self.assertIsNone(get_only_company())
		with patch("card.company.frappe.get_list", return_value=[]):
			self.assertIsNone(get_only_company())

	def test_asset_owns_equipment_details(self):
		# Owner 2026-10-19: picking the Asset fills the details; the type follows its category
		asset = self._make_asset()
		category = frappe.db.get_value("Asset", asset, "asset_category")
		# the site may already map this category; the test owns the mapping (rolled back)
		for other in frappe.get_all("Card Equipment Type", {"asset_category": category}, pluck="name"):
			frappe.db.set_value("Card Equipment Type", other, "asset_category", None)
		frappe.db.set_value("Card Equipment Type", self._m["etype"], "asset_category", category)
		other_type = frappe.db.get_value("Card Equipment Type", {"name": ["!=", self._m["etype"]]}, "name")
		eq = self._make_equipment(
			equipment_name="TYPED",
			equipment_type=other_type or self._m["etype"],
			**{"الأصل_في_erpnext": asset},
		)
		self.assertEqual(eq.equipment_name, frappe.db.get_value("Asset", asset, "asset_name"))
		self.assertEqual(eq.equipment_type, self._m["etype"])
		self.assertEqual(eq.equipment_type_from_asset, 1)
		self.assertEqual(get_asset_prefill(asset)["equipment_type"], self._m["etype"])

		dup = frappe.get_doc("Card Equipment Type", other_type) if other_type else None
		if dup:
			dup.asset_category = category
			with self.assertRaises(frappe.ValidationError):
				dup.save(ignore_permissions=True)

	def test_details_read_only_when_linked(self):
		meta = frappe.get_meta("Card Equipment")
		for fieldname in ("equipment_name", "brand", "model", "manufacture_year", "serial_no", "plate_no"):
			self.assertIn("الأصل_في_erpnext", meta.get_field(fieldname).read_only_depends_on or "", fieldname)
		self.assertEqual(
			meta.get_field("equipment_type").read_only_depends_on, "eval:doc.equipment_type_from_asset"
		)

	def test_sync_patch_updates_linked_equipment(self):
		from card.patches.v3_0_0 import sync_equipment_from_asset

		asset = self._make_asset()
		eq = self._make_equipment(**{"الأصل_في_erpnext": asset})
		frappe.db.set_value("Card Equipment", eq.name, "equipment_name", "OLD NAME")
		sync_equipment_from_asset.execute()
		asset_name = frappe.db.get_value("Asset", asset, "asset_name")
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "equipment_name"), asset_name)
		sync_equipment_from_asset.execute()  # idempotent
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "equipment_name"), asset_name)
