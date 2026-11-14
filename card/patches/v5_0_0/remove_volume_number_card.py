# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-166: the volume (m³) number card was removed from the fixture before any release. Fixture sync only inserts or
updates listed records, so sites that imported it keep a Number Card whose method no longer exists.

This patch deletes that one Number Card row and nothing else. The Workspace content is rewritten by the workspace
fixture sync that runs after migrate, which also drops the link. It is safe to run twice: when the row is gone, the
patch does nothing. The row is removed with a direct delete, because the Workspace child row still references it
until the fixture sync runs; no submitted card or other record is touched."""

import frappe

VOLUME_CARD = "Volume last month (m³)"


def execute():
	if frappe.db.exists("Number Card", VOLUME_CARD):
		frappe.db.delete("Number Card", {"name": VOLUME_CARD})
