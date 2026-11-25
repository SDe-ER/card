# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Project Invoice Profitability (FR-193, #53). Read-only: revenue and expenses of each project from
submitted Sales Invoice and Purchase Invoice lines. The totals reconcile to the invoices, returns
reduce their side, lines without a project sit on one "No project" row, the date window, company
isolation, role access and nothing written. All data is synthetic and rolled back."""

from unittest.mock import patch

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.utils import flt

from card.card.report.project_invoice_profitability.project_invoice_profitability import (
	execute as profitability,
)
from card.gl.masters import ensure_posting_masters
from card.tests.test_analytics_reports import PERIOD, _AnalyticsBase


class TestProjectProfitability(_AnalyticsBase):
	def _second_project(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-PROFIT-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _pi(self, rate, project=None, header_project=None, posting_date="2026-10-05"):
		inv = self._manual_pi(rate, posting_date=posting_date, submit=False)
		inv.project = header_project
		inv.items[0].project = project
		inv.save()
		inv.submit()
		return inv

	def _si(self, rate, project=None, header_project=None, posting_date="2026-10-05"):
		row = ensure_posting_masters(self.company)
		inv = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": self.company,
				"customer": self.customer,
				"set_posting_time": 1,
				"posting_date": posting_date,
				"due_date": posting_date,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"project": header_project,
				"items": [
					{
						"item_code": row.rental_item,
						"qty": 1,
						"rate": rate,
						"income_account": self.inc_rental,
						"cost_center": self._row()[1].cost_center,
						"project": project,
					}
				],
			}
		).insert(ignore_permissions=True)
		inv.submit()
		return inv

	def _return(self, invoice):
		ret = make_return_doc(invoice.doctype, invoice.name)
		ret.set_posting_time = 1
		ret.posting_date = ret.due_date = invoice.posting_date
		if invoice.doctype == "Purchase Invoice":
			ret.bill_no = "TEST-PROFIT-RET-" + frappe.generate_hash(length=6)
		ret.insert(ignore_permissions=True)
		ret.submit()
		return ret

	def _run(self, **kw):
		columns, data, message, _chart, summary = profitability(self._period(**kw))
		rows = {r["project"]: r for r in data if not r.get("is_total")}
		total = next(r for r in data if r.get("is_total"))
		return rows, total, message, {s["label"]: s["value"] for s in summary}, columns

	def _invoice_net(self, doctype):
		"""The net total of the submitted invoices of the period, straight from the invoice headers."""
		return flt(
			sum(
				flt(r.base_net_total)
				for r in frappe.get_all(
					doctype,
					filters={
						"company": self.company,
						"docstatus": 1,
						"posting_date": ["between", [PERIOD["from_date"], PERIOD["to_date"]]],
					},
					fields=["base_net_total"],
				)
			),
			2,
		)

	def test_columns_and_margin_per_project(self):
		self._si(1000, project=self.project)
		self._pi(400, project=self.project)
		rows, _total, message, _summary, columns = self._run()
		self.assertEqual(
			[c["fieldname"] for c in columns],
			["project", "project_name", "revenue", "expenses", "margin", "margin_percent"],
		)
		row = rows[self.project]
		self.assertEqual(row["project_name"], frappe.db.get_value("Project", self.project, "project_name"))
		self.assertEqual(row["revenue"], 1000.0)
		self.assertEqual(row["expenses"], 400.0)
		self.assertEqual(row["margin"], 600.0)
		self.assertEqual(row["margin_percent"], 60.0)
		self.assertIn("not the full net profit", message)
		self.assertIn("Journal entries and the general ledger are not read", message)

	def test_totals_reconcile_to_the_invoices(self):
		other = self._second_project()
		self._si(1000, project=self.project)
		self._si(250.55, project=other)
		self._si(80)  # no project anywhere
		self._pi(400, project=self.project)
		self._pi(120.45, project=other)
		self._pi(30)  # no project anywhere
		rows, total, _message, summary, _columns = self._run()
		self.assertEqual(rows[other]["revenue"], 250.55)
		self.assertEqual(rows[other]["expenses"], 120.45)
		self.assertEqual(total["revenue"], self._invoice_net("Sales Invoice"))
		self.assertEqual(total["expenses"], self._invoice_net("Purchase Invoice"))
		self.assertEqual(total["revenue"], flt(sum(r["revenue"] for r in rows.values()), 2))
		self.assertEqual(total["expenses"], flt(sum(r["expenses"] for r in rows.values()), 2))
		self.assertEqual(total["margin"], flt(total["revenue"] - total["expenses"], 2))
		self.assertEqual(summary["Project margin"], total["margin"])

	def test_lines_without_a_project_sit_on_one_row(self):
		before = self._run()[0].get(None) or {"revenue": 0, "expenses": 0}
		self._si(80)
		self._si(20)
		self._pi(30)
		rows, _total, _message, _summary, _columns = self._run()
		row = rows[None]
		self.assertEqual(row["project_name"], "No project")
		self.assertEqual(flt(row["revenue"] - before["revenue"], 2), 100.0)
		self.assertEqual(flt(row["expenses"] - before["expenses"], 2), 30.0)
		# the project filter leaves the lines without a project out
		rows, total, _message, _summary, _columns = self._run(project=self.project)
		self.assertNotIn(None, rows)
		self.assertEqual(total["revenue"], 0)

	def test_line_without_a_project_takes_the_project_of_its_invoice(self):
		self._si(500, header_project=self.project)
		self._pi(200, header_project=self.project)
		rows, _total, _message, _summary, _columns = self._run()
		self.assertEqual(rows[self.project]["revenue"], 500.0)
		self.assertEqual(rows[self.project]["expenses"], 200.0)

	def test_returns_reduce_their_side(self):
		sale = self._si(1000, project=self.project)
		purchase = self._pi(400, project=self.project)
		self._return(sale)
		rows, _total, _message, _summary, _columns = self._run()
		self.assertEqual(rows[self.project]["revenue"], 0)
		self.assertEqual(rows[self.project]["expenses"], 400.0)
		self._return(purchase)
		rows, total, _message, _summary, _columns = self._run()
		self.assertEqual(rows[self.project]["expenses"], 0)
		self.assertEqual(rows[self.project]["margin"], 0)
		self.assertIsNone(rows[self.project]["margin_percent"])  # no revenue: no percentage
		self.assertEqual(total["revenue"], self._invoice_net("Sales Invoice"))

	def test_draft_and_cancelled_invoices_are_not_read(self):
		draft = self._manual_pi(70, posting_date="2026-10-05", submit=False)
		draft.items[0].project = self.project
		draft.save()
		sale = self._si(90, project=self.project)
		sale.cancel()
		rows, total, _message, _summary, _columns = self._run(project=self.project)
		self.assertFalse(rows)
		self.assertEqual(total["revenue"], 0)
		self.assertEqual(total["expenses"], 0)

	def test_date_window(self):
		self._si(1000, project=self.project, posting_date="2026-10-05")
		self._si(111, project=self.project, posting_date="2026-11-05")
		self._pi(400, project=self.project, posting_date="2026-10-31")
		self._pi(222, project=self.project, posting_date="2026-11-01")
		_columns, data, _message, _chart, _summary = profitability(
			{"company": self.company, "from_date": "2026-10-01", "to_date": "2026-10-31"}
		)
		row = next(r for r in data if r["project"] == self.project)
		self.assertEqual(row["revenue"], 1000.0)
		self.assertEqual(row["expenses"], 400.0)
		with self.assertRaises(frappe.ValidationError):
			profitability({"company": self.company, "from_date": "2026-10-31", "to_date": "2026-10-01"})
		with self.assertRaises(frappe.ValidationError):
			profitability({"company": self.company})

	def test_company_isolation(self):
		sale = self._si(1000, project=self.project)
		purchase = self._pi(400, project=self.project)
		other = self._other_company()
		frappe.db.set_value("Sales Invoice", sale.name, "company", other, update_modified=False)
		frappe.db.set_value("Purchase Invoice", purchase.name, "company", other, update_modified=False)
		rows, _total, _message, _summary, _columns = self._run()
		self.assertNotIn(self.project, rows)
		# a user restricted to this company may not ask for the other one
		frappe.set_user(self._user(["Accounts Manager"], restrict_to=self.company))
		with self.assertRaises(frappe.PermissionError):
			profitability({"company": other, **PERIOD})

	def test_ledger_readers_only(self):
		self._si(1000, project=self.project)
		for roles in (["Card User"], ["Card Manager"]):
			frappe.set_user(self._user(roles))
			with self.assertRaises(frappe.PermissionError, msg=roles):
				profitability(self._period())
			frappe.set_user("Administrator")
		frappe.set_user(self._user(["Accounts Manager"]))
		_columns, data, _message, _chart, _summary = profitability(self._period(project=self.project))
		self.assertEqual([r["revenue"] for r in data if not r.get("is_total")], [1000.0])

	def test_report_roles_match_the_partial_margin(self):
		roles = {r.role for r in frappe.get_doc("Report", "Project Invoice Profitability").roles}
		self.assertEqual(roles, {r.role for r in frappe.get_doc("Report", "Equipment Partial Margin").roles})
		self.assertEqual(roles, {"System Manager", "Accounts Manager"})

	def test_nothing_is_written(self):
		self._si(1000, project=self.project)
		self._pi(400)
		with (
			patch.object(frappe.db, "set_value", side_effect=AssertionError("write")),
			patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql,
		):
			self._run()
		for call in sql.call_args_list:
			statement = str(call.args[0]).lstrip().lower() if call.args else ""
			self.assertFalse(statement.startswith(("insert", "update", "delete")), statement)
