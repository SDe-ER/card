---
title: "توزيع تعبئة الديزل"
description: "حقول نوع المستند توزيع تعبئة الديزل وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "توزيع تعبئة الديزل"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Diesel Fill Allocation**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المعدات <small>(للقراءة فقط)</small> | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) | نعم |
| اسم المعدة <small>(للقراءة فقط)</small> | `card_equipment_name` | Data |  |  |
| الأساس <small>(للقراءة فقط)</small> | `basis` | Select | مقدر · مقيس |  |
| Rule <small>(للقراءة فقط)</small> | `rule` | Data |  |  |
| ساعات التشغيل <small>(للقراءة فقط)</small> | `hours` | Float |  |  |
| المعدل المستخدم (لتر/ساعة) <small>(للقراءة فقط)</small> | `rate_used` | Float |  |  |
| اللترات الموزعة <small>(للقراءة فقط)</small> | `allocated_litres` | Float |  |  |
| Remainder row <small>(للقراءة فقط)</small> | `remainder` | Check |  |  |
| تحتاج مراجعة <small>(للقراءة فقط)</small> | `review_flag` | Check |  |  |
| Frozen on <small>(للقراءة فقط)</small> | `frozen_on` | Datetime |  |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
