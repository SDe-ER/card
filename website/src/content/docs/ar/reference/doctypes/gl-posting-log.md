---
title: "سجل الترحيل المحاسبي"
description: "حقول نوع المستند سجل الترحيل المحاسبي وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "سجل الترحيل المحاسبي"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة. وهي تتبع الفرع الرئيسي، فقد تصف تغييرات مدمجة لم تصدر بعد؛ راجع صفحة «ما الجديد».
:::

**GL Posting Log**

| | |
|---|---|
| النوع | مستند |
| الوحدة | Card |
| فتح في الواجهة | `/app/gl-posting-log` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الشركة | `company` | Link | الشركة | نعم |
| نوع الطرف | `party_type` | Select | المورد · العميل | نعم |
| الطرف | `party` | Dynamic Link | party_type | نعم |
| الشهر | `month` | Data |  | نعم |
| السنة | `year` | Int |  | نعم |
| نوع الترحيل | `posting_type` | Select | فاتورة الشراء · فاتورة المبيعات · Journal Entry | نعم |
| الحالة <small>(للقراءة فقط)</small> | `status` | Select | Draft · Submitted · Cancelled · Failed | نعم |


**مستند الترحيل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| نوع مستند الترحيل <small>(للقراءة فقط)</small> | `posting_doctype` | Data |  |  |
| مستند الترحيل <small>(للقراءة فقط)</small> | `posting_doc` | Dynamic Link | posting_doctype |  |
| المبلغ <small>(للقراءة فقط)</small> | `amount` | Currency |  |  |
| مفتاح الترحيل <small>(للقراءة فقط)</small> | `posting_key` | Data |  |  |
| سبب الفشل | `failure_reason` | Small Text |  |  |
| ملاحظات | `remarks` | Small Text |  |  |
| التسلسل <small>(للقراءة فقط)</small> | `sequence` | Int |  |  |
| المصادر <small>(للقراءة فقط)</small> | `sources` | Table | [مصدر الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-source/) |  |
| المصدر <small>(للقراءة فقط)</small> | `origin` | Select | Built · Linked · Credit Note |  |


**السلامة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| توقيع البناء <small>(للقراءة فقط)</small> | `built_signature` | Data |  |  |
| توقيع البنود <small>(للقراءة فقط)</small> | `lines_signature` | Data |  |  |
| لقطة البناء <small>(مخفي, للقراءة فقط)</small> | `built_snapshot` | Long Text |  |  |
| توقيع التصحيح المقبول <small>(للقراءة فقط)</small> | `accepted_signature` | Data |  |  |
| قبل التصحيح <small>(للقراءة فقط)</small> | `accepted_by` | Link | المستخدم |  |
| سبب التصحيح <small>(للقراءة فقط)</small> | `correction_reason` | Small Text |  |  |
| فواتير موردين روجعت كغير مرتبطة <small>(للقراءة فقط)</small> | `reviewed_invoices` | Small Text |  |  |
| فرق مفتوح (فاتورة مربوطة) <small>(للقراءة فقط)</small> | `link_difference` | Currency |  |  |


## الجداول الفرعية

- [مصدر الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-source/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, تقرير, تصدير, طباعة, بريد |
| مدير الحسابات | قراءة, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, تقرير, طباعة |
