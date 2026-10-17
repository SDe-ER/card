# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Customer-side reports (phase E, F.7 equipment-level model): "Equipment
Customer Statement" and "Equipment Customers Summary", the mirrors of the two
supplier reports. The customer billing side now lives ON the equipment
(rental_direction + default_customer + customer rate) and the cards mirror it.
CARD stores no customer balance: the accrued customer amount comes from the
cards and every money number (invoiced / received / balances) comes from the
official GL, so until Sales Invoices are posted (S3) those numbers are zero and
the reconciliation difference equals the accrued amount. App-level tests
(Frappe does not auto-build dependency test records); every record and setting
write is rolled back by the test transaction."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.constants import DIR_RENTED_OUT, DIR_SUBRENTAL, OWNED
from card.settings import setting
from card.tests.test_controllers import _days, _ensure_masters

RENTED = "إيجار"


def _set(field, value):
	frappe.db.set_single_value("Card Settings", field, value)
	# flipping single values mid-test: drop any cached single value so the next
	# setting() read is fresh (production rarely re-reads within one request).
	frappe.clear_document_cache("Card Settings", "Card Settings")


def _leaf(doctype, name_field, root):
	"""A non-group row of a tree master (Customer needs leaf group/territory)."""
	leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if leaf:
		return leaf
	leaf = "Test " + doctype
	if not frappe.db.exists(doctype, leaf):
		frappe.get_doc(
			{"doctype": doctype, name_field: leaf, "parent_" + frappe.scrub(doctype): root, "is_group": 0}
		).insert(ignore_permissions=True)
	return leaf


def _statement(filters):
	from card.card.report.equipment_customer_statement.equipment_customer_statement import execute

	columns, rows, message, _chart, summary, _flag = execute(filters)
	return columns, rows, message, summary


def _summary_report(filters):
	from card.card.report.equipment_customers_summary.equipment_customers_summary import execute

	columns, rows, message, _chart, summary, _flag = execute(filters)
	return columns, rows, message, summary


def _indicator(summary, label):
	for item in summary:
		if item["label"] == frappe._(label):
			return item["indicator"]
	return None


def _value(summary, label):
	for item in summary:
		if item["label"] == frappe._(label):
			return item["value"]
	return None


class TestCustomerReports(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		# baseline report settings (an earlier run may have left the site configured otherwise)
		_set("include_draft_in_reports", 0)
		_set("reconciliation_tolerance", 0.01)
		# A project of its own so report assertions are not polluted by other site data.
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-CRPT-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-CRPT-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		self.customer = self._customer("-A")

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _customer(self, suffix):
		cust = frappe.new_doc("Customer")
		cust.customer_name = "TEST-CRPT-CUST-" + self.token + suffix
		cust.customer_group = _leaf("Customer Group", "customer_group_name", "All Customer Groups")
		cust.territory = _leaf("Territory", "territory_name", "All Territories")
		cust.insert(ignore_permissions=True)
		return cust.name

	def _equipment(self, suffix, ownership=OWNED, direction=None, customer=None, customer_rate=None):
		"""F.7: the billing configuration lives on the equipment, not the card."""
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = ownership
		d.equipment_name = "TEST-CRPT-EQ-" + self.token + suffix
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		if ownership != OWNED:
			d.supplier = self.supplier
		if direction:
			d.rental_direction = direction
		if customer:
			d.default_customer = customer
			d.customer_rate_type = "باليوم"
			d.customer_rate = customer_rate if customer_rate is not None else 1000
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _rented_out(self, suffix, customer=None, customer_rate=1000):
		# owned equipment to a customer: 1000/day over 10h = 100/h
		return self._equipment(suffix, OWNED, DIR_RENTED_OUT, customer or self.customer, customer_rate)

	def _sub_rental(self, suffix, customer=None, customer_rate=1200):
		# rented at 750/day, rented out at 1200/day (120/h)
		return self._equipment(suffix, RENTED, DIR_SUBRENTAL, customer or self.customer, customer_rate)

	def _rented_in(self, suffix):
		# a plain rental with no customer side (derives مستأجَرة من مورد)
		return self._equipment(suffix, RENTED)

	def _card(self, eq, hours_list, submit=False):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _filters(self, **kw):
		f = {"from_month": 9, "from_year": 2026, "project": self.project}
		f.update(kw)
		return f

	def _card_rows(self, rows):
		return [r for r in rows if r.get("card")]

	# ---------- 1. statement lists the customer-billing cards ----------

	def test_statement_lists_rented_out_card_not_rented_in(self):
		# owned equipment to a customer: 1000/day over 10h = 100/h; 20h -> 2000
		card = self._card(self._rented_out("-OUT"), [10, 10], submit=True)
		# a plain rental (no customer on the equipment) never belongs to a customer statement
		rented_in = self._card(self._rented_in("-IN"), [10, 10], submit=True)

		_cols, rows, _msg, _summary = _statement(self._filters(customer=self.customer))
		card_rows = self._card_rows(rows)
		self.assertEqual([r["card"] for r in card_rows], [card.name])
		self.assertNotIn(rented_in.name, [r.get("card") for r in rows])

		row = card_rows[0]
		self.assertEqual(flt(row["hours"]), 20.0)
		self.assertEqual(flt(row["customer_amount"]), 2000.0)
		self.assertEqual(flt(row["hourly_rate"]), 100.0)  # snapshot taken on submit
		self.assertEqual(flt(row["customer_rate"]), 1000.0)
		self.assertEqual(row["period"], "2026-09")
		self.assertEqual(row["first_date"], "2026-09-01")
		self.assertEqual(row["last_date"], "2026-09-02")
		self.assertEqual(row["working_days"], 2)
		self.assertEqual(row["label"], card.name)  # submitted: no draft marker

		total = next(r for r in rows if r.get("row_id") == "TOTAL")
		self.assertEqual(flt(total["customer_amount"]), 2000.0)
		self.assertEqual(flt(total["hours"]), 20.0)

		# another customer's statement does not list this card
		other = self._customer("-B")
		_cols, other_rows, _msg, _summary = _statement(self._filters(customer=other))
		self.assertEqual(other_rows, [])

	def test_statement_includes_sub_rental_card(self):
		# rented at 750/day, rented out at 1200/day (120/h); 10h -> customer side 1200
		card = self._card(self._sub_rental("-SUB"), [10], submit=True)
		_cols, rows, _msg, _summary = _statement(self._filters(customer=self.customer))
		card_rows = self._card_rows(rows)
		self.assertEqual([r["card"] for r in card_rows], [card.name])
		self.assertEqual(flt(card_rows[0]["customer_amount"]), 1200.0)  # our price, not the supplier cost
		self.assertEqual(flt(card_rows[0]["hourly_rate"]), 120.0)

	def test_cancelled_card_is_not_listed(self):
		card = self._card(self._rented_out("-CAN"), [10], submit=True)
		card.cancel()
		_cols, rows, _msg, _summary = _statement(self._filters(customer=self.customer, include_draft=1))
		self.assertEqual(self._card_rows(rows), [])

	# ---------- 2. include_draft ----------

	def test_draft_card_only_when_include_draft(self):
		submitted = self._card(self._rented_out("-S"), [10, 10], submit=True)
		draft = self._card(self._rented_out("-D"), [10])
		self.assertEqual(draft.docstatus, 0)

		def card_rows(**kw):
			_cols, rows, _msg, _summary = _statement(self._filters(customer=self.customer, **kw))
			return {r["card"]: r for r in self._card_rows(rows)}

		# setting off (baseline) and no filter: draft excluded
		by_card = card_rows()
		self.assertIn(submitted.name, by_card)
		self.assertNotIn(draft.name, by_card)

		# explicit filter on: draft listed, marked, with its effective hourly rate and accrued amount
		by_card = card_rows(include_draft=1)
		self.assertIn(submitted.name, by_card)
		self.assertIn(draft.name, by_card)
		self.assertTrue(by_card[draft.name]["label"].endswith(frappe._(" (Draft)")))
		self.assertFalse(by_card[submitted.name]["label"].endswith(frappe._(" (Draft)")))
		self.assertEqual(flt(by_card[draft.name]["customer_amount"]), 1000.0)
		self.assertEqual(flt(by_card[draft.name]["hourly_rate"]), 100.0)

		# the setting drives the default when the filter is absent; an explicit filter still wins
		_set("include_draft_in_reports", 1)
		self.assertIn(draft.name, card_rows())
		self.assertNotIn(draft.name, card_rows(include_draft=0))

	def test_summary_counts_submitted_cards_only(self):
		# like the supplier summary: drafts are never part of the summary report
		self._card(self._rented_out("-S"), [10, 10], submit=True)
		self._card(self._rented_out("-D"), [10])
		_set("include_draft_in_reports", 1)
		_cols, rows, _msg, _summary = _summary_report(self._filters())
		data = [r for r in rows if not r.get("is_total")]
		self.assertEqual(len(data), 1)
		self.assertEqual(data[0]["card_count"], 1)
		self.assertEqual(flt(data[0]["accrued"]), 2000.0)

	# ---------- 3. summary: one row per customer + reconciliation ----------

	def test_summary_one_row_per_customer(self):
		customer_b = self._customer("-B")
		# customer A: two cards (2000 + 1000); customer B: one card (10h at 500/day = 50/h -> 500)
		self._card(self._rented_out("-A1"), [10, 10], submit=True)
		self._card(self._rented_out("-A2"), [10], submit=True)
		self._card(self._rented_out("-B1", customer=customer_b, customer_rate=500), [10], submit=True)
		# a rented-in card (no customer on the equipment) must not create a row
		self._card(self._rented_in("-IN"), [10], submit=True)

		_cols, rows, _msg, summary = _summary_report(self._filters())
		data = [r for r in rows if not r.get("is_total")]
		self.assertEqual(len(data), 2)
		by_customer = {r["customer"]: r for r in data}
		self.assertEqual(set(by_customer), {self.customer, customer_b})

		a = by_customer[self.customer]
		self.assertEqual(a["equipment_count"], 2)
		self.assertEqual(a["card_count"], 2)
		self.assertEqual(a["working_days"], 3)
		self.assertEqual(flt(a["hours"]), 30.0)
		self.assertEqual(flt(a["accrued"]), 3000.0)
		b = by_customer[customer_b]
		self.assertEqual(b["card_count"], 1)
		self.assertEqual(flt(b["accrued"]), 500.0)

		# highest accrued first, total row last
		self.assertEqual([r["customer"] for r in data], [self.customer, customer_b])
		self.assertTrue(rows[-1].get("is_total"))
		self.assertEqual(flt(rows[-1]["accrued"]), 3500.0)

		# no AR yet: invoiced / received / balances are zero and the difference is the full accrued amount
		for r in rows:
			self.assertEqual(flt(r["invoiced"]), 0.0)
			self.assertEqual(flt(r["received"]), 0.0)
			self.assertEqual(flt(r["opening"]), 0.0)
			self.assertEqual(flt(r["closing"]), 0.0)
			self.assertEqual(flt(r["diff"]), flt(r["accrued"]))

		self.assertEqual(_value(summary, "Number of customers"), 2)
		self.assertEqual(flt(_value(summary, "Total accrued (cards)")), 3500.0)
		self.assertEqual(flt(_value(summary, "Not invoiced through Card")), 3500.0)

	def test_statement_money_columns_zero_without_ar(self):
		self._card(self._rented_out("-Z"), [10, 10], submit=True)
		_cols, _rows, msg, summary = _statement(self._filters(customer=self.customer))
		self.assertEqual(flt(_value(summary, "Total accrued (cards)")), 2000.0)
		self.assertEqual(flt(_value(summary, "Invoiced entries (Debit)")), 0.0)
		self.assertEqual(flt(_value(summary, "Received (Credit)")), 0.0)
		self.assertEqual(flt(_value(summary, "Opening balance")), 0.0)
		self.assertEqual(flt(_value(summary, "Customer closing balance")), 0.0)
		self.assertEqual(flt(_value(summary, "Not invoiced through Card")), 2000.0)  # accrued - invoiced
		self.assertIn(self.customer, msg)

	def test_reconciliation_indicator_follows_tolerance_setting(self):
		# A submitted billing card with NO customer GL entries: accrued > 0, invoiced = 0, so the
		# reconciliation difference is large (2,000). Both reports expose the flag as the "indicator"
		# of the summary item labelled "Not invoiced through Card" (Green = within tolerance,
		# Red = over tolerance); that is what is asserted. Both are limited to this test's own
		# project so other data cannot offset the difference.
		self._card(self._rented_out("-T"), [10, 10], submit=True)

		# default reproduces the supplier-side 0.01 when the setting is unset
		frappe.db.delete("Singles", {"doctype": "Card Settings", "field": "reconciliation_tolerance"})
		self.assertEqual(flt(setting("reconciliation_tolerance")), 0.01)

		label = "Not invoiced through Card"
		statement_filters = self._filters(customer=self.customer)
		summary_filters = self._filters()

		# baseline tolerance (0.01): the large difference IS flagged in both reports
		_set("reconciliation_tolerance", 0.01)
		self.assertEqual(_indicator(_statement(statement_filters)[3], label), "Red")
		self.assertEqual(_indicator(_summary_report(summary_filters)[3], label), "Red")

		# huge tolerance: nothing is flagged (kept below the Currency column limit)
		_set("reconciliation_tolerance", 1000000000)
		self.assertEqual(_indicator(_statement(statement_filters)[3], label), "Green")
		self.assertEqual(_indicator(_summary_report(summary_filters)[3], label), "Green")

	# ---------- 4. empty filters ----------

	def test_reports_with_empty_filters_do_not_crash(self):
		self._card(self._rented_out("-E"), [10], submit=True)

		# no customer selected: empty statement + hint, columns still returned, no money items
		cols, rows, msg, summary = _statement({"from_month": 9, "from_year": 2026, "project": self.project})
		self.assertEqual(rows, [])
		self.assertTrue(cols)
		self.assertIn(frappe._("Select a customer to display the statement."), msg)
		labels = [item["label"] for item in summary]
		self.assertNotIn(frappe._("Invoiced entries (Debit)"), labels)
		self.assertNotIn(frappe._("Customer closing balance"), labels)
		self.assertEqual(_value(summary, "Number of equipment"), 0)

		# the period is the only mandatory input: no filters at all is a clean validation error
		# (never a TypeError / KeyError), exactly like the supplier reports
		with self.assertRaises(frappe.ValidationError):
			_statement({})
		with self.assertRaises(frappe.ValidationError):
			_summary_report(None)

		# a summary with only the period (no project filter) runs and returns the standard shape
		cols, rows, msg, summary = _summary_report({"from_month": 9, "from_year": 2026})
		self.assertTrue(cols)
		self.assertIsInstance(rows, list)
		self.assertIsInstance(summary, list)

		# a period with no billing cards: empty rows, no total row, zero summary
		cols, rows, msg, summary = _summary_report(
			self._filters(from_month=1, from_year=2000, to_month=1, to_year=2000)
		)
		self.assertEqual(rows, [])
		self.assertEqual(_value(summary, "Number of customers"), 0)
