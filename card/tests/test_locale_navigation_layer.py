# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Every CARD locale translates the navigation layer (owner decision 2026-11-26).

The navigation layer is the text a user reads before a form opens: the Card workspace (headers, shortcuts,
links, quick list, number cards, chart), the sidebars (`card/card/sidebar/`, `fixtures/sidebar.json` and the
older `fixtures/workspace_sidebar.json`) and the Number Card and Dashboard Chart records. English and Arabic
carry the full catalogue; every other locale carries at least this layer, in its own language.

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

# The full catalogues. `bench update-po-files` writes every new source string into them with an empty msgstr,
# and an empty msgstr only means "show the source text". The check for an empty msgstr therefore covers the
# other locales only: each of their entries is written by hand and exists to give a translation. The
# navigation layer itself is checked in every locale, the full catalogues included.
FULL_CATALOGUES = {"ar", "en"}

# Sidebar labels CARD does not own. A DocType or report of another app keeps the name that app gives it, and
# "Catalog" is a generic word: a plain translation in a CARD locale would override Frappe, ERPNext or HRMS on
# the whole site (`test_no_generic_msgid_overrides`).
NOT_CARD_LABELS = {"Catalog"}

# Generic words that are field labels or Select options of CARD DocTypes. Frappe reads a field or section
# label, a list header and an option of an editable dropdown with the DocType name as context first
# (`__(df.label, null, df.parent)` in form/controls/base_input.js, `__(v, null, doctype)` in
# form/controls/select.js; `frappe._` reads "<text>:<context>" before the plain text). A CARD locale
# translates these words under `msgctxt "<DocType>"` only. A plain entry would replace the wording of Frappe,
# ERPNext or HRMS on the whole site ("Approved" is an HRMS string, and its HRMS wording is accepted for the
# plain form).
GENERIC_WORDS = {
	"Approved",
	"Taxable",
	"Exclusive",
	"Inclusive",
	"Integrity",
	"Origin",
	"Replaces",
	"Confirm {0}",
	"Deductions",
	"Workshop",
	"Effective from",
}

# Status words that Frappe draws with the plain text: a read-only Select value and a list cell go through
# `__(value)` without a context (form/formatters.js), and a context entry of a catalogue is stored as
# "<text>:<context>" only. CARD's own scripts call the plain form too. None of these words is a msgid of the
# frappe, erpnext or hrms version-16 catalogues, so a plain entry overrides nothing; the Arabic catalogue
# carries both the plain entry and the context entries.
PLAIN_STATUS_WORDS = {"Posted", "Built", "Installation"}

# (locale, msgid) pairs whose correct translation is the English text itself.
SAME_AS_SOURCE = set()

# (locale, Arabic msgid) pairs whose correct translation is the text English uses.
SAME_AS_ENGLISH = set()

# Navigation names that are different things and must not read the same in any locale.
DISTINCT_NAMES = [
	("Equipment Needs Summary", "Equipment Needs Review"),
	("Equipment Needs Summary", "Equipment Needs Request"),
	("Equipment Supplier Statement", "Equipment Suppliers Summary"),
	("Equipment Customer Statement", "Equipment Customers Summary"),
	("Equipment Diesel Consumption", "Equipment Diesel Analysis"),
	("Card Equipment Type", "Card Equipment Category"),
]


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


def _records(kind):
	"""The record files of `card/card/<kind>/<name>/<name>.json`."""
	root = os.path.join(APP, "card", kind)
	return [
		_json("card", kind, folder, f"{folder}.json")
		for folder in sorted(os.listdir(root))
		if os.path.isfile(os.path.join(root, folder, f"{folder}.json"))
	]


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


def sidebars():
	"""The module sidebars and the two sidebar fixtures."""
	return (
		_records("sidebar") + _json("fixtures", "sidebar.json") + _json("fixtures", "workspace_sidebar.json")
	)


def sidebar_titles():
	return {doc["title"] for doc in sidebars()}


def sidebar_labels():
	"""The item labels CARD owns: its own DocTypes, reports and pages, and its own wording for a link. The
	name of a DocType or a report of another app is not CARD's to translate."""
	own = {
		"DocType": {doc["name"] for doc in _records("doctype")},
		"Report": {doc["name"] for doc in _records("report")},
	}
	labels = set()
	for doc in sidebars():
		for item in doc.get("items") or []:
			label = item.get("label")
			link_type = item.get("link_type")
			foreign_name = link_type in own and item.get("link_to") == label and label not in own[link_type]
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
		self.assertIn("الصفحة الرئيسية", sidebar_labels())
		self.assertIn("Card Monthly Card", sidebar_labels())

	def test_no_entry_has_an_empty_translation(self):
		for path in locales():
			if lang(path) in FULL_CATALOGUES:
				continue
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

	def test_generic_words_are_translated_under_a_context_only(self):
		for path in locales():
			with self.subTest(locale=lang(path)):
				self.assertEqual(sorted(GENERIC_WORDS & set(plain(path))), [])

	def test_arabic_translates_the_plain_status_words(self):
		arabic = plain(os.path.join(LOCALE, "ar.po"))
		self.assertEqual(sorted(word for word in PLAIN_STATUS_WORDS if not arabic.get(word)), [])
		self.assertFalse(PLAIN_STATUS_WORDS & GENERIC_WORDS)

	def test_navigation_layer_is_translated_in_every_locale(self):
		layer = navigation_layer()
		for path in locales():
			translated = plain(path)
			needed = layer
			if lang(path) == "ar":
				# an Arabic record name is its own Arabic text: the Arabic locale needs no entry for it
				needed = {msgid for msgid in layer if not ARABIC.search(msgid)}
			elif lang(path) == "en":
				# English reads the English source text; only the Arabic names need an English entry
				needed = {msgid for msgid in layer if ARABIC.search(msgid)}
			with self.subTest(locale=lang(path)):
				self.assertEqual(sorted(msgid for msgid in needed if not translated.get(msgid)), [])
				if lang(path) not in FULL_CATALOGUES:
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

	def test_arabic_text_is_not_left_in_english(self):
		"""An Arabic msgid (a stored Select value, a record name, an Arabic label) is translated into the
		language of the locale: its text is not the text of `en.po`."""
		english = plain(os.path.join(LOCALE, "en.po"))
		for path in locales():
			if lang(path) in FULL_CATALOGUES:
				continue
			with self.subTest(locale=lang(path)):
				self.assertEqual(
					sorted(
						msgid
						for msgid, msgstr in plain(path).items()
						if ARABIC.search(msgid)
						and msgstr == english.get(msgid)
						and (lang(path), msgid) not in SAME_AS_ENGLISH
					),
					[],
				)

	def test_different_names_read_differently(self):
		for path in locales():
			translated = plain(path)
			with self.subTest(locale=lang(path)):
				self.assertEqual(
					[
						pair
						for pair in DISTINCT_NAMES
						if translated.get(pair[0], pair[0]) == translated.get(pair[1], pair[1])
					],
					[],
				)

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
