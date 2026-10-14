# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""RULE 0 invariant: the module/app name "Card" is never translated. An empty
msgstr is insufficient (frappe/erpnext may translate "Card"), so every card
locale that lists msgid "Card" must map it to exactly "Card"."""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase


class TestCardNameNotTranslated(IntegrationTestCase):
	def test_card_msgid_maps_to_card_in_all_locales(self):
		locale_dir = os.path.join(frappe.get_app_path("card"), "locale")
		po_files = [f for f in os.listdir(locale_dir) if f.endswith(".po")]
		self.assertTrue(po_files, "no .po locale files found")
		checked = 0
		for po in po_files:
			text = open(os.path.join(locale_dir, po), encoding="utf-8").read()
			block = re.search(r'^msgid "Card"\n(msgstr "(?P<v>.*)")', text, re.M)
			if not block:
				continue
			checked += 1
			self.assertEqual(
				block.group("v"), "Card", f"{po}: 'Card' must not be translated (got {block.group('v')!r})"
			)
		self.assertGreater(checked, 0, "no locale listed msgid \"Card\" to check")


class TestCardSettingsDisplayName(IntegrationTestCase):
	def test_card_settings_display_name(self):
		locale_dir = os.path.join(frappe.get_app_path("card"), "locale")
		expected = {"ar.po": "الإعدادات", "en.po": "Settings"}
		for po, value in expected.items():
			text = open(os.path.join(locale_dir, po), encoding="utf-8").read()
			block = re.findall(r'^msgid "Card Settings"\nmsgstr "(.*)"', text, re.M)
			self.assertEqual(block, [value], f"{po}: 'Card Settings' must map to {value!r} exactly once")
