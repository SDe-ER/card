---
title: "مستند مصدري لدورة الفترة"
description: "حقول نوع المستند مستند مصدري لدورة الفترة وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "مستند مصدري لدورة الفترة"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Period Run Source**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| نوع المستند المصدري لدورة الفترة <small>(للقراءة فقط)</small> | `source_doctype` | Select | كارت التشغيل الشهري · تعبئة ديزل للمشروع · نقل المعدات |  |
| المستند المصدري لدورة الفترة <small>(للقراءة فقط)</small> | `source_name` | Data |  |  |
| المعدات <small>(للقراءة فقط)</small> | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |
| المشروع <small>(للقراءة فقط)</small> | `project` | Link | المشروع |  |
| المورد <small>(للقراءة فقط)</small> | `supplier` | Link | المورد |  |
| العميل <small>(للقراءة فقط)</small> | `customer` | Link | العميل |  |
| يُفوتر على جانب المورد <small>(للقراءة فقط)</small> | `supplier_side` | Check |  |  |
| يُفوتر على جانب العميل <small>(للقراءة فقط)</small> | `customer_side` | Check |  |  |
| مبلغ المصدر الإجمالي لجانب المورد في دورة الفترة <small>(للقراءة فقط)</small> | `supplier_amount` | Currency | currency |  |
| مبلغ المصدر الإجمالي لجانب العميل في دورة الفترة <small>(للقراءة فقط)</small> | `customer_amount` | Currency | currency |  |
| مورد التعبئة مسجّل في ضريبة القيمة المضافة <small>(للقراءة فقط)</small> | `supplier_vat_registered` | Check |  |  |
| جانب المورد مُرحَّل بالفعل <small>(للقراءة فقط)</small> | `supplier_posted` | Check |  |  |
| جانب العميل مُرحَّل بالفعل <small>(للقراءة فقط)</small> | `customer_posted` | Check |  |  |
| عملة دورة الفترة <small>(مخفي, للقراءة فقط)</small> | `currency` | Link | العملة |  |
| آخر تعديل للمستند المصدري <small>(للقراءة فقط)</small> | `source_modified` | Datetime |  |  |
| بصمة المستند المصدري <small>(للقراءة فقط)</small> | `content_hash` | Data |  |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
