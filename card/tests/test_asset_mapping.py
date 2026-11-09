# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Maintenance plan M1 (Owner approval 2026-10-31): minimum-input "Create from Asset" with duplicate prevention,
owned / third-party / rented kept apart (a rented machine never gets an Asset; no Asset is ever created), and the
read-only Asset Mapping Review that classifies every Asset for an Owner decision (nothing is created for it)."""

import re

import frappe
from frappe.tests import IntegrationTestCase

from card.api import create_equipment_from_asset
from card.tests import test_asset_link as link_tests
from card.tests.test_asset_link import ASSET_CATEGORY, LINK
from card.tests.test_controllers import _ensure_masters


class TestAssetMapping(IntegrationTestCase):
	# the Asset fixtures of the O2a link tests (methods only; the module is imported, not the class, so its
	# tests are not collected twice)
	_fixed_asset_account = link_tests.TestAssetLink._fixed_asset_account
	_asset_masters = link_tests.TestAssetLink._asset_masters
	_make_asset = link_tests.TestAssetLink._make_asset
	_make_equipment = link_tests.TestAssetLink._make_equipment
	_user = link_tests.TestAssetLink._user

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _map_category(self):
		"""An equipment type for the test Asset category (one type per category)."""
		self._asset_masters()
		existing = frappe.db.get_value("Card Equipment Type", {"asset_category": ASSET_CATEGORY}, "name")
		if existing:
			return existing
		return (
			frappe.get_doc(
				{
					"doctype": "Card Equipment Type",
					"equipment_type_name": "TEST-M1-TYPE-" + frappe.generate_hash(length=6),
					"asset_category": ASSET_CATEGORY,
					"equipment_category": frappe.db.get_value(
						"Card Equipment Type", self._m["etype"], "equipment_category"
					),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _default_hours(self, hours):
		frappe.db.set_single_value("Card Settings", "default_daily_hours", hours)
		frappe.clear_document_cache("Card Settings", "Card Settings")

	# ---- Create from Asset: one input when nothing else is needed
	def test_owned_machine_is_created_from_its_asset_in_one_step(self):
		etype = self._map_category()
		self._default_hours(10)
		asset = self._make_asset()
		assets_before = frappe.db.count("Asset")
		result = create_equipment_from_asset(asset, save=1)
		eq = frappe.get_doc("Card Equipment", result["name"])
		self.assertEqual(
			(eq.get(LINK), eq.ownership, eq.equipment_type, eq.daily_hours), (asset, "ملك", etype, 10)
		)
		self.assertEqual(frappe.db.count("Asset"), assets_before)  # no Asset is ever created

	def test_the_same_asset_is_never_linked_twice(self):
		self._map_category()
		self._default_hours(10)
		asset = self._make_asset()
		first = create_equipment_from_asset(asset, save=1)["name"]
		with self.assertRaisesRegex(
			frappe.ValidationError, "already linked to equipment " + re.escape(first)
		):
			create_equipment_from_asset(asset, save=1)
		self.assertEqual(frappe.db.count("Card Equipment", {LINK: asset}), 1)

	def test_missing_values_open_the_prefilled_form_instead(self):
		asset = self._make_asset()
		frappe.db.delete("Card Equipment Type", {"asset_category": ASSET_CATEGORY})  # category not mapped
		result = create_equipment_from_asset(asset, save=1)
		self.assertIn("equipment_type", result["missing"])
		self.assertEqual(result.get(LINK), asset)
		self.assertFalse(frappe.db.exists("Card Equipment", {LINK: asset}))

	def test_third_party_machine_keeps_its_ownership_and_needs_its_terms(self):
		self._map_category()
		self._default_hours(10)
		asset = self._make_asset()
		result = create_equipment_from_asset(asset, ownership="طرف ثالث", save=1)
		self.assertEqual(result["ownership"], "طرف ثالث")
		self.assertIn("rental_direction", result["missing"])
		self.assertNotEqual(result.get("operator_on"), "الشركة")
		self.assertFalse(frappe.db.exists("Card Equipment", {LINK: asset}))

	def test_rented_equipment_is_never_linked_to_an_asset(self):
		asset = self._make_asset()
		with self.assertRaisesRegex(frappe.ValidationError, "rented equipment has no Asset"):
			create_equipment_from_asset(asset, ownership="إيجار", save=1)

	def test_creating_needs_the_equipment_create_right(self):
		self._map_category()
		self._default_hours(10)
		asset = self._make_asset()
		frappe.set_user(self._user(["Accounts User"]))
		with self.assertRaises(frappe.PermissionError):
			create_equipment_from_asset(asset, save=1)

	# ---- Asset Mapping Review: one row per Asset, a decision per Asset, nothing created
	def _review(self, **filters):
		from card.card.report.asset_mapping_review.asset_mapping_review import execute

		return execute({"company": self._m["company"], "show": "All", **filters})

	def test_review_classifies_each_asset_and_creates_nothing(self):
		self._map_category()
		linked_asset = self._make_asset()
		free_asset = self._make_asset()
		self._make_equipment(**{LINK: linked_asset})
		owned_without_asset = self._make_equipment()
		counts = (frappe.db.count("Asset"), frappe.db.count("Card Equipment"))
		_c, rows, *_ = self._review()
		by_asset = {r["asset"]: r for r in rows if r["asset"]}
		self.assertEqual(by_asset[linked_asset]["review"], "Linked")
		self.assertTrue(by_asset[free_asset]["review"].startswith("Not in CARD"))
		self.assertTrue(by_asset[free_asset]["suggested_type"])
		self.assertIn(owned_without_asset.name, {r["equipment"] for r in rows if not r["asset"]})
		self.assertEqual((frappe.db.count("Asset"), frappe.db.count("Card Equipment")), counts)

	def test_review_flags_a_possible_identity_conflict(self):
		asset = self._make_asset()
		frappe.db.set_value("Asset", asset, "asset_name", "TEST-GEN C13-1")
		frappe.rename_doc("Asset", asset, "TEST-C15-1-GEN", force=True)
		_c, rows, *_ = self._review()
		row = {r["asset"]: r for r in rows if r["asset"]}["TEST-C15-1-GEN"]
		self.assertIn("C15 / C13", row["note"])

	def test_review_needs_its_role(self):
		frappe.set_user(self._user(["Card User"]))
		with self.assertRaises(frappe.PermissionError):
			self._review()
