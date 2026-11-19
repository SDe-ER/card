---
title: "Card Cash Disbursement"
description: "حقول نوع المستند Card Cash Disbursement وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "Card Cash Disbursement"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

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
| Source row <small>(للقراءة فقط)</small> | `adjustment_row` | Data |  | نعم |
| المعدات <small>(للقراءة فقط)</small> | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |
| المشروع <small>(للقراءة فقط)</small> | `project` | Link | المشروع |  |
| المبلغ | `amount` | Currency |  | نعم |
| تاريخ الدفع | `payment_date` | Date |  | نعم |
| Cash account | `cash_account` | Link | الحساب | نعم |
| Supporting evidence | `evidence` | Small Text |  | نعم |
| الحالة <small>(للقراءة فقط)</small> | `status` | Select | Pending · Approved · قيد الترحيل · فشل الترحيل · مرحَّل · طُلب الإلغاء · Cancelled |  |
| Transaction key <small>(للقراءة فقط)</small> | `transaction_key` | Data |  |  |
| Journal Entry <small>(للقراءة فقط)</small> | `journal_entry` | Link | Journal Entry |  |
| اعتمده <small>(للقراءة فقط)</small> | `approved_by` | Link | المستخدم |  |
| تاريخ الاعتماد <small>(للقراءة فقط)</small> | `approved_on` | Datetime |  |  |
| Posted on <small>(للقراءة فقط)</small> | `posted_on` | Datetime |  |  |
| Claimed for posting by <small>(للقراءة فقط)</small> | `posting_claimed_by` | Link | المستخدم |  |
| Claimed on <small>(للقراءة فقط)</small> | `posting_claimed_on` | Datetime |  |  |
| Cancellation Reason <small>(للقراءة فقط)</small> | `cancellation_reason` | Small Text |  |  |
| Cancellation Requested By <small>(للقراءة فقط)</small> | `cancellation_requested_by` | Data |  |  |
| Cancellation Requested On <small>(للقراءة فقط)</small> | `cancellation_requested_on` | Datetime |  |  |
| Cancelled By <small>(للقراءة فقط)</small> | `cancelled_by` | Data |  |  |
| Cancelled On <small>(للقراءة فقط)</small> | `cancelled_on` | Datetime |  |  |
| Replaces <small>(للقراءة فقط)</small> | `replaces` | Link | [Card Cash Disbursement](/card/ar/reference/doctypes/card-cash-disbursement/) |  |
| سبب الاستبدال <small>(للقراءة فقط)</small> | `replacement_reason` | Small Text |  |  |
| Posting Error <small>(للقراءة فقط)</small> | `posting_error` | Small Text |  |  |
| Posted By <small>(للقراءة فقط)</small> | `posted_by` | Data |  |  |


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير الكروت | قراءة, كتابة, إنشاء, تقرير, تصدير, طباعة |
| مدير الحسابات | قراءة, تقرير, طباعة |
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقرير, تصدير, طباعة, بريد |
