# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Diesel allocation for CARD v1.2 (display/costing only — never posts GL and
never changes a card's net_amount).

A Project Diesel Fill is either charged in full to one equipment (its
`card_equipment` is set) or, for a project-tank fill (`card_equipment` empty),
split across the equipment that operated in the same project + month, pro-rata
by their total operating hours (all shifts) from submitted Card Monthly Cards.
Splitting uses the ONE shared largest-remainder rule (split_by_weights), so the
GL posting and every display put the rounding difference on the SAME equipment
and the shares sum to the fill amount/litres exactly.
"""

import frappe
from frappe.utils import flt, getdate

# Sentinel key for project-tank diesel in a period with no operating hours (opt-in, see below)
UNALLOCATED = "__unallocated__"


def _month_year(date_value):
	d = getdate(date_value)
	return "%02d" % d.month, str(d.year)


def split_by_weights(amount, weights, precision=2):
	"""M6 — THE one largest-remainder split used by posting AND display:
	{key: share} summing EXACTLY to amount; the largest share absorbs the
	rounding drift (ties broken by sorted key order, deterministically).
	Empty/zero weights -> {} (callers keep the amount unallocated)."""
	total = sum(weights.values())
	if not total:
		return {}
	shares = {k: flt(flt(amount) * w / total, precision) for k, w in weights.items()}
	drift = flt(flt(amount) - sum(shares.values()), precision)
	if drift:
		largest = max(sorted(shares), key=lambda k: shares[k])
		shares[largest] = flt(shares[largest] + drift, precision)
	return shares


def project_operating_hours(project, month, year, company):
	"""{equipment: total operating hours} for one project + month across all
	SUBMITTED Card Monthly Cards (all shifts) of ONE company. The allocation
	basis for project-tank diesel — direct fills never influence these weights.
	``company`` is required: a project is not tied to one company, so an
	unscoped read would weight one company's fill by another's equipment."""
	rows = frappe.db.sql(
		"""
		select equipment, sum(total_working_hours) as hrs
		from `tabCard Monthly Card`
		where project = %s and month = %s and year = %s and company = %s and docstatus = 1
		group by equipment
		""",
		(project, "%02d" % int(month), str(year), company),
		as_dict=True,
	)
	return {r.equipment: flt(r.hrs) for r in rows if flt(r.hrs) > 0}


def allocate_project_diesel(project, month, year, company, include_unallocated=False):
	"""Return {equipment: {"litres": float, "amount": float}} for one
	project + month across all SUBMITTED Project Diesel Fills of ONE company in
	that period (fills and hour weights both scoped to ``company``).
	When include_unallocated is True, project-tank fills in a period with NO operating
	hours accumulate under the UNALLOCATED key instead of being dropped."""
	result = {}

	def add(equipment, litres, amount):
		row = result.setdefault(equipment, {"litres": 0.0, "amount": 0.0})
		row["litres"] = flt(row["litres"] + flt(litres), 3)
		row["amount"] = flt(row["amount"] + flt(amount), 2)

	if not project:
		return result
	month = "%02d" % int(month)
	year = str(year)
	hours_map = project_operating_hours(project, month, year, company)

	fills = frappe.get_all(
		"Project Diesel Fill",
		filters={"project": project, "company": company, "docstatus": 1},
		fields=["name", "card_equipment", "litres", "amount", "date"],
	)
	for f in fills:
		fm, fy = _month_year(f.date)
		if fm != month or fy != year:
			continue
		# direct fill: whole amount to the chosen equipment
		if f.card_equipment:
			add(f.card_equipment, f.litres, f.amount)
			continue
		# project-tank fill: pro-rata by operating hours via the SHARED split
		# rule (M6 — the remainder lands on the same equipment as in GL posting)
		amt_shares = split_by_weights(f.amount, hours_map, 2)
		if not amt_shares:
			if include_unallocated:
				add(UNALLOCATED, f.litres, f.amount)
			continue
		lit_shares = split_by_weights(f.litres, hours_map, 3)
		for eq in sorted(amt_shares):
			add(eq, lit_shares.get(eq, 0), amt_shares[eq])
	return result


@frappe.whitelist()
def get_card_diesel(card: str):
	"""Diesel allocated to one Card Monthly Card's equipment for its project +
	month. Display only; it is NEVER written back and NEVER affects net_amount."""
	doc = frappe.get_doc("Card Monthly Card", card)
	frappe.has_permission("Card Monthly Card", "read", doc.name, throw=True)
	if not (doc.project and doc.month and doc.year and doc.equipment):
		return {"litres": 0.0, "amount": 0.0, "company_bears": False}
	alloc = allocate_project_diesel(doc.project, doc.month, doc.year, doc.company)
	share = alloc.get(doc.equipment, {"litres": 0.0, "amount": 0.0})
	# flag when the company bears the fuel (الوقود_على = الشركة) → the diesel is our cost
	fuel_on = frappe.db.get_value("Card Equipment", doc.equipment, "الوقود_على")
	return {
		"litres": flt(share["litres"], 3),
		"amount": flt(share["amount"], 2),
		"company_bears": fuel_on == "الشركة",
	}
