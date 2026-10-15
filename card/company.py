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
