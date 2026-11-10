# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Additions/deductions of monthly cards split by billed side.

A card's total_additions / total_deductions mix both sides (a sub-rental card
bills a supplier AND a customer), so per-side figures come from the rows. A
row without a side is a v1.1 row, counted on the supplier side — exactly what
backfill_adjustment_side stored and what net_amount was computed with."""

import frappe
from frappe import _
from frappe.utils import cint, flt

ADDITION = "إضافة"
DEDUCTION = "خصم"


def sided_adjustments(card_names, side):
	"""{card name: (additions, deductions)} of ``side`` ("Supplier"/"Customer")
	for the given cards; cards without rows on that side are absent."""
	out = {}
	if not card_names:
		return out
	for r in frappe.get_all(
		"Card Monthly Card Adjustment",
		filters=[["parent", "in", list(card_names)], ["parenttype", "=", "Card Monthly Card"]],
		fields=["parent", "side", "adjustment_type", "amount"],
		limit_page_length=0,
	):
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
