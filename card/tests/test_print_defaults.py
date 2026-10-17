# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Owner decision 2026-10-17: patch v1_2.ensure_print_defaults keeps any
non-empty default print format (the legacy Monthly Card format stays the
default on sites that have it) and only creates a missing setter or fills an
empty one; the new formats stay selectable and new installs default to the new
Monthly Card format. All data is per-test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase

from card import install
from card.patches.v1_2.ensure_print_defaults import PRINT_FORMAT_DEFAULTS, _ensure_default_print_formats

CMC = "Card Monthly Card"
LEGACY = "كارت تشغيل شهري"
NEW = "Card Monthly Card Print"


class TestPrintDefaults(IntegrationTestCase):
	def tearDown(self):
		for doctype in PRINT_FORMAT_DEFAULTS:
			frappe.clear_cache(doctype=doctype)

	def _filters(self, doctype):
		return {"doc_type": doctype, "doctype_or_field": "DocType", "property": "default_print_format"}

	def _value(self, doctype):
		return frappe.db.get_value("Property Setter", self._filters(doctype), "value")

	def _set(self, doctype, value):
		name = frappe.db.get_value("Property Setter", self._filters(doctype))
		if name:
			frappe.db.set_value("Property Setter", name, "value", value, update_modified=False)
		else:
			frappe.get_doc(
				dict(self._filters(doctype), doctype="Property Setter", property_type="Data", value=value)
			).insert(ignore_permissions=True)

	def test_the_legacy_monthly_card_default_is_kept(self):
		self._set(CMC, LEGACY)
		_ensure_default_print_formats()
		_ensure_default_print_formats()  # idempotent
		self.assertEqual(self._value(CMC), LEGACY)
		frappe.clear_cache(doctype=CMC)
		self.assertEqual(frappe.get_meta(CMC).default_print_format, LEGACY)

	def test_any_other_non_empty_default_is_kept(self):
		for doctype in PRINT_FORMAT_DEFAULTS:
			self._set(doctype, "Standard")
		_ensure_default_print_formats()
		for doctype in PRINT_FORMAT_DEFAULTS:
			self.assertEqual(self._value(doctype), "Standard", doctype)

	def test_an_empty_default_is_filled(self):
		for doctype in PRINT_FORMAT_DEFAULTS:
			self._set(doctype, "")
		_ensure_default_print_formats()
		for doctype, print_format in PRINT_FORMAT_DEFAULTS.items():
			self.assertEqual(self._value(doctype), print_format, doctype)

	def test_a_missing_default_is_created(self):
		for doctype in PRINT_FORMAT_DEFAULTS:
			frappe.db.delete("Property Setter", self._filters(doctype))
		_ensure_default_print_formats()
		for doctype, print_format in PRINT_FORMAT_DEFAULTS.items():
			self.assertEqual(self._value(doctype), print_format, doctype)
			self.assertEqual(frappe.db.count("Property Setter", self._filters(doctype)), 1, doctype)

	def test_both_monthly_card_formats_stay_selectable(self):
		self._set(CMC, LEGACY)
		_ensure_default_print_formats()
		for print_format in (LEGACY, NEW):
			values = frappe.db.get_value("Print Format", print_format, ["doc_type", "disabled"], as_dict=True)
			self.assertEqual(values, frappe._dict(doc_type=CMC, disabled=0), print_format)

	def test_a_new_install_defaults_to_the_new_format(self):
		frappe.db.delete("Property Setter", self._filters(CMC))
		install._ensure_print_default_property_setter()
		self.assertEqual(install.CMC_DEFAULT_PRINT_FORMAT, NEW)
		self.assertEqual(self._value(CMC), NEW)
