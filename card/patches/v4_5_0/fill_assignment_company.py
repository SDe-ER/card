# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""R1: Card Equipment Assignment gets a read-only company (the equipment's) and, where empty,
its project's cost center when that is an active ledger cost center of the company. Fills
only empty values; idempotent."""

import frappe


def execute():
	frappe.reload_doc("card", "doctype", "card_equipment_assignment")
	for row in frappe.get_all(
		"Card Equipment Assignment",
		filters={"company": ["is", "not set"]},
		fields=["name", "equipment"],
	):
		company = frappe.db.get_value("Card Equipment", row.equipment, "company")
		if company:
			frappe.db.set_value(
				"Card Equipment Assignment", row.name, "company", company, update_modified=False
			)
	from card.card.doctype.card_equipment_assignment.card_equipment_assignment import _valid_cost_center

	for row in frappe.get_all(
		"Card Equipment Assignment",
		filters={"cost_center": ["is", "not set"], "project": ["is", "set"]},
		fields=["name", "project", "company"],
	):
		cc = frappe.db.get_value("Project", row.project, "cost_center")
		if cc and _valid_cost_center(cc, row.company):
			frappe.db.set_value(
				"Card Equipment Assignment", row.name, "cost_center", cc, update_modified=False
			)
