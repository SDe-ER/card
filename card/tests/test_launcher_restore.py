# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.1.2: a Dock layer saved before the launcher shipped hid nine of its ten entries
(production showed only the Card dashboard). card.navigation.restore_launcher_entries (after
migrate) appends the missing entries to such a layer and leaves newer layers and existing rows
alone. The tests use their own user's layer, so no existing layer is touched; rolled back."""

import frappe
from frappe.tests import IntegrationTestCase

from card import navigation
from card.tests.test_v3_navigation import _load


def _shipped_keys():
	return [navigation._key(row) for row in _load("dock", "card", "card.json")["items"]]


class TestLauncherRestore(IntegrationTestCase):
	def setUp(self):
		self.user = f"dock-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{"doctype": "User", "email": self.user, "first_name": "Dock Restore", "send_welcome_email": 0}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _layer(self, rows, modified="2026-10-13 17:05:25"):
		layer = frappe.get_doc(
			{"doctype": "Dock", "app": "card", "user": self.user, "standard": 0, "items": rows}
		)
		layer.insert(ignore_permissions=True)
		frappe.db.set_value("Dock", layer.name, "modified", modified, update_modified=False)
		return layer.name

	def _keys(self, name):
		return [navigation._key(row) for row in frappe.get_doc("Dock", name).items]

	def test_old_layer_gets_every_shipped_entry_in_order(self):
		name = self._layer([{"link_type": "Sidebar", "link_to": "Card", "added": 0}])
		navigation.restore_launcher_entries()
		self.assertEqual(self._keys(name), _shipped_keys())
		frappe.set_user(self.user)
		resolve = frappe.get_attr("frappe.desk.doctype.dock.dock.resolve_app_dock")
		self.assertEqual([navigation._key(entry) for entry in resolve("card", gated=False)], _shipped_keys())

	def test_production_layer_shape(self):
		# production site layer (read-only check 2026-10-25): one added row "Card (Custom)"
		name = self._layer(
			[
				{
					"link_type": "Sidebar",
					"link_to": "Card",
					"title": "Card (Custom)",
					"icon": "clipboard",
					"added": 1,
					"hidden": 0,
				}
			]
		)
		navigation.restore_launcher_entries()
		frappe.set_user(self.user)
		resolve = frappe.get_attr("frappe.desk.doctype.dock.dock.resolve_app_dock")
		rail = resolve("card", gated=False)
		self.assertEqual([navigation._key(entry) for entry in rail], _shipped_keys())
		self.assertEqual((rail[0]["title"], rail[0]["icon"]), ("Card (Custom)", "clipboard"))
		frappe.set_user("Administrator")
		before = self._keys(name)
		navigation.restore_launcher_entries()
		self.assertEqual(self._keys(name), before)

	def test_existing_rows_and_hidden_flags_are_kept(self):
		name = self._layer(
			[
				{"link_type": "Sidebar", "link_to": "Card Reports", "added": 0, "hidden": 1},
				{"link_type": "Sidebar", "link_to": "Card", "added": 0},
			]
		)
		navigation.restore_launcher_entries()
		rows = frappe.get_doc("Dock", name).items
		self.assertEqual((rows[0].link_to, rows[0].hidden), ("Card Reports", 1))
		self.assertEqual(rows[1].link_to, "Card")
		self.assertEqual(sorted(self._keys(name)), sorted(_shipped_keys()))

	def test_layer_saved_after_the_launcher_is_untouched(self):
		name = self._layer([{"link_type": "Sidebar", "link_to": "Card", "added": 0}], "2026-10-20 10:00:00")
		navigation.restore_launcher_entries()
		self.assertEqual(self._keys(name), ["Sidebar|Card|"])

	def test_second_run_changes_nothing(self):
		name = self._layer([{"link_type": "Sidebar", "link_to": "Card", "added": 0}])
		navigation.restore_launcher_entries()
		before = self._keys(name)
		navigation.restore_launcher_entries()
		self.assertEqual(self._keys(name), before)
