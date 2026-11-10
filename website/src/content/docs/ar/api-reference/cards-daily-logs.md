---
title: واجهة API للكروت واليوميات
description: نقاط نهاية نموذج الكرت الشهري، وإنشاء الكروت المسودة من اليوميات، والإلغاء مع السبب، وبطاقات الأرقام والرسم البياني في مساحة العمل.
sidebar:
  order: 3
---

## نظرة عامة

تُقرأ الكروت الشهرية واليوميات وتُكتب بواجهة الموارد القياسية (`/api/resource/Card Monthly Card` و
`/api/resource/Card Daily Log`)، وتُطبَّق كل القواعد عند الحفظ والاعتماد والإلغاء أيًّا كان المسار. وتضيف نقاط النهاية
أدناه ما تحتاجه النماذج ومساحة العمل: سياق الكرت، وإنشاء الكروت المسودة من اليوميات المعتمدة، وإجراء الإلغاء مع السبب،
وأرقام لوحة المعلومات.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.card.doctype.card_monthly_card.card_monthly_card.get_card_context` | مشاريع المعدة وأيامها في شهر. |
| POST | `card.daily_log_generation.generate_monthly_cards` | إنشاء الكروت المسودة أو تحديثها من اليوميات المعتمدة. |
| POST | `card.cancel_reason.cancel_with_reason` | إلغاء معاملة CARD وتخزين السبب. |
| POST | `card.card_value.supplier_cost_last_month` | بطاقة رقم: تكلفة إيجار الموردين للشهر الماضي. |
| POST | `card.card_value.customer_value_last_month` | بطاقة رقم: قيمة التشغيل للعملاء للشهر الماضي. |
| POST | `card.card_value.internal_value_last_month` | بطاقة رقم: قيمة التشغيل الداخلية للشهر الماضي. |
| POST | `card.card_value.cards_without_internal_rate_last_month` | بطاقة رقم: كروت المعدات الملك التي بلا سعر داخلي. |
| POST | `card.card_value.hours_without_internal_rate_last_month` | بطاقة رقم: ساعات تلك الكروت. |
| POST | `card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get` | مصدر الرسم البياني «Card Monthly Values». |

## get_card_context

`GET /api/method/card.card.doctype.card_monthly_card.card_monthly_card.get_card_context`

ما يملؤه نموذج الكرت بعد اختيار المعدة والشهر والسنة: المشاريع التي وضعت عمليات النقل المعتمدة المعدة عليها في ذلك الشهر،
والأيام التي كانت فيها على المشروع المختار (أو الوحيد). وفي الوحدة لا يُحتسب اليوم إلا إذا كانت كل قطعة في الوحدة على
المشروع، ولا تُعرض أيام القطعة الواقعة ضمن فترة وجودها في وحدة. للقراءة فقط.

**الصلاحية:** قراءة المعدة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `equipment` | string | نعم | اسم المعدة. |
| `month` | string | نعم | رقم الشهر، مثل `01`. |
| `year` | string | نعم | السنة، مثل `2026`. |
| `project` | string | لا | المشروع؛ وإذا كان فارغًا ووُجد مشروع واحد استُخدم. |

**القيمة المعادة:** `{"projects": [...], "project": "<project or null>", "days": ["2026-01-01", ...]}`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.card_monthly_card.card_monthly_card.get_card_context" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "equipment=EQ-0001" --data-urlencode "month=01" --data-urlencode "year=2026"
```

## generate_monthly_cards

`POST /api/method/card.daily_log_generation.generate_monthly_cards`

يُنشئ أو يحدّث الكروت الشهرية **المسودة** للوردية النهارية والليلية لشركة ومشروع وشهر (ومعدة واحدة اختياريًا) من
اليوميات **المعتمدة**. ولا يعتمد أي كرت أبدًا ولا يغيّر كرتًا معتمدًا.

**الصلاحية:** إنشاء كروت التشغيل الشهرية لتلك الشركة والمشروع، وقراءة اليوميات؛ ومع `equipment` قراءة تلك المعدة التي يجب
أن تتبع الشركة. ويجب أن يتبع المشروع الشركة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company` | string | نعم | الشركة. |
| `project` | string | نعم | مشروع تابع للشركة. |
| `month` | string | نعم | `YYYY-MM` أو أي تاريخ في الشهر. |
| `equipment` | string | لا | قصر العملية على معدة واحدة. |

**القيمة المعادة:** كائن من القوائم: `created` و`updated` و`unchanged` و`kept_submitted` و`overwritten_days`
و`cleared_days` و`skipped_days` و`conflicts` (معدة غيّرتها عملية أخرى في الوقت نفسه — أعد التشغيل) و`errors` (لكل معدة
ووردية مع رسالة التحقق، وتستمر بقية المعدات).

**الآثار الجانبية:** إدراج كروت شهرية مسودة أو حفظها. وتُرتَّب العمليات على المعدة نفسها بقفل على الصف.

```bash
curl -s -X POST "https://<your-site>/api/method/card.daily_log_generation.generate_monthly_cards" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "project": "PROJ-0001", "month": "2026-01"}'
```

## cancel_with_reason

`POST /api/method/card.cancel_reason.cancel_with_reason`

زر **الإلغاء** في النموذج: يخزّن سبب الإلغاء ويلغي المستند المخزّن في طلب واحد. وإذا رُفض الإلغاء أُلغي حفظ السبب معه.
ويُخزن السبب نصًا عاديًا.

**الصلاحية:** صلاحية الإلغاء في Frappe على المستند، وعزل الشركة الخاص بنوع المستند.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `doctype` | string | نعم | `Card Monthly Card` أو `Equipment Transport` أو `Project Diesel Fill`؛ ويُرفض ما سواها. |
| `name` | string | نعم | اسم المستند. |
| `reason` | string | لا | سبب الإلغاء (وتحدد قواعد نوع المستند ما إذا كان إلزاميًا). |

**القيمة المعادة:** `{"name": "<name>", "docstatus": 2}`. **الآثار الجانبية:** تعيين `cancel_reason` وإلغاء المستند.

```bash
curl -s -X POST "https://<your-site>/api/method/card.cancel_reason.cancel_with_reason" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"doctype": "Card Monthly Card", "name": "<card-name>", "reason": "Wrong project"}'
```

## بطاقات أرقام الشهر الماضي

تغذّي الدوال الخمس `card.card_value.*_last_month` **بطاقات الأرقام** (Number Cards) في مساحة العمل. وعنصر بطاقة الرقم في
Frappe يستدعي دائمًا بطريقة `POST`، لذا تقبل هذه الدوال — وهي قراءة بلا آثار جانبية — طريقة `POST` فقط. وتجمع الكروت
الشهرية التي تبدأ فترتها في الشهر التقويمي السابق.

**الصلاحية:** قراءة كروت التشغيل الشهرية (ولا يُحتسب إلا ما يحق للمستخدم قراءته). وتحتاج القيم الداخلية إلى صلاحية قراءة
حقول السعر الداخلي في المعدات، ودونها تكون الأرقام الداخلية `null`.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `filters` | object | لا | `{"company": "<company>", "include_drafts": 0}`؛ وقيمة `include_drafts` هي `0` أو `1`. |

**القيمة المعادة:** `{"value": <number or null>, "fieldtype": "Currency"|"Int"|"Float", "route": ["List", "Card Monthly Card"],
"route_options": {...}}` — ويفتح المسار قائمة الكروت التي وراء الرقم.

| الدالة | القيمة |
|---|---|
| `supplier_cost_last_month` | تكلفة إيجار الموردين (Currency). |
| `customer_value_last_month` | قيمة التشغيل للعملاء (Currency). |
| `internal_value_last_month` | قيمة التشغيل الداخلية للمعدات الملك (Currency). |
| `cards_without_internal_rate_last_month` | الكروت التي ليس لمعدتها سعر داخلي (Int). |
| `hours_without_internal_rate_last_month` | ساعات تلك الكروت (Float). |

```bash
curl -s -X POST "https://<your-site>/api/method/card.card_value.supplier_cost_last_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"filters": {"company": "Example Contracting Co."}}'
```

## مصدر الرسم البياني Card Monthly Values

`POST /api/method/card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get`

قيمة كل كرت شهري لكل فترة في ثلاث سلاسل: تكلفة إيجار الموردين، وقيمة التشغيل للعملاء، وقيمة التشغيل الداخلية. للقراءة
فقط، ودون تخزين مؤقت، فلا تُقدَّم إجماليات مستخدم لشركة أخرى أبدًا.

**الصلاحية:** قراءة الرسم البياني (Dashboard Chart) عند تمرير `chart_name`، وقراءة كروت التشغيل الشهرية.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `chart_name` | string | لا | سجل رسم بياني يستخدم هذا المصدر. |
| `chart` | object | لا | إعدادات الرسم عند عدم تمرير `chart_name`. |
| `filters` | object | لا | `{"company": ..., "include_drafts": ...}`؛ والافتراضي فلاتر الرسم. |
| `from_date`، `to_date` | date | لا | للمدى الزمني «Select Date Range». |
| `timespan` | string | لا | الافتراضي من الرسم، وإلا «Last Year». |
| `time_interval` | string | لا | الافتراضي من الرسم، وإلا «Monthly». |
| `no_cache`، `heatmap_year`، `refresh` | — | لا | تُقبل للتوافق مع عنصر الرسم، ولا تُستخدم. |

**القيمة المعادة:** `{"labels": [...], "datasets": [{"name": "<series label>", "values": [...]}, ...]}`. ولا تُضمَّن
السلسلة الداخلية إلا للمستخدمين الذين يحق لهم قراءة حقول السعر الداخلي في المعدات.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"chart": {"timespan": "Last Year", "time_interval": "Monthly"}, "filters": {"company": "Example Contracting Co."}}'
```

## ذو صلة

- [الكروت الشهرية](/card/ar/features/monthly-cards/)
- [اليوميات](/card/ar/features/daily-logs/)
- [مساحة العمل ولوحة المعلومات](/card/ar/features/workspace-dashboard/)
