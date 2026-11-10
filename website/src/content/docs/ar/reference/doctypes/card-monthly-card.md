---
title: "كارت التشغيل الشهري"
description: "حقول نوع المستند كارت التشغيل الشهري وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "كارت التشغيل الشهري"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Monthly Card**

| | |
|---|---|
| النوع | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-monthly-card` |


## الحقول


**بيانات الكارت**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المعدات | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) | نعم |
| المشروع | `project` | Link | المشروع | نعم |
| الشركة <small>(للقراءة فقط)</small> | `company` | Link | الشركة | نعم |
| اسم المشروع <small>(مخفي, للقراءة فقط)</small> | `project_name` | Data |  |  |
| الموقع | `site_location` | Data |  |  |
| السائق / المشغّل | `operator_name` | Data |  |  |
| نوع الوردية | `shift` | Select | نهاري · ليلي | نعم |
| الشهر | `month` | Select | 01 · 02 · 03 · 04 · 05 · 06 · 07 · 08 · 09 · 10 · 11 · 12 | نعم |
| السنة | `year` | Int |  | نعم |
| الصورة <small>(مخفي)</small> | `image` | Attach Image |  |  |
| اسم المعدة <small>(للقراءة فقط)</small> | `equipment_name` | Data |  |  |
| الملكية <small>(للقراءة فقط)</small> | `ownership` | Data |  |  |
| المالك <small>(للقراءة فقط)</small> | `supplier` | Link | المورد |  |
| من تاريخ <small>(للقراءة فقط)</small> | `from_date` | Date |  |  |
| إلى تاريخ <small>(للقراءة فقط)</small> | `to_date` | Date |  |  |


**أيام الشهر**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الأيام | `days` | Table | [يوم الكارت الشهري](/card/ar/reference/doctypes/card-monthly-card-day/) | نعم |


**الإجماليات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| طريقة الحساب <small>(للقراءة فقط)</small> | `rate_type` | Data |  |  |
| السعر <small>(للقراءة فقط)</small> | `rate` | Currency |  |  |
| أيام العمل <small>(للقراءة فقط)</small> | `working_days` | Int |  |  |
| إجمالي ساعات التشغيل <small>(للقراءة فقط)</small> | `total_working_hours` | Float |  |  |
| ساعات التوقف المحتسبة إيجارًا <small>(للقراءة فقط)</small> | `billable_stopped_hours` | Float |  |  |
| أيام التوقف المحتسبة إيجارًا <small>(للقراءة فقط)</small> | `billable_stopped_days` | Int |  |  |
| ساعات التوقف المحتسبة على المورد <small>(للقراءة فقط)</small> | `supplier_billable_stopped_hours` | Float |  |  |
| ساعات التوقف المحتسبة على العميل <small>(للقراءة فقط)</small> | `customer_billable_stopped_hours` | Float |  |  |
| القيمة الإجمالية <small>(للقراءة فقط)</small> | `amount` | Currency |  |  |
| معدّل من <small>(للقراءة فقط)</small> | `amended_from` | Link | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) |  |
| سبب الإلغاء <small>(للقراءة فقط)</small> | `cancel_reason` | Small Text |  |  |


**إضافات وخصومات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| إضافات وخصومات | `adjustments` | Table | [إضافة أو خصم الكارت الشهري](/card/ar/reference/doctypes/card-monthly-card-adjustment/) |  |
| إجمالي الإضافات <small>(للقراءة فقط)</small> | `total_additions` | Currency |  |  |
| إجمالي الخصومات <small>(للقراءة فقط)</small> | `total_deductions` | Currency |  |  |
| الصافي المستحق <small>(للقراءة فقط)</small> | `net_amount` | Currency |  |  |


**اعتماد الكارت الشهري**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مقدِّم الكارت الشهري للاعتماد (Submit) <small>(للقراءة فقط)</small> | `submitted_by` | Link | المستخدم |  |
| معتمد الكارت الشهري <small>(للقراءة فقط)</small> | `approved_by` | Link | المستخدم |  |
| تاريخ اعتماد الكارت الشهري <small>(للقراءة فقط)</small> | `approved_on` | Datetime |  |  |
| اعتمده معدّه <small>(للقراءة فقط)</small> | `self_approved` | Check |  |  |
| معدّلو الكارت الشهري <small>(مخفي, للقراءة فقط)</small> | `edited_by` | Small Text |  |  |


**المحاسبة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الترحيل المحاسبي <small>(للقراءة فقط)</small> | `gl_posting` | Link | [سجل الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-log/) |  |
| مرحَّل <small>(للقراءة فقط)</small> | `posted` | Check |  |  |
| فاتورة الشراء <small>(للقراءة فقط)</small> | `purchase_invoice` | Link | فاتورة الشراء |  |
| الساعات اليومية (المستخدمة) <small>(للقراءة فقط)</small> | `daily_hours_used` | Float |  |  |
| سعر الساعة (المستخدم) <small>(للقراءة فقط)</small> | `hourly_rate_used` | Currency |  |  |
| الوقود على (المستخدم) <small>(للقراءة فقط)</small> | `diesel_policy_used` | Data |  |  |
| اتجاه الكارت <small>(للقراءة فقط)</small> | `card_direction` | Select | مستأجَرة من مورد · مؤجَّرة لعميل · إيجار من الباطن · تشغيل داخلي |  |
| العميل <small>(للقراءة فقط)</small> | `customer` | Link | العميل |  |
| نوع سعر العميل <small>(للقراءة فقط)</small> | `customer_rate_type` | Select | باليوم · بالساعة · بالشهر |  |
| سعر العميل <small>(للقراءة فقط)</small> | `customer_rate` | Currency |  |  |
| أساس احتساب اليوم <small>(للقراءة فقط)</small> | `day_billing_basis` | Select | تناسبي حسب الساعات · يوم كامل |  |
| مبلغ العميل <small>(للقراءة فقط)</small> | `customer_amount` | Currency |  |  |
| سعر الساعة للعميل المستخدم <small>(للقراءة فقط)</small> | `customer_rate_used` | Currency |  |  |
| الاتجاه المستخدم <small>(للقراءة فقط)</small> | `direction_used` | Data |  |  |
| العميل المستخدم <small>(للقراءة فقط)</small> | `customer_used` | Data |  |  |
| أساس السعر المستخدم <small>(للقراءة فقط)</small> | `rate_basis_used` | Data |  |  |
| أساس احتساب اليوم المستخدم <small>(للقراءة فقط)</small> | `day_billing_basis_used` | Select | تناسبي حسب الساعات · يوم كامل |  |


**بيانات المعدة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| صافي جانب العميل <small>(للقراءة فقط)</small> | `customer_net_amount` | Currency |  |  |
| فاتورة المبيعات <small>(للقراءة فقط)</small> | `sales_invoice` | Link | فاتورة المبيعات |  |
| المشغّل على <small>(مخفي, للقراءة فقط)</small> | `operator_on` | Data |  |  |
| المشغّل | `operator` | Link | الموظف |  |


## الجداول الفرعية

- [يوم الكارت الشهري](/card/ar/reference/doctypes/card-monthly-card-day/)
- [إضافة أو خصم الكارت الشهري](/card/ar/reference/doctypes/card-monthly-card-adjustment/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مستخدم الكروت | قراءة, كتابة, إنشاء, تقرير, طباعة, بريد |
| مدير الحسابات | قراءة, تقرير, تصدير, طباعة |
