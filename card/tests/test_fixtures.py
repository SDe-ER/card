# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see LICENSE
"""Guards on the shipped fixtures and the legacy-module retirement.

frappe 16.51 made ``Workspace.module`` mandatory: a fixture doc with an empty or
missing module passes silently on older frappe but fails ``sync_fixtures`` on
16.51+ with ``MandatoryError``. These tests assert every fixture doc that carries
a ``module`` names a real Module Def owned by this app (the invariant that would
have caught the incident), and that the legacy ``Card (Custom)`` retirement is
idempotent.
"""

import json
import os
from typing import ClassVar
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card import install
from card.patches.v1_0_1 import fold_sidebar_and_retire_legacy_module as fold_patch

FIXTURES_DIR = frappe.get_app_path("card", "fixtures")


def _iter_fixture_docs():
	for fn in sorted(os.listdir(FIXTURES_DIR)):
		if not fn.endswith(".json"):
			continue
		with open(os.path.join(FIXTURES_DIR, fn), encoding="utf-8") as fh:
			data = json.load(fh)
		for doc in data if isinstance(data, list) else [data]:
			if isinstance(doc, dict):
				yield fn, doc


class TestCardFixtures(IntegrationTestCase):
	def test_every_fixture_module_is_valid(self):
		"""Every fixture doc with a 'module' key names a non-empty Module Def
		owned by app 'card'. (Would have caught the empty-module Workspace.)"""
		checked = 0
		for fn, doc in _iter_fixture_docs():
			if "module" not in doc:
				continue
			module = doc.get("module")
			self.assertTrue(module, "%s: doc %r has empty module" % (fn, doc.get("name")))
			self.assertTrue(
				frappe.db.exists("Module Def", {"name": module, "app_name": "card"}),
				"%s: module %r is not a Module Def of app 'card'" % (fn, module),
			)
			checked += 1
		self.assertGreater(checked, 0, "no fixture docs with a module were checked")

	def test_workspace_fixture_module_is_card(self):
		for fn, doc in _iter_fixture_docs():
			if fn == "workspace.json" and doc.get("name") == "Card":
				self.assertEqual(doc.get("module"), install.MODULE)
				return
		self.fail("Workspace 'Card' fixture not found")

	def test_retire_legacy_custom_module_idempotent(self):
		# simulate the live state: a legacy custom Module Def + the Card
		# Workspace scoped to it. Rolled back by the test transaction.
		if not frappe.db.exists("Module Def", install.LEGACY_MODULE):
			md = frappe.new_doc("Module Def")
			md.module_name = install.LEGACY_MODULE
			md.app_name = "card"
			md.custom = 1
			md.insert(ignore_permissions=True)
		if frappe.db.exists("Workspace", install.MODULE):
			frappe.db.set_value(
				"Workspace", install.MODULE, "module", install.LEGACY_MODULE, update_modified=False
			)

		install._retire_legacy_custom_module()
		install._retire_legacy_custom_module()  # idempotent re-run

		self.assertFalse(frappe.db.exists("Module Def", install.LEGACY_MODULE))
		if frappe.db.exists("Workspace", install.MODULE):
			self.assertEqual(
				frappe.db.get_value("Workspace", install.MODULE, "module"), install.MODULE
			)


class TestCardSidebarFold(IntegrationTestCase):
	"""frappe 16.50 `Sidebar` fold (see install._fold_legacy_sidebar)."""

	ITEMS: ClassVar = [
		{"type": "Link", "link_type": "Workspace", "link_to": "Card", "label": "الصفحة الرئيسية"},
		{"type": "Section Break", "label": "المعدات"},
		{"type": "Link", "link_type": "DocType", "link_to": "Card Equipment"},
		{"type": "Link", "link_type": "DocType", "link_to": "Card Monthly Card"},
		{"type": "Link", "link_type": "Report", "link_to": "Equipment Suppliers Summary"},
	]

	def setUp(self):
		if not frappe.db.exists("DocType", "Sidebar"):
			self.skipTest("Sidebar doctype is frappe 16.50+")
		# clean slate (DB-level, no validate/permission) — rolled back by the test transaction
		for nm in (install.MODULE, install.LEGACY_MODULE):
			if frappe.db.exists("Sidebar", nm):
				frappe.db.delete("Sidebar Item", {"parent": nm, "parenttype": "Sidebar"})
				frappe.db.delete("Sidebar", {"name": nm})
		if not frappe.db.exists("Module Def", install.LEGACY_MODULE):
			md = frappe.new_doc("Module Def")
			md.module_name = install.LEGACY_MODULE
			md.app_name = "card"
			md.custom = 1
			md.insert(ignore_permissions=True)

	def _mk_sidebar(self, title, module, items):
		"""Build an app-owned Sidebar at DB level (db_insert), so Sidebar.validate's
		app-owned/developer-mode guard is never invoked in the test."""
		s = frappe.new_doc("Sidebar")
		s.title = title
		s.module = module
		s.standard = 0
		s.app = "card"
		s.name = title  # Sidebar autoname = field:title
		s.owner = s.modified_by = frappe.session.user or "Administrator"
		s.creation = s.modified = frappe.utils.now()
		s.db_insert()
		for idx, it in enumerate(items, start=1):
			install._db_insert_sidebar_item(frappe._dict(it), parent=title, idx=idx)
		return s

	def _item_count(self, parent):
		return frappe.db.count("Sidebar Item", {"parent": parent, "parenttype": "Sidebar"})

	def test_rename_path_keeps_all_items(self):
		self._mk_sidebar(install.LEGACY_MODULE, install.LEGACY_MODULE, self.ITEMS)
		install._retire_legacy_custom_module()
		self.assertTrue(frappe.db.exists("Sidebar", install.MODULE))
		self.assertFalse(frappe.db.exists("Sidebar", install.LEGACY_MODULE))
		self.assertEqual(frappe.db.get_value("Sidebar", install.MODULE, "module"), install.MODULE)
		self.assertEqual(frappe.db.get_value("Sidebar", install.MODULE, "title"), install.MODULE)
		self.assertEqual(self._item_count(install.MODULE), len(self.ITEMS))
		self.assertFalse(frappe.db.exists("Module Def", install.LEGACY_MODULE))

	def test_merge_path_appends_missing_then_deletes(self):
		self._mk_sidebar(install.MODULE, install.MODULE, self.ITEMS[:1])  # canonical has item[0]
		self._mk_sidebar(install.LEGACY_MODULE, install.LEGACY_MODULE, self.ITEMS)  # legacy has all
		install._retire_legacy_custom_module()
		self.assertFalse(frappe.db.exists("Sidebar", install.LEGACY_MODULE))
		self.assertEqual(self._item_count(install.MODULE), len(self.ITEMS))
		self.assertFalse(frappe.db.exists("Module Def", install.LEGACY_MODULE))

	def test_idempotent(self):
		self._mk_sidebar(install.LEGACY_MODULE, install.LEGACY_MODULE, self.ITEMS)
		install._retire_legacy_custom_module()
		install._retire_legacy_custom_module()  # re-run: legacy already gone
		self.assertTrue(frappe.db.exists("Sidebar", install.MODULE))
		self.assertFalse(frappe.db.exists("Sidebar", install.LEGACY_MODULE))
		self.assertEqual(self._item_count(install.MODULE), len(self.ITEMS))
		self.assertFalse(frappe.db.exists("Module Def", install.LEGACY_MODULE))

	# ---- the v1_0_1 patch entrypoint (savepoint + resilience) ----
	def test_patch_execute_folds_and_retires(self):
		self._mk_sidebar(install.LEGACY_MODULE, install.LEGACY_MODULE, self.ITEMS)
		fold_patch.execute()
		self.assertTrue(frappe.db.exists("Sidebar", install.MODULE))
		self.assertFalse(frappe.db.exists("Sidebar", install.LEGACY_MODULE))
		self.assertEqual(frappe.db.get_value("Sidebar", install.MODULE, "title"), install.MODULE)
		self.assertEqual(self._item_count(install.MODULE), len(self.ITEMS))
		self.assertFalse(frappe.db.exists("Module Def", install.LEGACY_MODULE))

	def test_patch_execute_idempotent(self):
		self._mk_sidebar(install.LEGACY_MODULE, install.LEGACY_MODULE, self.ITEMS)
		fold_patch.execute()
		fold_patch.execute()  # second run: Module Def already gone -> no-op
		self.assertTrue(frappe.db.exists("Sidebar", install.MODULE))
		self.assertFalse(frappe.db.exists("Module Def", install.LEGACY_MODULE))

	def test_patch_execute_failure_is_logged_and_does_not_raise(self):
		self._mk_sidebar(install.LEGACY_MODULE, install.LEGACY_MODULE, self.ITEMS)
		before = frappe.db.count("Error Log")
		with patch.object(install, "_retire_legacy_custom_module", side_effect=RuntimeError("boom")):
			fold_patch.execute()  # must NOT raise
		# the failure was logged and bench migrate would continue
		self.assertGreater(frappe.db.count("Error Log"), before)
		# savepoint rollback left the legacy state untouched (no partial corruption)
		self.assertTrue(frappe.db.exists("Sidebar", install.LEGACY_MODULE))
		self.assertTrue(frappe.db.exists("Module Def", install.LEGACY_MODULE))
