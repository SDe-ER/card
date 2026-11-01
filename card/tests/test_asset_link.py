# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""O2a tests: owned Card Equipment <-> official ERPNext Asset link.

The tests build their own fixed-asset master data (accounts, Asset Category, fixed-asset
Item, Location) and their own Assets, so they run on a clean site. All of it is rolled
back with the test transaction."""

import re
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card.api import (
	available_assets_query,
	create_equipment_from_asset,
	get_asset_prefill,
	get_only_company,
)
from card.tests.test_controllers import _ensure_masters

ASSET_FIELDS = {
	"asset_item": "item_code",
	"asset_location": "location",
	"asset_cost_center": "cost_center",
	"asset_purchase_value": "net_purchase_amount",
}
LINK = "الأصل_في_erpnext"
ASSET_CATEGORY = "TEST-FA-CATEGORY"
ASSET_ITEM = "TEST-FA-ITEM"
ASSET_LOCATION = "TEST-FA-LOCATION"
STATUS_OF = {0: "Draft", 1: "Submitted", 2: "Cancelled"}


class TestAssetLink(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures (Administrator, rolled back) ----------

	def _fixed_asset_account(self, company, account_type, root_type):
		"""The company's leaf account of this type (the standard chart has them), else one
		created under the matching root."""
		name = frappe.db.get_value(
			"Account", {"company": company, "account_type": account_type, "is_group": 0}, "name"
		)
		if name:
			return name
		parent = frappe.db.get_value(
			"Account",
			{"company": company, "is_group": 1, "root_type": root_type, "parent_account": ["is", "not set"]},
			"name",
		)
		return (
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": "TEST-FA " + account_type,
					"company": company,
					"parent_account": parent,
					"account_type": account_type,
					"is_group": 0,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _asset_masters(self):
		"""Asset Category (with the company's accounts), fixed-asset Item and Location."""
		company = self._m["company"]
		if not frappe.db.exists("Asset Category", ASSET_CATEGORY):
			frappe.get_doc(
				{
					"doctype": "Asset Category",
					"asset_category_name": ASSET_CATEGORY,
					"accounts": [
						{
							"company_name": company,
							"fixed_asset_account": self._fixed_asset_account(company, "Fixed Asset", "Asset"),
							"accumulated_depreciation_account": self._fixed_asset_account(
								company, "Accumulated Depreciation", "Asset"
							),
							"depreciation_expense_account": self._fixed_asset_account(
								company, "Depreciation", "Expense"
							),
						}
					],
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Item", ASSET_ITEM):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": ASSET_ITEM,
					"item_name": ASSET_ITEM,
					"item_group": "All Item Groups",
					"stock_uom": "Nos",
					"is_stock_item": 0,
					"is_fixed_asset": 1,
					"asset_category": ASSET_CATEGORY,
				}
			).insert(ignore_permissions=True)
		if not frappe.db.exists("Location", ASSET_LOCATION):
			frappe.get_doc({"doctype": "Location", "location_name": ASSET_LOCATION}).insert(
				ignore_permissions=True
			)

	def _make_asset(self, docstatus=1):
		"""A minimal Asset of the test company. docstatus is set directly: 1 = submitted
		(no depreciation, GL or movement is wanted), 0 = draft, 2 = cancelled."""
		self._asset_masters()
		company = self._m["company"]
		asset = frappe.get_doc(
			{
				"doctype": "Asset",
				"asset_name": "TEST-ASSET-" + frappe.generate_hash(length=8),
				"item_code": ASSET_ITEM,
				"asset_category": ASSET_CATEGORY,
				"location": ASSET_LOCATION,
				"company": company,
				"cost_center": frappe.get_cached_value("Company", company, "cost_center")
				or frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name"),
				"asset_type": "Existing Asset",
				"net_purchase_amount": 1000,
				"purchase_date": frappe.utils.today(),
				"available_for_use_date": frappe.utils.today(),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Asset", asset.name, {"docstatus": docstatus, "status": STATUS_OF[docstatus]})
		return asset.name

	def _other_company(self):
		token = frappe.generate_hash(length=8)
		name = "TEST-ASSETLINK-CO-" + token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "L" + token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self._m["company"], "default_currency"),
				"country": frappe.db.get_value("Company", self._m["company"], "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _user(self, roles, restrict=None):
		email = f"assetlink-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Asset Link",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _as(self, roles, **kw):
		frappe.set_user(self._user(roles, **kw))

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
		first = self._make_equipment(**{"الأصل_في_erpnext": asset})
		with self.assertRaisesRegex(
			frappe.ValidationError, "already linked to equipment " + re.escape(first.name)
		):
			self._make_equipment(**{"الأصل_في_erpnext": asset})
		self.assertEqual(frappe.db.count("Card Equipment", {LINK: asset}), 1)
		first.reload()
		first.plate_no = "TST-1"
		first.save(ignore_permissions=True)  # the equipment that owns the link can still be saved
		self.assertEqual(first.get(LINK), asset)

	def test_create_equipment_from_asset(self):
		asset = self._make_asset()
		doc = create_equipment_from_asset(asset)
		self.assertEqual(doc.get("ownership"), "ملك")
		self.assertEqual(doc.get("الأصل_في_erpnext"), asset)
		self.assertTrue(doc.get("equipment_name"))
		# Prefilled but NOT inserted: the client opens it as a new form.
		self.assertFalse(frappe.db.exists("Card Equipment", {"الأصل_في_erpnext": asset}))

		# Once linked, the same asset cannot be offered again.
		eq = self._make_equipment(**{"الأصل_في_erpnext": asset})
		with self.assertRaisesRegex(
			frappe.ValidationError, "already linked to equipment " + re.escape(eq.name)
		):
			create_equipment_from_asset(asset)
		self.assertEqual(frappe.db.count("Card Equipment", {LINK: asset}), 1)

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

	def test_only_company_with_select_permission(self):
		# v4.1.2: a role that may only pick the company in a link (select, no read) gets it too
		def can(doctype, ptype="read", *args, **kwargs):
			return ptype == "select"

		with (
			patch("card.company.frappe.has_permission", side_effect=can),
			patch("card.company.frappe.get_list", return_value=["A"]),
		):
			self.assertEqual(get_only_company(), "A")
		with patch("card.company.frappe.has_permission", return_value=False):
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
		# FR-098: read-only where the Asset fills the field; model and plate number have no
		# Asset source and stay editable
		meta = frappe.get_meta("Card Equipment")
		for fieldname in ("equipment_name", "brand", "manufacture_year", "serial_no"):
			self.assertIn("الأصل_في_erpnext", meta.get_field(fieldname).read_only_depends_on or "", fieldname)
		for fieldname in ("model", "plate_no"):
			self.assertFalse(meta.get_field(fieldname).read_only_depends_on, fieldname)
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

	# ---------- H1: the Asset endpoints refuse what the user may not read, create or see ----------

	def test_asset_endpoints_need_asset_read_permission(self):
		asset = self._make_asset()
		self._as(["Card Manager"])  # may create Card Equipment, holds no Asset grant
		self.assertFalse(frappe.has_permission("Asset", "read", asset), "premise: no Asset read")
		with self.assertRaises(frappe.PermissionError):
			get_asset_prefill(asset)
		with self.assertRaises(frappe.PermissionError):
			create_equipment_from_asset(asset)
		# the same calls pass once the user may read Assets
		self._as(["Card Manager", "Accounts User"])
		self.assertEqual(get_asset_prefill(asset)["company"], self._m["company"])
		self.assertEqual(create_equipment_from_asset(asset).get(LINK), asset)

	def test_prefill_needs_equipment_read_and_create_needs_equipment_create(self):
		asset = self._make_asset()
		self._as(["Accounts User"])  # reads Assets, no Card Equipment grant
		with self.assertRaises(frappe.PermissionError):
			get_asset_prefill(asset)
		self._as(["Card User", "Accounts User"])  # reads Card Equipment, cannot create it
		self.assertEqual(get_asset_prefill(asset)["company"], self._m["company"])
		with self.assertRaises(frappe.PermissionError):
			create_equipment_from_asset(asset)

	def test_asset_must_exist_and_be_submitted(self):
		missing = "TEST-NO-ASSET-" + frappe.generate_hash(length=8)
		for call in (get_asset_prefill, create_equipment_from_asset):
			with self.subTest(call=call.__name__, case="missing"):
				with self.assertRaisesRegex(frappe.ValidationError, "does not exist"):
					call(missing)
		for docstatus in (0, 2):
			asset = self._make_asset(docstatus=docstatus)
			for call in (get_asset_prefill, create_equipment_from_asset):
				with self.subTest(call=call.__name__, docstatus=docstatus):
					with self.assertRaisesRegex(frappe.ValidationError, "must be submitted"):
						call(asset)

	def test_restricted_user_cannot_reach_an_asset_of_another_company(self):
		other = self._other_company()
		mine, theirs = self._make_asset(), self._make_asset()
		frappe.db.set_value("Asset", theirs, "company", other)
		self._as(["Card Manager", "Accounts User"], restrict=self._m["company"])
		self.assertEqual(get_asset_prefill(mine)["company"], self._m["company"])  # positive control
		with self.assertRaises(frappe.PermissionError):
			get_asset_prefill(theirs)
		with self.assertRaises(frappe.PermissionError):
			create_equipment_from_asset(theirs)
		with self.assertRaises(frappe.PermissionError):
			self._make_equipment(**{LINK: theirs})

	def test_available_assets_query_offers_only_free_submitted_assets_of_the_users_company(self):
		other = self._other_company()
		free, linked, draft, cancelled, scrapped, foreign = (
			self._make_asset(),
			self._make_asset(),
			self._make_asset(docstatus=0),
			self._make_asset(docstatus=2),
			self._make_asset(),
			self._make_asset(),
		)
		self._make_equipment(**{LINK: linked})
		frappe.db.set_value("Asset", scrapped, "status", "Scrapped")
		frappe.db.set_value("Asset", foreign, "company", other)
		everything = (free, linked, draft, cancelled, scrapped, foreign)

		def offered(filters=None):
			return {
				r[0] for r in available_assets_query("Asset", "TEST-ASSET-", "name", 0, 500, filters or {})
			}

		# Card Manager creates equipment; Accounts User gives the Asset read the rows need
		self._as(["Card Manager", "Accounts User"], restrict=self._m["company"])
		names = offered()
		self.assertIn(free, names)
		for excluded in (linked, draft, cancelled, scrapped, foreign):
			self.assertNotIn(excluded, names, excluded)
		# a company the user may not see lists nothing, however the filter is sent
		self.assertEqual(available_assets_query("Asset", "", "name", 0, 500, {"company": other}), [])
		self.assertEqual(available_assets_query("Asset", "", "name", 0, 500, '{"company": "%s"}' % other), [])
		self.assertIn(free, offered({"company": self._m["company"]}))

		# an unrestricted manager also sees the other company's free asset
		self._as(["Card Manager", "Accounts User"])
		self.assertEqual({foreign, free} & offered(), {foreign, free})
		self.assertFalse(set(everything[1:5]) & offered())

	def test_available_assets_query_is_for_users_who_may_create_or_edit_equipment(self):
		free = self._make_asset()
		self._as(["Accounts Manager"])  # reads Card Equipment only
		with self.assertRaises(frappe.PermissionError):
			available_assets_query("Asset", "TEST-ASSET-", "name", 0, 500, {})
		self._as(["Card Manager", "Accounts User"])
		rows = available_assets_query("Asset", "TEST-ASSET-", "name", 0, 500, {})
		self.assertIn(free, {r[0] for r in rows})

	# ---------- the Asset picker follows the Asset permissions ----------

	def _offered(self, filters=None):
		rows = available_assets_query("Asset", "TEST-ASSET-", "name", 0, 500, filters or {})
		return {r[0] for r in rows}

	def _user_permission(self, user, allow, value, applicable_for=None):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": allow,
				"for_value": value,
				"apply_to_all_doctypes": 0 if applicable_for else 1,
				"applicable_for": applicable_for,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)

	def test_available_assets_query_needs_asset_read(self):
		free = self._make_asset()
		for roles in (
			["Card Manager"],
			["Card User"],
			["Card Manager", "Stock User"],
		):  # Stock User: select only
			self._as(roles)
			with self.assertRaises(frappe.PermissionError, msg=roles):
				available_assets_query("Asset", "", "name", 0, 500, {})
		self._as(["Card Manager", "Accounts User"])  # positive control
		self.assertIn(free, self._offered())

	def test_available_assets_query_applies_asset_user_permissions(self):
		allowed, restricted = self._make_asset(), self._make_asset()
		user = self._user(["Card Manager", "Accounts User"])
		self._user_permission(user, "Asset", allowed, applicable_for="Asset")
		frappe.set_user(user)
		offered = self._offered()
		self.assertIn(allowed, offered)
		self.assertNotIn(restricted, offered)

	def test_available_assets_query_applies_the_asset_company_scope(self):
		# a Company User Permission that applies only to Asset still limits the picker
		other = self._other_company()
		mine, foreign = self._make_asset(), self._make_asset()
		frappe.db.set_value("Asset", foreign, "company", other)
		user = self._user(["Card Manager", "Accounts User"])
		self._user_permission(user, "Company", self._m["company"], applicable_for="Asset")
		frappe.set_user(user)
		self.assertIn(mine, self._offered())
		self.assertNotIn(foreign, self._offered())
		self.assertNotIn(foreign, self._offered({"company": other}))

	def test_link_search_route_keeps_the_asset_permissions(self):
		from frappe.desk.search import search_link

		allowed, restricted = self._make_asset(), self._make_asset()
		user = self._user(["Card Manager", "Accounts User"])
		self._user_permission(user, "Asset", allowed, applicable_for="Asset")
		frappe.set_user(user)
		rows = search_link(
			"Asset",
			"TEST-ASSET-",
			query="card.api.available_assets_query",
			filters={"company": self._m["company"]},
			page_length=500,
			reference_doctype="Card Equipment",
			ignore_user_permissions=1,  # asked by the client; refused: the Asset link field keeps User Permissions
		)
		names = {r["value"] for r in rows}
		self.assertIn(allowed, names)
		self.assertNotIn(restricted, names)

	def test_linked_asset_check_names_the_equipment_only_to_asset_readers(self):
		asset = self._make_asset()
		first = self._make_equipment(**{LINK: asset})
		self._as(["Card Manager"])
		with self.assertRaises(frappe.PermissionError) as refused:
			self._make_equipment(**{LINK: asset})
		self.assertNotIn(first.name, str(refused.exception))
		self._as(["Card Manager", "Accounts User"])  # positive control: an Asset reader sees which one
		with self.assertRaisesRegex(frappe.ValidationError, re.escape(first.name)):
			self._make_equipment(**{LINK: asset})

	def test_available_assets_query_offers_an_asset_shared_with_the_user(self):
		shared, other = self._make_asset(), self._make_asset()
		user = self._user(["Card Manager"])  # no Asset role
		frappe.share.add_docshare("Asset", shared, user, read=1, flags={"ignore_share_permission": True})
		frappe.set_user(user)
		offered = self._offered()
		self.assertIn(shared, offered)  # the save would accept it too
		self.assertNotIn(other, offered)

	def test_available_assets_query_keeps_a_page_limit(self):
		self._make_asset()
		self._make_asset()
		self._as(["Card Manager", "Accounts User"])
		self.assertEqual(len(available_assets_query("Asset", "TEST-ASSET-", "name", 0, 1, {})), 1)
		rows = available_assets_query("Asset", "TEST-ASSET-", "name", 0, 0, {})  # 0 is not "no limit"
		self.assertLessEqual(len(rows), 20)

	def test_unrelated_save_of_an_unchanged_duplicate_link_is_not_refused_for_asset_read(self):
		asset = self._make_asset()
		first = self._make_equipment(**{LINK: asset})
		second = self._make_equipment()
		frappe.db.set_value("Card Equipment", second.name, LINK, asset)  # legacy duplicate
		self._as(["Card Manager"])
		doc = frappe.get_doc("Card Equipment", second.name)
		doc.plate_no = "TST-2"
		with self.assertRaisesRegex(frappe.ValidationError, re.escape(first.name)) as raised:
			doc.save()  # unchanged link: the existing duplicate guard, not an Asset read refusal
		self.assertNotIsInstance(raised.exception, frappe.PermissionError)

	# ---------- H2: linking an Asset on save ----------

	def test_equipment_refuses_an_asset_of_another_company(self):
		asset = self._make_asset()
		self._make_equipment(**{LINK: asset})  # positive control: same company links
		foreign = self._make_asset()
		frappe.db.set_value("Asset", foreign, "company", self._other_company())
		with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
			self._make_equipment(**{LINK: foreign})
		self.assertFalse(frappe.db.exists("Card Equipment", {LINK: foreign}))

	def test_equipment_refuses_a_cancelled_asset_but_keeps_a_link_made_before(self):
		asset = self._make_asset()
		eq = self._make_equipment(**{LINK: asset})
		cancelled = self._make_asset(docstatus=2)
		with self.assertRaisesRegex(frappe.ValidationError, "cancelled"):
			self._make_equipment(**{LINK: cancelled})
		# the check runs when the link changes, so a later cancel never blocks an unrelated save
		frappe.db.set_value("Asset", asset, {"docstatus": 2, "status": "Cancelled"})
		eq.reload()
		eq.plate_no = "TST-2"
		eq.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "plate_no"), "TST-2")
		# ... but pointing the equipment at a cancelled asset is refused
		eq.reload()
		eq.set(LINK, cancelled)
		with self.assertRaisesRegex(frappe.ValidationError, "cancelled"):
			eq.save(ignore_permissions=True)

	def test_equipment_link_needs_asset_read_permission(self):
		asset = self._make_asset()
		self._as(["Card Manager"])
		self.assertFalse(frappe.has_permission("Asset", "read", asset), "premise: no Asset read")
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to read Asset"):
			self._make_equipment(**{LINK: asset})
		self.assertFalse(frappe.db.exists("Card Equipment", {LINK: asset}))
		self._as(["Card Manager", "Accounts User"])
		self.assertEqual(self._make_equipment(**{LINK: asset}).get(LINK), asset)

	def test_missing_asset_gives_no_details_and_cannot_be_linked(self):
		from card.card.doctype.card_equipment.card_equipment import asset_equipment_values

		missing = "TEST-NO-ASSET-" + frappe.generate_hash(length=8)
		self.assertEqual(asset_equipment_values(missing), {})
		with self.assertRaises(frappe.LinkValidationError):
			self._make_equipment(**{LINK: missing})
		self.assertFalse(frappe.db.exists("Card Equipment", {LINK: missing}))
