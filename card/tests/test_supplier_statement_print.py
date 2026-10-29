# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""The A4 print of the Equipment Supplier Statement: one layout for both print
paths (the report's html template and the standard Report Print Format the PDF
dialog pre-selects)."""

import re

import frappe
from frappe.tests import IntegrationTestCase

REPORT = "Equipment Supplier Statement"
PRINT_FORMAT = "Equipment Supplier Statement A4"
REPORT_DIR = ("card", "report", "equipment_supplier_statement")


def _read(*parts):
	with open(frappe.get_app_path("card", *parts), encoding="utf-8") as f:
		return f.read().replace("\r\n", "\n")


class TestSupplierStatementPrint(IntegrationTestCase):
	def test_print_format_is_a_standard_report_format(self):
		pf = frappe.get_doc("Print Format", PRINT_FORMAT)
		self.assertEqual(
			(pf.print_format_for, pf.report, pf.print_format_type, pf.standard, pf.disabled),
			("Report", REPORT, "JS", "Yes", 0),
		)

	def test_both_print_paths_use_the_same_layout(self):
		template = _read(*REPORT_DIR, "equipment_supplier_statement.html")
		self.assertEqual(
			frappe.db.get_value("Print Format", PRINT_FORMAT, "html").replace("\r\n", "\n"), template
		)
		shipped = _read(
			"card", "print_format", "equipment_supplier_statement_a4", "equipment_supplier_statement_a4.json"
		)
		self.assertEqual(frappe.parse_json(shipped)["html"], template)

		from frappe.desk.query_report import get_print_format_data

		self.assertEqual(get_print_format_data(PRINT_FORMAT)["html"].replace("\r\n", "\n"), template)

	def test_report_preselects_the_format(self):
		js = _read(*REPORT_DIR, "equipment_supplier_statement.js")
		self.assertIn(f'report.report_doc.default_print_format = "{PRINT_FORMAT}"', js)

	def test_template_escapes_text_and_has_no_line_comments_in_code(self):
		template = _read(*REPORT_DIR, "equipment_supplier_statement.html")
		# the microtemplate compiler joins lines, so a // comment would swallow the rest of the code block
		for block in re.findall(r"{%(?!=)(.*?)%}", template, flags=re.S):
			self.assertNotRegex(block, r"(?<![:\"])//")
		for field in (
			"filters.company",
			"filters.supplier",
			"statement_type",
			"item.label",
			"String(raw.message)",
		):
			self.assertIn(f"esc({field}", template)
		self.assertIn("size: A4 landscape", template)

	def test_new_strings_are_translated(self):
		po = _read("locale", "ar.po")
		for msgid in (
			"Issue date",
			"Accountant signature",
			"Reviewer signature",
			"Supplier signature",
			"Includes draft cards",
		):
			self.assertRegex(po, rf'msgid "{msgid}"\nmsgstr "[^"]+"')
