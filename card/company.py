# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""F.8 company helpers (owner amendment 2026-10-14): the system practically
runs ONE company, so whenever a company is needed it DEFAULTS to the existing
one — but a second company is never blocked. CARD enforces CONSISTENCY
instead: a document's company must match its equipment's company, and every
configured account must belong to its row's company."""

import frappe
from frappe import _


def single_company():
	"""The default company of this system (the configured global default when it
	exists, else the first one; None before setup)."""
	default = frappe.defaults.get_global_default("default_company")
	if default and frappe.db.exists("Company", default):
		return default
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def only_visible_company():
	"""The company a new CARD form fills in when the user may list exactly one; else
	None. Unlike single_company it never picks one of several: the field stays editable."""
	# select is enough: it is what lets the user pick the company in the link field, and
	# frappe.get_list lists with it when the user has no read (v4.1.2: Card Manager)
	if not (frappe.has_permission("Company", "read") or frappe.has_permission("Company", "select")):
		return None
	companies = frappe.get_list("Company", pluck="name", limit=2)
	return companies[0] if len(companies) == 1 else None


def validate_equipment_company(doc, equipment_fieldname="equipment"):
	"""The document's company must match its equipment's company."""
	equipment = doc.get(equipment_fieldname)
	if not equipment or not doc.get("company"):
		return
	eq_company = frappe.db.get_value("Card Equipment", equipment, "company")
	if eq_company and doc.company != eq_company:
		frappe.throw(
			_("Company {0} does not match the equipment's company {1}.").format(doc.company, eq_company)
		)
