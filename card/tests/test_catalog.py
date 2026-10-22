# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Catalog search (phase 1): the standard ERPNext catalogue read with the user's own rights;
OEM numbers, barcodes, alternatives and paging never reveal an item the user may not list."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from card import catalog


class TestCatalog(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=6)
		self.root = self._group("ROOT", parent="All Item Groups", is_group=1)
		self.parts = self._group("PARTS", parent=self.root)
		self.other_group = self._group("OTHER", parent="All Item Groups")
		self.brand = self._brand("BR")
		self.manufacturer = self._manufacturer("MF")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders ----------
	def _group(self, name, parent, is_group=0):
		group = f"CAT-{name}-{self.token}"
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": group,
				"parent_item_group": parent,
				"is_group": is_group,
			}
		).insert(ignore_permissions=True)
		return group

	def _brand(self, name):
		brand = f"CAT-{name}-{self.token}"
		frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)
		return brand

	def _manufacturer(self, name):
		manufacturer = f"CAT-{name}-{self.token}"
		frappe.get_doc({"doctype": "Manufacturer", "short_name": manufacturer}).insert(
			ignore_permissions=True
		)
		return manufacturer

	def _item(self, name, **values):
		code = f"CAT-{name}-{self.token}"
		doc = {
			"doctype": "Item",
			"item_code": code,
			"item_name": f"Catalog {name} {self.token}",
			"item_group": values.pop("item_group", self.parts),
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
		barcode = values.pop("barcode", None)
		if barcode:
			doc["barcodes"] = [{"barcode": barcode}]
		doc.update(values)
		frappe.get_doc(doc).insert(ignore_permissions=True)
		return code

	def _oem(self, item_code, part_no):
		frappe.get_doc(
			{
				"doctype": "Item Manufacturer",
				"item_code": item_code,
				"manufacturer": self.manufacturer,
				"manufacturer_part_no": part_no,
			}
		).insert(ignore_permissions=True)

	def _alternative(self, item_code, alternative, two_way=0):
		frappe.get_doc(
			{
				"doctype": "Item Alternative",
				"item_code": item_code,
				"alternative_item_code": alternative,
				"two_way": two_way,
			}
		).insert(ignore_permissions=True)

	def _user(self, prefix, roles):
		email = f"cat-{prefix}-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		return email

	def _restrict(self, user, doctype, value):
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": doctype, "for_value": value}
		).insert(ignore_permissions=True)

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _codes(self, result):
		return [row["item_code"] for row in result["items"]]

	# ---------- matching ----------
	def test_matches_item_name_code_barcode_and_oem_number(self):
		code = self._item("PUMP", barcode=f"BC{self.token}99")
		self._oem(code, f"OEM-{self.token}-7")
		self.assertIn(code, self._codes(catalog.search(f"Catalog PUMP {self.token}")))
		self.assertIn(code, self._codes(catalog.search(code)))
		self.assertIn(code, self._codes(catalog.search(f"BC{self.token}99")))
		self.assertIn(code, self._codes(catalog.search(f"OEM-{self.token}-7")))
		self.assertEqual(catalog.search(f"nothing-{self.token}")["items"], [])

	def test_like_wildcards_in_the_text_are_literal(self):
		self._item("PLAIN")
		self.assertEqual(catalog.search(f"%{self.token}")["items"], [])
		self.assertEqual(catalog.search(f"CAT_PLAIN_{self.token}")["items"], [])

	def test_item_group_filter_includes_sub_groups_and_brand_filter(self):
		in_parts = self._item("A")
		elsewhere = self._item("B", item_group=self.other_group, brand=self.brand)
		found = self._codes(catalog.search(self.token, item_group=self.root))
		self.assertIn(in_parts, found)
		self.assertNotIn(elsewhere, found)
		self.assertEqual(self._codes(catalog.search(self.token, brand=self.brand)), [elsewhere])

	def test_only_active_stock_or_purchase_items_are_listed(self):
		stock = self._item("STOCK")
		bought = self._item("BOUGHT", is_stock_item=0, is_purchase_item=1)
		service = self._item("SERVICE", is_stock_item=0, is_purchase_item=0)
		disabled = self._item("OFF", disabled=1)
		template = self._item("TPL")
		frappe.db.set_value("Item", template, "has_variants", 1)
		ended = self._item("ENDED")
		frappe.db.set_value("Item", ended, "end_of_life", add_days(nowdate(), -1))
		no_end = self._item("NOEND")
		frappe.db.set_value("Item", no_end, "end_of_life", None)
		found = set(self._codes(catalog.search(self.token, page_length=50)))
		self.assertTrue({stock, bought, no_end} <= found)
		self.assertFalse({service, disabled, template, ended} & found)

	# ---------- paging ----------
	def test_pages_follow_the_server_and_are_capped(self):
		codes = sorted(self._item(f"P{i:02d}") for i in range(5))
		first = catalog.search(self.token, page_length=2)
		second = catalog.search(self.token, start=2, page_length=2)
		last = catalog.search(self.token, start=4, page_length=2)
		self.assertTrue(first["has_more"])
		self.assertTrue(second["has_more"])
		self.assertFalse(last["has_more"])
		self.assertEqual(self._codes(first) + self._codes(second) + self._codes(last), codes)
		for i in range(55):
			self._item(f"MANY{i:02d}")
		self.assertEqual(len(catalog.search(self.token, page_length=500)["items"]), catalog.MAX_PAGE_LENGTH)

	def test_rows_carry_catalog_fields_only(self):
		code = self._item("ROW", brand=self.brand)
		frappe.db.set_value("Item", code, "image", "/files/cat-row.png")
		row = catalog.search(code)["items"][0]
		self.assertEqual(
			set(row),
			{
				"item_code",
				"item_name",
				"stock_uom",
				"image",
				"item_group",
				"item_group_label",
				"brand",
				"oem",
				"alternatives",
			},
		)
		self.assertEqual(
			(row["brand"], row["image"], row["item_group"]), (self.brand, "/files/cat-row.png", self.parts)
		)

	# ---------- alternatives ----------
	def test_alternatives_follow_erpnext_two_way(self):
		main = self._item("MAIN", allow_alternative_item=1)
		one_way = self._item("ONEWAY", allow_alternative_item=1)
		both = self._item("BOTH", allow_alternative_item=1)
		self._alternative(main, one_way)
		self._alternative(main, both, two_way=1)
		alts = {r["item_code"]: r for r in catalog.search(self.token, page_length=50)["items"]}
		self.assertEqual({a["item_code"] for a in alts[main]["alternatives"]}, {one_way, both})
		self.assertEqual(alts[one_way]["alternatives"], [])
		self.assertEqual([a["item_code"] for a in alts[both]["alternatives"]], [main])

	def test_disabled_alternative_is_not_shown(self):
		main = self._item("MAIN2", allow_alternative_item=1)
		alt = self._item("ALT2", allow_alternative_item=1)
		self._alternative(main, alt)
		frappe.db.set_value("Item", alt, "disabled", 1)
		self.assertEqual(catalog.search(main)["items"][0]["alternatives"], [])

	# ---------- who may read ----------
	def test_users_without_a_card_role_or_item_read_are_refused(self):
		outsider = self._user("out", [])
		for fn, args in ((catalog.search, ("x",)), (catalog.filter_options, ("brand",))):
			with self.assertRaises(frappe.PermissionError):
				self._as(outsider, fn, *args)
			with self.assertRaises(frappe.PermissionError):
				self._as("Guest", fn, *args)

	def test_endpoints_are_get_only(self):
		for fn in (catalog.search, catalog.filter_options):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[fn], ["GET"])

	def test_operator_sees_oem_and_alternatives_but_nothing_restricted(self):
		main = self._item("OPMAIN", allow_alternative_item=1)
		alt = self._item("OPALT", allow_alternative_item=1)
		self._alternative(main, alt)
		self._oem(main, f"OP-OEM-{self.token}")
		operator = self._user("op", ["Card Operator"])
		row = self._as(operator, catalog.search, f"OP-OEM-{self.token}")["items"][0]
		self.assertEqual(row["item_code"], main)
		self.assertEqual(row["oem"], [{"manufacturer": self.manufacturer, "part_no": f"OP-OEM-{self.token}"}])
		self.assertEqual([a["item_code"] for a in row["alternatives"]], [alt])
		self.assertNotIn("stock_qty", row)

	def test_item_reader_without_card_role_gets_no_oem_without_manufacturer_rights(self):
		code = self._item("NOOEM")
		self._oem(code, f"HIDDEN-{self.token}")
		reader = self._user("rd", ["Sales User"])
		self.assertEqual(self._as(reader, catalog.search, f"HIDDEN-{self.token}")["items"], [])
		row = self._as(reader, catalog.search, code)["items"][0]
		self.assertEqual(row["oem"], [])

	def test_item_group_user_permission_limits_item_readers(self):
		allowed = self._item("SEEN")
		hidden = self._item("UNSEEN", item_group=self.other_group, allow_alternative_item=1)
		self._oem(hidden, f"HID-OEM-{self.token}")
		supervisor = self._user("sv", ["Card Supervisor", "Stock User"])
		self._restrict(supervisor, "Item Group", self.parts)
		self.assertEqual(
			self._codes(self._as(supervisor, catalog.search, self.token, page_length=50)), [allowed]
		)
		# an OEM number of a hidden item finds nothing
		self.assertEqual(self._as(supervisor, catalog.search, f"HID-OEM-{self.token}")["items"], [])

	def test_item_group_user_permission_limits_operators(self):
		allowed = self._item("OPSEEN", allow_alternative_item=1)
		hidden = self._item("OPHIDDEN", item_group=self.other_group, allow_alternative_item=1)
		self._alternative(allowed, hidden)
		self._oem(hidden, f"OPHID-{self.token}")
		operator = self._user("op2", ["Card Operator"])
		self._restrict(operator, "Item Group", self.parts)
		result = self._as(operator, catalog.search, self.token, page_length=50)
		self.assertEqual(self._codes(result), [allowed])
		# the hidden item is neither an alternative, nor found by its OEM number, nor counted in paging
		self.assertEqual(result["items"][0]["alternatives"], [])
		self.assertEqual(self._as(operator, catalog.search, f"OPHID-{self.token}")["items"], [])
		self.assertFalse(self._as(operator, catalog.search, self.token, page_length=1)["has_more"])

	def test_alternative_hidden_from_an_item_reader_is_not_shown(self):
		main = self._item("RMAIN", allow_alternative_item=1)
		hidden = self._item("RHIDDEN", item_group=self.other_group, allow_alternative_item=1)
		self._alternative(main, hidden)
		supervisor = self._user("sv2", ["Card Supervisor", "Stock User"])
		self._restrict(supervisor, "Item Group", self.parts)
		self.assertEqual(self._as(supervisor, catalog.search, main)["items"][0]["alternatives"], [])

	# ---------- filters ----------
	def test_filter_options_search_page_and_respect_user_permissions(self):
		other = self._brand("BR2")
		names = [o["value"] for o in catalog.filter_options("brand", self.token)]
		self.assertEqual(names, sorted([self.brand, other]))
		self.assertEqual(len(catalog.filter_options("brand", self.token, page_length=1)), 1)
		operator = self._user("op3", ["Card Operator"])
		self._restrict(operator, "Brand", self.brand)
		self.assertEqual(
			[o["value"] for o in self._as(operator, catalog.filter_options, "brand", self.token)],
			[self.brand],
		)
		with self.assertRaises(frappe.ValidationError):
			catalog.filter_options("warehouse")

	def test_item_group_label_is_translated(self):
		self._item("TR")
		frappe.get_doc(
			{"doctype": "Translation", "language": "ar", "source_text": self.parts, "translated_text": "قطع"}
		).insert(ignore_permissions=True)
		user = self._user("ar", ["Card Operator"])
		frappe.db.set_value("User", user, "language", "ar")
		frappe.set_user(user)
		frappe.local.lang = "ar"
		try:
			frappe.clear_cache()
			row = catalog.search(self.token)["items"][0]
			options = catalog.filter_options("item_group", self.parts)
		finally:
			frappe.local.lang = "en"
			frappe.set_user("Administrator")
		self.assertEqual(row["item_group_label"], "قطع")
		self.assertEqual(options, [{"value": self.parts, "label": "قطع"}])

	# ---------- review follow-ups ----------
	def test_item_group_options_match_the_translated_name(self):
		frappe.get_doc(
			{
				"doctype": "Translation",
				"language": "ar",
				"source_text": self.parts,
				"translated_text": "قطع غيار",
			}
		).insert(ignore_permissions=True)
		frappe.local.lang = "ar"
		try:
			frappe.clear_cache()
			found = catalog.filter_options("item_group", "غيار")
		finally:
			frappe.local.lang = "en"
		self.assertEqual(found, [{"value": self.parts, "label": "قطع غيار"}])

	def test_unknown_item_group_lists_nothing(self):
		self._item("ANY")
		self.assertEqual(
			catalog.search(self.token, item_group=f"missing-{self.token}"), {"items": [], "has_more": False}
		)

	def test_manufacturer_user_permission_limits_operators(self):
		other = self._manufacturer("MF2")
		mine = self._item("MINE")
		self._oem(mine, f"MINE-OEM-{self.token}")
		theirs = self._item("THEIRS", default_item_manufacturer=other)
		frappe.get_doc(
			{
				"doctype": "Item Manufacturer",
				"item_code": mine,
				"manufacturer": other,
				"manufacturer_part_no": f"OTHER-OEM-{self.token}",
			}
		).insert(ignore_permissions=True)
		operator = self._user("op4", ["Card Operator"])
		self._restrict(operator, "Manufacturer", self.manufacturer)
		found = self._as(operator, catalog.search, self.token, page_length=50)
		self.assertNotIn(theirs, self._codes(found))
		row = next(r for r in found["items"] if r["item_code"] == mine)
		self.assertEqual([o["part_no"] for o in row["oem"]], [f"MINE-OEM-{self.token}"])
		self.assertEqual(self._as(operator, catalog.search, f"OTHER-OEM-{self.token}")["items"], [])

	def test_inline_search_items_follows_the_catalog_rules(self):
		from card import materials

		allowed = self._item("INSEEN", barcode=f"IN{self.token}BC")
		hidden = self._item("INHIDDEN", item_group=self.other_group)
		ended = self._item("INENDED")
		frappe.db.set_value("Item", ended, "end_of_life", add_days(nowdate(), -1))
		operator = self._user("op5", ["Card Operator"])
		self._restrict(operator, "Item Group", self.parts)
		found = {r["item_code"] for r in self._as(operator, materials.search_items, self.token)}
		self.assertEqual(found, {allowed})
		self.assertEqual(
			[r["item_code"] for r in self._as(operator, materials.search_items, f"IN{self.token}BC")],
			[allowed],
		)
		self.assertNotIn(hidden, found)

	def test_filter_options_use_applicable_for_of_the_listed_doctype(self):
		operator = self._user("op6", ["Card Operator"])
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": operator,
				"allow": "Item Group",
				"for_value": self.parts,
				"applicable_for": "Item Group",
			}
		).insert(ignore_permissions=True)
		groups = [o["value"] for o in self._as(operator, catalog.filter_options, "item_group", self.token)]
		self.assertEqual(groups, [self.parts])
		# a restriction that applies to Item only limits items, not the group list
		other = self._user("op7", ["Card Operator"])
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": other,
				"allow": "Item Group",
				"for_value": self.parts,
				"applicable_for": "Item",
			}
		).insert(ignore_permissions=True)
		groups = {o["value"] for o in self._as(other, catalog.filter_options, "item_group", self.token)}
		self.assertTrue({self.root, self.parts, self.other_group} <= groups)

	def test_barcode_and_oem_need_three_characters(self):
		code = self._item("SHORT", barcode="Z9")
		self.assertNotIn(code, self._codes(catalog.search("Z9")))
