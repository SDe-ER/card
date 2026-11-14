---
title: "Card Approval Tier Threshold"
description: "حقول نوع المستند Card Approval Tier Threshold وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "Card Approval Tier Threshold"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الشركة | `company` | Link | الشركة | نعم |
| اسم المستوى | `tier_name` | Data |  | نعم |
| حد صافي المبلغ | `amount_threshold` | Currency |  | نعم |
| الدور المطلوب | `role_required` | Link | الدور | نعم |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
