# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""The Card workspace shows a number card only when the label of its row equals the translated record name.

Frappe finds the data of a number card block with `row.label == __(number_card_name)`: the server sends the row
label through `_()` (frappe/desk/desktop.py, `get_number_cards`) and the Desk compares it with the translated block
name (frappe/public/js/frappe/views/workspace/blocks/block.js, `make`). A row that does not match is not drawn, and
nothing reports it. This check reads the fixture and the locale files only: it needs no site."""

import glob
import json
import os
import re

from frappe.tests import UnitTestCase

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = re.compile(
	r'(?s)(?:msgctxt\s+((?:"(?:[^"\\]|\\.)*"\s*)+?))?'
	r'msgid\s+((?:"(?:[^"\\]|\\.)*"\s*)+?)msgstr\s+((?:"(?:[^"\\]|\\.)*"\s*)+)'
)


def _text(quoted):
	raw = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', quoted))
	return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def translations(path):
	"""msgid -> msgstr of the entries without a context; an empty msgstr ships no translation."""
	with open(path, encoding="utf-8") as fh:
		text = fh.read()
	return {
		_text(m.group(2)): _text(m.group(3))
		for m in ENTRY.finditer(text)
		if not m.group(1) and _text(m.group(2)) and _text(m.group(3))
	}


def number_card_rows():
	with open(os.path.join(APP, "fixtures", "workspace.json"), encoding="utf-8") as fh:
		workspace = next(doc for doc in json.load(fh) if doc.get("name") == "Card")
	return [(row["number_card_name"], row.get("label") or row["number_card_name"]) for row in workspace["number_cards"]]


def unmatched_rows(po_path):
	"""The rows the Desk would not draw in the language of `po_path`: (record name, label shown, name shown)."""
	entries = translations(po_path)
	return [
		(name, entries.get(label, label), entries.get(name, name))
		for name, label in number_card_rows()
		if entries.get(label, label) != entries.get(name, name)
	]


class TestWorkspaceNumberCardLabels(UnitTestCase):
	def test_every_block_has_a_row(self):
		with open(os.path.join(APP, "fixtures", "workspace.json"), encoding="utf-8") as fh:
			workspace = next(doc for doc in json.load(fh) if doc.get("name") == "Card")
		blocks = [
			block["data"]["number_card_name"]
			for block in json.loads(workspace["content"])
			if block["type"] == "number_card"
		]
		self.assertTrue(blocks)
		self.assertEqual(sorted(blocks), sorted(name for name, _label in number_card_rows()))

	def test_row_label_equals_the_translated_record_name_in_english_and_arabic(self):
		for po in ("en.po", "ar.po"):
			with self.subTest(locale=po):
				self.assertEqual(unmatched_rows(os.path.join(APP, "locale", po)), [])

	def test_row_label_equals_the_translated_record_name_in_every_locale(self):
		locales = sorted(glob.glob(os.path.join(APP, "locale", "*.po")))
		self.assertTrue(locales)
		for path in locales:
			with self.subTest(locale=os.path.basename(path)):
				self.assertEqual(unmatched_rows(path), [])
