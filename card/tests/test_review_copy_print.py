# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Review copy print for unapproved Card Monthly Cards (FR-167).

An unapproved card (docstatus 0, any workflow state before approval) prints one review banner, a meta line
(workflow state, printed by, printed at) and a light watermark that the print engine repeats on every page.
A submitted card prints as before: no banner, no watermark. The generic Frappe draft heading is not used by
this format. Money follows card_print_can_view_money() exactly as before (FR-162). Proven on the real print
engine (frappe.get_print) with the standard format "Card Monthly Card Print". All data is per-test and rolled back.
"""

import glob
import os
import re
from unittest import mock

import frappe

from card.constants import DIR_RENTED_OUT, OWNED
from card.tests.cancel_reason import with_reason
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
		# the labels asserted here are the English ones: pin the print language, as test_print_formats does
		previous = frappe.local.lang
		try:
			frappe.local.lang = "en"
			return frappe.get_print("Card Monthly Card", card.name, print_format=PRINT_FORMAT)
		finally:
			frappe.local.lang = previous

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
		# the meta line shows the stored workflow state, or "Not yet approved" when none is set
		state = card.get("workflow_state") or "Not yet approved"
		self.assertIn(f"Workflow state: {state}", html)

	def test_pending_review_state_keeps_the_banner_and_watermark(self):
		# a card sent for review is still unapproved: the banner keys on docstatus, not on the workflow state name
		card = self._rented_card()
		card.db_set("workflow_state", "Pending Review", update_modified=False)
		html = self._html(card)
		self.assertIn("Pending Review", html)
		self.assertIn(BANNER, html)
		self.assertIn(WATERMARK, html)

	def test_every_review_copy_msgid_is_translated_in_every_locale(self):
		entries = [
			(None, "Review Copy — Not Approved"),
			(None, "REVIEW COPY"),
			("Card Review Copy", "Workflow state"),
			("Card Review Copy", "Not yet approved"),
			("Card Review Copy", "Printed by"),
			("Card Review Copy", "Printed at"),
		]
		locale_dir = os.path.join(frappe.get_app_path("card"), "locale")
		for path in glob.glob(os.path.join(locale_dir, "*.po")):
			with open(path, encoding="utf-8") as fh:
				text = fh.read()
			for ctx, msgid in entries:
				prefix = f'msgctxt "{ctx}"\n' if ctx else ""
				match = re.search(prefix + 'msgid "' + re.escape(msgid) + '"\nmsgstr "([^"]+)"', text)
				self.assertTrue(
					match and match.group(1).strip(),
					f"{os.path.basename(path)}: no translation for {msgid!r}",
				)

	def test_draft_has_one_label_and_no_generic_draft_heading(self):
		card = self._rented_card()
		html = self._html(card)
		self.assertNotIn("(Draft)", html)
		self.assertEqual(html.count(BANNER), 1)

	def test_submitted_card_prints_without_banner_or_watermark(self):
		card = self._rented_card(submit=True)
		self.assertEqual(card.docstatus, 1)
		html = self._html(card)
		self.assertNotIn(BANNER, html)
		self.assertNotIn(WATERMARK, html)
		self.assertNotIn('class="emc-review"', html)  # the stylesheet names the class too: check the markup
		self.assertNotIn("Printed by", html)

	def test_draft_still_prints_days_hours_and_totals(self):
		card = self._rented_card()
		html = self._html(card)
		self.assertIn("Total operating hours", html)
		self.assertIn("Working days", html)
		self.assertIn("16.0", html)  # two working days x 8 hours

	def test_cancelled_card_prints_cancelled_label_and_no_review_copy(self):
		card = self._rented_card(submit=True)
		with_reason(card).cancel()
		card.reload()
		self.assertEqual(card.docstatus, 2)
		# Frappe refuses to print a cancelled document unless Print Settings allow it; allowed only inside this test transaction
		frappe.db.set_single_value("Print Settings", "allow_print_for_cancelled", 1)
		html = self._html(card)
		self.assertIn("(Cancelled)", html)
		self.assertNotIn(BANNER, html)
		self.assertNotIn(WATERMARK, html)

	def test_money_rows_for_a_money_reader_are_unchanged(self):
		# Administrator reads money: the draft print keeps the amount row exactly as before
		card = self._rented_card()
		self.assertIn(MONEY_ROW, self._html(card))

	def test_money_rows_hidden_when_the_money_gate_is_closed(self):
		# the format's own money guard (card_print_can_view_money -> can_view_money) decides the amount rows: with the
		# gate closed the draft print has no amount row and keeps the banner. Patched in place of a real no-money
		# printing role, because no role in the permission matrix can print a card without level-1 read.
		card = self._rented_card()
		with mock.patch("card.field_privacy.can_view_money", return_value=False):
			html = self._html(card)
		self.assertNotIn(MONEY_ROW, html)
		self.assertIn(BANNER, html)

	def test_card_user_draft_print_shows_the_money_row(self):
		# Card User has print and level-1 read on Card Monthly Card: the review copy shows the amount row, as before
		card = self._rented_card()
		user = _user(["Card User"])
		self.addCleanup(frappe.delete_doc, "User", user, ignore_permissions=True, force=True)
		frappe.set_user(user)
		html = self._html(card)
		self.assertIn(MONEY_ROW, html)
		self.assertIn(BANNER, html)

	def test_card_operator_cannot_print_a_card(self):
		# Card Operator has no print right on Card Monthly Card (existing rule, not changed here)
		card = self._rented_card()
		operator = _user(["Card Operator"])
		self.addCleanup(frappe.delete_doc, "User", operator, ignore_permissions=True, force=True)
		frappe.set_user(operator)
		with self.assertRaises(frappe.PermissionError):
			self._html(card)
