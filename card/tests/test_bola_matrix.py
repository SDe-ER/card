# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-129 (#51, #35, #54): the role and action matrix of every CARD endpoint, as negative tests.

One row of ``CASES`` per ``@frappe.whitelist`` function of the app. Each row generates three tests:

- ``test_cross_company__*``: a user of company A who holds the endpoint's own roles aims it at company B's
  records. The call is refused (PermissionError), or it answers without any company-B value; it writes nothing.
- ``test_role_refused__*``: a user without the endpoint's roles is refused; nothing is written.
- ``test_read_makes_no_write__*`` (read endpoints only): a normal call by an allowed user of company A writes
  nothing: the transaction write counter and the row count / last ``modified`` of every watched table are equal
  before and after.

A row whose endpoint has no company-scoped record says why in ``unscoped``. The guard tests keep the table and
the code in step: a new whitelisted function, a changed HTTP method or a DocType permission change fails here until
the table and docs/governance/ROLE-ACTION-MATRIX.md are updated (the matrix tables are rendered from this module).

A row marked ``hole`` documents a cross-company gap that is reported for a separate fix: its test is an expected
failure, so the suite stays green and an unexpected success shows the gap is closed. Company B and its records are
inserted raw (no validation; only the stored company matters to a permission check); no role is widened; everything
is rolled back."""

import ast
import json
import pathlib
import unittest
from collections.abc import Callable
from dataclasses import dataclass

import frappe
from frappe.client import insert as rest_insert
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, get_first_day, get_last_day, nowdate

from card.constants import DIR_SUBRENTAL
from card.tests.test_controllers import _ensure_masters

CARD = "Card Monthly Card"
PERMISSION = (frappe.PermissionError,)
THROWN = (frappe.PermissionError, frappe.ValidationError)
NOT_SCOPED_ADMIN = (
	"System Manager maintenance of the global party registry (no company field, no stored figures)"
)

# rows and last change of these tables are compared before and after every call
EXTRA_WATCHED = (
	"Version",
	"Comment",
	"DocShare",
	"File",
	"Access Log",
	"Material Request",
	"Purchase Invoice",
	"Sales Invoice",
	"Journal Entry",
	"Stock Entry",
	"Equipment Transport",
)

# the doctypes the matrix documents, in the order of docs/governance/ROLE-ACTION-MATRIX.md
ACTIONS = ("read", "write", "create", "submit", "cancel", "delete")
REPO = pathlib.Path(__file__).resolve().parents[2]
MATRIX_DOC = REPO / "docs" / "governance" / "ROLE-ACTION-MATRIX.md"


@dataclass(frozen=True)
class Case:
	"""One whitelisted endpoint.

	method   HTTP methods the decorator allows
	roles    roles of a user who may call it (the test user is limited to company A)
	gate     the server-side check, as documented in the matrix
	isolation how company B stays out, as documented in the matrix
	effects  side effects, as documented in the matrix
	writes   the endpoint writes on success
	cross    ctx -> kwargs aimed at company B; None when ``unscoped`` explains why there is no company record
	expect   "refused" (raises ``refusal``) or "no_leak" (answers, without any company-B value)
	leak     (result, ctx) -> True when the result carries company-B data (default: a company-B name)
	control  Administrator gets the company-B data with the same kwargs (proves the probe can see a leak)
	own      ctx -> kwargs on company A records (role test and the no-write test); default: ``cross``
	denied   role sets that must be refused (the empty set is a user without any role)
	role_refusal  what a refused role gets
	denied_result result -> True for an endpoint that answers a user without the role with an empty value
	operator the test user is linked to an active Employee of company A (portal endpoints)
	hole     a reported cross-company gap: the cross test is an expected failure
	"""

	method: tuple
	roles: tuple
	gate: str
	isolation: str
	effects: str = "None (read only)"
	writes: bool = False
	cross: Callable | None = None
	expect: str = "refused"
	leak: Callable | None = None
	control: bool = False
	unscoped: str = ""
	own: Callable | None = None
	denied: tuple = ((),)
	role_refusal: tuple = PERMISSION
	denied_result: Callable | None = None
	operator: bool = False
	hole: str = ""


def _search(txt="", filters=None, doctype=""):
	return {
		"doctype": doctype,
		"txt": txt,
		"searchfield": "name",
		"start": 0,
		"page_len": 20,
		"filters": filters or {},
	}


def _zero_values(result, ctx):
	"""Chart answer: every dataset value is zero."""
	return any(v for ds in (result or {}).get("datasets") or [] for v in ds.get("values") or [])


def _nonzero_value(result, ctx):
	"""Number card answer: a value other than 0 / None."""
	return bool((result or {}).get("value"))


GET = ("GET",)
POST = ("POST",)
AUTOCOMPLETE = ("GET", "POST")
NUMBER_CARD = dict(
	method=POST,
	roles=("Card User",),
	gate="Card Monthly Card read (frappe.has_permission)",
	isolation="frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission, has_card_permission)",
	effects="None (read only; POST because the number card widget posts)",
	cross=lambda c: {"filters": {"company": c.B}},
	expect="no_leak",
	leak=_nonzero_value,
	own=lambda c: {"filters": {"company": c.A}},
)

CASES = {
	# ---------- card.api ----------
	"card.api.party_figures": Case(
		method=GET,
		roles=("Card User",),
		gate="assert_report_role; read on the registry row (has_registry_permission)",
		isolation="has_registry_permission (party with a card in a permitted company); figures limited to permitted_companies()",
		cross=lambda c: {"party_type": "Supplier", "party": c.sup_b},
		own=lambda c: {"party_type": "Supplier", "party": c.sup_a},
	),
	"card.api.refresh_supplier": Case(
		method=POST,
		roles=("System Manager",),
		gate="System Manager role (frappe.throw otherwise)",
		isolation="None: global registry, no company field",
		effects="Inserts or saves Card Equipment Supplier rows (aggregates cleared); may rename a misnamed row",
		writes=True,
		unscoped=NOT_SCOPED_ADMIN,
		own=lambda c: {"supplier": c.sup_a},
		denied=((), ("Card Manager",), ("Accounts Manager",)),
		role_refusal=THROWN,
	),
	"card.api.card_suppliers_query": Case(
		method=GET,
		roles=("Card User",),
		gate="assert_report_role",
		isolation="query_companies(filters) / permitted_companies (Company User Permission)",
		cross=lambda c: _search(c.token, {}, "Card Equipment Supplier"),
		expect="no_leak",
		control=True,
		own=lambda c: _search(c.token, {"company": c.A}, "Card Equipment Supplier"),
	),
	"card.api.refresh_customer": Case(
		method=POST,
		roles=("System Manager",),
		gate="System Manager role (frappe.throw otherwise)",
		isolation="None: global registry, no company field",
		effects="Inserts or saves Card Equipment Customer rows (aggregates cleared); may rename a misnamed row",
		writes=True,
		unscoped=NOT_SCOPED_ADMIN,
		own=lambda c: {"customer": c.cust_a},
		denied=((), ("Card Manager",), ("Accounts Manager",)),
		role_refusal=THROWN,
	),
	"card.api.card_customers_query": Case(
		method=GET,
		roles=("Card User",),
		gate="assert_report_role",
		isolation="query_companies(filters) / permitted_companies (Company User Permission)",
		cross=lambda c: _search(c.token, {}, "Card Equipment Customer"),
		expect="no_leak",
		control=True,
		own=lambda c: _search(c.token, {"company": c.A}, "Card Equipment Customer"),
	),
	"card.api.card_project_options": Case(
		method=AUTOCOMPLETE,
		roles=("Card User",),
		gate="assert_report_role",
		isolation="query_companies (requested company only when permitted)",
		effects="None (read only; also POST because the Autocomplete control posts)",
		cross=lambda c: {"txt": c.token},
		expect="no_leak",
		control=True,
		own=lambda c: {"txt": c.token, "company": c.A},
	),
	"card.api.report_defaults": Case(
		method=GET,
		roles=("Card User",),
		gate="assert_report_role",
		isolation="None: two Card Settings flags, no company data",
		unscoped="returns two global Card Settings flags only",
	),
	"card.api.card_company_options": Case(
		method=AUTOCOMPLETE,
		roles=("Card User",),
		gate="assert_report_role",
		isolation="permitted_companies (Company User Permission)",
		effects="None (read only; also POST because the Autocomplete control posts)",
		cross=lambda c: {"txt": c.token},
		expect="no_leak",
		control=True,
	),
	"card.api.get_only_company": Case(
		method=GET,
		roles=("Card User",),
		gate="Company read or select, else None",
		isolation="frappe.get_list on Company (Company User Permission)",
		cross=lambda c: {},
		expect="no_leak",
		denied_result=lambda r: r is None,
	),
	"card.api.get_asset_prefill": Case(
		method=GET,
		roles=("Card Manager", "Accounts User"),
		gate="Card Equipment read; Asset read on the record",
		isolation="frappe.has_permission(Asset, read, asset) (Company User Permission); fields filtered by Card Equipment read levels",
		cross=lambda c: {"asset": c.asset_b},
		own=lambda c: {"asset": c.asset_a},
	),
	"card.api.create_equipment_from_asset": Case(
		method=POST,
		roles=("Card Manager", "Accounts User"),
		gate="Card Equipment create; Asset read on the record; insert with the user's own permissions",
		isolation="Asset read on the record (Company User Permission); company taken from the Asset",
		effects="With save=1 and nothing missing: inserts one Card Equipment; otherwise returns the prefilled values",
		writes=True,
		cross=lambda c: {"asset": c.asset_b, "save": 1},
		own=lambda c: {"asset": c.asset_a, "save": 1},
	),
	"card.api.available_assets_query": Case(
		method=GET,
		roles=("Card Manager", "Accounts User"),
		gate="Card Equipment create or write by role; Asset read beyond select",
		isolation="query_companies(filters, Card Equipment); frappe.get_list on Asset",
		cross=lambda c: _search(c.token, {"company": c.B}, "Asset"),
		expect="no_leak",
		control=True,
		own=lambda c: _search(c.token, {"company": c.A}, "Asset"),
	),
	# ---------- dashboard chart source ----------
	"card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get": Case(
		method=POST,
		roles=("Card User",),
		gate="Dashboard Chart read when named; Card Monthly Card read",
		isolation="frappe.get_list on Card Monthly Card / Card Equipment (Company User Permission); no shared cache",
		effects="None (read only; POST because the chart widget posts)",
		cross=lambda c: {
			"chart": {"timespan": "Last Year", "time_interval": "Monthly"},
			"filters": {"company": c.B},
		},
		expect="no_leak",
		leak=_zero_values,
		control=True,
		own=lambda c: {
			"chart": {"timespan": "Last Year", "time_interval": "Monthly"},
			"filters": {"company": c.A},
		},
	),
	# ---------- Card Equipment ----------
	"card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues": Case(
		method=GET,
		roles=("Card User",),
		gate="Card Equipment read",
		isolation="frappe.get_list on Card Equipment (Company User Permission)",
		cross=lambda c: {"company": c.B},
		expect="no_leak",
		control=True,
		own=lambda c: {"company": c.A},
	),
	"card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag": Case(
		method=POST,
		roles=("Card Manager",),
		gate="write on the record and write level of is_unit_component (level 1)",
		isolation="doc.check_permission(write) (Company User Permission)",
		effects="Sets is_unit_component on the listed equipment",
		writes=True,
		cross=lambda c: {"equipment": c.eq_b},
		own=lambda c: {"equipment": c.eq_a},
		denied=((), ("Card User",)),
	),
	"card.card.doctype.card_equipment.card_equipment.get_shift_heatmap": Case(
		method=GET,
		roles=("Card User",),
		gate="Card Equipment read on the record; Card Monthly Card read",
		isolation="frappe.has_permission on the record (Company User Permission)",
		cross=lambda c: {"name": c.eq_b},
		own=lambda c: {"name": c.eq_a},
	),
	"card.card.doctype.card_equipment.card_equipment.replace_component": Case(
		method=POST,
		roles=("Card Manager",),
		gate="write on the unit and write level of components (level 1); read on the new component",
		isolation="doc.check_permission on both records (Company User Permission)",
		effects="Closes one component row and appends another; saves the unit",
		writes=True,
		cross=lambda c: {
			"unit": c.eq_b,
			"component": c.eq_b2,
			"new_component": c.eq_a2,
			"date": nowdate(),
		},
		own=lambda c: {"unit": c.eq_a, "component": c.eq_a2, "new_component": c.eq_a3, "date": nowdate()},
		denied=((), ("Card User",)),
	),
	"card.card.doctype.card_equipment.card_equipment.move_component": Case(
		method=POST,
		roles=("Card Manager",),
		gate="write on both units and write level of components (level 1)",
		isolation="doc.check_permission on both records (Company User Permission)",
		effects="Closes the row in the source unit, appends it to the target unit; saves both; syncs flags",
		writes=True,
		cross=lambda c: {"unit": c.eq_b, "component": c.eq_b2, "target_unit": c.eq_a, "date": nowdate()},
		own=lambda c: {"unit": c.eq_a, "component": c.eq_a2, "target_unit": c.eq_a3, "date": nowdate()},
		denied=((), ("Card User",)),
	),
	# ---------- Card Monthly Card ----------
	"card.card.doctype.card_monthly_card.card_monthly_card.get_card_context": Case(
		method=GET,
		roles=("Card User",),
		gate="Card Equipment read on the record",
		isolation="doc.check_permission(read) (Company User Permission)",
		cross=lambda c: {"equipment": c.eq_b, "month": c.month, "year": c.year},
		own=lambda c: {"equipment": c.eq_a, "month": c.month, "year": c.year},
	),
	# ---------- Equipment Transport ----------
	"card.card.doctype.equipment_transport.equipment_transport.get_equipment_location": Case(
		method=GET,
		roles=("Card User",),
		gate="Card Equipment read on the record",
		isolation="doc.check_permission(read) (Company User Permission)",
		cross=lambda c: {"equipment": c.eq_b},
		own=lambda c: {"equipment": c.eq_a},
	),
	"card.card.doctype.equipment_transport.equipment_transport.record_financial_decision": Case(
		method=POST,
		roles=("Accounts Manager",),
		gate="Accounts Manager role; read on the transport; not its creator, editor or submitter",
		isolation="has_transport_permission and permitted_companies(Equipment Transport)",
		effects="db_set of the financial decision fields; one Version; one Info Comment",
		writes=True,
		cross=lambda c: {"transport": c.trn_b, "decision": "Return for correction", "note": "x"},
		own=lambda c: {"transport": c.trn_a, "decision": "Return for correction", "note": "x"},
		denied=((), ("Card Manager",), ("Card User",)),
	),
	"card.card.doctype.equipment_transport.equipment_transport.billing_customer": Case(
		method=GET,
		roles=("Accounts Manager",),
		gate="Accounts Manager role; read on the transport",
		isolation="doc.check_permission(read) (has_transport_permission); project must be of the transport's company",
		cross=lambda c: {"transport": c.trn_b},
		own=lambda c: {"transport": c.trn_a},
		denied=((), ("Card Manager",)),
	),
	# ---------- Project Diesel Fill ----------
	"card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable": Case(
		method=GET,
		roles=("Card User",),
		gate="Project Diesel Fill read",
		isolation="None: a yes/no answer about the session user",
		unscoped="returns whether the session user may change the diesel supplier (no record)",
	),
	"card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query": Case(
		method=GET,
		roles=("Card User",),
		gate="Project Diesel Fill create or write",
		isolation="form company must be in permitted_companies(Project Diesel Fill); User Permissions of the linked doctype",
		cross=lambda c: _search(c.token, {"company": c.B}, "Project"),
		expect="no_leak",
		control=True,
		own=lambda c: _search("", {"company": c.A}, "Project"),
	),
	"card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context": Case(
		method=GET,
		roles=("Card User",),
		gate="Project Diesel Fill read",
		isolation="company must be in permitted_companies(Project Diesel Fill), else price 0",
		cross=lambda c: {"company": c.B},
		expect="no_leak",
		leak=lambda r, c: bool((r or {}).get("price")),
		control=True,
		own=lambda c: {"company": c.A},
	),
	"card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price": Case(
		method=POST,
		roles=("Card Manager", "Accounts Manager"),
		gate="write on the fill; diesel_price_exception_role; a reason",
		isolation="doc.check_permission(write) (has_diesel_fill_permission)",
		effects="Saves the draft fill with the company price (audited)",
		writes=True,
		cross=lambda c: {"name": c.fill_b, "reason": "x"},
		own=lambda c: {"name": c.fill_a, "reason": "x"},
		denied=((), ("Card User",)),
	),
	"card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception": Case(
		method=POST,
		roles=("Card Manager", "Accounts Manager"),
		gate="write on the fill; diesel_price_exception_role; a reason",
		isolation="doc.check_permission(write) (has_diesel_fill_permission)",
		effects="Saves the draft fill without its price exception (audited)",
		writes=True,
		cross=lambda c: {"name": c.fill_b, "reason": "x"},
		own=lambda c: {"name": c.fill_a, "reason": "x"},
		denied=((), ("Card User",)),
	),
	# ---------- reports ----------
	"card.card.report.equipment_supplier_statement.statement_pdf.download_pdf": Case(
		method=POST,
		roles=("Card User",),
		gate="print on the report's doctype (Card Monthly Card); the standard report run",
		isolation="resolve_company (Company User Permission); report rows by the user's permissions",
		effects="One Access Log; the PDF in the response",
		writes=True,
		cross=lambda c: {"filters": {"company": c.B, "statement_type": "مورد", "supplier": c.sup_b}},
		own=lambda c: {"filters": {"company": c.A, "statement_type": "مورد"}},
	),
	"card.card_value.supplier_cost_last_month": Case(**NUMBER_CARD, control=True),
	"card.card_value.customer_value_last_month": Case(**NUMBER_CARD, control=True),
	"card.card_value.internal_value_last_month": Case(**NUMBER_CARD),
	"card.card_value.cards_without_internal_rate_last_month": Case(**NUMBER_CARD),
	"card.card_value.hours_without_internal_rate_last_month": Case(**NUMBER_CARD),
	# ---------- cancel with a reason (FR-123) ----------
	"card.cancel_reason.cancel_with_reason": Case(
		method=POST,
		roles=("Card Manager",),
		gate="CARD transaction doctype only; cancel on the record (Frappe cancel right)",
		isolation="doc.check_permission(cancel) (has_card_permission / has_transport_permission / has_diesel_fill_permission)",
		effects="Stores the reason and cancels the document; one Info Comment",
		writes=True,
		cross=lambda c: {"doctype": CARD, "name": c.card_b, "reason": "x"},
		own=lambda c: {"doctype": CARD, "name": c.card_a, "reason": "x"},
		denied=((), ("Card User",), ("Accounts Manager",)),
	),
	# ---------- catalog ----------
	"card.catalog.search": Case(
		method=GET,
		roles=("Card User",),
		gate="check_catalog_user (Item read or a CARD catalog role); machine access when equipment is given",
		isolation="Items are global; equipment: fitment.check_equipment_access (record read or own machine)",
		cross=lambda c: {"txt": "x", "equipment": c.eq_b},
		own=lambda c: {"txt": "x", "equipment": c.eq_a},
	),
	"card.catalog.filter_options": Case(
		method=GET,
		roles=("Card User",),
		gate="check_catalog_user",
		isolation="None: Item Group and Brand are global masters",
		unscoped="Item Group / Brand options are global masters",
		own=lambda c: {"kind": "brand"},
	),
	"card.diesel.get_card_diesel": Case(
		method=GET,
		roles=("Card User",),
		gate="Card Monthly Card read on the record",
		isolation="frappe.has_permission on the record (has_card_permission)",
		cross=lambda c: {"card": c.card_b},
		own=lambda c: {"card": c.card_a},
	),
	"card.diesel_reconciliation.diesel_supplier_options": Case(
		method=GET,
		roles=("Accounts Manager",),
		gate="assert_report_role; report permitted; role read on Project Diesel Fill and Purchase Invoice",
		isolation="permitted_companies of both doctypes; frappe.get_list on Project Diesel Fill",
		cross=lambda c: {"txt": c.token},
		expect="no_leak",
		control=True,
		own=lambda c: {"txt": c.token, "company": c.A},
		denied=((), ("Card User",)),
	),
	"card.fitment.fit_for": Case(
		method=GET,
		roles=("Card User",),
		gate="check_catalog_user; machine access",
		isolation="fitment.check_equipment_access (record read, Company User Permission, or own machine)",
		cross=lambda c: {"equipment": c.eq_b, "items": json.dumps([c.item])},
		own=lambda c: {"equipment": c.eq_a, "items": json.dumps([c.item])},
	),
	"card.fitment.machines": Case(
		method=GET,
		roles=("Card User",),
		gate="check_catalog_user",
		isolation="frappe.get_list on Card Equipment (Company User Permission); operators: their own machines",
		cross=lambda c: {"txt": c.token},
		expect="no_leak",
		control=True,
	),
	# ---------- GL ----------
	"card.gl.integrity.accept_correction": Case(
		method=POST,
		roles=("Accounts Manager",),
		gate="Accounts Manager or System Manager; write on the invoice; a reason",
		isolation="doc.check_permission(write) and permitted_companies(sources, invoice, GL Posting Log)",
		effects="db_set of accepted_signature, accepted_by, correction_reason on the GL Posting Log",
		writes=True,
		cross=lambda c: {"invoice_doctype": "Purchase Invoice", "invoice": c.pi_b, "reason": "x"},
		own=lambda c: {"invoice_doctype": "Purchase Invoice", "invoice": c.pi_a, "reason": "x"},
		denied=((), ("Card Manager",), ("Accounts User",)),
	),
	"card.gl.integrity.link_supplier_invoice": Case(
		method=POST,
		roles=("Accounts Manager",),
		gate="Accounts Manager, Accounts User or System Manager; read and submit on the invoice; read on supplier and every source",
		isolation="permitted_companies(sources, Purchase Invoice, GL Posting Log); each source of the invoice's company",
		effects="Inserts one Linked GL Posting Log",
		writes=True,
		cross=lambda c: {"invoice": c.pi_b, "sources": json.dumps([{"doctype": CARD, "name": c.card_b}])},
		own=lambda c: {"invoice": c.pi_a, "sources": json.dumps([{"doctype": CARD, "name": c.card_a}])},
		denied=((), ("Card Manager",)),
	),
	"card.gl.journal_link.link_accrual_journal": Case(
		method=POST,
		roles=("Accounts Manager",),
		gate="Accounts Manager, Accounts User or System Manager; read and submit on the Journal Entry; read on supplier and every card",
		isolation="permitted_companies(sources, Journal Entry, GL Posting Log); each card of the entry's company",
		effects="Inserts one Linked GL Posting Log (type Journal Entry)",
		writes=True,
		cross=lambda c: {"journal_entry": c.je_b, "cards": json.dumps([c.card_b])},
		own=lambda c: {"journal_entry": c.je_a, "cards": json.dumps([c.card_a])},
		denied=((), ("Card Manager",)),
	),
	"card.gl.posting.rebuild_month": Case(
		method=POST,
		roles=("Card Manager", "Purchase User"),
		gate="Card Manager or System Manager; party read",
		isolation="_checked_endpoint_args: permitted_companies(sources, invoice, GL Posting Log)",
		effects="Rebuilds the draft Purchase / Sales Invoice and its GL Posting Log (builder inserts with ignore_permissions after the gate)",
		writes=True,
		cross=lambda c: {
			"company": c.B,
			"party_type": "Supplier",
			"party": c.sup_b,
			"month": c.month,
			"year": c.year,
		},
		own=lambda c: {
			"company": c.A,
			"party_type": "Supplier",
			"party": c.sup_a,
			"month": c.month,
			"year": c.year,
		},
		denied=((), ("Card User",), ("Accounts Manager",)),
	),
	"card.gl.posting.post_month": Case(
		method=POST,
		roles=("Card Manager", "Purchase User"),
		gate="Card Manager or System Manager; party read",
		isolation="_checked_endpoint_args: permitted_companies(sources, invoice, GL Posting Log)",
		effects="Builds a draft Purchase / Sales Invoice and a GL Posting Log (builder inserts with ignore_permissions after the gate)",
		writes=True,
		cross=lambda c: {
			"company": c.B,
			"party_type": "Supplier",
			"party": c.sup_b,
			"month": c.month,
			"year": c.year,
		},
		own=lambda c: {
			"company": c.A,
			"party_type": "Supplier",
			"party": c.sup_a,
			"month": c.month,
			"year": c.year,
		},
		denied=((), ("Card User",), ("Accounts Manager",)),
	),
	"card.gl.posting.posting_month_parties": Case(
		method=GET,
		roles=("Card Manager",),
		gate="Card Manager or System Manager",
		isolation="_checked_endpoint_args per side; parties the caller cannot read are left out",
		cross=lambda c: {"company": c.B, "month": c.month, "year": c.year},
		own=lambda c: {"company": c.A, "month": c.month, "year": c.year},
		denied=((), ("Card User",), ("Accounts Manager",)),
	),
	"card.gl.posting.preview_month": Case(
		method=GET,
		roles=("Card Manager", "Purchase User"),
		gate="Card Manager or System Manager; party read",
		isolation="_checked_endpoint_args; review invoices listed only when readable",
		cross=lambda c: {
			"company": c.B,
			"party_type": "Supplier",
			"party": c.sup_b,
			"month": c.month,
			"year": c.year,
		},
		own=lambda c: {
			"company": c.A,
			"party_type": "Supplier",
			"party": c.sup_a,
			"month": c.month,
			"year": c.year,
		},
		denied=((), ("Card User",), ("Accounts Manager",)),
	),
	# ---------- materials ----------
	"card.materials.review_stock": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="read on the review; stock shown only with role read on Bin and Warehouse",
		isolation="doc.check_permission(read) (Company User Permission); stock limited to the review's company",
		cross=lambda c: {"review": c.review_b},
		own=lambda c: {"review": c.review_a},
	),
	"card.materials.pull_requests": Case(
		method=POST,
		roles=("Card Supervisor",),
		gate="write on the review (draft only)",
		isolation="doc.check_permission(write) (Company User Permission); requests of the review's project",
		effects="Appends request lines and saves the draft review",
		writes=True,
		cross=lambda c: {"review": c.review_b},
		own=lambda c: {"review": c.review_a},
		denied=((), ("Card User",)),
	),
	"card.materials.approve_review": Case(
		method=POST,
		roles=("Card Manager", "Stock User"),
		gate="Card Manager or System Manager; Material Request create; read on the review; not a preparer (FR-121)",
		isolation="doc.check_permission(read) (Company User Permission); documents made in the review's company",
		effects="Inserts draft Material Requests and draft custody Handovers; db_set of the approval; request status",
		writes=True,
		cross=lambda c: {"review": c.review_b},
		own=lambda c: {"review": c.review_a},
		denied=((), ("Card Supervisor",)),
	),
	"card.materials.close_tool_handover": Case(
		method=POST,
		roles=("Card Manager",),
		gate="write on the custody record; Card Manager or the store side; not the worker; a reason",
		isolation="doc.check_permission(write) (Company User Permission)",
		effects="Saves the draft handover as Not handed over",
		writes=True,
		cross=lambda c: {"custody": c.custody_b, "reason": "x"},
		own=lambda c: {"custody": c.custody_a, "reason": "x"},
		denied=((), ("Card User",)),
	),
	"card.materials.make_tool_handover": Case(
		method=POST,
		roles=("Card Manager",),
		gate="Card Manager role; read on the review",
		isolation="review.check_permission(read) (Company User Permission)",
		effects="Inserts one draft Employee Tool Custody (Handover); links it on the review line",
		writes=True,
		cross=lambda c: {"review_item": c.review_item_b},
		own=lambda c: {"review_item": c.review_item_a},
		denied=((), ("Card Supervisor",)),
	),
	"card.materials.get_portal_context": Case(
		method=GET,
		roles=("Card Operator",),
		gate="Card Operator, Card Supervisor, Card Manager or System Manager",
		isolation="the session user's own Employee: his machines and his requests",
		cross=lambda c: {},
		expect="no_leak",
		operator=True,
	),
	"card.materials.search_items": Case(
		method=GET,
		roles=("Card Operator",),
		gate="Card Operator, Card Supervisor, Card Manager or System Manager",
		isolation="None: Items are global (catalog rules and Item User Permissions)",
		unscoped="Items are global masters",
		own=lambda c: {"txt": "x"},
		operator=True,
	),
	"card.materials.submit_needs": Case(
		method=POST,
		roles=("Card Operator",),
		gate="portal role; linked Employee; the machine is operated by that Employee (check_requester)",
		isolation="check_requester: the machine must be the session employee's; company from the machine",
		effects="Inserts and submits one Equipment Needs Request",
		writes=True,
		cross=lambda c: {
			"equipment": c.eq_b,
			"items": json.dumps([{"kind": "Part", "description": "x", "qty": 1}]),
		},
		operator=True,
	),
	"card.mobile.get_session_context": Case(
		method=GET,
		roles=("Card Operator",),
		gate="has_app_permission (portal role, or catalog-only Card User)",
		isolation="None: the session user's own context",
		unscoped="returns the session user's own context (roles, employee, version)",
		operator=True,
	),
	# ---------- tool custody screen ----------
	"card.tool_custody.context": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="Card Supervisor, Card Manager, Stock Manager or System Manager, and Employee Tool Custody read",
		isolation="None: flags about the session user",
		unscoped="returns the screen's tabs and the session user's action flags",
		denied=((), ("Card User",)),
	),
	"card.tool_custody.view": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="screen role and Employee Tool Custody read",
		isolation="frappe.get_list on Employee Tool Custody (Company User Permission)",
		cross=lambda c: {"tab": "awaiting", "employee": c.emp_b},
		expect="no_leak",
		control=True,
		own=lambda c: {"tab": "awaiting"},
		denied=((), ("Card User",)),
	),
	"card.tool_custody.employee_query": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="screen role and Employee Tool Custody read",
		isolation="query_companies(filters, Employee Tool Custody); Employee User Permissions",
		cross=lambda c: _search(c.token, {}, "Employee"),
		expect="no_leak",
		control=True,
		own=lambda c: _search("", {"company": c.A}, "Employee"),
		denied=((), ("Card User",)),
	),
	"card.tool_custody.store_query": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="screen role and Employee Tool Custody read",
		isolation="query_companies(filters, Employee Tool Custody); Warehouse User Permissions",
		cross=lambda c: _search(c.token, {}, "Warehouse"),
		expect="no_leak",
		control=True,
		own=lambda c: _search("", {"company": c.A}, "Warehouse"),
		denied=((), ("Card User",)),
	),
	"card.tool_custody.item_query": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="screen role and Employee Tool Custody read (then Item get_all with ignore_permissions)",
		isolation="None: Items are global masters",
		unscoped="Items are global masters",
		own=lambda c: _search("x", {}, "Item"),
		denied=((), ("Card User",)),
	),
	"card.tool_custody.confirm": Case(
		method=POST,
		roles=("Card Manager",),
		gate="screen role; submit on the custody record (controller rules on submit)",
		isolation="doc.check_permission(submit) (Company User Permission)",
		effects="Submits the movement; Handover / Return create and submit a Stock Entry",
		writes=True,
		cross=lambda c: {"custody": c.custody_b},
		own=lambda c: {"custody": c.custody_a},
		denied=((), ("Card User",)),
	),
	"card.tool_custody.move": Case(
		method=POST,
		roles=("Card Supervisor",),
		gate="screen role; Employee Tool Custody create (insert with the user's own permissions)",
		isolation="company taken from the Employee in validate, after Frappe's create check",
		effects="Inserts one draft Employee Tool Custody",
		writes=True,
		cross=lambda c: {
			"movement": "Transfer",
			"employee": c.emp_b,
			"item_code": c.item,
			"qty": 1,
			"to_employee": c.emp_b2,
		},
		denied=((), ("Card User",)),
		hole=(
			"card/tool_custody.py move() inserts with the user's create right while the custody company is "
			"still empty; EmployeeToolCustody.validate then sets it from the Employee "
			"(employee_tool_custody.py validate), and Employee Tool Custody has no company has_permission "
			"hook, so a user limited to company A creates a draft movement in company B."
		),
	),
}

# Frappe's own insert endpoint on CARD DocTypes whose company is set in validate (after Frappe's create check)
# and that have no company has_permission hook. Each probe is a test of its own.
REST_CREATE_PROBES = {
	"Equipment Needs Review": (
		("Card Supervisor",),
		lambda c: {"doctype": "Equipment Needs Review", "project": c.proj_b},
		"EquipmentNeedsReview.validate sets company from the Project after the create check; no company hook",
	),
	"Equipment Needs Request": (
		("Card Supervisor",),
		lambda c: {
			"doctype": "Equipment Needs Request",
			"equipment": c.eq_b,
			"operator": c.emp_b,
			"items": [{"kind": "Part", "description": "x", "qty": 1}],
		},
		"EquipmentNeedsRequest.validate sets company from the equipment after the create check; no company hook",
	),
	"Employee Tool Custody": (
		("Card Supervisor",),
		lambda c: {
			"doctype": "Employee Tool Custody",
			"movement": "Transfer",
			"employee": c.emp_b,
			"to_employee": c.emp_b2,
			"item_code": c.item,
			"qty": 1,
			"date": nowdate(),
		},
		"EmployeeToolCustody.validate sets company from the Employee after the create check; no company hook",
	),
}


# ---------- matrix rendering (docs/governance/ROLE-ACTION-MATRIX.md is generated from these) ----------
def card_doctypes():
	"""Every DocType JSON of the app, sorted by name."""
	out = []
	for path in sorted((REPO / "card" / "card" / "doctype").glob("*/*.json")):
		if path.stem != path.parent.name:
			continue
		meta = json.loads(path.read_text())
		if meta.get("doctype") == "DocType":
			out.append(meta)
	return sorted(out, key=lambda m: m["name"])


def _hooks():
	from card import hooks

	return hooks.has_permission, hooks.permission_query_conditions


def _company_mechanism(meta):
	has_perm, query = _hooks()
	fields = {f["fieldname"]: f for f in meta.get("fields") or []}
	parts = []
	if meta.get("istable"):
		return "Child table: the parent's permissions"
	if meta.get("issingle"):
		return "Single: role permissions only"
	company = fields.get("company")
	if company and company.get("fieldtype") == "Link":
		parts.append("Company User Permission on `company`")
	if meta["name"] in has_perm:
		parts.append("has_permission `" + has_perm[meta["name"]].rsplit(".", 1)[1] + "`")
	if meta["name"] in query:
		parts.append("permission_query_conditions `" + query[meta["name"]].rsplit(".", 1)[1] + "`")
	return "; ".join(parts) or "None (global master)"


def render_doctype_matrix():
	"""The DocType table of the matrix: level-0 role rights from the DocType JSON, plus the hooks."""
	lines = [
		"| DocType | Kind | Read | Write | Create | Submit | Cancel | Delete | Field levels | Company isolation |",
		"|---|---|---|---|---|---|---|---|---|---|",
	]
	for meta in card_doctypes():
		kind = (
			"Child"
			if meta.get("istable")
			else "Single"
			if meta.get("issingle")
			else "Submittable"
			if meta.get("is_submittable")
			else "Master"
		)
		perms = [p for p in meta.get("permissions") or [] if not p.get("permlevel")]
		cells = []
		for action in ACTIONS:
			roles = [p["role"] + (" (own)" if p.get("if_owner") else "") for p in perms if p.get(action)]
			cells.append(", ".join(roles) or "-")
		levels = []
		for level in sorted(
			{p.get("permlevel") for p in meta.get("permissions") or [] if p.get("permlevel")}
		):
			rows = [p for p in meta["permissions"] if p.get("permlevel") == level]
			read = ", ".join(p["role"] for p in rows if p.get("read")) or "-"
			write = ", ".join(p["role"] for p in rows if p.get("write")) or "-"
			levels.append(f"L{level} read: {read}; write: {write}")
		lines.append(
			"| {} | {} | {} | {} | {} |".format(
				meta["name"], kind, " | ".join(cells), "<br>".join(levels) or "-", _company_mechanism(meta)
			)
		)
	return "\n".join(lines)


def render_endpoint_matrix():
	"""The endpoint table of the matrix, from ``CASES``."""
	lines = [
		"| Endpoint | HTTP | Gate (server check) | Company isolation | Side effects |",
		"|---|---|---|---|---|",
	]
	for path in sorted(CASES):
		case = CASES[path]
		lines.append(
			f"| `{path}` | {', '.join(case.method)} | {case.gate} | {case.isolation} | {case.effects} |"
		)
	return "\n".join(lines)


def whitelisted_functions():
	"""``module.function`` of every @frappe.whitelist function in the app (tests excluded)."""
	out = {}
	root = REPO / "card"
	for path in sorted(root.rglob("*.py")):
		if "tests" in path.relative_to(root).parts:
			continue
		module = ".".join(path.relative_to(REPO).with_suffix("").parts)
		for node in ast.walk(ast.parse(path.read_text())):
			if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
				if any("whitelist" in ast.unparse(d) for d in node.decorator_list):
					out[f"{module}.{node.name}"] = f"{path.relative_to(REPO)}:{node.lineno}"
	return out


def _block(text, name):
	start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
	return text.split(start, 1)[1].split(end, 1)[0].strip() if start in text and end in text else None


# ---------- the tests ----------
class TestBolaMatrix(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.ctx = self._fixtures()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response.pop("filecontent", None)
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures (Administrator, rolled back) ----------
	def _raw(self, doctype, name, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = name
		doc.db_insert()
		return name

	def _fixtures(self):
		token = frappe.generate_hash(length=8)
		c = frappe._dict(token=token, A=self._m["company"])
		b = f"BOLA-B-{token}"  # in the name of every company-B record: the leak marker
		c.marker = b
		last = get_first_day(add_months(nowdate(), -1))
		c.month, c.year = "%02d" % last.month, str(last.year)
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)

		c.B = "TEST-CO-" + b
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": c.B,
				"abbr": "B" + token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", c.A, "default_currency"),
				"country": frappe.db.get_value("Company", c.A, "country"),
			}
		)
		co.name = c.B
		co.db_insert()

		c.proj_a = self._m["project"]
		c.proj_b = self._project("PRJ-" + b, c.B)
		c.eq_a, c.eq_a2, c.eq_a3 = (self._equipment(f"EQ-A{i}-{token}", c.A) for i in (1, 2, 3))
		c.eq_b, c.eq_b2 = (self._equipment(f"EQ-{i}-{b}", c.B) for i in (1, 2))
		frappe.db.set_value("Card Equipment", c.eq_b, "is_unit_component", 1)  # an integrity issue to list
		c.sup_a = self._supplier(f"SUP-A-{token}")
		c.sup_b = self._supplier(f"SUP-{b}")
		c.cust_a = self._customer(f"CUST-A-{token}")
		c.cust_b = self._customer(f"CUST-{b}")
		for registry, field, party in (
			("Card Equipment Supplier", "supplier", c.sup_a),
			("Card Equipment Supplier", "supplier", c.sup_b),
			("Card Equipment Customer", "customer", c.cust_a),
			("Card Equipment Customer", "customer", c.cust_b),
		):
			if not frappe.db.exists(registry, party):
				self._raw(registry, party, **{field: party})
		c.item = self._item(f"ITEM-{token}")
		c.emp_b = self._raw(
			"Employee", f"EMP-1-{b}", first_name="B1", employee_name="B1", company=c.B, status="Active"
		)
		c.emp_b2 = self._raw(
			"Employee", f"EMP-2-{b}", first_name="B2", employee_name="B2", company=c.B, status="Active"
		)
		c.emp_a = self._raw(
			"Employee", f"EMP-A-{token}", first_name="A1", employee_name="A1", company=c.A, status="Active"
		)
		frappe.db.set_value("Card Equipment", c.eq_b, {"operator": c.emp_b, "current_project": c.proj_b})
		c.wh_b = self._raw("Warehouse", f"WH-{b}", warehouse_name=f"WH-{b}", company=c.B, is_group=0)

		first, end = str(last), str(get_last_day(last))
		for side, company, equipment, project, supplier, customer in (
			("a", c.A, c.eq_a, c.proj_a, c.sup_a, c.cust_a),
			("b", c.B, c.eq_b, c.proj_b, c.sup_b, c.cust_b),
		):
			tag = f"A-{token}" if side == "a" else b
			c[f"card_{side}"] = self._raw(
				CARD,
				f"CARD-{tag}",
				company=company,
				equipment=equipment,
				project=project,
				supplier=supplier,
				customer=customer,
				ownership="إيجار",
				card_direction=DIR_SUBRENTAL,
				month=c.month,
				year=int(c.year),
				from_date=first,
				to_date=end,
				shift="نهاري",
				net_amount=4321.5,
				customer_net_amount=1234.5,
				total_working_hours=10,
				docstatus=1,
			)
			c[f"trn_{side}"] = self._raw(
				"Equipment Transport",
				f"TRN-{tag}",
				company=company,
				project=project,
				destination_type="Project",
				date=first,
				docstatus=1,
				financial_status="Pending",
				cost_bearer="Customer",
			)
			c[f"fill_{side}"] = self._raw(
				"Project Diesel Fill",
				f"FILL-{tag}",
				company=company,
				project=project,
				supplier=supplier,
				date=first,
				litres=10,
				unit_price=2,
				price_exception=1,
				docstatus=0,
			)
			c[f"review_{side}"] = self._raw(
				"Equipment Needs Review", f"REV-{tag}", company=company, project=project, docstatus=0
			)
			employee = c.emp_a if side == "a" else c.emp_b
			c[f"review_item_{side}"] = self._raw(
				"Equipment Needs Review Item",
				f"REVI-{tag}",
				parent=c[f"review_{side}"],
				parenttype="Equipment Needs Review",
				parentfield="items",
				idx=1,
				kind="Tool",
				item_code=c.item,
				operator=employee,
				approved_qty=1,
			)
			c[f"custody_{side}"] = self._raw(
				"Employee Tool Custody",
				f"CUS-{tag}",
				company=company,
				employee=employee,
				movement="Handover",
				item_code=c.item,
				qty=1,
				date=first,
				handover_status="Awaiting handover",
				review=c[f"review_{side}"],
				review_item=c[f"review_item_{side}"],
				docstatus=0,
			)
			c[f"pi_{side}"] = self._raw(
				"Purchase Invoice", f"PI-{tag}", company=company, supplier=supplier, posting_date=first
			)
			c[f"je_{side}"] = self._raw(
				"Journal Entry",
				f"JE-{tag}",
				company=company,
				posting_date=first,
				voucher_type="Journal Entry",
				docstatus=1,
			)
			c[f"asset_{side}"] = self._raw(
				"Asset",
				f"AST-{tag}",
				asset_name=f"AST-{tag}",
				company=company,
				docstatus=1,
				status="Submitted",
			)
		# company B holds a tool (a Transfer needs a balance) and has a diesel price
		self._raw(
			"Employee Tool Custody",
			f"CUS-HELD-{b}",
			company=c.B,
			employee=c.emp_b,
			movement="Handover",
			item_code=c.item,
			qty=2,
			date=first,
			docstatus=1,
		)
		self._raw(
			"Card Company Settings",
			f"CCS-{b}",
			parent="Card Settings",
			parenttype="Card Settings",
			parentfield="company_settings",
			idx=99,
			company=c.B,
			diesel_unit_price=3.21,
		)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		return c

	def _project(self, name, company):
		proj = frappe.new_doc("Project")
		proj.project_name = name
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, name, company):
		eq = frappe.new_doc("Card Equipment")
		eq.update(
			{
				"company": company,
				"equipment_type": self._m["etype"],
				"equipment_name": name,
				"ownership": "ملك",
				"rate_type": "باليوم",
				"rate": 750,
				"daily_hours": 10,
			}
		)
		eq.insert(ignore_permissions=True)
		return eq.name

	def _supplier(self, name):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = name
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _customer(self, name):
		cust = frappe.new_doc("Customer")
		cust.customer_name = name
		cust.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		cust.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		cust.insert(ignore_permissions=True)
		return cust.name

	def _item(self, code):
		item = frappe.new_doc("Item")
		item.update(
			{
				"item_code": code,
				"item_name": code,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		)
		item.insert(ignore_permissions=True)
		return item.name

	def _user(self, roles, restrict=None, operator=False):
		email = f"bola-{frappe.generate_hash(length=8)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "BOLA Matrix",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		if operator:
			self._raw(
				"Employee",
				"EMP-OP-" + frappe.generate_hash(length=8),
				first_name="Operator",
				employee_name="Operator",
				company=self.ctx.A,
				status="Active",
				user_id=email,
			)
		frappe.clear_cache(user=email)
		return email

	# ---------- probes ----------
	def _snapshot(self):
		doctypes = frappe.get_all("DocType", filters={"module": "Card", "issingle": 0}, pluck="name")
		out = {}
		for doctype in sorted({*doctypes, *EXTRA_WATCHED}):
			out[doctype] = tuple(frappe.db.sql(f"select count(*), max(modified) from `tab{doctype}`")[0])
		return out

	def _call(self, path, kwargs):
		"""(exception, result) of one call as the session user; messages are dropped."""
		try:
			return None, frappe.get_attr(path)(**kwargs)
		except Exception as exc:
			return exc, None
		finally:
			frappe.clear_messages()
			frappe.local.response.pop("filecontent", None)

	def _leaks(self, case, result):
		if case.leak:
			return case.leak(result, self.ctx)
		return self.ctx.marker in frappe.as_json(result or {})

	def _assert_quiet(self, before, writes, path, label, case):
		self.assertEqual(self._snapshot(), before, f"{path}: {label} changed the database")
		if not case.writes:
			# a refused insert may take a naming-series number first (rolled back with the request)
			self.assertEqual(frappe.db.transaction_writes, writes, f"{path}: {label} ran a write query")

	def _check_cross(self, path, case):
		c = self.ctx
		if case.cross is None:
			self.assertTrue(case.unscoped, f"{path}: no company case and no reason")
			if case.writes:
				return  # documented in unscoped; nothing company-scoped to aim at
			kwargs = case.own(c) if case.own else {}
		else:
			kwargs = case.cross(c)
		frappe.set_user(self._user(case.roles, restrict=c.A, operator=case.operator))
		before, writes = self._snapshot(), frappe.db.transaction_writes
		exc, result = self._call(path, kwargs)
		if case.expect == "refused" and case.cross is not None:
			self.assertIsInstance(
				exc, PERMISSION, f"{path}: company-B call not refused ({exc!r}, {result!r})"
			)
		else:
			if exc is not None:
				self.assertIsInstance(exc, PERMISSION, f"{path}: unexpected error {exc!r}")
			self.assertFalse(self._leaks(case, result), f"{path}: company-B data reached a company-A user")
		self._assert_quiet(before, writes, path, "a company-B call", case)
		if case.control:
			frappe.set_user("Administrator")
			exc, result = self._call(path, kwargs)
			self.assertIsNone(exc, f"{path}: control call failed ({exc!r})")
			self.assertTrue(self._leaks(case, result), f"{path}: the probe cannot see company-B data")

	def _check_role(self, path, case):
		c = self.ctx
		kwargs = (case.own or case.cross or (lambda _c: {}))(c)
		for roles in case.denied:
			with self.subTest(roles=roles):
				frappe.set_user("Administrator")
				frappe.set_user(self._user(roles))
				before, writes = self._snapshot(), frappe.db.transaction_writes
				exc, result = self._call(path, kwargs)
				if case.denied_result:
					self.assertIsNone(exc, f"{path}: {exc!r}")
					self.assertTrue(case.denied_result(result), f"{path}: {result!r} for roles {roles}")
				else:
					self.assertIsInstance(
						exc, case.role_refusal, f"{path}: roles {roles} not refused ({result!r})"
					)
				self._assert_quiet(before, writes, path, f"a call with roles {roles}", case)

	def _check_read(self, path, case):
		c = self.ctx
		kwargs = (case.own or case.cross or (lambda _c: {}))(c)
		frappe.set_user(self._user(case.roles, restrict=c.A, operator=case.operator))
		before, writes = self._snapshot(), frappe.db.transaction_writes
		exc, _result = self._call(path, kwargs)
		self.assertIsNone(exc, f"{path}: the allowed read failed ({exc!r})")
		self._assert_quiet(before, writes, path, "a read", case)

	def _check_rest_create(self, doctype, roles, doc):
		c = self.ctx
		frappe.set_user(self._user(roles, restrict=c.A))
		before = frappe.db.count(doctype, {"company": c.B})
		try:
			rest_insert(doc(c))
			refused = False
		except THROWN:
			refused = True
		finally:
			frappe.clear_messages()
		frappe.set_user("Administrator")
		self.assertTrue(refused, f"{doctype}: a company-A user created a company-B record")
		self.assertEqual(frappe.db.count(doctype, {"company": c.B}), before)

	# ---------- guards: the table follows the code ----------
	def test_every_whitelisted_function_is_in_the_table(self):
		found = whitelisted_functions()
		self.assertEqual(sorted(set(found) - set(CASES)), [], "whitelisted functions missing from CASES")
		self.assertEqual(sorted(set(CASES) - set(found)), [], "CASES rows without a whitelisted function")

	def test_table_methods_match_the_decorators(self):
		for path, case in CASES.items():
			with self.subTest(path=path):
				fn = frappe.get_attr(path)
				self.assertEqual(
					sorted(frappe.allowed_http_methods_for_whitelisted_func[fn]), sorted(case.method)
				)
				if case.method == GET:
					self.assertFalse(case.writes, "a GET-only endpoint is documented as writing")

	def test_every_row_is_scoped_or_says_why(self):
		for path, case in CASES.items():
			with self.subTest(path=path):
				self.assertTrue(bool(case.cross) != bool(case.unscoped), "exactly one of cross / unscoped")
				self.assertTrue(case.denied, "no refused role set")
				roles = {r for roles in case.denied for r in roles} | set(case.roles)
				self.assertEqual(sorted(r for r in roles if not frappe.db.exists("Role", r)), [])

	def test_matrix_document_matches_the_source(self):
		text = MATRIX_DOC.read_text()
		self.assertEqual(
			_block(text, "doctype-matrix"), render_doctype_matrix(), "regenerate the DocType table"
		)
		self.assertEqual(
			_block(text, "endpoint-matrix"), render_endpoint_matrix(), "regenerate the endpoint table"
		)


def _slug(path):
	return path.removeprefix("card.").replace(".", "_")


def _make(kind, path, case):
	def test(self):
		getattr(self, f"_check_{kind}")(path, case)

	test.__doc__ = f"{kind}: {path}"
	return test


for _path, _case in CASES.items():
	_cross = _make("cross", _path, _case)
	if _case.hole:
		_cross = unittest.expectedFailure(_cross)
	setattr(TestBolaMatrix, f"test_cross_company__{_slug(_path)}", _cross)
	setattr(TestBolaMatrix, f"test_role_refused__{_slug(_path)}", _make("role", _path, _case))
	if not _case.writes:
		setattr(TestBolaMatrix, f"test_read_makes_no_write__{_slug(_path)}", _make("read", _path, _case))


def _make_rest(doctype, roles, doc):
	def test(self):
		self._check_rest_create(doctype, roles, doc)

	test.__doc__ = f"frappe.client.insert: {doctype}"
	return test


for _doctype, (_roles, _doc, _hole) in REST_CREATE_PROBES.items():
	_test = _make_rest(_doctype, _roles, _doc)
	if _hole:
		_test = unittest.expectedFailure(_test)
	setattr(TestBolaMatrix, f"test_rest_create_other_company__{_doctype.lower().replace(' ', '_')}", _test)
