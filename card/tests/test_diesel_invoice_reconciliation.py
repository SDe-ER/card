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

	def _invoice(self, day, lines, vat=None, gross=None, month=9, item_name=None):
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
				"posting_date": f"2026-{month:02d}-{day:02d}",
				"due_date": f"2026-{month:02d}-{day:02d}",
				"bill_no": f"P11-{self.token}-{frappe.generate_hash(length=6)}",
				"bill_date": f"2026-{month:02d}-{day:02d}",
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"items": [
					{
						"item_code": row.diesel_item,
						"item_name": item_name or text,
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
		_cols, rows, _m, _c, summary = execute(
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
		self.assertEqual(line_litres("ديزل ١٬٠٠٠ لتر"), 1000)
		self.assertEqual(line_litres("ديزل ٢٥٫٥ لتر"), 25.5)
		self.assertEqual(line_kind("ديزل 1000 لتر شامل التوصيل"), "diesel")
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
		self.assertEqual(row["confidence"], "Confirmed: stated litres equal the session")
		self.assertEqual(row["session_state"], "Submitted 1, draft 0")
		self.assertEqual(row["allocation"], "Consistent")
		self.assertIn("VAT as booked", row["note"])
		self.assertFalse(row["exception"])

	def test_delivery_charge_inside_the_diesel_line_is_separated(self):
		fill = self._fill(11, 1000)
		inv = self._invoice(11, self._gross_lines("ديزل 1060 لتر", 1060))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["sessions"], fill.name)
		self.assertIn("delivery charge", row["status"])
		self.assertEqual(row["litre_difference"], 60)
		# physical diesel and the delivery-fee equivalent are reported apart
		self.assertEqual((row["physical_litres"], row["delivery_litres"]), (1000, 60))
		self.assertEqual(row["confidence"], "Confirmed: stated litres = session + delivery charge")
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
		# an unexplained difference is a point to review, never confirmed over-billing
		self.assertEqual(row["status"], "Period: difference to review (invoice above sessions)")
		self.assertIn("not a confirmed over-billing", row["note"])
		self.assertEqual(row["confidence"], "Estimated: period match, litres estimated from the amount")
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
		# any company outside the user's permitted set is refused (another real one where the site has it)
		other = (
			frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name") or "TEST-P11-NOT-PERMITTED"
		)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			execute({"company": other, "from_date": "2026-09-01", "to_date": "2026-09-30"})
		with self.assertRaises(frappe.PermissionError):
			execute({"company": "TEST-P11-NOT-PERMITTED", "from_date": "2026-09-01", "to_date": "2026-09-30"})

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

	def test_submitted_and_draft_sessions_are_separated(self):
		self._fill(10, 1000)
		draft = self._fill(12, 400, submit=False)
		self._invoice(28, self._gross_lines("ديزل 1000 لتر", 1000))
		rows, summary = self._run()
		tiles = {t["label"]: t["value"] for t in summary}
		self.assertEqual((tiles["Submitted session litres"], tiles["Draft session litres"]), (1000, 400))
		self.assertEqual(self._row(rows, session=draft.name)["session_state"], "Submitted 0, draft 1")
		rows, summary = self._run(session_status="Submitted only")
		self.assertFalse([r for r in rows if r.get("sessions") == draft.name])
		self.assertEqual({t["label"]: t["value"] for t in summary}["Draft session litres"], 0)

	def test_amount_only_match_is_estimated(self):
		self._fill(16, 1000)
		inv = self._invoice(16, self._gross_lines("ديزل - فاتورة", 1000))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["confidence"], "Estimated: amount only, the invoice states no litres")

	def test_project_conflict_is_reported_not_changed(self):
		other = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-P11-OTHER-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		self._fill(17, 1000)
		inv = self._invoice(17, self._gross_lines("ديزل 1000 لتر", 1000, project=other.name))
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["allocation"], "Project conflict")
		self.assertEqual(
			frappe.db.get_value("Purchase Invoice Item", {"parent": inv.name}, "project"), other.name
		)

	# ---- independent review findings (PR #153)
	def test_litres_in_the_description_of_an_item_line(self):
		self._fill(18, 1000)
		inv = self._invoice(18, self._gross_lines("ديزل 1000 لتر - 0006-1", 1000), item_name="Diesel")
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual(row["status"], "Matched")
		self.assertEqual(row["invoice_litres"], 1000)

	def test_line_naming_diesel_and_delivery_is_diesel(self):
		self._fill(19, 1000)
		inv = self._invoice(19, self._gross_lines("ديزل 1000 لتر شامل التوصيل", 1000))
		self.assertEqual(self._row(self._run()[0], invoice=inv.name)["status"], "Matched")

	def test_the_same_day_invoice_wins_over_the_day_before(self):
		fill = self._fill(10, 1000)
		before = self._invoice(9, self._gross_lines("ديزل 1000 لتر", 1000))
		same = self._invoice(10, self._gross_lines("ديزل 1000 لتر", 1000))
		rows = self._run()[0]
		self.assertEqual(self._row(rows, invoice=same.name)["sessions"], fill.name)
		self.assertEqual(self._row(rows, invoice=before.name)["status"], "Invoice without session")

	def test_amount_only_match_on_a_vat_exclusive_price(self):
		self._fill(21, 1000)
		inv = self._invoice(21, [("ديزل - فاتورة", 1790, self.project)])  # net = litres x price
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertIn("net / session price", row["status"])
		self.assertEqual(row["confidence"], "Estimated: amount only, the invoice states no litres")

	def test_session_linked_to_its_invoice_is_confirmed_by_the_link(self):
		fill = self._fill(22, 1000)
		inv = self._invoice(22, self._gross_lines("ديزل 999 لتر", 999))
		frappe.db.set_value("Project Diesel Fill", fill.name, "purchase_invoice", inv.name)
		row = self._row(self._run()[0], invoice=inv.name)
		self.assertEqual((row["sessions"], row["confidence"]), (fill.name, "Confirmed: linked in CARD"))

	def test_invoice_after_the_period_end_is_not_an_exception(self):
		self._fill(29, 1000)
		self._invoice(29, self._gross_lines("ديزل 1000 لتر", 1000))
		late = self._invoice(2, self._gross_lines("ديزل 700 لتر", 700), month=10)
		row = self._row(self._run()[0], invoice=late.name)
		self.assertEqual(row["status"], "After the period end: to review with the next period")
		self.assertFalse(row["exception"])

	def test_user_permission_on_supplier_hides_other_suppliers(self):
		self._fill(23, 1000)
		self._invoice(23, self._gross_lines("ديزل 1000 لتر", 1000))
		user = self._user(["Accounts Manager"])
		other = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "TEST-P11-OTHER-" + self.token,
				"supplier_group": self._m["supplier_group"],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Supplier", "for_value": other.name}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		rows = self._run()[0]
		self.assertFalse(rows)
