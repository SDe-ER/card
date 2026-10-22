# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""F2: before this fix a supervisor's review stored the stock on hand on every line
(Equipment Needs Review Item.stock_qty), read without any stock permission, so every
reader of the review (Card User included) saw it in the form, REST, report view, export
and print. The hint is no longer stored: the form reads it live with the reader's own
ERPNext rights (card.materials.review_stock). Clear the stored figures. A hint only: no
quantity the supervisor entered, no request and no Material Request is touched.

The review keeps its Version history as audit evidence (nothing deleted or rewritten);
this patch counts the Versions that carry an old stock figure and prints the count.
Idempotent."""

import json

import frappe

CHILD = "Equipment Needs Review Item"


def version_carries_stock(data):
	try:
		parsed = json.loads(data or "{}")
	except ValueError:
		return '"stock_qty"' in (data or "")
	if not isinstance(parsed, dict):
		return False
	for row in parsed.get("row_changed") or []:
		# [table_field, idx, row_name, [[field, old, new], ...]]
		if len(row) > 3 and any(change and change[0] == "stock_qty" for change in row[3] or []):
			return True
	for row in (parsed.get("added") or []) + (parsed.get("removed") or []):
		if len(row) > 1 and isinstance(row[1], dict) and row[1].get("stock_qty"):
			return True
	return False


def execute():
	if not frappe.db.table_exists(CHILD) or not frappe.db.has_column(CHILD, "stock_qty"):
		return 0
	table = frappe.qb.DocType(CHILD)
	frappe.qb.update(table).set(table.stock_qty, 0).where(table.stock_qty != 0).run()
	kept = sum(
		1
		for v in frappe.get_all(
			"Version",
			filters={"ref_doctype": "Equipment Needs Review", "data": ["like", "%stock_qty%"]},
			fields=["data"],
			limit_page_length=0,
		)
		if version_carries_stock(v.data)
	)
	if kept:
		# visible in the migrate output; nothing is deleted or changed
		print(f"CARD review history kept with old stock figures: {kept} Version(s)")
	return kept
