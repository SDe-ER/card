# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-098: the ERPNext Asset owns the master data of its linked Card Equipment.

Mapping (exact copy, empty Asset values keep CARD values), operational values kept,
Asset change hook (history + audit, never blocks the Asset), chassis uniqueness,
disposal/sale gate, read-only Asset view (permissions, financial level) and the
v4.3.0 backfill patch. Fixtures come from test_asset_link and are rolled back; the
optional SDCE Asset custom fields are created once on the test site when missing."""

from unittest.mock import patch

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from card.asset_master import (
	OWNED_LIST_FIELD,
	assert_asset_in_service,
	asset_master_values,
	get_asset_master_view,
	on_asset_change,
)
from card.tests.test_asset_link import TestAssetLink
from card.tests.test_controllers import _ensure_masters

LINK = "الأصل_في_erpnext"
SITE_ASSET_FIELDS = [
	{
		"fieldname": "custom_chassis_no",
		"fieldtype": "Data",
		"label": "Chassis No",
		"insert_after": "asset_name",
	},
	{
		"fieldname": "custom_manufacture_year",
		"fieldtype": "Int",
		"label": "Manufacture Year",
		"insert_after": "custom_chassis_no",
	},
	{
		"fieldname": "custom_engine_no",
		"fieldtype": "Data",
		"label": "Engine No",
		"insert_after": "custom_manufacture_year",
	},
	{
		"fieldname": "custom_customs_fees_sar",
		"fieldtype": "Currency",
		"label": "Customs Fees",
		"insert_after": "custom_engine_no",
	},
]


def _ensure_site_asset_fields():
	meta = frappe.get_meta("Asset")
	missing = [f for f in SITE_ASSET_FIELDS if not meta.has_field(f["fieldname"])]
	if missing:
		for f in missing:
			f["allow_on_submit"] = 1
		create_custom_fields({"Asset": missing}, ignore_validate=True)  # DDL: test site only
		frappe.db.commit()  # nosemgrep: frappe-manual-commit -- the ALTER TABLE has committed already
		frappe.clear_cache(doctype="Asset")


class TestAssetMaster(IntegrationTestCase):
	# the Asset fixtures of the Asset link tests (accounts, category, item, location, users)
	_fixed_asset_account = TestAssetLink._fixed_asset_account
	_asset_masters = TestAssetLink._asset_masters
	_make_asset = TestAssetLink._make_asset
	_user = TestAssetLink._user
	_as = TestAssetLink._as
	_make_equipment = TestAssetLink._make_equipment

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		_ensure_site_asset_fields()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def _asset(self, **values):
		asset = self._make_asset()
		if values:
			frappe.db.set_value("Asset", asset, values)
		return asset

	def _map_category(self, asset):
		category = frappe.db.get_value("Asset", asset, "asset_category")
		for other in frappe.get_all("Card Equipment Type", {"asset_category": category}, pluck="name"):
			frappe.db.set_value("Card Equipment Type", other, "asset_category", None)
		frappe.db.set_value("Card Equipment Type", self._m["etype"], "asset_category", category)

	# ---------- mapping ----------

	def test_link_fills_the_master_fields_exactly(self):
		chassis = " Ab-12 x٣ "  # spaces, case and Arabic digit kept as stored on the Asset
		asset = self._asset(
			custom_chassis_no=chassis, custom_manufacture_year=2015, image="/files/test-eq.png"
		)
		eq = self._make_equipment(**{LINK: asset})
		self.assertEqual(eq.serial_no, chassis)
		self.assertEqual(eq.manufacture_year, 2015)
		self.assertEqual(eq.image, "/files/test-eq.png")
		self.assertEqual(eq.equipment_name, frappe.db.get_value("Asset", asset, "asset_name"))
		owned = eq.get(OWNED_LIST_FIELD).split(",")
		for field in ("equipment_name", "serial_no", "manufacture_year", "image"):
			self.assertIn(field, owned)

	def test_empty_asset_values_keep_card_values(self):
		asset = self._asset(custom_chassis_no="", custom_manufacture_year=0)
		eq = self._make_equipment(
			serial_no="CARD-CH-1", manufacture_year=2001, brand="CARD BRAND", **{LINK: asset}
		)
		self.assertEqual(eq.serial_no, "CARD-CH-1")
		self.assertEqual(eq.manufacture_year, 2001)
		self.assertEqual(eq.brand, "CARD BRAND")  # the Asset item has no brand
		owned = eq.get(OWNED_LIST_FIELD).split(",")
		for field in ("serial_no", "manufacture_year", "brand"):
			self.assertNotIn(field, owned)
		self.assertNotIn("serial_no", asset_master_values(asset))

	def test_unmapped_category_keeps_the_card_type(self):
		asset = self._asset()
		category = frappe.db.get_value("Asset", asset, "asset_category")
		for other in frappe.get_all("Card Equipment Type", {"asset_category": category}, pluck="name"):
			frappe.db.set_value("Card Equipment Type", other, "asset_category", None)
		eq = self._make_equipment(**{LINK: asset})
		self.assertEqual(eq.equipment_type, self._m["etype"])
		self.assertEqual(eq.equipment_type_from_asset, 0)
		self.assertNotIn("equipment_type", eq.get(OWNED_LIST_FIELD).split(","))

	def test_rest_write_of_an_owned_field_is_replaced_by_the_asset_value(self):
		asset = self._asset(custom_chassis_no="ASSET-CH-7")
		eq = self._make_equipment(**{LINK: asset})
		eq.serial_no = "TYPED-OVER"
		eq.save(ignore_permissions=True)
		self.assertEqual(eq.serial_no, "ASSET-CH-7")
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "Card Equipment",
					"reference_name": eq.name,
					"content": ["like", "%TYPED-OVER%"],
				},
			)
		)

	def test_unlinking_keeps_the_values_and_unlocks_them(self):
		asset = self._asset(custom_chassis_no="KEEP-ME")
		eq = self._make_equipment(**{LINK: asset})
		eq.set(LINK, None)
		eq.save(ignore_permissions=True)
		self.assertEqual(eq.serial_no, "KEEP-ME")
		self.assertFalse(eq.get(OWNED_LIST_FIELD))

	def test_owned_fields_are_read_only_only_when_the_asset_fills_them(self):
		meta = frappe.get_meta("Card Equipment")
		for field in ("brand", "model", "manufacture_year", "serial_no", "plate_no", "image"):
			rule = meta.get_field(field).read_only_depends_on or ""
			self.assertIn(LINK, rule, field)
			self.assertIn(f'includes("{field}")', rule, field)
		self.assertIn(LINK, meta.get_field("company").read_only_depends_on or "")
		self.assertTrue(meta.get_field(OWNED_LIST_FIELD).hidden)

	def test_rented_equipment_is_untouched(self):
		eq = self._make_equipment(ownership="إيجار", serial_no="RENT-1", manufacture_year=1999)
		self.assertEqual(eq.serial_no, "RENT-1")
		self.assertEqual(eq.manufacture_year, 1999)
		self.assertFalse(eq.get(OWNED_LIST_FIELD))

	# ---------- Asset -> equipment ----------

	def test_asset_change_updates_master_and_keeps_operational_values(self):
		asset = self._asset(custom_chassis_no="OLD-CH")
		eq = self._make_equipment(**{LINK: asset})
		operational = {
			"daily_hours": 9,
			"tank_capacity": 300,
			"service_interval_hours": 250,
			"opening_meter": 1234.5,
			"insurance_policy_no": "POL-CARD",
			"site_location": "SITE-A",
		}
		frappe.db.set_value("Card Equipment", eq.name, operational)
		frappe.db.set_value("Asset", asset, {"asset_name": "RENAMED ASSET", "custom_chassis_no": "NEW-CH"})
		on_asset_change(frappe.get_doc("Asset", asset))
		eq.reload()
		self.assertEqual(eq.equipment_name, "RENAMED ASSET")
		self.assertEqual(eq.serial_no, "NEW-CH")
		self.assertEqual(eq.serial_no_key, "NEWCH")
		for field, value in operational.items():
			self.assertEqual(eq.get(field), value, field)
		version = frappe.get_all(
			"Version",
			{"ref_doctype": "Card Equipment", "docname": eq.name},
			["data"],
			order_by="creation desc",
			limit=1,
		)
		self.assertIn("NEW-CH", version[0].data)
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "Card Equipment",
					"reference_name": eq.name,
					"content": ["like", "%OLD-CH%"],
				},
			)
		)

	def test_asset_change_never_breaks_the_asset_save(self):
		asset = self._asset()
		self._make_equipment(**{LINK: asset})
		with patch("card.asset_master.sync_equipment_from_asset", side_effect=RuntimeError("boom")):
			on_asset_change(frappe.get_doc("Asset", asset))  # must not raise
		self.assertTrue(frappe.db.exists("Error Log", {"method": ["like", f"%{asset}%"]}))

	def test_asset_change_does_not_copy_a_chassis_used_by_another_equipment(self):
		asset = self._asset(custom_chassis_no="")
		eq = self._make_equipment(serial_no="MINE-1", **{LINK: asset})
		other = self._make_equipment(ownership="إيجار", serial_no="TAKEN-1")
		frappe.db.set_value("Asset", asset, "custom_chassis_no", "TAKEN-1")
		on_asset_change(frappe.get_doc("Asset", asset))
		eq.reload()
		self.assertEqual(eq.serial_no, "MINE-1")
		self.assertNotIn("serial_no", (eq.get(OWNED_LIST_FIELD) or "").split(","))
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "Card Equipment",
					"reference_name": eq.name,
					"content": ["like", f"%{other.name}%"],
				},
			)
		)

	def test_asset_change_without_a_linked_equipment_does_nothing(self):
		asset = self._asset()
		before = frappe.db.count("Version", {"ref_doctype": "Card Equipment"})
		on_asset_change(frappe.get_doc("Asset", asset))
		self.assertEqual(frappe.db.count("Version", {"ref_doctype": "Card Equipment"}), before)

	def test_card_never_writes_the_asset(self):
		asset = self._asset(custom_chassis_no="A-1")
		before = frappe.db.get_value(
			"Asset", asset, ["modified", "asset_name", "custom_chassis_no"], as_dict=True
		)
		eq = self._make_equipment(serial_no="X", **{LINK: asset})
		eq.serial_no = "Y"
		eq.save(ignore_permissions=True)
		on_asset_change(frappe.get_doc("Asset", asset))
		after = frappe.db.get_value(
			"Asset", asset, ["modified", "asset_name", "custom_chassis_no"], as_dict=True
		)
		self.assertEqual(before, after)

	# ---------- disposal / sale ----------

	def test_hours_after_disposal_are_refused(self):
		asset = self._asset()
		eq = self._make_equipment(**{LINK: asset})
		disposal = today()
		frappe.db.set_value("Asset", asset, {"status": "Sold", "disposal_date": disposal})
		assert_asset_in_service(eq.name, [add_days(disposal, -1)])  # before the sale: allowed
		with self.assertRaises(frappe.ValidationError):
			assert_asset_in_service(eq.name, [disposal])
		frappe.db.set_value("Asset", asset, {"status": "Scrapped"})
		with self.assertRaises(frappe.ValidationError):
			assert_asset_in_service(eq.name, [add_days(disposal, 3)])

	def test_cancelled_asset_refuses_any_hours_and_live_assets_allow_them(self):
		asset = self._asset()
		eq = self._make_equipment(**{LINK: asset})
		assert_asset_in_service(eq.name, [today()])
		assert_asset_in_service(eq.name, [])
		frappe.db.set_value("Asset", asset, {"docstatus": 2, "status": "Cancelled"})
		with self.assertRaises(frappe.ValidationError):
			assert_asset_in_service(eq.name, [add_days(today(), -400)])
		rented = self._make_equipment(ownership="إيجار")
		assert_asset_in_service(rented.name, [today()])  # no Asset: nothing to check

	def test_monthly_card_submit_runs_the_disposal_gate(self):
		from card.card.doctype.card_monthly_card.card_monthly_card import CardMonthlyCard

		card = frappe.new_doc("Card Monthly Card")
		card.equipment = "EQ-X"
		card.append("days", {"operation_date": today(), "working_hours": 5})
		card.append("days", {"operation_date": add_days(today(), -1), "working_hours": 0})
		with patch(
			"card.asset_master.assert_asset_in_service", side_effect=frappe.ValidationError("gate")
		) as gate:
			with self.assertRaisesRegex(frappe.ValidationError, "gate"):
				CardMonthlyCard.before_submit(card)
		gate.assert_called_once()
		self.assertEqual([str(d) for d in gate.call_args.args[1]], [str(today())])

	# ---------- D5 read-only view ----------

	def test_view_shows_asset_values_and_hides_financial_ones_without_level_2(self):
		asset = self._asset(custom_engine_no="ENG-55", custom_customs_fees_sar=1500)
		eq = self._make_equipment(**{LINK: asset})
		admin = {f["fieldname"]: f["value"] for f in get_asset_master_view(eq.name)["fields"]}
		self.assertEqual(admin["custom_engine_no"], "ENG-55")
		self.assertEqual(admin["custom_customs_fees_sar"], 1500)

		self._as(["Card User", "Accounts User"])
		if frappe.has_permission("Asset", "read", asset):
			view = {f["fieldname"]: f["value"] for f in get_asset_master_view(eq.name)["fields"]}
			self.assertEqual(view["custom_engine_no"], "ENG-55")
			self.assertNotIn("custom_customs_fees_sar", view)

	def test_view_needs_asset_read(self):
		asset = self._asset()
		eq = self._make_equipment(**{LINK: asset})
		self._as(["Card User"])
		if not frappe.has_permission("Asset", "read", asset):
			with self.assertRaises(frappe.PermissionError):
				get_asset_master_view(eq.name)

	def test_view_writes_nothing_and_skips_fields_the_site_lacks(self):
		asset = self._asset()
		eq = self._make_equipment(**{LINK: asset})
		modified = frappe.db.get_value("Card Equipment", eq.name, "modified")
		with patch("card.asset_master.VIEW_FIELDS", ("status", "no_such_field_on_asset")):
			view = get_asset_master_view(eq.name)
		self.assertEqual([f["fieldname"] for f in view["fields"]], ["status"])
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "modified"), modified)

	# ---------- v4.3.0 backfill ----------

	def test_backfill_fills_empty_values_reports_conflicts_and_is_idempotent(self):
		from card.patches.v4_3_0 import backfill_asset_master_fields as patch_module

		empty_asset = self._asset(custom_chassis_no="BF-1", custom_manufacture_year=2020)
		empty_eq = self._make_equipment(**{LINK: empty_asset})
		frappe.db.set_value(
			"Card Equipment",
			empty_eq.name,
			{"serial_no": None, "serial_no_key": None, "manufacture_year": 0, OWNED_LIST_FIELD: None},
		)
		conflict_asset = self._asset(custom_chassis_no="BF-ASSET")
		conflict_eq = self._make_equipment(**{LINK: conflict_asset})
		frappe.db.set_value(
			"Card Equipment", conflict_eq.name, {"serial_no": "BF-CARD", "serial_no_key": "BFCARD"}
		)

		report = patch_module.execute()
		self.assertEqual(frappe.db.get_value("Card Equipment", empty_eq.name, "serial_no"), "BF-1")
		self.assertEqual(frappe.db.get_value("Card Equipment", empty_eq.name, "manufacture_year"), 2020)
		self.assertEqual(frappe.db.get_value("Card Equipment", conflict_eq.name, "serial_no"), "BF-CARD")
		self.assertIn(
			{"equipment": conflict_eq.name, "field": "serial_no", "card": "BF-CARD", "asset": "BF-ASSET"},
			report["conflicts"],
		)
		self.assertNotIn(
			"serial_no",
			(frappe.db.get_value("Card Equipment", conflict_eq.name, OWNED_LIST_FIELD) or "").split(","),
		)
		self.assertFalse(
			[
				u
				for u in patch_module.execute()["updated"]
				if u["equipment"] in (empty_eq.name, conflict_eq.name)
			]
		)
