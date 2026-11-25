"""A child DocType of CARD never holds a table field (#320).

The Desk form supports a table one level deep only. A grid looks its own field up on the DocType of the
open form (``frappe/public/js/frappe/form/grid.js`` ``setup_fields``), so a Table field inside a child
row has no docfield there and the row editor fails to open. The server saves one level too
(``frappe/model/document.py`` ``update_children``). A table that belongs to a child row is therefore
declared on the parent DocType and keyed by a column, as ``approval_tier_thresholds`` is on Card Settings.

The check reads the DocType JSON files, so it needs no site.
"""

import json
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
TABLE_FIELDTYPES = ("Table", "Table MultiSelect")


def _doctypes():
	for path in sorted(APP_DIR.glob("*/doctype/*/*.json")):
		doc = json.loads(path.read_text(encoding="utf-8"))
		if isinstance(doc, dict) and doc.get("doctype") == "DocType":
			yield doc


class TestChildDoctypeTables(unittest.TestCase):
	def test_child_doctypes_are_found(self):
		names = {d["name"] for d in _doctypes() if d.get("istable")}
		self.assertIn("Card Company Settings", names)
		self.assertIn("Card Approval Tier Threshold", names)

	def test_no_child_doctype_has_a_table_field(self):
		nested = [
			f"{d['name']}.{f['fieldname']}"
			for d in _doctypes()
			if d.get("istable")
			for f in d.get("fields", [])
			if f.get("fieldtype") in TABLE_FIELDTYPES
		]
		self.assertEqual(nested, [], "the Desk row editor cannot render a table inside a child row")

	def test_approval_tier_thresholds_is_on_card_settings(self):
		by_name = {d["name"]: d for d in _doctypes()}
		tables = {
			f["fieldname"]: f
			for f in by_name["Card Settings"]["fields"]
			if f.get("fieldtype") in TABLE_FIELDTYPES
		}
		df = tables.get("approval_tier_thresholds")
		self.assertIsNotNone(df)
		self.assertEqual(df["options"], "Card Approval Tier Threshold")
		self.assertEqual(df.get("permlevel"), 1)
		self.assertFalse(df.get("description"))  # no field help under a field
