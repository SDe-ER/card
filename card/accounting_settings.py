# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Read-only first-run guard helpers for CARD accounting.

Used only by accounting features (none yet). Existing CARD behaviour never
imports this module, so it keeps working with no Card Settings configured.
"""

import frappe
from frappe import _


def is_accounting_enabled():
	try:
		return bool(frappe.db.get_single_value("Card Settings", "enable_accounting"))
	except Exception:
		return False


def get_company_settings(company, throw=True):
	"""Return the Card Company Settings row for `company`, or a friendly
	translated message when missing. Never a traceback. Called only by
	accounting features (none yet)."""
	if not company:
		if throw:
			frappe.throw(_("Company is required for Card accounting."))
		return None
	row = None
	try:
		doc = frappe.get_single("Card Settings")
		for r in doc.get("company_settings") or []:
			if r.company == company:
				row = r
				break
	except Exception:
		row = None
	if not row:
		if throw:
			frappe.throw(_("Configure Card Settings for company {0}").format(company))
		return None
	return row
