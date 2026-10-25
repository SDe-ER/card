# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.1.2: the CARD launcher shows every entry the app ships again.

frappe 16 lays a site's (and each user's) `Dock` layer over the app's own dock, and a saved
layer is the whole rail: an entry the app ships later is not added to it
(frappe/desk/doctype/dock/dock.py, resolve_app_dock, keep_unnamed=False). A layer saved before
v3.0.0 shipped the launcher names only the Card dashboard, so the other nine entries
(Equipment, Movement & Transport, ..., Settings) never appear and /desk/card shows three items.

A layer last saved before the shipped dock (its file's `modified`) cannot have left those
entries out on purpose, so they are appended to it as references (inheriting icon and title),
in the shipped order. Rows already in the layer, their order and their hidden flags are kept;
nothing is deleted; a layer saved later is not touched. Reach stays with frappe: an entry the
user may not open is still filtered out when the dock resolves. Idempotent."""

import json
import os

import frappe
from frappe.utils import get_datetime

DESTINATION_FIELDS = ("link_type", "link_to", "url")


def execute():
	if not frappe.db.exists("DocType", "Dock"):
		return
	with open(os.path.join(frappe.get_app_path("card"), "dock", "card", "card.json"), encoding="utf-8") as f:
		shipped = json.load(f)
	shipped_at = get_datetime(shipped["modified"])
	for name in frappe.get_all("Dock", filters={"app": "card", "standard": 0}, pluck="name"):
		layer = frappe.get_doc("Dock", name)
		if get_datetime(layer.modified) >= shipped_at:
			continue
		named = {_key(row) for row in layer.items}
		missing = [row for row in shipped["items"] if _key(row) not in named]
		if not missing:
			continue
		for row in missing:
			layer.append("items", {**{f: row.get(f) for f in DESTINATION_FIELDS}, "added": 0, "hidden": 0})
		layer.save()


def _key(row):
	return "|".join(row.get(field) or "" for field in DESTINATION_FIELDS)
