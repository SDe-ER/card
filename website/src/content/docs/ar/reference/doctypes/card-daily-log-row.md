---
title: "سطر اليومية"
description: "حقول نوع المستند سطر اليومية وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "سطر اليومية"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Daily Log Row**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المعدات | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) | نعم |
| اسم المعدة <small>(للقراءة فقط)</small> | `equipment_name` | Data |  |  |
| ساعات الوردية النهارية | `day_hours` | Float |  |  |
| ساعات الوردية الليلية | `night_hours` | Float |  |  |
| سبب التوقف | `stop_reason` | Link | [سبب توقف المعدة](/card/ar/reference/doctypes/card-stop-reason/) |  |
| ساعات التوقف | `stopped_hours` | Float |  |  |
| الجهة المسؤولة | `responsible_party_type` | Select | الشركة · المورد · العميل · Other |  |
| سجل الجهة المسؤولة | `responsible_party` | Dynamic Link | responsible_party_type |  |
| اسم الجهة المسؤولة | `responsible_party_name` | Data |  |  |
| ملاحظات | `notes` | Small Text |  |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
