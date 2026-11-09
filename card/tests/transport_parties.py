# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-2 (Owner 2026-10-31): every transport records who pays the transporter and who bears the cost;
nothing defaults it. Test data states it explicitly through these helpers."""

import frappe

from card.company import single_company


def company_paid(doc, basis="Company overhead", cost_project=None, overhead_cost_center=None):
	"""The company pays the transporter and bears the cost. Default charge: an overhead cost center of the
	transport's company (tests that check project costing pass basis="Project" and the cost project)."""
	doc.payer = "Company"
	doc.cost_bearer = "Company"
	doc.cost_basis = basis
	if basis == "Project":
		doc.cost_project = cost_project
	elif basis == "Company overhead":
		doc.overhead_cost_center = overhead_cost_center or frappe.db.get_value(
			"Cost Center",
			{"company": doc.get("company") or single_company(), "is_group": 0, "disabled": 0},
			"name",
		)
	return doc


def paid_by(doc, payer, cost_bearer=None):
	"""A move the company does not pay (record only): payer and bearer as stated."""
	doc.payer = payer
	doc.cost_bearer = cost_bearer if payer != "No charge" else None
	return doc


def as_recorded_before_p12(name, cost_borne_by="Company"):
	"""Simulate a transport recorded before P1-2 (history): no responsibility, payer or bearer; the old
	mixed field."""
	frappe.db.set_value(
		"Equipment Transport",
		name,
		{
			"responsibility": None,
			"payer": None,
			"cost_bearer": None,
			"customer_billable": 0,
			"supplier_recoverable": 0,
			"cost_basis": None,
			"cost_project": None,
			"overhead_cost_center": None,
			"financial_status": None,
			"cost_borne_by": cost_borne_by,
		},
	)


def company_paid_values(company):
	"""company_paid() as field values, for tests that build the transport from a dict."""
	return {
		"payer": "Company",
		"cost_bearer": "Company",
		"cost_basis": "Company overhead",
		"overhead_cost_center": frappe.db.get_value(
			"Cost Center", {"company": company, "is_group": 0, "disabled": 0}, "name"
		),
	}
