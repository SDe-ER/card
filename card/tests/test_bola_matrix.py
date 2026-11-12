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
from frappe.client import cancel as rest_cancel
from frappe.client import insert as rest_insert
from frappe.client import save as rest_save
from frappe.client import submit as rest_submit
from frappe.model.rename_doc import rename_doc
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, get_first_day, get_last_day, nowdate

from card.constants import DIR_SUBRENTAL
from card.tests.test_controllers import _ensure_masters
from card.tests.transport_parties import company_paid

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
	allowed  positive control: the same company-A user succeeds with ``own`` (test_allowed_on_own_company__*)
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
	allowed: bool = False


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
	"card.card.doctype.card_settings.card_settings.getdoc": Case(
		method=AUTOCOMPLETE,
		roles=("Accounts Manager",),
		gate="override of frappe.desk.form.load.getdoc: Frappe read check (CardSettings.has_permission)",
		isolation="FR-133: other companies' Card Settings rows and their Version changes removed",
		effects="None (read only; GET and POST as the Desk form loads)",
		unscoped="wraps the Frappe form load; company scope tested in test_settings_company_scope",
		own=lambda c: {"doctype": "Card Settings", "name": "Card Settings"},
	),
	"card.card.doctype.card_settings.card_settings.get_docinfo": Case(
		method=AUTOCOMPLETE,
		roles=("Accounts Manager",),
		gate="override of frappe.desk.form.load.get_docinfo: Frappe read check (CardSettings.has_permission)",
		isolation="FR-133: other companies' Card Settings Version changes removed",
		effects="None (read only; GET and POST as the Desk form timeline loads)",
		unscoped="wraps the Frappe timeline load; company scope tested in test_settings_company_scope",
		own=lambda c: {"doctype": "Card Settings", "name": "Card Settings"},
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
		allowed=True,
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
		allowed=True,
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
	# ---------- return for correction (FR-152) ----------
	"card.governance_workflows.return_for_correction": Case(
		method=POST,
		roles=("Card Manager",),
		gate="CARD transaction doctype only; non-empty reason; write on the record, then Frappe apply_workflow (transition, role, active Workflow)",
		isolation="doc.check_permission(write) (has_card_permission / has_transport_permission / has_diesel_fill_permission)",
		effects="Returns the document to Draft through its Workflow, stores return_reason; one Info Comment",
		writes=True,
		cross=lambda c: {"doctype": CARD, "name": c.card_b, "reason": "x"},
		own=lambda c: {"doctype": CARD, "name": c.card_a, "reason": "x"},
		denied=((), ("Accounts Manager",)),
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
	"card.daily_log_generation.generate_monthly_cards": Case(
		method=POST,
		roles=("Card Manager",),
		gate="Card Monthly Card create on a probe card of the company and project (DocPerm, has_card_permission); Card Daily Log read",
		isolation="probe card company (Company User Permission, has_card_permission); project and equipment of the company; frappe.get_list on Card Daily Log (FR-131); insert() / save() of each card with the user's permissions",
		effects="Creates or updates draft Card Monthly Cards from Approved daily logs; never submits; submitted cards unchanged",
		writes=True,
		cross=lambda c: {"company": c.B, "project": c.proj_b, "month": f"{c.year}-{c.month}"},
		own=lambda c: {"company": c.A, "project": c.proj_a, "month": f"{c.year}-{c.month}"},
		denied=((), ("Card Operator",), ("Card Supervisor",)),
		allowed=True,
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
	"card.gl.posting.posting_period_run": Case(
		method=GET,
		roles=("Card Manager",),
		gate="Card Manager or System Manager (either posting side); run details only with Card Period Run read",
		isolation="_checked_endpoint_args per side: permitted_companies(sources, invoice, GL Posting Log)",
		cross=lambda c: {"company": c.B, "month": c.month, "year": c.year},
		own=lambda c: {"company": c.A, "month": c.month, "year": c.year},
		denied=((), ("Card User",), ("Accounts Manager",)),
	),
	# ---------- period run (FR-147) ----------
	"card.gl.period_run.build_run": Case(
		method=POST,
		roles=("Card Manager",),
		gate="Card Manager or System Manager; Card Period Run create; the company permitted for Card Monthly Card and Card Period Run",
		isolation="permitted_companies(Card Monthly Card, Card Period Run); insert/save under the record's own permission and has_company_permission",
		effects="Inserts or saves one draft Card Period Run (its snapshot); no GL, invoice or source-document write",
		writes=True,
		cross=lambda c: {"company": c.B, "month": c.month, "year": c.year},
		own=lambda c: {"company": c.A, "month": c.month, "year": c.year},
		denied=((), ("Card User",), ("Card Operator",), ("Accounts Manager",)),
	),
	"card.gl.period_run.period_run_status": Case(
		method=GET,
		roles=("Accounts Manager",),
		gate="Card Period Run read; the company permitted for Card Monthly Card and Card Period Run; totals only with level-1 read",
		isolation="permitted_companies(Card Monthly Card, Card Period Run); run.check_permission(read) (has_company_permission)",
		cross=lambda c: {"company": c.B, "month": c.month, "year": c.year},
		own=lambda c: {"company": c.A, "month": c.month, "year": c.year},
		denied=((), ("Card User",), ("Card Operator",)),
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
	"card.tool_custody.employee_company": Case(
		method=GET,
		roles=("Card Supervisor",),
		gate="screen role and Employee Tool Custody read; the employee is in the employee_query scope",
		isolation="query_companies(None, Employee Tool Custody); Employee User Permissions",
		cross=lambda c: {"employee": c.emp_b},
		own=lambda c: {"employee": c.emp_a},
		allowed=True,
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
		gate="screen role; create on the new record (check_permission before any read for the worker); insert with the user's own permissions",
		isolation="has_custody_permission: the companies of the employee and the receiving employee (FR-129)",
		effects="Inserts one draft Employee Tool Custody",
		writes=True,
		cross=lambda c: {
			"movement": "Transfer",
			"employee": c.emp_b,
			"item_code": c.item,
			"qty": 1,
			"to_employee": c.emp_b2,
		},
		own=lambda c: {
			"movement": "Transfer",
			"employee": c.emp_a,
			"item_code": c.item,
			"qty": 1,
			"to_employee": c.emp_a2,
		},
		denied=((), ("Card User",)),
		allowed=True,
	),
}

# Frappe's own insert endpoint (frappe.client.insert, also with docstatus 1 = insert and submit) on the CARD
# DocTypes whose company the server sets in validate, after Frappe's create check: name -> (doctype, roles,
# company-B doc, company-A doc or None). Each probe is a test of its own; the company-A doc is its positive control.
REST_CREATE_PROBES = {
	"equipment_needs_review": (
		"Equipment Needs Review",
		("Card Supervisor",),
		lambda c: {"doctype": "Equipment Needs Review", "project": c.proj_b},
		lambda c: {"doctype": "Equipment Needs Review", "project": c.proj_a},
	),
	"equipment_needs_request": (
		"Equipment Needs Request",
		("Card Supervisor",),
		lambda c: _request_doc(c.eq_b, c.emp_b),
		lambda c: _request_doc(c.eq_a, c.emp_a),
	),
	"equipment_needs_request_submitted": (
		"Equipment Needs Request",
		("Card Supervisor",),
		lambda c: {**_request_doc(c.eq_b, c.emp_b), "docstatus": 1},
		None,
	),
	"employee_tool_custody": (
		"Employee Tool Custody",
		("Card Supervisor",),
		lambda c: _transfer_doc(c.emp_b, c.emp_b2, c.item),
		lambda c: _transfer_doc(c.emp_a, c.emp_a2, c.item),
	),
	"employee_tool_custody_loss_submitted": (
		"Employee Tool Custody",
		("Card Supervisor",),
		lambda c: {**_transfer_doc(c.emp_b, None, c.item), "movement": "Loss", "docstatus": 1},
		None,
	),
	"employee_tool_custody_loss_over_balance": (
		"Employee Tool Custody",
		("Card Supervisor",),
		lambda c: {**_transfer_doc(c.emp_b, None, c.item), "movement": "Loss", "qty": 5, "docstatus": 1},
		None,
	),
}


def _request_doc(equipment, operator):
	return {
		"doctype": "Equipment Needs Request",
		"equipment": equipment,
		"operator": operator,
		"items": [{"kind": "Part", "description": "x", "qty": 1}],
	}


def _transfer_doc(employee, to_employee, item):
	doc = {
		"doctype": "Employee Tool Custody",
		"movement": "Transfer",
		"employee": employee,
		"item_code": item,
		"qty": 1,
		"date": nowdate(),
	}
	if to_employee:
		doc["to_employee"] = to_employee
	return doc


# Every ignore_permissions=True (call keyword) and `.ignore_permissions = True` (flag) in production code
# (card/, tests and patches excluded), per file and enclosing function: (count, why it is safe). A new site
# fails test_ignore_permissions_sites_are_allowed until it is reviewed and listed here.
IGNORE_PERMISSIONS_ALLOWED = {
	("card/api.py", "_sync_registry_row"): (
		3,
		"party registry row (global, no figures); reached only from refresh_* (System Manager), a card "
		"submit/cancel (card permission checked first) and a Supplier/Customer rename (see party_registry)",
	),
	("card/card/doctype/employee_tool_custody/employee_tool_custody.py", "_make_stock_entry"): (
		1,
		"Loss/Damage draft Material Issue made on submit, in the custody's company; Frappe checks submit on "
		"the custody record first, and has_custody_permission (FR-129) refuses a user who may not see the "
		"employee's company (test_rest_create_other_company__employee_tool_custody_loss_submitted)",
	),
	("card/card/doctype/employee_tool_custody/employee_tool_custody.py", "on_cancel"): (
		1,
		"deletes only the draft entry this movement made (same company, own marker); cancel right and "
		"has_custody_permission checked first (test_loss_entry_needs_the_custody_rights_of_its_company)",
	),
	("card/card/doctype/equipment_transport/equipment_transport.py", "_audit_status_change"): (
		1,
		"Version of an authorized financial decision (record_financial_decision gate), as Frappe does",
	),
	("card/dimension.py", "ensure_card_equipment_dimension"): (
		1,
		"install / before_tests bootstrap of the Accounting Dimension; no request path",
	),
	("card/gl/events.py", "_build_non_taxable_credit_note"): (
		2,
		"FR-156: the credit note draft and its GL Posting Log, created in on_submit of the main SI "
		"(after `_check_credit_note_mode_still_on` in before_submit); same pattern as "
		"`build_monthly_posting` which also inserts a draft invoice + its log under the posting gate",
	),
	("card/gl/integrity.py", "link_supplier_invoice"): (1, "Linked GL Posting Log after the endpoint's gate"),
	("card/gl/journal_link.py", "link_accrual_journal"): (
		1,
		"Linked GL Posting Log after the endpoint's gate",
	),
	("card/gl/masters.py", "_ensure_item_group"): (1, "posting master Item Group, after the posting gate"),
	("card/gl/masters.py", "_ensure_item"): (1, "posting master Item, after the posting gate"),
	("card/gl/masters.py", "_reconcile_item_tax_template"): (
		1,
		"posting Item Tax Template, after the posting gate",
	),
	("card/gl/masters.py", "_ensure_item_tax_template"): (
		1,
		"posting Item Tax Template, after the posting gate",
	),
	("card/gl/masters.py", "ensure_selling_price_list"): (1, "posting Price List, after the posting gate"),
	("card/gl/posting.py", "build_monthly_posting"): (
		2,
		"draft invoice and its GL Posting Log after _checked_endpoint_args (role, company) and _check_party",
	),
	("card/gl/posting.py", "rebuild_monthly_posting"): (
		1,
		"deletes the CARD draft it replaces, after the same gate as build_monthly_posting",
	),
	("card/install.py", "ensure_card_roles"): (1, "install / migrate: CARD roles"),
	("card/install.py", "_retire_legacy_custom_module"): (1, "install / migrate: legacy Module Def"),
	("card/install.py", "_ensure_print_default_property_setter"): (1, "install / migrate: print default"),
	("card/install.py", "_ensure_card_desk_icon"): (2, "install / migrate: CARD desk icon"),
	("card/notifications.py", "notify"): (
		1,
		"Notification Log for the named recipients of an authorized action",
	),
	("card/party_registry.py", "before_rename"): (
		1,
		"Supplier/Customer merge hook: drops the merged party's registry row; Frappe's rename permission check "
		"follows and its refusal rolls the request back (test_supplier_rename_without_write_is_refused)",
	),
	("card/party_registry.py", "after_rename"): (
		2,
		"Supplier/Customer rename hook: realigns the registry row, after Frappe's rename permission check",
	),
	("card/tool_custody.py", "item_query"): (
		1,
		"global Items after _check_screen (documented in the function)",
	),
	("card/transfer.py", "sync_equipment_location"): (1, "Info Comment on the equipment's location change"),
	("card/transfer.py", "_record_overlap"): (1, "Info Comment recording an assignment overlap"),
	("card/transfer.py", "_apply_row_transfer"): (
		3,
		"close/open assignments on transport submit; submit right and has_transport_permission checked first "
		"(test_transport_cannot_move_other_company_equipment)",
	),
	("card/transfer.py", "reverse_transfer"): (
		2,
		"delete/reopen the assignments the transport wrote, on cancel; cancel right checked first",
	),
}


def ignore_permission_sites():
	"""{(file, enclosing function): count} of ignore_permissions=True / .ignore_permissions = True."""
	out = {}
	root = REPO / "card"

	def truthy(node):
		return isinstance(node, ast.Constant) and node.value in (True, 1)

	def visit(node, func, rel):
		if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
			func = node.name
		hits = 0
		if isinstance(node, ast.Call):
			hits = sum(1 for k in node.keywords if k.arg == "ignore_permissions" and truthy(k.value))
		elif isinstance(node, ast.Assign) and truthy(node.value):
			hits = sum(
				1
				for t in node.targets
				if (isinstance(t, ast.Attribute) and t.attr == "ignore_permissions")
				or (
					isinstance(t, ast.Subscript)
					and isinstance(t.slice, ast.Constant)
					and t.slice.value == "ignore_permissions"
				)
			)
		if hits:
			out[(rel, func)] = out.get((rel, func), 0) + hits
		for child in ast.iter_child_nodes(node):
			visit(child, func, rel)

	for path in sorted(root.rglob("*.py")):
		parts = path.relative_to(root).parts
		if "tests" in parts or "patches" in parts:
			continue
		visit(ast.parse(path.read_text()), "<module>", str(path.relative_to(REPO)))
	return out


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
		c.emp_a2 = self._raw(
			"Employee", f"EMP-A2-{token}", first_name="A2", employee_name="A2", company=c.A, status="Active"
		)
		frappe.db.set_value("Card Equipment", c.eq_b, {"operator": c.emp_b, "current_project": c.proj_b})
		frappe.db.set_value("Card Equipment", c.eq_a, {"operator": c.emp_a, "current_project": c.proj_a})
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
		# each company's first worker holds two tools (a Transfer or a Loss needs a balance); B has a diesel price
		for company, employee, tag in ((c.B, c.emp_b, b), (c.A, c.emp_a, f"A-{token}")):
			self._raw(
				"Employee Tool Custody",
				f"CUS-HELD-{tag}",
				company=company,
				employee=employee,
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
				self.skipTest(case.unscoped)  # nothing company-scoped to aim at
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

	def _messages(self, exc):
		log = getattr(frappe.local, "message_log", None) or []
		return " ".join([str(exc or ""), *(json.dumps(m) if not isinstance(m, str) else m for m in log)])

	def _check_rest_create(self, doctype, roles, doc, own):
		c = self.ctx
		# a custody store of company B: without the company check a Loss would make B's Material Issue
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", c.wh_b)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		user = self._user(roles, restrict=c.A)
		frappe.set_user(user)
		before = (frappe.db.count(doctype, {"company": c.B}), frappe.db.count("Stock Entry"))
		exc = None
		try:
			rest_insert(doc(c))
		except Exception as error:
			exc = error
		text = self._messages(exc)
		frappe.clear_messages()
		frappe.set_user("Administrator")
		self.assertIsInstance(
			exc, PERMISSION, f"{doctype}: a company-A user created a company-B record ({exc!r})"
		)
		self.assertEqual((frappe.db.count(doctype, {"company": c.B}), frappe.db.count("Stock Entry")), before)
		for secret in ("holds", c.emp_b, c.B):
			self.assertNotIn(secret, text, f"{doctype}: the refusal tells company-B data")
		if own:
			frappe.set_user(user)
			name = rest_insert(own(c))["name"]
			frappe.set_user("Administrator")
			self.assertEqual(frappe.db.get_value(doctype, name, "company"), c.A)

	def _check_allowed(self, path, case):
		c = self.ctx
		frappe.set_user(self._user(case.roles, restrict=c.A, operator=case.operator))
		exc, _result = self._call(path, case.own(c))
		frappe.set_user("Administrator")
		self.assertIsNone(exc, f"{path}: the company-A call failed ({exc!r})")

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
				if case.writes:
					self.assertNotIn("GET", case.method, "a writing endpoint accepts GET")

	def test_every_row_is_scoped_or_says_why(self):
		for path, case in CASES.items():
			with self.subTest(path=path):
				self.assertTrue(bool(case.cross) != bool(case.unscoped), "exactly one of cross / unscoped")
				self.assertTrue(case.denied, "no refused role set")
				roles = {r for roles in case.denied for r in roles} | set(case.roles)
				self.assertEqual(sorted(r for r in roles if not frappe.db.exists("Role", r)), [])

	# ---------- ignore_permissions sites (allow-list and their gates) ----------
	def test_ignore_permissions_sites_are_allowed(self):
		found = ignore_permission_sites()
		allowed = {key: count for key, (count, _why) in IGNORE_PERMISSIONS_ALLOWED.items()}
		self.assertEqual(found, allowed, "review the new ignore_permissions site and list it with a reason")
		for key, (_count, why) in IGNORE_PERMISSIONS_ALLOWED.items():
			self.assertTrue(why.strip(), f"{key}: no justification")

	def _assignments(self, equipment):
		return frappe.get_all(
			"Card Equipment Assignment",
			filters={"equipment": equipment},
			fields=["name", "project", "from_date", "to_date", "modified"],
			order_by="name",
		)

	def _transport(self, equipment, project, day, submit):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"equipment": equipment,
				"project": project,
				"date": day,
				"transport_supplier": self.ctx.sup_a,
				"company": self.ctx.A,
				"amount": 100,
			}
		)
		company_paid(t).insert(ignore_permissions=True)
		if submit:
			t.submit()
		return t.name

	def test_transport_cannot_move_other_company_equipment(self):
		"""transfer.py _apply_row_transfer / reverse_transfer: a user of company B neither submits nor
		cancels a company-A transport, nor moves company-A equipment with a transport of his own."""
		c = self.ctx
		eq = self._equipment(f"EQ-T-{c.token}", c.A)
		proj_a2 = self._project(f"PRJ-A2-{c.token}", c.A)
		day = get_first_day(add_months(nowdate(), -2))
		submitted = self._transport(eq, c.proj_a, str(day), submit=True)
		draft = self._transport(eq, proj_a2, str(add_months(day, 1)), submit=False)
		before = self._assignments(eq)
		self.assertEqual(len(before), 1, "fixture: the submitted transport opened one assignment")
		frappe.set_user(self._user(("Card Manager", "Card User"), restrict=c.B))
		own = {
			"doctype": "Equipment Transport",
			"equipment": eq,
			"project": c.proj_b,
			"date": nowdate(),
			"transport_supplier": c.sup_b,
			"amount": 1,
			"payer": "No charge",
		}
		attempts = (
			("submit", lambda: rest_submit(frappe.get_doc("Equipment Transport", draft).as_dict())),
			("cancel", lambda: rest_cancel("Equipment Transport", submitted)),
			("insert as company B", lambda: rest_insert({**own, "company": c.B})),
			("insert without company", lambda: rest_insert(dict(own))),
		)
		for label, attempt in attempts:
			with self.subTest(attempt=label):
				with self.assertRaises(THROWN):
					attempt()
				frappe.clear_messages()
		frappe.set_user("Administrator")
		self.assertEqual(self._assignments(eq), before)
		self.assertEqual(frappe.db.get_value("Equipment Transport", draft, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Equipment Transport", submitted, "docstatus"), 1)

	def test_loss_entry_needs_the_custody_rights_of_its_company(self):
		"""employee_tool_custody.py _make_stock_entry / on_cancel: a user of company A neither submits a
		company-B Loss (draft Material Issue) nor cancels one (draft entry deletion); a role without submit
		is refused on his own company's Loss."""
		c = self.ctx
		loss_b = self._raw(
			"Employee Tool Custody",
			f"CUS-LOSS-{c.marker}",
			company=c.B,
			employee=c.emp_b,
			movement="Loss",
			item_code=c.item,
			qty=1,
			date=nowdate(),
			docstatus=0,
		)
		done_b = f"CUS-LOSS-DONE-{c.marker}"
		entry_b = self._raw(
			"Stock Entry",
			f"STE-{c.marker}",
			company=c.B,
			purpose="Material Issue",
			stock_entry_type="Material Issue",
			remarks=f"CARD tool custody {done_b}",
			docstatus=0,
		)
		self._raw(
			"Employee Tool Custody",
			done_b,
			company=c.B,
			employee=c.emp_b,
			movement="Loss",
			item_code=c.item,
			qty=1,
			date=nowdate(),
			stock_entry=entry_b,
			docstatus=1,
		)
		loss_a = self._raw(
			"Employee Tool Custody",
			f"CUS-LOSS-A-{c.token}",
			company=c.A,
			employee=c.emp_a,
			movement="Loss",
			item_code=c.item,
			qty=1,
			date=nowdate(),
			docstatus=0,
		)
		entries = frappe.db.count("Stock Entry")
		attempts = (
			(
				("Card Supervisor",),
				c.A,
				lambda: rest_submit(frappe.get_doc("Employee Tool Custody", loss_b).as_dict()),
			),
			(("Card Manager",), c.A, lambda: rest_cancel("Employee Tool Custody", done_b)),
			(
				("Card User",),
				None,
				lambda: rest_submit(frappe.get_doc("Employee Tool Custody", loss_a).as_dict()),
			),
		)
		for roles, restrict, attempt in attempts:
			with self.subTest(roles=roles):
				frappe.set_user("Administrator")
				frappe.set_user(self._user(roles, restrict=restrict))
				with self.assertRaises(THROWN):
					attempt()
				frappe.clear_messages()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Stock Entry"), entries)
		self.assertTrue(frappe.db.exists("Stock Entry", entry_b))
		self.assertEqual(frappe.db.get_value("Employee Tool Custody", done_b, "stock_entry"), entry_b)
		for name, docstatus in ((loss_b, 0), (done_b, 1), (loss_a, 0)):
			self.assertEqual(frappe.db.get_value("Employee Tool Custody", name, "docstatus"), docstatus)

	def test_registry_sync_needs_the_card_rights_of_its_company(self):
		"""api.py _sync_registry_row via CardMonthlyCard._sync_supplier/_sync_customer (on submit/cancel):
		a user of company A cannot submit or cancel a company-B card, so the registry rows stay as they are.
		The other path, api.py refresh_supplier/refresh_customer (the recompute loop), is System Manager only:
		test_role_refused__api_refresh_supplier / _customer."""
		c = self.ctx
		draft_b = self._raw(
			CARD,
			f"CARD-DRAFT-{c.marker}",
			company=c.B,
			equipment=c.eq_b,
			project=c.proj_b,
			supplier=c.sup_b,
			customer=c.cust_b,
			ownership="إيجار",
			card_direction=DIR_SUBRENTAL,
			month=c.month,
			year=int(c.year),
			shift="نهاري",
			docstatus=0,
		)
		rows = {
			reg: frappe.db.get_value(reg, party, "modified")
			for reg, party in (("Card Equipment Supplier", c.sup_b), ("Card Equipment Customer", c.cust_b))
		}
		frappe.set_user(self._user(("Card Manager",), restrict=c.A))
		for label, attempt in (
			("submit", lambda: rest_submit(frappe.get_doc(CARD, draft_b).as_dict())),
			("cancel", lambda: rest_cancel(CARD, c.card_b)),
		):
			with self.subTest(attempt=label):
				with self.assertRaises(THROWN):
					attempt()
				frappe.clear_messages()
		frappe.set_user("Administrator")
		for reg, modified in rows.items():
			party = c.sup_b if reg == "Card Equipment Supplier" else c.cust_b
			self.assertEqual(frappe.db.get_value(reg, party, "modified"), modified)
		self.assertEqual(frappe.db.get_value(CARD, draft_b, "docstatus"), 0)
		self.assertEqual(frappe.db.get_value(CARD, c.card_b, "docstatus"), 1)

	def test_supplier_rename_without_write_is_refused(self):
		"""party_registry.py before_rename / after_rename: a CARD user without Supplier write cannot rename
		or merge a supplier. Frappe runs before_rename (which drops the merged party's registry row) BEFORE
		its own rename permission check (frappe/model/rename_doc.py rename_doc -> validate_rename); the
		refusal rolls the request back, which the savepoint below stands for, and the row is back."""
		c = self.ctx
		modified = frappe.db.get_value("Card Equipment Supplier", c.sup_b, "modified")
		for roles in (("Card Manager",), ("Card User",), ("Accounts User",)):
			for merge in (False, True):
				with self.subTest(roles=roles, merge=merge):
					frappe.set_user("Administrator")
					frappe.set_user(self._user(roles))
					frappe.db.savepoint("bola_rename")
					with self.assertRaises(THROWN):
						rename_doc("Supplier", c.sup_b, c.sup_a if merge else c.sup_b + "-X", merge=merge)
					frappe.db.rollback(save_point="bola_rename")  # what the failed request does
					frappe.clear_messages()
					frappe.set_user("Administrator")
					self.assertTrue(frappe.db.exists("Supplier", c.sup_b))
					self.assertEqual(
						frappe.db.get_value("Card Equipment Supplier", c.sup_b, "modified"), modified
					)

	def test_server_set_company_doctypes_check_the_company(self):
		"""Every CARD DocType (not a child table) whose company the server sets (read-only field) has a
		has_permission hook, or a REST create probe here: Frappe checks create on the company sent."""
		has_perm, _query = _hooks()
		probed = {doctype for doctype, *_rest in REST_CREATE_PROBES.values()}
		for meta in card_doctypes():
			company = next((f for f in meta.get("fields") or [] if f["fieldname"] == "company"), None)
			if meta.get("istable") or not company or not company.get("read_only"):
				continue
			with self.subTest(doctype=meta["name"]):
				self.assertTrue(meta["name"] in has_perm or meta["name"] in probed)

	def test_draft_cannot_be_moved_to_other_company(self):
		"""A company-A draft re-pointed to company B (custody employee, request equipment, review project)
		is refused by the record-level check on the new value; the stored record is unchanged."""
		c = self.ctx
		custody = self._raw(
			"Employee Tool Custody",
			f"CUS-T-A-{c.token}",
			company=c.A,
			employee=c.emp_a,
			to_employee=c.emp_a2,
			movement="Transfer",
			item_code=c.item,
			qty=1,
			date=nowdate(),
			docstatus=0,
		)
		request = self._raw(
			"Equipment Needs Request",
			f"REQ-A-{c.token}",
			company=c.A,
			equipment=c.eq_a,
			operator=c.emp_a,
			project=c.proj_a,
			request_date=nowdate(),
			docstatus=0,
		)
		cases = (
			("Employee Tool Custody", custody, {"employee": c.emp_b, "to_employee": c.emp_b2}),
			("Employee Tool Custody", custody, {"employee": c.emp_b}),
			("Equipment Needs Request", request, {"equipment": c.eq_b, "operator": c.emp_b}),
			("Equipment Needs Review", c.review_a, {"project": c.proj_b}),
		)
		user = self._user(("Card Supervisor",), restrict=c.A)
		for doctype, name, change in cases:
			with self.subTest(doctype=doctype, change=change):
				frappe.set_user("Administrator")
				stored = frappe.db.get_value(doctype, name, ["modified", *change], as_dict=True)
				doc = frappe.get_doc(doctype, name).as_dict()
				doc.update(change)
				frappe.set_user(user)
				with self.assertRaises(PERMISSION):
					rest_save(doc)
				frappe.clear_messages()
				frappe.set_user("Administrator")
				self.assertEqual(
					frappe.db.get_value(doctype, name, ["modified", *change], as_dict=True), stored
				)

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
	if _case.allowed:
		setattr(
			TestBolaMatrix, f"test_allowed_on_own_company__{_slug(_path)}", _make("allowed", _path, _case)
		)


def _make_rest(doctype, roles, doc, own):
	def test(self):
		self._check_rest_create(doctype, roles, doc, own)

	test.__doc__ = f"frappe.client.insert: {doctype}"
	return test


for _probe, (_doctype, _roles, _doc, _own) in REST_CREATE_PROBES.items():
	setattr(
		TestBolaMatrix, f"test_rest_create_other_company__{_probe}", _make_rest(_doctype, _roles, _doc, _own)
	)
