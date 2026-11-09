# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Company transport cost per project, for the cost reports.

v3.0.0: only moves the company pays are its transport cost (Owner 2026-10-19). P1-2 (Owner
2026-10-31): a transport with a recorded responsibility counts when the company bears the cost, on its explicitly chosen
cost project — never on the destination; a move charged to a workshop, storage or overhead cost
center has no project. A transport recorded before P1-2 keeps its old rule (header project)."""

import frappe
from frappe.utils import flt


def transport_cost_by_project(company=None, from_date=None, to_date=None, project=None):
	"""{project: {"transports": n, "amount": total}} of submitted transports."""
	filters = [["docstatus", "=", 1]]
	if company:
		filters.append(["company", "=", company])
	if from_date:
		filters.append(["date", ">=", from_date])
	if to_date:
		filters.append(["date", "<=", to_date])
	rows = frappe.get_all(
		"Equipment Transport",
		filters=filters,
		fields=[
			"project",
			"cost_project",
			"cost_basis",
			"responsibility",
			"payer",
			"cost_bearer",
			"cost_borne_by",
			"amount",
		],
		limit_page_length=0,
	)
	totals = {}
	for row in rows:
		if row.responsibility:
			# only a move whose cost the company finally bears, on its chosen cost project
			company_cost = (row.payer, row.cost_bearer) == ("Company", "Company")
			key = row.cost_project if company_cost and row.cost_basis == "Project" else None
		else:
			key = row.project if row.cost_borne_by in ("Company", "", None) else None
		if not key or (project and key != project):
			continue
		entry = totals.setdefault(key, {"transports": 0, "amount": 0.0})
		entry["transports"] += 1
		entry["amount"] += flt(row.amount)
	return totals
