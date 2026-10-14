# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""F.8: CARD runs on exactly ONE company (owner 2026-10-14). Whenever a company
is needed it is THE existing company, and creating/importing additional
(subsidiary) companies is blocked — via a standard doc_events hook, no core
edits. The first company (setup wizard / install) is always allowed, and
tests/migrations are exempt so QA suites that build scratch companies keep
working."""

import frappe
from frappe import _


def single_company():
	"""THE company of this system (None only before setup)."""
	return frappe.db.get_value("Company", {}, "name", order_by="creation asc")


def block_additional_companies(doc, method=None):
	"""doc_events: Company.before_insert."""
	if (
		frappe.flags.in_test
		or frappe.flags.in_install
		or frappe.flags.in_setup_wizard
		or frappe.flags.in_migrate
		or frappe.flags.in_patch
	):
		return
	existing = single_company()
	if existing:
		frappe.throw(
			_("CARD runs on a single company ({0}); creating additional companies is not allowed.").format(
				existing
			)
		)
