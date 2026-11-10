# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-124 (WP-08, FR-015, issue #50): settings that no code reads are marked deprecated, not deleted.
The columns and stored values stay; the fields are hidden and read only, and nothing in the app reads
them (a grep over the app's code, the DocType JSON, patches, tests and translations excluded)."""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase

DEPRECATED = {
	"Card Settings": ("auto_submit", "notify_on_posting"),
	"Card Company Settings": ("bank_cash_account", "mode_of_payment"),
}
DESCRIPTION = "Deprecated – not used"
CODE_EXTENSIONS = (".py", ".js", ".ts", ".vue", ".html")
# where a deprecated fieldname may still appear: the field definitions, the one-time v1.2 defaults patch
# (already run; it only wrote the stored default), the tests and the translations
EXCLUDED_DIRS = ("patches", "tests", "locale", "node_modules", "dist")


class TestDeprecatedSettings(IntegrationTestCase):
	def test_deprecated_fields_hidden_read_only_and_described(self):
		for doctype, fieldnames in DEPRECATED.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fieldnames:
				with self.subTest(doctype=doctype, field=fieldname):
					df = meta.get_field(fieldname)
					self.assertTrue(df, "the column stays (data kept)")
					self.assertEqual((df.hidden, df.read_only), (1, 1))
					self.assertEqual(df.description, DESCRIPTION)

	def test_deprecated_description_has_arabic(self):
		po = os.path.join(frappe.get_app_path("card"), "locale", "ar.po")
		text = open(po, encoding="utf-8").read()
		match = re.search(r'\nmsgid "%s"\nmsgstr "([^"]+)"' % re.escape(DESCRIPTION), text)
		self.assertTrue(match and match.group(1), "ar.po has no translation of the deprecation note")

	def test_nothing_in_the_app_reads_them(self):
		app = frappe.get_app_path("card")
		roots = [app, os.path.join(os.path.dirname(app), "frontend", "src")]
		names = [f for fields in DEPRECATED.values() for f in fields]
		pattern = re.compile(r"\b(%s)\b" % "|".join(names))
		readers = []
		for root in roots:
			for dirpath, dirnames, filenames in os.walk(root):
				dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
				for filename in filenames:
					if not filename.endswith(CODE_EXTENSIONS):
						continue
					path = os.path.join(dirpath, filename)
					with open(path, encoding="utf-8", errors="ignore") as fh:
						for number, line in enumerate(fh, 1):
							if pattern.search(line):
								readers.append(f"{os.path.relpath(path, root)}:{number}: {line.strip()}")
		self.assertEqual(readers, [], "a deprecated setting is read; wire it up and document it instead")
