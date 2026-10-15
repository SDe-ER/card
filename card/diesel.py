# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Diesel allocation for CARD v1.2 (display/costing only — never posts GL and
never changes a card's net_amount).

A Project Diesel Fill is either charged in full to one equipment (its
`card_equipment` is set) or, for a project-tank fill (`card_equipment` empty),
split across the equipment that operated in the same project + month, pro-rata
by their total operating hours (all shifts) from submitted Card Monthly Cards.
When splitting, the last equipment (stable alphabetical order) absorbs the
rounding difference so the shares sum to the fill amount/litres exactly.
"""

import frappe
from frappe.utils import flt, getdate

# Sentinel key for project-tank diesel in a period with no operating hours (opt-in, see below)
UNALLOCATED = "__unallocated__"


def _month_year(date_value):
	d = getdate(date_value)
	return "%02d" % d.month, str(d.year)


def allocate_project_diesel(project, month, year, include_unallocated=False):
	"""Return {equipment: {"litres": float, "amount": float}} for one
	project + month across all SUBMITTED Project Diesel Fills in that period.
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

	# total operating hours per equipment in this project + month (submitted cards, all shifts)
	hours_rows = frappe.db.sql(
		"""
		select equipment, sum(total_working_hours) as hrs
		from `tabCard Monthly Card`
		where project = %s and month = %s and year = %s and docstatus = 1
		group by equipment
		""",
		(project, month, year),
		as_dict=True,
	)
	hours_map = {r.equipment: flt(r.hrs) for r in hours_rows if flt(r.hrs) > 0}

	fills = frappe.get_all(
		"Project Diesel Fill",
		filters={"project": project, "docstatus": 1},
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
		# project-tank fill: pro-rata by operating hours; last row absorbs rounding
		total_hours = sum(hours_map.values())
		if total_hours <= 0:
			if include_unallocated:
				add(UNALLOCATED, f.litres, f.amount)
			continue
		equipments = sorted(hours_map.keys())
		done_amt = 0.0
		done_lit = 0.0
		for i, eq in enumerate(equipments):
			if i == len(equipments) - 1:
				share_amt = flt(flt(f.amount) - done_amt, 2)
				share_lit = flt(flt(f.litres) - done_lit, 3)
			else:
				ratio = hours_map[eq] / total_hours
				share_amt = flt(flt(f.amount) * ratio, 2)
				share_lit = flt(flt(f.litres) * ratio, 3)
				done_amt += share_amt
				done_lit += share_lit
			add(eq, share_lit, share_amt)
	return result


@frappe.whitelist()
def get_card_diesel(card: str):
	"""Diesel allocated to one Card Monthly Card's equipment for its project +
	month. Display only; it is NEVER written back and NEVER affects net_amount."""
	doc = frappe.get_doc("Card Monthly Card", card)
	frappe.has_permission("Card Monthly Card", "read", doc.name, throw=True)
	if not (doc.project and doc.month and doc.year and doc.equipment):
		return {"litres": 0.0, "amount": 0.0, "company_bears": False}
	alloc = allocate_project_diesel(doc.project, doc.month, doc.year)
	share = alloc.get(doc.equipment, {"litres": 0.0, "amount": 0.0})
	# flag when the company bears the fuel (الوقود_على = الشركة) → the diesel is our cost
	fuel_on = frappe.db.get_value("Card Equipment", doc.equipment, "الوقود_على")
	return {
		"litres": flt(share["litres"], 3),
		"amount": flt(share["amount"], 2),
		"company_bears": fuel_on == "الشركة",
	}
