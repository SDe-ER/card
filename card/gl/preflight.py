# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3 preflight gates (owner item 4c + the F.4 panel assertions). Every gate
throws a clear translated message — never a traceback — and nothing posts
when any gate fails. v16.50 note: the frozen-books control lives on Company
(accounts_frozen_till_date / role_allowed_for_frozen_entries), not on
Accounts Settings as older designs assumed."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.gl.masters import ADJUSTMENT_ITEM_GROUP, vat_account_heads
from card.settings import setting


def require_enabled():
	if not setting("enable_accounting"):
		frappe.throw(_("Accounting posting is disabled; enable it in Card Settings first."))


def company_settings_row(company):
	settings = frappe.get_doc("Card Settings")
	row = next((r for r in settings.get("company_settings") or [] if r.company == company), None)
	if row is None:
		frappe.throw(_("Configure Card Settings for company {0}").format(company))
	return row


def require_accounts(row, fieldnames):
	meta = frappe.get_meta("Card Company Settings")
	for fieldname in fieldnames:
		value = row.get(fieldname)
		field = meta.get_field(fieldname)
		label = _(field.label)
		if not value:
			frappe.throw(
				_("Configure Card Settings for company {0}: {1} is not set.").format(row.company, label)
			)
		link_doctype = field.options  # Account or Cost Center
		link_meta = frappe.get_meta(link_doctype)
		props = ["company"]
		if link_meta.has_field("is_group"):
			props.append("is_group")
		if link_meta.has_field("disabled"):
			props.append("disabled")
		rec = frappe.db.get_value(link_doctype, value, props, as_dict=True)
		if not rec or rec.company != row.company or rec.get("is_group") or rec.get("disabled"):
			frappe.throw(
				_("{0} {1} ({2}) must be an active leaf record of company {3}.").format(
					_(link_doctype), value, label, row.company
				)
			)


def check_period_open(company, posting_date, doctype):
	"""Owner 4c — all four period gates."""
	posting_date = getdate(posting_date)

	# 1) fiscal year exists and is not disabled
	from erpnext.accounts.utils import get_fiscal_year

	try:
		fy = get_fiscal_year(posting_date, company=company, as_dict=True)
	except Exception:
		frappe.throw(
			_("No fiscal year covers {0} for company {1}; create it before posting.").format(
				posting_date, company
			)
		)
	if frappe.db.get_value("Fiscal Year", fy.name, "disabled"):
		frappe.throw(_("Fiscal year {0} is disabled; nothing can be posted into it.").format(fy.name))

	# 2) closed Accounting Period for this doctype
	periods = frappe.get_all(
		"Accounting Period",
		filters={
			"company": company,
			"start_date": ["<=", posting_date],
			"end_date": [">=", posting_date],
		},
		pluck="name",
	)
	for period in periods:
		closed = frappe.get_all(
			"Closed Document",
			filters={"parent": period, "document_type": doctype, "closed": 1},
			limit=1,
		)
		if closed:
			frappe.throw(
				_("Accounting period {0} is closed for {1}; choose another posting date.").format(
					period, _(doctype)
				)
			)

	# 3) frozen books (Company-level in v16)
	frozen_till = frappe.db.get_value("Company", company, "accounts_frozen_till_date")
	if frozen_till and posting_date <= getdate(frozen_till):
		allowed_role = frappe.db.get_value("Company", company, "role_allowed_for_frozen_entries")
		if not allowed_role or allowed_role not in frappe.get_roles():
			frappe.throw(
				_(
					"Books are frozen up to {0} for company {1}; the posting date {2} is inside the frozen period."
				).format(frozen_till, company, posting_date)
			)

	# 4) Card Settings period lock
	lock = setting("period_lock_date")
	if lock and posting_date <= getdate(lock):
		override_role = setting("period_lock_override_role")
		if not override_role or override_role not in frappe.get_roles():
			frappe.throw(
				_("Card period lock: {0} is on or before the lock date {1}; posting is blocked.").format(
					posting_date, lock
				)
			)


def check_invoice_settings(party_type):
	if party_type == "Customer" and frappe.db.get_single_value("Selling Settings", "validate_selling_price"):
		frappe.throw(
			_(
				"Selling Settings validates selling prices, which rejects deduction lines; disable it before posting."
			)
		)
	settings_doctype = "Selling Settings" if party_type == "Customer" else "Buying Settings"
	# v16.50 gate (newer than the design's extracts): PURCHASE deduction lines
	# are negative-rate items and the submit path rejects them unless allowed.
	# Sales Invoices carry NO negative lines (ZATCA; customer deductions post
	# as a Net Total discount), so the selling-side toggle is not required.
	if party_type == "Supplier" and not frappe.db.get_single_value(
		settings_doctype, "allow_negative_rates_for_items"
	):
		frappe.throw(
			_("{0} must allow negative rates for items (deduction lines post as negative rates).").format(
				_(settings_doctype)
			)
		)
	if not frappe.db.get_single_value(settings_doctype, "allow_multiple_items"):
		frappe.throw(
			_("{0} must allow the same item on multiple rows (one line per source document).").format(
				_(settings_doctype)
			)
		)
	if party_type == "Supplier":
		if (frappe.db.get_single_value("Buying Settings", "po_required") or "No") == "Yes":
			frappe.throw(_("Buying Settings requires a Purchase Order; the monthly posting has none."))
	else:
		for field, label in (("so_required", "Sales Order"), ("dn_required", "Delivery Note")):
			if (frappe.db.get_single_value("Selling Settings", field) or "No") == "Yes":
				frappe.throw(
					_("Selling Settings requires a {0}; the monthly posting has none.").format(_(label))
				)


def check_template_mapping(row):
	"""The per-line VAT override only works while the templates still point at
	the live VAT account heads AND the adjustment items carry no item-level
	taxes (else the engine silently swaps the row template)."""
	heads = vat_account_heads(row)
	for fieldname, expected_rate in (("vat_item_tax_template", 15), ("vat_zero_item_tax_template", 0)):
		template = row.get(fieldname)
		if not template:
			continue
		details = frappe.get_all(
			"Item Tax Template Detail",
			filters={"parent": template},
			fields=["tax_type", "tax_rate"],
		)
		if {d.tax_type for d in details} != heads:
			frappe.throw(
				_(
					"Item tax template {0} no longer matches the company's VAT accounts; re-run the posting master setup."
				).format(template)
			)
		for d in details:
			if flt(d.tax_rate) != expected_rate:
				frappe.throw(
					_("Item tax template {0} must carry a flat {1}% rate.").format(template, expected_rate)
				)
	tainted = frappe.get_all(
		"Item Tax",
		filters={"parenttype": "Item", "parent": ["like", "CARD-%"]},
		pluck="parent",
		limit=1,
	)
	if tainted:
		frappe.throw(
			_(
				"Item {0} carries item-level tax templates; CARD items must have none (the line template must win)."
			).format(tainted[0])
		)
	group_taxes = frappe.get_all(
		"Item Tax", filters={"parenttype": "Item Group", "parent": ADJUSTMENT_ITEM_GROUP}, limit=1
	)
	if group_taxes:
		frappe.throw(
			_("Item group {0} carries tax templates; it must have none.").format(ADJUSTMENT_ITEM_GROUP)
		)
