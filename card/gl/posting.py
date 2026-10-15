# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3 monthly posting builder (approved design: GL-posting-design-v1.2.md +
F-design §F.4-panel).

One DRAFT Purchase Invoice per supplier per month / one DRAFT Sales Invoice
per customer per month; one item line per source document (rental card,
diesel fill, transport) plus one line per typed adjustment row; every line
carries project + cost_center (+ card_equipment when the dimension exists).
Creating the draft RESERVES its sources (per-side invoice link); `posted`
flips only when the invoice is submitted (card/gl/events.py).

Implementation notes vs the design text (documented divergences):
- Sub-rental cards bill BOTH parties, so the per-side reservation uses the
  card's `purchase_invoice` / `sales_invoice` links; `gl_posting` mirrors the
  most recent active posting for display. Fills/transports are supplier-only.
- VAT registration is detected by the supplier's `tax_id` (KSA VAT number).
"""

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.constants import CUSTOMER_BILLING_DIRECTIONS, SUPPLIER_BILLING_DIRECTIONS
from card.diesel import project_operating_hours
from card.gl import preflight
from card.gl.events import _point_display
from card.gl.masters import ensure_posting_masters
from card.settings import setting


def _month_bounds(month, year):
	month = int(month)
	year = int(year)
	last = calendar.monthrange(year, month)[1]
	return datetime.date(year, month, 1), datetime.date(year, month, last)


def _held_by_active_log(doctype, names, posting_type):
	"""Sources already included in an ACTIVE (Draft/Submitted) posting of the
	same type. The side's invoice link appears only on submit, so GL Posting
	Source membership is the check that also covers drafts."""
	if not names:
		return set()
	held = set()
	for row in frappe.get_all(
		"GL Posting Source",
		filters={
			"parenttype": "GL Posting Log",
			"source_doctype": doctype,
			"source_name": ["in", names],
		},
		fields=["source_name", "parent"],
	):
		log = frappe.db.get_value("GL Posting Log", row.parent, ["status", "posting_type"], as_dict=True)
		if log and log.status in ACTIVE_STATES and log.posting_type == posting_type:
			held.add(row.source_name)
	return held


def _exclude_held(rows, doctype, posting_type):
	held = _held_by_active_log(doctype, [r.name for r in rows], posting_type)
	return [r for r in rows if r.name not in held]


def _types_map(company):
	settings = frappe.get_doc("Card Settings")
	return {
		t.type_name: t
		for t in (settings.get("adjustment_types") or [])
		if t.company == company and not t.disabled
	}


def _assert_identity(card, lines_total, expected, side_label):
	tolerance = flt(setting("reconciliation_tolerance")) or 0.01
	if abs(flt(lines_total, 2) - flt(expected, 2)) > tolerance:
		frappe.throw(
			_(
				"Reconciliation mismatch on card {0} ({1} side): invoice lines total {2} but the card stores {3}."
			).format(card.name, _(side_label), flt(lines_total, 2), flt(expected, 2))
		)


def _split_fill_by_allocation(fill, month, year):
	"""[(card_equipment or None, amount)] for one diesel fill. A fill bound to
	an equipment is one line; a project-tank fill is split per equipment
	pro-rata by the project+month OPERATING HOURS (owner checkpoint C: direct
	fills must never influence tank weights; largest-remainder rounding keeps
	the sum halala-exact); a period with no eligible hours stays one
	unallocated line at project level."""
	amount = flt(fill.amount, 2)
	if fill.card_equipment:
		return [(fill.card_equipment, amount)]
	hours = project_operating_hours(fill.project, month, year)
	total_hours = sum(hours.values())
	if not total_hours:
		return [(None, amount)]
	shares = []
	for eq, hrs in sorted(hours.items()):
		shares.append([eq, flt(amount * hrs / total_hours, 2)])
	drift = flt(amount - sum(s[1] for s in shares), 2)
	if drift:
		largest = max(shares, key=lambda s: s[1])
		largest[1] = flt(largest[1] + drift, 2)
	return [(eq, amt) for eq, amt in shares if amt]


def _supplier_sources(company, party, first_day, last_day, month, year):
	cards = frappe.get_all(
		"Card Monthly Card",
		filters={
			"docstatus": 1,
			"company": company,
			"supplier": party,
			"month": "%02d" % int(month),
			"year": int(year),
			"purchase_invoice": ["in", ["", None]],
			"card_direction": ["in", list(SUPPLIER_BILLING_DIRECTIONS)],
		},
		fields=["name"],
	)
	fills = frappe.get_all(
		"Project Diesel Fill",
		filters={
			"docstatus": 1,
			"company": company,
			"supplier": party,
			"date": ["between", [first_day, last_day]],
			"purchase_invoice": ["in", ["", None]],
		},
		fields=["name", "project", "card_equipment", "litres", "amount", "date"],
	)
	transports = frappe.get_all(
		"Equipment Transport",
		filters={
			"docstatus": 1,
			"company": company,
			"transport_supplier": party,
			"date": ["between", [first_day, last_day]],
			"purchase_invoice": ["in", ["", None]],
		},
		fields=["name", "project", "equipment", "amount", "date", "from_location", "to_location"],
	)
	return cards, fills, transports


def _customer_cards(company, party, month, year):
	return frappe.get_all(
		"Card Monthly Card",
		filters={
			"docstatus": 1,
			"company": company,
			"customer": party,
			"month": "%02d" % int(month),
			"year": int(year),
			"sales_invoice": ["in", ["", None]],
			"card_direction": ["in", list(CUSTOMER_BILLING_DIRECTIONS)],
		},
		fields=["name"],
	)


def _card_lines(card_name, side, row, types):
	"""The invoice lines one card contributes on one side."""
	card = frappe.get_doc("Card Monthly Card", card_name)
	lines = []
	if side == "Supplier":
		base_rate, base_item, base_account = (
			flt(card.amount, 2),
			row.rental_item,
			row.equipment_rental_expense_account,
		)
		expected = flt(card.net_amount, 2)
	else:
		base_rate, base_item, base_account = (
			flt(card.customer_amount, 2),
			row.rental_out_item,
			row.equipment_rental_income_account,
		)
		expected = flt(card.customer_net_amount, 2)
	lines.append(
		{
			"item_code": base_item,
			"rate": base_rate,
			"account": base_account,
			"project": card.project,
			"card_equipment": card.equipment,
			"taxable": 1,
			"description": _("Monthly operation card {0} — {1}").format(
				card.name, card.equipment_name or card.equipment
			),
		}
	)
	total = base_rate
	discount = 0.0
	for adj in card.get("adjustments") or []:
		if (adj.side or "Supplier") != side:
			continue
		signed = flt(adj.amount, 2) if adj.adjustment_type == "إضافة" else -flt(adj.amount, 2)
		total = flt(total + signed, 2)
		typ = types.get(adj.adjustment_type_ref) if adj.adjustment_type_ref else None
		if adj.adjustment_type_ref and not typ:
			frappe.throw(
				_(
					"Addition/deduction type {0} on card {1} is not configured (or is disabled) in Card Settings."
				).format(adj.adjustment_type_ref, card.name)
			)
		if side == "Customer" and signed < 0:
			# ZATCA rule (owner 2026-10-15): NO negative lines on Sales Invoices.
			# Taxable customer deductions become an invoice discount on Net Total
			# (same VAT base effect); non-taxable ones cannot be represented as a
			# Net Total discount without shifting VAT — refuse until the owner
			# decides the representation (credit note vs Grand Total discount).
			if typ is not None and not typ.taxable:
				frappe.throw(
					_(
						"Non-taxable customer-side deduction {0} on card {1} is not supported on a Sales Invoice (ZATCA: no negative lines; a Net Total discount would change the VAT base). Ask the owner for the representation."
					).format(adj.adjustment_type_ref or adj.description or "", card.name)
				)
			discount = flt(discount + flt(adj.amount, 2), 2)
			continue
		lines.append(
			{
				"item_code": typ.item if typ else base_item,
				"rate": signed,
				"account": typ.account if typ else base_account,
				"project": card.project,
				"card_equipment": card.equipment,
				"taxable": 1 if (typ is None or typ.taxable) else 0,
				"description": "{0} — {1} — {2}".format(
					(typ.type_name if typ else adj.adjustment_type), card.name, adj.description or ""
				),
			}
		)
	_assert_identity(card, total, expected, side)
	return card, lines, discount


def build_monthly_posting(company, party_type, party, month, year):
	"""Create ONE draft posting (PI for a Supplier, SI for a Customer) for the
	party's unposted submitted sources of that month. Returns the invoice name."""
	preflight.require_enabled()
	row = preflight.company_settings_row(company)
	first_day, last_day = _month_bounds(month, year)
	posting_doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
	preflight.check_period_open(company, last_day, posting_doctype)
	preflight.check_invoice_settings(party_type)
	# fail-closed: never build GL without the equipment dimension (checkpoint B)
	preflight.require_equipment_dimension(posting_doctype)
	ensure_posting_masters(company)
	row = preflight.company_settings_row(company)  # re-read after provisioning

	if party_type == "Supplier":
		preflight.require_accounts(
			row,
			[
				"equipment_rental_expense_account",
				"diesel_expense_account",
				"transport_expense_account",
				"payable_account",
				"cost_center",
			],
		)
	else:
		preflight.require_accounts(
			row, ["equipment_rental_income_account", "receivable_account", "cost_center"]
		)

	actives = frappe.get_all(
		"GL Posting Log",
		filters={
			"company": company,
			"party_type": party_type,
			"party": party,
			"month": "%02d" % int(month),
			"year": int(year),
			"posting_type": posting_doctype,
			"status": ["in", list(ACTIVE_STATES)],
		},
		fields=["name", "posting_doc", "sequence"],
		order_by="sequence asc",
	)
	sequence = 1
	for active in actives:
		if frappe.db.get_value(posting_doctype, active.posting_doc, "docstatus") == 0:
			frappe.throw(
				_(
					"A draft posting already exists for {0} {1} in {2}/{3}: {4}. Submit it, or rebuild it to include newer documents."
				).format(_(party_type), party, month, year, active.posting_doc)
			)
		sequence = max(sequence, (active.sequence or 1) + 1)

	types = _types_map(company)

	# ---- collect lines ----
	lines = []
	total_discount = 0.0
	sources = {"Card Monthly Card": [], "Project Diesel Fill": [], "Equipment Transport": []}
	if party_type == "Supplier":
		cards, fills, transports = _supplier_sources(company, party, first_day, last_day, month, year)
		cards = _exclude_held(cards, "Card Monthly Card", posting_doctype)
		fills = _exclude_held(fills, "Project Diesel Fill", posting_doctype)
		transports = _exclude_held(transports, "Equipment Transport", posting_doctype)
		for c in cards:
			card, card_lines, _discount = _card_lines(c.name, "Supplier", row, types)
			lines.extend(card_lines)
			sources["Card Monthly Card"].append((card.name, flt(card.net_amount, 2)))
		for fill in fills:
			for equipment, amount in _split_fill_by_allocation(fill, int(month), int(year)):
				lines.append(
					{
						"item_code": row.diesel_item,
						"rate": amount,
						"account": row.diesel_expense_account,
						"project": fill.project,
						"card_equipment": equipment,
						"taxable": 1,
						"description": _("Diesel fill {0} — {1} L").format(fill.name, fill.litres),
					}
				)
			sources["Project Diesel Fill"].append((fill.name, flt(fill.amount, 2)))
		for t in transports:
			lines.append(
				{
					"item_code": row.transport_item,
					"rate": flt(t.amount, 2),
					"account": row.transport_expense_account,
					"project": t.project,
					"card_equipment": t.equipment or None,
					"taxable": 1,
					"description": _("Equipment transport {0}: {1} → {2}").format(
						t.name, t.from_location or "", t.to_location or ""
					),
				}
			)
			sources["Equipment Transport"].append((t.name, flt(t.amount, 2)))
	else:
		customer_cards = _exclude_held(
			_customer_cards(company, party, month, year), "Card Monthly Card", posting_doctype
		)
		for c in customer_cards:
			card, card_lines, discount = _card_lines(c.name, "Customer", row, types)
			lines.extend(card_lines)
			total_discount = flt(total_discount + discount, 2)
			sources["Card Monthly Card"].append((card.name, flt(card.customer_net_amount, 2)))
		if total_discount and any(not line["taxable"] for line in lines):
			# A Net Total discount is apportioned across ALL lines, so a
			# zero-rated line would absorb part of a fully-taxable deduction
			# and shift the VAT base (ZATCA). Refuse the mix.
			frappe.throw(
				_(
					"Customer {0} has both a zero-rated addition line and a deduction discount in {1}/{2}; the discount would shift the VAT base across the zero-rated line. Post them in separate months or ask the owner."
				).format(party, month, year)
			)

	if not lines:
		frappe.throw(
			_("Nothing to post: no unposted submitted documents for {0} {1} in {2}/{3}.").format(
				_(party_type), party, month, year
			)
		)

	# ---- taxes ----
	if party_type == "Supplier":
		vat_registered = bool(frappe.db.get_value("Supplier", party, "tax_id"))
		tax_template = row.purchase_tax_template if vat_registered else None
		if vat_registered and not tax_template:
			frappe.throw(
				_(
					"Supplier {0} is VAT-registered (tax ID set) but Card Settings for company {1} has no Purchase tax template; posting would silently drop the VAT."
				).format(party, company)
			)
	else:
		vat_registered = True  # owned rental revenue is always 15% ZATCA per the design
		tax_template = row.sales_tax_template
		if not tax_template:
			frappe.throw(
				_("Configure Card Settings for company {0}: Sales tax template is not set.").format(company)
			)
	if tax_template:
		preflight.check_template_mapping(row)
		for fieldname in ("vat_item_tax_template", "vat_zero_item_tax_template"):
			if not row.get(fieldname):
				frappe.throw(
					_("Configure Card Settings for company {0}: {1} is not set.").format(
						company, _(frappe.get_meta("Card Company Settings").get_label(fieldname))
					)
				)

	total = flt(sum(flt(line["rate"], 2) for line in lines) - total_discount, 2)
	if total < 0:
		offenders = ", ".join(sorted({name for name, _amt in sources["Card Monthly Card"]})) or party
		frappe.throw(
			_(
				"The monthly total for {0} {1} is negative ({2}); deductions exceed the dues. Resolve the cards ({3}) or ask the owner how to carry the balance."
			).format(_(party_type), party, total, offenders)
		)

	# ---- build the invoice ----
	inv = frappe.new_doc(posting_doctype)
	inv.company = company
	inv.set_posting_time = 1
	inv.posting_date = last_day
	inv.update_stock = 0
	inv.ignore_pricing_rule = 1
	# halala-exact postings: no rounded_total / Round Off entry on generated invoices
	inv.disable_rounded_total = 1
	if total_discount:
		# customer-side taxable deductions (ZATCA: no negative SI lines); a
		# Net Total discount reduces the VAT base by exactly the same amount
		inv.apply_discount_on = "Net Total"
		inv.discount_amount = total_discount
	if party_type == "Supplier":
		inv.supplier = party
		inv.credit_to = row.payable_account
		inv.due_date = last_day
	else:
		inv.customer = party
		inv.debit_to = row.receivable_account
	inv.cost_center = row.cost_center
	for line in lines:
		item = {
			"item_code": line["item_code"],
			"qty": 1,
			"uom": "Nos",
			"conversion_factor": 1,
			"rate": line["rate"],
			"description": line["description"],
			"project": line["project"],
			"cost_center": row.cost_center,
		}
		if party_type == "Supplier":
			item["expense_account"] = line["account"]
		else:
			item["income_account"] = line["account"]
		if line.get("card_equipment"):
			item["card_equipment"] = line["card_equipment"]
		if tax_template:
			item["item_tax_template"] = (
				row.vat_item_tax_template if line["taxable"] else row.vat_zero_item_tax_template
			)
		inv.append("items", item)
	if tax_template:
		inv.taxes_and_charges = tax_template
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		for tax_row in get_taxes_and_charges(
			(
				"Purchase Taxes and Charges Template"
				if party_type == "Supplier"
				else "Sales Taxes and Charges Template"
			),
			tax_template,
		):
			inv.append("taxes", tax_row)
	inv.flags.card_gl_build = True
	inv.insert(ignore_permissions=True)

	# ---- reserve sources + log (same transaction; the unique key is the race guard) ----
	log = frappe.get_doc(
		{
			"doctype": "GL Posting Log",
			"company": company,
			"party_type": party_type,
			"party": party,
			"month": "%02d" % int(month),
			"year": int(year),
			"posting_type": posting_doctype,
			"sequence": sequence,
			"status": "Draft",
			"posting_doctype": posting_doctype,
			"posting_doc": inv.name,
			"amount": flt(inv.grand_total, 2),
		}
	)
	# The sources child table is the AUTHORITATIVE reservation list; the
	# lifecycle handlers (card/gl/events.py) iterate it on submit/cancel/trash.
	for doctype, rows in sources.items():
		for name, amount in rows:
			log.append("sources", {"source_doctype": doctype, "source_name": name, "amount": amount})
	log.insert(ignore_permissions=True)

	# gl_posting on the source is DISPLAY-ONLY (never the invoice itself: a
	# backlink from a submitted source would block cancelling the invoice).
	# The invoice link fields are written only on submit (card/gl/events.py).
	for doctype, rows in sources.items():
		for name, _amount in rows:
			_point_display(doctype, name, log.name)

	return inv.name


def rebuild_monthly_posting(company, party_type, party, month, year):
	"""Late sources against a DRAFT posting: delete the draft (its reservations
	are freed by card.gl.events.on_trash) and build the month again so the new
	draft includes every unposted submitted document."""
	posting_doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
	for active in frappe.get_all(
		"GL Posting Log",
		filters={
			"company": company,
			"party_type": party_type,
			"party": party,
			"month": "%02d" % int(month),
			"year": int(year),
			"posting_type": posting_doctype,
			"status": "Draft",
		},
		fields=["posting_doc"],
	):
		if frappe.db.get_value(posting_doctype, active.posting_doc, "docstatus") == 0:
			frappe.delete_doc(posting_doctype, active.posting_doc, ignore_permissions=True)
	return build_monthly_posting(company, party_type, party, month, year)


def _checked_endpoint_args(party_type, month, year):
	"""Shared gate for the whitelisted entry points: role, party type, period."""
	if not ({"Card Manager", "System Manager"} & set(frappe.get_roles())):
		frappe.throw(
			_("Only Card Manager or System Manager may build monthly postings."), frappe.PermissionError
		)
	if party_type not in ("Supplier", "Customer"):
		frappe.throw(_("Party type must be Supplier or Customer."))
	try:
		month = int(month)
		year = int(year)
	except (TypeError, ValueError):
		frappe.throw(_("Month and year must be numbers."))
	if not 1 <= month <= 12:
		frappe.throw(_("Month must be between 1 and 12."))
	return month, year


@frappe.whitelist(methods=["POST"])
def rebuild_month(company: str, party_type: str, party: str, month: str, year: str):
	"""Desk entry point for rebuilding a draft posting after late documents."""
	month, year = _checked_endpoint_args(party_type, month, year)
	return rebuild_monthly_posting(company, party_type, party, month, year)


@frappe.whitelist(methods=["POST"])
def post_month(company: str, party_type: str, party: str, month: str, year: str):
	"""Desk entry point (S4 wires the button). Card Manager / System Manager only."""
	month, year = _checked_endpoint_args(party_type, month, year)
	return build_monthly_posting(company, party_type, party, month, year)
