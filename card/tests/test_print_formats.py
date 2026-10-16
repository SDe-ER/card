# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#25: the CARD print formats print the right money on the right side.

Rendered through frappe.get_print (the same Jinja path the PDF uses), on cards
of each billed side with additions/deductions. All data is per-test and
rolled back."""

import re

import frappe
from frappe.utils import fmt_money

from card.print_utils import card_amount_in_words
from card.tests.test_controllers import _days
from card.tests.test_customer import RENTED, _CustomerCardsBase

MONTHLY = "Card Monthly Card Print"
LEGACY_MONTHLY = "كارت تشغيل شهري"
ADD, DED = "إضافة", "خصم"
HOURS = [10, 10, 10, 10, 8]  # 48 h


def _cell(html, label):
	"""The value printed under a totals-cell label (None when the cell is absent)."""
	m = re.search(re.escape(label) + r'</span><span class="val">([^<]*)</span>', html)
	return m.group(1).strip() if m else None


class TestPrintFormats(_CustomerCardsBase):
	def _card_with(self, eq, adjustments):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days(HOURS):
			c.append("days", row)
		for kind, amount, side, description in adjustments:
			c.append(
				"adjustments",
				{"adjustment_type": kind, "amount": amount, "side": side, "description": description},
			)
		c.insert(ignore_permissions=True)
		c.reload()
		return c

	def _print(self, card, fmt=MONTHLY):
		return frappe.get_print("Card Monthly Card", card.name, print_format=fmt)

	def test_customer_card_prints_the_customer_net(self):
		# 1500/day over 10 h = 150/h x 48 h = 7,200; customer deduction 1,200 -> 6,000
		card = self._card_with(
			self._rented_out(customer_rate=1500), [(DED, 1200, "Customer", "TEST-PRINT-DED")]
		)
		self.assertEqual(card.customer_net_amount, 6000)
		self.assertEqual(card.net_amount, 0)
		html = self._print(card)
		self.assertEqual(_cell(html, "الصافي المستحق على العميل"), fmt_money(6000))
		self.assertEqual(_cell(html, "خصومات العميل"), fmt_money(1200))
		self.assertIsNone(_cell(html, "الصافي المستحق للمورد"))
		self.assertIn("TEST-PRINT-DED", html)

	def test_supplier_card_prints_the_supplier_net(self):
		# 750/day over 10 h = 75/h x 48 h = 3,600; supplier deduction 600 -> 3,000
		card = self._card_with(self._equipment(RENTED), [(DED, 600, "Supplier", "TEST-PRINT-SUP")])
		self.assertEqual(card.net_amount, 3000)
		html = self._print(card)
		self.assertEqual(_cell(html, "الصافي المستحق للمورد"), fmt_money(3000))
		self.assertEqual(_cell(html, "خصومات المورد"), fmt_money(600))
		self.assertIsNone(_cell(html, "الصافي المستحق على العميل"))

	def test_sub_rental_prints_each_side_with_its_own_rows(self):
		# supplier 3,600 + 100 = 3,700; customer 1200/day = 120/h x 48 = 5,760 - 200 = 5,560
		card = self._card_with(
			self._sub_rental(),
			[(ADD, 100, "Supplier", "TEST-PRINT-S"), (DED, 200, "Customer", "TEST-PRINT-C")],
		)
		self.assertEqual((card.net_amount, card.customer_net_amount), (3700, 5560))
		html = self._print(card)
		self.assertEqual(_cell(html, "إضافات المورد"), fmt_money(100))
		self.assertEqual(_cell(html, "خصومات المورد"), fmt_money(0))
		self.assertEqual(_cell(html, "الصافي المستحق للمورد"), fmt_money(3700))
		self.assertEqual(_cell(html, "إضافات العميل"), fmt_money(0))
		self.assertEqual(_cell(html, "خصومات العميل"), fmt_money(200))
		self.assertEqual(_cell(html, "الصافي المستحق على العميل"), fmt_money(5560))

	def test_no_adjustments_prints_no_net_block(self):
		html = self._print(self._card_with(self._equipment(RENTED), []))
		self.assertIsNone(_cell(html, "الصافي المستحق للمورد"))
		self.assertNotIn('class="emc-adj"', html)

	def test_printing_changes_no_stored_value(self):
		card = self._card_with(self._sub_rental(), [(DED, 200, "Customer", "TEST-PRINT-K")])
		fields = ["amount", "net_amount", "customer_amount", "customer_net_amount", "modified"]
		before = frappe.db.get_value("Card Monthly Card", card.name, fields, as_dict=True)
		self._print(card)
		self._print(card, LEGACY_MONTHLY)
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, fields, as_dict=True), before)

	def test_legacy_format_prints_the_customer_amount_on_customer_cards(self):
		card = self._card_with(self._rented_out(customer_rate=1500), [])
		html = self._print(card, LEGACY_MONTHLY)
		self.assertEqual(_cell(html, "القيمة الإجمالية"), fmt_money(7200))


class TestDieselTransportPrints(_CustomerCardsBase):
	def test_money_fields_are_not_labelled_amount(self):
		# core translates "Amount" as a quantity (كمية) in Arabic
		for doctype, label in (
			("Project Diesel Fill", "Fill amount"),
			("Equipment Transport", "Transport cost"),
		):
			self.assertEqual(frappe.get_meta(doctype).get_label("amount"), label)

	def test_prints_render_the_amount_in_words(self):
		fill = frappe.new_doc("Project Diesel Fill")
		fill.update(
			{
				"date": "2026-09-15",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 1000,
				"unit_price": 2,
			}
		)
		fill.insert(ignore_permissions=True)
		transport = frappe.new_doc("Equipment Transport")
		transport.update(
			{
				"date": "2026-09-15",
				"project": self.project,
				"transport_supplier": self.supplier,
				"company": self.company,
				"amount": 3500,
			}
		)
		transport.insert(ignore_permissions=True)
		for doc, amount in ((fill, 2000), (transport, 3500)):
			html = frappe.get_print(doc.doctype, doc.name, print_format=doc.doctype + " Print")
			self.assertIn(card_amount_in_words(amount, self.company), html)

	def test_arabic_words_use_the_currency_symbol_not_its_code(self):
		currency = frappe.get_cached_value("Company", self.company, "default_currency")
		symbol = frappe.get_cached_value("Currency", currency, "symbol")
		lang = frappe.local.lang
		try:
			frappe.local.lang = "ar"
			words = card_amount_in_words(2000, self.company)
		finally:
			frappe.local.lang = lang
		if symbol and symbol != currency:
			self.assertNotIn(currency, words)
			self.assertIn(symbol, words)
		frappe.local.lang = "en"
		try:
			self.assertEqual(
				card_amount_in_words(2000, self.company), frappe.utils.money_in_words(2000, currency)
			)
		finally:
			frappe.local.lang = lang
