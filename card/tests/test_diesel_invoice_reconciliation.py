# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-1: the read-only Diesel Invoice Reconciliation report matches CARD diesel sessions with the
suppliers' own Purchase Invoices (litres from the line text, delivery charges apart, VAT basis per
invoice) and changes nothing."""

import frappe
from frappe.utils import flt

from card.card.report.diesel_invoice_reconciliation.diesel_invoice_reconciliation import execute
from card.diesel_reconciliation import diesel_supplier_options, line_kind, line_litres
from card.gl.masters import ensure_posting_masters
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_s3_posting import _PostingBase

PRICE = 1.79


class TestDieselInvoiceReconciliation(_PostingBase):
	def _fill(self, day, litres, submit=True, price=PRICE):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": f"2026-09-{day:02d}",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": litres,
				"unit_price": price,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		if submit:
			approve_fill(fill)
			fill.submit()
		return fill

	def _invoice(self, day, lines, vat=None, gross=None):
		"""A supplier's own invoice as entered in Desk: free-text lines (litres in the text), VAT as one
		Actual row. `lines` = [(text, amount, project)]; vat = 15 % of net unless given."""
		row = ensure_posting_masters(self.company)
		net = flt(sum(a for _t, a, _p in lines), 2)
		inv = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": self.supplier,
				"set_posting_time": 1,
				"posting_date": f"2026-09-{day:02d}",
				"due_date": f"2026-09-{day:02d}",
				"bill_no": f"P11-{self.token}-{frappe.generate_hash(length=6)}",
				"bill_date": f"2026-09-{day:02d}",
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"items": [
					{
						"item_code": row.diesel_item,
						"item_name": text,
						"description": text,
						"qty": 1,
						"rate": amount,
						"expense_account": self.exp_diesel,
						"project": project,
					}
					for text, amount, project in lines
				],
				"taxes": [
					{
						"charge_type": "Actual",
						"account_head": self.vat_in,
						"description": "VAT 15%",
						"tax_amount": flt(net * 0.15, 2) if vat is None else vat,
						"category": "Total",
						"add_deduct_tax": "Add",
					}
				],
			}
		).insert(ignore_permissions=True)
		inv.submit()
		return inv

	def _gross_lines(self, litres_text, litres, project="self", price=PRICE):
		"""One diesel line whose gross (net + 15 %) is `litres` x `price`, as the suppliers invoice."""
		net = flt(litres * price / 1.15, 2)
		return [(litres_text, net, self.project if project == "self" else project)]

	def _run(self, **filters):
		cols, rows, _m, _c, summary = execute(
			{
				"company": self.company,
				"suppliers": [self.supplier],
				"from_date": "2026-09-01",
				"to_date": "2026-09-30",
				**filters,
			}
		)
		return rows, summary

	def _row(self, rows, invoice=None, session=None):
		for r in rows:
			if invoice and r.get("invoice") == invoice:
				return r
			if session and r.get("sessions") == session:
				return r
		self.fail(f"no row for {invoice or session}: {rows}")

	# ---- parsing
	def test_litres_are_read_from_the_line_text(self):
		self.assertEqual(line_litres("ديزل 2380 لتر - 0006-753"), 2380)
		self.assertEqual(line_litres("ديزل ٣٢٧٦ لتر"), 3276)
		self.assertEqual(line_litres("Diesel 1,500.5 L"), 1500.5)
		self.assertIsNone(line_litres("ديزل - فاتورة 1322 - PROJ-0010"))
		self.assertEqual(line_kind("أجرة نقل 60 لتر - 0006-511"), "delivery")
		self.assertEqual(line_kind("بنزين 91 - 43.58 لتر"), "other fuel")
		self.assertEqual(line_kind("ديزل 3800 لتر"), "diesel")

	# ---- positive
	def test_delivery_invoice_with_equal_litres_matches_and_is_vat_inclusive(self):
		fill = self._fill(10, 1000)
		inv = self._invoice(10, self._gross_lines("ديزل 1000 لتر", 1000))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["sessions"], fill.name)
		self.assertEqual(row["status"], "Matched")
		self.assertEqual(row["litre_difference"], 0)
		self.assertEqual(row["vat_pct"], 15)
		self.assertEqual(row["vat_basis"], "VAT-inclusive price")
		self.assertFalse(row["exception"])

	def test_delivery_charge_inside_the_diesel_line_is_separated(self):
		fill = self._fill(11, 1000)
		inv = self._invoice(11, self._gross_lines("ديزل 1060 لتر", 1060))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["sessions"], fill.name)
		self.assertIn("delivery charge", row["status"])
		self.assertEqual(row["litre_difference"], 60)
		self.assertIn("Physical diesel = session litres", row["note"])
		self.assertFalse(row["exception"])

	def test_separate_delivery_charge_line(self):
		self._fill(12, 1000)
		diesel = flt(1000 * PRICE / 1.15, 2)
		fee = flt(60 * PRICE / 1.15, 2)
		inv = self._invoice(
			12, [("ديزل 1000 لتر", diesel, self.project), ("أجرة نقل 60 لتر", fee, self.project)]
		)
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["status"], "Matched")
		self.assertEqual((row["invoice_litres"], row["delivery_litres"]), (1000, 60))
		self.assertEqual(row["vat_basis"], "VAT-inclusive price")
		self.assertIn("Separate delivery charge line", row["note"])

	def test_vat_exclusive_price_is_detected_from_the_invoice(self):
		self._fill(13, 1000)
		inv = self._invoice(13, [("ديزل 1000 لتر", 1790, self.project)])  # net = litres x price
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["vat_basis"], "VAT-exclusive price")

	def test_aggregated_invoice_is_reconciled_by_period(self):
		for day, litres in ((1, 1000), (2, 1200), (3, 800)):
			self._fill(day, litres)
		inv = self._invoice(5, self._gross_lines("ديزل - فاتورة مجمعة", 5000))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["status"], "Period: invoiced more than sessions")
		self.assertEqual(row["session_litres"], 3000)
		self.assertAlmostEqual(row["invoice_litres"], 5000, delta=1)
		self.assertTrue(row["vat_basis"].startswith("Unverified"))
		self.assertIn("estimated", row["note"])
		self.assertTrue(row["exception"])

	def test_aggregated_invoice_that_agrees_with_its_sessions(self):
		for day, litres in ((1, 1000), (2, 1200), (3, 800)):
			self._fill(day, litres)
		inv = self._invoice(5, self._gross_lines("ديزل 3000 لتر - فاتورة مجمعة", 3000))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["status"], "Period: litres agree")
		self.assertFalse(row["exception"])

	# ---- negative
	def test_session_and_invoice_without_counterpart_are_exceptions(self):
		fill = self._fill(10, 1000)
		inv = self._invoice(20, self._gross_lines("ديزل 777 لتر", 777))
		rows, summary = self._run()
		self.assertEqual(self._row(rows, session=fill.name)["status"], "Session without invoice")
		self.assertEqual(self._row(rows, invoice=inv.name)["status"], "Invoice without session")
		self.assertEqual(next(t for t in summary if t["label"] == "Exceptions")["value"], 2)

	def test_session_after_the_last_invoice_is_not_invoiced_yet(self):
		self._fill(10, 1000)
		self._invoice(10, self._gross_lines("ديزل 1000 لتر", 1000))
		late = self._fill(25, 900)
		row = self._row(self._run()[0], session=late.name)
		self.assertEqual(row["status"], "Not invoiced yet")
		self.assertFalse(row["exception"])

	def test_invoice_line_without_project_is_flagged(self):
		self._fill(14, 1000)
		inv = self._invoice(14, self._gross_lines("ديزل 1000 لتر", 1000, project=None))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertIn("without project", row["note"])
		self.assertEqual(row["invoice_projects"], "none")

	def test_draft_session_is_listed_with_its_review_state(self):
		draft = self._fill(15, 500, submit=False)
		self._invoice(28, self._gross_lines("ديزل 9 لتر", 9))
		row = self._row(self._run()[0], session=draft.name)
		self.assertIn("Draft session", row["note"])

	# ---- read-only and access
	def test_report_changes_no_document(self):
		fill = self._fill(10, 1000)
		inv = self._invoice(10, self._gross_lines("ديزل 1000 لتر", 1000))
		before = (
			frappe.db.get_value(
				"Project Diesel Fill", fill.name, ["modified", "purchase_invoice", "docstatus"]
			),
			frappe.db.get_value("Purchase Invoice", inv.name, ["modified", "docstatus", "grand_total"]),
			frappe.db.count("GL Posting Log"),
			frappe.db.count("Journal Entry"),
		)
		self._run()
		after = (
			frappe.db.get_value(
				"Project Diesel Fill", fill.name, ["modified", "purchase_invoice", "docstatus"]
			),
			frappe.db.get_value("Purchase Invoice", inv.name, ["modified", "docstatus", "grand_total"]),
			frappe.db.count("GL Posting Log"),
			frappe.db.count("Journal Entry"),
		)
		self.assertEqual(before, after)

	def _user(self, roles):
		email = f"p11-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "P11", "send_welcome_email": 0}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		return email

	def test_user_without_purchase_invoice_read_is_refused(self):
		frappe.set_user(self._user(["Card User"]))
		with self.assertRaises(frappe.PermissionError):
			self._run()

	def test_another_company_is_refused(self):
		user = self._user(["Accounts Manager"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Company", "for_value": self.company}
		).insert(ignore_permissions=True)
		other = frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name")
		if not other:
			self.skipTest("the site has one company only")
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			execute({"company": other, "from_date": "2026-09-01", "to_date": "2026-09-30"})

	def test_supplier_options_list_diesel_suppliers_of_the_company(self):
		self._fill(10, 100, submit=False)
		values = [o["value"] for o in diesel_supplier_options(txt="", company=self.company)]
		self.assertIn(self.supplier, values)

	def test_vat_basis_uses_the_price_of_the_invoices_own_sessions(self):
		self._fill(5, 1000, price=1.66)
		early = self._invoice(5, self._gross_lines("ديزل 1000 لتر", 1000, price=1.66))
		self._fill(20, 1000)
		late = self._invoice(20, self._gross_lines("ديزل 1000 لتر", 1000))
		rows = self._run()[0]
		self.assertEqual(self._row(rows, invoice=early.name)["vat_basis"], "VAT-inclusive price")
		self.assertEqual(self._row(rows, invoice=late.name)["vat_basis"], "VAT-inclusive price")

	def test_supplier_options_need_a_report_role_and_diesel_session_read(self):
		frappe.set_user(self._user(["Accounts User"]))  # reads Purchase Invoice, not diesel sessions
		with self.assertRaises(frappe.PermissionError):
			self._run()
		with self.assertRaises(frappe.PermissionError):
			diesel_supplier_options(txt="", company=self.company)
