# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, get_last_day, getdate, nowdate

from card.adjustments import validate_downtime_fields
from card.api import recompute_customer, recompute_supplier
from card.card.doctype.card_stop_reason.card_stop_reason import SIDE_BOTH, billable_side_of
from card.card_value import PER_VOLUME_M3, bills_full_days, day_billing_basis

# direction constants live in card.constants (re-exported here for callers/tests)
from card.constants import (
	CUSTOMER_BILLING_DIRECTIONS,
	DIR_INTERNAL,
	DIR_RENTED_IN,
	DIR_RENTED_OUT,
	DIR_SUBRENTAL,
	OWNED,
	SHIFT_NIGHT,
	SUPPLIER_BILLING_DIRECTIONS,
	allowed_directions,
	derive_direction,
)
from card.equipment_status import check_equipment_status, equipment_is_new_on
from card.notifications import notify
from card.settings import setting
from card.transfer import (
	_assigned_on,
	_component_rows,
	_has_any_assignment,
	_in_unit_on,
	assignment_projects,
	is_billed_day,
	month_assignments,
	validate_card_days,
)


@frappe.whitelist(methods=["GET"])
def get_card_context(equipment: str, month: str, year: str, project: str | None = None):
	"""v3.0.0: what the card form fills in by itself once equipment, month and year are
	picked — the projects the approved transports put the equipment on that month, and
	the days it was on the chosen (or only) project. Read-only."""
	frappe.get_doc("Card Equipment", equipment).check_permission("read")
	first_day = getdate("%s-%s-01" % (cint(year), str(month).zfill(2)))
	last_day = get_last_day(first_day)
	rows = month_assignments(equipment, first_day, last_day)
	projects = []
	for a in rows:
		if a.project not in projects:
			projects.append(a.project)
	if not project and len(projects) == 1:
		project = projects[0]
	days = set()
	for a in rows:
		if a.project != project:
			continue
		start = max(getdate(a.from_date), first_day)
		end = min(getdate(a.to_date), last_day) if a.to_date else last_day
		while start <= end:
			days.add(str(start))
			start = add_days(start, 1)
	if days and frappe.db.get_value("Card Equipment", equipment, "is_unit"):
		# same rule as validate_card_days: a unit day needs every piece in the unit that
		# day on the project, once any piece has assignment history
		pieces = _component_rows(equipment)
		if any(_has_any_assignment(r.component) for r in pieces):
			days = {
				d
				for d in days
				if all(
					_assigned_on(r.component, project, getdate(d))
					for r in pieces
					if _in_unit_on(r, getdate(d))
				)
			}
	if days:
		# WP-05: a piece's days inside a unit period belong on the unit's card
		# (CardMonthlyCard._refuse_unit_component_days), so the form does not offer them
		from card.card.doctype.card_equipment.card_equipment import component_periods

		periods = component_periods(equipment)
		if periods:
			days = {d for d in days if not any(_in_unit_on(p, getdate(d)) for p in periods)}
	return {"projects": projects, "project": project, "days": sorted(days)}


class CardMonthlyCard(Document):
	def before_validate(self):
		# Ported verbatim-in-behaviour from Server Script "Card Monthly Card - Validate" v4 (Before Validate).
		doc_month = cint(self.month)
		doc_year = cint(self.year)
		if not doc_month or not doc_year:
			frappe.throw(_("Month and year are required"))

		if not self.shift:
			self.shift = setting("default_shift")
		# v3.0.0: a company operator is an Employee; the card keeps the name it prints
		if self.get("operator"):
			self.operator_name = frappe.db.get_value("Employee", self.operator, "employee_name")

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
				"day_billing_basis",
				"rental_start_date",
				"rental_end_date",
				"is_unit_component",
				"default_customer",
				"customer_rate_type",
				"customer_rate",
				"customer_rate_night",
				"load_volume_m3",
			],
			as_dict=True,
		)
		if not eq:
			frappe.throw(_("Equipment not found: {0}").format(self.equipment))
		# FR-118 (#45): stop reasons and the responsible party of each day row, before the
		# unit and assignment checks (a billable stopped day is billed like a working day)
		self._resolve_stop_reasons(eq.company, eq.rental_direction or derive_direction(eq.ownership))
		self._refuse_unit_component_days(eq)
		if self.company and self.company != eq.company:
			frappe.throw(_("The card's company does not match the equipment's company"))

		# ---- period of the card (first: the fiscal-year and project rules need it) ----
		first_day = getdate(str(doc_year) + "-" + str(doc_month).zfill(2) + "-01")
		last_day = get_last_day(first_day)
		self.from_date = first_day
		self.to_date = last_day
		today = getdate(nowdate())
		# FR-122: an ended equipment gets no new card after its exit (checked after the company match,
		# so another company's equipment status is never shown)
		if equipment_is_new_on(self):
			check_equipment_status(self.equipment, "monthly card", eq.company, period_start=first_day)

		# retro entry window (owner 2026-10-14): past periods only within the CURRENT fiscal year
		self._validate_fiscal_year_window(first_day, last_day, today)

		# ---- F.7: the equipment is the single source of truth — mirror it LIVE.
		# fetch_from does not refresh on the submit save (docstatus is already 1 by
		# then), so this explicit read keeps submit-time direction/rates current.
		self.card_direction = eq.rental_direction or derive_direction(eq.ownership)
		# FR-138 (C-05): the equipment's day billing basis, mirrored live like the rates (empty = prorated)
		self.day_billing_basis = day_billing_basis(eq.day_billing_basis)
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
			# FR-109 (Owner 2026-11-08): a night-shift card uses the equipment's
			# night-shift rate (same basis) when one is set; otherwise the customer rate
			if self.shift == SHIFT_NIGHT and flt(eq.customer_rate_night) > 0:
				self.customer_rate = flt(eq.customer_rate_night)
		else:
			self.customer = None
			self.customer_rate_type = None
			self.customer_rate = 0

		# ---- v3.0.0 (Owner 2026-10-19): the project comes from the approved transports ----
		self._resolve_project(first_day, last_day)
		self._warn_foreign_responsible_party()

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
		# FR-166: loads counted on working days (volume is priced only on a per-m³ customer rate)
		loads_total = 0
		billable_stopped = 0.0
		billable_stop_days = 0
		# FR-134: billable stopped hours per billed side (a Both reason counts on each side)
		stopped_for = {"Supplier": 0.0, "Customer": 0.0}
		# FR-138: days billed only by billable stopped hours, per side (a "Full day" basis bills them)
		stop_days_for = {"Supplier": 0, "Customer": 0}
		reason_sides = getattr(self, "_reason_sides", None) or {}
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
			# FR-166: loads are entered on a working day, zero hours allowed (the day status decides)
			loads = cint(row.loads_count)
			if loads < 0:
				frappe.throw(_("Negative loads on day {0}").format(key))
			if loads and row.day_status != "عمل":
				frappe.throw(_("Loads can be recorded only on a working day: {0}").format(key))
			if loads and d > today:
				frappe.throw(_("Cannot record loads for a future day: {0}").format(key))
			loads_total = loads_total + loads
			if h > 0 and d > today:
				frappe.throw(_("Cannot record operating hours for a future day: {0}").format(key))
			stopped = flt(row.stopped_hours)
			if stopped > 0 and d > today:
				frappe.throw(_("Cannot record stopped hours for a future day: {0}").format(key))
			# FR-118: a day has 24 hours, operating and stopped together (a day without stopped
			# hours keeps the old rule: the shift limit only warns)
			if stopped > 0 and h + stopped > 24:
				frappe.throw(
					_("Day {0}: operating hours ({1}) and stopped hours ({2}) exceed 24 hours.").format(
						key, h, stopped
					)
				)
			day_stopped_billed = stopped if stopped > 0 and cint(row.reason_billable) else 0.0
			billed_day = h + day_stopped_billed
			if billed_day > max_hours:
				# Shift limit is advisory only: every recorded hour is billed, so a day
				# over the limit is flagged for review, never blocked (owner 2026-10-14).
				# FR-118: billable stopped hours count, as they are billed too.
				over_shift_limit.append(key + " (" + str(billed_day) + ")")
			if h > 0:
				total_hours = total_hours + h
				work_days = work_days + 1
				hours_by_date[key] = h
			billable_stopped = billable_stopped + day_stopped_billed
			if day_stopped_billed > 0:
				side = reason_sides.get(row.stop_reason, SIDE_BOTH)
				for billed_side in stopped_for:
					if side in (SIDE_BOTH, billed_side):
						stopped_for[billed_side] = stopped_for[billed_side] + day_stopped_billed
						if h <= 0:
							stop_days_for[billed_side] = stop_days_for[billed_side] + 1
			if day_stopped_billed > 0 and h <= 0:
				# a day billed only by billable stopped hours (not already a working day)
				billable_stop_days = billable_stop_days + 1

		# ---- shift limit (advisory warning, never blocks; every recorded hour is billed) ----
		if over_shift_limit:
			frappe.msgprint(
				_(
					"Days over the {0}-hour shift limit for shift {1} (recorded and billed — review): {2}"
				).format(max_hours, _(self.shift), _(", ", context="Card").join(over_shift_limit)),
				title=_("Shift hours exceeded warning"),
				indicator="orange",
			)

		# ---- supplier-side amount (only directions that bill a supplier; F.5 bases) ----
		self.rate_type = eq.rate_type
		self.rate = flt(eq.rate)
		self.total_working_hours = total_hours
		self.total_loads = loads_total
		self.working_days = work_days
		# FR-118: only stopped hours of an explicitly billable reason are billed; with no
		# billable reason this is 0 and every amount is what it was before
		self.billable_stopped_hours = flt(billable_stopped, 2)
		self.billable_stopped_days = billable_stop_days
		# FR-134: each side bills its own billable stopped hours (Both reasons: the same as before)
		self.supplier_billable_stopped_hours = flt(stopped_for["Supplier"], 2)
		self.customer_billable_stopped_hours = flt(stopped_for["Customer"], 2)
		supplier_billed_hours = total_hours + flt(stopped_for["Supplier"], 2)
		customer_billed_hours = total_hours + flt(stopped_for["Customer"], 2)
		# FR-138: a "Full day" basis bills each billed day at the per-day rate (operating days and
		# days billed only by billable stopped hours of that side); otherwise billed hours x hourly rate
		supplier_billed_days = work_days + stop_days_for["Supplier"]
		customer_billed_days = work_days + stop_days_for["Customer"]
		if self.card_direction in SUPPLIER_BILLING_DIRECTIONS:
			if bills_full_days(eq.rate_type, self.day_billing_basis):
				self.amount = flt(supplier_billed_days * flt(eq.rate), 2)
			else:
				hourly_rate = self._hourly_for(eq.rate_type, flt(eq.rate), eq.daily_hours, required=True)
				self.amount = flt(supplier_billed_hours * hourly_rate, 2)
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
		# FR-134: the sides each stop reason is billed on through the days (a Both reason: both)
		billed_on = {}
		for row in self.days or []:
			if row.stop_reason and cint(row.reason_billable) and flt(row.stopped_hours) > 0:
				side = reason_sides.get(row.stop_reason, SIDE_BOTH)
				billed_on.setdefault(row.stop_reason, set()).update(
					("Supplier", "Customer") if side == SIDE_BOTH else (side,)
				)
		double_charged = []
		for adj in self.adjustments or []:
			typ = None
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
			# FR-134 (#45, C-07): a downtime charge names its stop reason, party and agreement
			is_downtime_charge = bool(typ and cint(typ.get("is_downtime_charge")))
			validate_downtime_fields(adj, self.company or eq.company, is_downtime_charge)
			if not adj.side:
				if self.card_direction == DIR_SUBRENTAL:
					frappe.throw(
						_(
							"Sub-rental cards bill both parties; choose the side (Supplier/Customer) for the addition/deduction {0}."
						).format(adj.description or adj.adjustment_type_ref or "")
					)
				adj.side = default_side
			if adj.side not in sided:
				frappe.throw(
					_("Invalid side {0} on addition/deduction {1}; it must be Supplier or Customer.").format(
						adj.side, adj.description or adj.adjustment_type_ref or ""
					)
				)
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
			if is_downtime_charge and adj.side in billed_on.get(adj.stop_reason, ()):
				# the same downtime billed on the same side by the reason and by this charge
				double_charged.append(adj.description or adj.adjustment_type_ref or "")
		if double_charged:
			frappe.msgprint(
				_(
					"These downtime charges name a stop reason that is also billable on the card's days, so the same downtime may be charged twice (review): {0}"
				).format(_(", ", context="Card").join(double_charged)),
				title=_("Downtime charge"),
				indicator="orange",
			)
		self.total_additions = flt(total_additions, 2)
		self.total_deductions = flt(total_deductions, 2)
		# Supplier net: rental amount + supplier-side rows only (legacy rows are
		# all Supplier after the backfill, so stored baselines are unchanged).
		self.net_amount = flt(flt(self.amount) + sided["Supplier"], 2)

		# ---- customer-side amount (rate mirrored from the equipment; the SI itself is S3) ----
		self.total_volume_m3 = 0
		if self.card_direction in CUSTOMER_BILLING_DIRECTIONS:
			if self.customer_rate_type == PER_VOLUME_M3:
				# FR-166: loads x load volume (m³) x rate per m³ before VAT; hours and billable stops add nothing
				self.total_volume_m3 = flt(loads_total * flt(eq.load_volume_m3), 3)
				self.customer_amount = flt(self.total_volume_m3 * flt(self.customer_rate), 2)
			elif bills_full_days(self.customer_rate_type, self.day_billing_basis):
				self.customer_amount = flt(customer_billed_days * flt(self.customer_rate), 2)
			else:
				customer_hourly = self._hourly_for(
					self.customer_rate_type, flt(self.customer_rate), eq.daily_hours, required=False
				)
				self.customer_amount = flt(customer_billed_hours * customer_hourly, 2)
		else:
			self.customer_amount = 0
		self.customer_net_amount = (
			flt(flt(self.customer_amount) + sided["Customer"], 2)
			if flt(self.customer_amount) or sided["Customer"]
			else 0
		)

		# ---- duplicate card: same equipment + month + year + shift + project ----
		# (v3.0.0: a machine moved during the month has one card per project; the
		# assignment periods keep their days apart)
		dup = frappe.get_all(
			"Card Monthly Card",
			filters={
				"equipment": self.equipment,
				"month": self.month,
				"year": self.year,
				"shift": self.shift,
				"project": self.project,
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
						_("Days exceeding shift hours ({0} hours): {1}").format(
							shift_hours, _(", ", context="Card").join(over)
						),
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
						).format(_(", ", context="Card").join(outside)),
						title=_("Review rental period"),
						indicator="orange",
					)

	def _resolve_stop_reasons(self, company, direction=None):
		"""FR-118 (#45): a day row's stop reason must be an enabled reason of the card's
		company; the row keeps whether it was billable (a snapshot, so a submitted card never
		follows a later change of the reason). A row without a reason is never billable, so
		a card without reasons bills exactly as before. The responsible party is normalised:
		a record for Company/Supplier/Customer, a free-text name for Other.

		FR-134: a billable reason bills only its billable side. ``reason_billable`` is set
		when the reason bills on at least one side this card bills (Both: as before; a
		Supplier or Customer reason on a card that does not bill that side is not billable)."""
		names = list({row.stop_reason for row in self.days or [] if row.stop_reason})
		reasons = {}
		if names:
			reasons = {
				r.name: r
				for r in frappe.get_all(
					"Card Stop Reason",
					filters={"name": ["in", names]},
					fields=[
						"name",
						"company",
						"enabled",
						"billable",
						"billable_side",
						"default_responsible_party_type",
					],
				)
			}
		billed_sides = set()
		if direction in SUPPLIER_BILLING_DIRECTIONS:
			billed_sides.add("Supplier")
		if direction in CUSTOMER_BILLING_DIRECTIONS:
			billed_sides.add("Customer")
		self._reason_sides = {name: billable_side_of(r) for name, r in reasons.items()}
		one_sided = set()
		for row in self.days or []:
			if not row.stop_reason:
				row.reason_billable = 0
			else:
				reason = reasons.get(row.stop_reason)
				if not reason:
					frappe.throw(_("Stop reason {0} does not exist.").format(row.stop_reason))
				if reason.company != company:
					frappe.throw(
						_(
							"Stop reason {0} belongs to another company; choose a reason of company {1}."
						).format(row.stop_reason, company),
						frappe.PermissionError,
					)
				if not cint(reason.enabled):
					frappe.throw(
						_("Stop reason {0} is disabled; choose an enabled reason (day {1}).").format(
							row.stop_reason, row.operation_date
						)
					)
				side = billable_side_of(reason)
				row.reason_billable = (
					cint(reason.billable) if side == SIDE_BOTH or side in billed_sides else 0
				)
				if row.reason_billable and side != SIDE_BOTH and len(billed_sides) > 1:
					one_sided.add((row.stop_reason, side))
				if not row.responsible_party_type and reason.default_responsible_party_type:
					row.responsible_party_type = reason.default_responsible_party_type
			self._normalise_responsible_party(row, company)
		if one_sided:
			# a sub-rental card bills both sides; its billable stopped hours (statements,
			# summaries) count the reason, but only the named side's amount includes it
			frappe.msgprint(
				_(
					"These billable stop reasons bill one side only; the other side's amount does not include their stopped hours (review): {0}"
				).format(
					_(", ", context="Card").join(
						"{0} ({1})".format(name, _(side)) for name, side in sorted(one_sided)
					)
				),
				title=_("Billable side"),
				indicator="orange",
			)

	@staticmethod
	def _normalise_responsible_party(row, company):
		party_type = row.responsible_party_type
		if not party_type:
			row.responsible_party = None
			row.responsible_party_name = None
			return
		if party_type == "Other":
			row.responsible_party = None
			return
		row.responsible_party_name = None
		if party_type == "Company":
			if not row.responsible_party:
				row.responsible_party = company
			elif row.responsible_party != company:
				frappe.throw(
					_("The responsible company on day {0} must be the card's company {1}.").format(
						row.operation_date, company
					)
				)

	def _warn_foreign_responsible_party(self):
		"""FR-118 (review L2): a supplier or customer held responsible for a stopped day that is
		not the card's own supplier or customer is flagged for review, never blocked."""
		own = {"Supplier": self.supplier, "Customer": self.customer}
		foreign = []
		for row in self.days or []:
			party_type = row.responsible_party_type
			if party_type in own and row.responsible_party and row.responsible_party != own[party_type]:
				foreign.append(
					"{0} ({1}: {2})".format(row.operation_date, _(party_type), row.responsible_party)
				)
		if foreign:
			frappe.msgprint(
				_(
					"The responsible party of these stopped days is not the card's own supplier or customer (review): {0}"
				).format(_(", ", context="Card").join(foreign)),
				title=_("Responsible party"),
				indicator="orange",
			)

	def _refuse_unit_component_days(self, eq):
		"""WP-05 (#42): a piece is billed on its unit's card while it is in the unit, so its
		own card may not record working hours on a day inside a component period of any unit (the dated
		rows of the units' component tables). A flag ticked before the flag was derived,
		on equipment no unit lists, still refuses the whole card: nothing says when the
		piece was in a unit (get_unit_integrity_issues lists those)."""
		from card.card.doctype.card_equipment.card_equipment import component_periods

		periods = component_periods(self.equipment)
		if not periods:
			if eq.is_unit_component:
				frappe.throw(
					_(
						"This equipment is a unit component; the monthly card is kept on the unit, not the component."
					)
				)
			return
		for d in self.days:
			# like validate_card_days: only a day with hours is billed; the form adds a 0-hour
			# row for every day of the month the machine was on the project
			if not d.operation_date or not is_billed_day(d):
				continue
			day = getdate(d.operation_date)
			unit = next((p.unit for p in periods if _in_unit_on(p, day)), None)
			if unit:
				frappe.throw(
					_(
						"On {0} equipment {1} is a component of unit {2}; that day belongs on the unit's card, not the component's."
					).format(frappe.format(day, "Date"), self.equipment, unit),
					title=_("Unit component"),
				)

	def _resolve_project(self, first_day, last_day):
		"""The user picks the equipment, month and shift; the project is the one the
		equipment's approved transports put it on that month (Card Equipment Assignment).
		One project: set. Several (moved during the month): one card per project, and a
		project outside them is refused even through the API. None: the card is refused
		until an Equipment Transport records the move. A machine that stays a year on a
		project keeps an open assignment, so every month (day and night shift) has its card."""
		projects = assignment_projects(self.equipment, first_day, last_day)
		if not projects:
			if frappe.flags.in_test and not frappe.flags.card_require_assignment:
				return  # older suites build cards without transports; v3 tests turn this on
			frappe.throw(
				_(
					"Equipment {0} has no approved transport to a project in {1}/{2}. Record an Equipment Transport first."
				).format(self.equipment, self.month, self.year),
				title=_("No transport"),
			)
		if self.project and self.project not in projects:
			frappe.throw(
				_("In {0}/{1} equipment {2} was on {3}, not on project {4}.").format(
					self.month, self.year, self.equipment, ", ".join(projects), self.project
				)
			)
		if not self.project:
			if len(projects) > 1:
				frappe.throw(
					_(
						"In {0}/{1} equipment {2} moved between {3}. Choose the project: one card per project."
					).format(self.month, self.year, self.equipment, ", ".join(projects))
				)
			self.project = projects[0]

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

	def on_update(self):
		# report filters link to the party registries; a party must be selectable
		# from its first card, draft included (submit/cancel keep the totals)
		if (
			self.supplier
			and self.ownership != "ملك"
			and not frappe.db.exists("Card Equipment Supplier", self.supplier)
		):
			self._sync_supplier()
		if (
			self.customer
			and self.card_direction in CUSTOMER_BILLING_DIRECTIONS
			and not frappe.db.exists("Card Equipment Customer", self.customer)
		):
			self._sync_customer()

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
		# FR-166: a per-m³ customer card stores its rate per m³ (SAR) as customer_rate_used, not an hourly rate;
		# customer_rate_type tells the two apart
		per_volume = self.customer_rate_type == PER_VOLUME_M3
		self.db_set("daily_hours_used", daily_hours, update_modified=False)
		self.db_set("hourly_rate_used", hourly, update_modified=False)
		self.db_set("diesel_policy_used", eq.get("الوقود_على"), update_modified=False)
		# customer-side snapshot (phase E): the hourly rate the customer amount used
		self.db_set(
			"customer_rate_used",
			flt(self.customer_rate)
			if per_volume
			else self._hourly_for(
				self.customer_rate_type, flt(self.customer_rate), daily_hours, required=False
			),
			update_modified=False,
		)
		self.db_set(
			"load_volume_used",
			flt(frappe.db.get_value("Card Equipment", self.equipment, "load_volume_m3")) if per_volume else 0,
			update_modified=False,
		)
		# F.7 snapshot: direction, customer and the supplier rate basis used at submit
		self.db_set("direction_used", self.card_direction, update_modified=False)
		self.db_set("customer_used", self.customer, update_modified=False)
		self.db_set("rate_basis_used", self.rate_type, update_modified=False)
		# FR-138: the day billing basis this card was priced with (set by the submit save's mirror)
		self.db_set(
			"day_billing_basis_used", day_billing_basis(self.day_billing_basis), update_modified=False
		)

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


# P0 company isolation D2 (Owner 2026-10-20): Frappe checks create/write permission on
# the values the client sends (frappe/model/document.py: insert, _save) and only then
# fetches `company` from the equipment, so an empty company passed the Company User
# Permission. The card's company is its equipment's company.


def has_card_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level check for every path (read, create, REST/Desk save, set_value,
	submit, cancel): the company sent, the company stored for a saved card AND the
	company of a new or changed equipment must all be permitted, so a card can be
	neither created in, moved to, nor taken over from another company. Scope = the
	Company User Permissions that apply to cards, as the card list uses. A saved card's
	unchanged equipment is not re-read, so a read costs one query.
	A controller can only deny (Frappe 16 treats a falsy return as a denial)."""
	from card.party_registry import _restricted_companies

	companies = _restricted_companies(user or frappe.session.user, "Card Monthly Card")
	if companies is None:
		return True
	owners = {doc.get("company")}
	stored = None
	if not doc.is_new():
		stored = frappe.db.get_value(doc.doctype, doc.name, ["company", "equipment"], as_dict=True)
		if stored:
			owners.add(stored.company)
	equipment = doc.get("equipment")
	if equipment and (not stored or equipment != stored.equipment):
		owners.add(frappe.db.get_value("Card Equipment", equipment, "company"))
	owners.discard(None)
	owners.discard("")
	return all(company in companies for company in owners)
