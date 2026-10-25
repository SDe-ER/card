# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""WS-013 (Owner, 2026-10-26): the application name is CARD in every language. The record
names stay "Card" (frappe names the Workspace, Workspace Sidebar and Desktop Icon after
their label), so msgid "Card" maps to exactly "CARD" in every card locale, and card ships
a locale for every language frappe translates "Card" into (fr "Carte", fa "کارت", ...)."""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase


class TestCardNameNotTranslated(IntegrationTestCase):
	def _locale_dir(self, app):
		return os.path.join(frappe.get_app_path(app), "locale")

	def _app_name_msgstr(self, path):
		# the plain msgid only: an entry under a msgctxt is another string
		lines = open(path, encoding="utf-8").read().split("\n")
		return [
			re.fullmatch(r'msgstr "(.*)"', lines[i + 1]).group(1)
			for i, line in enumerate(lines)
			if line == 'msgid "Card"' and not (i and lines[i - 1].startswith("msgctxt"))
		]

	def test_card_msgid_maps_to_card_in_all_locales(self):
		po_files = [f for f in os.listdir(self._locale_dir("card")) if f.endswith(".po")]
		self.assertTrue(po_files, "no .po locale files found")
		for po in po_files:
			self.assertEqual(
				self._app_name_msgstr(os.path.join(self._locale_dir("card"), po)),
				["CARD"],
				f"{po}: msgid 'Card' must map to 'CARD' exactly once",
			)

	def test_every_installed_language_has_a_card_locale(self):
		card_po = set(os.listdir(self._locale_dir("card")))
		missing = set()
		for app in frappe.get_installed_apps():
			if app != "card" and os.path.isdir(self._locale_dir(app)):
				missing.update(f for f in os.listdir(self._locale_dir(app)) if f.endswith(".po"))
		self.assertFalse(
			sorted(missing - card_po),
			'add card/locale/<lang>.po with msgid "Card" -> msgstr "CARD" for these languages '
			"(an installed app ships them, so they would show its own word for Card)",
		)

	def test_apps_screen_titles(self):
		entries = frappe.get_hooks("add_to_apps_screen", app_name="card")
		self.assertEqual([e["title"] for e in entries], ["CARD", "CARD Mobile"])


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
		allow = {"Card"}  # the application name, CARD in every language (WS-013)
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


class TestNoArabicFallback(IntegrationTestCase):
	"""v4.1.2 (Owner): an English user sees no Arabic. Stored Select values and the names of
	the workspace widgets are Arabic and stay so (data), so each one shown on screen needs an
	English translation in en.po; the other non-Arabic CARD locales carry one too, so they fall
	back to English, never to Arabic."""

	ARABIC = re.compile(r"[؀-ۿ]")
	FALLBACK_LOCALES = ("en.po", "bn.po", "hi.po", "ur.po")

	def _shown_arabic(self):
		import glob
		import json

		shown = set()
		root = frappe.get_app_path("card")
		for path in glob.glob(os.path.join(root, "**", "*.json"), recursive=True):
			if os.sep + "tests" + os.sep in path:
				continue
			with open(path, encoding="utf-8") as f:
				data = json.load(f)
			for doc in data if isinstance(data, list) else [data]:
				if not isinstance(doc, dict):
					continue
				for field in doc.get("fields") or []:
					if field.get("fieldtype") == "Select":
						shown.update(
							o for o in (field.get("options") or "").split("\n") if self.ARABIC.search(o)
						)
					if self.ARABIC.search(field.get("description") or ""):
						shown.add(field["description"])
				if doc.get("doctype") == "Workspace":
					# shortcut names and header blocks are drawn through __() by the workspace widgets
					shown.update(
						s["label"] for s in doc.get("shortcuts") or [] if self.ARABIC.search(s["label"])
					)
					for block in json.loads(doc.get("content") or "[]"):
						text = (block.get("data") or {}).get("text") or ""
						if block.get("type") == "header" and self.ARABIC.search(text):
							shown.add(text)
				if doc.get("doctype") in ("Number Card", "Dashboard Chart"):
					shown.update(
						v for v in (doc.get("label"), doc.get("chart_name")) if v and self.ARABIC.search(v)
					)
		return shown

	def test_arabic_display_values_have_english(self):
		shown = self._shown_arabic()
		self.assertTrue(shown)
		locale_dir = os.path.join(frappe.get_app_path("card"), "locale")
		for po in self.FALLBACK_LOCALES:
			entries = TestCardLocaleCardStringsOnly._parse_po(None, os.path.join(locale_dir, po))
			missing = sorted(v for v in shown if not entries.get(v) or self.ARABIC.search(entries[v]))
			self.assertFalse(
				missing, f"{po}: Arabic values shown without a non-Arabic translation: {missing}"
			)
