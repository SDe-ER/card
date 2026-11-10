# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Company transport cost per project, for the cost reports.

v3.0.0: only moves the company pays are its transport cost (Owner 2026-10-19). P1-2 (Owner
2026-10-31): a transport with a recorded responsibility counts when the company bears the cost, on its explicitly chosen
cost project — never on the destination; a move charged to a workshop, storage or overhead cost
center has no project. A transport recorded before P1-2 keeps its old rule (header project)."""

import frappe
from frappe.utils import flt

from card.constants import NON_COMPANY_PAYERS

TRANSPORT_COST_FIELDS = (
	"project",
	"cost_project",
	"cost_basis",
	"responsibility",
	"payer",
	"cost_bearer",
	"cost_borne_by",
	"amount",
)


def company_cost_project(row):
	"""The project a submitted transport is company cost of, or None when the company does not
	bear it (or bears it on a workshop, storage or overhead cost center)."""
	if row.responsibility:
		# only a move whose cost the company finally bears, on its chosen cost project
		company_cost = (row.payer, row.cost_bearer) == ("Company", "Company")
		return row.cost_project if company_cost and row.cost_basis == "Project" else None
	return row.project if row.cost_borne_by in ("Company", "", None) else None


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
		fields=list(TRANSPORT_COST_FIELDS),
		limit_page_length=0,
	)
	totals = {}
	for row in rows:
		key = company_cost_project(row)
		if not key or (project and key != project):
			continue
		entry = totals.setdefault(key, {"transports": 0, "amount": 0.0})
		entry["transports"] += 1
		entry["amount"] += flt(row.amount)
	return totals


# #43/#48/#121 (WP-14): moves the equipment supplier, the customer or another party pays may keep the
# amount agreed with them. It is information only and is read apart from the company's cost: it never
# enters transport_cost_by_project, the partial margin (card.analytics) or any posting (card.gl).
NOT_COMPANY_COST_FIELDS = ("project", "responsibility", "payer", "informational_amount")


def not_company_cost_project(row):
	"""The project (destination, or the project a supplier return leaves) a submitted transport's
	informational amount is shown on, or None when it has none or the company pays the move."""
	if not row.responsibility or row.payer not in NON_COMPANY_PAYERS or flt(row.informational_amount) <= 0:
		return None
	return row.project or None


def not_company_cost_by_project(company=None, from_date=None, to_date=None, project=None):
	"""{project: {"transports": n, "amount": total}} of the informational amounts of submitted transports
	the company does not pay (never company cost)."""
	filters = [["docstatus", "=", 1], ["informational_amount", ">", 0]]
	if company:
		filters.append(["company", "=", company])
	if from_date:
		filters.append(["date", ">=", from_date])
	if to_date:
		filters.append(["date", "<=", to_date])
	rows = frappe.get_all(
		"Equipment Transport",
		filters=filters,
		fields=list(NOT_COMPANY_COST_FIELDS),
		limit_page_length=0,
	)
	totals = {}
	for row in rows:
		key = not_company_cost_project(row)
		if not key or (project and key != project):
			continue
		entry = totals.setdefault(key, {"transports": 0, "amount": 0.0})
		entry["transports"] += 1
		entry["amount"] += flt(row.informational_amount)
	return totals


# ---- FR-139 (#49, #126, #43; conflict C-09, owner decision O-14): transport responsibility posting ----
# Per company (Card Company Settings.transport_responsibility_posting). "Hold" (the default, and an empty
# value) keeps the P1-2 rule of 2026-10-31: a transport recorded with a responsibility scenario is never
# posted. "Post" lets the monthly builder (card.gl.posting) add it to the draft invoices. Only the
# classification lives here; the builder makes the lines. No GL, no VAT decision: the lines carry the
# company's CARD item tax template (FR-127 rate) exactly as every other CARD line.

# what the builder reads of a transport recorded with a responsibility (all stored by the server)
RESPONSIBILITY_POSTING_FIELDS = (
	"responsibility",
	"payer",
	"cost_bearer",
	"cost_basis",
	"cost_project",
	"overhead_cost_center",
	"equipment_supplier",
	"financial_status",
	"financial_decision",
	"customer",
	"billing_project",
	"billing_amount",
	"billing_mode",
	"recovery_mode",
	"recovery_amount",
)

# the supplier-side kinds of a transport the company pays
COMPANY_COST = "Company cost"  # the company bears it: the transporter's line on its cost allocation
BILLED_TO_CUSTOMER = "Billed to customer"  # recharged: the transporter's line on the billing project
RECOVERED_BY_DEDUCTION = "Recovered by deduction"  # same supplier: the line and the recovery deduction
RECOVERED_BY_ADJUSTMENT = "Recovered by adjustment document"  # the line; the recovery is the accountant's

# why a transport the company pays stays out of the build in Post mode (the builder says it in the preview)
HELD_NOT_PAID = "not paid by the company"
HELD_DECISION = "decision not approved"
HELD_OTHER_SUPPLIER = "recovery from another supplier"
HELD_ABSORBED = "absorbed without a cost project"


def supplier_posting_kind(row):
	"""(kind, reason) of a submitted transport recorded with a responsibility, on the transporter's
	Purchase Invoice: kind is one of the constants above, or None with the HELD_* reason it is not posted."""
	if row.payer != "Company":
		return None, HELD_NOT_PAID
	if row.cost_bearer == "Company":
		return COMPANY_COST, None
	if row.financial_status != "Approved":
		return None, HELD_DECISION
	if row.cost_bearer == "Customer" and row.financial_decision == "Bill customer":
		return BILLED_TO_CUSTOMER, None
	if (
		row.cost_bearer == "Equipment Supplier"
		and row.financial_decision == "Recover from equipment supplier"
	):
		if row.recovery_mode == "Adjustment document":
			return RECOVERED_BY_ADJUSTMENT, None
		if row.equipment_supplier and row.equipment_supplier == row.get("transport_supplier"):
			return RECOVERED_BY_DEDUCTION, None
		# the deduction belongs on another supplier's invoice; one transport is one supplier-side source
		return None, HELD_OTHER_SUPPLIER
	# "Company absorbs": no cost project is recorded for the absorbed cost, and none is assumed
	return None, HELD_ABSORBED


def customer_billing_eligible(row):
	"""A transport whose approved decision bills the customer on the monthly Sales Invoice."""
	return bool(
		row.responsibility
		and row.payer == "Company"
		and row.cost_bearer == "Customer"
		and row.financial_status == "Approved"
		and row.financial_decision == "Bill customer"
		and row.billing_mode == "Monthly invoice"
		and row.customer
	)
