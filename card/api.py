# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint, flt

from card.card.doctype.card_equipment.card_equipment import asset_equipment_values
from card.party_registry import registry_row
from card.report_access import assert_report_role, permitted_companies, query_companies
from card.settings import setting

# Registry aggregates (counts, hours, totals, months) are NOT stored: a registry
# row is per party across every company, so any stored figure would expose
# other companies' activity (#23). Figures are computed on request, per company
# the caller may see (party_figures).
REGISTRY_AGGREGATES = (
	"first_month",
	"last_month",
	"equipment_count",
	"card_count",
	"total_hours",
	"last_refreshed",
)
REGISTRY_MONEY = {"Supplier": "total_net", "Customer": "total_accrued"}


def _party_cards(party_type, party, companies=None):
	"""Submitted cards that bill ``party`` on its side (supplier: non-owned;
	customer: customer-billing directions), optionally limited to companies."""
	from card.constants import CUSTOMER_BILLING_DIRECTIONS

	if party_type == "Supplier":
		filters = [["supplier", "=", party], ["docstatus", "=", 1], ["ownership", "!=", "ملك"]]
		money = "net_amount"
	else:
		filters = [
			["customer", "=", party],
			["docstatus", "=", 1],
			["card_direction", "in", list(CUSTOMER_BILLING_DIRECTIONS)],
		]
		money = "customer_net_amount"
	if companies is not None:
		filters.append(["company", "in", list(companies) or [""]])
	return frappe.get_all(
		"Card Monthly Card",
		filters=filters,
		fields=["company", "equipment", "total_working_hours", money + " as money", "year", "month"],
		limit_page_length=0,
	)


def _figures_by_company(cards):
	by = {}
	for c in cards:
		f = by.setdefault(c.company, {"eq": set(), "cards": 0, "hours": 0.0, "money": 0.0, "periods": []})
		f["eq"].add(c.equipment)
		f["cards"] = f["cards"] + 1
		f["hours"] = f["hours"] + flt(c.total_working_hours)
		f["money"] = f["money"] + flt(c.money)
		f["periods"].append(str(c.year) + "-" + str(c.month).zfill(2))
	result = []
	for company in sorted(by):
		f = by[company]
		periods = sorted(f["periods"])
		result.append(
			{
				"company": company,
				"equipment_count": len(f["eq"]),
				"card_count": f["cards"],
				"total_hours": flt(f["hours"], 2),
				"total": flt(f["money"], 2),
				"first_month": periods[0] if periods else None,
				"last_month": periods[-1] if periods else None,
			}
		)
	return result


@frappe.whitelist()
def party_figures(party_type: str, party: str):
	"""Per-company figures of one registry party (supplier net / customer
	accrued = customer net), for the companies the caller may see only."""
	assert_report_role()
	registry = {"Supplier": "Card Equipment Supplier", "Customer": "Card Equipment Customer"}.get(party_type)
	if not registry:
		frappe.throw(_("Party type must be Supplier or Customer."))
	if not frappe.db.exists(registry, party) or not frappe.has_permission(registry, "read", party):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return _figures_by_company(_party_cards(party_type, party, permitted_companies()))


def _sync_registry_row(registry, field, party):
	"""Make sure ``party`` has its registry row, named after the party (a row a
	pre-hook rename left misnamed is realigned), with no stored aggregates."""
	row = registry_row(registry, field, party)
	if row and row != party:
		# a row left misnamed by an old rename: realign it to the party's name
		rename_doc(registry, row, party, force=True, ignore_permissions=True, show_alert=False)
		row = party
	rec = frappe.get_doc(registry, row) if row else frappe.new_doc(registry)
	if rec.is_new():
		rec.set(field, party)
	for fieldname in (*REGISTRY_AGGREGATES, *REGISTRY_MONEY.values()):
		if rec.meta.has_field(fieldname):
			rec.set(fieldname, None)
	if rec.is_new():
		rec.insert(ignore_permissions=True)
	else:
		rec.save(ignore_permissions=True)
	return rec.name


def recompute_supplier(supplier):
	"""Keep the supplier's registry row (Card Equipment Supplier) in sync. Shared
	by the refresh API and the Card Monthly Card events; no figures are stored
	(see REGISTRY_AGGREGATES)."""
	_sync_registry_row("Card Equipment Supplier", "supplier", supplier)
	return {"supplier": supplier}


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
	"""Keep the customer's registry row (Card Equipment Customer) in sync; no
	figures are stored. Balances live in the official AR (Sales Invoice /
	Payment Entry / GL Entry)."""
	_sync_registry_row("Card Equipment Customer", "customer", customer)
	return {"customer": customer}


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


@frappe.whitelist(methods=["GET"])
def get_only_company():
	"""The company a new CARD form takes when the user may see exactly one; else None.
	frappe already fills the user's default company; this covers a site with one
	company and no default. The field stays editable."""
	from card.company import only_visible_company

	return only_visible_company()


# Equipment field <- ERPNext Asset field. An owned (or managed) machine is already
# registered as an Asset, so its form takes these instead of retyping them.
ASSET_PREFILL = {
	"company": "company",
	"image": "image",
	"cost_center": "cost_center",
	"operator": "custodian",
	"insurance_company": "insurer",
	"insurance_policy_no": "policy_number",
	"insurance_expiry": "insurance_end_date",
}


def _asset_prefill(asset):
	"""Equipment values taken from a submitted Asset the user may read."""
	if not frappe.db.exists("Asset", asset):
		frappe.throw(_("Asset {0} does not exist").format(asset))
	frappe.has_permission("Asset", "read", asset, throw=True)
	values = frappe.db.get_value("Asset", asset, ["name", "docstatus", *ASSET_PREFILL.values()], as_dict=True)
	if values.docstatus != 1:
		frappe.throw(_("Asset {0} must be submitted").format(asset))
	prefill = {field: values.get(source) for field, source in ASSET_PREFILL.items() if values.get(source)}
	details = asset_equipment_values(asset)
	prefill.update({field: value for field, value in details.items() if value})
	prefill["equipment_type_from_asset"] = 1 if details.get("equipment_type") else 0
	return prefill


@frappe.whitelist(methods=["GET"])
def get_asset_prefill(asset: str):
	"""Values the equipment form fills from the chosen Asset (read only)."""
	frappe.has_permission("Card Equipment", "read", throw=True)
	return _asset_prefill(asset)


@frappe.whitelist(methods=["POST"])
def create_equipment_from_asset(asset: str):
	"""Return a NEW, UNSAVED Card Equipment prefilled from a submitted ERPNext Asset.

	Nothing is inserted: the client opens the prefilled form and the user completes the
	remaining mandatory fields (e.g. daily hours, equipment type) before saving."""
	frappe.has_permission("Card Equipment", "create", throw=True)
	prefill = _asset_prefill(asset)
	linked = frappe.db.get_value("Card Equipment", {"الأصل_في_erpnext": asset}, "name")
	if linked:
		frappe.throw(_("Asset {0} is already linked to equipment {1}").format(asset, linked))

	doc = frappe.new_doc("Card Equipment")
	doc.update(prefill)
	doc.ownership = "ملك"
	doc.operator_on = "الشركة"
	doc.set("الوقود_على", "الشركة")
	doc.set("الأصل_في_erpnext", asset)
	return doc.as_dict()


@frappe.whitelist(methods=["GET"])
@frappe.validate_and_sanitize_search_inputs
def available_assets_query(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
):
	"""Link-filter query for Card Equipment.الأصل_في_erpnext: submitted Assets of the
	given company that are not Scrapped/Sold and not already linked to a Card Equipment.
	Only for users who may create or edit Card Equipment and may read Assets (linking
	needs Asset read, see CardEquipment.validate_asset_link), within the companies they
	may see for Card Equipment. frappe.get_list applies the Asset permissions and User
	Permissions."""
	# role permissions only: a shared Card Equipment must not open the Asset list
	perms = frappe.permissions.get_role_permissions(frappe.get_meta("Card Equipment"))
	if frappe.session.user != "Administrator" and not (perms.get("create") or perms.get("write")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Asset", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	companies = query_companies(filters, "Card Equipment")
	if not companies:
		return []
	linked = frappe.get_all(
		"Card Equipment", filters={"الأصل_في_erpnext": ["is", "set"]}, pluck="الأصل_في_erpnext"
	)
	asset_filters = [
		["docstatus", "=", 1],
		["status", "not in", ["Scrapped", "Sold"]],
		["company", "in", companies],
	]
	if linked:
		asset_filters.append(["name", "not in", linked])
	like = "%" + (txt or "") + "%"
	return frappe.get_list(
		"Asset",
		fields=["name", "asset_name"],
		filters=asset_filters,
		or_filters=[["name", "like", like], ["asset_name", "like", like]],
		order_by="name asc",
		limit_start=cint(start),
		limit_page_length=cint(page_len),
		as_list=True,
	)
