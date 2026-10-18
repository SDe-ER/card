# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import json
import unittest
from pathlib import Path

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "number_card.json"


def _cards():
	with open(FIXTURE_PATH, encoding="utf-8") as f:
		return json.load(f)


class TestNumberCards(unittest.TestCase):
	def test_all_number_cards_show_full_number(self):
		cards = _cards()
		self.assertTrue(len(cards) > 0, "number_card.json is empty")
		for card in cards:
			label = card.get("label") or card.get("name") or "<unknown>"
			self.assertEqual(
				card.get("show_full_number"),
				1,
				f"Number Card '{label}' must have show_full_number == 1",
			)

	def test_no_number_card_pins_a_currency(self):
		# Frappe v16 formats any value as money in the card's currency when one is
		# set: counts and diesel litres rendered as SAR, and non-SAR companies saw
		# SAR (issue #15). Unset, the aggregated field's own type drives the format.
		for card in _cards():
			label = card.get("label") or card.get("name") or "<unknown>"
			self.assertFalse(card.get("currency"), f"Number Card '{label}' must not pin a currency")


if __name__ == "__main__":
	unittest.main()
