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
		self.assertGreater(checked, 0, 'no locale listed msgid "Card" to check')


class TestCardLocaleCardStringsOnly(IntegrationTestCase):
	"""Owner standing rule (2026-10-14): card/locale/*.po may contain CARD strings
	only. card loads last in apps.txt, so a generic msgid (Customer, Company,
	Amount, ...) translated here overrides frappe/erpnext SITE-WIDE. This guard
	fails when a card msgid also exists in a frappe/erpnext po file for the same
	language with a DIFFERENT msgstr — except the explicit allowlist ("Card" and
	CARD doctype/report display-name overrides)."""

	def _parse_po(self, path):
		entries = {}
		if not os.path.exists(path):
			return entries
		text = open(path, encoding="utf-8").read()
		pattern = re.compile(
			r'(?s)(?:msgctxt\s+((?:"(?:[^"\\]|\\.)*"\s*)+?))?'
			r'msgid\s+((?:"(?:[^"\\]|\\.)*"\s*)+?)msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*)+)'
		)

		def joinstr(s):
			parts = re.findall(r'"((?:[^"\\]|\\.)*)"', s)
			raw = "".join(parts)
			return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

		for m in pattern.finditer(text):
			k = joinstr(m.group(2))
			if k:
				# Frappe keys a translation with context as "msgid:context" (frappe.gettext), so a
				# context entry never overrides the plain msgid of another app
				if m.group(1):
					k = f"{k}:{joinstr(m.group(1))}"
				entries[k] = joinstr(m.group(3))
		return entries

	def _allowlist(self):
		allow = {"Card"}  # app name, never translated (RULE 0)
		# CARD-owned display names (e.g. "Card Settings" -> "Settings") are ours to translate
		allow.update(frappe.get_all("DocType", filters={"module": "Card"}, pluck="name"))
		allow.update(frappe.get_all("Report", filters={"module": "Card"}, pluck="name"))
		return allow

	def test_no_generic_msgid_overrides(self):
		allow = self._allowlist()
		card_locale = os.path.join(frappe.get_app_path("card"), "locale")
		violations = []
		for po in [f for f in os.listdir(card_locale) if f.endswith(".po")]:
			card_entries = self._parse_po(os.path.join(card_locale, po))
			for app in ("frappe", "erpnext"):
				other = self._parse_po(os.path.join(frappe.get_app_path(app), "locale", po))
				for msgid, msgstr in card_entries.items():
					if msgid in allow or msgid not in other:
						continue
					# an EMPTY msgstr ships no translation (not compiled into the MO),
					# so card translating such a msgid overrides nothing site-wide
					if other[msgid] and other[msgid] != msgstr:
						violations.append(f"{po}: {msgid!r} (card={msgstr!r} vs {app}={other[msgid]!r})")
		self.assertFalse(
			violations,
			"card locale overrides generic frappe/erpnext strings site-wide:\n" + "\n".join(violations),
		)


class TestCardSettingsDisplayName(IntegrationTestCase):
	def test_card_settings_display_name(self):
		locale_dir = os.path.join(frappe.get_app_path("card"), "locale")
		expected = {"ar.po": "الإعدادات", "en.po": "Settings"}
		for po, value in expected.items():
			text = open(os.path.join(locale_dir, po), encoding="utf-8").read()
			block = re.findall(r'^msgid "Card Settings"\nmsgstr "(.*)"', text, re.M)
			self.assertEqual(block, [value], f"{po}: 'Card Settings' must map to {value!r} exactly once")
