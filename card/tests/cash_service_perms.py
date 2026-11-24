# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Test helper: the accounting service identity's rights in the test site, without breaking other roles.

Frappe replaces a DocType's whole rights matrix with its Custom DocPerm rows as soon as one exists for it. A Custom
DocPerm that lists only the service role therefore removes every other role's rights on that DocType (found in CI:
Accounts Manager and System Manager lost write and cancel on Journal Entry). This helper copies the standard rows of
the DocType into Custom DocPerm first, so every other role keeps exactly its rights, and then the caller adds the
service role's own row. Test site only: production needs its own approved change.
"""

import frappe

COPY_SKIP = {
	"name",
	"parent",
	"parenttype",
	"parentfield",
	"idx",
	"docstatus",
	"creation",
	"modified",
	"modified_by",
	"owner",
}


def copy_standard_perms(doctype):
	"""Copy the standard DocPerm rows of ``doctype`` into Custom DocPerm, once per test (rolled back afterwards)."""
	if frappe.db.exists("Custom DocPerm", {"parent": doctype}):
		return
	rows = frappe.get_all("DocPerm", filters={"parent": doctype, "parenttype": "DocType"}, fields=["*"])
	for row in rows:
		values = {key: value for key, value in row.items() if key not in COPY_SKIP}
		frappe.get_doc({"doctype": "Custom DocPerm", **values, "parent": doctype}).insert(
			ignore_permissions=True
		)
	frappe.clear_cache(doctype=doctype)
