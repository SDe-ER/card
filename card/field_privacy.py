# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Financial privacy of Card Equipment (Owner decision 2026-10-31) and of Card Monthly Card money fields (FR-162,
Owner decision O-20, 2026-11-10).

Card Equipment: the Asset purchase value, the internal hourly rate and the cost centers (the equipment's and the
Asset's) sit at permlevel 2, read only by System Manager, Card Manager and Accounts Manager; the commercial terms
stay at permlevel 1.

Card Monthly Card: the ten Currency fields (``rate``, ``amount``, ``total_additions``, ``total_deductions``,
``net_amount``, ``hourly_rate_used``, ``customer_rate``, ``customer_amount``, ``customer_rate_used``,
``customer_net_amount``) sit at permlevel 1; the child ``Card Monthly Card Adjustment.amount`` sits at permlevel 1
too and inherits the parent's level-1 rights. Level-1 read is granted to the four current level-0 readers only
(System Manager, Card Manager, Card User, Accounts Manager). The DocType has no DocPerm for Card Operator or for
the CARD Mobile portal roles, so if any future change were to give them level-0 read they would still never see the
money fields.

Frappe applies these levels to the form, the REST API, list and report views and their exports. Two paths it does
not cover and that CARD closes here:

- a document's change history (Version) reaches every reader of the document, at any level, with the raw values:
  :func:`mask_restricted_version` masks new Versions of a private DocType, keeping who changed a field above level 0
  and when but never its values;
- the Jinja print template receives the loaded doc with its level-1 field values: :func:`card_print_can_view_money`
  is the Jinja helper the Card Monthly Card print format uses to hide every money row from a user without level-1
  read.

Nothing is deleted; the data stays on the record."""

import json

import frappe
from frappe.utils import cint

HISTORY_LEVEL = 1  # Versions reach level-0 readers: every field above level 0 is masked there
MASKED = "•••"
PRIVATE_DOCTYPES = ("Card Equipment",)

# FR-162 (Owner decision O-20): the money fields of Card Monthly Card that permlevel 1 moves above Card Operator /
# CARD Mobile. The adjustment child's own level-1 ``amount`` follows the parent's level-1 rights.
CARD_MONEY_FIELDS = (
	"rate",
	"amount",
	"total_additions",
	"total_deductions",
	"net_amount",
	"hourly_rate_used",
	"customer_rate",
	"customer_amount",
	"customer_rate_used",
	"customer_net_amount",
)
MONEY_DOCTYPE = "Card Monthly Card"
MONEY_LEVEL = 1


def restricted_fields(doctype, level=HISTORY_LEVEL):
	return {df.fieldname for df in frappe.get_meta(doctype).fields if cint(df.permlevel) >= level}


def _roles(user=None):
	user = user or frappe.session.user
	return set(frappe.get_roles(user))


def can_view_money(doctype=MONEY_DOCTYPE, user=None, level=MONEY_LEVEL):
	"""True when the user's ROLES grant read at the given permlevel on ``doctype``.

	Administrator always qualifies (Frappe treats it as every role). A document share or an ``if_owner`` read never
	raises the permlevel; this check reads only the DocType's own ``permissions`` table."""
	if (user or frappe.session.user) == "Administrator":
		return True
	roles = _roles(user)
	for perm in frappe.get_meta(doctype).permissions:
		if cint(perm.permlevel) == level and perm.read and perm.role in roles:
			return True
	return False


def card_print_can_view_money():
	"""Jinja helper for the Card Monthly Card print format (FR-162): True when the session user may read the money
	fields (permlevel 1 of Card Monthly Card). The print engine loads the doc without permlevel filtering, so the
	template must guard every money row on its own."""
	return can_view_money()


def strip_money(columns, rows, keys=CARD_MONEY_FIELDS, summary=None, tile_labels=()):
	"""Remove money columns, row values and summary tiles in place of hiding them, so the amounts never reach the
	browser (same shape as :func:`card.report_access.strip_ledger`). Pass the report's full column/row/summary set."""
	keys = tuple(keys)
	columns = [c for c in columns if (c.get("fieldname") if isinstance(c, dict) else None) not in keys]
	for row in rows or ():
		if isinstance(row, dict):
			for key in keys:
				row.pop(key, None)
	if summary is not None:
		summary = [t for t in summary if (t.get("label") if isinstance(t, dict) else None) not in tile_labels]
		return columns, summary
	return columns


def mask_restricted_version(doc, method=None):
	"""Version before_insert: mask the values of every field above level 0 in the change history of a private
	doctype, in its own fields and in its child-table rows."""
	if doc.ref_doctype not in PRIVATE_DOCTYPES or not doc.data:
		return
	meta = frappe.get_meta(doc.ref_doctype)
	restricted = restricted_fields(doc.ref_doctype)
	child = {df.fieldname: restricted_fields(df.options) for df in meta.get_table_fields()}
	data = json.loads(doc.data)
	masked = _mask_changes(data.get("changed"), restricted)
	for table, row in (data.get("added") or []) + (data.get("removed") or []):
		for field in child.get(table, ()):
			if isinstance(row, dict) and field in row:
				row[field] = MASKED
				masked = True
	for entry in data.get("row_changed") or []:
		if len(entry) == 4:
			masked = _mask_changes(entry[3], child.get(entry[0], ())) or masked
	if masked:
		doc.data = frappe.as_json(data, indent=None, separators=(",", ":"))


def _mask_changes(changes, restricted):
	masked = False
	for change in changes or []:
		if change and change[0] in restricted:
			change[1:] = [MASKED, MASKED]
			masked = True
	return masked
