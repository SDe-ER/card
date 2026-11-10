# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-137 (#35 Q2): the Card Reviewer role exists on every site, is granted to nobody and is
named in no DocPerm yet. The v4.8.0 patch is idempotent."""

import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase

from card import install
from card.patches.v4_8_0 import ensure_card_reviewer_role

ROLE = "Card Reviewer"
APP = Path(__file__).resolve().parents[1]


class TestCardReviewerRole(IntegrationTestCase):
	def _holders(self):
		return frappe.get_all("Has Role", filters={"role": ROLE, "parenttype": "User"}, pluck="parent")

	def test_role_is_one_of_the_card_roles(self):
		self.assertEqual(install.CARD_REVIEWER_ROLE, ROLE)
		self.assertIn(ROLE, install.CARD_ROLES)
		self.assertNotIn(ROLE, install.NO_DESK_ROLES)

	def test_patch_twice_creates_the_role_once_with_no_users(self):
		# Simulate a site upgraded from v4.7.0 (no role); rolled back by the test transaction.
		frappe.db.delete("Has Role", {"role": ROLE})
		frappe.db.delete("Role", {"name": ROLE})
		self.assertFalse(frappe.db.exists("Role", ROLE))

		ensure_card_reviewer_role.execute()
		ensure_card_reviewer_role.execute()  # second migrate: no error, no duplicate

		self.assertEqual(frappe.db.count("Role", {"name": ROLE}), 1)
		role = frappe.get_doc("Role", ROLE)
		self.assertEqual(role.desk_access, 1)
		self.assertFalse(role.disabled)
		self.assertEqual(self._holders(), [])

	def test_patch_keeps_an_existing_role_and_its_settings(self):
		ensure_card_reviewer_role.execute()
		frappe.db.set_value("Role", ROLE, "desk_access", 0, update_modified=False)
		ensure_card_reviewer_role.execute()
		self.assertEqual(frappe.db.get_value("Role", ROLE, "desk_access"), 0)
		self.assertEqual(frappe.db.count("Role", {"name": ROLE}), 1)

	def test_install_grants_the_role_to_nobody(self):
		install.ensure_card_roles()
		self.assertTrue(frappe.db.exists("Role", ROLE))
		self.assertEqual(self._holders(), [])

	def test_no_docperm_names_the_role(self):
		self.assertEqual(frappe.get_all("DocPerm", filters={"role": ROLE}, pluck="parent"), [])
		self.assertEqual(frappe.get_all("Custom DocPerm", filters={"role": ROLE}, pluck="parent"), [])
		for path in APP.glob("card/doctype/*/*.json"):
			meta = json.loads(path.read_text())
			roles = {p.get("role") for p in meta.get("permissions") or []}
			self.assertNotIn(ROLE, roles, path.name)

	def test_patch_is_registered(self):
		lines = (APP / "patches.txt").read_text().splitlines()
		self.assertIn("card.patches.v4_8_0.ensure_card_reviewer_role", lines)
