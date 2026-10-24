# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Catalog phase 2a (FR-077): equipment make / model masters and part fitment rows.
A fitment row says that an ERPNext Item fits an equipment model or one machine. Its
status follows the DESIGN v4.1 states, and only a second, independent reviewer can
make it final (Owner decision Q5, 2026-10-23)."""

import re

import frappe

APPROVER_ROLES = ("Card Manager", "System Manager")

PENDING = "Pending Technical Review"
CONFIRMED = "Confirmed"
NOT_COMPATIBLE = "Not Compatible"
DECISIONS = (CONFIRMED, NOT_COMPATIBLE)
SECOND_REVIEW = "Pending Second Review"

APPLIES_TO_MODEL = "Equipment Model"
APPLIES_TO_MACHINE = "Equipment"

_SEPARATORS = re.compile(r"[\s\-_./]+")


def normalise(value):
	"""Upper case without spaces, dashes, dots, underscores or slashes, so that
	"PC200-8" and "pc 200 8" give the same key."""
	return _SEPARATORS.sub("", value or "").upper()


def is_approver(user=None):
	return bool(set(APPROVER_ROLES) & set(frappe.get_roles(user or frappe.session.user)))


# ---------- phase 2b: effective fit at read time (DESIGN 4.2, PLAN-phase2b section 8) ----------
# Four separate states, never merged: a compatible fit (machine or model), Not Compatible,
# Pending review, and no fitment record. Only an active Confirmed row is a fit (O6).
FIT_MACHINE = "confirmed_machine"
FIT_MODEL = "confirmed_model"
FIT_NOT_COMPATIBLE = "not_compatible"
FIT_PENDING = "pending"
FIT_UNKNOWN = "unknown"
COMPATIBLE = (FIT_MACHINE, FIT_MODEL)

# the request line keeps the state it was asked with (Select values of the line)
FIT_LABELS = {
	FIT_MACHINE: "Confirmed for machine",
	FIT_MODEL: "Confirmed for model",
	FIT_NOT_COMPATIBLE: "Not compatible",
	FIT_PENDING: "Pending review",
	FIT_UNKNOWN: "No fitment record",
}
MAX_FIT_ITEMS = 50
MACHINE_PAGE_LENGTH = 20


def _statuses(filters, item_codes):
	return {
		row.item_code: row.compatibility_status
		for row in frappe.get_all(
			"Card Equipment Part",
			filters={**filters, "is_active": 1, "item_code": ["in", item_codes]},
			fields=["item_code", "compatibility_status"],
		)
	}


def effective_fit(equipment, item_codes):
	"""The fit of each Item for the machine: {item_code: {"fit": state, "fit_model": label}}.
	The machine's decided row wins over its model's; a pending row is never a fit. Reads fixed
	fields only, never the evidence, reasons or reviewers (Q8). The caller checks the machine."""
	codes = sorted({code for code in item_codes or [] if code})
	if not codes:
		return {}
	model = frappe.db.get_value("Card Equipment", equipment, "equipment_model")
	machine = _statuses({"applies_to": APPLIES_TO_MACHINE, "card_equipment": equipment}, codes)
	by_model = _statuses({"applies_to": APPLIES_TO_MODEL, "equipment_model": model}, codes) if model else {}
	model_label = model and frappe.db.get_value("Card Equipment Model", model, "model_name")
	out = {}
	for code in codes:
		own, shared = machine.get(code), by_model.get(code)
		fit_model = None
		if own in DECISIONS:
			fit = FIT_MACHINE if own == CONFIRMED else FIT_NOT_COMPATIBLE
		elif shared in DECISIONS:
			fit = FIT_MODEL if shared == CONFIRMED else FIT_NOT_COMPATIBLE
			fit_model = model_label
		elif PENDING in (own, shared):
			fit = FIT_PENDING
		else:
			fit = FIT_UNKNOWN
		out[code] = {"fit": fit, "fit_model": fit_model}
	return out


def compatible_items(equipment):
	"""Item codes with a Confirmed fit for the machine (machine row, or model row the machine
	row does not overrule): the "fits this machine" list."""
	model = frappe.db.get_value("Card Equipment", equipment, "equipment_model")
	machine = {
		row.item_code: row.compatibility_status
		for row in frappe.get_all(
			"Card Equipment Part",
			filters={
				"applies_to": APPLIES_TO_MACHINE,
				"card_equipment": equipment,
				"is_active": 1,
				"compatibility_status": ["in", DECISIONS],
			},
			fields=["item_code", "compatibility_status"],
		)
	}
	codes = {code for code, status in machine.items() if status == CONFIRMED}
	if model:
		codes |= {
			code
			for code in frappe.get_all(
				"Card Equipment Part",
				filters={
					"applies_to": APPLIES_TO_MODEL,
					"equipment_model": model,
					"is_active": 1,
					"compatibility_status": CONFIRMED,
				},
				pluck="item_code",
			)
			if code not in machine
		}
	return sorted(codes)


def check_equipment_access(equipment):
	"""A machine is used for the fit only by a user who may read it (DocPerms, User Permissions,
	company isolation) or who operates it (Card Operator)."""
	from card.materials import OPERATOR_ROLE, has_any_role, operator_equipment, session_employee

	if equipment and frappe.db.exists("Card Equipment", equipment):
		if frappe.has_permission("Card Equipment", "read", doc=equipment):
			return
		if has_any_role([OPERATOR_ROLE]) and equipment in operator_equipment(session_employee()):
			return
	frappe.throw(frappe._("Not permitted"), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def fit_for(equipment: str, items: str | list):
	"""The fit of up to 50 Items for one machine (the inline item picker of CARD Mobile)."""
	from card.catalog import _list_items, check_catalog_user

	check_catalog_user()
	check_equipment_access(equipment)
	codes = frappe.parse_json(items) if isinstance(items, str) else items
	if not isinstance(codes, list) or len(codes) > MAX_FIT_ITEMS:
		frappe.throw(frappe._("Send a list of at most {0} items.").format(MAX_FIT_ITEMS))
	# only Items the caller may list in the catalog (his own Item rights), as the search does
	visible = (
		_list_items([["name", "in", [str(code) for code in codes]]], fields=["item_code"]) if codes else []
	)
	return effective_fit(equipment, [row.item_code for row in visible])


@frappe.whitelist(methods=["GET"])
def machines(txt: str | None = None, start: int = 0):
	"""Machines the caller may look up in the catalog: a Desk reader's own list (his DocPerms and
	User Permissions apply), or an operator's own machines. Searched and paged on the server."""
	from frappe.utils import cint

	from card.catalog import MAX_TEXT, _like, check_catalog_user
	from card.materials import (
		ENDED_STATUS,
		OPERATOR_ROLE,
		has_any_role,
		operator_equipment,
		session_employee,
	)

	check_catalog_user()
	txt = (txt or "").strip()[:MAX_TEXT]
	start = max(cint(start), 0)
	fields = ["name", "equipment_name", "equipment_model"]
	or_filters = {"name": ["like", _like(txt)], "equipment_name": ["like", _like(txt)]} if txt else None
	if frappe.has_permission("Card Equipment", "read"):
		rows = frappe.get_list(
			"Card Equipment",
			filters={"status": ["!=", ENDED_STATUS]},
			fields=fields,
			or_filters=or_filters,
			order_by="equipment_name asc, name asc",
			limit_start=start,
			limit_page_length=MACHINE_PAGE_LENGTH + 1,
		)
	elif has_any_role([OPERATOR_ROLE]):
		own = operator_equipment(session_employee())
		rows = (
			frappe.get_all(
				"Card Equipment",
				filters={"name": ["in", own]},
				fields=fields,
				or_filters=or_filters,
				order_by="equipment_name asc, name asc",
				limit_start=start,
				limit_page_length=MACHINE_PAGE_LENGTH + 1,
			)
			if own
			else []
		)
	else:
		rows = []
	labels = {
		row.name: row.model_name
		for row in frappe.get_all(
			"Card Equipment Model",
			filters={"name": ["in", sorted({r.equipment_model for r in rows if r.equipment_model})]},
			fields=["name", "model_name"],
		)
	}
	return {
		"machines": [
			{"name": r.name, "equipment_name": r.equipment_name, "model": labels.get(r.equipment_model)}
			for r in rows[:MACHINE_PAGE_LENGTH]
		],
		"has_more": len(rows) > MACHINE_PAGE_LENGTH,
	}
