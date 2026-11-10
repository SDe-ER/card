# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-127 (#50): the standard rate of the CARD item tax template comes from the company's Card Company
Settings row (`vat_rate`, default 15), not from a hardcoded 15. The 0% template stays 0. An existing
linked template is never renamed; its rows are reconciled to the configured rate as before."""

import frappe
from frappe.utils import flt

from card.gl.masters import _abbr, ensure_posting_masters, standard_vat_rate, vat_account_heads
from card.gl.preflight import check_template_mapping
from card.tests.test_s3_posting import _PostingBase


class TestVatRateSetting(_PostingBase):
	def setUp(self):
		super().setUp()
		self._set_rate(15)

	def tearDown(self):
		self._set_rate(15)
		super().tearDown()

	def _settings_row(self):
		settings = frappe.get_doc("Card Settings")
		return settings, next(r for r in settings.company_settings if r.company == self.company)

	def _set_rate(self, rate, clear_templates=True):
		settings, row = self._settings_row()
		row.vat_rate = rate
		if clear_templates:
			row.vat_item_tax_template = ""
			row.vat_zero_item_tax_template = ""
		settings.save(ignore_permissions=True)

	def _rates(self, template):
		return {
			d.tax_type: flt(d.tax_rate)
			for d in frappe.get_all(
				"Item Tax Template Detail", filters={"parent": template}, fields=["tax_type", "tax_rate"]
			)
		}

	def test_field_default_is_15(self):
		meta = frappe.get_meta("Card Company Settings")
		df = meta.get_field("vat_rate")
		self.assertEqual(df.fieldtype, "Percent")
		self.assertEqual(flt(df.default), 15)
		self.assertFalse(df.description)
		self.assertEqual(flt(frappe.new_doc("Card Company Settings").vat_rate), 15)

	def test_default_keeps_existing_names_and_rates(self):
		row = ensure_posting_masters(self.company)
		abbr = _abbr(self.company)
		heads = vat_account_heads(row)
		self.assertEqual(
			frappe.db.get_value("Item Tax Template", row.vat_item_tax_template, "title"),
			f"CARD VAT 15% - {abbr}",
		)
		self.assertEqual(
			frappe.db.get_value("Item Tax Template", row.vat_zero_item_tax_template, "title"),
			f"CARD VAT 0% - {abbr}",
		)
		self.assertEqual(self._rates(row.vat_item_tax_template), {h: 15.0 for h in heads})
		self.assertEqual(self._rates(row.vat_zero_item_tax_template), {h: 0.0 for h in heads})
		check_template_mapping(row)

	def test_configured_rate_names_and_rates_the_new_template(self):
		self._set_rate(5)
		row = ensure_posting_masters(self.company)
		abbr = _abbr(self.company)
		heads = vat_account_heads(row)
		self.assertEqual(
			frappe.db.get_value("Item Tax Template", row.vat_item_tax_template, "title"),
			f"CARD VAT 5% - {abbr}",
		)
		self.assertEqual(self._rates(row.vat_item_tax_template), {h: 5.0 for h in heads})
		# the zero-rated template is not a guessed VAT: it stays 0
		self.assertEqual(self._rates(row.vat_zero_item_tax_template), {h: 0.0 for h in heads})
		check_template_mapping(row)

	def test_existing_template_is_not_renamed(self):
		row = ensure_posting_masters(self.company)
		linked = row.vat_item_tax_template
		title = frappe.db.get_value("Item Tax Template", linked, "title")
		self._set_rate(5, clear_templates=False)
		row = ensure_posting_masters(self.company)
		self.assertEqual(row.vat_item_tax_template, linked)
		self.assertEqual(frappe.db.get_value("Item Tax Template", linked, "title"), title)
		self.assertTrue(frappe.db.exists("Item Tax Template", linked))
		# the existing reconcile re-points the template rows at the configured rate
		self.assertEqual(self._rates(linked), {h: 5.0 for h in vat_account_heads(row)})
		check_template_mapping(row)

	def test_preflight_refuses_a_template_off_the_configured_rate(self):
		row = ensure_posting_masters(self.company)
		_settings, fresh = self._settings_row()
		fresh.vat_rate = 5  # in memory only: the provisioned template still carries 15
		self.assertRaisesRegex(frappe.ValidationError, "flat 5%", check_template_mapping, fresh)
		check_template_mapping(row)

	def test_validation(self):
		for bad in (0, 100, 150, -1):
			settings, row = self._settings_row()
			row.vat_rate = bad
			with self.assertRaises(frappe.ValidationError, msg=f"vat_rate {bad} accepted"):
				settings.save(ignore_permissions=True)
		self._set_rate(7.5)
		_settings, row = self._settings_row()
		self.assertEqual(flt(row.vat_rate), 7.5)

	def test_out_of_range_rate_stops_provisioning(self):
		_settings, row = self._settings_row()
		row.vat_rate = 0
		self.assertRaises(frappe.ValidationError, standard_vat_rate, row)
		row.vat_rate = 15
		self.assertEqual(standard_vat_rate(row), 15)
