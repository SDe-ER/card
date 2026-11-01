# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Company scope of the FR-099/FR-100 records that belong to an equipment.

Same rule as Card Equipment Assignment / Card Equipment Part: a record belongs to the
company of its equipment. Frappe checks the create right before ``validate`` fills the
company, so the check is made on the equipment itself, for every path (list, read,
REST save, create): the equipment the request sends AND, for a saved record, the one it
has in the database must both belong to a permitted company. A controller can only deny.
"""

import frappe

READING = "Card Meter Reading"
ORDER = "Card Maintenance Order"
PLAN = "Card Maintenance Plan"


def _restricted(user, doctype):
	from card.party_registry import _restricted_companies

	return _restricted_companies(user or frappe.session.user, doctype, "Card Equipment")


def _in(companies):
	return ", ".join(frappe.db.escape(c) for c in companies)


def _equipment_companies(doc, field):
	names = {doc.get(field)}
	if not doc.is_new():
		names.add(frappe.db.get_value(doc.doctype, doc.name, field))
	names.discard(None)
	names.discard("")
	if not names:
		return None
	return frappe.get_all("Card Equipment", filters={"name": ["in", list(names)]}, pluck="company")


# ---------- Card Meter Reading ----------


def reading_query_conditions(user=None):
	companies = _restricted(user, READING)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	# legacy readings of an unmapped Asset carry the Asset's company only
	return f"`tab{READING}`.`company` in ({_in(companies)})"


def has_reading_permission(doc, ptype=None, user=None, debug=False):
	companies = _restricted(user, READING)
	if companies is None:
		return True
	owners = _equipment_companies(doc, "equipment")
	if owners is None:
		if doc.get("asset"):
			return frappe.db.get_value("Asset", doc.asset, "company") in companies
		return doc.get("company") in companies if doc.get("company") else True
	return all(c in companies for c in owners)


# ---------- Card Maintenance Order ----------


def order_query_conditions(user=None):
	companies = _restricted(user, ORDER)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	return (
		f"`tab{ORDER}`.`equipment` in"
		f" (select e.`name` from `tabCard Equipment` e where e.`company` in ({_in(companies)}))"
	)


def has_order_permission(doc, ptype=None, user=None, debug=False):
	companies = _restricted(user, ORDER)
	if companies is None:
		return True
	owners = _equipment_companies(doc, "equipment")
	return True if owners is None else all(c in companies for c in owners)


# ---------- Card Maintenance Plan ----------


def plan_query_conditions(user=None):
	"""Model plans are site-wide (readable by every plan reader); machine plans follow
	the machine's company."""
	companies = _restricted(user, PLAN)
	if companies is None:
		return ""
	if not companies:
		return f"`tab{PLAN}`.`applies_to` = 'Equipment Model'"
	return (
		f"(`tab{PLAN}`.`applies_to` = 'Equipment Model' or `tab{PLAN}`.`card_equipment` in"
		f" (select e.`name` from `tabCard Equipment` e where e.`company` in ({_in(companies)})))"
	)


def has_plan_permission(doc, ptype=None, user=None, debug=False):
	"""A company-restricted user may read model plans but never write them (they change
	the machines of every company); a machine plan follows the machine's company."""
	companies = _restricted(user, PLAN)
	if companies is None:
		return True
	applies = {doc.get("applies_to")}
	if not doc.is_new():
		applies.add(frappe.db.get_value(PLAN, doc.name, "applies_to"))
	if "Equipment Model" in applies and (ptype or "read") != "read":
		return False
	owners = _equipment_companies(doc, "card_equipment")
	return True if owners is None else all(c in companies for c in owners)


# ---------- R1: Card Personnel Assignment ----------
PERSONNEL = "Card Personnel Assignment"


def personnel_query_conditions(user=None):
	"""By the company stored on the assignment (the employee's company when it was made), so
	an employee who later changes company does not move his history to the new company."""
	companies = _restricted(user, PERSONNEL)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	return f"`tab{PERSONNEL}`.`company` in ({_in(companies)})"


def has_personnel_permission(doc, ptype=None, user=None, debug=False):
	"""The stored company of a saved row AND the company of the employee sent (the company
	field is filled only in validate, after Frappe's create check) must be permitted."""
	companies = _restricted(user, PERSONNEL)
	if companies is None:
		return True
	owners = set()
	if not doc.is_new():
		owners.add(frappe.db.get_value(PERSONNEL, doc.name, "company"))
	if doc.get("employee") and (doc.is_new() or not doc.get("company")):
		owners.add(frappe.db.get_value("Employee", doc.get("employee"), "company"))
	elif doc.get("company"):
		owners.add(doc.get("company"))
	owners.discard(None)
	return all(c in companies for c in owners)
