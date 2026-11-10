---
title: واجهة API للترحيل والمحاسبة
description: نقاط نهاية شاشة الترحيل الشهري، وبناء الفواتير المسودة وإعادة بنائها، وقبول التصحيحات، وربط الفواتير اليدوية وقيود الاستحقاق.
sidebar:
  order: 8
---

## نظرة عامة

لا يكتب CARD قيود دفتر الأستاذ أبدًا. فترحيله الشهري يبني **فاتورة ERPNext مسودة واحدة لكل طرف وشهر** — فاتورة شراء للمورد،
وفاتورة مبيعات للعميل — من مصادر الطرف المعتمدة غير المرحّلة (الكروت الشهرية، وتعبئات الديزل، وعمليات النقل)، ويسجّل
الربط في **سجل الترحيل المحاسبي**. ولا تظهر صفوف الدفتر إلا عندما يعتمد شخص الفاتورة في ERPNext. وإذا كان المصدر قد دُفع
بفاتورة يدوية أو اعترف به قيد يومية استحقاق، فإن المحاسب يربطه بدلًا من ذلك، فلا يبنيه CARD مرتين أبدًا.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.gl.posting.posting_month_parties` | أطراف الشهر للشركة مع حالة ترحيلها. |
| GET | `card.gl.posting.preview_month` | تشغيل تجريبي للبناء التالي لطرف وشهر. |
| POST | `card.gl.posting.post_month` | بناء الترحيل المسودة لطرف وشهر. |
| POST | `card.gl.posting.rebuild_month` | حذف مسودة CARD وبناء الشهر من جديد. |
| POST | `card.gl.integrity.accept_correction` | قبول تصحيح مركز التكلفة / الحساب في مسودة CARD. |
| POST | `card.gl.integrity.link_supplier_invoice` | ربط فاتورة شراء يدوية بمصادر CARD. |
| POST | `card.gl.journal_link.link_accrual_journal` | ربط قيد يومية استحقاق لمورد بكروت CARD. |

## قواعد مشتركة لنقاط الترحيل

تتشارك `posting_month_parties` و`preview_month` و`post_month` و`rebuild_month` بوابة واحدة:

- دور **Card Manager** أو **System Manager**.
- يجب أن تكون الشركة مما يحق للمستخدم رؤيته في كروت التشغيل الشهرية وتعبئة ديزل للمشروع ونقل المعدات ونوع فاتورة الجانب
  وسجل الترحيل المحاسبي.
- `party_type` هو `Supplier` أو `Customer`؛ و`month` من 1 إلى 12، و`year` رقم.
- للطرف الواحد، يجب أن يستطيع المستخدم قراءة الطرف (وتنطبق صلاحيات المستخدم على الموردين أو العملاء).

## posting_month_parties

`GET /api/method/card.gl.posting.posting_month_parties`

أطراف شهر الشركة: كل طرف له مصادر معتمدة غير مرحّلة أو سجل ترحيل CARD نشط. ولا يُعرض الجانب إلا إذا كان يحق للمستدعي بناء
ترحيلاته، ويُستبعد الأطراف الذين لا يستطيع المستدعي قراءتهم.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company` | string | نعم | الشركة. |
| `month` | string | نعم | رقم الشهر. |
| `year` | string | نعم | السنة. |

**القيمة المعادة:** قائمة `{"party_type", "party", "party_name", "pending_sources", "status": "Not posted"|"Draft"|"Posted",
"postings": [{"log", "status", "origin": "Built"|"Linked", "posting_doctype", "posting_doc", "amount"}]}`.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.posting.posting_month_parties" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co." --data-urlencode "month=01" --data-urlencode "year=2026"
```

## preview_month

`GET /api/method/card.gl.posting.preview_month`

سطور الفاتورة التي سيُنشئها الترحيل التالي (أو إعادة البناء إذا وُجدت مسودة CARD). ولا يُدرج شيء ولا يُحفظ ولا يُحجز ولا
يُسجَّل.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company` | string | نعم | الشركة. |
| `party_type` | string | نعم | `Supplier` أو `Customer`. |
| `party` | string | نعم | المورد أو العميل. |
| `month`، `year` | string | نعم | الفترة. |

**القيمة المعادة:** كائن يضم `company` و`party_type` و`party` و`party_name` و`month` و`year` و`posting_doctype` و`mode`
(`post` أو `rebuild`) و`replaces` (المسودات التي تحذفها إعادة البناء) و`currency` و`posting_date` و`sequence` و`lines` و
`discount` و`net_total` و`taxable_net` و`zero_rated_net` و`vat_registered` و`tax_template` و`vat_rate` و`vat_estimate`
(تقدير، إذ يحسب ERPNext الضرائب) و`diesel_note` و`sources` (`doctype` و`name` و`amount`) و`review_invoices` (فواتير
الموردين التي يجب أن يراجعها المحاسب أولًا، المقروءة منها فقط) و`hidden_review_invoices` و`can_review` و`warnings`، و
`blocked` — وهي رسالة أداة البناء نفسها إذا كان البناء سيُرفض.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.posting.preview_month" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co." --data-urlencode "party_type=Supplier" \
  --data-urlencode "party=Supplier A" --data-urlencode "month=01" --data-urlencode "year=2026"
```

## post_month

`POST /api/method/card.gl.posting.post_month`

يُنشئ ترحيلًا **مسودة واحدًا** (فاتورة شراء للمورد، وفاتورة مبيعات للعميل) لمصادر الطرف المعتمدة غير المرحّلة في ذلك الشهر.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company`، `party_type`، `party`، `month`، `year` | string | نعم | كما سبق. |
| `reviewed_invoices` | list | لا | فواتير موردين في الشهر أعلن المحاسب أنها لا علاقة لها بهذه المصادر. |

**القيمة المعادة:** اسم الفاتورة المسودة. **الآثار الجانبية:** إدراج الفاتورة المسودة وسجل ترحيلها، وحجز المصادر. ويُرفض
الطلب ما دامت فواتير موردين قائمة في الشهر لم تُراجع، أو عند نقص الإعدادات (الحسابات، أو قالب الضريبة، أو أساس الضريبة).

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.posting.post_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "party_type": "Supplier", "party": "Supplier A", "month": "01", "year": "2026"}'
```

## rebuild_month

`POST /api/method/card.gl.posting.rebuild_month`

مصادر متأخرة مقابل ترحيل **مسودة**: يحذف مسودة CARD (فيحرر حجوزاتها) ويبني الشهر من جديد، فتشمل المسودة الجديدة كل مستند
معتمد غير مرحّل. والمعاملات والقيمة المعادة كما في `post_month`.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.posting.rebuild_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "party_type": "Customer", "party": "<customer>", "month": "01", "year": "2026"}'
```

## accept_correction

`POST /api/method/card.gl.integrity.accept_correction`

يقبل مدير الحسابات مركز تكلفة أو حسابًا مصحّحًا في فاتورة CARD مسودة. ولا يجوز أن يختلف عما بناه CARD إلا هذان الحقلان؛
ويرتبط القبول بمحتوى الفاتورة بعينه، فأي تعديل لاحق يحتاج إلى قبول جديد.

**الصلاحية:** Accounts Manager أو System Manager؛ وكتابة الفاتورة؛ وأن تكون الشركة ضمن نطاق المستخدم في CARD والمحاسبة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice_doctype` | string | نعم | `Purchase Invoice` أو `Sales Invoice`. |
| `invoice` | string | نعم | فاتورة مسودة بناها CARD. |
| `reason` | string | نعم | سبب التصحيح. |

**القيمة المعادة:** اسم سجل الترحيل المحاسبي. **الآثار الجانبية:** تخزين بصمة المحتوى المقبول، والمستخدم القابل، والسبب في
السجل.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.accept_correction" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice_doctype": "Purchase Invoice", "invoice": "<invoice-name>", "reason": "Project cost center corrected"}'
```

## link_supplier_invoice

`POST /api/method/card.gl.integrity.link_supplier_invoice`

يسجّل أن فاتورة شراء قائمة لمورد، أُدخلت يدويًا، تدفع بالفعل قيمة مصادر CARD هذه. ولا يُعاد ترحيل شيء ولا تتغير الفاتورة:
فسجل ترحيل **مربوط** يحجز المصادر حتى لا يبنيها CARD مرة أخرى أبدًا، وتُظهر المصادر الفاتورة بعد اعتمادها. ويجوز أن تمتد
المصادر على عدة أشهر.

**الصلاحية:** Accounts Manager أو Accounts User أو System Manager؛ وقراءة الفاتورة وصلاحية **اعتمادها**؛ وقراءة المورد وكل
مصدر؛ وأن تكون الشركة ضمن نطاق المستخدم في CARD والمحاسبة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice` | string | نعم | فاتورة شراء (غير ملغاة، وليست مرتجعًا، وليست ترحيلًا أو ربطًا من CARD من قبل). |
| `sources` | list | نعم | `[{"doctype": "Card Monthly Card", "name": "..."}]`، حيث `doctype` هو `Card Monthly Card` أو `Project Diesel Fill` أو `Equipment Transport`؛ معتمدة، ومن شركة الفاتورة ومورّدها. |
| `reason` | string | مع وجود فرق | سبب قبول الفرق. |
| `accept_difference` | int | لا | ‏`1` لقبول فرق بين المصادر وصافي الفاتورة. |

**قاعدة الإثبات:** تُقارَن المصادر بصافي الفاتورة على أساس واحد (الكروت وعمليات النقل بصافيها؛ والتعبئات حسب أساس ضريبة سعر
الديزل). ويُرفض الفرق، أو الأساس الذي لا يمكن التحقق منه، ما لم يُقبل مع سبب؛ وعندئذ يُخزن في السجل فرقًا مفتوحًا، ولا يُعرض
أبدًا على أنه مطابق. وجلسة الديزل المستوردة التي تحمل رقم فاتورة المورد لا تُربط إلا بالفاتورة التي تحمل ذلك الرقم.

**القيمة المعادة:** اسم سجل الترحيل المحاسبي.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.link_supplier_invoice" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice": "<invoice-name>", "sources": [{"doctype": "Card Monthly Card", "name": "<card-name>"}]}'
```

## link_accrual_journal

`POST /api/method/card.gl.journal_link.link_accrual_journal`

يسجّل أن قيد يومية استحقاق معتمدًا لمورد قد اعترف بالفعل بهذه الكروت الشهرية المعتمدة للمورد. ولا يُرحَّل شيء ولا يُنشأ ولا
يُغيَّر في ERPNext. وإلغاء قيد اليومية لاحقًا يحرر الكروت من جديد.

**الصلاحية:** Accounts Manager أو Accounts User أو System Manager؛ وقراءة قيد اليومية وصلاحية اعتماده؛ وقراءة المورد وكل
كرت؛ وأن تكون الشركة ضمن نطاق المستخدم في CARD والمحاسبة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `journal_entry` | string | نعم | قيد يومية عادي معتمد (ليس افتتاحيًا ولا إشعار مدين أو دائن) يقيّد في الدائن لمورد واحد بالضبط، دون صف طرف مقابل مستند آخر. |
| `cards` | list | نعم | كروت معتمدة في جانب المورد، من الشركة والمورد نفسيهما، غير مفوترة وغير محجوزة في ترحيل آخر، دون تكرار. |
| `reason` | string | مع وجود فرق | سبب قبول الفرق. |
| `accept_difference` | int | لا | ‏`1` لقبول الفرق. |

**قاعدة الإثبات:** يجب أن يساوي المبلغُ الدائن للمورد، مطروحًا منه صفوف الضريبة في القيد، صافيَ الكروت في حدود المطابقة
المسموح بها (من الإعدادات، و0.01 على الأقل)؛ ويُرفض الفرق ما لم يُقبل مع سبب، وعندئذ يُخزن في السجل.

**القيمة المعادة:** اسم سجل الترحيل المحاسبي. **الآثار الجانبية:** إدراج سجل ترحيل مربوط من نوع قيد يومية يسرد الكروت،
وتعليم كل كرت بأنه مُرحَّل.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.journal_link.link_accrual_journal" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"journal_entry": "<journal-entry>", "cards": ["<card-1>", "<card-2>"]}'
```

## ذو صلة

- [الفوترة والترحيل](/card/ar/features/invoicing-posting/)
- [تقارير الرقابة المحاسبية](/card/ar/reports/accounting-control/)
- [حالة تسوية الكروت](/card/ar/reports/parties-statements/)
