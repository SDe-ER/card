# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Additions/deductions of monthly cards split by billed side.

A card's total_additions / total_deductions mix both sides (a sub-rental card
bills a supplier AND a customer), so per-side figures come from the rows. A
row without a side is a v1.1 row, counted on the supplier side — exactly what
backfill_adjustment_side stored and what net_amount was computed with."""

import frappe
from frappe.utils import flt

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
