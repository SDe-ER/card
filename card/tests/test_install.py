# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Tests for the install-time automation (card.install).

These cover the idempotent reconciliation helpers and the legacy-adoption
paths at the function level. The end-to-end fresh-site and legacy-config
install paths are proven as integration in the T9b rehearsal.
"""

import json
import os
from typing import ClassVar

import frappe
from frappe.tests import IntegrationTestCase

from card import install


class TestCardInstall(IntegrationTestCase):
	# ---- post-install ownership invariants ----
	def test_module_def_app_owned(self):
		self.assertEqual(frappe.db.get_value("Module Def", "Card", "app_name"), "card")
		self.assertEqual(frappe.db.get_value("Module Def", "Card", "custom"), 0)

	def test_doctypes_app_owned(self):
		for dt in install.CARD_DOCTYPES:
			self.assertEqual(frappe.db.get_value("DocType", dt, "custom"), 0, dt)
			self.assertEqual(frappe.db.get_value("DocType", dt, "module"), "Card", dt)

	# ---- adoption is correct AND idempotent (partial-failure re-run safety) ----
	def test_adopt_module_def_idempotent(self):
		# simulate the legacy custom Module Def; rolled back by the transaction
		frappe.db.set_value("Module Def", "Card", {"app_name": "frappe", "custom": 1}, update_modified=False)
		install._adopt_module_def()
		install._adopt_module_def()  # re-run (as after a mid-install failure)
		self.assertEqual(frappe.db.get_value("Module Def", "Card", "app_name"), "card")
		self.assertEqual(frappe.db.get_value("Module Def", "Card", "custom"), 0)

	def test_adopt_doctypes_idempotent(self):
		# simulate a legacy custom DocType + stray row-level print default
		frappe.db.set_value("DocType", "Card Equipment", {"custom": 1}, update_modified=False)
		frappe.db.set_value(
			"DocType",
			install.CMC_DOCTYPE,
			"default_print_format",
			install.CMC_DEFAULT_PRINT_FORMAT,
			update_modified=False,
		)
		install._adopt_doctypes()
		install._adopt_doctypes()  # re-run
		self.assertEqual(frappe.db.get_value("DocType", "Card Equipment", "custom"), 0)
		self.assertEqual(frappe.db.get_value("DocType", "Card Equipment", "module"), "Card")
		# stray row-level default_print_format cleared (moved to the Property Setter)
		self.assertFalse(frappe.db.get_value("DocType", install.CMC_DOCTYPE, "default_print_format"))

	def test_reconcile_idempotent_full(self):
		# the full post-install reconciliation re-run must be a no-op (same final state)
		install._reconcile()
		install._reconcile()
		self.assertEqual(frappe.db.count("Desktop Icon", {"label": install.DESK_ICON_LABEL}), 1)
		self.assertEqual(
			frappe.db.count(
				"Property Setter",
				{
					"doc_type": install.CMC_DOCTYPE,
					"doctype_or_field": "DocType",
					"property": "default_print_format",
				},
			),
			1,
		)

	# ---- idempotent reconciliation helpers ----
	def test_disable_legacy_scripts_idempotent(self):
		install.disable_legacy_scripts()
		install.disable_legacy_scripts()
		for name in install.LEGACY_SERVER_SCRIPTS:
			if frappe.db.exists("Server Script", name):
				self.assertEqual(frappe.db.get_value("Server Script", name, "disabled"), 1, name)
		for name in install.LEGACY_CLIENT_SCRIPTS:
			if frappe.db.exists("Client Script", name):
				self.assertEqual(frappe.db.get_value("Client Script", name, "enabled"), 0, name)

	def test_print_default_property_setter_idempotent(self):
		install._ensure_print_default_property_setter()
		install._ensure_print_default_property_setter()
		rows = frappe.get_all(
			"Property Setter",
			filters={
				"doc_type": install.CMC_DOCTYPE,
				"doctype_or_field": "DocType",
				"property": "default_print_format",
			},
			pluck="name",
		)
		self.assertEqual(len(rows), 1)
		frappe.clear_cache(doctype=install.CMC_DOCTYPE)
		self.assertEqual(
			frappe.get_meta(install.CMC_DOCTYPE).default_print_format, install.CMC_DEFAULT_PRINT_FORMAT
		)

	# ---- Desk launcher: exactly one, idempotent ----
	def test_desk_icon_single_and_idempotent(self):
		install._ensure_card_desk_icon()
		install._ensure_card_desk_icon()
		icons = frappe.get_all(
			"Desktop Icon",
			filters={"label": install.DESK_ICON_LABEL},
			fields=["name", "standard", "app", "logo_url", "icon_type", "link_type", "link_to"],
		)
		self.assertEqual(len(icons), 1)
		icon = icons[0]
		self.assertEqual(icon.standard, 1)
		self.assertEqual(icon.app, install.APP_NAME)
		self.assertEqual(icon.logo_url, install.CARD_LOGO_URL)
		self.assertEqual(icon.link_to, install.MODULE)

	def test_desk_icon_adopts_legacy_standard_zero(self):
		# Simulate the production case: a legacy standard=0, Administrator-owned
		# "Card" Desktop Icon with no logo. Rolled back by the test transaction.
		# Use a raw DB delete (not frappe.delete_doc): in developer mode deleting
		# a standard Desktop Icon doc also removes the app's shipped export file.
		if frappe.db.exists("Desktop Icon", install.DESK_ICON_LABEL):
			frappe.db.delete("Desktop Icon", {"name": install.DESK_ICON_LABEL})
		legacy = frappe.new_doc("Desktop Icon")
		legacy.label = install.DESK_ICON_LABEL
		legacy.standard = 0
		legacy.icon_type = "Link"
		legacy.link_type = "Workspace Sidebar"
		legacy.link_to = install.MODULE
		legacy.flags.ignore_links = True
		legacy.flags.ignore_mandatory = True
		legacy.insert(ignore_permissions=True)

		install._ensure_card_desk_icon()

		icons = frappe.get_all(
			"Desktop Icon",
			filters={"label": install.DESK_ICON_LABEL},
			fields=["name", "standard", "app", "logo_url"],
		)
		self.assertEqual(len(icons), 1)  # never two
		self.assertEqual(icons[0].standard, 1)
		self.assertEqual(icons[0].app, install.APP_NAME)
		self.assertEqual(icons[0].logo_url, install.CARD_LOGO_URL)

	# ---- guard: app-owned records relied on at runtime have a backing file ----
	def test_app_backing_files_present(self):
		"""Every app-owned record that must survive migrate's orphan-prune /
		fixture sync has its backing file shipped in the app. The Desk icon
		bug (a standard=1 Desktop Icon with no backing card/desktop_icon file
		was pruned) is what this guards against."""
		rel = [
			# app-level entity pruned by remove_orphan_entities if unbacked
			("desktop_icon", "card.json"),
			# the logo the icon/launcher point at
			("public", "images", "card-logo.svg"),
			# fixtures (Workspace, Sidebar, Number Cards, Chart, Print Format)
			("fixtures", "workspace.json"),
			("fixtures", "workspace_sidebar.json"),
			("fixtures", "number_card.json"),
			("fixtures", "dashboard_chart.json"),
			("fixtures", "print_format.json"),
			# standard Script Reports (module-file backed)
			("card", "report", "equipment_suppliers_summary", "equipment_suppliers_summary.json"),
			("card", "report", "equipment_supplier_statement", "equipment_supplier_statement.json"),
		]
		missing = [
			os.path.join(*parts) for parts in rel if not os.path.exists(frappe.get_app_path("card", *parts))
		]
		self.assertEqual(missing, [], "missing app backing files: %s" % missing)


class TestCardDeskLayoutAppend(IntegrationTestCase):
	"""Append-only injection of the Card launcher into existing per-user
	Desktop Layouts (option B). All records roll back with the transaction."""

	# a non-Card grid that predates the Card launcher
	BASE_GRID: ClassVar = [
		{
			"name": "System",
			"label": "System",
			"link_to": "System",
			"icon_type": "Link",
			"idx": 0,
			"standard": 1,
		},
		{"name": "Users", "label": "Users", "link_to": "Users", "icon_type": "Link", "idx": 1, "standard": 1},
	]

	def setUp(self):
		install._ensure_card_desk_icon()  # guarantee the Card icon template exists
		self.token = frappe.generate_hash(length=8)

	def _make_user(self, system_manager=True):
		u = frappe.new_doc("User")
		u.email = "card-test-%s@example.com" % self.token
		u.first_name = "Card Test"
		u.send_welcome_email = 0
		if system_manager:
			u.append("roles", {"role": "System Manager"})
		u.flags.ignore_permissions = True
		u.insert(ignore_permissions=True)
		return u.name

	def _make_layout(self, user, grid):
		dl = frappe.new_doc("Desktop Layout")
		dl.user = user
		dl.layout = json.dumps(grid)
		dl.flags.ignore_permissions = True
		dl.insert(ignore_permissions=True)
		return dl.name

	def _grid(self, user):
		return json.loads(frappe.db.get_value("Desktop Layout", user, "layout"))

	def test_append_for_entitled_user(self):
		user = self._make_user(system_manager=True)
		self._make_layout(user, self.BASE_GRID)

		self.assertEqual(install._append_card_to_user_layouts().count(user), 1)

		grid = self._grid(user)
		# existing entries untouched, same order
		self.assertEqual([g["name"] for g in grid[:2]], ["System", "Users"])
		# Card appended at the very end, exactly once, with the launcher shape
		card = [g for g in grid if install._is_card_layout_entry(g)]
		self.assertEqual(len(card), 1)
		self.assertEqual(grid[-1]["name"], install.MODULE)
		self.assertEqual(grid[-1]["link_to"], install.MODULE)
		self.assertEqual(grid[-1]["logo_url"], install.CARD_LOGO_URL)
		self.assertEqual(grid[-1]["app"], install.APP_NAME)
		self.assertEqual(grid[-1]["idx"], 2)

	def test_idempotent_and_no_reorder(self):
		user = self._make_user(system_manager=True)
		self._make_layout(user, self.BASE_GRID)

		install._append_card_to_user_layouts()
		# second run must not re-append and must report nothing for this user
		self.assertEqual(install._append_card_to_user_layouts().count(user), 0)

		grid = self._grid(user)
		self.assertEqual(len([g for g in grid if install._is_card_layout_entry(g)]), 1)
		self.assertEqual([g["name"] for g in grid], ["System", "Users", install.MODULE])

	def test_existing_legacy_card_logo_backfilled_only(self):
		# production case: a legacy Card entry already present, WITHOUT the logo.
		user = self._make_user(system_manager=True)
		grid = [
			*self.BASE_GRID,
			{
				"name": "Card",
				"label": "Card",
				"link_to": "Card",
				"icon_type": "Link",
				"idx": 2,
				"standard": 0,
				"logo_url": None,
			},
		]
		self._make_layout(user, grid)

		# reconcile backfills ONLY the Card entry's logo (reported as updated)
		self.assertEqual(install._append_card_to_user_layouts().count(user), 1)
		after = self._grid(user)
		self.assertEqual(len(after), 3)  # nothing appended, nothing removed
		self.assertEqual([g["name"] for g in after], ["System", "Users", "Card"])  # no reorder
		card = [g for g in after if install._is_card_layout_entry(g)]
		self.assertEqual(len(card), 1)  # never duplicated
		self.assertEqual(card[0]["logo_url"], install.CARD_LOGO_URL)  # logo backfilled
		self.assertEqual(card[0]["standard"], 0)  # other fields of the entry untouched
		# the two non-Card entries are byte-for-byte unchanged
		self.assertEqual(after[0], self.BASE_GRID[0])
		self.assertEqual(after[1], self.BASE_GRID[1])

		# idempotent: second run makes no change
		self.assertEqual(install._append_card_to_user_layouts().count(user), 0)

	def test_existing_card_with_logo_untouched(self):
		user = self._make_user(system_manager=True)
		grid = [
			*self.BASE_GRID,
			{
				"name": "Card",
				"label": "Card",
				"link_to": "Card",
				"icon_type": "Link",
				"idx": 2,
				"standard": 1,
				"logo_url": install.CARD_LOGO_URL,
			},
		]
		self._make_layout(user, grid)
		self.assertEqual(install._append_card_to_user_layouts().count(user), 0)  # nothing to do
		after = self._grid(user)
		self.assertEqual(len(after), 3)
		self.assertEqual(len([g for g in after if install._is_card_layout_entry(g)]), 1)

	def test_not_appended_for_unentitled_user(self):
		user = self._make_user(system_manager=False)  # no System Manager role
		self._make_layout(user, self.BASE_GRID)

		self.assertEqual(install._append_card_to_user_layouts().count(user), 0)
		grid = self._grid(user)
		self.assertEqual(len([g for g in grid if install._is_card_layout_entry(g)]), 0)
