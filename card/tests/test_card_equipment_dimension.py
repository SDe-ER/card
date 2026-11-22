# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-176 (Owner decisions 2026-11-22): the app creates the Card Equipment accounting dimension itself (patch and
after_install), idempotently and never mandatory; on uninstall it is only disabled, never deleted."""

import frappe
from frappe.tests import IntegrationTestCase

from card.dimension import (
	DIMENSION_DOCTYPE,
	DIMENSION_FIELD,
	ensure_card_equipment_dimension,
	set_card_equipment_dimension_disabled,
)
from card.patches.v4_11_0 import ensure_card_equipment_dimension as patch

DOCTYPES = ("GL Entry", "Journal Entry Account", "Payment Entry", "Purchase Invoice", "Purchase Invoice Item")


class TestCardEquipmentDimension(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def _fields(self):
		return frappe.get_all(
			"Custom Field",
			filters={"fieldname": DIMENSION_FIELD},
			fields=["dt", "read_only", "fieldtype", "options"],
			limit_page_length=0,
		)

	def test_patch_is_idempotent_and_not_mandatory(self):
		before = len(self._fields())
		for _run in range(2):
			patch.execute()
			self.assertEqual(ensure_card_equipment_dimension(), "exists")
		self.assertEqual(frappe.db.count("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE}), 1)
		self.assertEqual(len(self._fields()), before)  # no duplicate field
		name = frappe.db.get_value("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE})
		for row in frappe.get_doc("Accounting Dimension", name).dimension_defaults:
			self.assertFalse(row.mandatory_for_bs)
			self.assertFalse(row.mandatory_for_pl)

	def test_payment_and_invoice_doctypes_carry_the_dimension(self):
		for doctype in DOCTYPES:
			self.assertTrue(frappe.get_meta(doctype).has_field(DIMENSION_FIELD), doctype)
			self.assertFalse(frappe.get_meta(doctype).get_field(DIMENSION_FIELD).reqd, doctype)

	def test_registered_as_patch_and_hooks(self):
		patches = open(frappe.get_app_path("card", "patches.txt"), encoding="utf-8").read()
		self.assertIn("card.patches.v4_11_0.ensure_card_equipment_dimension", patches)
		self.assertIn("card.install.before_uninstall", frappe.get_hooks("before_uninstall", app_name="card"))

	def test_uninstall_disables_and_never_deletes(self):
		from card.install import before_uninstall

		count = len(self._fields())
		try:
			self._check_uninstall(before_uninstall, count)
		finally:
			# never leave the shared test site with a disabled dimension (the posting preflight needs it)
			set_card_equipment_dimension_disabled(False)

	def _check_uninstall(self, before_uninstall, count):
		before_uninstall()
		name = frappe.db.get_value("Accounting Dimension", {"document_type": DIMENSION_DOCTYPE})
		self.assertTrue(name)  # never deleted
		self.assertEqual(frappe.db.get_value("Accounting Dimension", name, "disabled"), 1)
		fields = self._fields()
		self.assertEqual(len(fields), count)  # every field (and its data) kept
		self.assertTrue(all(f.read_only for f in fields))
		self.assertEqual(set_card_equipment_dimension_disabled(True), "unchanged")
		# a reinstall (or the manual command) enables it again
		self.assertEqual(ensure_card_equipment_dimension(), "enabled")
		fields = self._fields()
		self.assertFalse(any(f.read_only for f in fields))
		self.assertTrue(
			all(f.fieldtype == "Link" and f.options == DIMENSION_DOCTYPE for f in fields)
		)  # unchanged
