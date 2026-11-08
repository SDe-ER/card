# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Catalog restricted read with permission query rules (2026-11-09). ERPNext version-16 v16.54.0
registers ``permission_query_conditions`` for Item and ``*`` (Company Restriction). The restricted
read of the Card portal roles used to return nothing whenever such a hook existed, so the operator's
catalog was empty. It now applies the hooks the way ``frappe.get_list`` does; a Permission Query
server script still closes the read."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card import catalog
from card.tests import test_catalog as base

KEEP = "KEEPME"


def only_kept_items(user, doctype=None):
	"""Test rule on Item: only items whose name carries the KEEP marker (string condition, as many
	apps return one; no LIKE wildcard, which a raw condition cannot carry next to bound values)."""
	return f"locate('{KEEP}', `tabItem`.`item_name`) > 0"


def drop_marked_oem(user, doctype=None):
	"""Test rule on ``*``: hide OEM rows marked DROP (pypika condition, as ERPNext returns one)."""
	if doctype != "Item Manufacturer":
		return None
	from pypika import functions as fn

	table = frappe.qb.DocType("Item Manufacturer")
	return fn.Substring(table.manufacturer_part_no, 1, 4) != "DROP"


def _with_rules(rules):
	real = frappe.get_hooks

	def get_hooks(hook=None, default=None, app_name=None):
		if hook == "permission_query_conditions":
			merged = dict(real(hook, {}, app_name) or {})
			for doctype, methods in rules.items():
				merged[doctype] = list(merged.get(doctype, [])) + methods
			return merged
		return real(hook, default, app_name)

	return patch.object(frappe, "get_hooks", side_effect=get_hooks)


class TestCatalogQueryRules(IntegrationTestCase):
	# the catalog test builders, without running that class's tests again
	setUp = base.TestCatalog.setUp
	tearDown = base.TestCatalog.tearDown
	_group = base.TestCatalog._group
	_brand = base.TestCatalog._brand
	_manufacturer = base.TestCatalog._manufacturer
	_item = base.TestCatalog._item
	_oem = base.TestCatalog._oem
	_alternative = base.TestCatalog._alternative
	_user = base.TestCatalog._user
	_as = base.TestCatalog._as
	_codes = base.TestCatalog._codes

	def _items(self):
		kept = self._item("A", item_name=f"{KEEP} A {self.token}", allow_alternative_item=1)
		hidden = self._item("B", item_name=f"Other B {self.token}", allow_alternative_item=1)
		return kept, hidden

	def test_operator_catalog_applies_item_rules(self):
		kept, hidden = self._items()
		self._alternative(kept, hidden)
		self._oem(hidden, f"RULE-OEM-{self.token}")
		operator = self._user("qr1", ["Card Operator"])
		with _with_rules({"Item": [f"{__name__}.only_kept_items"]}):
			result = self._as(operator, catalog.search, self.token, page_length=50)
			self.assertEqual(self._codes(result), [kept])
			# the hidden item is neither an alternative, nor found by its OEM number, nor paged
			self.assertEqual(result["items"][0]["alternatives"], [])
			self.assertEqual(self._as(operator, catalog.search, f"RULE-OEM-{self.token}")["items"], [])
			self.assertFalse(self._as(operator, catalog.search, self.token, page_length=1)["has_more"])

	def test_operator_and_item_reader_get_the_same_answer_under_rules(self):
		kept, _hidden = self._items()
		operator = self._user("qr2", ["Card Operator"])
		reader = self._user("qr3", ["Stock User"])
		with _with_rules({"Item": [f"{__name__}.only_kept_items"]}):
			restricted = self._codes(self._as(operator, catalog.search, self.token, page_length=50))
			standard = self._codes(self._as(reader, catalog.search, self.token, page_length=50))
		self.assertEqual(restricted, [kept])
		self.assertEqual(restricted, standard)

	def test_star_rule_reaches_oem_numbers(self):
		code = self._item("C", item_name=f"{KEEP} C {self.token}")
		self._oem(code, f"KEEP-{self.token}")
		self._oem(code, f"DROP-{self.token}")
		operator = self._user("qr4", ["Card Operator"])
		with _with_rules({"*": [f"{__name__}.drop_marked_oem"]}):
			row = self._as(operator, catalog.search, code)["items"][0]
			self.assertEqual([o["part_no"] for o in row["oem"]], [f"KEEP-{self.token}"])
			self.assertEqual(self._as(operator, catalog.search, f"DROP-{self.token}")["items"], [])

	def test_without_rules_the_operator_still_sees_the_catalog(self):
		kept, hidden = self._items()
		operator = self._user("qr5", ["Card Operator"])
		self.assertEqual(
			sorted(self._codes(self._as(operator, catalog.search, self.token, page_length=50))),
			sorted([kept, hidden]),
		)

	def test_permission_query_server_script_closes_the_restricted_read(self):
		self._items()
		operator = self._user("qr6", ["Card Operator"])
		scripts = {"permission_query": {"Item": "Some Script"}}
		with patch(
			"frappe.core.doctype.server_script.server_script_utils.get_server_script_map",
			return_value=scripts,
		):
			self.assertEqual(self._as(operator, catalog.search, self.token, page_length=50)["items"], [])

	def test_brand_and_group_filters_page_under_rules(self):
		self._items()
		operator = self._user("qr7", ["Card Operator"])
		with _with_rules({"*": [f"{__name__}.drop_marked_oem"]}):
			self.assertEqual(
				[o["value"] for o in self._as(operator, catalog.filter_options, "brand", self.token)],
				[self.brand],
			)
			groups = [
				o["value"] for o in self._as(operator, catalog.filter_options, "item_group", self.token)
			]
			self.assertIn(self.parts, groups)
