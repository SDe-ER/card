# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Every CARD locale translates the navigation layer (owner decision 2026-11-26).

The navigation layer is the text a user reads before a form opens: the Card workspace (headers, shortcuts,
links, quick list, number cards, chart), the module sidebars under `card/card/sidebar/` and the Number Card and
Dashboard Chart records. English and Arabic carry the full catalogue; every other locale carries at least this
layer, in its own language.

These checks read the fixtures and the locale files only: they need no site."""

import glob
import json
import os
import re

from frappe.tests import UnitTestCase

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE = os.path.join(APP, "locale")
QUOTED = r'"(?:[^"\\]|\\.)*"'
ENTRY = re.compile(
	r"(?s)(?:msgctxt\s+((?:" + QUOTED + r"\s*)+?))?"
	r"msgid\s+((?:" + QUOTED + r"\s*)+?)msgstr\s+((?:" + QUOTED + r"\s*)+)"
)
PLACEHOLDER = re.compile(r"\{\d+\}")
ARABIC = re.compile(r"[؀-ۿ]")

# Sidebar labels CARD does not own. An ERPNext DocType keeps the name ERPNext gives it, and "Catalog" is a
# generic word: a plain translation in a CARD locale would override Frappe and ERPNext on the whole site
# (`test_no_generic_msgid_overrides`).
NOT_CARD_LABELS = {"Catalog"}

# (locale, msgid) pairs whose correct translation is the English text itself.
SAME_AS_SOURCE = set()


def _text(quoted):
	raw = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', quoted))
	return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def entries(path):
	"""(msgctxt or None, msgid, msgstr) of every entry of a locale file, without the header."""
	with open(path, encoding="utf-8") as fh:
		text = fh.read()
	found = [
		(_text(m.group(1)) if m.group(1) else None, _text(m.group(2)), _text(m.group(3)))
		for m in ENTRY.finditer(text)
	]
	return [entry for entry in found if entry[1]]


def plain(path):
	"""msgid -> msgstr of the entries without a context."""
	return {msgid: msgstr for context, msgid, msgstr in entries(path) if context is None}


def locales():
	return sorted(glob.glob(os.path.join(LOCALE, "*.po")))


def lang(path):
	return os.path.basename(path)[: -len(".po")]


def _json(*parts):
	with open(os.path.join(APP, *parts), encoding="utf-8") as fh:
		return json.load(fh)


def card_workspace():
	return next(doc for doc in _json("fixtures", "workspace.json") if doc.get("name") == "Card")


def workspace_labels():
	workspace = card_workspace()
	labels = {workspace["label"]}
	for table in ("shortcuts", "links", "quick_lists", "number_cards", "charts"):
		for row in workspace.get(table) or []:
			labels.update(
				v for v in (row.get("label"), row.get("number_card_name"), row.get("chart_name")) if v
			)
	labels.update(
		block["data"]["text"] for block in json.loads(workspace["content"]) if block["type"] == "header"
	)
	return labels


def sidebar_titles():
	return {
		_json("card", "sidebar", folder, f"{folder}.json")["title"]
		for folder in os.listdir(os.path.join(APP, "card", "sidebar"))
	}


def sidebar_labels():
	"""The item labels CARD owns: its own DocTypes, reports and pages, and its own wording for a link."""
	own_doctypes = {
		_json("card", "doctype", folder, f"{folder}.json")["name"]
		for folder in os.listdir(os.path.join(APP, "card", "doctype"))
		if os.path.isfile(os.path.join(APP, "card", "doctype", folder, f"{folder}.json"))
	}
	labels = set()
	for folder in os.listdir(os.path.join(APP, "card", "sidebar")):
		for item in _json("card", "sidebar", folder, f"{folder}.json")["items"]:
			label = item.get("label")
			foreign_name = (
				item.get("link_type") == "DocType"
				and item.get("link_to") == label
				and label not in own_doctypes
			)
			if label and not foreign_name and label not in NOT_CARD_LABELS:
				labels.add(label)
	return labels


def record_labels():
	labels = set()
	for doc in _json("fixtures", "number_card.json") + _json("fixtures", "dashboard_chart.json"):
		labels.update(v for v in (doc.get("name"), doc.get("label"), doc.get("chart_name")) if v)
	return labels


def navigation_layer():
	return workspace_labels() | sidebar_titles() | sidebar_labels() | record_labels()


def number_card_row_labels():
	return [row["label"] for row in card_workspace()["number_cards"]]


class TestLocaleNavigationLayer(UnitTestCase):
	def test_the_navigation_layer_is_found(self):
		self.assertGreater(len(sidebar_titles()), 5)
		self.assertGreater(len(sidebar_labels()), 40)
		self.assertEqual(len(number_card_row_labels()), 9)
		self.assertNotIn("Purchase Invoice", sidebar_labels())

	def test_no_entry_has_an_empty_translation(self):
		for path in locales():
			with self.subTest(locale=lang(path)):
				self.assertEqual([msgid for _context, msgid, msgstr in entries(path) if not msgstr], [])

	def test_no_entry_is_given_twice(self):
		for path in locales():
			with self.subTest(locale=lang(path)):
				keys = [(context, msgid) for context, msgid, _msgstr in entries(path)]
				self.assertEqual(sorted({key for key in keys if keys.count(key) > 1}, key=str), [])

	def test_placeholders_are_kept(self):
		for path in locales():
			with self.subTest(locale=lang(path)):
				lost = [
					msgid
					for _context, msgid, msgstr in entries(path)
					if msgstr and sorted(PLACEHOLDER.findall(msgid)) != sorted(PLACEHOLDER.findall(msgstr))
				]
				self.assertEqual(lost, [])

	def test_navigation_layer_is_translated_in_every_locale(self):
		layer = navigation_layer()
		for path in locales():
			if lang(path) == "en":
				continue  # English reads the source text; its Arabic-named records: TestNoArabicFallback
			translated = plain(path)
			# an Arabic record name is its own Arabic text: the Arabic locale needs no entry for it
			needed = {m for m in layer if not ARABIC.search(m)} if lang(path) == "ar" else layer
			with self.subTest(locale=lang(path)):
				self.assertEqual(sorted(msgid for msgid in needed if not translated.get(msgid)), [])
				if lang(path) != "ar":
					self.assertEqual(
						sorted(
							msgid
							for msgid in layer
							if translated.get(msgid) == msgid and (lang(path), msgid) not in SAME_AS_SOURCE
						),
						[],
					)

	def test_english_names_every_sidebar(self):
		english = plain(os.path.join(LOCALE, "en.po"))
		self.assertEqual(sorted(title for title in sidebar_titles() if not english.get(title)), [])

	def test_number_card_labels_are_translated_in_every_locale(self):
		for path in locales():
			if lang(path) == "en":
				continue
			translated = plain(path)
			with self.subTest(locale=lang(path)):
				self.assertEqual(
					[label for label in number_card_row_labels() if translated.get(label, label) == label], []
				)

	def test_card_suffix_of_a_number_card_label_is_kept(self):
		"""A row label that ends with "(CARD)" keeps it in every locale. Arabic is the exception: its labels
		carry no "(CARD)" at all (the text Arabic users know since v4.10.0)."""
		marked = [label for label in number_card_row_labels() if label.endswith("(CARD)")]
		self.assertTrue(marked)
		for path in locales():
			if lang(path) == "ar":
				continue
			translated = plain(path)
			with self.subTest(locale=lang(path)):
				self.assertEqual(
					[label for label in marked if not translated.get(label, "").endswith("(CARD)")], []
				)
