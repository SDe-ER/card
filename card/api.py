# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.utils import cint, flt

from card.party_registry import registry_row
from card.report_access import assert_report_role, permitted_companies, query_companies
from card.settings import setting


def recompute_supplier(supplier):
	"""Recompute one supplier's registry record from ALL its submitted, non-owned cards.
	Shared by the refresh API and the Card Monthly Card submit/cancel events.
	Writes only to "Card Equipment Supplier"."""
	cards = frappe.get_all(
		"Card Monthly Card",
		filters=[["supplier", "=", supplier], ["docstatus", "=", 1], ["ownership", "!=", "ملك"]],
		fields=[
			"equipment",
			"total_working_hours",
			"amount",
			"total_additions",
			"total_deductions",
			"year",
			"month",
		],
		limit_page_length=0,
	)
	eqs = set()
	hours = 0.0
	net = 0.0
	periods = []
	for c in cards:
		eqs.add(c.equipment)
		hours = hours + flt(c.total_working_hours)
		net = net + flt(c.amount) + flt(c.total_additions) - flt(c.total_deductions)
		periods.append(str(c.year) + "-" + str(c.month).zfill(2))
	periods = sorted(periods)

	row = registry_row("Card Equipment Supplier", "supplier", supplier)
	if row and row != supplier:
		# a row left misnamed by an old rename: realign it to the party's name
		frappe.rename_doc("Card Equipment Supplier", row, supplier, force=True, ignore_permissions=True)
		row = supplier
	if row:
		rec = frappe.get_doc("Card Equipment Supplier", row)
	else:
		rec = frappe.new_doc("Card Equipment Supplier")
		rec.supplier = supplier
	rec.equipment_count = len(eqs)
	rec.card_count = len(cards)
	rec.total_hours = flt(hours, 2)
	rec.total_net = flt(net, 2)
	rec.first_month = periods[0] if periods else None
	rec.last_month = periods[-1] if periods else None
	rec.last_refreshed = frappe.utils.now_datetime()
	if rec.is_new():
		rec.insert(ignore_permissions=True)
	else:
		rec.save(ignore_permissions=True)
	return {"supplier": supplier, "cards": len(cards), "net": flt(net, 2)}


@frappe.whitelist(methods=["POST"])
def refresh_supplier(supplier: str | None = None):
	"""Refresh one supplier, or all suppliers with submitted non-owned cards.
	Ported from Server Script "Card Equipment Supplier - Refresh" v1.1. System Manager only."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Not allowed: this operation is for System Managers only"))

	if supplier:
		suppliers = [supplier]
	else:
		suppliers = sorted(
			list(
				set(
					frappe.get_all(
						"Card Monthly Card",
						filters=[
							["docstatus", "=", 1],
							["ownership", "!=", "ملك"],
							["supplier", "is", "set"],
						],
						pluck="supplier",
						limit_page_length=0,
					)
				)
			)
		)

	done = []
	for one in suppliers:
		done.append(recompute_supplier(one))
	return done


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def card_suppliers_query(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict):
	"""Link-filter query for the supplier reports: rows of the CARD supplier
	registry (Card Equipment Supplier, named by the supplier) with at least one
	Card Monthly Card in a company the user may see (drafts + submitted;
	cancelled excluded). The filter links to the registry — readable by every
	report role — because Frappe validates report Link filter values against the
	user's own permissions, and operational roles cannot read Supplier."""
	assert_report_role()
	companies = query_companies(filters)
	if not companies:
		return []
	like = "%" + (txt or "") + "%"
	return frappe.db.sql(
		"""
		select r.name, r.supplier_name
		from `tabCard Equipment Supplier` r
		where exists (
			select 1 from `tabCard Monthly Card` c
			where c.supplier = r.name and c.docstatus < 2 and c.company in %(companies)s
		)
		and (r.name like %(txt)s or r.supplier_name like %(txt)s)
		order by r.name
		limit %(start)s, %(page_len)s
		""",
		{"txt": like, "start": start, "page_len": page_len, "companies": companies},
	)


def recompute_customer(customer):
	"""Recompute one customer's registry record from ALL its submitted
	customer-billing cards (rented-out + sub-rental). Operational counters and
	the card-accrued total only — balances are never stored in CARD; they live
	in the official AR (Sales Invoice / Payment Entry / GL Entry).
	Writes only to "Card Equipment Customer"."""
	from card.constants import CUSTOMER_BILLING_DIRECTIONS

	cards = frappe.get_all(
		"Card Monthly Card",
		filters=[
			["customer", "=", customer],
			["docstatus", "=", 1],
			["card_direction", "in", list(CUSTOMER_BILLING_DIRECTIONS)],
		],
		fields=["equipment", "total_working_hours", "customer_amount", "year", "month"],
		limit_page_length=0,
	)
	eqs = set()
	hours = 0.0
	accrued = 0.0
	periods = []
	for c in cards:
		eqs.add(c.equipment)
		hours = hours + flt(c.total_working_hours)
		accrued = accrued + flt(c.customer_amount)
		periods.append(str(c.year) + "-" + str(c.month).zfill(2))
	periods = sorted(periods)

	row = registry_row("Card Equipment Customer", "customer", customer)
	if row and row != customer:
		frappe.rename_doc("Card Equipment Customer", row, customer, force=True, ignore_permissions=True)
		row = customer
	if row:
		rec = frappe.get_doc("Card Equipment Customer", row)
	else:
		rec = frappe.new_doc("Card Equipment Customer")
		rec.customer = customer
	rec.equipment_count = len(eqs)
	rec.card_count = len(cards)
	rec.total_hours = flt(hours, 2)
	rec.total_accrued = flt(accrued, 2)
	rec.first_month = periods[0] if periods else None
	rec.last_month = periods[-1] if periods else None
	rec.last_refreshed = frappe.utils.now_datetime()
	if rec.is_new():
		rec.insert(ignore_permissions=True)
	else:
		rec.save(ignore_permissions=True)
	return {"customer": customer, "cards": len(cards), "accrued": flt(accrued, 2)}


@frappe.whitelist(methods=["POST"])
def refresh_customer(customer: str | None = None):
	"""Refresh one customer, or all customers with submitted billing cards.
	Mirror of refresh_supplier. System Manager only."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(_("Not allowed: this operation is for System Managers only"))

	from card.constants import CUSTOMER_BILLING_DIRECTIONS

	if customer:
		customers = [customer]
	else:
		customers = sorted(
			set(
				frappe.get_all(
					"Card Monthly Card",
					filters=[
						["docstatus", "=", 1],
						["card_direction", "in", list(CUSTOMER_BILLING_DIRECTIONS)],
						["customer", "is", "set"],
					],
					pluck="customer",
					limit_page_length=0,
				)
			)
		)

	done = []
	for one in customers:
		done.append(recompute_customer(one))
	return done


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def card_customers_query(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict):
	"""Link-filter query for the customer reports: rows of the CARD customer
	registry (Card Equipment Customer, named by the customer) with at least one
	Card Monthly Card in a company the user may see — the owner's "customers
	with at least one card" rule. Links to the registry for the same reason as
	card_suppliers_query."""
	assert_report_role()
	companies = query_companies(filters)
	if not companies:
		return []
	like = "%" + (txt or "") + "%"
	return frappe.db.sql(
		"""
		select r.name, r.customer_name
		from `tabCard Equipment Customer` r
		where exists (
			select 1 from `tabCard Monthly Card` c
			where c.customer = r.name and c.docstatus < 2 and c.company in %(companies)s
		)
		and (r.name like %(txt)s or r.customer_name like %(txt)s)
		order by r.name
		limit %(start)s, %(page_len)s
		""",
		{"txt": like, "start": start, "page_len": page_len, "companies": companies},
	)


@frappe.whitelist()
def card_project_options(txt: str | None = None, company: str | None = None):
	"""Options for the reports' Project filter (an Autocomplete, not a Link:
	Frappe validates report Link filter values against the user's own
	permissions, and operational roles cannot read Project). Projects of the
	companies the user may see; the reports scope their rows by company too."""
	assert_report_role()
	companies = query_companies({"company": company} if company else {})
	if not companies:
		return []
	like = "%" + (txt or "") + "%"
	rows = frappe.db.sql(
		"""
		select p.name, p.project_name
		from `tabProject` p
		where p.company in %(companies)s
		and (p.name like %(txt)s or p.project_name like %(txt)s)
		order by p.name
		limit 50
		""",
		{"txt": like, "companies": companies},
		as_dict=True,
	)
	return [
		{"value": r.name, "label": f"{r.name}: {r.project_name}" if r.project_name else r.name} for r in rows
	]


@frappe.whitelist()
def report_defaults():
	"""Report filter defaults for any report role (Card Settings itself is not
	readable by Card User)."""
	assert_report_role()
	return {
		"default_statement_type": setting("default_statement_type"),
		"include_draft_in_reports": setting("include_draft_in_reports"),
	}


@frappe.whitelist()
def card_company_options(txt: str | None = None):
	"""Options for the reports' Company filter: the companies the user may see.
	An Autocomplete rather than a Link — Frappe checks Link filter values for
	read before select and posts a permission message for every operational
	user; each report validates the company server-side (resolve_company)."""
	assert_report_role()
	needle = (txt or "").lower()
	return [c for c in permitted_companies() if needle in c.lower()][:50]


@frappe.whitelist(methods=["POST"])
def create_equipment_from_asset(asset: str):
	"""Return a NEW, UNSAVED Card Equipment prefilled from a submitted ERPNext Asset.

	Nothing is inserted: the client opens the prefilled form and the user completes the
	remaining mandatory fields (e.g. daily hours, equipment type) before saving."""
	frappe.has_permission("Card Equipment", "create", throw=True)
	frappe.has_permission("Asset", "read", asset, throw=True)

	values = frappe.db.get_value("Asset", asset, ["name", "asset_name", "company", "docstatus"], as_dict=True)
	if not values:
		frappe.throw(_("Asset {0} does not exist").format(asset))
	if values.docstatus != 1:
		frappe.throw(_("Asset {0} must be submitted").format(asset))
	linked = frappe.db.get_value("Card Equipment", {"الأصل_في_erpnext": asset}, "name")
	if linked:
		frappe.throw(_("Asset {0} is already linked to equipment {1}").format(asset, linked))

	doc = frappe.new_doc("Card Equipment")
	doc.company = values.company
	doc.ownership = "ملك"
	doc.equipment_name = values.asset_name or values.name
	doc.set("الأصل_في_erpnext", values.name)
	return doc.as_dict()


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def available_assets_query(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
):
	"""Link-filter query for Card Equipment.الأصل_في_erpnext: submitted Assets of the
	given company that are not Scrapped/Sold and not already linked to a Card Equipment.
	Only for users who may create or edit Card Equipment, and only within the
	companies they may see for it."""
	# role permissions only: a shared Card Equipment must not open the Asset list
	perms = frappe.permissions.get_role_permissions(frappe.get_meta("Card Equipment"))
	if frappe.session.user != "Administrator" and not (perms.get("create") or perms.get("write")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	companies = query_companies(filters, "Card Equipment")
	if not companies:
		return []
	like = "%" + (txt or "") + "%"
	return frappe.db.sql(
		"""
		select a.name, a.asset_name
		from `tabAsset` a
		where a.docstatus = 1
		and a.status not in ('Scrapped', 'Sold')
		and a.company in %(companies)s
		and not exists (
			select 1 from `tabCard Equipment` e
			where e.`الأصل_في_erpnext` = a.name
		)
		and (a.name like %(txt)s or a.asset_name like %(txt)s)
		order by a.name
		limit %(start)s, %(page_len)s
		""",
		{
			"companies": companies,
			"txt": like,
			"start": frappe.utils.cint(start),
			"page_len": frappe.utils.cint(page_len),
		},
	)
