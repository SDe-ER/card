---
title: "طلب احتياجات معدة"
description: "حقول نوع المستند طلب احتياجات معدة وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "طلب احتياجات معدة"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Equipment Needs Request**

| | |
|---|---|
| النوع | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| الوحدة | Card |
| فتح في الواجهة | `/app/equipment-needs-request` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الشركة <small>(مخفي, للقراءة فقط)</small> | `company` | Link | الشركة |  |
| المعدات | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) | نعم |
| اسم المعدة <small>(للقراءة فقط)</small> | `equipment_name` | Data |  |  |
| المشروع <small>(للقراءة فقط)</small> | `project` | Link | المشروع |  |
| المشغّل | `operator` | Link | الموظف | نعم |
| اسم المشغّل <small>(للقراءة فقط)</small> | `operator_name` | Data |  |  |
| التاريخ | `request_date` | Date |  | نعم |
| أدخله <small>(للقراءة فقط)</small> | `entered_by` | Link | المستخدم |  |
| مُدخل نيابة عن المشغل <small>(للقراءة فقط)</small> | `on_behalf` | Check |  |  |
| حالة المراجعة <small>(للقراءة فقط)</small> | `review_status` | Select | Pending · قيد المراجعة · Approved · Rejected |  |


**الاحتياجات**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الأصناف | `items` | Table | [بند طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request-item/) | نعم |
| ملاحظات | `notes` | Small Text |  |  |
| معدّل من <small>(للقراءة فقط)</small> | `amended_from` | Link | [طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request/) |  |


## الجداول الفرعية

- [بند طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request-item/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مشرف الكروت | قراءة, كتابة, إنشاء, تقديم, إلغاء, تعديل, تقرير, طباعة |
| مشغّل الكروت | قراءة, كتابة, إنشاء, تقديم, طباعة |
| مستخدم الكروت | قراءة, تقرير, طباعة |
