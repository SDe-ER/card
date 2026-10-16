# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Sum, UnixTimestamp
from frappe.utils import flt

from card.constants import (
	CUSTOMER_BILLING_DIRECTIONS,
	SUPPLIER_BILLING_DIRECTIONS,
	allowed_directions,
	derive_direction,
)
from card.dimension import sync_asset_dimension
from card.settings import setting

# Commercial terms: permlevel 1 (Card Manager writes, Card User reads) and every
# change needs a reason, recorded with the change in the document history.
COMMERCIAL_FIELDS = (
	"ownership",
	"supplier",
	"rental_start_date",
	"rental_end_date",
	"contract_no",
	"rate_type",
	"rate",
	"daily_hours",
	"الوقود_على",
	"internal_hourly_rate",
	"customer_rate_type",
	"customer_rate",
	"default_customer",
	"rental_direction",
	"operator_on",
)


class CardEquipment(Document):
	def on_update(self):
		# O3: the linked Asset carries the equipment as its accounting dimension,
		# so depreciation entries land on the equipment in GL. No-op without the dimension.
		sync_asset_dimension(self)

	def validate(self):
		self.apply_new_record_defaults()
		self.validate_rental_direction()
		self.validate_commercial_change_reason()
		self.validate_unique_asset()
		# Ported from Server Script "Card Equipment - Hourly Rate" (Before Validate).
		# Computes the read-only approved_hourly_rate shown on the equipment.
		rate = flt(self.rate)
		if self.rate_type == "باليوم":
			if flt(self.daily_hours) <= 0:
				frappe.throw(_("Set the daily working hours (shift) to calculate the hourly rate"))
			self.approved_hourly_rate = flt(rate / flt(self.daily_hours), 2)
		elif self.rate_type == "بالساعة":
			self.approved_hourly_rate = rate
		elif self.rate_type == "بالشهر":
			# F.5: monthly basis spreads the rate over the standard month hours
			month_hours = flt(setting("standard_month_hours")) or 260
			self.approved_hourly_rate = flt(rate / month_hours, 2)
		else:
			self.approved_hourly_rate = 0

	def validate_commercial_change_reason(self):
		"""A change to a commercial term of an existing equipment needs a NEW
		reason (enforced server-side, so REST and imports are covered too).
		Migrations and installs are exempt."""
		if self.is_new() or frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		before = self.get_doc_before_save()
		if not before:
			return
		changed = [f for f in COMMERCIAL_FIELDS if _differs(before.get(f), self.get(f))]
		if not changed:
			return
		reason = (self.commercial_change_reason or "").strip()
		if not reason or reason == (before.commercial_change_reason or "").strip():
			labels = ", ".join(_(self.meta.get_label(f)) for f in changed)
			frappe.throw(
				_("Enter the reason for changing the commercial terms: {0}").format(labels),
				title=_("Reason required"),
			)

	def validate_rental_direction(self):
		"""F.7: rental_direction is the single source of truth. A blank one is
		derived from ownership (legacy rows keep working); a chosen one must
		match the ownership; the mandatory party/rate of each direction is
		enforced server-side (depends_on in the form is client-side only)."""
		if not self.rental_direction:
			self.rental_direction = derive_direction(self.ownership)
		if self.rental_direction not in allowed_directions(self.ownership):
			frappe.throw(
				_("Direction {0} is not valid for ownership {1}.").format(
					self.rental_direction, self.ownership
				)
			)
		if self.rental_direction in SUPPLIER_BILLING_DIRECTIONS:
			if not self.supplier:
				frappe.throw(_("Direction {0} requires a supplier.").format(self.rental_direction))
			if not self.rate_type or not flt(self.rate):
				frappe.throw(
					_("Direction {0} requires the supplier rate and its basis.").format(self.rental_direction)
				)
		if self.rental_direction in CUSTOMER_BILLING_DIRECTIONS:
			if not self.default_customer:
				frappe.throw(_("Direction {0} requires a customer.").format(self.rental_direction))
			if not self.customer_rate_type or not flt(self.customer_rate):
				frappe.throw(
					_("Direction {0} requires the customer rate and its basis.").format(self.rental_direction)
				)

	def validate_unique_asset(self):
		# One ERPNext Asset <-> at most one Card Equipment.
		asset = self.get("الأصل_في_erpnext")
		if not asset:
			return
		other = frappe.db.get_value(
			"Card Equipment",
			{"الأصل_في_erpnext": asset, "name": ["!=", self.name or ""]},
			"name",
		)
		if other:
			frappe.throw(_("Asset {0} is already linked to equipment {1}").format(asset, other))

	def apply_new_record_defaults(self):
		# Card Settings pre-fill for NEW equipment only; a provided value is never overridden.
		if not self.is_new():
			return
		default_hours = flt(setting("default_daily_hours"))
		if not flt(self.daily_hours) and default_hours > 0:
			self.daily_hours = default_hours
		fuel_on = setting("default_fuel_charged_to")
		if not self.get("الوقود_على") and fuel_on:
			self.set("الوقود_على", fuel_on)
		operator_on = setting("default_operator_on")
		if not self.operator_on and operator_on:
			self.operator_on = operator_on
		# F.5: default calculation basis for both sides (new records only)
		basis = setting("default_rate_basis")
		if basis:
			if not self.rate_type:
				self.rate_type = basis
			if not self.customer_rate_type:
				self.customer_rate_type = basis


def get_timeline_data(doctype: str, name: str) -> dict:
	"""Daily operating hours for the form-dashboard heatmap.

	Dispatched by frappe.desk.notifications.get_open_count via
	frappe.get_meta_module(doctype); mirrors hrms employee_master.get_timeline_data.
	Sums working_hours of submitted Card Monthly Card day rows per operation_date;
	dates with a zero total (stoppage days) are left out so their cells stay empty.
	"""
	frappe.has_permission(doctype, "read", name, throw=True)
	frappe.has_permission("Card Monthly Card", "read", throw=True)

	card = frappe.qb.DocType("Card Monthly Card")
	day = frappe.qb.DocType("Card Monthly Card Day")
	total_hours = Sum(day.working_hours)

	rows = (
		frappe.qb.from_(day)
		.join(card)
		.on(day.parent == card.name)
		.select(UnixTimestamp(day.operation_date), total_hours)
		.where((card.equipment == name) & (card.docstatus == 1))
		.groupby(day.operation_date)
		.having(total_hours > 0)
	).run()

	return {int(timestamp): flt(hours) for timestamp, hours in rows}


@frappe.whitelist()
def get_shift_heatmap(name: str):
	"""Per-shift daily operating hours, so two-shift equipment can show the day
	(نهاري) and night (ليلي) activity as two separate heatmaps with distinct
	palettes. Mirrors get_timeline_data but also groups by the card's shift.
	Returns {"day": {ts: hours}, "night": {ts: hours}, "has_night": bool}.
	"""
	frappe.has_permission("Card Equipment", "read", name, throw=True)
	frappe.has_permission("Card Monthly Card", "read", throw=True)

	card = frappe.qb.DocType("Card Monthly Card")
	day = frappe.qb.DocType("Card Monthly Card Day")
	total_hours = Sum(day.working_hours)

	rows = (
		frappe.qb.from_(day)
		.join(card)
		.on(day.parent == card.name)
		.select(UnixTimestamp(day.operation_date), card.shift, total_hours)
		.where((card.equipment == name) & (card.docstatus == 1))
		.groupby(day.operation_date, card.shift)
		.having(total_hours > 0)
	).run()

	day_map, night_map = {}, {}
	for timestamp, shift, hours in rows:
		(night_map if shift == "ليلي" else day_map)[int(timestamp)] = flt(hours)
	return {"day": day_map, "night": night_map, "has_night": bool(night_map)}


def _differs(old, new):
	"""Compare stored vs incoming values without false positives from type
	(1 vs 1.0, None vs "", date vs "YYYY-MM-DD")."""
	if (old in (None, "")) and (new in (None, "")):
		return False
	if isinstance(old, (int, float)) or isinstance(new, (int, float)):
		return flt(old) != flt(new)
	return str(old) != str(new)
