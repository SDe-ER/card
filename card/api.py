# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import flt


def recompute_supplier(supplier):
	"""Recompute one supplier's registry record from ALL its submitted, non-owned cards.
	Shared by the refresh API and the Card Monthly Card submit/cancel events.
	Writes only to "Card Equipment Supplier"."""
	cards = frappe.get_all(
		"Card Monthly Card",
		filters=[["supplier", "=", supplier], ["docstatus", "=", 1], ["ownership", "!=", "ملك"]],
		fields=["equipment", "total_working_hours", "amount", "total_additions", "total_deductions", "year", "month"],
		limit_page_length=0,
	)
	eqs = set()
	hours = 0.0
	net = 0.0
	periods = []
	for c in cards:
		eqs.add(c.equipment)
		hours = hours + flt(c.total_working_hours)
		net = net + flt(c.amount) + flt(c.total_additions) - flt(c.total_deductions)
		periods.append(str(c.year) + "-" + str(c.month).zfill(2))
	periods = sorted(periods)

	if frappe.db.exists("Card Equipment Supplier", supplier):
		rec = frappe.get_doc("Card Equipment Supplier", supplier)
	else:
		rec = frappe.new_doc("Card Equipment Supplier")
		rec.supplier = supplier
	rec.equipment_count = len(eqs)
	rec.card_count = len(cards)
	rec.total_hours = flt(hours, 2)
	rec.total_net = flt(net, 2)
	rec.first_month = periods[0] if periods else None
	rec.last_month = periods[-1] if periods else None
	rec.last_refreshed = frappe.utils.now_datetime()
	if rec.is_new():
		rec.insert(ignore_permissions=True)
	else:
		rec.save(ignore_permissions=True)
	return {"supplier": supplier, "cards": len(cards), "net": flt(net, 2)}


@frappe.whitelist(methods=["POST"])
def refresh_supplier(supplier=None):
	"""Refresh one supplier, or all suppliers with submitted non-owned cards.
	Ported from Server Script "Card Equipment Supplier - Refresh" v1.1. System Manager only."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw("غير مسموح: هذه العملية لمدير النظام فقط")

	if supplier:
		suppliers = [supplier]
	else:
		suppliers = sorted(list(set(frappe.get_all(
			"Card Monthly Card",
			filters=[["docstatus", "=", 1], ["ownership", "!=", "ملك"], ["supplier", "is", "set"]],
			pluck="supplier", limit_page_length=0,
		))))

	done = []
	for one in suppliers:
		done.append(recompute_supplier(one))
	return done
