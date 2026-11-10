# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-123 test helpers: a CARD transaction (Card Monthly Card, Equipment Transport, Project
Diesel Fill) is cancelled only with a reason. Tests whose subject is not the reason itself
cancel with this one."""

import frappe

TEST_REASON = "Test cancel"


def with_reason(doc, reason=TEST_REASON):
	"""Give a loaded document the cancel reason a cancel request sends; other doctypes unchanged."""
	if doc.meta.has_field("cancel_reason"):
		doc.cancel_reason = reason
	return doc


def store_reason(doctype, name, reason=TEST_REASON):
	"""Store the reason on the submitted record, for a cancel request that loads the stored
	document (a Desk savedocs request built from the stored record, frappe.client.cancel)."""
	frappe.db.set_value(doctype, name, "cancel_reason", reason, update_modified=False)
