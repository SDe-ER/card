---
title: "المرجع"
description: "مرجع مولَّد لكل أنواع المستندات والتقارير ونقاط الـ API في CARD."
editUrl: false
sidebar:
  order: 1
  label: "الملخص"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

يُبنى هذا القسم من الشيفرة نفسها، لذا يطابق دائمًا الإصدار الحالي من CARD. وللشرح وسير العمل والأمثلة راجع أقسام المزايا والتقارير ومرجع الـ API.

| | |
|---|---|
| [أنواع المستندات](/card/ar/reference/doctypes/card-adjustment-type/) | 41 |
| [التقارير](/card/ar/reference/reports/) | 25 |
| [نقاط الـ API](/card/ar/reference/api-endpoints/) | 70 |


## أنواع المستندات

| أنواع المستندات | النوع |
|---|---|
| [نوع الإضافة والخصم](/card/ar/reference/doctypes/card-adjustment-type/) | جدول فرعي (صفوف داخل مستند آخر) |
| [مسؤولية تكلفة في الاتفاقية](/card/ar/reference/doctypes/card-agreement-responsibility/) | جدول فرعي (صفوف داخل مستند آخر) |
| [إعدادات كارت للشركة](/card/ar/reference/doctypes/card-company-settings/) | جدول فرعي (صفوف داخل مستند آخر) |
| [معدل الاستهلاك](/card/ar/reference/doctypes/card-consumption-rate/) | جدول فرعي (صفوف داخل مستند آخر) |
| [اليومية](/card/ar/reference/doctypes/card-daily-log/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [سطر اليومية](/card/ar/reference/doctypes/card-daily-log-row/) | جدول فرعي (صفوف داخل مستند آخر) |
| [إعدادات اليومية](/card/ar/reference/doctypes/card-daily-log-settings/) | مستند |
| [سعر الديزل](/card/ar/reference/doctypes/card-diesel-price/) | جدول فرعي (صفوف داخل مستند آخر) |
| [المعدات](/card/ar/reference/doctypes/card-equipment/) | مستند |
| [تعيين معدة على مشروع](/card/ar/reference/doctypes/card-equipment-assignment/) | مستند |
| [فئة المعدات](/card/ar/reference/doctypes/card-equipment-category/) | مستند |
| [مكوّن المعدة](/card/ar/reference/doctypes/card-equipment-component/) | جدول فرعي (صفوف داخل مستند آخر) |
| [عميل المعدات](/card/ar/reference/doctypes/card-equipment-customer/) | مستند |
| [ماركة المعدة](/card/ar/reference/doctypes/card-equipment-make/) | مستند |
| [موديل المعدة](/card/ar/reference/doctypes/card-equipment-model/) | مستند |
| [توافق قطع الغيار](/card/ar/reference/doctypes/card-equipment-part/) | مستند |
| [مورد المعدات](/card/ar/reference/doctypes/card-equipment-supplier/) | مستند |
| [نوع المعدة](/card/ar/reference/doctypes/card-equipment-type/) | مستند |
| [مركز تكلفة المكان](/card/ar/reference/doctypes/card-location-cost-center/) | جدول فرعي (صفوف داخل مستند آخر) |
| [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [إضافة أو خصم الكارت الشهري](/card/ar/reference/doctypes/card-monthly-card-adjustment/) | جدول فرعي (صفوف داخل مستند آخر) |
| [يوم الكارت الشهري](/card/ar/reference/doctypes/card-monthly-card-day/) | جدول فرعي (صفوف داخل مستند آخر) |
| [دورة الفترة](/card/ar/reference/doctypes/card-period-run/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [مستند مصدري لدورة الفترة](/card/ar/reference/doctypes/card-period-run-source/) | جدول فرعي (صفوف داخل مستند آخر) |
| [سعر النقل للمشروع](/card/ar/reference/doctypes/card-project-transport-price/) | جدول فرعي (صفوف داخل مستند آخر) |
| [اتفاقية أسعار المعدة](/card/ar/reference/doctypes/card-rate-agreement/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [الإعدادات](/card/ar/reference/doctypes/card-settings/) | مفرد (سجل إعدادات واحد) |
| [سبب توقف المعدة](/card/ar/reference/doctypes/card-stop-reason/) | مستند |
| [معدل استهلاك النوع](/card/ar/reference/doctypes/card-type-consumption-rate/) | جدول فرعي (صفوف داخل مستند آخر) |
| [معدات تعبئة الديزل](/card/ar/reference/doctypes/diesel-fill-equipment/) | جدول فرعي (صفوف داخل مستند آخر) |
| [عهدة أدوات الموظف](/card/ar/reference/doctypes/employee-tool-custody/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [قراءة عداد المعدة](/card/ar/reference/doctypes/equipment-meter-reading/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [بند طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request-item/) | جدول فرعي (صفوف داخل مستند آخر) |
| [مراجعة احتياجات المعدات](/card/ar/reference/doctypes/equipment-needs-review/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [بند مراجعة احتياجات المعدات](/card/ar/reference/doctypes/equipment-needs-review-item/) | جدول فرعي (صفوف داخل مستند آخر) |
| [نقل المعدات](/card/ar/reference/doctypes/equipment-transport/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
| [معدة رحلة النقل](/card/ar/reference/doctypes/equipment-transport-item/) | جدول فرعي (صفوف داخل مستند آخر) |
| [سجل الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-log/) | مستند |
| [مصدر الترحيل](/card/ar/reference/doctypes/gl-posting-source/) | جدول فرعي (صفوف داخل مستند آخر) |
| [تعبئة ديزل للمشروع](/card/ar/reference/doctypes/project-diesel-fill/) | قابل للتقديم (مسودة ← مقدَّم ← ملغى) |
