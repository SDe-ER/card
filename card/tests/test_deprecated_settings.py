# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-124 (WP-08, FR-015, issue #50): settings that no code reads are marked deprecated, not deleted.
The columns and stored values stay; the fields are hidden and read only, and nothing in the app reads
them (a grep over the app's code and JSON; the two DocType JSON files that define them, patches, tests and
translations excluded). A retired account field is not checked when Card Settings is saved."""

import os
import re

import frappe
from frappe.tests import IntegrationTestCase

DEPRECATED = {
	"Card Settings": ("auto_submit", "notify_on_posting"),
	"Card Company Settings": ("bank_cash_account", "mode_of_payment"),
}
DESCRIPTION = "Deprecated – not used"
CODE_EXTENSIONS = (".py", ".js", ".ts", ".vue", ".html", ".json")
# where a deprecated fieldname may still appear: the field definitions (the two DocType JSON files), the
# one-time v1.2 defaults patch (already run; it only wrote the stored default), the tests and the translations
EXCLUDED_DIRS = ("patches", "tests", "locale", "node_modules", "dist")
DEFINITIONS = (
	os.path.join("card", "doctype", "card_settings", "card_settings.json"),
	os.path.join("card", "doctype", "card_company_settings", "card_company_settings.json"),
)


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
		with open(po, encoding="utf-8") as fh:
			text = fh.read()
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
					if root == app and os.path.relpath(path, app) in DEFINITIONS:
						continue
					with open(path, encoding="utf-8", errors="ignore") as fh:
						for number, line in enumerate(fh, 1):
							if pattern.search(line):
								readers.append(f"{os.path.relpath(path, root)}:{number}: {line.strip()}")
		self.assertEqual(readers, [], "a deprecated setting is read; wire it up and document it instead")

	def test_retired_account_field_does_not_block_saving_settings(self):
		"""A stored account of another company in the hidden bank/cash field cannot be cleared by
		anyone, so the account-company check of Card Settings skips retired fields; a live account
		field is still checked."""
		from card.tests.test_controllers import _ensure_masters

		company = _ensure_masters()["company"]
		other = frappe.db.get_value("Account", {"company": ("!=", company), "is_group": 0}, "name")
		if not other:
			self.skipTest("no account of another company on this site")
		frappe.db.savepoint("retired_account_field")
		try:
			settings = frappe.get_doc("Card Settings")
			row = next((r for r in settings.company_settings if r.company == company), None)
			if row is None:
				row = settings.append("company_settings", {"company": company})
			row.set(DEPRECATED["Card Company Settings"][0], other)
			settings.save(ignore_permissions=True)  # must not raise
			row.diesel_expense_account = other
			with self.assertRaises(frappe.ValidationError):
				settings.save(ignore_permissions=True)
		finally:
			frappe.db.rollback(save_point="retired_account_field")
