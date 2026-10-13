# Copyright (c) 2026, Ahmed Shehab and contributors
# For license information, please see LICENSE

import frappe
from frappe.model.document import Document
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
