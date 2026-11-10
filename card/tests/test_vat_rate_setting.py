# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-127 (#50): ONE VAT source per company. The standard rate of the CARD item tax template is the single
positive rate of the company's configured purchase/sales tax templates (no hardcoded 15, nothing inferred).
The rate rows of an existing linked template are never changed: a new rate gets a new "CARD VAT {rate}% -
<abbr>" template and the old one stays for the drafts that use it. A built draft whose VAT changed before
submit is refused."""

import frappe
from frappe.utils import flt

from card.gl import integrity
from card.gl.masters import _abbr, ensure_posting_masters, standard_vat_rate, vat_account_heads
from card.gl.posting import _template_vat_rate, _vat_rate, build_monthly_posting
from card.gl.preflight import check_template_mapping
from card.tests.test_s3_posting import _PostingBase


def _rated_template(doctype, company, title, account_head, rate):
	existing = frappe.db.get_value(doctype, {"title": title, "company": company}, "name")
	if existing:
		return existing
	row = {
		"charge_type": "On Net Total",
		"account_head": account_head,
		"rate": rate,
		"description": f"VAT {rate:g}%",
	}
	if doctype == "Purchase Taxes and Charges Template":
		row.update({"category": "Total", "add_deduct_tax": "Add"})
	doc = frappe.get_doc({"doctype": doctype, "title": title, "company": company, "taxes": [row]})
	doc.insert(ignore_permissions=True)
	return doc.name


class TestVatRateFromTaxTemplates(_PostingBase):
	def _settings_row(self):
		settings = frappe.get_doc("Card Settings")
		return settings, next(r for r in settings.company_settings if r.company == self.company)

	def _use_templates(self, purchase_rate, sales_rate):
		pt = _rated_template(
			"Purchase Taxes and Charges Template",
			self.company,
			f"Test CARD Purchase VAT {purchase_rate:g}",
			self.vat_in,
			purchase_rate,
		)
		st = _rated_template(
			"Sales Taxes and Charges Template",
			self.company,
			f"Test CARD Sales VAT {sales_rate:g}",
			self.vat_out,
			sales_rate,
		)
		settings, row = self._settings_row()
		row.purchase_tax_template = pt
		row.sales_tax_template = st
		settings.save(ignore_permissions=True)
		return self._settings_row()[1]

	def _rates(self, template):
		return {
			d.tax_type: flt(d.tax_rate)
			for d in frappe.get_all(
				"Item Tax Template Detail", filters={"parent": template}, fields=["tax_type", "tax_rate"]
			)
		}

	def test_default_15_keeps_existing_names_and_rates(self):
		row = ensure_posting_masters(self.company)
		abbr = _abbr(self.company)
		heads = vat_account_heads(row)
		self.assertEqual(standard_vat_rate(row), 15)
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

	def test_rate_change_creates_a_new_template_and_leaves_the_old(self):
		row = ensure_posting_masters(self.company)
		old = row.vat_item_tax_template
		old_title = frappe.db.get_value("Item Tax Template", old, "title")
		old_rates = self._rates(old)
		zero = row.vat_zero_item_tax_template

		self._use_templates(5, 5)
		row = ensure_posting_masters(self.company)
		heads = vat_account_heads(row)
		self.assertNotEqual(row.vat_item_tax_template, old)
		self.assertEqual(
			frappe.db.get_value("Item Tax Template", row.vat_item_tax_template, "title"),
			f"CARD VAT 5% - {_abbr(self.company)}",
		)
		self.assertEqual(self._rates(row.vat_item_tax_template), {h: 5.0 for h in heads})
		# the old template is not renamed and its rate rows are unchanged
		self.assertEqual(frappe.db.get_value("Item Tax Template", old, "title"), old_title)
		self.assertEqual(self._rates(old), old_rates)
		# the zero-rated template is not a guessed VAT: it stays 0 and stays linked
		self.assertEqual(row.vat_zero_item_tax_template, zero)
		self.assertEqual(self._rates(zero), {h: 0.0 for h in heads})
		check_template_mapping(row)

	def test_old_draft_keeps_its_rate(self):
		self._vat_supplier()
		self._example_card()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		taxes_before = flt(pi.total_taxes_and_charges, 2)
		line_rates_before = [i.item_tax_rate for i in pi.items]

		self._use_templates(5, 5)
		ensure_posting_masters(self.company)

		pi.reload()
		pi.bill_no = "FR127-" + frappe.generate_hash(length=8)
		pi.bill_date = pi.posting_date
		pi.save()
		self.assertEqual([i.item_tax_rate for i in pi.items], line_rates_before)
		self.assertEqual(flt(pi.total_taxes_and_charges, 2), taxes_before)

	def test_snapshot_refuses_a_vat_change(self):
		self._vat_supplier()
		self._example_card()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		log = frappe.get_doc("GL Posting Log", {"posting_doc": pi.name})
		built = frappe.parse_json(log.built_snapshot)
		self.assertIn("vat", built)
		self.assertEqual(built["vat"], integrity.vat_snapshot(pi))
		# the template's rate is edited outside CARD: ERPNext recalculates the draft's line VAT on save
		template = frappe.get_doc("Item Tax Template", pi.items[0].item_tax_template)
		original = [(t.tax_type, t.tax_rate) for t in template.taxes]
		try:
			for t in template.taxes:
				t.tax_rate = 10
			template.save(ignore_permissions=True)
			pi.reload()
			pi.bill_no = "FR127-" + frappe.generate_hash(length=8)
			pi.bill_date = pi.posting_date
			pi.save()
			self.assertNotEqual(integrity.vat_snapshot(pi), built["vat"])
			self.assertRaisesRegex(frappe.ValidationError, "VAT changed", pi.submit)
			# a snapshot stored before FR-127 has no VAT key: it is compared exactly as before
			integrity.check_built_vat(pi, {k: v for k, v in built.items() if k != "vat"})
		finally:
			template.reload()
			template.set("taxes", [{"tax_type": a, "tax_rate": r} for a, r in original])
			template.save(ignore_permissions=True)

	def test_preview_and_diesel_use_the_same_rate(self):
		row = self._use_templates(5, 5)
		ensure_posting_masters(self.company)
		row = self._settings_row()[1]
		self.assertEqual(standard_vat_rate(row), 5)
		self.assertEqual(_template_vat_rate(row.purchase_tax_template, row), 5)
		self.assertEqual(_template_vat_rate(row.sales_tax_template, row), 5)
		self.assertEqual(_vat_rate(row), 5)
		self.assertEqual(set(self._rates(row.vat_item_tax_template).values()), {5.0})
		self.assertEqual(_template_vat_rate(None, row), 0.0)

	def test_purchase_and_sales_rates_differing_are_refused(self):
		row = self._use_templates(5, 15)
		self.assertRaisesRegex(frappe.ValidationError, "different VAT rates", standard_vat_rate, row)
		self.assertRaisesRegex(
			frappe.ValidationError, "different VAT rates", ensure_posting_masters, self.company
		)
		self.assertRaisesRegex(
			frappe.ValidationError,
			"different VAT rates",
			check_template_mapping,
			row,
			provisioned=False,
		)

	def test_no_template_no_rate(self):
		_settings, row = self._settings_row()
		row.purchase_tax_template = ""
		row.sales_tax_template = ""
		self.assertIsNone(standard_vat_rate(row))
		self.assertEqual(_template_vat_rate(None, row), 0.0)
