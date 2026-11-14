---
title: "يوم الكارت الشهري"
description: "حقول نوع المستند يوم الكارت الشهري وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "يوم الكارت الشهري"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Monthly Card Day**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول


**بيانات اليوم**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| التاريخ | `operation_date` | Date |  | نعم |
| اليوم <small>(للقراءة فقط)</small> | `day_name` | Data |  |  |
| حالة اليوم | `day_status` | Select | عمل · إجازة · عطل · توقف من العميل |  |
| ساعات التشغيل | `working_hours` | Float |  |  |
| عدد الردود | `loads_count` | Int |  |  |
| سبب التوقف | `idle_reason` | Data |  |  |


**التوقف**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| سبب التوقف | `stop_reason` | Link | [سبب توقف المعدة](/card/ar/reference/doctypes/card-stop-reason/) |  |
| ساعات التوقف | `stopped_hours` | Float |  |  |
| توقف يُحتسب إيجارًا <small>(للقراءة فقط)</small> | `reason_billable` | Check |  |  |
| الجهة المسؤولة | `responsible_party_type` | Select | الشركة · المورد · العميل · Other |  |
| سجل الجهة المسؤولة | `responsible_party` | Dynamic Link | responsible_party_type |  |
| اسم الجهة المسؤولة | `responsible_party_name` | Data |  |  |
| ملاحظات | `notes` | Data |  |  |


**مصدر الإدخال**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مصدر الإدخال | `intake_source` | Select | يدوي · ورقي · واتساب · تطبيق موبايل · استيراد |  |
| مفتاح المصدر | `intake_source_key` | Data |  |  |
| تاريخ ووقت الاستلام | `intake_received_on` | Datetime |  |  |
| بصمة مستند المصدر (SHA-256) <small>(للقراءة فقط)</small> | `intake_evidence_hash` | Data |  |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
