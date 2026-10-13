# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe.model.document import Document
from frappe.query_builder.functions import Sum, UnixTimestamp
from frappe.utils import flt


class CardEquipment(Document):
	def validate(self):
		# Ported from Server Script "Card Equipment - Hourly Rate" (Before Validate).
		# Computes the read-only approved_hourly_rate shown on the equipment.
		rate = flt(self.rate)
		if self.rate_type == "باليوم":
			if flt(self.daily_hours) <= 0:
				frappe.throw("حدد ساعات العمل اليومية (الدوام) لحساب سعر الساعة")
			self.approved_hourly_rate = flt(rate / flt(self.daily_hours), 2)
		elif self.rate_type == "بالساعة":
			self.approved_hourly_rate = rate
		else:
			self.approved_hourly_rate = 0


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
