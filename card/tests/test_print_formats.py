# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#25: the CARD print formats print the right money on the right side.

Rendered through frappe.get_print (the same Jinja path the PDF uses), on cards
of each billed side with additions/deductions. All data is per-test and
rolled back."""

import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.utils import fmt_money

from card.constants import OWNED
from card.print_utils import card_amount_in_words
from card.tests.diesel_price import use_fill_price
from card.tests.test_controllers import _days
from card.tests.test_customer import RENTED, _CustomerCardsBase
from card.tests.transport_parties import company_paid

MONTHLY = "Card Monthly Card Print"
LEGACY_MONTHLY = "كارت تشغيل شهري"
ADD, DED = "إضافة", "خصم"
HOURS = [10, 10, 10, 10, 8]  # 48 h
# FR-174: the four settlement rows of each billed side, in print order (owner's exact Arabic labels)
BEFORE, ADDITIONS, DEDUCTIONS, NET = (
	"الإجمالي قبل الإضافات والخصومات",
	"إجمالي الإضافات",
	"إجمالي الخصومات",
	"الصافي بعد الإضافات والخصومات",
)
# the settlement headers say the figures are before VAT (owner decision 2026-11-22)
SUPPLIER, CUSTOMER = "تسوية المورد (قبل الضريبة)", "تسوية العميل (قبل الضريبة)"


def _cell(html, label):
	"""The value printed next to a totals label (None when the line is absent)."""
	m = re.search(re.escape(label) + r'</td><td class="v">([^<]*)</td>', html)
	return m.group(1).strip() if m else None


def _settlement(html, header):
	"""The (label, value) rows of one side's settlement table, in print order (None when the side is absent)."""
	m = re.search(
		r'<table class="emc-tot emc-net">\s*<tr><th colspan="2">'
		+ re.escape(header)
		+ r"</th></tr>(.*?)</table>",
		html,
		re.S,
	)
	if not m:
		return None
	return re.findall(r'<td class="k">([^<]*)</td><td class="v">([^<]*)</td>', m.group(1))


def _sar(value, company):
	"""A settlement amount as printed: two decimals and the company currency (SAR for SDCE)."""
	currency = frappe.get_cached_value("Company", company, "default_currency")
	return "%s %s" % (fmt_money(value, precision=2), currency)


class TestPrintFormats(_CustomerCardsBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# the print labels go through _(): compile Card's ar catalogue in this process (Frappe's
		# own step) into a folder only this class reads, so the Arabic assertions never depend on
		# a stale bench-wide sites/assets/locale catalogue (same approach as test_mobile)
		from frappe.gettext import translate
		from frappe.translate import clear_cache

		cls._mo_dir = tempfile.TemporaryDirectory()
		cls.addClassCleanup(cls._mo_dir.cleanup)
		card_mo = Path(cls._mo_dir.name, "card.mo")
		real_mo_path = translate.get_mo_path

		def mo_path(app, locale=None):
			return card_mo if (app, locale) == ("card", "ar") else real_mo_path(app, locale)

		mo_patch = patch.object(translate, "get_mo_path", side_effect=mo_path)
		mo_patch.start()
		# class cleanups run even when setUpClass fails after this point; clear_cache runs after
		# the patch stops (cleanups run last-in first-out)
		cls.addClassCleanup(clear_cache)
		cls.addClassCleanup(mo_patch.stop)
		translate._compile_translation("card", "ar", force=True)
		clear_cache()

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
				{
					"adjustment_date": "2026-09-01",
					"adjustment_type": kind,
					"amount": amount,
					"side": side,
					"description": description,
				},
			)
		c.insert(ignore_permissions=True)
		c.reload()
		return c

	def _print(self, card, fmt=MONTHLY, lang="ar"):
		# the print follows the print language: the labels asserted here are the Arabic ones
		previous = frappe.local.lang
		try:
			frappe.local.lang = lang
			return frappe.get_print("Card Monthly Card", card.name, print_format=fmt)
		finally:
			frappe.local.lang = previous

	def test_customer_card_prints_the_customer_net(self):
		# 1500/day over 10 h = 150/h x 48 h = 7,200; customer deduction 1,200 -> 6,000
		card = self._card_with(
			self._rented_out(customer_rate=1500), [(DED, 1200, "Customer", "TEST-PRINT-DED")]
		)
		self.assertEqual(card.customer_net_amount, 6000)
		self.assertEqual(card.net_amount, 0)
		html = self._print(card)
		c = self.company
		self.assertEqual(
			_settlement(html, CUSTOMER),
			[
				(BEFORE, _sar(7200, c)),
				(ADDITIONS, _sar(0, c)),
				(DEDUCTIONS, _sar(1200, c)),
				(NET, _sar(6000, c)),
			],
		)
		self.assertIsNone(_settlement(html, SUPPLIER))
		self.assertIn("TEST-PRINT-DED", html)

	def test_supplier_card_prints_the_supplier_net(self):
		# 750/day over 10 h = 75/h x 48 h = 3,600; supplier deduction 600 -> 3,000
		card = self._card_with(self._equipment(RENTED), [(DED, 600, "Supplier", "TEST-PRINT-SUP")])
		self.assertEqual(card.net_amount, 3000)
		html = self._print(card)
		# the top box is the gross (the strip carries the net)
		self.assertEqual(_cell(html, "القيمة الإجمالية"), _sar(3600, self.company))
		c = self.company
		self.assertEqual(
			_settlement(html, SUPPLIER),
			[
				(BEFORE, _sar(3600, c)),
				(ADDITIONS, _sar(0, c)),
				(DEDUCTIONS, _sar(600, c)),
				(NET, _sar(3000, c)),
			],
		)
		self.assertIsNone(_settlement(html, CUSTOMER))

	def test_sub_rental_prints_each_side_with_its_own_rows(self):
		# supplier 3,600 + 100 = 3,700; customer 1200/day = 120/h x 48 = 5,760 - 200 = 5,560
		card = self._card_with(
			self._sub_rental(),
			[(ADD, 100, "Supplier", "TEST-PRINT-S"), (DED, 200, "Customer", "TEST-PRINT-C")],
		)
		self.assertEqual((card.net_amount, card.customer_net_amount), (3700, 5560))
		html = self._print(card)
		self.assertEqual(_cell(html, "القيمة الإجمالية"), _sar(3600, self.company))
		self.assertIn(frappe.db.get_value("Customer", self.customer, "customer_name"), html)
		c = self.company
		self.assertEqual(
			_settlement(html, SUPPLIER),
			[
				(BEFORE, _sar(3600, c)),
				(ADDITIONS, _sar(100, c)),
				(DEDUCTIONS, _sar(0, c)),
				(NET, _sar(3700, c)),
			],
		)
		self.assertEqual(
			_settlement(html, CUSTOMER),
			[
				(BEFORE, _sar(5760, c)),
				(ADDITIONS, _sar(0, c)),
				(DEDUCTIONS, _sar(200, c)),
				(NET, _sar(5560, c)),
			],
		)
		# the printed nets are what the monthly invoices bill before VAT
		from card.gl.posting import _card_lines

		row = frappe._dict(
			rental_item="X",
			rental_out_item="X",
			equipment_rental_expense_account="X",
			equipment_rental_income_account="X",
		)
		for side, header in (("Supplier", SUPPLIER), ("Customer", CUSTOMER)):
			_doc, lines, discount, _cn = _card_lines(card.name, side, row, {})
			billed = sum(line["rate"] for line in lines) - discount
			self.assertEqual(_settlement(html, header)[-1], (NET, _sar(billed, c)))

	def test_no_adjustments_prints_gross_equal_to_net(self):
		html = self._print(self._card_with(self._equipment(RENTED), []))
		self.assertNotIn('class="emc-adj"', html)
		c = self.company
		self.assertEqual(
			_settlement(html, SUPPLIER),
			[
				(BEFORE, _sar(3600, c)),
				(ADDITIONS, _sar(0, c)),
				(DEDUCTIONS, _sar(0, c)),
				(NET, _sar(3600, c)),
			],
		)
		self.assertIsNone(_settlement(html, CUSTOMER))

	def test_a_v1_1_row_without_side_prints_on_the_supplier_side(self):
		card = self._card_with(self._equipment(RENTED), [(DED, 600, "Supplier", "TEST-PRINT-V11")])
		frappe.db.set_value(
			"Card Monthly Card Adjustment", card.adjustments[0].name, "side", None, update_modified=False
		)
		card.reload()
		html = self._print(card)
		rows = dict(_settlement(html, SUPPLIER))
		self.assertEqual((rows[DEDUCTIONS], rows[NET]), (_sar(600, self.company), _sar(3000, self.company)))
		self.assertIsNone(_settlement(html, CUSTOMER))

	def test_internal_card_prints_no_settlement(self):
		html = self._print(self._card_with(self._equipment(OWNED), []))
		self.assertIsNone(_settlement(html, SUPPLIER))
		self.assertIsNone(_settlement(html, CUSTOMER))

	def _card_2430(self, adjustments, extra=()):
		# 750/day over 10 h = 75/h x 32.4 h = 2,430.00
		c = frappe.new_doc("Card Monthly Card")
		c.update({"equipment": self._equipment(RENTED).name, "project": self.project, "shift": "نهاري"})
		c.update({"month": "09", "year": 2026})
		for row in _days([10, 10, 10, 2.4]):
			c.append("days", row)
		for kind, amount, description in adjustments:
			row = {"adjustment_type": kind, "amount": amount, "side": "Supplier", "description": description}
			c.append("adjustments", {"adjustment_date": "2026-09-02", **row})
		for row in extra:
			c.append("adjustments", {"adjustment_date": "2026-09-03", **row})
		c.insert(ignore_permissions=True)
		c.reload()
		return c

	def _assert_four_rows(self, card, before, additions, deductions, net):
		# the four printed amounts are the saved card's: its base, additions, deductions and stored net
		self.assertEqual(
			(card.amount, card.total_additions, card.total_deductions, card.net_amount),
			(before, additions, deductions, net),
		)
		c = self.company
		self.assertEqual(
			_settlement(self._print(card), SUPPLIER),
			[
				(BEFORE, _sar(before, c)),
				(ADDITIONS, _sar(additions, c)),
				(DEDUCTIONS, _sar(deductions, c)),
				(NET, _sar(net, c)),
			],
		)

	def test_diesel_deduction_only_prints_zero_additions(self):
		self._assert_four_rows(self._card_2430([(DED, 200, "TEST-PRINT-DIESEL")]), 2430, 0, 200, 2230)

	def test_additions_and_deductions_are_applied_once(self):
		card = self._card_2430([(ADD, 150, "TEST-PRINT-ADD"), (DED, 200, "TEST-PRINT-DED2")])
		self._assert_four_rows(card, 2430, 150, 200, 2380)

	def test_net_row_is_the_last_highlighted_row(self):
		html = self._print(self._card_2430([(DED, 200, "TEST-PRINT-BOLD")]))
		net_row = '<tr class="last"><td class="k">%s</td><td class="v">%s</td></tr>'
		self.assertIn(net_row % (NET, _sar(2230, self.company)), html)
		self.assertIn(".emc-net tr.last td {", frappe.db.get_value("Print Format", MONTHLY, "css"))

	def test_a_cash_row_is_not_counted_in_the_printed_totals(self):
		# an owner-paid cash row is recorded, not in the card's totals: the printed rows still add up to the net
		from card.tests.test_cash_disbursement_db import _cash_account

		cash = {
			"is_cash_disbursement": 1,
			"cash_account": _cash_account(self.company),
			"adjustment_type": DED,
			"amount": 300,
			"side": "Supplier",
			"description": "TEST-PRINT-CASH",
		}
		card = self._card_2430([(DED, 200, "TEST-PRINT-DIESEL2")], extra=[cash])
		self._assert_four_rows(card, 2430, 0, 200, 2230)
		self.assertIn(
			'TEST-PRINT-CASH <span class="emc-cash">(دفع نقدي، غير محتسب في الإجماليات)</span>',
			self._print(card),
		)

	def test_adjustment_text_is_escaped(self):
		card = self._card_with(self._equipment(RENTED), [(DED, 10, "Supplier", "<b>TEST-PRINT-ESC</b>")])
		html = self._print(card)
		self.assertIn("&lt;b&gt;TEST-PRINT-ESC&lt;/b&gt;", html)
		self.assertNotIn("<b>TEST-PRINT-ESC</b>", html)

	def test_printing_changes_no_stored_value(self):
		card = self._card_with(self._sub_rental(), [(DED, 200, "Customer", "TEST-PRINT-K")])
		fields = ["amount", "net_amount", "customer_amount", "customer_net_amount", "modified"]
		before = frappe.db.get_value("Card Monthly Card", card.name, fields, as_dict=True)
		self._print(card)
		self._print(card, LEGACY_MONTHLY)
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, fields, as_dict=True), before)

	def test_card_document_prints_use_the_chrome_pdf_generator(self):
		# wkhtmltopdf (old Qt) breaks Arabic letter joining; frappe's Chrome generator shapes it like the browser
		formats = frappe.get_all(
			"Print Format",
			filters={"module": "Card", "print_format_type": "Jinja", "custom_format": 1},
			fields=["name", "pdf_generator"],
		)
		self.assertTrue(formats)
		for pf in formats:
			with self.subTest(print_format=pf.name):
				self.assertEqual(pf.pdf_generator, "chrome")

	def test_every_card_print_template_compiles(self):
		# a Jinja syntax error only shows when the format is saved or printed: compile them all
		jenv = frappe.get_jenv()
		formats = frappe.get_all(
			"Print Format",
			filters={"module": "Card", "print_format_type": "Jinja", "custom_format": 1},
			pluck="name",
		)
		self.assertIn(MONTHLY, formats)
		self.assertIn(LEGACY_MONTHLY, formats)
		for name in formats:
			with self.subTest(print_format=name):
				jenv.parse(frappe.db.get_value("Print Format", name, "html") or "")

	def test_print_follows_the_print_language(self):
		card = self._card_with(self._equipment(RENTED), [(DED, 600, "Supplier", "TEST-PRINT-LANG")])
		html = self._print(card)
		self.assertIn('class="emc rtl" dir="rtl"', html)
		self.assertIn("كارت تشغيل معدة شهري", html)
		html = self._print(card, lang="en")
		self.assertIn('class="emc ltr" dir="ltr"', html)
		self.assertIn("Equipment Monthly Operation Card", html)
		self.assertNotIn("كارت تشغيل معدة شهري", html)
		# Urdu is right-to-left in CARD, although frappe is_rtl() lists only ar/he/fa/ps
		self.assertIn('class="emc rtl" dir="rtl"', self._print(card, lang="ur"))
		self.assertEqual(_cell(html, "Total amount"), _sar(3600, self.company))
		self.assertEqual(
			_settlement(html, "Supplier settlement (before VAT)"),
			[
				("Total before additions and deductions", _sar(3600, self.company)),
				("Total additions", _sar(0, self.company)),
				("Total deductions", _sar(600, self.company)),
				("Net after additions and deductions", _sar(3000, self.company)),
			],
		)
		self.assertIsNone(_settlement(html, "Customer settlement (before VAT)"))
		# stored Arabic option values print in the print language (card/locale/en.po)
		self.assertIn("Deduction", html)
		legacy = self._print(card, LEGACY_MONTHLY, lang="en")
		self.assertIn('dir="ltr"', legacy)
		self.assertEqual(_cell(legacy, "Total amount"), fmt_money(3600))

	def test_legacy_format_prints_the_customer_amount_on_customer_cards(self):
		card = self._card_with(self._rented_out(customer_rate=1500), [])
		html = self._print(card, LEGACY_MONTHLY)
		self.assertEqual(_cell(html, "القيمة الإجمالية"), fmt_money(7200))


class TestDieselTransportPrints(_CustomerCardsBase):
	def test_money_fields_are_not_labelled_amount(self):
		# core translates "Amount" as a quantity (كمية) in Arabic
		for doctype, label in (
			("Project Diesel Fill", "Fill amount"),
			("Equipment Transport", "Transporter cost"),
		):
			self.assertEqual(frappe.get_meta(doctype).get_label("amount"), label)

	def test_prints_render_the_amount_in_words(self):
		# variable diesel supplier policy (rolled back): the site may pin one
		frappe.db.set_single_value("Card Settings", "diesel_supplier", None)
		frappe.db.set_single_value("Card Settings", "diesel_supplier_policy", "متغير")
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
		use_fill_price(fill).insert(ignore_permissions=True)
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
		company_paid(transport).insert(ignore_permissions=True)
		currency = frappe.get_cached_value("Company", self.company, "default_currency")
		symbol = frappe.get_cached_value("Currency", currency, "symbol")
		lang = frappe.local.lang
		try:
			frappe.local.lang = "ar"
			for doc, amount in ((fill, 2000), (transport, 3500)):
				html = frappe.get_print(doc.doctype, doc.name, print_format=doc.doctype + " Print")
				words = card_amount_in_words(amount, self.company)
				self.assertIn(words, html)
				if symbol and symbol != currency:
					# the old line printed core money_in_words: the ISO code first
					self.assertNotIn(frappe.utils.money_in_words(amount, currency), html)
		finally:
			frappe.local.lang = lang

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
