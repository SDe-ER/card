---
title: "دورة الفترة"
description: "حقول نوع المستند دورة الفترة وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "دورة الفترة"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Period Run**

| | |
|---|---|
| النوع | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-period-run` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الشركة | `company` | Link | الشركة | نعم |
| شهر دورة الفترة | `month` | Select | 01 · 02 · 03 · 04 · 05 · 06 · 07 · 08 · 09 · 10 · 11 · 12 | نعم |
| سنة دورة الفترة | `year` | Int |  | نعم |
| إصدار دورة الفترة <small>(للقراءة فقط)</small> | `version` | Int |  |  |
| قاعدة الاعتماد الذاتي لدورة الفترة | `self_approval_rule` | Select | تنبيه فقط (دورة الفترة) · رفض (دورة الفترة) |  |
| اعتماد دورة الفترة <small>(للقراءة فقط)</small> | `approval_status` | Select | Pending · Approved · مرجعة للتصحيح |  |
| أرسل دورة الفترة <small>(للقراءة فقط)</small> | `submitted_by` | Link | المستخدم |  |
| عدّل دورة الفترة <small>(مخفي, للقراءة فقط)</small> | `edited_by` | Small Text |  |  |
| اعتمد دورة الفترة <small>(للقراءة فقط)</small> | `approved_by` | Link | المستخدم |  |
| تاريخ اعتماد دورة الفترة <small>(للقراءة فقط)</small> | `approved_on` | Datetime |  |  |
| الإصدار المعتمد لدورة الفترة <small>(للقراءة فقط)</small> | `approved_version` | Int |  |  |
| بصمة اللقطة المعتمدة <small>(مخفي, للقراءة فقط)</small> | `approved_hash` | Data |  |  |
| اعتمدها معدّها <small>(للقراءة فقط)</small> | `self_approved` | Check |  |  |
| سبب إرجاع دورة الفترة <small>(للقراءة فقط)</small> | `return_reason` | Small Text |  |  |
| أرجع دورة الفترة <small>(للقراءة فقط)</small> | `returned_by` | Link | المستخدم |  |
| تاريخ إرجاع دورة الفترة <small>(للقراءة فقط)</small> | `returned_on` | Datetime |  |  |


**لقطة دورة الفترة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| تاريخ بناء اللقطة <small>(للقراءة فقط)</small> | `built_on` | Datetime |  |  |
| بصمة اللقطة <small>(للقراءة فقط)</small> | `snapshot_hash` | Data |  |  |
| عملة دورة الفترة <small>(للقراءة فقط)</small> | `currency` | Link | العملة |  |
| أساس ضريبة سعر الديزل وقت البناء <small>(للقراءة فقط)</small> | `diesel_vat_basis` | Data |  |  |
| إصدار البصمة لدورة الفترة <small>(مخفي, للقراءة فقط)</small> | `fingerprint_version` | Int |  |  |
| المستندات المصدرية في الدورة <small>(للقراءة فقط)</small> | `source_count` | Int |  |  |
| مستندات جانب المورد <small>(للقراءة فقط)</small> | `supplier_source_count` | Int |  |  |
| إجمالي المصادر الإجمالي لجانب المورد <small>(للقراءة فقط)</small> | `supplier_total` | Currency | currency |  |
| مستندات جانب العميل <small>(للقراءة فقط)</small> | `customer_source_count` | Int |  |  |
| إجمالي المصادر الإجمالي لجانب العميل <small>(للقراءة فقط)</small> | `customer_total` | Currency | currency |  |


**المستندات المصدرية لدورة الفترة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المستندات المصدرية لدورة الفترة <small>(للقراءة فقط)</small> | `sources` | Table | [مستند مصدري لدورة الفترة](/card/ar/reference/doctypes/card-period-run-source/) |  |
| معدّل من <small>(للقراءة فقط)</small> | `amended_from` | Link | [دورة الفترة](/card/ar/reference/doctypes/card-period-run/) |  |


## الجداول الفرعية

- [مستند مصدري لدورة الفترة](/card/ar/reference/doctypes/card-period-run-source/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة |
| مدير الحسابات | قراءة, كتابة, تقديم, إلغاء, تقرير, تصدير, طباعة |
| مدير النظام (permlevel 1) | قراءة |
| مدير الكروت (permlevel 1) | قراءة |
| مدير الحسابات (permlevel 1) | قراءة |
