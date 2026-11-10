# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Crusher Owner Statement (Script Report, read-only, Owner 2026-11-10).

What each owner of third-party equipment is due from the monthly cards, the deductions by type, the
owner's party ledger (payments, recharges, reclasses, transfers, manual accruals) and the balance.
Tree: Family -> Owner -> Equipment -> Month. The rules are in ``card.owner_statement``.

Access: the report roles, one company the user may see; ledger figures (cost-center expenses, party
ledger) only for users who may read the General Ledger, wages only for users who may read Salary
Slips. Without them the entitlement is marked incomplete and no ledger figure reaches the browser."""

import frappe
from frappe import _
from frappe.utils import flt

from card import owner_statement as os_
from card.constants import OWNER_MODELS
from card.report_access import (
	can_view_ledger,
	ledger_notice,
	permitted_companies,
	readable_links,
	resolve_company,
	role_reads,
)
from card.report_currency import company_currency_report

STATUS_LABELS = {
	os_.PENDING: "Pending",
	os_.APPROVED: "Approved",
	os_.PARTIAL: "Partially approved",
	os_.REJECTED: "Rejected",
}


def can_view_wages(company):
	"""Wages are payroll data: shown only to a user whose roles read Salary Slips in bulk (no owner
	restriction), with no User Permission limiting Employee or Salary Slip, and who may see the company's
	Salary Slips. A user who reads only his own slip (the HRMS Employee role) never qualifies. Without
	HRMS there are no Salary Slips, so nothing is hidden."""
	if not frappe.db.table_exists("Salary Slip"):
		return True  # no payroll on the site: there are no wages to hide
	if not role_reads("Salary Slip"):
		return False
	if frappe.session.user != "Administrator":
		limits = frappe.permissions.get_user_permissions(frappe.session.user)
		if limits.get("Employee") or limits.get("Salary Slip"):
			return False
	return company in permitted_companies("Salary Slip")


@company_currency_report()
def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters)
	start, end = os_.period(filters.from_month, filters.from_year, filters.to_month, filters.to_year)
	if filters.owner_model and filters.owner_model not in OWNER_MODELS:
		frappe.throw(_("Invalid owner model {0}.").format(filters.owner_model))
	show_ledger = can_view_ledger(company)
	show_wages = can_view_wages(company)

	family = filters.family
	owners = []
	if filters.owner:
		# a payment to one member is the family's: an owner of a family is always shown with it
		family = family or os_.family_of(filters.owner)
		owners = [filters.owner]
	if family:
		members = os_.family_members(company, family)
		if filters.owner and filters.owner not in members:
			frappe.throw(_("Owner {0} is not a member of family {1}.").format(filters.owner, family))
		owners = members
	columns = get_columns(show_ledger)
	if not owners:
		return columns, [], _("Select an owner or a family to display the statement.")

	statement = os_.build_statement(
		company,
		owners,
		start,
		end,
		equipment=filters.equipment,
		owner_model=filters.owner_model,
		family=family,
		show_ledger=show_ledger,
		show_wages=show_wages,
	)
	rows = build_rows(statement, family, show_ledger)
	summary = build_summary(statement, family, show_ledger)
	message = statement_message(company, start, end, family, show_ledger, show_wages)
	if statement.warnings:
		message = message + " " + " ".join(statement.warnings)
	columns = readable_links(columns, rows)
	return columns, rows, message, None, summary, True


def build_rows(statement, family, show_ledger):
	rows = []
	vat = vat_shares([m for m in statement.months if m.in_period])
	root = None
	if family:
		root = "F|" + family
		f = statement.family
		rows.append(
			{
				"row_id": root,
				"parent_row": None,
				"indent": 0,
				"label": _("Family: {0}").format(family),
				"entitlement": f.entitlement if f.complete else None,
				"opening": f.opening if show_ledger and f.complete else None,
				"payments_unallocated": f.payments if show_ledger else None,
				"closing": f.closing if show_ledger and f.complete else None,
				"note": None if f.complete else _("Incomplete: figures you may not see are missing."),
				"bold": 1,
			}
		)
	for owner, o in statement.owners.items():
		owner_id = (root + "|" if root else "") + "O|" + owner
		row = {
			"row_id": owner_id,
			"parent_row": root,
			"indent": 1 if root else 0,
			"label": owner,
			"owner": owner,
			"confirmed_revenue": o.confirmed,
			"pending_potential": o.pending,
			"deductions": o.deductions,
			"entitlement": o.entitlement if o.complete else None,
			"bold": 1,
		}
		if not o.complete:
			row["note"] = _("Incomplete: figures you may not see are missing.")
		if show_ledger:
			row.update(
				{
					"opening": o.opening,
					"payments_allocated": None if family else o.payments_allocated,
					"payments_unallocated": None if family else o.payments_unallocated,
					"recharges": o[os_.RECHARGE],
					"reclasses": o[os_.RECLASS],
					"transfers": o[os_.TRANSFER],
					"accruals": o.accruals,
					"other_adjustments": o[os_.ADJUSTMENT],
					"duplicate_accruals": o.duplicate_accruals,
					"closing": o.closing if o.complete else None,
				}
			)
			if not o.complete:
				row["opening"] = None
			elif family and o[os_.PAYMENT]:
				row["note"] = _("Family payment — not yet allocated: {0}").format(
					frappe.format_value(o[os_.PAYMENT], {"fieldtype": "Currency"})
				)
			elif family:
				row["note"] = _("Balance before family payments")
		rows.append(row)
		shown = [m for m in statement.months if m.owner == owner and m.shown]
		names = sorted({m.equipment for m in shown})
		for machine in [m for m in statement.machines if m.name in names]:
			eq_id = owner_id + "|E|" + machine.name
			months = [m for m in shown if m.equipment == machine.name and m.in_period]
			final = [m for m in months if m.final]
			rows.append(
				{
					"row_id": eq_id,
					"parent_row": owner_id,
					"indent": row["indent"] + 1,
					"label": machine.equipment_name or machine.name,
					"equipment": machine.name,
					"owner_model": _(machine.owner_model) if machine.owner_model else None,
					"confirmed_revenue": flt(sum(m.confirmed for m in final), 2),
					"pending_potential": flt(sum(m.pending for m in final), 2),
					"deductions": flt(sum(m.deductions for m in final), 2),
					"entitlement": flt(sum(m.entitlement for m in final), 2)
					if all(m.complete for m in final)
					else None,
					"bold": 1,
				}
			)
			for m in months:
				rows.append(month_row(m, eq_id, row["indent"] + 2, vat, show_ledger))
		if show_ledger:
			for line in o.ledger_lines:
				rows.append(ledger_row(line, owner_id, row["indent"] + 1))
	return rows


def month_row(m, parent, indent, vat, show_ledger):
	label = os_.month_label(m.month)
	if not m.final:
		label = label + " " + _("(Draft — not in the dues)")
	notes = []
	if m.get("no_card"):
		notes.append(_("Deductions recorded in a month with no card of this owner on the machine."))
	if m.approval_mismatch:
		notes.append(_("A card row changed after its approval was recorded; the smaller amount is used."))
	if m.check:
		notes.append(_("The customer net is not fully explained: {0}").format(m.check))
	if m.no_cost_center:
		notes.append(_("The equipment has no cost center: expenses not computed."))
	if m.unclassified:
		notes.append(_("Untyped customer rows kept as the company's: {0}").format(m.unclassified))
	row = {
		"row_id": parent + "|M|" + label + "|" + ",".join(m.cards),
		"parent_row": parent,
		"indent": indent,
		"label": label,
		"equipment": m.equipment,
		"cards": ", ".join(m.cards),
		"customer_net": m.customer_net,
		"conditional_gross": m.conditional_gross,
		"approval_status": ", ".join(_(STATUS_LABELS.get(s, s)) for s in m.approval_status),
		"approval_record": m.approval_records[0] if len(m.approval_records) == 1 else None,
		"approved_amount": m.approved,
		"confirmed_revenue": m.confirmed,
		"pending_potential": m.pending,
		"excluded_amount": m.excluded,
		"company_rows": m.company_rows,
		"wages": m.wages,
		"shared_expenses": m.shared_expenses,
		"paid_on_behalf": m.paid_on_behalf,
		"other_deductions": flt(m.recorded_wages + m.other_deductions, 2),
		"deductions": m.deductions,
		"entitlement": m.entitlement if m.complete else None,
		"vat_company": vat.get(tuple(m.cards)),
		"note": " ".join(notes)
		or (None if m.complete else _("Incomplete: figures you may not see are missing.")),
	}
	if show_ledger:
		row["expenses"] = m.expenses
	return row


def ledger_row(line, parent, indent):
	kind_labels = {
		os_.PAYMENT: _("Payment"),
		os_.RECHARGE: _("Recharge / paid on behalf"),
		os_.RECLASS: _("Reclass"),
		os_.TRANSFER: _("Inter-owner transfer"),
		os_.ACCRUAL: _("Manual accrual"),
		os_.ADJUSTMENT: _("Other adjustment"),
	}
	label = kind_labels.get(line.kind, line.kind)
	if line.duplicate:
		label = _("Possible duplicate accrual")
	return {
		"row_id": parent + "|L|" + line.name,
		"parent_row": parent,
		"indent": indent,
		"label": label + " — " + str(line.posting_date),
		"voucher_type": line.voucher_type,
		"voucher_no": line.voucher_no,
		"account": line.account,
		"ledger_amount": line.effect,
		"note": _("Counterparty: {0}").format(line.counterparty) if line.counterparty else None,
	}


def vat_shares(months):
	"""The company's VAT on the submitted Sales Invoices of the month's cards, shared by the
	cards' customer net (an invoice may bill several cards). Only for Sales Invoice readers."""
	out = {}
	if not role_reads("Sales Invoice"):
		return out
	names = {c for m in months for c in m.cards}
	if not names:
		return out
	cards = frappe.get_all(
		"Card Monthly Card",
		filters=[["name", "in", list(names)], ["sales_invoice", "is", "set"]],
		fields=["name", "sales_invoice", "customer_net_amount"],
		limit_page_length=0,
	)
	invoices = {c.sales_invoice for c in cards}
	if not invoices:
		return out
	si = {
		i.name: i
		for i in frappe.get_all(
			"Sales Invoice",
			filters=[["name", "in", list(invoices)], ["docstatus", "=", 1]],
			fields=["name", "net_total", "total_taxes_and_charges"],
			limit_page_length=0,
		)
	}
	by_card = {}
	for c in cards:
		inv = si.get(c.sales_invoice)
		if inv and flt(inv.net_total):
			by_card[c.name] = (
				flt(inv.total_taxes_and_charges) * flt(c.customer_net_amount) / flt(inv.net_total)
			)
	for m in months:
		if any(c in by_card for c in m.cards):
			out[tuple(m.cards)] = flt(sum(by_card.get(c, 0) for c in m.cards), 2)
	return out


def build_summary(statement, family, show_ledger):
	owners = statement.owners.values()
	summary = [
		{
			"key": "confirmed",
			"label": _("Confirmed owner revenue"),
			"value": flt(sum(o.confirmed for o in owners), 2),
			"datatype": "Currency",
			"indicator": "Blue",
		},
		{
			"key": "pending",
			"label": _("Pending approval (potential, not due)"),
			"value": flt(sum(o.pending for o in owners), 2),
			"datatype": "Currency",
			"indicator": "Orange",
		},
		{
			"key": "deductions",
			"label": _("Deductions"),
			"value": flt(sum(o.deductions for o in owners), 2),
			"datatype": "Currency",
			"indicator": "Red",
		},
	]
	complete = all(o.complete for o in owners)
	if complete:
		summary.append(
			{
				"key": "entitlement",
				"label": _("Owner entitlement for the period"),
				"value": flt(sum(o.entitlement for o in owners), 2),
				"datatype": "Currency",
				"indicator": "Green",
			}
		)
	if show_ledger and complete:
		if family:
			opening, paid, closing = (
				statement.family.opening,
				statement.family.payments,
				statement.family.closing,
			)
		else:
			opening = flt(sum(o.opening for o in owners), 2)
			paid = flt(sum(o[os_.PAYMENT] for o in owners), 2)
			closing = flt(sum(o.closing for o in owners), 2)
		summary += [
			{
				"key": "opening",
				"label": _("Opening balance"),
				"value": opening,
				"datatype": "Currency",
				"indicator": "Grey",
			},
			{
				"key": "paid",
				"label": _("Payments"),
				"value": paid,
				"datatype": "Currency",
				"indicator": "Orange",
			},
			{
				"key": "duplicates",
				"label": _("Possible duplicate accruals (not counted)"),
				"value": flt(sum(o.duplicate_accruals for o in owners), 2),
				"datatype": "Currency",
				"indicator": "Red",
			},
			{
				"key": "closing",
				"label": _("Closing balance due to the owner"),
				"value": closing,
				"datatype": "Currency",
				"indicator": "Red" if closing > 0 else "Green",
			},
		]
	return summary


def statement_message(company, start, end, family, show_ledger, show_wages):
	parts = [
		company + " — " + _("Crusher owner statement — Period from {0} to {1}.").format(start, end),
		_(
			"Amounts before VAT; VAT is the company's. Draft months and pending or disputed amounts are not in the dues."
		),
	]
	if family:
		parts.append(_("A payment to any family member is a family payment."))
	if not show_ledger:
		parts.append(ledger_notice())
	if not show_wages:
		parts.append(_("Wages are shown only to users who may read Salary Slips."))
	return " ".join(parts)


def get_columns(show_ledger):
	cur = "Currency"
	columns = [
		{"fieldname": "label", "label": _("Description"), "fieldtype": "Data", "width": 260},
		{"fieldname": "owner", "label": _("Owner"), "fieldtype": "Link", "options": "Supplier", "width": 120},
		{
			"fieldname": "equipment",
			"label": _("Equipment"),
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 100,
		},
		{"fieldname": "owner_model", "label": _("Owner model"), "fieldtype": "Data", "width": 120},
		{"fieldname": "cards", "label": _("Cards"), "fieldtype": "Data", "width": 150},
		{"fieldname": "customer_net", "label": _("Customer net"), "fieldtype": cur, "width": 120},
		{
			"fieldname": "conditional_gross",
			"label": _("Conditional addition (generator)"),
			"fieldtype": cur,
			"width": 130,
		},
		{"fieldname": "approval_status", "label": _("Approval status"), "fieldtype": "Data", "width": 110},
		{
			"fieldname": "approval_record",
			"label": _("Approval evidence"),
			"fieldtype": "Link",
			"options": "Card Owner Revenue Approval",
			"width": 110,
		},
		{"fieldname": "approved_amount", "label": _("Approved amount"), "fieldtype": cur, "width": 110},
		{
			"fieldname": "confirmed_revenue",
			"label": _("Confirmed owner revenue"),
			"fieldtype": cur,
			"width": 130,
		},
		{"fieldname": "pending_potential", "label": _("Pending potential"), "fieldtype": cur, "width": 110},
		{"fieldname": "excluded_amount", "label": _("Not approved"), "fieldtype": cur, "width": 100},
		{"fieldname": "company_rows", "label": _("Company rows"), "fieldtype": cur, "width": 100},
	]
	if show_ledger:
		columns.append(
			{"fieldname": "expenses", "label": _("Cost-center expenses"), "fieldtype": cur, "width": 120}
		)
	columns += [
		{"fieldname": "wages", "label": _("Wages"), "fieldtype": cur, "width": 100},
		{"fieldname": "shared_expenses", "label": _("Shared expenses"), "fieldtype": cur, "width": 110},
		{"fieldname": "paid_on_behalf", "label": _("Paid on behalf"), "fieldtype": cur, "width": 110},
		{"fieldname": "other_deductions", "label": _("Other deductions"), "fieldtype": cur, "width": 110},
		{"fieldname": "deductions", "label": _("Total deductions"), "fieldtype": cur, "width": 120},
		{"fieldname": "entitlement", "label": _("Owner entitlement"), "fieldtype": cur, "width": 130},
		{"fieldname": "vat_company", "label": _("VAT (company's)"), "fieldtype": cur, "width": 100},
	]
	if show_ledger:
		columns += [
			{"fieldname": "opening", "label": _("Opening balance"), "fieldtype": cur, "width": 120},
			{
				"fieldname": "payments_allocated",
				"label": _("Payments allocated"),
				"fieldtype": cur,
				"width": 120,
			},
			{
				"fieldname": "payments_unallocated",
				"label": _("Payments unallocated"),
				"fieldtype": cur,
				"width": 120,
			},
			{
				"fieldname": "recharges",
				"label": _("Recharges / paid on behalf"),
				"fieldtype": cur,
				"width": 120,
			},
			{"fieldname": "reclasses", "label": _("Reclasses"), "fieldtype": cur, "width": 100},
			{"fieldname": "transfers", "label": _("Inter-owner transfers"), "fieldtype": cur, "width": 110},
			{
				"fieldname": "accruals",
				"label": _("Manual accruals (before cut-over)"),
				"fieldtype": cur,
				"width": 120,
			},
			{
				"fieldname": "other_adjustments",
				"label": _("Other adjustments"),
				"fieldtype": cur,
				"width": 110,
			},
			{
				"fieldname": "duplicate_accruals",
				"label": _("Possible duplicate accruals"),
				"fieldtype": cur,
				"width": 130,
			},
			{"fieldname": "closing", "label": _("Balance"), "fieldtype": cur, "width": 120},
			{"fieldname": "voucher_type", "label": _("Voucher type"), "fieldtype": "Data", "width": 110},
			{
				"fieldname": "voucher_no",
				"label": _("Voucher"),
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 140,
			},
			{
				"fieldname": "account",
				"label": _("Account"),
				"fieldtype": "Link",
				"options": "Account",
				"width": 140,
			},
			{
				"fieldname": "ledger_amount",
				"label": _("Ledger amount (+ due to owner)"),
				"fieldtype": cur,
				"width": 120,
			},
		]
	columns.append({"fieldname": "note", "label": _("Note"), "fieldtype": "Data", "width": 240})
	return columns
