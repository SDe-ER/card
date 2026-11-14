"""Fail the screenshot job unless the per-m³ demo data that the volume-billing shots need exists.

Run inside the CI bench after seed_demo.py. Checks: the per-m³ equipment (basis "بالمتر المكعب") exists, its
monthly card exists, and the card has loads on its day rows. Prints only counts and names, no secrets.
"""

import frappe

PER_M3 = "بالمتر المكعب"

equipment = frappe.db.get_value(
	"Card Equipment",
	{"equipment_name": ["like", "%(WL-05)%"]},
	["name", "customer_rate_type"],
	as_dict=True,
)
basis_ok = bool(equipment) and equipment.customer_rate_type == PER_M3
card = frappe.db.get_value("Card Monthly Card", {"equipment": equipment.name}, "name") if equipment else None
loads = 0
if card:
	loads = frappe.db.sql(
		"select coalesce(sum(loads_count), 0) from `tabCard Monthly Card Day` where parent = %s", card
	)[0][0]
print(f"VERIFY per_m3_equipment={basis_ok} per_m3_card={bool(card)} loads={loads}")
if not (basis_ok and card and loads > 0):
	raise SystemExit("VERIFY FAILED: per-m3 equipment, card or loads missing")
