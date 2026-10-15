# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_last_day, getdate, nowdate

from card.api import recompute_customer, recompute_supplier

# direction constants live in card.constants (re-exported here for callers/tests)
from card.constants import (
	CUSTOMER_BILLING_DIRECTIONS,
	DIR_INTERNAL,
	DIR_RENTED_IN,
	DIR_RENTED_OUT,
	DIR_SUBRENTAL,
	OWNED,
	SUPPLIER_BILLING_DIRECTIONS,
	allowed_directions,
	derive_direction,
)
from card.notifications import notify
from card.settings import setting
from card.transfer import covering_assignment, validate_card_days


class CardMonthlyCard(Document):
	def before_validate(self):
		# Ported verbatim-in-behaviour from Server Script "Card Monthly Card - Validate" v4 (Before Validate).
		doc_month = cint(self.month)
		doc_year = cint(self.year)
		if not doc_month or not doc_year:
			frappe.throw(_("Month and year are required"))

		if not self.shift:
			self.shift = setting("default_shift")

		eq = frappe.db.get_value(
			"Card Equipment",
			self.equipment,
			[
				"company",
				"ownership",
				"rental_direction",
				"rate_type",
				"rate",
				"daily_hours",
				"rental_start_date",
				"rental_end_date",
				"is_unit_component",
				"default_customer",
				"customer_rate_type",
				"customer_rate",
			],
			as_dict=True,
		)
		if not eq:
			frappe.throw(_("Equipment not found: {0}").format(self.equipment))
		if eq.is_unit_component:
			frappe.throw(
				_(
					"This equipment is a unit component; the monthly card is kept on the unit, not the component."
				)
			)
		if self.company and self.company != eq.company:
			frappe.throw(_("The card's company does not match the equipment's company"))

		# ---- period of the card (first: the fiscal-year and project rules need it) ----
		first_day = getdate(str(doc_year) + "-" + str(doc_month).zfill(2) + "-01")
		last_day = get_last_day(first_day)
		self.from_date = first_day
		self.to_date = last_day
		today = getdate(nowdate())

		# retro entry window (owner 2026-10-14): past periods only within the CURRENT fiscal year
		self._validate_fiscal_year_window(first_day, last_day, today)

		# ---- F.7: the equipment is the single source of truth — mirror it LIVE.
		# fetch_from does not refresh on the submit save (docstatus is already 1 by
		# then), so this explicit read keeps submit-time direction/rates current.
		self.card_direction = eq.rental_direction or derive_direction(eq.ownership)
		if self.card_direction not in allowed_directions(eq.ownership):
			frappe.throw(
				_(
					"Equipment {0}: direction {1} is not valid for ownership {2}. Fix the equipment first."
				).format(self.equipment, self.card_direction, eq.ownership)
			)
		if self.card_direction in CUSTOMER_BILLING_DIRECTIONS:
			self.customer = eq.default_customer
			self.customer_rate_type = eq.customer_rate_type
			self.customer_rate = flt(eq.customer_rate)
		else:
			self.customer = None
			self.customer_rate_type = None
			self.customer_rate = 0

		# ---- F.7: the project follows the assignment covering the card's month
		# (retro months keep their historical project); free entry when none covers it
		covering = covering_assignment(self.equipment, first_day, last_day)
		if covering:
			self.project = covering.project

		# customer mismatch is a review flag, never a block (owner F.7.3)
		if self.project and self.customer:
			project_customer = frappe.db.get_value("Project", self.project, "customer")
			if project_customer and project_customer != self.customer:
				frappe.msgprint(
					_(
						"The project's customer ({0}) differs from the equipment's customer ({1}). Review before submitting."
					).format(project_customer, self.customer),
					title=_("Customer mismatch"),
					indicator="orange",
				)

		# location/assignment constraint (phase A): working days must fall inside
		# an assignment period for the card's project (units check every component).
		validate_card_days(self)

		# ---- day rows ----
		seen = {}
		hours_by_date = {}
		total_hours = 0.0
		work_days = 0
		limit_field = "max_day_shift_hours" if self.shift == "نهاري" else "max_night_shift_hours"
		max_hours = flt(setting(limit_field)) or 12
		over_shift_limit = []
		for row in self.days:
			if not row.operation_date:
				frappe.throw(_("There is a day row without a date"))
			d = getdate(row.operation_date)
			key = str(d)
			if d < first_day or d > last_day:
				frappe.throw(_("Date {0} is outside the card's month").format(key))
			if key in seen:
				frappe.throw(_("Date {0} is duplicated in the card").format(key))
			seen[key] = 1
			if row.day_status != "عمل":
				row.working_hours = 0
			h = flt(row.working_hours)
			if h < 0:
				frappe.throw(_("Negative hours on day {0}").format(key))
			if h > 0 and d > today:
				frappe.throw(_("Cannot record operating hours for a future day: {0}").format(key))
			if h > max_hours:
				# Shift limit is advisory only: every recorded hour is billed, so a day
				# over the limit is flagged for review, never blocked (owner 2026-10-14).
				over_shift_limit.append(key + " (" + str(h) + ")")
			if h > 0:
				total_hours = total_hours + h
				work_days = work_days + 1
				hours_by_date[key] = h

		# ---- shift limit (advisory warning, never blocks; every recorded hour is billed) ----
		if over_shift_limit:
			frappe.msgprint(
				_(
					"Days over the {0}-hour shift limit for shift {1} (recorded and billed — review): {2}"
				).format(max_hours, self.shift, "، ".join(over_shift_limit)),
				title=_("Shift hours exceeded warning"),
				indicator="orange",
			)

		# ---- supplier-side amount (only directions that bill a supplier; F.5 bases) ----
		self.rate_type = eq.rate_type
		self.rate = flt(eq.rate)
		self.total_working_hours = total_hours
		self.working_days = work_days
		if self.card_direction in SUPPLIER_BILLING_DIRECTIONS:
			hourly_rate = self._hourly_for(eq.rate_type, flt(eq.rate), eq.daily_hours, required=True)
			self.amount = flt(total_hours * hourly_rate, 2)
		else:
			self.amount = 0  # internal / rented-out: no supplier billing

		# ---- additions / deductions (v4; S3 adds configured types + sides) ----
		# Side default = the card's billed side; sub-rental rows must say which
		# invoice they belong to. Typed rows (adjustment_type_ref) are validated
		# against Card Settings and mirror the type's kind; legacy untyped rows
		# keep the v1.1 behaviour (counted on the supplier side).
		default_side = "Customer" if self.card_direction == DIR_RENTED_OUT else "Supplier"
		configured = {
			(t.company, t.type_name): t
			for t in (frappe.get_doc("Card Settings").get("adjustment_types") or [])
		}
		total_additions = 0.0
		total_deductions = 0.0
		sided = {"Supplier": 0.0, "Customer": 0.0}
		for adj in self.adjustments or []:
			a = flt(adj.amount)
			if a <= 0:
				frappe.throw(
					_("The addition/deduction amount must be greater than zero: {0}").format(
						adj.description or ""
					)
				)
			if adj.adjustment_type_ref:
				typ = configured.get((self.company, adj.adjustment_type_ref))
				if not typ or typ.disabled:
					frappe.throw(
						_(
							"Addition/deduction type {0} is not configured (or is disabled) for company {1} in Card Settings."
						).format(adj.adjustment_type_ref, self.company)
					)
				adj.adjustment_type = typ.kind
			if not adj.side:
				if self.card_direction == DIR_SUBRENTAL:
					frappe.throw(
						_(
							"Sub-rental cards bill both parties; choose the side (Supplier/Customer) for the addition/deduction {0}."
						).format(adj.description or adj.adjustment_type_ref or "")
					)
				adj.side = default_side
			if adj.adjustment_type_ref:
				if adj.side == "Customer" and not self.customer:
					frappe.throw(
						_(
							"The card has no customer; a customer-side addition/deduction needs one: {0}."
						).format(adj.adjustment_type_ref)
					)
				if adj.side == "Supplier" and not self.supplier:
					frappe.throw(
						_(
							"The card has no supplier; a supplier-side addition/deduction needs one: {0}."
						).format(adj.adjustment_type_ref)
					)
			signed = a if adj.adjustment_type == "إضافة" else -a
			if adj.adjustment_type == "إضافة":
				total_additions = total_additions + a
			elif adj.adjustment_type == "خصم":
				total_deductions = total_deductions + a
			else:
				frappe.throw(_("Unknown type in additions and deductions: {0}").format(adj.adjustment_type))
			sided[adj.side] = sided[adj.side] + signed
		self.total_additions = flt(total_additions, 2)
		self.total_deductions = flt(total_deductions, 2)
		# Supplier net: rental amount + supplier-side rows only (legacy rows are
		# all Supplier after the backfill, so stored baselines are unchanged).
		self.net_amount = flt(flt(self.amount) + sided["Supplier"], 2)

		# ---- customer-side amount (rate mirrored from the equipment; the SI itself is S3) ----
		if self.card_direction in CUSTOMER_BILLING_DIRECTIONS:
			customer_hourly = self._hourly_for(
				self.customer_rate_type, flt(self.customer_rate), eq.daily_hours, required=False
			)
			self.customer_amount = flt(total_hours * customer_hourly, 2)
		else:
			self.customer_amount = 0
		self.customer_net_amount = (
			flt(flt(self.customer_amount) + sided["Customer"], 2)
			if flt(self.customer_amount) or sided["Customer"]
			else 0
		)

		# ---- duplicate card: same equipment + month + year + shift ----
		dup = frappe.get_all(
			"Card Monthly Card",
			filters={
				"equipment": self.equipment,
				"month": self.month,
				"year": self.year,
				"shift": self.shift,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
			},
			pluck="name",
			limit=1,
		)
		if dup:
			frappe.throw(
				_("A {0} card already exists for the same equipment and month: {1}").format(
					self.shift, dup[0]
				)
			)

		# ---- shift length warning (per card, per day; each shift card stands alone) ----
		if setting("warn_on_shift_hours_exceeded"):
			shift_hours = flt(eq.daily_hours)
			if shift_hours > 0:
				over = [
					k + " (" + str(hours_by_date[k]) + ")"
					for k in sorted(hours_by_date.keys())
					if hours_by_date[k] > shift_hours
				]
				if over:
					frappe.msgprint(
						_("Days exceeding shift hours ({0} hours): {1}").format(shift_hours, "، ".join(over)),
						title=_("Shift hours exceeded warning"),
						indicator="orange",
					)
			else:
				frappe.msgprint(
					_(
						"Shift hours are not set for equipment {0}; the shift-hours-exceeded warning will not appear."
					).format(self.equipment),
					title=_("Shift hours"),
					indicator="orange",
				)

		# ---- rental period (flag for review, hours still counted) ----
		if setting("warn_outside_rental_period") and eq.ownership != "ملك" and hours_by_date:
			if not eq.rental_start_date:
				frappe.msgprint(
					_("The equipment has no rental start date. Review the rental data."),
					title=_("Review rental period"),
					indicator="orange",
				)
			else:
				rs = getdate(eq.rental_start_date)
				re_end = getdate(eq.rental_end_date) if eq.rental_end_date else None
				outside = []
				for k in sorted(hours_by_date.keys()):
					d = getdate(k)
					if d < rs or (re_end and d > re_end):
						outside.append(k)
				if outside:
					frappe.msgprint(
						_(
							"Days with operation outside the rental period (calculated, needs review): {0}"
						).format("، ".join(outside)),
						title=_("Review rental period"),
						indicator="orange",
					)

	def _hourly_for(self, basis, rate, equipment_daily_hours, required):
		"""Hourly rate for a F.5 basis, shared by both sides: بالساعة = rate;
		باليوم = rate over the equipment's daily hours; بالشهر = rate over the
		standard month hours (Card Settings, default 260). With required=True a
		missing basis/divisor throws (supplier-billing cards must price)."""
		if basis == "باليوم":
			dh = flt(equipment_daily_hours)
			if dh <= 0:
				if required:
					frappe.throw(_("Set the daily working hours for equipment {0}").format(self.equipment))
				return 0.0
			return rate / dh
		if basis == "بالساعة":
			return rate
		if basis == "بالشهر":
			month_hours = flt(setting("standard_month_hours")) or 260
			return rate / month_hours
		if required:
			frappe.throw(_("Equipment rate type is not defined: {0}").format(self.equipment))
		return 0.0

	def _validate_fiscal_year_window(self, first_day, last_day, today):
		"""Owner rule (2026-10-14): cards may be back-entered for past months, but
		only within the CURRENT fiscal year. Skipped when no fiscal year exists."""
		try:
			from erpnext.accounts.utils import get_fiscal_year

			fy = get_fiscal_year(today, company=self.company)
		except Exception:
			return
		fy_name, fy_start, fy_end = fy[0], getdate(fy[1]), getdate(fy[2])
		if last_day < fy_start or first_day > fy_end:
			frappe.throw(
				_(
					"Card period {0}-{1} is outside the current fiscal year {2}; past cards are allowed only within it."
				).format(self.year, self.month, fy_name)
			)

	def before_submit(self):
		# A card that bills a customer is final only when its EQUIPMENT carries the customer.
		if self.card_direction in CUSTOMER_BILLING_DIRECTIONS and not self.customer:
			frappe.throw(
				_(
					"The equipment has no customer; set the customer on the equipment before submitting a {0} card."
				).format(self.card_direction)
			)

	def on_submit(self):
		self._snapshot_settings_used()
		self._sync_supplier()
		self._sync_customer()
		notify(
			"notify_on_card_submit",
			[self.owner],
			_("Monthly operation card submitted: {0}").format(self.name),
			_("Card {0} for equipment {1} was submitted.").format(
				self.name, self.equipment_name or self.equipment
			),
			self,
		)

	def on_cancel(self):
		self._sync_supplier()
		self._sync_customer()

	def _snapshot_settings_used(self):
		"""Store the calculation-affecting values used at submit time so a
		submitted card never depends on later equipment/settings changes.
		Read-only snapshot; never changes net_amount or any amount field."""
		eq = (
			frappe.db.get_value("Card Equipment", self.equipment, ["daily_hours", "الوقود_على"], as_dict=True)
			or frappe._dict()
		)
		daily_hours = flt(eq.daily_hours)
		hourly = self._hourly_for(self.rate_type, flt(self.rate), daily_hours, required=False)
		self.db_set("daily_hours_used", daily_hours, update_modified=False)
		self.db_set("hourly_rate_used", hourly, update_modified=False)
		self.db_set("diesel_policy_used", eq.get("الوقود_على"), update_modified=False)
		# customer-side snapshot (phase E): the hourly rate the customer amount used
		self.db_set(
			"customer_rate_used",
			self._hourly_for(self.customer_rate_type, flt(self.customer_rate), daily_hours, required=False),
			update_modified=False,
		)
		# F.7 snapshot: direction, customer and the supplier rate basis used at submit
		self.db_set("direction_used", self.card_direction, update_modified=False)
		self.db_set("customer_used", self.customer, update_modified=False)
		self.db_set("rate_basis_used", self.rate_type, update_modified=False)

	def _sync_customer(self):
		# Customer registry sync (phase E, non-blocking like the supplier one).
		if self.customer and self.card_direction in CUSTOMER_BILLING_DIRECTIONS:
			try:
				recompute_customer(self.customer)
			except Exception:
				frappe.log_error(
					title="Card Equipment Customer sync failed: " + str(self.customer),
					message="Card " + str(self.name) + " (event " + str(self.docstatus) + ")",
				)
				frappe.msgprint(
					_(
						"Could not update the customer record {0}. The card was saved normally; use the «Refresh numbers» button in the customer record."
					).format(self.customer),
					title=_("Customer record"),
					indicator="orange",
				)

	def _sync_supplier(self):
		# Ported from Server Scripts "Card Equipment Supplier - Sync on Submit/Cancel" (non-blocking).
		if self.supplier and self.ownership != "ملك":
			try:
				recompute_supplier(self.supplier)
			except Exception:
				frappe.log_error(
					title="Card Equipment Supplier sync failed: " + str(self.supplier),
					message="Card " + str(self.name) + " (event " + str(self.docstatus) + ")",
				)
				frappe.msgprint(
					_(
						"Could not update the supplier record {0}. The card was saved normally; use the «Refresh numbers» button in the supplier record."
					).format(self.supplier),
					title=_("Supplier record"),
					indicator="orange",
				)
