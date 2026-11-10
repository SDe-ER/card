---
title: "توافق قطع الغيار"
description: "حقول نوع المستند توافق قطع الغيار وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "توافق قطع الغيار"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Equipment Part**

| | |
|---|---|
| النوع | مستند |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-equipment-part` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| صنف القطعة | `item_code` | Link | الصنف | نعم |
| ينطبق على | `applies_to` | Select | موديل معدة · المعدات | نعم |
| موديل المعدة | `equipment_model` | Link | [موديل المعدة](/card/ar/reference/doctypes/card-equipment-model/) |  |
| المعدات | `card_equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |
| حالة التوافق | `compatibility_status` | Select | قيد المراجعة الفنية · Confirmed · غير متوافق | نعم |
| مرحلة المراجعة <small>(للقراءة فقط)</small> | `review_stage` | Select | بانتظار المراجعة الثانية |  |
| سبب القرار | `decision_reason` | Small Text |  |  |
| نشط | `is_active` | Check |  |  |


**إثبات التوافق**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مصدر الإثبات | `evidence_source` | Select | كتالوج قطع الصانع · كتالوج الصانع أو الوكيل · تأكيد المورد أو الوكيل · فحص فعلي على المعدة · سجل تركيب · Other |  |
| مرجع الإثبات | `evidence_reference` | Data |  |  |
| ملف الإثبات | `evidence_file` | Attach |  |  |
| الكمية لكل استخدام | `qty_per_use` | Float |  |  |
| ملاحظات فنية | `technical_notes` | Small Text |  |  |


**سجل المراجعة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| اقترحه <small>(للقراءة فقط)</small> | `proposed_by` | Link | المستخدم |  |
| تاريخ الاقتراح <small>(للقراءة فقط)</small> | `proposed_on` | Datetime |  |  |
| المراجعة الأولى بواسطة <small>(للقراءة فقط)</small> | `first_review_by` | Link | المستخدم |  |
| تاريخ المراجعة الأولى <small>(للقراءة فقط)</small> | `first_review_on` | Datetime |  |  |
| قرار المراجعة الأولى <small>(للقراءة فقط)</small> | `first_review_decision` | Select | Confirmed · غير متوافق |  |
| سبب المراجعة الأولى <small>(للقراءة فقط)</small> | `first_review_reason` | Small Text |  |  |
| قرره <small>(للقراءة فقط)</small> | `confirmed_by` | Link | المستخدم |  |
| تاريخ القرار <small>(للقراءة فقط)</small> | `confirmed_on` | Datetime |  |  |
| أوقفه <small>(للقراءة فقط)</small> | `retired_by` | Link | المستخدم |  |
| تاريخ الإيقاف <small>(للقراءة فقط)</small> | `retired_on` | Datetime |  |  |
| سبب الإيقاف | `retire_reason` | Small Text |  |  |
| المصدر <small>(للقراءة فقط)</small> | `source` | Select | Manual · اقتراح المشرف · طلب معتمد · Installation |  |
| الطلب المصدر <small>(للقراءة فقط)</small> | `source_request` | Link | [طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request/) |  |
| الشركة <small>(للقراءة فقط)</small> | `company` | Link | الشركة |  |
| مفتاح التوافق <small>(مخفي, للقراءة فقط)</small> | `compat_key` | Data |  |  |


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, تقرير, تصدير, طباعة |
| مدير الكروت | قراءة, كتابة, إنشاء, تقرير, تصدير, طباعة |
| مشرف الكروت | قراءة, كتابة, إنشاء, تقرير, طباعة |
