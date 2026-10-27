# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD catalog search (phase 1, Owner 2026-10-22).

One paged read over the standard ERPNext catalogue: Item, Item Group, Brand, Item Barcode,
Item Manufacturer (OEM part numbers) and Item Alternative. CARD keeps no item master of its own.

Who sees what is decided on the server (``_read``):
- a user whose roles read a DocType gets ``frappe.get_list`` on it: his roles, User Permissions,
  shares and permission rules apply;
- a Card portal role without that read (the Card Operator; Owner G1 exception, widened by D-1 to
  OEM numbers and alternatives) gets the same catalogue rules on fixed safe fields, with his User
  Permissions and shares applied the way ``frappe.get_list`` applies them. Frappe has no public
  call that applies User Permissions without the role check, so ``_user_permission_filters``
  follows frappe v16 ``database/query.py``; ``test_catalog`` compares both paths (R7). Where
  Frappe would add permission query rules (hooks or a Permission Query server script) that CARD
  cannot apply, the restricted read returns nothing;
- anyone else gets nothing.
Card User reads the catalogue like a portal role (phase 2b, Owner decision A, 2026-10-23: the
read-only catalog view of CARD Mobile); he still has no access to requests.
Barcode and OEM matches, alternatives and ``has_more`` only ever come from items the user may
list. No stock, price, supplier or account is returned (stock stays with the F2 hint)."""

import frappe
from frappe import _
from frappe.utils import cint, nowdate

from card.materials import PORTAL_ROLES, has_any_role
from card.report_access import _role_reads

PAGE_LENGTH = 20
MAX_PAGE_LENGTH = 50
MAX_TEXT = 140
# barcode and OEM numbers are matched from this length (as ERPNext's item search index)
MIN_CODE_TEXT = 3
FIELDS = ["item_code", "item_name", "stock_uom", "image", "item_group", "brand", "allow_alternative_item"]
FILTER_KINDS = {"item_group": "Item Group", "brand": "Brand"}
# read-only catalog viewers of CARD Mobile (phase 2b, decision A): not a portal role
CATALOG_VIEW_ROLES = ("Card User",)
CATALOG_ROLES = (*PORTAL_ROLES, *CATALOG_VIEW_ROLES)


# ---------- who is asking ----------
def _reads_items():
	return _role_reads("Item")


def check_catalog_user():
	if frappe.session.user == "Guest" or not (_reads_items() or has_any_role(CATALOG_ROLES)):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _sees(doctype):
	"""OEM numbers and alternatives: for readers of the ERPNext DocType and for Card roles (D-1)."""
	return _role_reads(doctype) or has_any_role(CATALOG_ROLES)


def _permitted_docs(link_doctype, doctype):
	"""Values of ``link_doctype`` the user's User Permissions allow on ``doctype`` (applicable_for
	empty or ``doctype``; Frappe already expands tree descendants). None: no restriction."""
	rows = frappe.permissions.get_user_permissions(frappe.session.user).get(link_doctype) or []
	docs = [row.get("doc") for row in rows if row.get("applicable_for") in (None, "", doctype)]
	return docs or None


def _strict():
	return cint(frappe.get_system_settings("apply_strict_user_permissions"))


def _user_permission_filters(doctype):
	"""The User Permission conditions ``frappe.get_list`` adds for ``doctype`` (frappe v16
	``database/query.py`` ``get_user_permission_conditions``): on the record itself and on every
	Link field; an empty link passes unless strict user permissions are on."""
	filters = []
	fields = [frappe._dict(fieldname="name", options=doctype), *frappe.get_meta(doctype).get_link_fields()]
	for df in fields:
		if df.get("ignore_user_permissions"):
			continue
		docs = _permitted_docs(df.options, doctype)
		if docs is None:
			continue
		allowed = [df.fieldname, "in", docs]
		if _strict() or df.fieldname == "name":
			filters.append(allowed)
		else:
			filters.append([allowed, "or", [df.fieldname, "is", "not set"]])
	return filters


def _restriction(doctype):
	"""User Permissions, or a document shared with the user (shares trump them, as in Frappe's
	``get_permission_conditions``)."""
	conditions = _user_permission_filters(doctype)
	if not conditions:
		return []
	shared = frappe.share.get_shared(doctype, frappe.session.user)
	if shared:
		# Frappe's nested filters take one condition as itself, not as a one-item group
		restricted = conditions[0] if len(conditions) == 1 else _and(conditions)
		return [[restricted, "or", ["name", "in", shared]]]
	return conditions


def _has_query_rules(doctype):
	"""Permission query rules Frappe would add for ``doctype`` (hooks or a server script)."""
	from frappe.core.doctype.server_script.server_script_utils import get_server_script_map

	hooks = frappe.get_hooks("permission_query_conditions", {})
	return bool(
		hooks.get(doctype)
		or hooks.get("*")
		or get_server_script_map().get("permission_query", {}).get(doctype)
	)


def _read(doctype, filters, **kwargs):
	"""``frappe.get_list`` for a reader of ``doctype``; the restricted read only for Card portal
	roles (R1); nothing for anyone else or where Frappe would add rules CARD cannot apply."""
	if _role_reads(doctype):
		return frappe.get_list(doctype, filters=_and(filters), **kwargs)
	if not has_any_role(CATALOG_ROLES) or _has_query_rules(doctype):
		return []
	return frappe.get_all(doctype, filters=_and(filters + _restriction(doctype)), **kwargs)


def _and(conditions):
	"""Frappe's nested filter form: [c1, "and", c2, "and", ...]."""
	nested = []
	for condition in conditions:
		if nested:
			nested.append("and")
		nested.append(condition)
	return nested


# ---------- the item query ----------
def _like(txt):
	"""A LIKE pattern for the text: its own ``%`` and ``_`` stay literal."""
	escaped = txt.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	return f"%{escaped}%"


def _base_filters():
	return [
		["disabled", "=", 0],
		["has_variants", "=", 0],
		[["end_of_life", "is", "not set"], "or", ["end_of_life", ">", nowdate()]],
		[["is_stock_item", "=", 1], "or", ["is_purchase_item", "=", 1]],
	]


def _match_conditions(txt):
	"""Code or name; from three characters also a barcode (child table, inside the item query) or an
	OEM number the user may see (read through the same path as the OEM numbers shown, R2). No cap:
	nothing the user may list is dropped before his own rights apply (R3)."""
	pattern = _like(txt)
	match = [["item_code", "like", pattern], "or", ["item_name", "like", pattern]]
	if len(txt) >= MIN_CODE_TEXT:
		match += ["or", ["barcodes.barcode", "like", pattern]]
		if _sees("Item Manufacturer"):
			codes = _read(
				"Item Manufacturer",
				[["manufacturer_part_no", "like", pattern]],
				pluck="item_code",
				distinct=True,
				limit_page_length=0,
			)
			if codes:
				match += ["or", ["name", "in", sorted(set(codes))]]
	return [match]


def _list_items(conditions, start=0, page_length=None, fields=None):
	"""Items the user may list, with the CARD catalogue rules, through his own rights (one row per
	item, also when several barcodes match)."""
	return _read(
		"Item",
		_base_filters() + conditions,
		fields=fields or FIELDS,
		order_by="item_name asc, item_code asc",
		distinct=True,
		limit_start=start,
		limit_page_length=page_length or 0,
	)


# ---------- extras per page ----------
def _oem_numbers(codes):
	out = {}
	if not codes or not _sees("Item Manufacturer"):
		return out
	for row in _read(
		"Item Manufacturer",
		[["item_code", "in", codes]],
		fields=["item_code", "manufacturer", "manufacturer_part_no"],
		order_by="is_default desc, manufacturer asc",
		limit_page_length=0,
	):
		if row.manufacturer_part_no:
			out.setdefault(row.item_code, []).append(
				{"manufacturer": row.manufacturer, "part_no": row.manufacturer_part_no}
			)
	return out


def _alternatives(items):
	"""ERPNext Item Alternative rows for the page: X -> Y always, Y -> X only when two-way; only for
	items that allow alternatives and only alternatives the user may list himself."""
	codes = [item.item_code for item in items if item.allow_alternative_item]
	if not codes or not _sees("Item Alternative"):
		return {}
	fields = ["item_code", "alternative_item_code"]
	pairs = [
		(row.item_code, row.alternative_item_code)
		for row in _read("Item Alternative", [["item_code", "in", codes]], fields=fields, limit_page_length=0)
	]
	pairs += [
		(row.alternative_item_code, row.item_code)
		for row in _read(
			"Item Alternative",
			[["alternative_item_code", "in", codes], ["two_way", "=", 1]],
			fields=fields,
			limit_page_length=0,
		)
	]
	if not pairs:
		return {}
	visible = {
		row.item_code: row.item_name
		for row in _list_items(
			[["name", "in", sorted({alt for _main, alt in pairs})]], fields=["item_code", "item_name"]
		)
	}
	out = {}
	for main, alt in pairs:
		if alt in visible and alt != main and alt not in {a["item_code"] for a in out.get(main, [])}:
			out.setdefault(main, []).append({"item_code": alt, "item_name": visible[alt]})
	return out


def _page_window(start, page_length):
	return max(cint(start), 0), min(max(cint(page_length) or PAGE_LENGTH, 1), MAX_PAGE_LENGTH)


# ---------- endpoints ----------
@frappe.whitelist(methods=["GET"])
def search(
	txt: str | None = None,
	item_group: str | None = None,
	brand: str | None = None,
	start: int = 0,
	page_length: int = PAGE_LENGTH,
	equipment: str | None = None,
	fits: int = 0,
):
	"""One page of the catalogue for the search text (item code, item name, barcode, OEM number)
	and the filters (item group with its sub-groups, brand). ``has_more`` says whether another page
	exists; no total count is given. With ``equipment`` (phase 2b) every item carries its ``fit``
	for that machine; ``fits`` lists only the items Confirmed for it (machine or model)."""
	from card import fitment

	check_catalog_user()
	if equipment:
		fitment.check_equipment_access(equipment)
	txt = (txt or "").strip()[:MAX_TEXT]
	start, page_length = _page_window(start, page_length)

	conditions = _match_conditions(txt) if txt else []
	if item_group:
		# an unknown group (or one renamed meanwhile) lists nothing, like a hidden one
		if not frappe.db.exists("Item Group", item_group):
			return {"items": [], "has_more": False}
		# the group and its sub-groups (tree operators are not accepted inside nested filters)
		groups = [item_group, *frappe.db.get_descendants("Item Group", item_group)]
		conditions.append(["item_group", "in", groups])
	if brand:
		conditions.append(["brand", "=", brand])
	if equipment and cint(fits):
		compatible = fitment.compatible_items(equipment)
		if not compatible:
			return {"items": [], "has_more": False}
		conditions.append(["name", "in", compatible])

	rows = _list_items(conditions, start, page_length + 1)
	has_more = len(rows) > page_length
	rows = rows[:page_length]
	codes = [row.item_code for row in rows]
	oem = _oem_numbers(codes)
	alternatives = _alternatives(rows)
	items = [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"stock_uom": row.stock_uom,
			"image": row.image,
			"item_group": row.item_group,
			"item_group_label": _(row.item_group) if row.item_group else None,
			"brand": row.brand,
			"oem": oem.get(row.item_code, []),
			"alternatives": alternatives.get(row.item_code, []),
		}
		for row in rows
	]
	if equipment:
		fits_of = fitment.effective_fit(equipment, codes)
		for item in items:
			item.update(fits_of[item["item_code"]])
	return {"items": items, "has_more": has_more}


def quick_search(txt, limit=20):
	"""The inline item suggestions of the needs pages (``materials.search_items``): the same
	catalogue rules and rights as ``search``, code, name and unit only."""
	txt = (txt or "").strip()[:MAX_TEXT]
	return _list_items(
		_match_conditions(txt) if txt else [], 0, limit, fields=["item_code", "item_name", "stock_uom"]
	)


@frappe.whitelist(methods=["GET"])
def filter_options(kind: str, txt: str | None = None, start: int = 0, page_length: int = PAGE_LENGTH):
	"""Values for the Item Group or Brand filter, searched and paged on the server, read with the
	user's rights (the restricted read for Card portal roles). Item Group names are translated by
	Frappe, so they are matched by name or by their translation."""
	check_catalog_user()
	doctype = FILTER_KINDS.get(kind)
	if not doctype:
		frappe.throw(_("Unknown catalog filter"))
	txt = (txt or "").strip()[:MAX_TEXT]
	start, page_length = _page_window(start, page_length)
	if doctype == "Brand":
		names = _read(
			doctype,
			[["name", "like", _like(txt)]] if txt else [],
			pluck="name",
			order_by="name asc",
			limit_start=start,
			limit_page_length=page_length,
		)
		return [{"value": name, "label": name} for name in names]
	# Item Groups are few; the translated label is matched in Python
	needle = txt.casefold()
	options = sorted(
		(
			{"value": name, "label": _(name)}
			for name in _read(doctype, [], pluck="name", order_by="name asc", limit_page_length=0)
		),
		key=lambda o: o["label"].casefold(),
	)
	if needle:
		options = [o for o in options if needle in o["value"].casefold() or needle in o["label"].casefold()]
	return options[start : start + page_length]
