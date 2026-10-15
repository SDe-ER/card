# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import json
import unittest
from pathlib import Path


class TestNumberCards(unittest.TestCase):
	def test_all_number_cards_show_full_number(self):
		fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "number_card.json"
		with open(fixture_path, encoding="utf-8") as f:
			cards = json.load(f)

		self.assertTrue(len(cards) > 0, "number_card.json is empty")
		for card in cards:
			label = card.get("label") or card.get("name") or "<unknown>"
			self.assertEqual(
				card.get("show_full_number"),
				1,
				f"Number Card '{label}' must have show_full_number == 1",
			)


if __name__ == "__main__":
	unittest.main()
