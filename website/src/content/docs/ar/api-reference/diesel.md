---
title: واجهة API للديزل
description: نقاط نهاية الديزل الموزع على الكرت، ومساعدات نموذج تعبئة الديزل، واستثناءات السعر، وفلتر الموردين في تقرير المطابقة.
sidebar:
  order: 4
---

## نظرة عامة

جلسات الديزل هي سجلات **تعبئة ديزل للمشروع** (Project Diesel Fill)، وتُقرأ وتُكتب بواجهة الموارد القياسية
(`/api/resource/Project Diesel Fill`). ويحدد التحقق الخاص بالتعبئة في كل حفظ سعرَ الشركة والمبلغ وحالة المراجعة وتحذيرات
الأدلة. وتقدّم نقاط النهاية أدناه لنموذج التعبئة ما لا يستطيع مستخدمو التعبئة قراءته بأنفسهم (الإعدادات والمشاريع ومراكز
التكلفة والموردون)، وتعالج تغييرات السعر المدقَّقة في المسودة المحفوظة، وتعرض الديزل الموزع على الكرت.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.diesel.get_card_diesel` | الديزل الموزع على معدة كرت شهري واحد. |
| GET | `card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable` | هل يحق للمستخدم تغيير مورد الديزل. |
| GET | `card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query` | بحث الربط للمشروع ومركز التكلفة والمورد في نموذج التعبئة. |
| GET | `card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context` | سعر الشركة في تاريخ، وصلاحيات المستخدم في السعر. |
| POST | `card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price` | استبدال سعر المسودة بسعر الشركة. |
| POST | `card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception` | إنهاء استثناء السعر في مسودة. |
| GET | `card.diesel_reconciliation.diesel_supplier_options` | خيارات الموردين في تقرير مطابقة فواتير الديزل. |

## get_card_diesel

`GET /api/method/card.diesel.get_card_diesel`

الديزل الموزع على معدة الكرت لمشروع الكرت وشهره، مع جزأيه المسجل (التعبئة المباشرة) والتقديري (التوزيع بالساعات). للعرض
فقط: لا يُكتب أبدًا في الكرت ولا يؤثر أبدًا في صافيه.

**الصلاحية:** قراءة الكرت الشهري.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `card` | string | نعم | اسم كرت التشغيل الشهري. |

**القيمة المعادة:** `{"litres", "amount", "litres_recorded", "litres_estimated", "amount_recorded", "amount_estimated",
"company_bears"}` — وتكون `company_bears` صحيحة إذا كان وقود المعدة على الشركة («الشركة»). والكرت الذي لا مشروع له أو
لا شهر أو لا سنة أو لا معدة يعيد أصفارًا.

```bash
curl -s -G "https://<your-site>/api/method/card.diesel.get_card_diesel" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "card=<card-name>"
```

## get_supplier_editable

`GET /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable`

هل يتيح نموذج التعبئة للمستخدم الحالي تغيير مورد الديزل. ولا يخرج من الخادم إلا هذا الجواب بنعم أو لا.

**الصلاحية:** قراءة تعبئة ديزل للمشروع. **المعاملات:** لا توجد.

**القيمة المعادة:** `true` إذا لم يُحدد مورد ديزل افتراضي في الإعدادات؛ و`false` إذا كانت سياسة المورد ثابتة («ثابت»)؛
وفي غير ذلك `true` لحامل دور محرر المورد المحدد في الإعدادات (Card Manager افتراضيًا) أو للمسؤول (Administrator) فقط.

```bash
curl -s "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_supplier_editable" \
  -H "Authorization: token <api_key>:<api_secret>"
```

## fill_link_query

`GET /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query`

بحث الربط في نموذج التعبئة لـ**المشروع** و**مركز التكلفة** و**المورد**. فمستخدمو التعبئة لا يملكون صلاحية الاختيار على
هذه السجلات الرئيسية، فيبحث النموذج عبر هذا الاستعلام، ولا يعيد إلا الأسماء والعناوين.

**الصلاحية:** إنشاء أو تعديل تعبئة ديزل للمشروع. ويتطلب المشروع ومركز التكلفة شركةَ النموذج، ويجب أن تكون شركة يحق للمستخدم
رؤيتها في تعبئات الديزل؛ وتنطبق صلاحيات المستخدم الخاصة بتعبئات الديزل؛ والمستخدم الذي لا يحق له تغيير مورد الديزل لا
يحصل إلا على المورد المحدد في الإعدادات.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `doctype` | string | نعم | `Project` أو `Cost Center` أو `Supplier`؛ ويُرفض ما سواها. |
| `txt` | string | نعم | نص البحث (الاسم أو العنوان). |
| `searchfield` | string | نعم | وسيط استعلام الربط القياسي. |
| `start` | int | نعم | الإزاحة. |
| `page_len` | int | نعم | حجم الصفحة. |
| `filters` | object | لا | `{"company": "<company>"}` للمشروع ومركز التكلفة. |

**القيمة المعادة:** قائمة أزواج `[name, title]` (مراكز التكلفة: الطرفية والمفعّلة فقط؛ الموردون: المفعّلون فقط).

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.fill_link_query" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Project" --data-urlencode "txt=" --data-urlencode "searchfield=name" \
  --data-urlencode "start=0" --data-urlencode "page_len=20" \
  --data-urlencode 'filters={"company":"Example Contracting Co."}'
```

## get_diesel_price_context

`GET /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context`

ما يحتاجه نموذج التعبئة قبل الحفظ: سعر الديزل للشركة في تاريخ التعبئة، وهل يحق للمستخدم منح استثناء في السعر أو سعر صفري.

**الصلاحية:** قراءة تعبئة ديزل للمشروع؛ والشركة التي لا يحق للمستخدم رؤيتها تعيد سياقًا فارغًا.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company` | string | لا | شركة التعبئة. |
| `date` | date | لا | تاريخ التعبئة؛ واليوم إذا كان فارغًا. |

**القيمة المعادة:** `{"price": <number>, "can_except": bool, "can_zero": bool, "exception_role": "<role or null>"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.get_diesel_price_context" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co." --data-urlencode "date=2026-01-15"
```

## use_company_price

`POST /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price`

في مسودة محفوظة بلا استثناء سعر، يستبدل السعرَ بسعر الشركة الحالي.

**الصلاحية:** كتابة التعبئة، و**دور استثناء سعر الديزل** المحدد في الإعدادات.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `name` | string | نعم | تعبئة ديزل مسودة. |
| `reason` | string | نعم | سبب تغيير السعر (ويُرفض السبب الفارغ). |

**القيمة المعادة:** `{"unit_price": <number>, "price_source": "<source>"}`. **الآثار الجانبية:** حفظ التعبئة، وتدقيق
التغيير بتعليق على التعبئة يتضمن السبب.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.use_company_price" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"name": "<fill-name>", "reason": "Price entered by mistake"}'
```

## remove_price_exception

`POST /api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception`

ينهي استثناء السعر في مسودة محفوظة، فتعود إلى سعر الشركة الحالي.

**الصلاحية:** كتابة التعبئة، ودور استثناء سعر الديزل.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `name` | string | نعم | تعبئة مسودة عليها استثناء سعر. |
| `reason` | string | نعم | سبب مكتوب. |

**القيمة المعادة:** `{"unit_price", "price_source"}`. **الآثار الجانبية:** إزالة الاستثناء، والحفظ، وتدقيق التغيير.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.project_diesel_fill.project_diesel_fill.remove_price_exception" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"name": "<fill-name>", "reason": "Supplier agreed to the company price"}'
```

## diesel_supplier_options

`GET /api/method/card.diesel_reconciliation.diesel_supplier_options`

خيارات فلتر الموردين في تقرير [مطابقة فواتير الديزل](/card/ar/reports/diesel-fuel/): موردو جلسات الديزل التي يحق للمستخدم
قراءتها، في الشركات التي يحق له رؤيتها في كلٍّ من تعبئة ديزل للمشروع وفواتير الشراء.

**الصلاحية:** أحد أدوار تقارير CARD، وأدوار التقرير نفسه، وصلاحية قراءة بالأدوار على تعبئة ديزل للمشروع وفواتير الشراء.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `txt` | string | لا | نص البحث. |
| `company` | string | لا | قصر النتائج على شركة واحدة. |

**القيمة المعادة:** حتى 50 كائنًا `{"value": "<supplier>", "description": ""}`.

```bash
curl -s -G "https://<your-site>/api/method/card.diesel_reconciliation.diesel_supplier_options" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "company=Example Contracting Co."
```

## ذو صلة

- [الديزل](/card/ar/features/diesel/)
- [تقارير الديزل والوقود](/card/ar/reports/diesel-fuel/)
