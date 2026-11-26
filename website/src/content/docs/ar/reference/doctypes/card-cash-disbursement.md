---
title: "الصرف النقدي"
description: "حقول نوع المستند الصرف النقدي وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "الصرف النقدي"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة. وهي تتبع الفرع الرئيسي، فقد تصف تغييرات مدمجة لم تصدر بعد؛ راجع صفحة «ما الجديد».
:::

**Card Cash Disbursement**

| | |
|---|---|
| النوع | مستند |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-cash-disbursement` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الشركة <small>(للقراءة فقط)</small> | `company` | Link | الشركة | نعم |
| المورد <small>(للقراءة فقط)</small> | `supplier` | Link | المورد | نعم |
| CARD <small>(للقراءة فقط)</small> | `card` | Link | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | نعم |
| السطر المصدر <small>(للقراءة فقط)</small> | `adjustment_row` | Data |  | نعم |
| المعدات <small>(للقراءة فقط)</small> | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |
| المشروع <small>(للقراءة فقط)</small> | `project` | Link | المشروع |  |
| المبلغ | `amount` | Currency |  | نعم |
| تاريخ الدفع | `payment_date` | Date |  | نعم |
| حساب النقدية | `cash_account` | Link | الحساب | نعم |
| مستند الإثبات | `evidence` | Small Text |  | نعم |
| الحالة <small>(للقراءة فقط)</small> | `status` | Select | Pending · Approved · قيد الترحيل · فشل الترحيل · مُرحَّل · طُلب الإلغاء · Cancelled |  |
| مفتاح المعاملة <small>(للقراءة فقط)</small> | `transaction_key` | Data |  |  |
| Journal Entry <small>(للقراءة فقط)</small> | `journal_entry` | Link | Journal Entry |  |
| اعتمده <small>(للقراءة فقط)</small> | `approved_by` | Link | المستخدم |  |
| تاريخ الاعتماد <small>(للقراءة فقط)</small> | `approved_on` | Datetime |  |  |
| تاريخ الترحيل <small>(للقراءة فقط)</small> | `posted_on` | Datetime |  |  |
| حجزه للترحيل <small>(للقراءة فقط)</small> | `posting_claimed_by` | Link | المستخدم |  |
| تاريخ الحجز <small>(للقراءة فقط)</small> | `posting_claimed_on` | Datetime |  |  |
| سبب الإلغاء <small>(للقراءة فقط)</small> | `cancellation_reason` | Small Text |  |  |
| طلب الإلغاء بواسطة <small>(للقراءة فقط)</small> | `cancellation_requested_by` | Data |  |  |
| تاريخ طلب الإلغاء <small>(للقراءة فقط)</small> | `cancellation_requested_on` | Datetime |  |  |
| ألغاه <small>(للقراءة فقط)</small> | `cancelled_by` | Data |  |  |
| تاريخ الإلغاء <small>(للقراءة فقط)</small> | `cancelled_on` | Datetime |  |  |
| Replaces <small>(للقراءة فقط)</small> | `replaces` | Link | [الصرف النقدي](/card/ar/reference/doctypes/card-cash-disbursement/) |  |
| سبب الاستبدال <small>(للقراءة فقط)</small> | `replacement_reason` | Small Text |  |  |
| خطأ الترحيل <small>(للقراءة فقط)</small> | `posting_error` | Small Text |  |  |
| رحّله <small>(للقراءة فقط)</small> | `posted_by` | Data |  |  |


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير الكروت | قراءة, كتابة, إنشاء, تقرير, تصدير, طباعة |
| مدير الحسابات | قراءة, تقرير, طباعة |
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقرير, تصدير, طباعة, بريد |
