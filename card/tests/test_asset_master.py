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
from card.tests import test_asset_link as _link
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
	_fixed_asset_account = _link.TestAssetLink._fixed_asset_account
	_asset_masters = _link.TestAssetLink._asset_masters
	_make_asset = _link.TestAssetLink._make_asset
	_user = _link.TestAssetLink._user
	_as = _link.TestAssetLink._as
	_make_equipment = _link.TestAssetLink._make_equipment

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

	def _comments(self, equipment, text):
		return frappe.get_all(
			"Comment",
			{
				"reference_doctype": "Card Equipment",
				"reference_name": equipment,
				"content": ["like", f"%{text}%"],
			},
			pluck="name",
		)

	def _rented(self, **kw):
		"""A rented equipment (no Asset): rented directions need a supplier and a rate."""
		supplier = frappe.new_doc("Supplier")
		supplier.supplier_name = "TEST-AM-SUP-" + frappe.generate_hash(length=8)
		supplier.supplier_group = self._m["supplier_group"]
		supplier.insert(ignore_permissions=True)
		return self._make_equipment(
			ownership="إيجار", supplier=supplier.name, rate_type="باليوم", rate=500, **kw
		)

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
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "serial_no"), "ASSET-CH-7")
		# the typed value was never stored: nothing to note
		self.assertFalse(self._comments(eq.name, "TYPED-OVER"))

	def test_a_stored_card_value_replaced_by_the_asset_is_noted(self):
		asset = self._asset(custom_chassis_no="ASSET-CH-8")
		eq = self._make_equipment(**{LINK: asset})
		frappe.db.set_value(
			"Card Equipment", eq.name, {"serial_no": "STORED-OLD", "serial_no_key": "STOREDOLD"}
		)
		eq.reload()
		eq.save(ignore_permissions=True)
		self.assertEqual(eq.serial_no, "ASSET-CH-8")
		self.assertTrue(self._comments(eq.name, "STORED-OLD"))

	def test_save_does_not_copy_a_chassis_another_equipment_uses(self):
		self._rented(serial_no="DUP-SAVE-1")
		asset = self._asset(custom_chassis_no="DUP-SAVE-1")
		eq = self._make_equipment(serial_no="OWN-1", **{LINK: asset})  # saves: no duplicate error
		self.assertEqual(eq.serial_no, "OWN-1")
		self.assertNotIn("serial_no", eq.get(OWNED_LIST_FIELD).split(","))
		eq.site_location = "SITE-B"
		eq.save(ignore_permissions=True)  # still savable
		self.assertEqual(eq.serial_no, "OWN-1")

	def test_year_held_as_text_compares_as_a_number(self):
		from card.asset_master import _coerce

		self.assertEqual(_coerce("manufacture_year", "2015"), 2015)
		self.assertEqual(_coerce("manufacture_year", 2015), 2015)
		self.assertEqual(_coerce("serial_no", " x "), " x ")  # text untouched
		with patch("card.asset_master.frappe.db.get_value", wraps=frappe.db.get_value):
			asset = self._asset(custom_manufacture_year=2015)
			eq = self._make_equipment(**{LINK: asset})
			versions = frappe.db.count("Version", {"ref_doctype": "Card Equipment", "docname": eq.name})
			on_asset_change(frappe.get_doc("Asset", asset))
			self.assertEqual(
				frappe.db.count("Version", {"ref_doctype": "Card Equipment", "docname": eq.name}), versions
			)

	def test_private_asset_image_is_not_copied(self):
		asset = self._asset(image="/private/files/secret.png")
		eq = self._make_equipment(**{LINK: asset})
		self.assertNotEqual(eq.image, "/private/files/secret.png")
		self.assertNotIn("image", eq.get(OWNED_LIST_FIELD).split(","))

	def test_switching_the_link_takes_the_new_assets_values(self):
		first = self._asset(custom_chassis_no="SW-A")
		second = self._asset(custom_chassis_no="SW-B")
		eq = self._make_equipment(**{LINK: first})
		eq.set(LINK, second)
		eq.save(ignore_permissions=True)
		self.assertEqual(eq.serial_no, "SW-B")
		self.assertEqual(eq.equipment_name, frappe.db.get_value("Asset", second, "asset_name"))

	def test_prefill_returns_the_owned_list(self):
		from card.api import get_asset_prefill

		asset = self._asset(custom_chassis_no="PF-1")
		values = get_asset_prefill(asset)
		self.assertEqual(values["serial_no"], "PF-1")
		self.assertIn("serial_no", values[OWNED_LIST_FIELD].split(","))

	def test_unlinking_keeps_the_values_and_unlocks_them(self):
		asset = self._asset(custom_chassis_no="KEEP-ME")
		eq = self._make_equipment(**{LINK: asset})
		eq.set(LINK, None)
		eq.save(ignore_permissions=True)
		self.assertEqual(eq.serial_no, "KEEP-ME")
		self.assertFalse(eq.get(OWNED_LIST_FIELD))

	def test_owned_fields_are_read_only_only_when_the_asset_fills_them(self):
		meta = frappe.get_meta("Card Equipment")
		for field in ("brand", "manufacture_year", "serial_no", "image"):
			rule = meta.get_field(field).read_only_depends_on or ""
			self.assertIn(LINK, rule, field)
			self.assertIn(f'includes("{field}")', rule, field)
		self.assertIn(LINK, meta.get_field("company").read_only_depends_on or "")
		for field in ("model", "plate_no"):  # no Asset source: always CARD's
			self.assertFalse(meta.get_field(field).read_only_depends_on, field)
		self.assertTrue(meta.get_field(LINK).search_index)
		self.assertTrue(meta.get_field(OWNED_LIST_FIELD).hidden)

	def test_rented_equipment_is_untouched(self):
		eq = self._rented(serial_no="RENT-1", manufacture_year=1999)
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
		frappe.db.set_value("Card Equipment", eq.name, dict(operational))
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
		logs = frappe.db.count("Error Log")
		with patch("card.asset_master.sync_equipment_from_asset", side_effect=RuntimeError("boom")):
			on_asset_change(frappe.get_doc("Asset", asset))  # must not raise
		self.assertEqual(frappe.db.count("Error Log") - logs, 1)

	def test_asset_change_does_not_copy_a_chassis_used_by_another_equipment(self):
		asset = self._asset(custom_chassis_no="")
		eq = self._make_equipment(serial_no="MINE-1", **{LINK: asset})
		other = self._rented(serial_no="TAKEN-1")
		frappe.db.set_value("Asset", asset, "custom_chassis_no", "TAKEN-1")
		on_asset_change(frappe.get_doc("Asset", asset))
		on_asset_change(frappe.get_doc("Asset", asset))  # same situation again: one note only
		eq.reload()
		self.assertEqual(eq.serial_no, "MINE-1")
		self.assertNotIn("serial_no", (eq.get(OWNED_LIST_FIELD) or "").split(","))
		notes = self._comments(eq.name, "TAKEN-1")
		self.assertEqual(len(notes), 1)
		self.assertFalse(self._comments(eq.name, other.name))  # the other equipment is not named

	def test_hook_twice_changes_nothing_the_second_time(self):
		asset = self._asset(custom_chassis_no="TWICE-1")
		eq = self._make_equipment(**{LINK: asset})
		frappe.db.set_value("Asset", asset, "custom_chassis_no", "TWICE-2")
		on_asset_change(frappe.get_doc("Asset", asset))
		count = frappe.db.count("Version", {"ref_doctype": "Card Equipment", "docname": eq.name})
		comments = frappe.db.count(
			"Comment", {"reference_doctype": "Card Equipment", "reference_name": eq.name}
		)
		on_asset_change(frappe.get_doc("Asset", asset))
		self.assertEqual(
			frappe.db.count("Version", {"ref_doctype": "Card Equipment", "docname": eq.name}), count
		)
		self.assertEqual(
			frappe.db.count("Comment", {"reference_doctype": "Card Equipment", "reference_name": eq.name}),
			comments,
		)

	def test_failed_sync_leaves_nothing_half_written(self):
		asset = self._asset(custom_chassis_no="ATOM-OLD")
		eq = self._make_equipment(**{LINK: asset})
		frappe.db.set_value("Asset", asset, "custom_chassis_no", "ATOM-NEW")
		logs = frappe.db.count("Error Log")
		with patch("card.asset_master.comment_replaced", side_effect=RuntimeError("audit failed")):
			on_asset_change(frappe.get_doc("Asset", asset))  # must not raise
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "serial_no"), "ATOM-OLD")
		self.assertEqual(frappe.db.count("Error Log") - logs, 1)

	def test_deadlocks_are_raised_not_swallowed(self):
		asset = self._asset()
		self._make_equipment(**{LINK: asset})
		with patch("card.asset_master.sync_equipment_from_asset", side_effect=frappe.QueryDeadlockError("x")):
			with self.assertRaises(frappe.QueryDeadlockError):
				on_asset_change(frappe.get_doc("Asset", asset))

	def test_legacy_duplicate_links_are_reported_not_half_synced(self):
		# CARD refuses to save two equipment on one Asset (one Asset, one equipment); legacy rows
		# that share an Asset are left unchanged, the failure is logged and the Asset save goes on
		asset = self._asset(custom_chassis_no="")
		first = self._make_equipment(**{LINK: asset})
		second = self._make_equipment()
		frappe.db.set_value("Card Equipment", second.name, LINK, asset)  # legacy duplicate link
		names = {
			n: frappe.db.get_value("Card Equipment", n, "equipment_name") for n in (first.name, second.name)
		}
		frappe.db.set_value("Asset", asset, "asset_name", "SHARED NAME")
		logs = frappe.db.count("Error Log")
		on_asset_change(frappe.get_doc("Asset", asset))  # must not raise
		for name, before in names.items():
			self.assertEqual(frappe.db.get_value("Card Equipment", name, "equipment_name"), before)
		self.assertEqual(frappe.db.count("Error Log") - logs, 2)

	def test_asset_events_are_wired(self):
		events = frappe.get_hooks("doc_events").get("Asset", {})
		for event in ("on_update", "on_update_after_submit", "on_cancel"):
			self.assertIn("card.asset_master.on_asset_change", events.get(event, []), event)

	def test_a_real_asset_update_after_submit_reaches_the_equipment(self):
		asset = self._asset(custom_chassis_no="REAL-1")
		eq = self._make_equipment(**{LINK: asset})
		doc = frappe.get_doc("Asset", asset)
		doc.custom_chassis_no = "REAL-2"  # allow on submit (site field)
		doc.flags.ignore_validate = True  # the fixture Asset has no depreciation set-up
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "serial_no"), "REAL-2")

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
		rented = self._rented()
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

		self._as(["Card User", "Accounts User"])  # Asset read, no level 2 on the equipment
		self.assertTrue(frappe.has_permission("Asset", "read", asset))
		view = {f["fieldname"]: f["value"] for f in get_asset_master_view(eq.name)["fields"]}
		self.assertEqual(view["custom_engine_no"], "ENG-55")
		self.assertNotIn("custom_customs_fees_sar", view)

		frappe.set_user("Administrator")
		self._as(["Card Manager", "Accounts User"])  # level 2 reader
		view = {f["fieldname"]: f["value"] for f in get_asset_master_view(eq.name)["fields"]}
		self.assertEqual(view["custom_customs_fees_sar"], 1500)

	def test_view_needs_asset_read(self):
		asset = self._asset()
		eq = self._make_equipment(**{LINK: asset})
		self._as(["Card User"])  # equipment read, no Asset read
		self.assertTrue(frappe.has_permission("Card Equipment", "read", eq.name))
		self.assertFalse(frappe.has_permission("Asset", "read", asset))
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

		self._rented(serial_no="BF-DUP")
		dup_asset = self._asset(custom_chassis_no="BF-DUP")
		dup_eq = self._make_equipment(**{LINK: dup_asset})
		frappe.db.set_value("Card Equipment", dup_eq.name, {"serial_no": None, "serial_no_key": None})

		with patch("card.patches.v4_3_0.backfill_asset_master_fields.frappe.reload_doc"):  # no DDL commit
			report = patch_module.execute()
		self.assertIn(dup_eq.name, [r["equipment"] for r in report["skipped_duplicate_chassis"]])
		self.assertFalse(frappe.db.get_value("Card Equipment", dup_eq.name, "serial_no"))
		self.assertTrue(self._comments(conflict_eq.name, "BF-ASSET"))
		self.assertTrue(
			frappe.db.exists(
				"Version",
				{"ref_doctype": "Card Equipment", "docname": empty_eq.name, "data": ["like", "%BF-1%"]},
			)
		)
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
