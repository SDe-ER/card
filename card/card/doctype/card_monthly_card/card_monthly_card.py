# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, get_last_day, getdate, nowdate

from card.api import recompute_supplier


class CardMonthlyCard(Document):
	def before_validate(self):
		# Ported verbatim-in-behaviour from Server Script "Card Monthly Card - Validate" v4 (Before Validate).
		doc_month = cint(self.month)
		doc_year = cint(self.year)
		if not doc_month or not doc_year:
			frappe.throw(_("Month and year are required"))

		eq = frappe.db.get_value(
			"Card Equipment",
			self.equipment,
			[
				"company",
				"ownership",
				"rate_type",
				"rate",
				"daily_hours",
				"rental_start_date",
				"rental_end_date",
			],
			as_dict=True,
		)
		if not eq:
			frappe.throw(_("Equipment not found: {0}").format(self.equipment))
		if self.company and self.company != eq.company:
			frappe.throw(_("The card's company does not match the equipment's company"))

		# ---- period of the card ----
		first_day = getdate(str(doc_year) + "-" + str(doc_month).zfill(2) + "-01")
		last_day = get_last_day(first_day)
		self.from_date = first_day
		self.to_date = last_day
		today = getdate(nowdate())

		# ---- day rows ----
		seen = {}
		hours_by_date = {}
		total_hours = 0.0
		work_days = 0
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
			if h > 24:
				frappe.throw(_("Number of hours on day {0} exceeds 24 hours").format(key))
			if h > 0 and d > today:
				frappe.throw(_("Cannot record operating hours for a future day: {0}").format(key))
			if h > 0:
				total_hours = total_hours + h
				work_days = work_days + 1
				hours_by_date[key] = h

		# ---- hourly rate ----
		rate = flt(eq.rate)
		if eq.rate_type == "باليوم":
			daily_hours = flt(eq.daily_hours)
			if daily_hours <= 0:
				frappe.throw(_("Set the daily working hours for equipment {0}").format(self.equipment))
			hourly_rate = rate / daily_hours
		elif eq.rate_type == "بالساعة":
			hourly_rate = rate
		else:
			frappe.throw(_("Equipment rate type is not defined: {0}").format(self.equipment))

		self.rate_type = eq.rate_type
		self.rate = rate
		self.total_working_hours = total_hours
		self.working_days = work_days
		if eq.ownership == "ملك":
			self.amount = 0  # owned equipment: no supplier billing
		else:
			self.amount = flt(total_hours * hourly_rate, 2)

		# ---- additions / deductions (v4) ----
		total_additions = 0.0
		total_deductions = 0.0
		for adj in self.adjustments or []:
			a = flt(adj.amount)
			if a <= 0:
				frappe.throw(_("The addition/deduction amount must be greater than zero: {0}").format(adj.description or ""))
			if adj.adjustment_type == "إضافة":
				total_additions = total_additions + a
			elif adj.adjustment_type == "خصم":
				total_deductions = total_deductions + a
			else:
				frappe.throw(_("Unknown type in additions and deductions: {0}").format(adj.adjustment_type))
		self.total_additions = flt(total_additions, 2)
		self.total_deductions = flt(total_deductions, 2)
		self.net_amount = flt(flt(self.amount) + total_additions - total_deductions, 2)

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
			frappe.throw(_("A {0} card already exists for the same equipment and month: {1}").format(self.shift, dup[0]))

		# ---- shift length warning (per card, per day; each shift card stands alone) ----
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
				_("Shift hours are not set for equipment {0}; the shift-hours-exceeded warning will not appear.").format(self.equipment),
				title=_("Shift hours"),
				indicator="orange",
			)

		# ---- rental period (flag for review, hours still counted) ----
		if eq.ownership != "ملك" and hours_by_date:
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
						_("Days with operation outside the rental period (calculated, needs review): {0}").format("، ".join(outside)),
						title=_("Review rental period"),
						indicator="orange",
					)

	def on_submit(self):
		self._sync_supplier()

	def on_cancel(self):
		self._sync_supplier()

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
					_("Could not update the supplier record {0}. The card was saved normally; use the \"Refresh numbers\" button in the supplier record.").format(self.supplier),
					title=_("Supplier record"),
					indicator="orange",
				)
