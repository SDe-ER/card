# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see license.txt
"""Tests for the install-time automation (card.install).

These cover the idempotent reconciliation helpers and the legacy-adoption
paths at the function level. The end-to-end fresh-site and legacy-config
install paths are proven as integration in the T9b rehearsal.
"""

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
			filters={"doc_type": install.CMC_DOCTYPE, "doctype_or_field": "DocType", "property": "default_print_format"},
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
			"Desktop Icon", filters={"label": install.DESK_ICON_LABEL},
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
		if frappe.db.exists("Desktop Icon", install.DESK_ICON_LABEL):
			frappe.delete_doc("Desktop Icon", install.DESK_ICON_LABEL, force=1, ignore_permissions=True)
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
			"Desktop Icon", filters={"label": install.DESK_ICON_LABEL},
			fields=["name", "standard", "app", "logo_url"],
		)
		self.assertEqual(len(icons), 1)  # never two
		self.assertEqual(icons[0].standard, 1)
		self.assertEqual(icons[0].app, install.APP_NAME)
		self.assertEqual(icons[0].logo_url, install.CARD_LOGO_URL)
