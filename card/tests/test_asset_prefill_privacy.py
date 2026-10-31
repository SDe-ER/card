# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Financial privacy of the Asset prefill (Owner decision 2026-10-31, after FR-096): the values CARD sends to the
equipment form from an Asset follow the equipment's field levels. A user without level 2 never receives the cost
center (or another restricted field) through Create from Asset or the Asset fill; authorized users still do; what
is saved stays complete."""

import frappe
from frappe.tests import IntegrationTestCase

from card.api import _readable_equipment_values, create_equipment_from_asset, get_asset_prefill
from card.field_privacy import restricted_fields
from card.tests import test_asset_link as link_tests
from card.tests import test_asset_mapping as mapping_tests
from card.tests.test_asset_link import LINK
from card.tests.test_controllers import _ensure_masters

# Quality Manager reads Assets in ERPNext: an operational user who may open the Asset itself
ASSET_READER = "Quality Manager"


class TestAssetPrefillPrivacy(IntegrationTestCase):
	# fixtures of the O2a link and M1 mapping tests (modules imported, so their tests are not collected twice)
	_fixed_asset_account = link_tests.TestAssetLink._fixed_asset_account
	_asset_masters = link_tests.TestAssetLink._asset_masters
	_make_asset = link_tests.TestAssetLink._make_asset
	_user = link_tests.TestAssetLink._user
	_other_company = link_tests.TestAssetLink._other_company
	_map_category = mapping_tests.TestAssetMapping._map_category
	_default_hours = mapping_tests.TestAssetMapping._default_hours

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _as(self, roles, company=None):
		frappe.set_user(self._user(roles, restrict=company or self._m["company"]))

	def _restricted(self):
		fields = restricted_fields("Card Equipment", level=2)
		self.assertIn("cost_center", fields)
		return fields

	def test_operational_user_never_receives_the_asset_cost_center(self):
		asset = self._make_asset()
		restricted = self._restricted()
		for roles in (["Card User", ASSET_READER], ["Card Supervisor", ASSET_READER]):
			with self.subTest(roles=roles):
				self._as(roles)
				prefill = get_asset_prefill(asset)
				self.assertTrue(prefill.get("equipment_name"))  # the non-financial values still fill the form
				for field in restricted:
					self.assertNotIn(field, prefill, f"{roles} {field}")
				frappe.set_user("Administrator")

	def test_supervisor_receives_only_level_zero_values(self):
		asset = self._make_asset()
		self._as(["Card Supervisor", ASSET_READER])
		prefill = get_asset_prefill(asset)
		self.assertNotIn("company", prefill)  # level 1 on the equipment

	def test_create_from_asset_form_follows_the_field_levels(self):
		"""Only Card Manager and System Manager create equipment on a standard site, and both read level 2; a role
		that may create without level 2 (a site's own role) gets the prefilled form without the restricted
		values. Card User cannot create at all."""
		asset = self._make_asset()
		self._as(["Card User", ASSET_READER])
		with self.assertRaises(frappe.PermissionError):
			create_equipment_from_asset(asset, save=1)
		values = {"equipment_name": "X", "company": self._m["company"], "cost_center": "CC", "missing": []}
		readable = _readable_equipment_values(values)
		self.assertEqual(readable.get("equipment_name"), "X")
		self.assertEqual(readable.get("company"), self._m["company"])  # level 1: Card User reads it
		for field in (*self._restricted(), "missing"):
			self.assertNotIn(field, readable, field)

	def test_authorized_users_still_receive_the_cost_center(self):
		asset = self._make_asset()
		cost_center = frappe.db.get_value("Asset", asset, "cost_center")
		self.assertTrue(cost_center)
		for roles in (["Card Manager", ASSET_READER], ["Accounts Manager", ASSET_READER]):
			with self.subTest(roles=roles):
				self._as(roles)
				self.assertEqual(get_asset_prefill(asset).get("cost_center"), cost_center)
				frappe.set_user("Administrator")
		frappe.db.delete("Card Equipment Type", {"asset_category": link_tests.ASSET_CATEGORY})
		self._as(["Card Manager", ASSET_READER])
		self.assertEqual(create_equipment_from_asset(asset, save=1).get("cost_center"), cost_center)

	def test_saved_equipment_keeps_the_asset_values(self):
		"""The response is filtered; the record is not: the Asset's cost center and purchase value are still
		stored on the equipment."""
		self._map_category()
		self._default_hours(10)
		asset = self._make_asset()
		self._as(["Card Manager", ASSET_READER])
		result = create_equipment_from_asset(asset, save=1)
		self.assertEqual(set(result), {"name"})
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(
			"Card Equipment", result["name"], ["asset_cost_center", "asset_purchase_value"], as_dict=True
		)
		self.assertEqual(stored.asset_cost_center, frappe.db.get_value("Asset", asset, "cost_center"))
		self.assertEqual(stored.asset_purchase_value, 1000)

	def test_another_company_asset_is_refused(self):
		asset = self._make_asset()
		self._as(["Card Manager", ASSET_READER], company=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			get_asset_prefill(asset)
		with self.assertRaises(frappe.PermissionError):
			create_equipment_from_asset(asset, save=0)

	def test_user_without_asset_read_is_refused(self):
		asset = self._make_asset()
		self._as(["Card User"])
		with self.assertRaises(frappe.PermissionError):
			get_asset_prefill(asset)
