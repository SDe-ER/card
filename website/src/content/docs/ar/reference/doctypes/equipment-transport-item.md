---
title: "معدة رحلة النقل"
description: "حقول نوع المستند معدة رحلة النقل وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "معدة رحلة النقل"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Equipment Transport Item**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المعدات | `card_equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) | نعم |
| اسم المعدة <small>(للقراءة فقط)</small> | `equipment_name` | Data |  |  |
| حصة التكلفة | `amount` | Currency |  |  |
| Manual share <small>(مخفي)</small> | `manual_share` | Check |  |  |
| التعيين السابق <small>(للقراءة فقط)</small> | `previous_assignment` | Link | [تعيين معدة على مشروع](/card/ar/reference/doctypes/card-equipment-assignment/) |  |
| التعيين المُنشأ <small>(للقراءة فقط)</small> | `created_assignment` | Link | [تعيين معدة على مشروع](/card/ar/reference/doctypes/card-equipment-assignment/) |  |
| الحركة <small>(للقراءة فقط)</small> | `movement` | Select | أول دخول · Transfer · للورشة · للمستودع · رجوع للمورد |  |
| من مشروع <small>(للقراءة فقط)</small> | `from_project` | Link | المشروع |  |
| مكانها الحالي <small>(للقراءة فقط)</small> | `from_type` | Select | المشروع · ورشة صيانة · مستودع · المورد |  |
| من مكان <small>(للقراءة فقط)</small> | `from_location` | Link | الموقع |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
