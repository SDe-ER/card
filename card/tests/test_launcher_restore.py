# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.1.2: a site Dock layer saved before the launcher shipped hid nine of its ten entries
(production showed only the Card dashboard). The patch appends the missing entries to such a
layer and leaves newer layers and existing rows alone."""

import frappe
from frappe.tests import IntegrationTestCase

from card.patches.v4_1_2 import restore_launcher_entries as patch
from card.tests.test_v3_navigation import _load


def _shipped_keys():
	return [patch._key(row) for row in _load("dock", "card", "card.json")["items"]]


class TestLauncherRestore(IntegrationTestCase):
	def setUp(self):
		for name in frappe.get_all("Dock", filters={"app": "card", "standard": 0}, pluck="name"):
			frappe.delete_doc("Dock", name, force=True)

	def _layer(self, rows, modified="2026-10-13 17:05:25"):
		layer = frappe.get_doc({"doctype": "Dock", "app": "card", "user": "", "standard": 0, "items": rows})
		layer.insert()
		frappe.db.set_value("Dock", layer.name, "modified", modified, update_modified=False)
		return layer.name

	def _keys(self, name):
		return [patch._key(row) for row in frappe.get_doc("Dock", name).items]

	def test_old_site_layer_gets_every_shipped_entry_in_order(self):
		name = self._layer([{"link_type": "Sidebar", "link_to": "Card", "added": 0}])
		patch.execute()
		self.assertEqual(self._keys(name), _shipped_keys())
		resolved = frappe.get_attr("frappe.desk.doctype.dock.dock.resolve_app_dock")("card", gated=False)
		self.assertEqual([patch._key(entry) for entry in resolved], _shipped_keys())

	def test_existing_rows_and_hidden_flags_are_kept(self):
		name = self._layer(
			[
				{"link_type": "Sidebar", "link_to": "Card Reports", "added": 0, "hidden": 1},
				{"link_type": "Sidebar", "link_to": "Card", "added": 0},
			]
		)
		patch.execute()
		rows = frappe.get_doc("Dock", name).items
		self.assertEqual((rows[0].link_to, rows[0].hidden), ("Card Reports", 1))
		self.assertEqual(rows[1].link_to, "Card")
		self.assertEqual(sorted(self._keys(name)), sorted(_shipped_keys()))

	def test_layer_saved_after_the_launcher_is_untouched(self):
		name = self._layer([{"link_type": "Sidebar", "link_to": "Card", "added": 0}], "2026-10-20 10:00:00")
		patch.execute()
		self.assertEqual(self._keys(name), ["Sidebar|Card|"])

	def test_second_run_changes_nothing(self):
		name = self._layer([{"link_type": "Sidebar", "link_to": "Card", "added": 0}])
		patch.execute()
		before = self._keys(name)
		patch.execute()
		self.assertEqual(self._keys(name), before)
