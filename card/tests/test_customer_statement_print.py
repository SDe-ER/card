# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""The A4 print of the Equipment Customer Statement (FR-149): the customer mirror
of "Equipment Supplier Statement A4", one layout for both print paths (the
report's html template and the standard Report Print Format the PDF dialog
pre-selects)."""

import re

import frappe
from frappe.tests import IntegrationTestCase

REPORT = "Equipment Customer Statement"
PRINT_FORMAT = "Equipment Customer Statement A4"
REPORT_DIR = ("card", "report", "equipment_customer_statement")
SUPPLIER_TEMPLATE = ("card", "report", "equipment_supplier_statement", "equipment_supplier_statement.html")


def _read(*parts):
	with open(frappe.get_app_path("card", *parts), encoding="utf-8") as f:
		return f.read().replace("\r\n", "\n")


def _template():
	return _read(*REPORT_DIR, "equipment_customer_statement.html")


def _style(template):
	return re.search(r"<style>.*?</style>", template, flags=re.S).group(0)


class TestCustomerStatementPrint(IntegrationTestCase):
	def test_print_format_is_a_standard_report_format(self):
		pf = frappe.get_doc("Print Format", PRINT_FORMAT)
		self.assertEqual(
			(pf.print_format_for, pf.report, pf.print_format_type, pf.standard, pf.disabled, pf.module),
			("Report", REPORT, "JS", "Yes", 0, "Card"),
		)

	def test_both_print_paths_use_the_same_layout(self):
		template = _template()
		self.assertEqual(
			frappe.db.get_value("Print Format", PRINT_FORMAT, "html").replace("\r\n", "\n"), template
		)
		shipped = _read(
			"card", "print_format", "equipment_customer_statement_a4", "equipment_customer_statement_a4.json"
		)
		self.assertEqual(frappe.parse_json(shipped)["html"], template)

		from frappe.desk.query_report import get_print_format_data

		self.assertEqual(get_print_format_data(PRINT_FORMAT)["html"].replace("\r\n", "\n"), template)

	def test_report_preselects_the_format(self):
		js = _read(*REPORT_DIR, "equipment_customer_statement.js")
		self.assertIn(f'report.report_doc.default_print_format = "{PRINT_FORMAT}"', js)

	def test_same_print_style_as_the_supplier_statement(self):
		# the approved SDCE print design (2026-11-09): the style block is the supplier one, unchanged
		self.assertEqual(_style(_template()), _style(_read(*SUPPLIER_TEMPLATE)))
		self.assertIn("@page { size: A4 portrait; margin: 10mm; }", _template())
		self.assertIn('dir="{%= frappe.utils.is_rtl() ? "rtl" : "ltr" %}"', _template())

	def test_template_escapes_text_and_has_no_line_comments_in_code(self):
		template = _template()
		# the microtemplate compiler joins lines, so a // comment would swallow the rest of the code block
		for block in re.findall(r"{%(?!=)(.*?)%}", template, flags=re.S):
			self.assertNotRegex(block, r"(?<![:\"])//")
		for field in ("filters.company", "filters.customer", "item.label"):
			self.assertIn(f"esc({field}", template)

	def test_columns_and_optional_columns(self):
		template = _template()
		columns = re.findall(r'\["(\w+)", ([\d.]+), "\w+"\]', template.split("var rows = []")[0])
		self.assertTrue(columns)
		self.assertEqual(
			[c[0] for c in columns],
			[
				"label",
				"first_date",
				"last_date",
				"working_days",
				"hours",
				"customer_rate_type",
				"customer_rate",
				"customer_amount",
				"additions",
				"deductions",
				"net",
			],
		)
		# the widths fill the A4 width with the "#" column (3%)
		self.assertAlmostEqual(sum(float(c[1]) for c in columns) + 3, 100)
		self.assertIn("var optional = { additions: 1, deductions: 1 };", template)
		self.assertIn('if (has_value("stopped_hours"))', template)
		self.assertIn('var totals_from = "customer_rate";', template)
		# owner 2026-11-10: the contract rate (rate type + customer rate), never the effective hourly rate
		self.assertNotIn('"hourly_rate"', template)
		self.assertIn('if (f[2] === "type") return v ? esc(__(String(v))) : "";', template)
		# every column label comes from the report's own columns (already in the user's language)
		source = _read(*REPORT_DIR, "equipment_customer_statement.py")
		for fieldname, _width in columns:
			self.assertIn(f'"fieldname": "{fieldname}"', source)

	def test_printed_totals_are_picked_by_key_only(self):
		template = _template()
		self.assertIn('var print_keys = ["net_cards", "not_invoiced"];', template)
		self.assertIn("if (summary[s] && summary[s].key) summary_of[summary[s].key] = summary[s];", template)
		# no positional fallback and no fallback to the raw summary: the reconciliation item ("outside") and
		# the ledger items never print
		self.assertNotIn("key_order", template)
		self.assertNotIn("totals = summary", template)
		self.assertNotIn('"outside"', template)
		self.assertNotIn("raw.message", template)
		# a print without a customer says why it is empty (a fixed string, never the server message)
		self.assertIn(
			'{% if (!filters.customer) { %}<p class="ess-note"><b>{%= __("Select a customer to display the statement.") %}',
			template,
		)
		self.assertIn("if (original_data[i]) rows.push(original_data[i]);", template)

	def test_no_system_name_on_the_statement(self):
		# owner rule: the printed account statement never names a system (ERPNext, Frappe)
		template = _template()
		# the static markup (code blocks and the style removed) and every printed string, in English and Arabic
		markup = re.sub(r"{%.*?%}", "", template.split("</style>")[1], flags=re.S)
		self.assertNotRegex(markup, r"(?i)erpnext|frappe")
		po = _read("locale", "ar.po")
		for text in re.findall(r'__\("((?:[^"\\]|\\.)*)"', template):
			self.assertNotRegex(text, r"(?i)erpnext|frappe")
			match = re.search(rf'msgid "{re.escape(text)}"\nmsgstr "([^"]*)"', po)
			if match:
				self.assertNotRegex(match.group(1), r"(?i)erpnext|frappe")

	def test_draft_note_follows_the_rows(self):
		# the server includes drafts also by the Card Settings default (filter unset): the note follows the rows
		template = _template()
		self.assertIn("var has_draft = !!filters.include_draft;", template)
		self.assertIn('String(rows[r].label || "").indexOf(__("(Draft)")) !== -1', template)
		self.assertIn('{% if (has_draft) { %}<p class="ess-note"><b>{%= __("Includes draft cards")', template)
		self.assertIn('" " + _("(Draft)")', _read(*REPORT_DIR, "equipment_customer_statement.py"))

	def test_signatures_and_footer(self):
		template = _template()
		for sign in ("Accountant signature", "Reviewer signature", "Customer signature"):
			self.assertIn(f'__("{sign}")', template)
		self.assertNotIn("Supplier", template)
		self.assertIn('esc(__("Issued by the electronic system of {0}", [filters.company || ""]))', template)
		self.assertLess(template.index('class="ess-rows"'), template.index('class="ess-totals"'))
		self.assertLess(template.index('class="ess-totals"'), template.index('class="ess-signs"'))

	def test_every_printed_string_is_translated(self):
		po = _read("locale", "ar.po")
		texts = set(re.findall(r'__\("((?:[^"\\]|\\.)*)"', _template()))
		self.assertIn("Equipment Customer Statement", texts)
		self.assertIn("Customer signature", texts)
		for text in texts:
			self.assertRegex(po, rf'msgid "{re.escape(text)}"\nmsgstr "[^"]+"')
