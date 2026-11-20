# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Show the addition/deduction date to users who saved their own columns for the table.

Frappe shows only the saved columns of a child table when a user chose them with "Configure columns"
(GridView user settings). A user who did that before v4.10.0 never sees the new required Adjustment date
column. This patch puts that column first in every saved column list of the table that does not have it.
The other saved columns, their order and widths stay as the user chose them. Only user display settings
change; no document, amount or permission changes. A second run changes nothing."""

import json

import frappe
from frappe.model.utils.user_settings import clear_user_settings_cache, sync_user_settings

PARENT = "Card Monthly Card"
CHILD = "Card Monthly Card Adjustment"
FIELD = "adjustment_date"


def add_date_column(data):
	"""Return the settings with the date column added, or None when nothing changes."""
	grid = (data or {}).get("GridView") if isinstance(data, dict) else None
	columns = grid.get(CHILD) if isinstance(grid, dict) else None
	if not columns or not isinstance(columns, list):
		return None  # no saved columns: Frappe shows the DocType's list-view columns, date included
	if any(isinstance(c, dict) and c.get("fieldname") == FIELD for c in columns):
		return None
	grid[CHILD] = [{"fieldname": FIELD, "sticky": 0}, *columns]
	return data


def execute():
	# As in frappe's own user-settings patches: write the cached settings to the database first, so that a
	# later sync of an old cached copy cannot remove the column again; the cache is cleared at the end.
	sync_user_settings()
	for user, raw in frappe.db.sql("select `user`, `data` from `__UserSettings` where `doctype`=%s", PARENT):
		try:
			data = json.loads(raw or "{}")
		except ValueError:
			continue  # unreadable settings are left as they are
		new = add_date_column(data)
		if new is not None:
			frappe.db.sql(
				"update `__UserSettings` set `data`=%s where `user`=%s and `doctype`=%s",
				(json.dumps(new), user, PARENT),
			)
	clear_user_settings_cache(PARENT)
