# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Sum, UnixTimestamp
from frappe.utils import flt

from card.settings import setting


class CardEquipment(Document):
	def validate(self):
		self.apply_new_record_defaults()
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
		else:
			self.approved_hourly_rate = 0

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
def get_shift_heatmap(name):
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
