---
title: "تعبئة ديزل للمشروع"
description: "حقول نوع المستند تعبئة ديزل للمشروع وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "تعبئة ديزل للمشروع"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Project Diesel Fill**

| | |
|---|---|
| النوع | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| الوحدة | Card |
| فتح في الواجهة | `/app/project-diesel-fill` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| التاريخ | `date` | Date |  | نعم |
| المشروع | `project` | Link | المشروع | نعم |
| المورد | `supplier` | Link | المورد | نعم |
| الشركة | `company` | Link | الشركة | نعم |


**قراءات العداد**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| صورة العداد عند البداية | `opening_photo` | Attach Image |  |  |
| قراءة عداد التعبئة عند البداية | `opening_reading` | Float |  |  |
| صورة العداد عند النهاية | `closing_photo` | Attach Image |  |  |
| قراءة عداد التعبئة عند النهاية | `closing_reading` | Float |  |  |
| اللترات | `litres` | Float |  | نعم |


**المعدات التي تمت تعبئتها**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المعدات التي تمت تعبئتها | `equipment_filled` | Table | [معدات تعبئة الديزل](/card/ar/reference/doctypes/diesel-fill-equipment/) |  |
| المعدة (تحميل مباشر) | `card_equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |


**التوزيع (تقديري، للعرض فقط)**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| توزيع تعبئة الديزل <small>(للقراءة فقط)</small> | `diesel_fill_allocation` | Table | [توزيع تعبئة الديزل](/card/ar/reference/doctypes/diesel-fill-allocation/) |  |
| مراجعة التوزيع <small>(للقراءة فقط)</small> | `allocation_review` | Small Text |  |  |

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| سعر الوحدة <small>(للقراءة فقط)</small> | `unit_price` | Currency |  |  |
| قيمة التعبئة <small>(للقراءة فقط)</small> | `amount` | Currency |  |  |
| مصدر السعر <small>(للقراءة فقط)</small> | `price_source` | Select | سعر الشركة · Exception · يحتاج مراجعة |  |
| سعر الشركة <small>(مخفي, للقراءة فقط)</small> | `company_price` | Currency |  |  |
| عملة سعر الديزل <small>(للقراءة فقط)</small> | `price_currency` | Link | العملة |  |
| وحدة قياس سعر الديزل <small>(للقراءة فقط)</small> | `price_uom` | Link | وحدة القياس |  |
| سعر الديزل ساري من <small>(للقراءة فقط)</small> | `price_valid_from` | Date |  |  |


**فحص الأدلة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| فحص العداد التراكمي <small>(للقراءة فقط)</small> | `totalizer_check` | Select | غير قابل للفحص · متطابق · غير متطابق |  |
| تنبيهات الأدلة <small>(للقراءة فقط)</small> | `evidence_warnings` | Small Text |  |  |


**مراجعة التشغيل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| حالة المراجعة | `review_status` | Select | Draft · يحتاج مراجعة · موافقة التشغيل · Rejected |  |
| ملاحظات المراجعة | `review_notes` | Small Text |  |  |
| راجعه <small>(للقراءة فقط)</small> | `ops_reviewed_by` | Link | المستخدم |  |
| تاريخ المراجعة <small>(للقراءة فقط)</small> | `ops_reviewed_on` | Datetime |  |  |


**تفاصيل العداد**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| العداد التراكمي عند البداية | `opening_totalizer` | Data |  |  |
| وقت صورة البداية | `opening_photo_time` | Datetime |  |  |
| العداد التراكمي عند النهاية | `closing_totalizer` | Data |  |  |
| وقت صورة النهاية | `closing_photo_time` | Datetime |  |  |
| موقع التصوير | `photo_location` | Data |  |  |


**استثناء السعر**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| استثناء السعر | `price_exception` | Check |  |  |
| سبب الاستثناء | `exception_reason` | Small Text |  |  |
| الاستثناء بواسطة <small>(للقراءة فقط)</small> | `exception_by` | Link | المستخدم |  |
| تاريخ الاستثناء <small>(للقراءة فقط)</small> | `exception_on` | Datetime |  |  |


**فاتورة المورد والمصدر**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مفتاح المصدر <small>(للقراءة فقط)</small> | `source_key` | Data |  |  |
| رسائل المصدر <small>(للقراءة فقط)</small> | `source_messages` | Small Text |  |  |
| تعليق المصدر <small>(للقراءة فقط)</small> | `source_caption` | Small Text |  |  |
| رقم فاتورة المورد <small>(للقراءة فقط)</small> | `supplier_invoice_no` | Data |  |  |
| اللترات في الفاتورة <small>(للقراءة فقط)</small> | `invoiced_litres` | Float |  |  |
| سعر اللتر في الفاتورة <small>(للقراءة فقط)</small> | `invoice_unit_price` | Currency |  |  |
| أجرة النقل المفوترة كلترات <small>(للقراءة فقط)</small> | `delivery_charge_litres` | Float |  |  |
| دليل الفاتورة <small>(للقراءة فقط)</small> | `invoice_evidence` | Small Text |  |  |


**مركز التكلفة والترحيل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مركز التكلفة | `cost_center` | Link | مركز التكلفة |  |
| فاتورة الشراء <small>(للقراءة فقط)</small> | `purchase_invoice` | Link | فاتورة الشراء |  |
| الترحيل المحاسبي <small>(للقراءة فقط)</small> | `gl_posting` | Link | [سجل الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-log/) |  |
| مرحَّل <small>(للقراءة فقط)</small> | `posted` | Check |  |  |
| معدّل من <small>(للقراءة فقط)</small> | `amended_from` | Link | [تعبئة ديزل للمشروع](/card/ar/reference/doctypes/project-diesel-fill/) |  |
| سبب الإلغاء <small>(للقراءة فقط)</small> | `cancel_reason` | Small Text |  |  |

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| ملاحظات | `remarks` | Small Text |  |  |


**سير عمل الاعتماد**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| Workflow State <small>(مخفي, للقراءة فقط)</small> | `workflow_state` | Link | Workflow State |  |
| سبب الإرجاع للتصحيح <small>(للقراءة فقط)</small> | `return_reason` | Small Text |  |  |


## الجداول الفرعية

- [معدات تعبئة الديزل](/card/ar/reference/doctypes/diesel-fill-equipment/)
- [توزيع تعبئة الديزل](/card/ar/reference/doctypes/diesel-fill-allocation/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مستخدم الكروت | قراءة, كتابة, إنشاء, تقرير, طباعة, بريد |
| مدير الحسابات | قراءة, تقرير, تصدير, طباعة |
| مدير النظام (permlevel 1) | قراءة, كتابة |
| مدير الكروت (permlevel 1) | قراءة, كتابة |
| مستخدم الكروت (permlevel 1) | قراءة |
| مدير الحسابات (permlevel 1) | قراءة |
