# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""The PDF action of the Equipment Supplier Statement: the server runs the report
with the user's permissions, builds the page itself (never from browser HTML) and
renders it with the Frappe Chrome PDF generator. Chrome is not started in tests:
``get_chrome_pdf`` is replaced and the HTML it receives is checked."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card.card.report.equipment_supplier_statement import statement_pdf
from card.tests.test_controllers import _days, _ensure_masters

RENTED = "إيجار"
CHROME = "frappe.utils.pdf.get_chrome_pdf"


class TestSupplierStatementPdf(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-SPDF-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-SPDF-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		self.response = frappe.local.response
		frappe.local.response = frappe._dict()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = self.response
		frappe.db.rollback()

	def _card(self, suffix, hours, shift):
		eq = frappe.new_doc("Card Equipment")
		eq.company = self.company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-SPDF-EQ-" + self.token + suffix
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.ownership = RENTED
		eq.supplier = self.supplier
		eq.insert(ignore_permissions=True)
		card = frappe.new_doc("Card Monthly Card")
		card.equipment = eq.name
		card.project = self.project
		card.shift = shift
		card.month = "09"
		card.year = 2026
		for row in _days(hours):
			card.append("days", row)
		card.insert(ignore_permissions=True)
		card.submit()
		return card

	def _filters(self, **kw):
		f = {
			"company": self.company,
			"statement_type": "مورد",
			"supplier": self.supplier,
			"from_month": "09",
			"from_year": 2026,
			"project": self.project,
		}
		f.update(kw)
		return json.dumps(f)

	def _user(self, roles, restrict_to=None):
		email = f"spdf-{frappe.generate_hash(length=6)}@example.com"
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
		day = self._card("A", [8, 8], "نهاري")
		night = self._card("B", [6], "ليلي")
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
		# every card is listed and numbered, with its shift
		for card in (day, night):
			self.assertIn(card.name + " — ", html)
		self.assertIn('<td class="ess-c">1</td>', html)
		self.assertIn('<td class="ess-c">2</td>', html)
		self.assertIn('<div class="ess-end">', html)
		self.assertNotIn("<script", html)

	def test_report_permission_is_required(self):
		self._card("A", [8], "نهاري")
		frappe.set_user(self._user([]))
		with patch(CHROME) as chrome, self.assertRaises(frappe.PermissionError):
			statement_pdf.download_pdf(self._filters())
		chrome.assert_not_called()

	def test_company_outside_user_permission_is_refused(self):
		self._card("A", [8], "نهاري")
		other = frappe.new_doc("Company")
		other.update(
			{
				"company_name": "TEST-SPDF-CO-" + self.token,
				"abbr": "S" + self.token[:6].upper(),
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

	def test_build_html_escapes_text_and_hides_empty_columns(self):
		columns = [
			{"fieldname": f, "label": f.upper()}
			for f in ("label", "first_date", "hours", "additions", "deductions", "net")
		]
		rows = [
			{"row_id": "P|x", "indent": 0, "label": "<b>P</b>", "net": 10},
			{"row_id": "E", "parent_row": "P|x", "indent": 1, "label": "EQ", "net": 10},
			{
				"row_id": "C",
				"parent_row": "E",
				"indent": 2,
				"label": "C-1",
				"card": "C-1",
				"shift": "نهاري",
				"net": 10,
			},
			{"row_id": "TOTAL", "indent": 0, "label": "T", "net": 10},
		]
		summary = [
			{"key": "net_cards", "label": "n", "value": 10, "datatype": "Currency"},
			{"key": "not_invoiced", "label": "x", "value": 0, "datatype": "Currency"},
		]
		html = statement_pdf.build_html(
			frappe._dict(
				{"company": "Co <i>", "supplier": "<script>s</script>", "from_month": "02", "from_year": 2026}
			),
			columns,
			rows,
			None,
			summary,
		)
		self.assertNotIn("<script>s", html)
		self.assertIn("&lt;script&gt;", html)
		self.assertNotIn("<b>P</b>", html)
		# additions/deductions are all zero: no column
		self.assertNotIn(">ADDITIONS<", html)
		self.assertNotIn(">DEDUCTIONS<", html)
		# the not-invoiced line prints only when positive
		self.assertEqual(html.count('class="ess-k"'), 1)
		# the period is full dates: 1 Feb to 28 Feb 2026
		self.assertIn(frappe.utils.formatdate("2026-02-28"), html)
		self.assertIn('<td class="ess-c">1</td>', html)
		self.assertNotIn('<td class="ess-c">2</td>', html)

	def test_report_js_routes_only_this_report_to_the_server_pdf(self):
		with open(
			frappe.get_app_path(
				"card", "card", "report", "equipment_supplier_statement", "equipment_supplier_statement.js"
			),
			encoding="utf-8",
		) as f:
			js = f.read()
		self.assertIn("card.card.report.equipment_supplier_statement.statement_pdf.download_pdf", js)
		self.assertIn('this.report_name !== "Equipment Supplier Statement"', js)
		self.assertIn("return standard_pdf.call(this, print_settings);", js)
		self.assertNotIn("outerHTML", js)
