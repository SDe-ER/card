---
title: واجهة API للأطراف والكشوف
description: نقاط نهاية سجل الموردين والعملاء، وخيارات فلاتر التقارير وقيمها الافتراضية، وملف PDF لكشف حساب المورد.
sidebar:
  order: 7
---

## نظرة عامة

يحتفظ CARD بصف في السجل لكل مورد معدات (**مورد المعدات**) ولكل عميل (**عميل المعدات**)، يحمل اسم الطرف في ERPNext. ولا
يخزّن السجل أي أرقام: فالصف مشترك بين جميع الشركات، وأي إجمالي مخزّن كان سيكشف نشاط الشركات الأخرى. وتُحسب الأرقام عند
الطلب للشركات التي يحق للمستدعي رؤيتها. وتخدم نقاط النهاية أدناه السجلَّ، وفلاترَ تقارير CARD، وملفَّ PDF لكشف المورد.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.api.party_figures` | أرقام طرف واحد من السجل لكل شركة. |
| POST | `card.api.refresh_supplier` | مزامنة صفوف الموردين في السجل. |
| POST | `card.api.refresh_customer` | مزامنة صفوف العملاء في السجل. |
| GET | `card.api.card_suppliers_query` | استعلام ربط: موردو السجل الذين لهم كروت. |
| GET | `card.api.card_customers_query` | استعلام ربط: عملاء السجل الذين لهم كروت. |
| GET، POST | `card.api.card_company_options` | خيارات فلتر الشركة في التقارير. |
| GET، POST | `card.api.card_project_options` | خيارات فلتر المشروع في التقارير. |
| GET | `card.api.report_defaults` | القيم الافتراضية لفلاتر التقارير من الإعدادات. |
| POST | `card.card.report.equipment_supplier_statement.statement_pdf.download_pdf` | كشف المورد بصيغة PDF بحجم A4. |

## party_figures

`GET /api/method/card.api.party_figures`

أرقام طرف واحد من السجل لكل شركة: صافي المورد، أو المبلغ المستحق على العميل (صافي العميل)، من الكروت المعتمدة، للشركات
المسموح بها فقط.

**الصلاحية:** أحد أدوار تقارير CARD، وقراءة صف السجل.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `party_type` | string | نعم | `Supplier` أو `Customer`. |
| `party` | string | نعم | اسم صف السجل (اسم الطرف). |

**القيمة المعادة:** قائمة لكل شركة من `{"company", "equipment_count", "card_count", "total_hours", "total", "first_month",
"last_month"}` (والأشهر بصيغة `YYYY-MM`).

```bash
curl -s -G "https://<your-site>/api/method/card.api.party_figures" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "party_type=Supplier" --data-urlencode "party=Supplier A"
```

## refresh_supplier وrefresh_customer

`POST /api/method/card.api.refresh_supplier` · `POST /api/method/card.api.refresh_customer`

تضمنان أن يكون لطرف واحد — أو لكل طرف له كروت معتمدة في جانبه (الموردون: الكروت غير الملك؛ العملاء: كروت الفوترة) — صفٌّ
في السجل يحمل اسمه، دون أرقام مخزّنة. ويُعاد ضبط الصف الذي بقي باسم خاطئ بعد إعادة تسمية سابقة.

**الصلاحية:** System Manager فقط.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `supplier` / `customer` | string | لا | طرف واحد؛ وعند تركه فارغًا: جميع الأطراف. |

**القيمة المعادة:** قائمة `{"supplier": "<name>"}` / `{"customer": "<name>"}`. **الآثار الجانبية:** إدراج صفوف السجل أو
إعادة تسميتها أو حفظها.

```bash
curl -s -X POST "https://<your-site>/api/method/card.api.refresh_supplier" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"supplier": "Supplier A"}'
```

## card_suppliers_query وcard_customers_query

`GET /api/method/card.api.card_suppliers_query` · `GET /api/method/card.api.card_customers_query`

استعلاما الربط لفلاتر الكشوف: صفوف السجل التي لها كرت واحد على الأقل، مسودة أو معتمد، في شركة يحق للمستخدم رؤيتها. ويرتبط
الفلتر بالسجل لأن كل أدوار التقارير يحق لها قراءته، في حين لا تستطيع الأدوار التشغيلية قراءة الموردين أو العملاء.

**الصلاحية:** أحد أدوار تقارير CARD.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `doctype` | string | نعم | وسيط استعلام الربط القياسي. |
| `txt` | string | نعم | نص البحث (الاسم أو اسم الطرف). |
| `searchfield` | string | نعم | وسيط استعلام الربط القياسي. |
| `start` | int | نعم | الإزاحة. |
| `page_len` | int | نعم | حجم الصفحة. |
| `filters` | object | نعم | `{"company": "<company>"}` (والشركة اختيارية؛ والشركة التي لا يحق للمستخدم رؤيتها لا تعيد شيئًا). |

**القيمة المعادة:** قائمة `[name, supplier_name]` أو `[name, customer_name]`.

```bash
curl -s -G "https://<your-site>/api/method/card.api.card_suppliers_query" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Card Equipment Supplier" --data-urlencode "txt=" --data-urlencode "searchfield=name" \
  --data-urlencode "start=0" --data-urlencode "page_len=20" --data-urlencode 'filters={"company":"Example Contracting Co."}'
```

## card_company_options

`GET|POST /api/method/card.api.card_company_options`

خيارات فلتر الشركة في التقارير: الشركات التي يحق للمستخدم رؤيتها. للقراءة فقط (وتُقبل `POST` لأن عنصر الإكمال التلقائي
يرسل بها).

**الصلاحية:** أحد أدوار تقارير CARD.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `txt` | string | لا | نص بحث لا يميّز حالة الأحرف. |

**القيمة المعادة:** حتى 50 اسم شركة.

```bash
curl -s -G "https://<your-site>/api/method/card.api.card_company_options" -H "Authorization: token <api_key>:<api_secret>"
```

## card_project_options

`GET|POST /api/method/card.api.card_project_options`

خيارات فلتر المشروع في التقارير: مشاريع الشركات التي يحق للمستخدم رؤيتها. للقراءة فقط.

**الصلاحية:** أحد أدوار تقارير CARD.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `txt` | string | لا | نص البحث (رقم السجل أو اسم المشروع). |
| `company` | string | لا | قصر النتائج على شركة واحدة. |

**القيمة المعادة:** حتى 50 كائنًا `{"value": "PROJ-0001", "label": "PROJ-0001: Project name"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.api.card_project_options" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "company=Example Contracting Co."
```

## report_defaults

`GET /api/method/card.api.report_defaults`

القيم الافتراضية لفلاتر التقارير من الإعدادات، لأي دور من أدوار التقارير (إذ لا يستطيع Card User قراءة الإعدادات).

**الصلاحية:** أحد أدوار تقارير CARD. **المعاملات:** لا توجد.

**القيمة المعادة:** `{"default_statement_type": "<value>", "include_draft_in_reports": 0|1}`.

```bash
curl -s "https://<your-site>/api/method/card.api.report_defaults" -H "Authorization: token <api_key>:<api_secret>"
```

## download_pdf

`POST /api/method/card.card.report.equipment_supplier_statement.statement_pdf.download_pdf`

يشغّل **كشف حساب المورد** بصلاحيات المستدعي ويعيد كشف A4 ملفَّ PDF مولَّدًا بمولّد Chrome (بتشكيل عربي صحيح). ونقطة
النهاية لا تقبل إلا الفلاتر، ولا تقبل HTML أبدًا.

**الصلاحية:** أدوار التقرير، وصلاحية **الطباعة** على كروت التشغيل الشهرية، والفحوص القياسية للتقرير ولقيم الفلاتر؛ ويتحقق
التقرير من الشركة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `filters` | object | نعم | فلاتر التقرير: `company` و`statement_type` و`supplier` و`from_month` و`from_year` و`to_month` و`to_year` و`project` و`equipment` و`equipment_type` و`include_draft`. قيم بسيطة فقط؛ وتُرفض القيمة التي هي قائمة أو كائن. |

**القيمة المعادة:** ملف PDF (`Equipment Supplier Statement.pdf` مترجمًا). **الآثار الجانبية:** تسجيل قيد في سجل الوصول.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.report.equipment_supplier_statement.statement_pdf.download_pdf" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"filters": {"company": "Example Contracting Co.", "statement_type": "مورد", "supplier": "Supplier A", "from_month": "01", "from_year": 2026, "to_month": "01", "to_year": 2026}}' \
  -o statement.pdf
```

## ذو صلة

- [الموردون والعملاء](/card/ar/features/suppliers-customers/)
- [تقارير الأطراف والكشوف](/card/ar/reports/parties-statements/)
- [تنسيقات الطباعة](/card/ar/features/print-formats/)
