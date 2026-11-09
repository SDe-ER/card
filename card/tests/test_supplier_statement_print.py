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

	def test_totals_table_follows_the_rows_and_no_css_variables(self):
		template = _read(*REPORT_DIR, "equipment_supplier_statement.html")
		# the summary figures print as a "Totals" table after the rows, before the signatures
		self.assertLess(template.index('class="ess-rows"'), template.index('class="ess-totals"'))
		self.assertLess(template.index('class="ess-totals"'), template.index('class="ess-signs"'))
		# wkhtmltopdf (old QtWebKit) drops CSS custom properties and cannot shape Arabic from webfonts
		self.assertNotIn("var(--", template)
		self.assertNotIn("@import", template)
		# owner 2026-11-09: no equipment number, rate type or rate column in the print; widths fill the A4 width
		# additions and deductions are optional columns (hidden when no row has a value)
		self.assertIn("var optional = { additions: 1, deductions: 1 };", template)
		# the Arabic filter value is printed in the user's language
		self.assertIn('__("Owned equipment")', template)
		for field in ("equipment", "rate_type", "rate"):
			# a column entry is ["<fieldname>", <width>, ...]; the totals key lists are plain names
			self.assertNotRegex(template, r'\["' + field + r'", \d')
		for widths in re.findall(r"\? (\[\[.*?\]\])\n\t\t: (\[\[.*?\]\]);", template, flags=re.S)[0]:
			self.assertAlmostEqual(sum(float(w) for w in re.findall(r"\[\"\w+\", ([\d.]+)", widths)) + 3, 100)

	def test_printed_totals_are_a_short_statement(self):
		# owner 2026-11-09: the printed totals keep only opening + period charges - payments = closing;
		# the reconciliation figures stay on the screen report. Picked by stable summary keys.
		template = _read(*REPORT_DIR, "equipment_supplier_statement.html")
		self.assertIn('["opening", "accrued", "paid", "closing"]', template)
		self.assertIn('["equipment", "days", "hours"]', template)
		source = _read(*REPORT_DIR, "equipment_supplier_statement.py")
		for key in ("equipment", "days", "hours", "net_cards", "accrued", "opening", "paid", "closing"):
			self.assertIn(f'"key": "{key}"', source)

	def test_new_strings_are_translated(self):
		po = _read("locale", "ar.po")
		for msgid in (
			"Issue date",
			"Accountant signature",
			"Reviewer signature",
			"Supplier signature",
			"Includes draft cards",
			"Statement totals",
			"Period charges (incl. VAT)",
			"Owned equipment",
		):
			self.assertRegex(po, rf'msgid "{re.escape(msgid)}"\nmsgstr "[^"]+"')
