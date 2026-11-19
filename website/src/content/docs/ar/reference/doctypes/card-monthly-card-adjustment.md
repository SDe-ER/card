---
title: "إضافة أو خصم الكارت الشهري"
description: "حقول نوع المستند إضافة أو خصم الكارت الشهري وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "إضافة أو خصم الكارت الشهري"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Monthly Card Adjustment**

| | |
|---|---|
| النوع | جدول فرعي (صفوف داخل مستند آخر) |
| الوحدة | Card |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| دفع نقدي | `is_cash_disbursement` | Check |  |  |
| حالة الدفعة النقدية <small>(للقراءة فقط)</small> | `cash_status` | Data |  |  |
| الدفعة النقدية <small>(للقراءة فقط)</small> | `cash_payment` | Link | [Card Cash Disbursement](/card/ar/reference/doctypes/card-cash-disbursement/) |  |
| Journal Entry <small>(للقراءة فقط)</small> | `cash_journal_entry` | Link | Journal Entry |  |
| حساب النقدية للمصروف المدفوع نيابةً عن المالك | `cash_account` | Link | الحساب |  |
| التاريخ | `adjustment_date` | Date |  | نعم |
| النوع | `adjustment_type` | Select | إضافة · خصم | نعم |
| الوصف | `description` | Data |  | نعم |
| المبلغ | `amount` | Currency |  | نعم |
| نوع الإضافة/الخصم | `adjustment_type_ref` | Data |  |  |
| الجانب | `side` | Select | المورد · العميل |  |


**رسوم توقف**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| سبب التوقف | `stop_reason` | Link | [سبب توقف المعدة](/card/ar/reference/doctypes/card-stop-reason/) |  |
| مرجع الاتفاق | `agreement_reference` | Data |  |  |
| الجهة المسؤولة | `responsible_party_type` | Select | الشركة · المورد · العميل · Other |  |
| سجل الجهة المسؤولة | `responsible_party` | Dynamic Link | responsible_party_type |  |
| اسم الجهة المسؤولة | `responsible_party_name` | Data |  |  |


## الصلاحيات

لا صلاحيات مستقلة: يتبع الوصول المستند الأب.
