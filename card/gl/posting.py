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
from card.diesel import project_operating_hours, split_by_weights
from card.gl import integrity, preflight
from card.gl.events import _point_display
from card.gl.masters import ensure_posting_masters, ensure_selling_price_list
from card.report_access import permitted_companies
from card.settings import setting

# documents the builder reads; a User Permission on Company scoped to any of
# them limits what the caller may post
POSTING_SOURCE_DOCTYPES = ("Card Monthly Card", "Project Diesel Fill", "Equipment Transport")


def _month_bounds(month, year):
	month = int(month)
	year = int(year)
	last = calendar.monthrange(year, month)[1]
	return datetime.date(year, month, 1), datetime.date(year, month, last)


def _held_by_active_log(doctype, names, party_type):
	"""Sources already included in ANY ACTIVE (Draft/Submitted) posting unit of
	the same SIDE — G0 §5a: the discriminator is the log's party_type, never the
	document type (a JE and a PI must not both recognize a source). The side's
	invoice link appears only on submit, so GL Posting Source membership is the
	check that also covers drafts."""
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
		log = frappe.db.get_value("GL Posting Log", row.parent, ["status", "party_type"], as_dict=True)
		if log and log.status in ACTIVE_STATES and log.party_type == party_type:
			held.add(row.source_name)
	return held


def _exclude_held(rows, doctype, party_type):
	held = _held_by_active_log(doctype, [r.name for r in rows], party_type)
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


def _split_fill_by_allocation(fill, month, year, company):
	"""[(card_equipment or None, amount)] for one diesel fill. A fill bound to
	an equipment is one line; a project-tank fill is split per equipment
	pro-rata by the project+month OPERATING HOURS (owner checkpoint C: direct
	fills must never influence tank weights; largest-remainder rounding keeps
	the sum halala-exact); a period with no eligible hours stays one
	unallocated line at project level."""
	amount = flt(fill.amount, 2)
	if fill.card_equipment:
		return [(fill.card_equipment, amount, flt(fill.litres, 3))]
	hours = project_operating_hours(fill.project, month, year, company)
	# M6: ONE shared split rule for posting and display (card.diesel.split_by_weights);
	# the litres shares use the same rule as the diesel reports (sum exactly)
	shares = split_by_weights(amount, hours, 2)
	if not shares:
		return [(None, amount, flt(fill.litres, 3))]
	litres = split_by_weights(fill.litres, hours, 3)
	return [(eq, amt, flt(litres.get(eq), 3)) for eq, amt in sorted(shares.items()) if amt]


def _source_cost_center(doctype, source, company):
	"""The source document's own cost center, if it can carry the line: a leaf,
	enabled cost center of the posting's company. Refused before anything is
	reserved — otherwise the draft invoice could never be submitted (#34)."""
	cc = source.get("cost_center")
	if not cc:
		return None
	row = frappe.db.get_value("Cost Center", cc, ["company", "is_group", "disabled"], as_dict=True)
	if not row or row.company != company or row.is_group or row.disabled:
		frappe.throw(
			_(
				"{0} {1}: cost center {2} cannot be used for company {3} (it must be an enabled, non-group cost center of that company)."
			).format(_(doctype), source.get("name"), cc, company)
		)
	return cc


def _valid_cost_center(cc, company):
	"""A cost center that can carry a posting line of the company: enabled leaf of that company."""
	if not cc:
		return None
	row = frappe.db.get_value("Cost Center", cc, ["company", "is_group", "disabled"], as_dict=True)
	return cc if row and row.company == company and not row.is_group and not row.disabled else None


def _allocation_exception(message):
	frappe.throw(message, title=_("Cost allocation needs review"))


def _checked_allocation(cc, company, what):
	"""A configured allocation must be usable as it is: an invalid one is an exception for
	review, never silently replaced by a less specific cost center."""
	if _valid_cost_center(cc, company):
		return cc
	_allocation_exception(
		_(
			"{0} has cost center {1}, which cannot carry a posting of company {2} (it must be an enabled, non-group cost center of that company). Correct it and build again."
		).format(what, cc, company)
	)


def card_cost_center(card, company):
	"""P1-0: the cost center of a monthly card's lines, from the most specific allocation
	that is set: the equipment's assignment(s) to the card's project overlapping the card's
	period, then the project's cost center, then the equipment's own; None = no allocation
	is set anywhere, so the Card Company Settings default applies.
	A card covers one project; an equipment that worked on two projects in a month has one
	card per project (card days must fall inside that project's assignment). Assignments
	with different cost centers inside one card's period, or a set but unusable cost center,
	cannot be allocated reliably: the build is refused with an exception for review."""
	start, end = getdate(card.from_date), getdate(card.to_date or card.from_date)
	assignments = [
		a
		for a in frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": card.equipment, "project": card.project},
			fields=["name", "from_date", "to_date", "cost_center"],
		)
		if a.from_date and getdate(a.from_date) <= end and (not a.to_date or getdate(a.to_date) >= start)
	]
	centers = {a.cost_center for a in assignments if a.cost_center}
	if len(centers) > 1:
		_allocation_exception(
			_(
				"Card {0}: the assignments of {1} to project {2} in its period carry different cost centers ({3}: {4}); split the card by assignment or align the assignments, then build again."
			).format(
				card.name,
				card.equipment,
				card.project,
				", ".join(sorted(a.name for a in assignments if a.cost_center)),
				", ".join(sorted(centers)),
			)
		)
	if centers:
		return _checked_allocation(
			centers.pop(),
			company,
			_("The assignment of {0} to project {1}").format(card.equipment, card.project),
		)
	project_cc = card.project and frappe.db.get_value("Project", card.project, "cost_center")
	if project_cc:
		return _checked_allocation(project_cc, company, _("Project {0}").format(card.project))
	equipment_cc = card.equipment and frappe.db.get_value("Card Equipment", card.equipment, "cost_center")
	if equipment_cc:
		return _checked_allocation(equipment_cc, company, _("Equipment {0}").format(card.equipment))
	return None


def fill_cost_center(fill, company):
	"""P1-0: a diesel fill's own cost center (validated, #34), else its project's (checked the
	same way: a set but unusable project cost center is an exception). The equipment stays on
	the line (direct fill, or the split by operating hours), so equipment traceability is kept."""
	own = _source_cost_center("Project Diesel Fill", fill, company)
	if own:
		return own
	project_cc = fill.project and frappe.db.get_value("Project", fill.project, "cost_center")
	if project_cc:
		return _checked_allocation(project_cc, company, _("Project {0}").format(fill.project))
	return None


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
			# FR-086b (Owner 2026-10-27): an imported WhatsApp session is never posted here. Its
			# supplier's own invoice is the Purchase Invoice (entered in Desk, or already there),
			# and its price includes VAT. source_messages: always set by the import, and kept by
			# an amendment (the unique source_key stays with the original).
			"source_key": ["in", ["", None]],
			"source_messages": ["in", ["", None]],
		},
		fields=["name", "project", "card_equipment", "litres", "amount", "date", "cost_center"],
	)
	transports = frappe.get_all(
		"Equipment Transport",
		filters={
			"docstatus": 1,
			"company": company,
			"transport_supplier": party,
			"date": ["between", [first_day, last_day]],
			"purchase_invoice": ["in", ["", None]],
			# only a move the company pays is billed by the transport supplier (Owner 2026-10-19)
			"cost_borne_by": ["in", ["Company", "", None]],
		},
		fields=[
			"name",
			"project",
			"amount",
			"date",
			"from_location",
			"to_location",
			"source_project",
			"source_location",
			"destination_type",
			"destination_location",
			"cost_center",
		],
	)
	return cards, fills, transports


def _transport_shares(transports):
	"""{transport: [(equipment, amount)]}, read in one query; a transport that moved no
	equipment gets [(None, amount)]."""
	shares = {t.name: [] for t in transports}
	if shares:
		for r in frappe.get_all(
			"Equipment Transport Item",
			filters={"parent": ["in", list(shares)], "parenttype": "Equipment Transport"},
			fields=["parent", "card_equipment", "amount"],
			order_by="parent asc, idx asc",
		):
			shares[r.parent].append((r.card_equipment, flt(r.amount, 2)))
	for t in transports:
		if not shares[t.name]:
			shares[t.name] = [(None, flt(t.amount, 2))]
	return shares


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
	cost_center = card_cost_center(card, card.company)
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
			"cost_center": cost_center,
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
				"cost_center": cost_center,
				"card_equipment": card.equipment,
				"taxable": 1 if (typ is None or typ.taxable) else 0,
				"description": "{0} — {1} — {2}".format(
					(typ.type_name if typ else adj.adjustment_type), card.name, adj.description or ""
				),
			}
		)
	_assert_identity(card, total, expected, side)
	return card, lines, discount


def build_monthly_posting(company, party_type, party, month, year, reviewed_invoices=None):
	"""Create ONE draft posting (PI for a Supplier, SI for a Customer) for the
	party's unposted submitted sources of that month. Returns the invoice name.
	reviewed_invoices: supplier invoices of the month an accountant declared
	unrelated to these sources (P0 manual-invoice evidence)."""
	reviewed_invoices = list(reviewed_invoices or [])
	preflight.require_enabled()
	row = preflight.company_settings_row(company)
	first_day, last_day = _month_bounds(month, year)
	posting_doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
	preflight.require_item_read(posting_doctype)
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

	# G0 §5a: TYPE-FREE — one active posting unit per party-month-side, whatever
	# document type carries it; supplementary sequences count across all types.
	actives = frappe.get_all(
		"GL Posting Log",
		filters={
			"company": company,
			"party_type": party_type,
			"party": party,
			"month": "%02d" % int(month),
			"year": int(year),
			"status": ["in", list(ACTIVE_STATES)],
			# a linked hand-booked supplier invoice is not a CARD posting unit of the month
			"origin": ["in", ["Built", "", None]],
		},
		fields=["name", "posting_doc", "posting_doctype", "sequence"],
		order_by="sequence asc",
	)
	sequence = 1
	for active in actives:
		if frappe.db.get_value(active.posting_doctype, active.posting_doc, "docstatus") == 0:
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
		cards = _exclude_held(cards, "Card Monthly Card", party_type)
		fills = _exclude_held(fills, "Project Diesel Fill", party_type)
		transports = _exclude_held(transports, "Equipment Transport", party_type)
		for c in cards:
			card, card_lines, _discount = _card_lines(c.name, "Supplier", row, types)
			lines.extend(card_lines)
			sources["Card Monthly Card"].append((card.name, flt(card.net_amount, 2)))
		for fill in fills:
			cost_center = fill_cost_center(fill, company)
			for equipment, amount, share in _split_fill_by_allocation(fill, int(month), int(year), company):
				if fill.card_equipment or not equipment:
					# a direct fill (recorded) or a project-level line (unallocated)
					description = _("Diesel fill {0} — {1} L").format(fill.name, share)
				else:
					# a project-tank fill split by operating hours: each line states ITS
					# share of the litres, marked as an estimate (not measured) — #34
					description = _(
						"Diesel fill {0} — {1} L estimated share of {2} L (split by hours)"
					).format(fill.name, share, flt(fill.litres, 3))
				lines.append(
					{
						"item_code": row.diesel_item,
						"rate": amount,
						"account": row.diesel_expense_account,
						"project": fill.project,
						"cost_center": cost_center,
						"card_equipment": equipment,
						"taxable": 1,
						"description": description,
						"fill": fill.name,
					}
				)
			sources["Project Diesel Fill"].append((fill.name, flt(fill.amount, 2)))
		transport_shares = _transport_shares(transports)
		for t in transports:
			cost_center = _source_cost_center("Equipment Transport", t, company)
			description = _("Equipment transport {0}: {1} → {2}").format(
				t.name,
				t.source_project or t.source_location or t.from_location or "",
				(t.project if (t.destination_type or "Project") == "Project" else t.destination_location)
				or t.to_location
				or "",
			)
			# v3.0.0: one line per equipment share (the shares add up to the trip cost,
			# enforced on save), so each machine carries its own transport cost; a
			# transport with no equipment stays one project-level line
			for equipment, amount in transport_shares[t.name]:
				lines.append(
					{
						"item_code": row.transport_item,
						"rate": amount,
						"account": row.transport_expense_account,
						"project": t.project,
						"cost_center": cost_center,
						"card_equipment": equipment,
						"taxable": 1,
						"description": description,
					}
				)
			sources["Equipment Transport"].append((t.name, flt(t.amount, 2)))
	else:
		customer_cards = _exclude_held(
			_customer_cards(company, party, month, year), "Card Monthly Card", party_type
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
	diesel_note = _apply_diesel_vat_basis(row, lines, sources, tax_template, party)
	if party_type == "Supplier":
		# P0: hand-booked supplier invoices of the month that book to the CARD accounts or
		# items are evidence the same operations may already be expensed
		candidates = integrity.manual_invoice_candidates(
			company,
			party,
			first_day,
			last_day,
			{line["account"] for line in lines if line.get("account")},
			{line["item_code"] for line in lines if line.get("item_code")},
		)
		integrity.require_reviewed(candidates, reviewed_invoices)
	# P0: serialize concurrent builds/links of the same sources, then re-check membership
	integrity.lock_sources(sources)
	for doctype, rows in sources.items():
		held = _held_by_active_log(doctype, [name for name, _amount in rows], party_type)
		if held:
			frappe.throw(
				_("{0} {1} was just reserved by another posting; build again.").format(
					_(doctype), ", ".join(sorted(held))
				)
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
	# deterministic: generated postings are ALWAYS in the company currency —
	# never the ambient user/Global Defaults currency (a clean site defaults
	# to INR and ERPNext then rejects the SAR party account).
	inv.currency = frappe.get_cached_value("Company", company, "default_currency")
	inv.conversion_rate = 1
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
		# SI makes the selling price list mandatory; resolve it deterministically
		# (rates are explicit and pricing rules are ignored — it is a reference)
		inv.selling_price_list = ensure_selling_price_list(company)
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
			# the source document's own cost center when it has one, else the
			# company default from Card Company Settings (#34)
			"cost_center": line.get("cost_center") or row.cost_center,
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
	inv.reload()
	built = integrity.snapshot(inv)

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
			"origin": "Built",
			"built_signature": integrity.full_signature(built),
			"lines_signature": integrity.lines_signature(built),
			"built_snapshot": frappe.as_json(built),
			"reviewed_invoices": ", ".join(sorted(reviewed_invoices)) or None,
			"remarks": _build_remarks(diesel_note, reviewed_invoices),
		}
	)
	# The sources child table is the AUTHORITATIVE reservation list; the
	# lifecycle handlers (card/gl/events.py) iterate it on submit/cancel/trash.
	for doctype, rows in sources.items():
		for name, amount in rows:
			log.append("sources", {"source_doctype": doctype, "source_name": name, "amount": amount})
	log.flags.card_gl_build = True  # #57: only the builder creates logs (GLPostingLog.validate)
	log.insert(ignore_permissions=True)

	# gl_posting on the source is DISPLAY-ONLY (never the invoice itself: a
	# backlink from a submitted source would block cancelling the invoice).
	# The invoice link fields are written only on submit (card/gl/events.py).
	for doctype, rows in sources.items():
		for name, _amount in rows:
			_point_display(doctype, name, log.name)

	return inv.name


def rebuild_monthly_posting(company, party_type, party, month, year, reviewed_invoices=None):
	"""Late sources against a DRAFT posting: delete the draft (its reservations
	are freed by card.gl.events.on_trash) and build the month again so the new
	draft includes every unposted submitted document."""
	posting_doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
	preflight.require_item_read(posting_doctype)  # before deleting the old draft
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
			# never a linked hand-booked supplier invoice: only CARD's own drafts are rebuilt
			"origin": ["in", ["Built", "", None]],
		},
		fields=["posting_doc"],
	):
		if frappe.db.get_value(posting_doctype, active.posting_doc, "docstatus") == 0:
			frappe.delete_doc(posting_doctype, active.posting_doc, ignore_permissions=True)
	return build_monthly_posting(company, party_type, party, month, year, reviewed_invoices)


def _build_remarks(diesel_note, reviewed_invoices):
	parts = [diesel_note]
	if reviewed_invoices:
		parts.append(
			_("Reviewed as unrelated by {0}: {1}.").format(
				frappe.session.user, ", ".join(sorted(reviewed_invoices))
			)
		)
	return " ".join(p for p in parts if p) or None


def _vat_rate(template):
	"""The single VAT rate of a purchase tax template (multi-rate templates are refused by preflight)."""
	rates = {
		flt(r.rate)
		for r in frappe.get_all(
			"Purchase Taxes and Charges",
			filters={"parent": template, "parenttype": "Purchase Taxes and Charges Template"},
			fields=["rate"],
		)
		if flt(r.rate) > 0
	}
	if len(rates) != 1:
		frappe.throw(_("Tax template {0} must have exactly one VAT rate to post diesel.").format(template))
	return rates.pop()


def _apply_diesel_vat_basis(row, lines, sources, tax_template, party):
	"""P0 diesel VAT basis. With VAT input (a VAT-registered supplier) the fill price
	must be known to include or exclude VAT: Exclusive keeps the line at the fill
	amount (VAT is added), Inclusive books the net part so the invoice total stays
	the fill amount and VAT is not added twice; not set = refused for review.
	Without VAT input the fill amount is the whole cost either way."""
	fill_lines = [line for line in lines if line.get("fill")]
	if not fill_lines or not tax_template:
		return None
	basis = row.get("diesel_price_vat_basis")
	if not basis:
		frappe.throw(
			_(
				"The VAT basis of the diesel price is not verified for company {0} (Card Settings: Diesel price VAT basis); supplier {1} is VAT-registered, so fills {2} need review before posting."
			).format(row.company, party, ", ".join(sorted({line["fill"] for line in fill_lines}))),
			title=_("Diesel VAT basis needs review"),
		)
	if basis != "Inclusive":
		return None
	rate = _vat_rate(tax_template)
	gross = flt(sum(flt(line["rate"], 2) for line in fill_lines), 2)
	net_by_fill = {}
	for line in fill_lines:
		line["rate"] = flt(flt(line["rate"], 2) * 100 / (100 + rate), 2)
		line["description"] = "{0} ({1})".format(line["description"], _("price incl. VAT, net booked"))
		net_by_fill[line["fill"]] = flt(net_by_fill.get(line["fill"], 0) + line["rate"], 2)
	sources["Project Diesel Fill"] = [
		(name, net_by_fill.get(name, amount)) for name, amount in sources["Project Diesel Fill"]
	]
	net = flt(sum(net_by_fill.values()), 2)
	vat = flt(net * rate / 100, 2)
	return _("Diesel price includes VAT: fills gross {0}, net booked {1}, VAT {2} (rounding {3}).").format(
		gross, net, vat, flt(gross - net - vat, 2)
	)


def _checked_endpoint_args(company, party_type, month, year):
	"""Shared gate for the whitelisted entry points: role, company scope, party
	type, period. The builder inserts with ignore_permissions, so the company the
	caller may see is enforced here, before any work (#36)."""
	if not ({"Card Manager", "System Manager"} & set(frappe.get_roles())):
		frappe.throw(
			_("Only Card Manager or System Manager may build monthly postings."), frappe.PermissionError
		)
	# the sources it reads AND the documents it writes (security review LOW-1)
	written = (
		("Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"),
		"GL Posting Log",
	)
	if not company or company not in permitted_companies(*POSTING_SOURCE_DOCTYPES, *written):
		frappe.throw(
			_("You are not permitted to build postings for company {0}.").format(company),
			frappe.PermissionError,
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


def _check_party(party_type, party):
	"""The caller must be able to read the party (a User Permission on Supplier /
	Customer applies too) — security review LOW-1."""
	if not party or not frappe.has_permission(party_type, "read", party):
		frappe.throw(
			_("You are not permitted to build postings for {0} {1}.").format(_(party_type), party),
			frappe.PermissionError,
		)


@frappe.whitelist(methods=["POST"])
def rebuild_month(
	company: str,
	party_type: str,
	party: str,
	month: str,
	year: str,
	reviewed_invoices: str | list | None = None,
):
	"""Desk entry point for rebuilding a draft posting after late documents."""
	month, year = _checked_endpoint_args(company, party_type, month, year)
	_check_party(party_type, party)
	return rebuild_monthly_posting(company, party_type, party, month, year, _as_list(reviewed_invoices))


@frappe.whitelist(methods=["POST"])
def post_month(
	company: str,
	party_type: str,
	party: str,
	month: str,
	year: str,
	reviewed_invoices: str | list | None = None,
):
	"""Desk entry point (S4 wires the button). Card Manager / System Manager only.
	reviewed_invoices: supplier invoices an accountant declares unrelated (P0)."""
	month, year = _checked_endpoint_args(company, party_type, month, year)
	_check_party(party_type, party)
	return build_monthly_posting(company, party_type, party, month, year, _as_list(reviewed_invoices))


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.strip().startswith("[") else [value]
	return [str(v) for v in value if v]
