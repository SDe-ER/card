# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Equipment Supplier Statement for a date range (interim settlement, Owner 2026-11-22).

Read-only. The work of a range is computed from the card day rows dated inside it, priced with
the card's exact hourly rate (rate / daily hours, never the rounded rate shown on the equipment).
Additions and deductions count by their own date. The balance follows the rule the Owner approved
on 2026-11-22:

    previous_due = card work before the range
                   + VAT of CARD purchase invoices posted before the range
                   + supplier credits before the range that CARD did not post (opening, other invoices)
                   - supplier debits before the range (payments, advances, debit notes)
    current_due  = previous_due + work of the range + VAT and other credits of the range
                   - supplier debits of the range

Double-count guard: a supplier credit posted by a CARD voucher (a submitted GL Posting Log) is
never counted, because the card work already counts that liability; only the VAT of a CARD
purchase invoice is added, since card work is before VAT. Only submitted ledger entries count
(GL Entry exists only for submitted documents; cancelled ones are skipped)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate

from card.adjustments import ADDITION, DEDUCTION, sided_adjustments
from card.card.doctype.card_stop_reason.card_stop_reason import SIDE_BOTH, billable_side_of
from card.card_value import bills_full_days, day_billing_basis, exact_hourly_rate
from card.constants import SUPPLIER_BILLING_DIRECTIONS
from card.transfer import is_billed_day

SUPPLIER = "Supplier"
CARD_FIELDS = (
	"name",
	"equipment",
	"rate_type",
	"rate",
	"day_billing_basis",
	"day_billing_basis_used",
	"daily_hours_used",
	"hourly_rate_used",
	"card_direction",
	"amount",
	"docstatus",
	"from_date",
	"to_date",
)


def date_range(filters):
	"""(from_date, to_date) when both date filters are set, None when neither is (the month filters
	apply). One date alone is refused, so a user never gets the month statement by mistake."""
	if filters.get("from_date") and filters.get("to_date"):
		return getdate(filters.get("from_date")), getdate(filters.get("to_date"))
	if filters.get("from_date") or filters.get("to_date"):
		frappe.throw(_("Set both From date and To date, or clear both to use the months."))
	return None


def range_work(cards, start, end):
	"""{card name: work of the card from ``start`` to ``end``} for the supplier side.

	Each value: dates (billed days, as the statement counts them), hours, stopped (supplier-side
	billable stopped hours), amount, additions, deductions. Cards with nothing in the range are
	absent. A range that holds the whole card period uses the card's own stored amount, so a full
	month prints exactly what the card shows; a partial range prices its hours with the exact rate."""
	if not cards:
		return {}
	names = [c.name for c in cards]
	days = frappe.get_all(
		"Card Monthly Card Day",
		filters=[["parent", "in", names], ["parenttype", "=", "Card Monthly Card"]],
		fields=[
			"parent",
			"operation_date",
			"working_hours",
			"stopped_hours",
			"stop_reason",
			"reason_billable",
			"loads_count",
		],
		limit_page_length=0,
		parent_doctype="Card Monthly Card",
	)
	reasons = {r.stop_reason for r in days if r.stop_reason}
	side_of = {}
	if reasons:
		for r in frappe.get_all(
			"Card Stop Reason",
			filters={"name": ["in", list(reasons)]},
			fields=["name", "billable_side"],
			limit_page_length=0,
		):
			side_of[r.name] = billable_side_of(r)
	equipment = list({c.equipment for c in cards if c.equipment})
	daily_hours_of = {}
	if equipment:
		for e in frappe.get_all(
			"Card Equipment",
			filters=[["name", "in", equipment]],
			fields=["name", "daily_hours"],
			limit_page_length=0,
		):
			daily_hours_of[e.name] = flt(e.daily_hours)

	work = {}
	by_card = {c.name: c for c in cards}
	for r in days:
		d = getdate(r.operation_date) if r.operation_date else None
		if not d or d < start or d > end:
			continue
		h = flt(r.working_hours)
		stopped = 0.0
		if cint(r.reason_billable) and flt(r.stopped_hours) > 0:
			if side_of.get(r.stop_reason, SIDE_BOTH) in (SIDE_BOTH, SUPPLIER):
				stopped = flt(r.stopped_hours)
		billed = is_billed_day(r, include_loads=False)
		if not (billed or h > 0 or stopped > 0):
			continue  # a day without billed work does not list its card
		w = work.setdefault(r.parent, _empty())
		if billed:
			w["dates"].add(str(d))
		if h > 0:
			w["hours"] = w["hours"] + h
			w["work_days"] = w["work_days"] + 1
		elif stopped > 0:
			w["stop_days"] = w["stop_days"] + 1
		w["stopped"] = w["stopped"] + stopped

	for a in frappe.get_all(
		"Card Monthly Card Adjustment",
		filters=[["parent", "in", names], ["parenttype", "=", "Card Monthly Card"]],
		fields=["parent", "side", "adjustment_type", "amount", "is_cash_disbursement", "adjustment_date"],
		limit_page_length=0,
	):
		# a pending owner-paid cash row is in no statement total (as sided_adjustments)
		if cint(a.is_cash_disbursement) or (a.side or SUPPLIER) != SUPPLIER:
			continue
		# a row saved before adjustment dates were required (2026-11-16) counts on its card's last day
		card = by_card.get(a.parent)
		dated = a.adjustment_date or (card.to_date if card else None)
		if not dated or not (start <= getdate(dated) <= end):
			continue
		w = work.setdefault(a.parent, _empty())
		if a.adjustment_type == ADDITION:
			w["additions"] = flt(w["additions"] + flt(a.amount), 2)
		elif a.adjustment_type == DEDUCTION:
			w["deductions"] = flt(w["deductions"] + flt(a.amount), 2)

	for name, w in work.items():
		w["amount"] = _amount(by_card[name], w, start, end, daily_hours_of)
		w["hours"] = flt(w["hours"], 2)
		w["stopped"] = flt(w["stopped"], 2)
	return work


def _empty():
	return {
		"dates": set(),
		"hours": 0.0,
		"stopped": 0.0,
		"work_days": 0,
		"stop_days": 0,
		"amount": 0.0,
		"additions": 0.0,
		"deductions": 0.0,
	}


def _amount(card, w, start, end, daily_hours_of):
	"""Supplier amount of the card's days in the range, as the card itself prices them."""
	if card.card_direction not in SUPPLIER_BILLING_DIRECTIONS:
		return 0.0
	if card.from_date and card.to_date and start <= getdate(card.from_date) and getdate(card.to_date) <= end:
		return flt(card.amount, 2)
	submitted = card.docstatus == 1
	basis = day_billing_basis(
		card.day_billing_basis_used if submitted and card.day_billing_basis_used else card.day_billing_basis
	)
	if bills_full_days(card.rate_type, basis):
		return flt((w["work_days"] + w["stop_days"]) * flt(card.rate), 2)
	# a submitted card is priced with the hourly rate it was submitted with (snapshot); a draft with the
	# equipment's daily hours, as its own save does
	if submitted and flt(card.hourly_rate_used):
		return flt((w["hours"] + w["stopped"]) * flt(card.hourly_rate_used), 2)
	daily_hours = (
		flt(card.daily_hours_used)
		if submitted and flt(card.daily_hours_used)
		else daily_hours_of.get(card.equipment)
	)
	hourly = exact_hourly_rate(card.rate_type, flt(card.rate), daily_hours)
	return flt((w["hours"] + w["stopped"]) * hourly, 2)


def card_vouchers(company, supplier):
	"""{(doctype, name)} of the submitted CARD postings for this supplier (accrual JE or Purchase Invoice)."""
	return {
		(log.posting_doctype, log.posting_doc)
		for log in frappe.get_all(
			"GL Posting Log",
			filters={
				"company": company,
				"party_type": SUPPLIER,
				"party": supplier,
				"status": "Submitted",
			},
			fields=["posting_doctype", "posting_doc"],
			limit_page_length=0,
		)
		if log.posting_doctype and log.posting_doc
	}


def supplier_ledger(company, supplier, start, end):
	"""The supplier's ledger side of the balance, split before / inside the range.

	Returns a dict: before and period, each with paid, vat, other (credits CARD did not post),
	and payments (the debit entries of the range: date, voucher, remark, amount)."""
	vouchers = card_vouchers(company, supplier)
	out = {
		"before": {"paid": 0.0, "vat": 0.0, "other": 0.0},
		"period": {"paid": 0.0, "vat": 0.0, "other": 0.0},
		"payments": [],
	}
	for g in frappe.get_all(
		"GL Entry",
		filters=[
			["company", "=", company],
			["party_type", "=", SUPPLIER],
			["party", "=", supplier],
			["is_cancelled", "=", 0],
			["posting_date", "<=", end],
		],
		fields=["posting_date", "voucher_type", "voucher_no", "debit", "credit", "remarks"],
		order_by="posting_date asc, creation asc",
		limit_page_length=0,
	):
		part = out["before"] if getdate(g.posting_date) < start else out["period"]
		if flt(g.debit):
			part["paid"] = part["paid"] + flt(g.debit)
			if part is out["period"]:
				out["payments"].append(
					{
						"posting_date": g.posting_date,
						"voucher_type": g.voucher_type,
						"voucher_no": g.voucher_no,
						"remarks": g.remarks,
						"amount": flt(g.debit, 2),
					}
				)
		# double-count guard: a CARD posting's credit is the card work already counted
		if flt(g.credit) and (g.voucher_type, g.voucher_no) not in vouchers:
			part["other"] = part["other"] + flt(g.credit)

	invoices = [name for doctype, name in vouchers if doctype == "Purchase Invoice"]
	if invoices:
		for pi in frappe.get_all(
			"Purchase Invoice",
			filters=[["name", "in", invoices], ["docstatus", "=", 1], ["posting_date", "<=", end]],
			fields=["posting_date", "base_taxes_and_charges_added", "base_taxes_and_charges_deducted"],
			limit_page_length=0,
		):
			part = out["before"] if getdate(pi.posting_date) < start else out["period"]
			part["vat"] = (
				part["vat"] + flt(pi.base_taxes_and_charges_added) - flt(pi.base_taxes_and_charges_deducted)
			)
	for key in ("before", "period"):
		for field in ("paid", "vat", "other"):
			out[key][field] = flt(out[key][field], 2)
	return out


def previous_work(cards_before, start):
	"""Net supplier card work (amount + additions - deductions) dated before ``start``.

	A card that ends before ``start`` counts with its stored amount and all its supplier rows (no day
	rows are read); only a card that runs across ``start`` is split by its day rows and row dates."""
	if not cards_before:
		return 0.0
	ended = [c for c in cards_before if c.to_date and getdate(c.to_date) < start]
	ended_names = {c.name for c in ended}
	running = [c for c in cards_before if c.name not in ended_names]
	total = 0.0
	sided = sided_adjustments(list(ended_names), SUPPLIER)
	for c in ended:
		add, ded = sided.get(c.name, (0.0, 0.0))
		amount = flt(c.amount, 2) if c.card_direction in SUPPLIER_BILLING_DIRECTIONS else 0.0
		total = total + amount + add - ded
	for w in range_work(running, getdate("1900-01-01"), add_days(start, -1)).values():
		total = total + w["amount"] + w["additions"] - w["deductions"]
	return flt(total, 2)
