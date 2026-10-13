# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, get_last_day, getdate, nowdate

from card.api import recompute_supplier


class CardMonthlyCard(Document):
	def before_validate(self):
		# Ported verbatim-in-behaviour from Server Script "Card Monthly Card - Validate" v4 (Before Validate).
		doc_month = cint(self.month)
		doc_year = cint(self.year)
		if not doc_month or not doc_year:
			frappe.throw("الشهر والسنة مطلوبين")

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
			frappe.throw("المعدة غير موجودة: " + str(self.equipment))
		if self.company and self.company != eq.company:
			frappe.throw("شركة الكارت لا تطابق شركة المعدة")

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
				frappe.throw("يوجد صف أيام بدون تاريخ")
			d = getdate(row.operation_date)
			key = str(d)
			if d < first_day or d > last_day:
				frappe.throw("التاريخ " + key + " خارج شهر الكارت")
			if key in seen:
				frappe.throw("التاريخ " + key + " مكرر في الكارت")
			seen[key] = 1
			if row.day_status != "عمل":
				row.working_hours = 0
			h = flt(row.working_hours)
			if h < 0:
				frappe.throw("ساعات بالسالب في يوم " + key)
			if h > 24:
				frappe.throw("عدد ساعات يوم " + key + " أكبر من 24 ساعة")
			if h > 0 and d > today:
				frappe.throw("لا يمكن تسجيل ساعات تشغيل ليوم لم يأت بعد: " + key)
			if h > 0:
				total_hours = total_hours + h
				work_days = work_days + 1
				hours_by_date[key] = h

		# ---- hourly rate ----
		rate = flt(eq.rate)
		if eq.rate_type == "باليوم":
			daily_hours = flt(eq.daily_hours)
			if daily_hours <= 0:
				frappe.throw("حدد ساعات العمل اليومية للمعدة " + str(self.equipment))
			hourly_rate = rate / daily_hours
		elif eq.rate_type == "بالساعة":
			hourly_rate = rate
		else:
			frappe.throw("طريقة حساب المعدة غير محددة: " + str(self.equipment))

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
				frappe.throw("مبلغ الإضافة/الخصم لازم يكون أكبر من صفر: " + str(adj.description or ""))
			if adj.adjustment_type == "إضافة":
				total_additions = total_additions + a
			elif adj.adjustment_type == "خصم":
				total_deductions = total_deductions + a
			else:
				frappe.throw("نوع غير معروف في الإضافات والخصومات: " + str(adj.adjustment_type))
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
			frappe.throw("يوجد كارت " + str(self.shift) + " لنفس المعدة ونفس الشهر: " + dup[0])

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
					"أيام تخطت ساعات الدوام (" + str(shift_hours) + " ساعة): " + "، ".join(over),
					title="تحذير تخطي الدوام",
					indicator="orange",
				)
		else:
			frappe.msgprint(
				"لم يتم تحديد ساعات الدوام للمعدة " + str(self.equipment) + "، لن يظهر تحذير تخطي الدوام.",
				title="ساعات الدوام",
				indicator="orange",
			)

		# ---- rental period (flag for review, hours still counted) ----
		if eq.ownership != "ملك" and hours_by_date:
			if not eq.rental_start_date:
				frappe.msgprint(
					"المعدة ليس لها تاريخ بداية إيجار. راجع بيانات الإيجار.",
					title="مراجعة فترة الإيجار",
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
						"أيام فيها تشغيل خارج فترة الإيجار (محسوبة، تحتاج مراجعة): " + "، ".join(outside),
						title="مراجعة فترة الإيجار",
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
					"تعذّر تحديث سجل المورد "
					+ str(self.supplier)
					+ ". الكارت اتحفظ عادي؛ استخدم زرار «تحديث الأرقام» في سجل المورد.",
					title="سجل المورد",
					indicator="orange",
				)
