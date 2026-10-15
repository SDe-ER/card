# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Reproduce the old implicit production default for new Card Equipment: before
v1.2, operator_on and الوقود_على had no explicit DocType default, so a new
record took the first Select option (المؤجر). v1.2 gives both a blank first
option and drives the new-record default from Card Settings, so set the two
Card Settings defaults to المؤجر — only when unset — so new equipment keeps
getting المؤجر exactly as before. Idempotent."""

import frappe

DEFAULT = "المؤجر"
FIELDS = ("default_operator_on", "default_fuel_charged_to")


def execute():
	if not frappe.db.exists("DocType", "Card Settings"):
		return
	doc = frappe.get_single("Card Settings")
	changed = False
	for fieldname in FIELDS:
		if not (doc.get(fieldname) or "").strip():
			doc.set(fieldname, DEFAULT)
			changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save(ignore_permissions=True)
