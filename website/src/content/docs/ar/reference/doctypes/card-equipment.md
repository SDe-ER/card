---
title: "المعدات"
description: "حقول نوع المستند المعدات وتخطيطه وصلاحياته."
editUrl: false
sidebar:
  label: "المعدات"
---

:::note
تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.
:::

**Card Equipment**

| | |
|---|---|
| النوع | مستند |
| الوحدة | Card |
| فتح في الواجهة | `/app/card-equipment` |


## الحقول


### البيانات الأساسية


**بيانات المعدة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الشركة | `company` | Link | الشركة | نعم |
| الملكية | `ownership` | Select | ملك · إيجار · طرف ثالث | نعم |
| العلامة التجارية | `brand` | Data |  |  |
| الموديل | `model` | Data |  |  |
| ماركة المعدة | `equipment_make` | Link | [ماركة المعدة](/card/ar/reference/doctypes/card-equipment-make/) |  |
| موديل المعدة | `equipment_model` | Link | [موديل المعدة](/card/ar/reference/doctypes/card-equipment-model/) |  |
| سنة الصنع | `manufacture_year` | Int |  |  |
| رقم الشاسيه | `serial_no` | Data |  |  |
| رقم اللوحة | `plate_no` | Data |  |  |
| مفتاح رقم الشاسيه <small>(مخفي, للقراءة فقط)</small> | `serial_no_key` | Data |  |  |
| مفتاح رقم اللوحة <small>(مخفي, للقراءة فقط)</small> | `plate_no_key` | Data |  |  |
| فئة المعدة <small>(للقراءة فقط)</small> | `equipment_category` | Link | [فئة المعدات](/card/ar/reference/doctypes/card-equipment-category/) |  |
| اسم المعدة | `equipment_name` | Data |  | نعم |
| نوع المعدة | `equipment_type` | Link | [نوع المعدة](/card/ar/reference/doctypes/card-equipment-type/) | نعم |
| الصورة <small>(مخفي)</small> | `image` | Attach Image |  |  |
| الحالة | `status` | Select | نشطة · متوقفة · في الصيانة · منتهية |  |
| وحدة (معدتين مع بعض) | `is_unit` | Check |  |  |


**مكوّنات الوحدة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المكوّنات | `components` | Table | [مكوّن المعدة](/card/ar/reference/doctypes/card-equipment-component/) |  |


### التشغيل والتعيين


**التعيين الحالي**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المشروع الحالي <small>(للقراءة فقط)</small> | `current_project` | Link | المشروع |  |
| اسم المشغّل | `external_operator_name` | Data |  |  |
| المشغّل | `operator` | Link | الموظف |  |
| تاريخ التعيين <small>(للقراءة فقط)</small> | `assignment_date` | Date |  |  |
| مركز التكلفة | `cost_center` | Link | مركز التكلفة |  |
| جوال المشغّل | `external_operator_phone` | Data |  |  |
| اسم المشغّل <small>(للقراءة فقط)</small> | `operator_name` | Data |  |  |
| الموقع | `site_location` | Data |  |  |


### التكلفة والإيجار


**بيانات الإيجار**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| المؤجر / المالك | `supplier` | Link | المورد |  |
| بداية الإيجار | `rental_start_date` | Date |  |  |
| طريقة الحساب | `rate_type` | Select | باليوم · بالساعة · بالشهر |  |
| ساعات العمل اليومية | `daily_hours` | Float |  | نعم |
| مُهمَل – غير مستخدم <small>(مخفي, للقراءة فقط)</small> | `min_hours` | Float |  |  |
| المشغّل على | `operator_on` | Select | المؤجر · الشركة |  |
| رقم العقد | `contract_no` | Data |  |  |
| نهاية الإيجار | `rental_end_date` | Date |  |  |
| السعر | `rate` | Currency |  |  |
| أساس احتساب اليوم | `day_billing_basis` | Select | تناسبي حسب الساعات · يوم كامل |  |
| الوقود على | `الوقود_على` | Select | المؤجر · الشركة |  |
| سعر الساعة <small>(للقراءة فقط)</small> | `approved_hourly_rate` | Currency |  |  |


**التكلفة الداخلية**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الأصل في ERPNext | `الأصل_في_erpnext` | Link | الأصل |  |
| صنف الأصل <small>(للقراءة فقط)</small> | `asset_item` | Data |  |  |
| موقع الأصل <small>(للقراءة فقط)</small> | `asset_location` | Data |  |  |
| مركز تكلفة الأصل <small>(للقراءة فقط)</small> | `asset_cost_center` | Link | مركز التكلفة |  |
| قيمة شراء الأصل <small>(للقراءة فقط)</small> | `asset_purchase_value` | Currency |  |  |
| سعر الساعة الداخلي | `internal_hourly_rate` | Currency |  |  |
| أساس السعر الداخلي للتشغيل | `internal_rate_basis` | Select | بالساعة · باليوم |  |
| السعر الداخلي للتشغيل | `internal_rate` | Currency |  |  |


### العداد والصيانة


**العداد**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| نوع العداد | `meter_type` | Select | ساعات · كيلومترات · بدون عداد |  |
| قراءة العداد عند الاستلام | `opening_meter` | Float |  |  |
| آخر قراءة <small>(للقراءة فقط)</small> | `current_meter` | Float |  |  |
| سعة الخزان (لتر) | `tank_capacity` | Float |  |  |
| الاستهلاك المتوقع (لتر/ساعة) | `expected_consumption` | Float |  |  |


**الصيانة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| الصيانة كل (ساعة) | `service_interval_hours` | Float |  |  |
| تاريخ آخر صيانة | `last_service_date` | Date |  |  |
| الصيانة كل (لتر ديزل) | `service_interval_liters` | Float |  |  |
| قراءة العداد عند آخر صيانة | `last_service_meter` | Float |  |  |


### المستندات


**مستندات المعدة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| رقم الاستمارة | `registration_no` | Data |  |  |
| انتهاء الاستمارة | `registration_expiry` | Date |  |  |
| صورة الاستمارة | `registration_file` | Attach |  |  |
| انتهاء الفحص الدوري | `inspection_expiry` | Date |  |  |
| شهادة الفحص | `inspection_file` | Attach |  |  |
| شركة التأمين | `insurance_company` | Data |  |  |
| رقم وثيقة التأمين | `insurance_policy_no` | Data |  |  |
| انتهاء التأمين | `insurance_expiry` | Date |  |  |
| ملف التأمين | `insurance_file` | Attach |  |  |
| رقم TUV | `tuv_no` | Data |  |  |
| انتهاء TUV | `tuv_expiry` | Date |  |  |
| صورة TUV | `tuv_file` | Attach |  |  |


### الخروج


**إنهاء المعدة**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| تاريخ الإنهاء | `exit_date` | Date |  |  |
| سبب الإنهاء | `exit_reason` | Select | انتهاء الإيجار · إرجاع للمؤجر · بيع · تكهين · نقل لفرع آخر |  |
| قراءة العداد عند الإنهاء | `exit_meter` | Float |  |  |
| حالة التسوية | `settlement_status` | Select | لم تتم · تمت |  |

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| ملاحظات | `exit_notes` | Small Text |  |  |


### الارتباطات

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| مكوّن وحدة (بدون كارت شهري) <small>(للقراءة فقط)</small> | `is_unit_component` | Check |  |  |
| نوع سعر العميل | `customer_rate_type` | Select | باليوم · بالساعة · بالشهر · بالمتر المكعب |  |
| سعر العميل | `customer_rate` | Currency |  |  |
| سعر العميل (الوردية الليلية) | `customer_rate_night` | Currency |  |  |
| سعة الرد (م³) | `load_volume_m3` | Float |  |  |
| العميل | `default_customer` | Link | العميل |  |
| اتجاه التأجير | `rental_direction` | Select | مستأجَرة من مورد · مؤجَّرة لعميل · إيجار من الباطن · تشغيل داخلي |  |
| سبب تغيير الشروط التجارية | `commercial_change_reason` | Small Text |  |  |
| استهلاك الديزل اليومي (لتر لليوم القياسي) | `daily_diesel_consumption` | Float |  |  |
| معدلات استهلاك المعدة (لتر في الساعة) | `consumption_rates` | Table | [معدل الاستهلاك](/card/ar/reference/doctypes/card-consumption-rate/) |  |


**معايير التشغيل**


**جانب العميل**

| التسمية | اسم الحقل | النوع | الخيارات / الربط | إلزامي |
|---|---|---|---|---|
| النوع من الأصل <small>(مخفي, للقراءة فقط)</small> | `equipment_type_from_asset` | Check |  |  |


## الجداول الفرعية

- [مكوّن المعدة](/card/ar/reference/doctypes/card-equipment-component/)
- [معدل الاستهلاك](/card/ar/reference/doctypes/card-consumption-rate/)


## الصلاحيات

| الدور | الحقوق |
|---|---|
| مدير النظام | قراءة, كتابة, إنشاء, حذف, تقرير, تصدير, طباعة, بريد |
| مدير الكروت | قراءة, كتابة, إنشاء, تقرير, تصدير, طباعة, بريد |
| مستخدم الكروت | قراءة, كتابة, تقرير, طباعة, بريد |
| مدير الحسابات | قراءة, تقرير, تصدير, طباعة |
| مشرف الكروت | قراءة |
| مدير النظام (permlevel 1) | قراءة, كتابة |
| مدير الكروت (permlevel 1) | قراءة, كتابة |
| مستخدم الكروت (permlevel 1) | قراءة |
| مدير الحسابات (permlevel 1) | قراءة |
| مدير النظام (permlevel 2) | قراءة, كتابة |
| مدير الكروت (permlevel 2) | قراءة, كتابة |
| مدير الحسابات (permlevel 2) | قراءة |
