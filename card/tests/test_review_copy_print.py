# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Review copy print for unapproved Card Monthly Cards (FR-167).

An unapproved card (docstatus 0, any workflow state before approval) prints one review banner, a meta line
(workflow state, printed by, printed at) and a light watermark that the print engine repeats on every page.
A submitted card prints as before: no banner, no watermark. The generic Frappe draft heading is not used by
this format. Money follows card_print_can_view_money() exactly as before (FR-162). Proven on the real print
engine (frappe.get_print) with the standard format "Card Monthly Card Print". All data is per-test and rolled back.
"""

import frappe

from card.constants import DIR_RENTED_OUT, OWNED
from card.tests.test_card_money_privacy import _user
from card.tests.test_stop_reasons import WORK, _StopBase

PRINT_FORMAT = "Card Monthly Card Print"
BANNER = "Review Copy — Not Approved"
WATERMARK = "REVIEW COPY"
MONEY_ROW = "Total amount"


class TestReviewCopyPrint(_StopBase):
	def _rented_card(self, submit=False, ym=("09", 2026)):
		eq = self._equipment(
			OWNED,
			direction=DIR_RENTED_OUT,
			customer=self.customer,
			customer_rate=2500,
			customer_rate_type="باليوم",
		)
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = ym[0]
		c.year = ym[1]
		for i in range(1, 3):
			c.append(
				"days",
				{
					"operation_date": "%s-%s-%02d" % (ym[1], ym[0], i),
					"day_status": WORK,
					"working_hours": 8,
				},
			)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _html(self, card):
		return frappe.get_print("Card Monthly Card", card.name, print_format=PRINT_FORMAT)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_draft_prints_banner_watermark_and_meta(self):
		card = self._rented_card()
		self.assertEqual(card.docstatus, 0)
		html = self._html(card)
		self.assertIn(BANNER, html)
		self.assertIn(WATERMARK, html)
		self.assertIn("emc-review-wm", html)  # the watermark is fixed to the page, repeated on every page
		self.assertIn("Printed by", html)
		self.assertIn("Printed at", html)
		self.assertIn(
			"Not yet approved", html
		)  # no workflow on this site: the state reads as not yet approved

	def test_draft_has_one_label_and_no_generic_draft_heading(self):
		card = self._rented_card()
		html = self._html(card)
		self.assertNotIn('document-status="draft"', html)
		self.assertNotIn("(Draft)", html)
		self.assertEqual(html.count(BANNER), 1)

	def test_submitted_card_prints_without_banner_or_watermark(self):
		card = self._rented_card(submit=True)
		self.assertEqual(card.docstatus, 1)
		html = self._html(card)
		self.assertNotIn(BANNER, html)
		self.assertNotIn(WATERMARK, html)
		self.assertNotIn("emc-review", html)
		self.assertNotIn("Printed by", html)

	def test_draft_still_prints_days_hours_and_totals(self):
		card = self._rented_card()
		html = self._html(card)
		self.assertIn("Total operating hours", html)
		self.assertIn("Working days", html)
		self.assertIn("16.0", html)  # two working days x 8 hours

	def test_money_rows_for_a_money_reader_are_unchanged(self):
		# Administrator reads money: the draft print keeps the amount row exactly as before
		card = self._rented_card()
		self.assertIn(MONEY_ROW, self._html(card))

	def test_money_rows_hidden_from_a_card_operator_on_a_draft(self):
		# the review banner adds no money: a Card Operator's draft print still has no amount row
		card = self._rented_card()
		operator = _user(["Card Operator"])
		self.addCleanup(frappe.delete_doc, "User", operator, ignore_permissions=True, force=True)
		frappe.set_user(operator)
		html = self._html(card)
		self.assertNotIn(MONEY_ROW, html)
		self.assertIn(BANNER, html)
