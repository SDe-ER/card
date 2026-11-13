# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-164 (#31, #47; closure plan WP-I1, owner decision O-11 D1): Diesel Dispense.

Tanks are modelled as ERPNext Warehouses of warehouse type "Fuel Tank" (O-11 D1 approved,
2026-11-10). A ``Diesel Dispense`` records litres leaving one tank (a Warehouse) to one
project on one date, optionally attributed to one Card Equipment. On submit, CARD creates
a DRAFT Stock Entry of purpose Material Transfer that moves ``dispensed_litres`` of the
company's diesel item from the tank Warehouse to the project level; the Stock Entry is
NEVER auto-submitted (FR-004). The accountant submits it after review.

FR-100 (owner 2026-11-02) is preserved: a tank fill never splits per equipment at GL —
the resulting Stock Entry carries the project (and, when the dispense names one, the
equipment as a diagnostic column on the detail row, but the stock movement itself stays
at project level). No GL line is created by the Dispense directly: CARD writes no GL
(AGENTS.md); the ERPNext Stock Entry does, and only when a user submits it.

Opt-in per company: ``Card Company Settings.enable_diesel_tanks`` (Check, default 0).
With the flag off the Dispense cannot be inserted or submitted for that company; the
route for the existing direct-fill flow is unchanged.

Rules enforced on every write path (form save, REST insert / PUT with docstatus = 0 or 1,
``frappe.client.set_value``, ``frappe.client.save``, savedocs, bulk update, bulk cancel):

- ``company``, ``date``, ``tank_warehouse``, ``project`` and ``dispensed_litres`` required;
  ``dispensed_litres`` must be strictly positive.
- The company must have ``enable_diesel_tanks = 1`` in its Card Company Settings row, else
  insert and submit are refused (``DieselTanksDisabledError``).
- ``tank_warehouse`` must be a Warehouse of warehouse type "Fuel Tank" that belongs to the
  dispense's company (``is_fuel_tank_warehouse``, ``check_warehouse_company``).
- ``card_equipment``, when set, must belong to the dispense's company
  (``validate_equipment_company``, F.8 pattern, reused from ``card.company``).
- Server-written fields (``stock_entry``, ``posting_key``) are protected on every save
  route (Lesson 1): a client-supplied value on insert, save, REST PUT, savedocs or
  ``set_value`` is dropped; on cancel / amend they are read from the stored record first.
- Idempotency (FR-090): active (Draft/Submitted) rows carry a composite ``posting_key``
  (``company|date|tank_warehouse|project|card_equipment``); a DB unique index on the field
  refuses a second active dispense for the same tuple. Cancelled dispenses clear the key
  (NULL), so a corrected dispense can be re-entered (MySQL allows many NULLs in a unique
  index; same pattern as GL Posting Log).
- Cancel: on ``before_cancel`` the generic FR-123 guard (``card.cancel_reason._refuse_changes``
  with ``neutral=True``) refuses a cancel that changes any other stored field; the draft
  Stock Entry linked on ``stock_entry`` is deleted (it has docstatus 0); the dispense's
  ``posting_key`` is cleared via ``db_set`` after Frappe's own cancel transition writes
  ``docstatus = 2``.

Scoping is picked up by the generic ``card.company_scope`` hooks registered for this
DocType in ``card/hooks.py`` ``_COMPANY_SCOPED`` (FR-131). ``tank_warehouse`` is also one
of the ``COMPANY_SOURCES`` of the scope module: a warehouse of another company is
refused on save by the hook, in addition to ``check_warehouse_company`` here.

No role or DocPerm is widened beyond O-09 / O-16 / O-20: the permissions on the JSON
mirror the sibling master DocTypes added by wave 7 (read / report to Card User and
Accounts Manager; create / write / submit / cancel / amend to Card Manager and System
Manager). Nothing on this DocType grants or widens access to another; the draft Stock
Entry is a standard ERPNext document whose own Role Permission Manager rights apply.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, flt, getdate

from card.cancel_reason import _refuse_changes as refuse_cancel_changes
from card.company import validate_equipment_company
from card.settings import company_setting

#: the Card Company Settings field flag that opts a company into the Tank module
ENABLE_FLAG = "enable_diesel_tanks"
#: the Warehouse Type that marks a Warehouse as a diesel fuel tank (O-11 D1)
FUEL_TANK_WAREHOUSE_TYPE = "Fuel Tank"
#: fields the server writes; client-supplied values on save are dropped, cancel reads them
#: back from the stored record (Lesson 1 defence)
SERVER_FIELDS: tuple[str, ...] = ("stock_entry", "posting_key")


class DieselTanksDisabledError(frappe.ValidationError):
	"""Raised when a company that has ``enable_diesel_tanks = 0`` tries to insert or submit
	a Diesel Dispense. The direct-fill flow (``Project Diesel Fill``) is unaffected."""


class NotAFuelTankWarehouseError(frappe.ValidationError):
	"""Raised when ``tank_warehouse`` is not a Warehouse of warehouse type
	``"Fuel Tank"`` of the dispense's company."""


def build_posting_key(
	company: str | None,
	date: str | None,
	tank_warehouse: str | None,
	project: str | None,
	card_equipment: str | None,
) -> str:
	"""Deterministic composite idempotency key (FR-090).

	The empty Card Equipment slot takes the literal "-" so a tank-level dispense (no
	equipment) is its own unit and does not collide with any equipment-attributed one.
	"""
	return "|".join(
		[
			cstr(company or ""),
			cstr(date or ""),
			cstr(tank_warehouse or ""),
			cstr(project or ""),
			cstr(card_equipment or "-"),
		]
	)


class DieselDispense(Document):
	"""Server-side controller for the ``Diesel Dispense`` DocType (FR-164)."""

	# ---------- Lifecycle ----------

	def validate(self):
		# every save route (form, REST insert / PUT, set_value, savedocs, bulk update) runs validate.
		# The cancel path skips validate (Frappe document.py `_save`) and is covered by before_cancel.
		self._restore_server_fields_on_save()
		self._check_tanks_enabled()
		self._check_required()
		self._check_positive_litres()
		self._check_warehouse()
		validate_equipment_company(self, "card_equipment")
		self._apply_posting_key()

	def before_submit(self):
		# A direct submit route (set_value / REST PUT with docstatus = 1) that also toggled the
		# enable flag between the insert and the submit would otherwise sneak through: validate
		# runs first on submit, but we re-check here as a belt-and-braces guard (Lesson 12 target).
		self._check_tanks_enabled()

	def on_submit(self):
		# Create the draft Stock Entry that records the movement; never auto-submit it (FR-004).
		from card.diesel_stock import post_dispense

		post_dispense(self)

	def before_cancel(self):
		# Lesson 2: Frappe skips validate on cancel and stores what the request sends, so a cancel
		# that changes any stored field (including the server-written ones) is refused through the
		# generic FR-123 guard before the state transition. ``get_latest`` returns the stored copy.
		latest = self.get_latest()
		if latest:
			# restore the server-written fields first so a forged request whose only change is on
			# one of them does not even reach the guard with mismatched values (and so a later
			# re-read sees the stored row untouched)
			for field in SERVER_FIELDS:
				self.set(field, latest.get(field))
			refuse_cancel_changes(self, latest, neutral=True)

	def on_cancel(self):
		# Clear the dispense's back-reference BEFORE deleting the draft Stock Entry,
		# else Frappe's ``LinkExistsError`` check refuses the delete (the Dispense
		# still points at the SE). Then remove the draft Stock Entry (docstatus 0),
		# then clear ``posting_key`` so a corrected dispense for the same tuple can
		# be entered. ``db_set`` skips validate and update_modified; Frappe's own
		# cancel transition has already set docstatus = 2.
		from card.diesel_stock import drop_stock_entry_by_name

		se_name = self.stock_entry
		self.db_set("stock_entry", None, update_modified=False)
		drop_stock_entry_by_name(se_name)
		self.db_set("posting_key", None, update_modified=False)

	# ---------- Guards ----------

	def _restore_server_fields_on_save(self):
		"""Lesson 1: a REST PUT, ``frappe.client.set_value``, savedocs or bulk update may carry
		forged values for ``stock_entry`` or ``posting_key``. On every save route drop what the
		client sent and take the stored values; on insert force them empty (the on_submit path
		writes them)."""
		if self.is_new():
			for field in SERVER_FIELDS:
				self.set(field, None)
			return
		stored = frappe.db.get_value(self.doctype, self.name, list(SERVER_FIELDS), as_dict=True)
		if not stored:
			return
		for field in SERVER_FIELDS:
			self.set(field, stored.get(field))

	def _check_tanks_enabled(self):
		if not cint_flag(self.company):
			frappe.throw(
				_(
					"Diesel tanks are not enabled for company {0}. Enable {1} in Card Company Settings first."
				).format(self.company, _("Enable diesel tanks")),
				DieselTanksDisabledError,
			)

	def _check_required(self):
		for field, label in (
			("company", _("Company")),
			("date", _("Date")),
			("tank_warehouse", _("Tank")),
			("project", _("Project")),
		):
			if not self.get(field):
				frappe.throw(_("{0} is required.").format(label))

	def _check_positive_litres(self):
		if flt(self.dispensed_litres) <= 0:
			frappe.throw(
				_("Dispensed litres must be greater than zero (got {0}).").format(flt(self.dispensed_litres))
			)

	def _check_warehouse(self):
		# FR-164: the tank must be a Fuel Tank warehouse of the dispense's company.
		from card.diesel_stock import check_warehouse_company, is_fuel_tank_warehouse

		if not is_fuel_tank_warehouse(self.tank_warehouse):
			frappe.throw(
				_("Warehouse {0} is not a diesel tank (its warehouse type is not {1}).").format(
					self.tank_warehouse, FUEL_TANK_WAREHOUSE_TYPE
				),
				NotAFuelTankWarehouseError,
			)
		check_warehouse_company(self.tank_warehouse, self.company)

	def _apply_posting_key(self):
		# The posting_key is a derived idempotency token: it is rewritten here on every save so an
		# edit that changes any component moves the key with it. The DB unique index on the field
		# refuses a second active (Draft/Submitted) row for the same tuple.
		self.posting_key = build_posting_key(
			self.company,
			getdate(self.date).isoformat() if self.date else None,
			self.tank_warehouse,
			self.project,
			self.card_equipment,
		)


def cint_flag(company: str | None) -> int:
	"""Return 1 when ``company`` has ``enable_diesel_tanks = 1`` in Card Company Settings, else 0.

	An empty / unknown company returns 0, which keeps the default behaviour (the flag is 0 for
	every company until the owner opts in).
	"""
	if not company:
		return 0
	value = company_setting(company, ENABLE_FLAG)
	try:
		return 1 if int(value or 0) else 0
	except (TypeError, ValueError):
		return 0
