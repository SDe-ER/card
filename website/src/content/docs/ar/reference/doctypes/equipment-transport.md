---
title: "نقل المعدات"
description: "حقول نوع المستند نقل المعدات وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "نقل المعدات"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Equipment Transport**

| | |
|---|---|
| النوع | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| الوحدة | Card |
| فتح في الواجهة | `/app/equipment-transport` |


## الحقول

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| التاريخ | `date` | Date |  | نعم |
| إلى مشروع | `project` | Link | المشروع |  |
| مورد النقل | `transport_supplier` | Link | المورد |  |
| الشركة | `company` | Link | الشركة | نعم |
| المعدات <small>(مخفي, للقراءة فقط)</small> | `equipment` | Link | [المعدات](/card/ar/reference/doctypes/card-equipment/) |  |
| من (نص قديم) <small>(مخفي, للقراءة فقط)</small> | `from_location` | Data |  |  |
| إلى (نص قديم) <small>(مخفي, للقراءة فقط)</small> | `to_location` | Data |  |  |
| تكلفة الناقل | `amount` | Currency |  |  |
| مركز التكلفة <small>(للقراءة فقط)</small> | `cost_center` | Link | مركز التكلفة |  |

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المعدات | `items` | Table | [معدة رحلة النقل](/card/ar/reference/doctypes/equipment-transport-item/) |  |


**السجلات المرتبطة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| فاتورة الشراء <small>(للقراءة فقط)</small> | `purchase_invoice` | Link | فاتورة الشراء |  |
| ملاحظات | `remarks` | Small Text |  |  |
| معدّل من <small>(للقراءة فقط)</small> | `amended_from` | Link | [نقل المعدات](/card/ar/reference/doctypes/equipment-transport/) |  |
| سبب الإلغاء <small>(للقراءة فقط)</small> | `cancel_reason` | Small Text |  |  |
| الترحيل المحاسبي <small>(للقراءة فقط)</small> | `gl_posting` | Link | [سجل الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-log/) |  |
| مرحَّل <small>(للقراءة فقط)</small> | `posted` | Check |  |  |
| طريقة النقل | `transport_method` | Select | رأس تريلا · ونش · لوبد · سير ذاتي · Other |  |
| التعيين السابق <small>(للقراءة فقط)</small> | `previous_assignment` | Link | [تعيين معدة على مشروع](/card/ar/reference/doctypes/card-equipment-assignment/) |  |
| التعيين المُنشأ <small>(للقراءة فقط)</small> | `created_assignment` | Link | [تعيين معدة على مشروع](/card/ar/reference/doctypes/card-equipment-assignment/) |  |
| ملكية المعدة | `ownership` | Select | ملك · إيجار · طرف ثالث |  |
| مورد المعدة | `equipment_supplier` | Link | المورد |  |
| تكلفة النقل على <small>(للقراءة فقط)</small> | `cost_borne_by` | Select | الشركة · مورد المعدة · العميل |  |
| الوجهة | `destination_type` | Select | المشروع · ورشة صيانة · مستودع · المورد | نعم |
| إلى مكان | `destination_location` | Link | الموقع |  |
| من <small>(للقراءة فقط)</small> | `source_type` | Select | المشروع · ورشة صيانة · مستودع · المورد |  |
| من مشروع <small>(للقراءة فقط)</small> | `source_project` | Link | المشروع |  |
| من مكان <small>(للقراءة فقط)</small> | `source_location` | Link | الموقع |  |


**المسار**


**التكلفة والتاريخ**


**مسؤولية التكلفة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مسؤولية النقل | `responsibility` | Select | الشركة تتحمل التكلفة · الشركة تدفع وتفوتر العميل · الشركة تدفع وتسترد من مورد المعدة · مورد المعدة يتحمل التكلفة · العميل يدفع للناقل مباشرة · طرف آخر يتحمل التكلفة · بدون تكلفة نقل · المسؤولية تحتاج مراجعة | نعم |
| مين بيدفع للناقل <small>(مخفي, للقراءة فقط)</small> | `payer` | Select | الشركة · مورد المعدة · العميل · طرف آخر · بدون تكلفة |  |
| مين يتحمل التكلفة <small>(مخفي, للقراءة فقط)</small> | `cost_bearer` | Select | الشركة · مورد المعدة · العميل · طرف آخر |  |
| تُحمّل على <small>(مخفي, للقراءة فقط)</small> | `cost_basis` | Select | المشروع · ورشة أو مخزن · مصروف عام للشركة |  |
| قابل للفوترة على العميل <small>(مخفي, للقراءة فقط)</small> | `customer_billable` | Check |  |  |
| قابل للاسترداد من المورد <small>(مخفي, للقراءة فقط)</small> | `supplier_recoverable` | Check |  |  |
| مشروع التكلفة | `cost_project` | Link | المشروع |  |
| مركز تكلفة عام <small>(مخفي)</small> | `overhead_cost_center` | Link | مركز التكلفة |  |


**القرار المالي**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الحالة المالية <small>(للقراءة فقط)</small> | `financial_status` | Select | لا يحتاج قرارًا · Pending · Approved · Rejected |  |
| القرار المالي للتكلفة <small>(للقراءة فقط)</small> | `financial_decision` | Select | فوترة العميل · الشركة تتحمل · الاسترداد من مورد المعدة · إعادة للتصحيح |  |
| العميل <small>(للقراءة فقط)</small> | `customer` | Link | العميل |  |
| مشروع الفوترة <small>(للقراءة فقط)</small> | `billing_project` | Link | المشروع |  |
| مبلغ الفوترة المتفق عليه (قبل الضريبة) <small>(للقراءة فقط)</small> | `billing_amount` | Currency |  |  |
| الفوترة <small>(للقراءة فقط)</small> | `billing_mode` | Select | الفاتورة الشهرية · فاتورة منفصلة |  |
| مرجع التفويض <small>(للقراءة فقط)</small> | `billing_reference` | Data |  |  |
| مستند التفويض <small>(للقراءة فقط)</small> | `billing_document` | Attach |  |  |
| سبب التحمل <small>(للقراءة فقط)</small> | `absorption_reason` | Small Text |  |  |
| طريقة الاسترداد <small>(للقراءة فقط)</small> | `recovery_mode` | Select | خصم من المستحقات الشهرية · مستند تسوية |  |
| مبلغ الاسترداد <small>(للقراءة فقط)</small> | `recovery_amount` | Currency |  |  |
| ملاحظة القرار <small>(للقراءة فقط)</small> | `decision_note` | Small Text |  |  |
| قرره <small>(للقراءة فقط)</small> | `financial_approver` | Link | المستخدم |  |
| تاريخ القرار <small>(للقراءة فقط)</small> | `financial_decided_on` | Datetime |  |  |
| اعتمد النقل <small>(للقراءة فقط)</small> | `submitted_by` | Link | المستخدم |  |
| عدّل النقل <small>(مخفي, للقراءة فقط)</small> | `edited_by` | Small Text |  |  |
| قاعدة يوم النقل <small>(للقراءة فقط)</small> | `move_day_rule` | Select | التخصيص الجديد يبدأ في اليوم التالي للنقل · التخصيص الجديد يبدأ في يوم النقل |  |
| نوع الطرف الآخر | `party_type` | Select | المورد · العميل · الموظف |  |
| الطرف الآخر الذي يتحمل تكلفة النقل | `party` | Dynamic Link | party_type |  |
| المبلغ المتفق عليه (ليس تكلفة على الشركة) | `informational_amount` | Currency |  |  |


**مصدر الإدخال**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| قناة الاستلام | `intake_channel` | Select | Manual · ورقي · WhatsApp · Email · Other |  |
| مفتاح المصدر | `intake_source_key` | Data |  |  |
| تاريخ ووقت الاستلام | `intake_received_on` | Datetime |  |  |
| مستند المصدر | `intake_evidence` | Attach |  |  |
| بصمة مستند المصدر (SHA-256) <small>(للقراءة فقط)</small> | `intake_evidence_hash` | Data |  |  |


**سير عمل الاعتماد**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| Workflow State <small>(مخفي, للقراءة فقط)</small> | `workflow_state` | Link | Workflow State |  |
| سبب الإرجاع للتصحيح <small>(للقراءة فقط)</small> | `return_reason` | Small Text |  |  |


## الجداول الفرعية

- [معدة رحلة النقل](/card/ar/reference/doctypes/equipment-transport-item/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, تقديم, إلغاء, تعديل, تقرير, تصدير, طباعة, بريد |
| مستخدم الكروت | قراءة, كتابة, إنشاء, تقرير, طباعة, بريد |
| مدير الحسابات | قراءة, تقرير, تصدير, طباعة |
| مدير النظام (permlevel 1) | قراءة |
| مدير الكروت (permlevel 1) | قراءة |
| مدير الحسابات (permlevel 1) | قراءة |
