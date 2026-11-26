# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Project Invoice Profitability (FR-193, #53). Read-only: revenue and expenses of each project from
submitted Sales Invoice and Purchase Invoice lines. Only the purchase lines booked to an Expense
account that are neither a stock item nor a fixed asset are expenses; the other purchase lines are
in one informational column outside the margin. The totals reconcile to the invoices, returns
reduce their side, lines without a project sit on one "No project" row, the date window, company
isolation, role access and nothing written. All data is synthetic and rolled back."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe
from erpnext.controllers.sales_and_purchase_return import make_return_doc
from frappe.utils import flt

from card import analytics
from card.card.report.project_invoice_profitability.project_invoice_profitability import (
	execute as profitability,
)
from card.gl.masters import ensure_posting_masters, ensure_selling_price_list
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
				"selling_price_list": ensure_selling_price_list(self.company),
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

	def _stock_item(self):
		service = ensure_posting_masters(self.company).rental_item
		return (
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": "TEST-PROFIT-SPARE-" + self.token,
					"item_name": "Spare part",
					"item_group": frappe.db.get_value("Item", service, "item_group"),
					"stock_uom": frappe.db.get_value("Item", service, "stock_uom"),
					"is_stock_item": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	@contextmanager
	def _mocked_reads(self, sales, purchases, accounts=(), items=(), precision=2):
		"""Replace the invoice reads by synthetic lines, and the Account and Item reads by the
		given records. ``frappe.get_all`` goes through ``frappe.get_list``, so one patch covers
		both; every other doctype is read from the site."""
		heads = {
			"Sales Invoice": [frappe._dict(name="SI-1", project=None)],
			"Purchase Invoice": [frappe._dict(name="PI-1", project=None)],
		}
		lines = {
			"Sales Invoice Item": [frappe._dict(parent="SI-1", **line) for line in sales],
			"Purchase Invoice Item": [frappe._dict(parent="PI-1", **line) for line in purchases],
		}
		records = {"Account": list(accounts), "Item": list(items)}
		real = frappe.get_list

		def matches(record, filters):
			for field, wanted in filters.items():
				value = record.get(field)
				if isinstance(wanted, list | tuple):
					operator, operand = wanted
					if operator != "in":
						raise AssertionError(f"unexpected filter {field} {operator}")
					if value not in operand:
						return False
				elif value != wanted:
					return False
			return True

		def read(doctype, *args, **kwargs):
			if doctype in heads:
				return heads[doctype]
			if doctype in records:
				found = [frappe._dict(r) for r in records[doctype] if matches(r, kwargs["filters"])]
				return [r[kwargs["pluck"]] for r in found] if kwargs.get("pluck") else found
			return real(doctype, *args, **kwargs)

		target = (
			"card.card.report.project_invoice_profitability.project_invoice_profitability.currency_precision"
		)
		with (
			patch.object(analytics.frappe, "get_list", side_effect=read),
			patch.object(analytics, "_children", side_effect=lambda child, *args, **kw: lines[child]),
			patch(target, return_value=precision),
		):
			yield

	def _accounts(self):
		"""Synthetic accounts: classification facts only (company and root type)."""
		return [
			{"name": "EXP", "company": self.company, "root_type": "Expense"},
			{"name": "STOCK", "company": self.company, "root_type": "Asset"},
			{"name": "CWIP", "company": self.company, "root_type": "Asset"},
			{"name": "SRBNB", "company": self.company, "root_type": "Liability"},
			{"name": "EXP-OTHER", "company": "Another company", "root_type": "Expense"},
		]

	def _purchase(self, amount, project="P1", item_code="SERVICE", expense_account="EXP", is_fixed_asset=0):
		return {
			"project": project,
			"base_net_amount": amount,
			"item_code": item_code,
			"expense_account": expense_account,
			"is_fixed_asset": is_fixed_asset,
		}

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
						"is_opening": ["!=", "Yes"],
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
			["project", "project_name", "revenue", "expenses", "not_in_expenses", "margin", "margin_percent"],
		)
		extra = columns[4]
		self.assertEqual(extra["label"], "Purchases not in expenses (stock, assets)")
		self.assertEqual(extra["fieldtype"], "Currency")
		row = rows[self.project]
		self.assertEqual(row["project_name"], frappe.db.get_value("Project", self.project, "project_name"))
		self.assertEqual(row["revenue"], 1000.0)
		self.assertEqual(row["expenses"], 400.0)
		self.assertEqual(row["not_in_expenses"], 0)
		self.assertEqual(row["margin"], 600.0)
		self.assertEqual(row["margin_percent"], 60.0)
		self.assertIn("not the full net profit", message)
		self.assertIn("Journal entries and the general ledger are not read", message)
		self.assertIn("booked to an Expense account", message)
		self.assertIn('"Purchases not in expenses (stock, assets)"', message)
		self.assertNotIn("Expenses include every Purchase Invoice line", message)

	def test_expense_line_classification(self):
		"""A purchase line is an expense only when it is booked to an Expense account of the
		report company and is neither a stock item nor a fixed asset."""
		purchases = [
			self._purchase(100),  # a service on an Expense account
			self._purchase(40, item_code=None),  # no item, Expense account
			self._purchase(25, item_code="SPARE"),  # a stock item, whatever the account
			self._purchase(300, item_code="MACHINE", expense_account="CWIP", is_fixed_asset=1),
			self._purchase(7, is_fixed_asset=1),  # a fixed-asset line, whatever the account
			self._purchase(60, expense_account="STOCK"),  # not an Expense account
			self._purchase(9, expense_account="SRBNB"),
			self._purchase(5, expense_account=None),  # no account
			self._purchase(3, expense_account="EXP-OTHER"),  # an account of another company
			self._purchase(-5, item_code="SPARE"),  # a debit note reduces its own column
			self._purchase(11, project=None),
			self._purchase(13, project=None, item_code="SPARE"),
		]
		sales = [{"project": "P1", "base_net_amount": 1000}]
		items = [
			{"name": "SERVICE", "is_stock_item": 0},
			{"name": "SPARE", "is_stock_item": 1},
			{"name": "MACHINE", "is_stock_item": 0},
		]
		with self._mocked_reads(sales, purchases, self._accounts(), items):
			rows, total, _message, summary, _columns = self._run()
		row = rows["P1"]
		self.assertEqual(row["revenue"], 1000.0)
		self.assertEqual(row["expenses"], 140.0)
		self.assertEqual(row["not_in_expenses"], 404.0)
		self.assertEqual(row["margin"], 860.0)  # revenue minus expenses only
		self.assertEqual(row["margin_percent"], 86.0)
		none = rows[None]
		self.assertEqual(none["project_name"], "No project")
		self.assertEqual(none["expenses"], 11.0)
		self.assertEqual(none["not_in_expenses"], 13.0)
		self.assertEqual(none["margin"], -11.0)
		self.assertEqual(total["revenue"], 1000.0)
		self.assertEqual(total["expenses"], 151.0)
		self.assertEqual(total["not_in_expenses"], 417.0)
		self.assertEqual(total["margin"], 849.0)
		# the two purchase columns together are the net total of the purchase invoice lines
		self.assertEqual(
			total["expenses"] + total["not_in_expenses"], sum(line["base_net_amount"] for line in purchases)
		)
		self.assertEqual(summary["Project revenue"], 1000.0)
		self.assertEqual(summary["Project expenses"], 151.0)
		self.assertEqual(summary["Project margin"], 849.0)
		self.assertEqual(summary["Purchases not in expenses (stock, assets)"], 417.0)

	def test_project_with_only_non_expense_purchases_has_a_row(self):
		purchases = [self._purchase(250, item_code="SPARE", expense_account="STOCK")]
		items = [{"name": "SPARE", "is_stock_item": 1}]
		with self._mocked_reads([], purchases, self._accounts(), items):
			rows, total, _message, _summary, _columns = self._run()
		self.assertEqual(rows["P1"]["expenses"], 0)
		self.assertEqual(rows["P1"]["not_in_expenses"], 250.0)
		self.assertEqual(rows["P1"]["margin"], 0)
		self.assertIsNone(rows["P1"]["margin_percent"])
		self.assertEqual(total["margin"], 0)

	def test_stock_item_purchase_is_not_an_expense(self):
		"""Real documents: a submitted Purchase Invoice of a stock item."""
		self._si(1000, project=self.project)
		self._pi(400, project=self.project)
		stock = self._manual_pi(90, posting_date="2026-10-07", item=self._stock_item(), submit=False)
		stock.items[0].project = self.project
		stock.save()
		stock.submit()
		rows, total, _message, _summary, _columns = self._run()
		row = rows[self.project]
		self.assertEqual(row["expenses"], 400.0)
		self.assertEqual(row["not_in_expenses"], 90.0)
		self.assertEqual(row["margin"], 600.0)
		self.assertEqual(
			flt(total["expenses"] + total["not_in_expenses"], 2), self._invoice_net("Purchase Invoice")
		)

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
		# these purchases are services on an Expense account: all of them are expenses
		self.assertEqual(total["expenses"], self._invoice_net("Purchase Invoice"))
		self.assertEqual(total["not_in_expenses"], 0)
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

	def test_opening_invoices_are_not_read(self):
		sale = self._si(1000, project=self.project)
		purchase = self._pi(400, project=self.project)
		self._si(50, project=self.project)
		frappe.db.set_value("Sales Invoice", sale.name, "is_opening", "Yes", update_modified=False)
		frappe.db.set_value("Purchase Invoice", purchase.name, "is_opening", "Yes", update_modified=False)
		rows, _total, message, _summary, _columns = self._run(project=self.project)
		self.assertEqual(rows[self.project]["revenue"], 50.0)
		self.assertEqual(rows[self.project]["expenses"], 0)
		self.assertIn("Opening invoices are not read", message)

	def test_needs_read_on_both_invoice_types(self):
		"""A margin built from one side only would mislead: the report is refused."""
		self._si(1000, project=self.project)
		real = analytics.can_read
		for unreadable in ("Sales Invoice", "Purchase Invoice"):
			with patch.object(
				analytics,
				"can_read",
				side_effect=lambda doctype, u=unreadable: doctype != u and real(doctype),
			):
				with self.assertRaises(frappe.PermissionError, msg=unreadable):
					profitability(self._period())

	def test_amounts_are_summed_unrounded_and_rounded_once(self):
		sales = [{"project": "P1", "base_net_amount": 0.125}] * 3
		purchases = [self._purchase(0.0333)] * 3 + [self._purchase(0.0004, item_code="SPARE")] * 3
		items = [{"name": "SPARE", "is_stock_item": 1}]
		with self._mocked_reads(sales, purchases, self._accounts(), items, precision=3):
			rows, total, _message, summary, _columns = self._run()
		self.assertEqual(rows["P1"]["revenue"], 0.375)
		self.assertEqual(rows["P1"]["expenses"], 0.1)
		self.assertEqual(rows["P1"]["not_in_expenses"], 0.001)
		self.assertEqual(rows["P1"]["margin"], 0.275)
		self.assertEqual(total["revenue"], 0.375)
		self.assertEqual(summary["Project margin"], 0.275)

	def test_project_column_keeps_the_record_name_without_project_read(self):
		self._si(1000, project=self.project)
		with patch("card.report_access._role_reads", return_value=False):
			rows, _total, _message, _summary, columns = self._run(project=self.project)
		self.assertEqual(columns[0]["fieldtype"], "Data")
		self.assertNotIn("options", columns[0])
		row = rows[self.project]  # the record name stays; the name has its own column
		self.assertEqual(row["project_name"], frappe.db.get_value("Project", self.project, "project_name"))

	def test_project_of_another_company_shows_its_id_only(self):
		foreign = self._second_project()
		self._si(100, project=foreign)
		frappe.db.set_value("Project", foreign, "company", self._other_company(), update_modified=False)
		rows, _total, _message, _summary, _columns = self._run(project=foreign)
		self.assertEqual(rows[foreign]["revenue"], 100.0)
		self.assertIsNone(rows[foreign]["project_name"])

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
