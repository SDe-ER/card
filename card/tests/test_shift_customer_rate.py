# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-109 (Owner 2026-11-08): one machine rented to a customer with a different
monthly price per shift (e.g. day 50,000 / night 40,000, 26 days x 10 h). The
equipment keeps the customer rate (day shift) and an optional night-shift rate
on the same basis; a night card mirrors the night rate, a day card the customer
rate, and an equipment without a night rate keeps the previous behaviour."""

import frappe
from frappe.utils import flt

from card.constants import DIR_RENTED_OUT, DIR_SUBRENTAL, SHIFT_DAY, SHIFT_NIGHT
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase


class TestShiftCustomerRate(_CustomerCardsBase):
	def _monthly(self, night=None):
		kw = {"customer_rate_type": "بالشهر"}
		if night is not None:
			kw["customer_rate_night"] = night
		return self._rented_out(customer_rate=52000, **kw)

	def test_night_card_uses_night_rate(self):
		eq = self._monthly(night=41600)
		card = self._card(eq, [10, 10], submit=True, shift=SHIFT_NIGHT)
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertEqual(flt(card.customer_rate), 41600.0)
		# 41,600 / 260 standard month hours = 160/h; 20 h
		self.assertEqual(flt(card.customer_rate_used), 160.0)
		self.assertEqual(flt(card.customer_amount), 3200.0)

	def test_day_card_keeps_customer_rate(self):
		eq = self._monthly(night=41600)
		card = self._card(eq, [10, 10], submit=True, shift=SHIFT_DAY)
		self.assertEqual(flt(card.customer_rate), 52000.0)
		self.assertEqual(flt(card.customer_rate_used), 200.0)  # 52,000 / 260
		self.assertEqual(flt(card.customer_amount), 4000.0)

	def test_no_night_rate_falls_back_to_customer_rate(self):
		for night in (None, 0):
			eq = self._monthly(night=night)
			card = self._card(eq, [10], shift=SHIFT_NIGHT)
			self.assertEqual(flt(card.customer_rate), 52000.0)
			self.assertEqual(flt(card.customer_amount), 2000.0)

	def test_draft_follows_shift_change_and_submitted_is_frozen(self):
		eq = self._monthly(night=41600)
		card = self._card(eq, [10], shift=SHIFT_DAY)
		self.assertEqual(flt(card.customer_amount), 2000.0)
		card.shift = SHIFT_NIGHT
		card.save(ignore_permissions=True)
		card.reload()
		self.assertEqual(flt(card.customer_rate), 41600.0)
		self.assertEqual(flt(card.customer_amount), 1600.0)
		card.submit()
		card.reload()
		self.assertEqual(flt(card.customer_rate_used), 160.0)
		draft = frappe.new_doc("Card Monthly Card")  # same equipment, October night card
		draft.update({"equipment": eq.name, "project": self.project, "shift": SHIFT_NIGHT})
		draft.update({"month": "10", "year": 2026})
		for row in _days([10], month=10):
			draft.append("days", row)
		draft.insert(ignore_permissions=True)

		# the night rate changes through the equipment form (commercial reason required)
		eq.reload()
		eq.customer_rate_night = 26000
		eq.commercial_change_reason = "night rate revised " + self.token
		eq.save(ignore_permissions=True)

		card.reload()  # submitted: stored values never change
		self.assertEqual(flt(card.customer_rate), 41600.0)
		self.assertEqual(flt(card.customer_amount), 1600.0)
		self.assertEqual(flt(card.customer_rate_used), 160.0)
		draft.reload()  # draft: re-mirrored on its next save
		draft.save(ignore_permissions=True)
		draft.reload()
		self.assertEqual(flt(draft.customer_rate), 26000.0)
		self.assertEqual(flt(draft.customer_amount), 1000.0)  # 26,000 / 260 x 10 h

	def test_sub_rental_night_card_changes_customer_side_only(self):
		eq = self._sub_rental(customer_rate=1200, customer_rate_night=900)
		day = self._card(eq, [10], submit=True, shift=SHIFT_DAY)
		night = self._card(eq, [10], submit=True, shift=SHIFT_NIGHT)
		self.assertEqual(night.card_direction, DIR_SUBRENTAL)
		self.assertEqual(flt(night.customer_rate), 900.0)
		self.assertEqual(flt(night.customer_amount), 900.0)  # 900/day over 10 h x 10 h
		self.assertEqual(flt(day.customer_amount), 1200.0)
		# supplier side identical on both shifts (750/day over 10 h)
		for card in (day, night):
			self.assertEqual(flt(card.rate), 750.0)
			self.assertEqual(flt(card.amount), 750.0)
			self.assertEqual(flt(card.hourly_rate_used), 75.0)

	def test_night_rate_ignored_without_customer_billing(self):
		eq = self._equipment()  # rented in, supplier side only
		frappe.db.set_value("Card Equipment", eq.name, "customer_rate_night", 41600)
		card = self._card(eq, [10], shift=SHIFT_NIGHT)
		self.assertFalse(card.customer)
		self.assertEqual(flt(card.customer_rate), 0)
		self.assertEqual(flt(card.customer_amount), 0)

	def test_negative_night_rate_refused(self):
		eq = self._monthly()
		eq.customer_rate_night = -1
		with self.assertRaises(frappe.ValidationError):
			eq.save(ignore_permissions=True)

	def test_night_rate_is_a_commercial_field(self):
		from card.card.doctype.card_equipment.card_equipment import COMMERCIAL_FIELDS

		self.assertIn("customer_rate_night", COMMERCIAL_FIELDS)
