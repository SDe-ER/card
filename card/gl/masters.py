# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3 master-data provisioning (idempotent): the service items and the two
per-company VAT item tax templates the posting builder needs. Standard-first:
plain Items / Item Groups / Item Tax Templates — nothing custom."""

import frappe
from frappe import _
from frappe.utils import flt

ADJUSTMENT_ITEM_GROUP = "Card Adjustments"
SERVICE_ITEM_GROUP = "Card Services"

# (Card Company Settings fieldname, item_code stem, item_name)
POSTING_ITEMS = [
	("rental_item", "CARD-RENTAL", "Equipment Rental"),
	("diesel_item", "CARD-DIESEL", "Diesel"),
	("transport_item", "CARD-TRANSPORT", "Equipment Transport"),
	("rental_out_item", "CARD-RENTAL-OUT", "Equipment Rental Revenue"),
]


def _abbr(company):
	return frappe.db.get_value("Company", company, "abbr") or company


def _ensure_item_group(name):
	if not frappe.db.exists("Item Group", name):
		frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": "All Item Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	return name


def _ensure_item(code, name, group):
	"""A non-stock service item with NO item-level tax templates — the row's
	item_tax_template must always win verbatim (taxes_and_totals skips the
	item-tax merge entirely when Item.taxes and the group's taxes are empty)."""
	if frappe.db.exists("Item", code):
		return code
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_name": name,
			"item_group": group,
			"stock_uom": "Nos",
			"is_stock_item": 0,
			"is_sales_item": 1,
			"is_purchase_item": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _template_vat_head(template, child_dt):
	"""The template's single VAT account head. Shape-asserted: exactly one
	'On Net Total' row with rate > 0 and no 'Actual' rows (an Actual row is
	copied verbatim onto the invoice regardless of the per-line overrides,
	so it would silently corrupt the generated posting's VAT)."""
	rows = frappe.get_all(
		child_dt,
		filters={
			"parent": template,
			"parenttype": child_dt.replace("Taxes and Charges", "Taxes and Charges Template"),
		},
		fields=["account_head", "rate", "charge_type"],
	)
	vat_rows = [d for d in rows if d.charge_type == "On Net Total" and flt(d.rate) > 0]
	actual_rows = [d for d in rows if d.charge_type == "Actual"]
	if len(vat_rows) != 1 or actual_rows:
		frappe.throw(
			_(
				"Tax template {0} must carry exactly one 'On Net Total' VAT row and no 'Actual' rows (found {1} VAT row(s), {2} 'Actual' row(s)); fix the template before posting."
			).format(template, len(vat_rows), len(actual_rows))
		)
	if not vat_rows[0].account_head:
		frappe.throw(_("Tax template {0}: the VAT row has no account head.").format(template))
	return vat_rows[0].account_head


def vat_account_heads(row):
	"""The VAT account heads of the company's purchase AND sales tax templates
	— one shape-asserted 'On Net Total' row each (the rows the per-line item
	tax templates must override)."""
	heads = set()
	for template_field, child_dt in (
		("purchase_tax_template", "Purchase Taxes and Charges"),
		("sales_tax_template", "Sales Taxes and Charges"),
	):
		template = row.get(template_field)
		if template:
			heads.add(_template_vat_head(template, child_dt))
	return heads


def _reconcile_item_tax_template(name, heads, rate):
	"""A drifted template (the company's VAT account heads changed) is
	re-pointed at the current heads instead of dead-ending every posting."""
	expected = {head: flt(rate) for head in heads}
	current = {
		d.tax_type: flt(d.tax_rate)
		for d in frappe.get_all(
			"Item Tax Template Detail", filters={"parent": name}, fields=["tax_type", "tax_rate"]
		)
	}
	if current == expected:
		return
	doc = frappe.get_doc("Item Tax Template", name)
	doc.set("taxes", [{"tax_type": head, "tax_rate": rate} for head in sorted(heads)])
	doc.save(ignore_permissions=True)


def _ensure_item_tax_template(company, title, heads, rate):
	existing = frappe.db.get_value("Item Tax Template", {"title": title, "company": company}, "name")
	if existing:
		_reconcile_item_tax_template(existing, heads, rate)
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Item Tax Template",
			"title": title,
			"company": company,
			"taxes": [{"tax_type": head, "tax_rate": rate} for head in sorted(heads)],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_posting_masters(company):
	"""Idempotent: service items for the posting lines + the two VAT override
	templates + per-type adjustment items. Fills the blanks in the company's
	Card Company Settings row and the adjustment types' item column."""
	settings = frappe.get_doc("Card Settings")
	row = next((r for r in settings.get("company_settings") or [] if r.company == company), None)
	if row is None:
		frappe.throw(_("Configure Card Settings for company {0}").format(company))

	_ensure_item_group(SERVICE_ITEM_GROUP)
	_ensure_item_group(ADJUSTMENT_ITEM_GROUP)
	changed = []
	for fieldname, code, name in POSTING_ITEMS:
		if not row.get(fieldname):
			row.db_set(fieldname, _ensure_item(code, name, SERVICE_ITEM_GROUP), update_modified=False)
			changed.append(fieldname)
		elif not frappe.db.exists("Item", row.get(fieldname)):
			_ensure_item(row.get(fieldname), name, SERVICE_ITEM_GROUP)

	heads = vat_account_heads(row)
	abbr = _abbr(company)
	if heads:
		for fieldname, title, rate in (
			("vat_item_tax_template", f"CARD VAT 15% - {abbr}", 15),
			("vat_zero_item_tax_template", f"CARD VAT 0% - {abbr}", 0),
		):
			if not row.get(fieldname):
				row.db_set(
					fieldname,
					_ensure_item_tax_template(company, title, heads, rate),
					update_modified=False,
				)
			else:
				_reconcile_item_tax_template(row.get(fieldname), heads, rate)

	for t in settings.get("adjustment_types") or []:
		if t.company != company or t.disabled:
			continue
		if not t.item:
			code = f"CARD-ADJ-{frappe.scrub(t.type_name).upper().replace('_', '-')}-{abbr}"
			t.db_set("item", _ensure_item(code, t.type_name, ADJUSTMENT_ITEM_GROUP), update_modified=False)
	return row
