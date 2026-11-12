---
title: "بند مراجعة احتياجات المعدات"
description: "حقول نوع المستند بند مراجعة احتياجات المعدات وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "بند مراجعة احتياجات المعدات"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Equipment Needs Review Item**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الطلب <small>(للقراءة فقط)</small> | `request` | Link | [طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request/) |  |
| سطر الطلب <small>(مخفي, للقراءة فقط)</small> | `request_item` | Data |  |  |
| المعدات <small>(للقراءة فقط)</small> | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |
| المشغّل <small>(للقراءة فقط)</small> | `operator` | Link | الموظف |  |
| النوع <small>(للقراءة فقط)</small> | `kind` | Select | قطعة غيار · أداة |  |
| الصنف المطلوب | `item_code` | Link | الصنف |  |
| الوصف <small>(للقراءة فقط)</small> | `description` | Data |  |  |
| وحدة القياس | `uom` | Link | وحدة القياس |  |
| الكمية المطلوبة <small>(للقراءة فقط)</small> | `requested_qty` | Float |  |  |
| الموجود بالموقع | `found_qty` | Float |  |  |
| الكمية المعتمدة | `approved_qty` | Float |  |  |
| معاينة الموقع | `inspection` | Select | لم تتم المعاينة · تمت المعاينة |  |
| ملاحظة المعاينة | `inspection_note` | Data |  |  |
| عاينه <small>(للقراءة فقط)</small> | `inspected_by` | Link | المستخدم |  |
| تاريخ المعاينة <small>(للقراءة فقط)</small> | `inspected_on` | Date |  |  |
| طريقة التوفير | `route` | Select | من المخزن · شراء للمشروع |  |
| المستودع | `warehouse` | Link | المستودع |  |
| في المخزون <small>(للقراءة فقط)</small> | `stock_qty` | Float |  |  |
| مطلوب مؤخرًا <small>(للقراءة فقط)</small> | `repeat_flag` | Check |  |  |
| التوافق مع المعدة <small>(للقراءة فقط)</small> | `fit_status` | Select | مؤكد للمعدة · مؤكد للموديل · غير متوافق · قيد المراجعة · لا يوجد سجل توافق |  |
| سبب صنف بدون توافق مؤكد <small>(للقراءة فقط)</small> | `fit_reason` | Small Text |  |  |
| طلب المواد <small>(للقراءة فقط)</small> | `material_request` | Link | طلب المواد |  |
| عهدة الأداة <small>(للقراءة فقط)</small> | `tool_custody` | Link | [عهدة أدوات الموظف](/card/ar/reference/doctypes/employee-tool-custody/) |  |
| الكمية المسلّمة <small>(للقراءة فقط)</small> | `handed_qty` | Float |  |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
