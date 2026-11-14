---
title: "التقارير"
description: "كل تقارير CARD مع عوامل التصفية والأدوار التي يمكنها تشغيلها."
editUrl: false
sidebar:
  order: 2
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

| التقارير | مبني على | الأدوار |
|---|---|---|
| [مراجعة ربط الأصول](#asset-mapping-review) | [المعدات](/card/ar/reference/doctypes/card-equipment/) | مدير النظام, مدير الكروت, مدير الحسابات |
| [حالة تسوية الكروت](#card-settlement-status) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الحسابات |
| [تحليل ديزل المجموعة](#diesel-group-analysis) | [مجموعة تشغيل معدات](/card/ar/reference/doctypes/equipment-operating-group/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [مطابقة فواتير الديزل](#diesel-invoice-reconciliation) | [تعبئة ديزل للمشروع](/card/ar/reference/doctypes/project-diesel-fill/) | مدير النظام, مدير الحسابات |
| [فروقات الديزل والحالات الشاذة](#diesel-variance-anomaly) | [تعبئة ديزل للمشروع](/card/ar/reference/doctypes/project-diesel-fill/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [استهلاك المعدات](#equipment-consumption) | [المعدات](/card/ar/reference/doctypes/card-equipment/) | مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات |
| [كشف حساب العميل](#equipment-customer-statement) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [ملخص العملاء](#equipment-customers-summary) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [تحليل ديزل المعدات](#equipment-diesel-analysis) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [استهلاك ديزل المعدات](#equipment-diesel-consumption) | [تعبئة ديزل للمشروع](/card/ar/reference/doctypes/project-diesel-fill/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [توقفات المعدات](#equipment-downtime) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [مصروفات معدات بدون معدة](#equipment-expenses-without-equipment) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الحسابات |
| [سجل مواقع المعدات](#equipment-location-history) | [المعدات](/card/ar/reference/doctypes/card-equipment/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [تكلفة صيانة المعدات](#equipment-maintenance-cost) | فاتورة الشراء | مدير النظام, مدير الحسابات |
| [قيم الماركة والموديل النصية](#equipment-make-model-values) | [المعدات](/card/ar/reference/doctypes/card-equipment/) | مدير النظام, مدير الكروت |
| [مطابقة عدادات المعدات](#equipment-meter-reconciliation) | [المعدات](/card/ar/reference/doctypes/card-equipment/) | مدير النظام, مدير الكروت, مدير الحسابات |
| [القائمة المجمعة لاحتياجات المعدات](#equipment-needs-summary) | [مراجعة احتياجات المعدات](/card/ar/reference/doctypes/equipment-needs-review/) | مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات |
| [الهامش الجزئي للمعدات](#equipment-partial-margin) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الحسابات |
| [كشف حساب المورد](#equipment-supplier-statement) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [ملخص الموردين](#equipment-suppliers-summary) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [تكلفة التشغيل بالمشروع](#operating-cost-by-project) | [تعبئة ديزل للمشروع](/card/ar/reference/doctypes/project-diesel-fill/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [سلامة مصادر الترحيل](#posting-source-integrity) | [سجل الترحيل المحاسبي](/card/ar/reference/doctypes/gl-posting-log/) | مدير النظام, مدير الحسابات |
| [الطلبات المتكررة للمعدات](#repeat-equipment-requests) | [طلب احتياجات معدة](/card/ar/reference/doctypes/equipment-needs-request/) | مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات |
| [مراجعة محاسبة النقل](#transport-accounting-review) | [نقل المعدات](/card/ar/reference/doctypes/equipment-transport/) | مدير النظام, مدير الحسابات |
| [تكلفة النقل بالمشروع](#transport-cost-by-project) | [نقل المعدات](/card/ar/reference/doctypes/equipment-transport/) | مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات |
| [أعمال الكروت غير المفوترة](#unbilled-card-work) | [كارت التشغيل الشهري](/card/ar/reference/doctypes/card-monthly-card/) | مدير النظام, مدير الحسابات, مدير الكروت |
| [عهد العمال](#worker-custody) | [عهدة أدوات الموظف](/card/ar/reference/doctypes/employee-tool-custody/) | مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات |


<h2 id="asset-mapping-review">مراجعة ربط الأصول</h2>

**Asset Mapping Review**

- النوع: Script Report
- مبني على: المعدات
- الأدوار: مدير النظام, مدير الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| عرض | `show` | Select |  |


<h2 id="card-settlement-status">حالة تسوية الكروت</h2>

**Card Settlement Status**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| نوع الطرف | `party_type` | Select | نعم |
| الطرف | `party` | Dynamic Link |  |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |


<h2 id="diesel-group-analysis">تحليل ديزل المجموعة</h2>

**Diesel Group Analysis**

- النوع: Script Report
- مبني على: مجموعة تشغيل معدات
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| مجموعة التشغيل | `group` | Link → مجموعة تشغيل معدات |  |


<h2 id="diesel-invoice-reconciliation">مطابقة فواتير الديزل</h2>

**Diesel Invoice Reconciliation**

- النوع: Script Report
- مبني على: تعبئة ديزل للمشروع
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| موردو الديزل (مسار توريد واحد) | `suppliers` | MultiSelectList |  |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| جلسات الديزل المشمولة | `session_status` | Select |  |
| مدى تاريخ الفاتورة (أيام) | `date_window_days` | Int |  |
| أجرة التوصيل حتى (لتر) | `max_delivery_litres` | Float |  |


<h2 id="diesel-variance-anomaly">فروقات الديزل والحالات الشاذة</h2>

**Diesel Variance Anomaly**

- النوع: Script Report
- مبني على: تعبئة ديزل للمشروع
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |
| نوع المعدة | `equipment_type` | Link → نوع المعدة |  |


<h2 id="equipment-consumption">استهلاك المعدات</h2>

**Equipment Consumption**

- النوع: Script Report
- مبني على: المعدات
- الأدوار: مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| من تاريخ | `from_date` | Date |  |
| إلى تاريخ | `to_date` | Date |  |
| المشروع | `project` | Link → المشروع |  |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="equipment-customer-statement">كشف حساب العميل</h2>

**Equipment Customer Statement**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| العميل | `customer` | Link → عميل المعدات | نعم |
| من شهر | `from_month` | Select | نعم |
| من سنة | `from_year` | Int | نعم |
| إلى شهر | `to_month` | Select | نعم |
| إلى سنة | `to_year` | Int | نعم |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |
| نوع المعدة | `equipment_type` | Link → نوع المعدة |  |
| تشمل المسودات | `include_draft` | Check |  |


<h2 id="equipment-customers-summary">ملخص العملاء</h2>

**Equipment Customers Summary**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من شهر | `from_month` | Select | نعم |
| من سنة | `from_year` | Int | نعم |
| إلى شهر | `to_month` | Select | نعم |
| إلى سنة | `to_year` | Int | نعم |
| المشروع | `project` | Autocomplete |  |


<h2 id="equipment-diesel-analysis">تحليل ديزل المعدات</h2>

**Equipment Diesel Analysis**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من شهر | `from_month` | Select | نعم |
| من سنة | `from_year` | Int | نعم |
| إلى شهر | `to_month` | Select |  |
| إلى سنة | `to_year` | Int |  |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="equipment-diesel-consumption">استهلاك ديزل المعدات</h2>

**Equipment Diesel Consumption**

- النوع: Script Report
- مبني على: تعبئة ديزل للمشروع
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date |  |
| إلى تاريخ | `to_date` | Date |  |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="equipment-downtime">توقفات المعدات</h2>

**Equipment Downtime**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| تجميع التوقف حسب | `group_by` | Select |  |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |
| سبب التوقف | `stop_reason` | Link → سبب توقف المعدة |  |
| الجهة المسؤولة | `responsible_party_type` | Select |  |
| تضمين الكروت المسودة | `include_drafts` | Check |  |


<h2 id="equipment-expenses-without-equipment">مصروفات معدات بدون معدة</h2>

**Equipment Expenses Without Equipment**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date |  |
| إلى تاريخ | `to_date` | Date |  |


<h2 id="equipment-location-history">سجل مواقع المعدات</h2>

**Equipment Location History**

- النوع: Script Report
- مبني على: المعدات
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="equipment-maintenance-cost">تكلفة صيانة المعدات</h2>

**Equipment Maintenance Cost**

- النوع: Script Report
- مبني على: فاتورة الشراء
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="equipment-make-model-values">قيم الماركة والموديل النصية</h2>

**Equipment Make Model Values**

- النوع: Script Report
- مبني على: المعدات
- الأدوار: مدير النظام, مدير الكروت

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| المعدات بدون موديل فقط | `unlinked_only` | Check |  |


<h2 id="equipment-meter-reconciliation">مطابقة عدادات المعدات</h2>

**Equipment Meter Reconciliation**

- النوع: Script Report
- مبني على: المعدات
- الأدوار: مدير النظام, مدير الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| المعدات | `equipment` | Link → المعدات |  |
| العرض | `view` | Select |  |
| عرض | `show` | Select |  |
| نسبة الفرق المسموح بها % | `tolerance_pct` | Float |  |


<h2 id="equipment-needs-summary">القائمة المجمعة لاحتياجات المعدات</h2>

**Equipment Needs Summary**

- النوع: Script Report
- مبني على: مراجعة احتياجات المعدات
- الأدوار: مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| المشروع | `project` | Link → المشروع |  |
| اعتماد الإدارة | `approval_status` | Select |  |


<h2 id="equipment-partial-margin">الهامش الجزئي للمعدات</h2>

**Equipment Partial Margin**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="equipment-supplier-statement">كشف حساب المورد</h2>

**Equipment Supplier Statement**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| نوع الكشف | `statement_type` | Select | نعم |
| المورد | `supplier` | Link → مورد المعدات | نعم |
| من شهر | `from_month` | Select | نعم |
| من سنة | `from_year` | Int | نعم |
| إلى شهر | `to_month` | Select | نعم |
| إلى سنة | `to_year` | Int | نعم |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |
| نوع المعدة | `equipment_type` | Link → نوع المعدة |  |
| تشمل المسودات | `include_draft` | Check |  |


<h2 id="equipment-suppliers-summary">ملخص الموردين</h2>

**Equipment Suppliers Summary**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من شهر | `from_month` | Select | نعم |
| من سنة | `from_year` | Int | نعم |
| إلى شهر | `to_month` | Select | نعم |
| إلى سنة | `to_year` | Int | نعم |
| المشروع | `project` | Autocomplete |  |


<h2 id="operating-cost-by-project">تكلفة التشغيل بالمشروع</h2>

**Operating Cost by Project**

- النوع: Script Report
- مبني على: تعبئة ديزل للمشروع
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date |  |
| إلى تاريخ | `to_date` | Date |  |
| المشروع | `project` | Autocomplete |  |


<h2 id="posting-source-integrity">سلامة مصادر الترحيل</h2>

**Posting Source Integrity**

- النوع: Script Report
- مبني على: سجل الترحيل المحاسبي
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| عرض | `show` | Select |  |


<h2 id="repeat-equipment-requests">الطلبات المتكررة للمعدات</h2>

**Repeat Equipment Requests**

- النوع: Script Report
- مبني على: طلب احتياجات معدة
- الأدوار: مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| المشروع | `project` | Link → المشروع |  |
| المعدات | `equipment` | Link → المعدات |  |


<h2 id="transport-accounting-review">مراجعة محاسبة النقل</h2>

**Transport Accounting Review**

- النوع: Script Report
- مبني على: نقل المعدات
- الأدوار: مدير النظام, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| عرض | `show` | Select |  |


<h2 id="transport-cost-by-project">تكلفة النقل بالمشروع</h2>

**Transport Cost by Project**

- النوع: Script Report
- مبني على: نقل المعدات
- الأدوار: مدير النظام, مدير الكروت, مستخدم الكروت, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date |  |
| إلى تاريخ | `to_date` | Date |  |
| المشروع | `project` | Autocomplete |  |


<h2 id="unbilled-card-work">أعمال الكروت غير المفوترة</h2>

**Unbilled Card Work**

- النوع: Script Report
- مبني على: كارت التشغيل الشهري
- الأدوار: مدير النظام, مدير الحسابات, مدير الكروت

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الشركة | `company` | Autocomplete | نعم |
| من تاريخ | `from_date` | Date | نعم |
| إلى تاريخ | `to_date` | Date | نعم |
| جانب الفوترة | `side` | Select |  |
| المشروع | `project` | Autocomplete |  |
| المعدات | `equipment` | Link → المعدات |  |
| تضمين الكروت المحجوزة في ترحيل مسودة | `include_drafts` | Check |  |


<h2 id="worker-custody">عهد العمال</h2>

**Worker Custody**

- النوع: Script Report
- مبني على: عهدة أدوات الموظف
- الأدوار: مدير النظام, مدير الكروت, مشرف الكروت, مستخدم الكروت, مدير المخزون, مدير الحسابات

| التسمية | اسم الحقل | النوع | إلزامي |
|---|---|---|---|
| الموظف | `employee` | Link → الموظف |  |
