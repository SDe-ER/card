# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Additions/deductions of monthly cards split by billed side.

A card's total_additions / total_deductions mix both sides (a sub-rental card
bills a supplier AND a customer), so per-side figures come from the rows. A
row without a side is a v1.1 row, counted on the supplier side — exactly what
backfill_adjustment_side stored and what net_amount was computed with."""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from card.constants import SUPPLIER_BILLING_DIRECTIONS

ADDITION = "إضافة"
DEDUCTION = "خصم"


def check_adjustment_date(description, adjustment_date, period_start, period_end):
	"""An addition/deduction is dated and falls inside its card's period (Owner, 2026-11-16):
	every movement must carry a date so the card and its statements can be computed by date."""
	if not adjustment_date:
		frappe.throw(_("Enter the date of the addition/deduction: {0}").format(description or ""))
	if not (getdate(period_start) <= getdate(adjustment_date) <= getdate(period_end)):
		frappe.throw(
			_("The date of the addition/deduction {0} must be inside the card period ({1} to {2}).").format(
				description or "", period_start, period_end
			)
		)


def sided_adjustments(card_names, side):
	"""{card name: (additions, deductions)} of ``side`` ("Supplier"/"Customer")
	for the given cards; cards without rows on that side are absent."""
	out = {}
	if not card_names:
		return out
	for r in frappe.get_all(
		"Card Monthly Card Adjustment",
		filters=[["parent", "in", list(card_names)], ["parenttype", "=", "Card Monthly Card"]],
		fields=["parent", "side", "adjustment_type", "amount", "is_cash_disbursement"],
		limit_page_length=0,
	):
		if cint(r.is_cash_disbursement):
			# recorded, not posted: a pending owner-paid cash row is in no statement total (owner decisions 2026-11-16)
			continue
		if (r.side or "Supplier") != side:
			continue
		add, ded = out.get(r.parent, (0.0, 0.0))
		if r.adjustment_type == ADDITION:
			add = flt(add + flt(r.amount), 2)
		elif r.adjustment_type == DEDUCTION:
			ded = flt(ded + flt(r.amount), 2)
		out[r.parent] = (add, ded)
	return out


DOWNTIME_PARTY_TYPES = ("Company", "Supplier", "Customer", "Other")


def validate_downtime_fields(adj, company, is_downtime_charge):
	"""FR-134 (#45, C-07): the explicit, audited route to charge for downtime.

	A row of an adjustment type flagged ``is_downtime_charge`` must name the stop reason
	(an enabled reason of the card's company), the responsible party and the agreement
	reference. On any other row these fields are optional, but a stop reason given there
	must still belong to the card's company. Returns the row's stop reason (or None)."""
	label = adj.description or adj.adjustment_type_ref or ""
	adj.agreement_reference = (adj.agreement_reference or "").strip() or None
	reason = None
	if adj.stop_reason:
		reason = frappe.db.get_value(
			"Card Stop Reason", adj.stop_reason, ["name", "company", "enabled", "billable"], as_dict=True
		)
		if not reason:
			frappe.throw(_("Stop reason {0} does not exist.").format(adj.stop_reason))
		if reason.company != company:
			frappe.throw(
				_("Stop reason {0} belongs to another company; choose a reason of company {1}.").format(
					adj.stop_reason, company
				),
				frappe.PermissionError,
			)
	_normalise_party(adj, company, label)
	if not is_downtime_charge:
		return reason
	missing = []
	if not adj.stop_reason:
		missing.append(_("Stop reason"))
	if not adj.responsible_party_type or (
		adj.responsible_party_type == "Other" and not (adj.responsible_party_name or "").strip()
	):
		missing.append(_("Responsible party"))
	elif adj.responsible_party_type in ("Supplier", "Customer") and not adj.responsible_party:
		missing.append(_("Responsible party record"))
	if not adj.agreement_reference:
		missing.append(_("Agreement reference"))
	if missing:
		frappe.throw(
			_("The downtime charge {0} needs: {1}.").format(label, _(", ", context="Card").join(missing))
		)
	if not cint(reason.enabled):
		frappe.throw(_("Stop reason {0} is disabled; choose an enabled reason.").format(adj.stop_reason))
	return reason


def _normalise_party(adj, company, label):
	party_type = adj.responsible_party_type
	if not party_type:
		adj.responsible_party = None
		adj.responsible_party_name = None
		return
	if party_type not in DOWNTIME_PARTY_TYPES:
		frappe.throw(_("Invalid responsible party type: {0}").format(party_type))
	if party_type == "Other":
		adj.responsible_party = None
		return
	adj.responsible_party_name = None
	if party_type == "Company":
		if not adj.responsible_party:
			adj.responsible_party = company
		elif adj.responsible_party != company:
			frappe.throw(
				_(
					"The responsible company of the downtime charge {0} must be the card's company {1}."
				).format(label, company)
			)


CASH_ACCOUNT_TYPE = "Cash"


def validate_cash_account(account, company):
	"""The account that pays a cash disbursement must be an enabled leaf of the same company whose
	Account Type is Cash (Petty Cash or Cash). The account number is not evidence: the type is read."""
	if not account:
		frappe.throw(_("Choose the cash account the expense was paid from."))
	row = frappe.db.get_value(
		"Account", account, ["company", "is_group", "disabled", "account_type"], as_dict=True
	)
	if not row:
		frappe.throw(_("Cash account {0} does not exist.").format(account))
	if row.company != company:
		frappe.throw(_("Cash account {0} belongs to another company.").format(account))
	if row.is_group or row.disabled:
		frappe.throw(_("Cash account {0} must be an enabled account, not a group.").format(account))
	if row.account_type != CASH_ACCOUNT_TYPE:
		frappe.throw(_("Account {0} is not a Cash account (its Account Type must be Cash).").format(account))


def validate_cash_row(adj, company, supplier, direction):
	"""Save-time checks of an owner-paid cash row. A Draft may be saved and edited with such a row; the
	row is only validated here. Returns True when the row is a cash disbursement (it is then excluded from
	the card's totals and its invoice recognition). Owner decisions 2026-11-16: the payment is made on behalf
	of the equipment owner, so the card must be supplier-billed and carry the owner's supplier."""
	if not cint(adj.get("is_cash_disbursement")):
		return False
	validate_cash_account(adj.get("cash_account"), company)
	if direction not in SUPPLIER_BILLING_DIRECTIONS or not supplier:
		frappe.throw(
			_(
				"The owner-paid cash row {0} needs a supplier-billed card with the equipment owner as its supplier."
			).format(adj.get("description") or "")
		)
	return True


def refuse_cash_rows_on_submit(rows, posted_rows=()):
	"""Submit gate: a cash row blocks the card's submission only until its payment is Posted (its Journal
	Entry exists). posted_rows holds the names of the rows whose payment is posted. A posted row is not an
	invoice line, so the monthly card submits without it."""
	pending = [
		r.get("description") or ""
		for r in rows or []
		if cint(r.get("is_cash_disbursement")) and r.get("name") not in set(posted_rows or ())
	]
	if pending:
		frappe.throw(
			_(
				"Cash paid on behalf of an equipment owner is recorded but not posted yet, so the card cannot be submitted: {0}."
			).format(", ".join(pending))
		)
