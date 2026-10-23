# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v3.0.0 launcher: the app ships one Dock (card/dock/card) whose rows open Sidebar shells
of the Card module (card/card/sidebar/*). Every row must resolve to a real shell and every
shell row to a real DocType or Report, otherwise the launcher shows a dead icon."""

import json
import os

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime

EXPECTED_DOCK_TITLES = [
	"Card Dashboard",
	"Card Fleet",
	"Card Movement",
	"Card Operating Units",
	"Card Operation Cards",
	"Card Expenses",
	"Card Materials",  # v4.0.0
	"Card Parties",
	"Card Reports",
	"Card Setup",
]


def _load(*parts):
	with open(os.path.join(frappe.get_app_path("card"), *parts), encoding="utf-8") as f:
		return json.load(f)


class TestCardLauncher(IntegrationTestCase):
	def test_dock_rows_in_launcher_order(self):
		dock = _load("dock", "card", "card.json")
		self.assertEqual(dock["name"], "card")
		self.assertEqual([row["title"] for row in dock["items"]], EXPECTED_DOCK_TITLES)
		for row in dock["items"]:
			self.assertEqual(row["link_type"], "Sidebar")

	def test_dock_rows_open_existing_shells(self):
		dock = _load("dock", "card", "card.json")
		for row in dock["items"]:
			self.assertTrue(
				frappe.db.exists("Sidebar", {"name": row["link_to"], "module": "Card"}),
				f"dock row {row['title']!r} opens missing shell {row['link_to']!r}",
			)

	def test_shell_items_point_to_existing_targets(self):
		sidebar_dir = os.path.join(frappe.get_app_path("card"), "card", "sidebar")
		shells = sorted(os.listdir(sidebar_dir))
		self.assertEqual(len(shells), 9)
		for slug in shells:
			doc = _load("card", "sidebar", slug, f"{slug}.json")
			self.assertEqual((doc["module"], doc["app"], doc["standard"]), ("Card", "card", 1))
			self.assertEqual(doc["name"], doc["title"])
			self.assertTrue(doc["items"], f"{slug}: empty shell would fall back to computed rows")
			for item in doc["items"]:
				self.assertTrue(
					frappe.db.exists(item["link_type"], item["link_to"]),
					f"{slug}: {item['link_type']} {item['link_to']!r} does not exist",
				)

	def test_rows_match_shipped_files(self):
		# a re-migrate must replace rows, never append them
		dock = _load("dock", "card", "card.json")
		self.assertEqual(frappe.db.count("Dock Item", {"parent": "card"}), len(dock["items"]))
		sidebar_dir = os.path.join(frappe.get_app_path("card"), "card", "sidebar")
		for slug in os.listdir(sidebar_dir):
			doc = _load("card", "sidebar", slug, f"{slug}.json")
			message = f"{slug}: stored rows differ from the shipped file"
			stored = frappe.db.get_value("Sidebar", doc["name"], "modified")
			if stored and get_datetime(doc["modified"]) <= get_datetime(stored):
				# migrate imports a standard sidebar only when the file is newer (FR-077 follow-up)
				message += "; the file's 'modified' is not newer than the stored sidebar: bump it"
			self.assertEqual(
				frappe.db.count("Sidebar Item", {"parent": doc["name"], "parenttype": "Sidebar"}),
				len(doc["items"]),
				message,
			)
