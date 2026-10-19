# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.0.0: create the Card Supervisor (desk) and Card Operator (worker page only) roles on
existing sites. The DocType sync creates a role named in a new DocType's permissions with
desk access on by default, before this patch runs, so the operator role is set to no desk
here once (Owner 2026-10-19: operators do not get the Desk by default). No user is given a
role."""

import frappe

from card.install import NO_DESK_ROLES, ensure_card_roles


def execute():
	ensure_card_roles()
	for role in NO_DESK_ROLES:
		if frappe.db.get_value("Role", role, "desk_access"):
			doc = frappe.get_doc("Role", role)
			doc.desk_access = 0
			doc.save(ignore_permissions=True)
