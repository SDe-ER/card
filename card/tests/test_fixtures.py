# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see license.txt
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

import frappe
from frappe.tests import IntegrationTestCase

from card import install

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
