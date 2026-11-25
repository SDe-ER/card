# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""The PDF action of the Equipment Customer Statement (issue #324): the same server
route as the supplier statement. The server runs the report with the user's
permissions, builds the page itself (never from browser HTML) and renders it with
the Frappe Chrome PDF generator, which shapes Arabic. Chrome is not started in
tests: ``get_chrome_pdf`` is replaced and the HTML it receives is checked."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card.card.report.equipment_customer_statement import statement_pdf
from card.tests.test_controllers import _ensure_masters

CHROME = "frappe.utils.pdf.get_chrome_pdf"
METHOD = "card.card.report.equipment_customer_statement.statement_pdf.download_pdf"


class TestCustomerStatementPdf(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.response = frappe.local.response
		frappe.local.response = frappe._dict()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = self.response
		frappe.db.rollback()

	def _filters(self, **kw):
		f = {"company": self.company, "from_month": "09", "from_year": 2026}
		f.update(kw)
		return json.dumps(f)

	def _user(self, roles, restrict_to=None):
		email = f"cpdf-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Statement PDF",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def test_endpoint_is_post_only(self):
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[statement_pdf.download_pdf], ["POST"]
		)

	def test_pdf_uses_chrome_with_server_built_html(self):
		with patch(CHROME, return_value=b"%PDF-1.4 test") as chrome:
			statement_pdf.download_pdf(self._filters())
		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertEqual(frappe.local.response.filecontent, b"%PDF-1.4 test")
		args, kwargs = chrome.call_args
		self.assertIsNone(args[0])
		self.assertEqual(kwargs, {"pdf_generator": "chrome"})
		html = args[1]
		self.assertEqual(args[2]["margin-top"], "10mm")
		# the CSS is the browser template's own style block: one source for both paths
		self.assertIn(statement_pdf.template_style(), html)
		self.assertIn("size: A4 portrait", html)
		self.assertIn('<div class="ess-end">', html)
		self.assertNotIn("<script", html)
		# one Access Log row, as the standard report PDF writes
		self.assertTrue(
			frappe.db.exists("Access Log", {"report_name": statement_pdf.REPORT, "file_type": "PDF"})
		)

	def test_report_permission_is_required(self):
		frappe.set_user(self._user([]))
		with patch(CHROME) as chrome, self.assertRaises(frappe.PermissionError):
			statement_pdf.download_pdf(self._filters())
		chrome.assert_not_called()

	def test_company_outside_user_permission_is_refused(self):
		other = frappe.new_doc("Company")
		other.update(
			{
				"company_name": "TEST-CPDF-CO-" + self.token,
				"abbr": "C" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		other.name = other.company_name
		other.db_insert()
		frappe.set_user(self._user(["Card User"], restrict_to=other.name))
		with patch(CHROME) as chrome, self.assertRaises(frappe.PermissionError):
			statement_pdf.download_pdf(self._filters())
		chrome.assert_not_called()

	def test_link_filter_values_are_checked_like_the_report_run(self):
		with (
			patch(
				"frappe.desk.query_report.validate_filters_permissions", side_effect=frappe.PermissionError
			) as check,
			patch(CHROME) as chrome,
			self.assertRaises(frappe.PermissionError),
		):
			statement_pdf.download_pdf(self._filters())
		chrome.assert_not_called()
		js_filters = check.call_args.args[3]
		self.assertIn(
			{"fieldname": "customer", "fieldtype": "Link", "options": "Card Equipment Customer"}, js_filters
		)

	def test_non_scalar_filter_values_are_refused(self):
		with patch(CHROME) as chrome, self.assertRaises(frappe.ValidationError):
			statement_pdf.download_pdf(self._filters(customer={"name": "<img src=x>"}))
		chrome.assert_not_called()

	def test_empty_pdf_is_an_error(self):
		with patch(CHROME, return_value=None), self.assertRaises(frappe.ValidationError):
			statement_pdf.download_pdf(self._filters())

	def _columns(self, *fieldnames):
		return [{"fieldname": f, "label": f.upper()} for f in fieldnames]

	def _rows(self, **card):
		return [
			{"row_id": "P|x", "indent": 0, "label": "<b>P</b>", "net": 10},
			{"row_id": "E", "parent_row": "P|x", "indent": 1, "label": "EQ", "net": 10},
			{
				"row_id": "C",
				"parent_row": "E",
				"indent": 2,
				"label": "C-1",
				"card": "C-1",
				"shift": "نهاري",
				"customer_rate_type": "باليوم",
				"customer_rate": 5,
				"customer_amount": 10,
				"net": 10,
				**card,
			},
			{"row_id": "TOTAL", "indent": 0, "label": "T", "net": 10},
		]

	def test_build_html_escapes_text_and_hides_empty_columns(self):
		columns = self._columns(
			"label",
			"first_date",
			"hours",
			"customer_rate_type",
			"customer_rate",
			"customer_amount",
			"total_loads",
			"total_volume_m3",
			"additions",
			"deductions",
			"net",
		)
		summary = [
			{"key": "net_cards", "label": "n", "value": 10, "datatype": "Currency"},
			{"key": "not_invoiced", "label": "x", "value": 0, "datatype": "Currency"},
			{"key": "closing", "label": "ledger", "value": 99, "datatype": "Currency"},
		]
		html = statement_pdf.build_html(
			frappe._dict(
				{"company": "Co <i>", "customer": "<script>s</script>", "from_month": "02", "from_year": 2026}
			),
			columns,
			self._rows(),
			summary,
		)
		self.assertNotIn("<script>s", html)
		self.assertIn("&lt;script&gt;", html)
		self.assertNotIn("<b>P</b>", html)
		# additions/deductions and the per-m3 quantities are all zero: no column
		for label in ("ADDITIONS", "DEDUCTIONS", "TOTAL_LOADS", "TOTAL_VOLUME_M3"):
			self.assertNotIn(f">{label}<", html)
		self.assertIn(">CUSTOMER_RATE<", html)
		# only the cards net prints: not-invoiced is zero and ledger items stay on the screen report
		self.assertEqual(html.count('class="ess-k"'), 1)
		# the period is full dates: 1 Feb to 28 Feb 2026
		self.assertIn(frappe.utils.formatdate("2026-02-28"), html)
		self.assertIn('<td class="ess-c">1</td>', html)
		self.assertNotIn('<td class="ess-c">2</td>', html)
		self.assertIn(frappe._("Customer signature"), html)
		self.assertNotIn('class="ess-note"', html)

	def test_build_html_prints_loads_and_volume_of_a_per_m3_card(self):
		columns = self._columns(
			"label", "hours", "customer_rate", "customer_amount", "total_loads", "total_volume_m3", "net"
		)
		html = statement_pdf.build_html(
			frappe._dict({"company": "Co", "customer": "Cu", "from_month": "02", "from_year": 2026}),
			columns,
			self._rows(total_loads=4, total_volume_m3=72),
			[],
		)
		self.assertLess(html.index(">HOURS<"), html.index(">TOTAL_LOADS<"))
		self.assertLess(html.index(">TOTAL_LOADS<"), html.index(">TOTAL_VOLUME_M3<"))
		self.assertLess(html.index(">TOTAL_VOLUME_M3<"), html.index(">CUSTOMER_RATE<"))

	def test_build_html_follows_the_report_when_money_columns_are_withheld(self):
		# FR-178: the report sends no money column to a user who cannot read the card amounts
		html = statement_pdf.build_html(
			frappe._dict({"company": "Co", "customer": "Cu", "from_month": "02", "from_year": 2026}),
			self._columns("label", "first_date", "hours"),
			self._rows(),
			[],
		)
		self.assertNotIn('<td class="ess-num">5.00</td>', html)
		self.assertNotIn('<td class="ess-num">10.00</td>', html)

	def test_build_html_announces_drafts_and_a_missing_customer(self):
		rows = self._rows(label="C-1 " + frappe._("(Draft)"))
		html = statement_pdf.build_html(
			frappe._dict({"company": "Co", "from_month": "02", "from_year": 2026}),
			self._columns("label", "net"),
			rows,
			[],
		)
		self.assertIn(frappe.utils.escape_html(frappe._("Includes draft cards")), html)
		self.assertIn(frappe.utils.escape_html(frappe._("Select a customer to display the statement.")), html)

	def test_report_js_routes_only_this_report_to_the_server_pdf(self):
		with open(
			frappe.get_app_path(
				"card", "card", "report", "equipment_customer_statement", "equipment_customer_statement.js"
			),
			encoding="utf-8",
		) as f:
			js = f.read()
		self.assertIn(METHOD, js)
		self.assertIn('this.report_name !== "Equipment Customer Statement"', js)
		self.assertIn("return standard_pdf.call(this, print_settings);", js)
		self.assertNotIn("outerHTML", js)
