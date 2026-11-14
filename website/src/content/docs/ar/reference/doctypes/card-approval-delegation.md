---
title: "Card Approval Delegation"
description: "حقول نوع المستند Card Approval Delegation وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "Card Approval Delegation"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

| | |
|---|---|
| النوع | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-approval-delegation` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| Delegator (grantor) | `delegator_user` | Link | المستخدم | نعم |
| Delegate (grantee) | `delegate_user` | Link | المستخدم | نعم |
| الشركة | `company` | Link | الشركة | نعم |
| Approval scope | `approval_scope` | Select | All CARD approvals · Monthly Cards · عدد النقلات · Diesel Fills | نعم |


**نافذة التفويض**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| من تاريخ | `from_date` | Date |  | نعم |
| إلى تاريخ | `to_date` | Date |  | نعم |
| Delegation status <small>(للقراءة فقط)</small> | `status` | Select | نشط · Expired · Cancelled |  |


**السبب**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| السبب | `reason` | Small Text |  | نعم |


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة |
