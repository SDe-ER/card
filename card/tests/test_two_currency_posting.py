# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-136 (#54 test matrix rows 1, 2 and 6; #53 currency policy; risk R-26): two companies with two currencies.

Company A keeps the test site's company and currency; company B is a real ERPNext company whose default currency
is different. The same supplier works for both. The monthly posting of each company:

- takes only that company's sources (B's card never reaches A's invoice, and the other way round);
- is an invoice in that company's own currency at rate 1 (O-17: company currency only, CARD converts nothing),
  against that company's payable account, expense accounts, cost centers and project;
- posts, on submit, ledger rows of that company in that company's currency only.

The CARD reports label money with the currency of the company they ran for (``card.report_currency``)."""

import frappe
from frappe.utils import flt

from card.card.report.posting_source_integrity.posting_source_integrity import execute as integrity_report
from card.gl.posting import build_monthly_posting
from card.report_currency import company_currency, company_currency_report, label_currency
from card.tests.test_s3_posting import _PostingBase

ACCOUNT_KEYS = ("exp_rental", "exp_diesel", "exp_transport", "inc_rental", "vat_in", "vat_out")


def _other_currency(currency):
	for code in ("USD", "EUR", "AED", "GBP"):
		if code != currency and frappe.db.exists("Currency", code):
			return code
	raise AssertionError("the test site has no second currency")


def _company_b(token, like):
	"""A real company (chart of accounts, cost centers) in another currency than ``like``."""
	currency = _other_currency(frappe.db.get_value("Company", like, "default_currency"))
	frappe.db.set_value("Currency", currency, "enabled", 1)
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "TEST-2CUR-B-" + token,
			"abbr": "B" + token[:5].upper(),
			"default_currency": currency,
			"country": frappe.db.get_value("Company", like, "country"),
			"create_chart_of_accounts_based_on": "Standard Template",
			"chart_of_accounts": "Standard",
		}
	).insert(ignore_permissions=True)
	for fy in frappe.get_all(
		"Fiscal Year",
		filters={"year_start_date": ["<=", "2026-09-30"], "year_end_date": [">=", "2026-09-30"]},
		pluck="name",
	):
		doc = frappe.get_doc("Fiscal Year", fy)
		if doc.get("companies") and company.name not in [c.company for c in doc.companies]:
			doc.append("companies", {"company": company.name})
			doc.save(ignore_permissions=True)
	return company.name


class TestTwoCurrencyPosting(_PostingBase):
	def setUp(self):
		super().setUp()  # company A, fully configured
		self.A = frappe._dict(
			company=self.company,
			project=self.project,
			supplier=self.supplier,
			**{key: getattr(self, key) for key in ACCOUNT_KEYS},
		)
		self.A.currency = company_currency(self.A.company)
		company_b = _company_b(self.token, self.A.company)
		# configure company B with the same fixture (its own project, accounts, tax templates, settings row)
		self._m = dict(self._m, company=company_b)
		_PostingBase.setUp(self)
		self.B = frappe._dict(
			company=company_b,
			project=self.project,
			supplier=self.supplier,
			**{key: getattr(self, key) for key in ACCOUNT_KEYS},
		)
		self.B.currency = company_currency(company_b)
		self.supplier = self.A.supplier  # one supplier for both companies
		frappe.db.set_value("Supplier", self.supplier, "tax_id", "300000000000003", update_modified=False)

	def _side(self, side):
		self.company, self.project = side.company, side.project
		eq = self._equipment(rate_type="بالساعة", rate=10 if side is self.A else 7)
		card = self._card(eq, [8, 8], submit=True)
		return eq, card

	def _build(self, side):
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(side.company, "Supplier", self.supplier, 9, 2026)
		)
		return pi

	def test_each_company_posts_in_its_own_currency(self):
		self.assertNotEqual(self.A.currency, self.B.currency)
		_eq_a, card_a = self._side(self.A)
		_eq_b, card_b = self._side(self.B)
		self.assertEqual(flt(card_a.net_amount), 160.0)
		self.assertEqual(flt(card_b.net_amount), 112.0)
		pis = {}
		for side, card, other in ((self.A, card_a, card_b), (self.B, card_b, card_a)):
			with self.subTest(company=side.company):
				pi = self._build(side)
				pis[side.company] = pi
				self.assertEqual(pi.company, side.company)
				self.assertEqual(pi.currency, side.currency)
				self.assertEqual(flt(pi.conversion_rate), 1.0)
				self.assertEqual(frappe.db.get_value("Account", pi.credit_to, "company"), side.company)
				self.assertEqual(
					frappe.db.get_value("Account", pi.credit_to, "account_currency"), side.currency
				)
				self.assertEqual(flt(pi.net_total, 2), flt(card.net_amount, 2))
				self.assertEqual(flt(pi.base_net_total, 2), flt(pi.net_total, 2))
				descriptions = " | ".join(i.description or "" for i in pi.items)
				self.assertIn(card.name, descriptions)
				self.assertNotIn(other.name, descriptions)
				for item in pi.items:
					self.assertEqual(item.expense_account, side.exp_rental)
					self.assertEqual(
						frappe.db.get_value("Cost Center", item.cost_center, "company"), side.company
					)
					self.assertEqual(item.project, side.project)
				log = frappe.get_all(
					"GL Posting Log",
					filters={"posting_doc": pi.name, "status": "Draft"},
					fields=["name", "company"],
				)
				self.assertEqual([row.company for row in log], [side.company])
				sources = frappe.get_all(
					"GL Posting Source", filters={"parent": log[0].name}, pluck="source_name"
				)
				self.assertEqual(sources, [card.name])

		for side in (self.A, self.B):
			pi = pis[side.company]
			pi.bill_no = "TEST-2CUR-" + side.company[-6:] + self.token
			pi.bill_date = pi.posting_date
			pi.submit()
			gl = frappe.get_all(
				"GL Entry",
				filters={"voucher_type": "Purchase Invoice", "voucher_no": pi.name, "is_cancelled": 0},
				fields=[
					"company",
					"account",
					"account_currency",
					"debit",
					"credit",
					"debit_in_account_currency",
				],
			)
			self.assertTrue(gl)
			self.assertEqual({g.company for g in gl}, {side.company})
			self.assertEqual({g.account_currency for g in gl}, {side.currency})
			for g in gl:
				self.assertEqual(frappe.db.get_value("Account", g.account, "company"), side.company)
				self.assertEqual(flt(g.debit, 2), flt(g.debit_in_account_currency, 2))
			self.assertEqual(flt(sum(g.debit for g in gl), 2), flt(sum(g.credit for g in gl), 2))

		# the reports label money with the currency of the company they ran for
		for side, card in ((self.A, card_a), (self.B, card_b)):
			columns, rows, *_rest = integrity_report(
				{"company": side.company, "from_date": "2026-09-01", "to_date": "2026-09-30", "show": "All"}
			)
			amount = next(c for c in columns if c["fieldname"] == "amount")
			self.assertEqual(amount["options"], "currency")
			mine = [r for r in rows if r["source"] == card.name]
			self.assertEqual(len(mine), 1, rows)
			self.assertFalse(mine[0]["problem"], mine[0])
			self.assertEqual(mine[0]["currency"], side.currency)
			self.assertFalse(
				[r for r in rows if r["source"] in (card_a.name, card_b.name) and r is not mine[0]]
			)

	def test_label_keeps_values_and_own_options(self):
		columns = [
			{"fieldname": "amount", "fieldtype": "Currency"},
			{"fieldname": "rate", "fieldtype": "Currency", "options": "rate_currency"},
			{"fieldname": "qty", "fieldtype": "Float"},
		]
		rows = [{"amount": 5.0, "qty": 1}, {"amount": 7.0, "currency": "XYZ"}]
		summary = [{"label": "Total", "value": 12, "datatype": "Currency"}, {"label": "N", "datatype": "Int"}]
		out = label_currency((columns, rows, None, None, summary), self.B.currency)
		self.assertIsInstance(out, tuple)
		self.assertEqual(columns[0]["options"], "currency")
		self.assertEqual(columns[1]["options"], "rate_currency")  # a column's own currency field wins
		self.assertEqual([r["currency"] for r in rows], [self.B.currency, "XYZ"])
		self.assertEqual([r["amount"] for r in rows], [5.0, 7.0])
		self.assertEqual(summary[0]["currency"], self.B.currency)
		self.assertNotIn("currency", summary[1])
		# no money column: rows are left as they are
		plain = [{"qty": 1}]
		label_currency(([{"fieldname": "qty", "fieldtype": "Float"}], plain), self.B.currency)
		self.assertEqual(plain, [{"qty": 1}])

	def test_decorator_uses_the_company_the_report_ran_for(self):
		@company_currency_report("Card Monthly Card")
		def execute(filters=None):
			return [{"fieldname": "amount", "fieldtype": "Currency"}], [{"amount": 1.0}]

		for side in (self.A, self.B):
			with self.subTest(company=side.company):
				_columns, rows = execute({"company": side.company})
				self.assertEqual(rows[0]["currency"], side.currency)
