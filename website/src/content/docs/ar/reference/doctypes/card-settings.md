---
title: "الإعدادات"
description: "حقول نوع المستند الإعدادات وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "الإعدادات"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Settings**

| | |
|---|---|
| النوع | مفرد (سجل إعدادات واحد) |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-settings` |


## الحقول


### المحاسبة


**السياسة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| تفعيل الترحيل المحاسبي | `enable_accounting` | Check |  |  |
| ترحيل تلقائي <small>(مخفي, للقراءة فقط)</small> | `auto_submit` | Check |  |  |


**إعدادات الشركات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| إعدادات الشركة | `company_settings` | Table | [إعدادات كارت للشركة](/card/ar/reference/doctypes/card-company-settings/) |  |


### التشغيل


**الافتراضيات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الوردية الافتراضية | `default_shift` | Select | نهاري · ليلي |  |
| أقصى ساعات الوردية النهارية | `max_day_shift_hours` | Float |  |  |
| أقصى ساعات الوردية الليلية | `max_night_shift_hours` | Float |  |  |
| الساعات اليومية الافتراضية (للمعدات الجديدة فقط) | `default_daily_hours` | Float |  |  |
| الوقود على حساب (افتراضي للمعدات الجديدة) | `default_fuel_charged_to` | Select | المؤجر · الشركة |  |
| المشغّل على حساب (افتراضي للمعدات الجديدة) | `default_operator_on` | Select | المؤجر · الشركة |  |
| سماحية المطابقة | `reconciliation_tolerance` | Currency |  |  |


**التحذيرات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| تنبيه عند تجاوز ساعات اليوم للساعات اليومية | `warn_on_shift_hours_exceeded` | Check |  |  |
| تنبيه عند وقوع تواريخ الكارت خارج فترة الإيجار | `warn_outside_rental_period` | Check |  |  |


**افتراضيات التقارير**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| نوع كشف الحساب الافتراضي | `default_statement_type` | Select | مورد · معدات ملك |  |
| تضمين الكروت المسودة في التقارير | `include_draft_in_reports` | Check |  |  |


### قفل الفترة


**قفل الفترة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| تاريخ قفل الفترة | `period_lock_date` | Date |  |  |
| دور تجاوز قفل الفترة | `period_lock_override_role` | Link | الدور |  |


### الإشعارات


**الإشعارات (كلها متوقفة افتراضيًا)**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| إشعار عند اعتماد الكارت | `notify_on_card_submit` | Check |  |  |
| إشعار عند الترحيل المحاسبي <small>(مخفي, للقراءة فقط)</small> | `notify_on_posting` | Check |  |  |
| إشعار عند تجاوز قفل الفترة | `notify_on_period_lock_override` | Check |  |  |
| أساس السعر الافتراضي | `default_rate_basis` | Select | باليوم · بالساعة · بالشهر |  |
| ساعات الشهر القياسي | `standard_month_hours` | Float |  |  |
| المزامنة اليومية لموقع المعدات | `sync_equipment_location_daily` | Check |  |  |


### إعدادات الديزل


**جدول أسعار الديزل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| جدول أسعار الديزل | `diesel_price_schedule` | Table | [سعر الديزل](/card/ar/reference/doctypes/card-diesel-price/) |  |


**مورد الديزل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| سياسة مورد الديزل | `diesel_supplier_policy` | Select | ثابت · متغير |  |
| مورد الديزل | `diesel_supplier` | Link | المورد |  |
| دور تعديل مورد الديزل | `diesel_supplier_editor_role` | Link | الدور |  |
| دور استثناء سعر الديزل | `diesel_price_exception_role` | Link | الدور |  |
| دور السعر الصفري للديزل | `diesel_zero_price_role` | Link | الدور |  |


### إعدادات النقل


**أسعار النقل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| دور تعديل سعر النقل | `transport_price_editor_role` | Link | الدور |  |
| سعر النقل لكل مشروع | `project_transport_prices` | Table | [سعر النقل للمشروع](/card/ar/reference/doctypes/card-project-transport-price/) |  |


### المخازن ومراكز التكلفة


**أنواع الإضافات والخصومات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| أنواع الإضافات والخصومات | `adjustment_types` | Table | [نوع الإضافة والخصم](/card/ar/reference/doctypes/card-adjustment-type/) |  |
| مركز التكلفة لكل ورشة / مستودع | `location_cost_centers` | Table | [مركز تكلفة المكان](/card/ar/reference/doctypes/card-location-cost-center/) |  |


### المواد


**احتياجات المعدات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المخزن الرئيسي | `default_store_warehouse` | Link | المستودع |  |
| مخزن عهدة الأدوات | `tool_custody_warehouse` | Link | المستودع |  |
| تنبيه للطلب المتكرر خلال (يوم) | `repeat_request_days` | Int |  |  |


### صلاحيات متقدمة


## الجداول الفرعية

- [إعدادات كارت للشركة](/card/ar/reference/doctypes/card-company-settings/)
- [سعر الديزل](/card/ar/reference/doctypes/card-diesel-price/)
- [سعر النقل للمشروع](/card/ar/reference/doctypes/card-project-transport-price/)
- [نوع الإضافة والخصم](/card/ar/reference/doctypes/card-adjustment-type/)
- [مركز تكلفة المكان](/card/ar/reference/doctypes/card-location-cost-center/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء |
| مدير النظام (permlevel 1) | قراءة, كتابة |
| مدير النظام (permlevel 2) | قراءة, كتابة |
| مدير الحسابات | قراءة, كتابة |
| مدير الحسابات (permlevel 1) | قراءة, كتابة |
| مدير الحسابات (permlevel 2) | قراءة |
| مدير الكروت | قراءة |
| مدير الكروت (permlevel 2) | قراءة |
