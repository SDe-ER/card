---
title: واجهة API للترحيل والمحاسبة
description: نقاط نهاية شاشة الترحيل الشهري، وبناء الفواتير المسودة وإعادة بنائها، وقبول التصحيحات، وربط الفواتير اليدوية وقيود الاستحقاق.
sidebar:
  order: 8
---

## نظرة عامة

لا يكتب Card قيود دفتر الأستاذ أبدًا. فترحيله الشهري يبني **فاتورة ERPNext مسودة واحدة لكل طرف وشهر** — فاتورة شراء للمورد،
وفاتورة مبيعات للعميل — من مصادر الطرف المعتمدة غير المرحّلة (الكروت الشهرية، وتعبئات الديزل، وعمليات النقل)، ويسجّل
الربط في **سجل الترحيل المحاسبي**. ولا تظهر صفوف الدفتر إلا عندما يعتمد شخص الفاتورة في ERPNext. وإذا كان المصدر قد دُفع
بفاتورة يدوية أو اعترف به قيد يومية استحقاق، فإن المحاسب يربطه بدلًا من ذلك، فلا يبنيه Card مرتين أبدًا.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.gl.posting.posting_month_parties` | أطراف الشهر للشركة مع حالة ترحيلها. |
| GET | `card.gl.posting.preview_month` | تشغيل تجريبي للبناء التالي لطرف وشهر. |
| POST | `card.gl.posting.post_month` | بناء الترحيل المسودة لطرف وشهر. |
| POST | `card.gl.posting.rebuild_month` | حذف مسودة Card وبناء الشهر من جديد. |
| POST | `card.gl.integrity.accept_correction` | قبول تصحيح مركز التكلفة / الحساب في مسودة Card. |
| POST | `card.gl.integrity.link_supplier_invoice` | ربط فاتورة شراء يدوية بمصادر Card. |
| POST | `card.gl.integrity.link_customer_invoice` | ربط فاتورة مبيعات يدوية معتمدة بالكروت الشهرية للعميل. |
| POST | `card.gl.integrity.unlink_customer_invoice` | إزالة ربط خاطئ بين فاتورة مبيعات وكروتها الشهرية (System Manager). |
| GET | `card.gl.integrity.unlinked_customer_invoice_candidates` | عرض فواتير المبيعات اليدوية غير المربوطة مع الكروت التي قد تطابقها. |
| GET | `card.gl.integrity.customer_invoice_link_info` | حالة ربط فاتورة مبيعات واحدة والكروت التي قد تفوترها (بيانات أزرار Desk). |
| POST | `card.gl.journal_link.link_accrual_journal` | ربط قيد يومية استحقاق لمورد بكروت Card. |

## قواعد مشتركة لنقاط الترحيل

تتشارك `posting_month_parties` و`preview_month` و`post_month` و`rebuild_month` بوابة واحدة:

- دور **Card Manager** أو **System Manager**.
- يجب أن تكون الشركة مما يحق للمستخدم رؤيته في كروت التشغيل الشهرية وتعبئة ديزل للمشروع ونقل المعدات ونوع فاتورة الجانب
  وسجل الترحيل المحاسبي.
- `party_type` هو `Supplier` أو `Customer`؛ و`month` من 1 إلى 12، و`year` رقم.
- للطرف الواحد، يجب أن يستطيع المستخدم قراءة الطرف (وتنطبق صلاحيات المستخدم على الموردين أو العملاء).

## posting_month_parties

`GET /api/method/card.gl.posting.posting_month_parties`

أطراف شهر الشركة: كل طرف له مصادر معتمدة غير مرحّلة أو سجل ترحيل Card نشط. ولا يُعرض الجانب إلا إذا كان يحق للمستدعي بناء
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

سطور الفاتورة التي سيُنشئها الترحيل التالي (أو إعادة البناء إذا وُجدت مسودة Card). ولا يُدرج شيء ولا يُحفظ ولا يُحجز ولا
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

مصادر متأخرة مقابل ترحيل **مسودة**: يحذف مسودة Card (فيحرر حجوزاتها) ويبني الشهر من جديد، فتشمل المسودة الجديدة كل مستند
معتمد غير مرحّل. والمعاملات والقيمة المعادة كما في `post_month`.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.posting.rebuild_month" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"company": "Example Contracting Co.", "party_type": "Customer", "party": "<customer>", "month": "01", "year": "2026"}'
```

## accept_correction

`POST /api/method/card.gl.integrity.accept_correction`

يقبل مدير الحسابات مركز تكلفة أو حسابًا مصحّحًا في فاتورة Card مسودة. ولا يجوز أن يختلف عما بناه Card إلا هذان الحقلان؛
ويرتبط القبول بمحتوى الفاتورة بعينه، فأي تعديل لاحق يحتاج إلى قبول جديد.

**الصلاحية:** Accounts Manager أو System Manager؛ وكتابة الفاتورة؛ وأن تكون الشركة ضمن نطاق المستخدم في Card والمحاسبة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice_doctype` | string | نعم | `Purchase Invoice` أو `Sales Invoice`. |
| `invoice` | string | نعم | فاتورة مسودة بناها Card. |
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

يسجّل أن فاتورة شراء قائمة لمورد، أُدخلت يدويًا، تدفع بالفعل قيمة مصادر Card هذه. ولا يُعاد ترحيل شيء ولا تتغير الفاتورة:
فسجل ترحيل **مربوط** يحجز المصادر حتى لا يبنيها Card مرة أخرى أبدًا، وتُظهر المصادر الفاتورة بعد اعتمادها. ويجوز أن تمتد
المصادر على عدة أشهر.

**الصلاحية:** Accounts Manager أو Accounts User أو System Manager؛ وقراءة الفاتورة وصلاحية **اعتمادها**؛ وقراءة المورد وكل
مصدر؛ وأن تكون الشركة ضمن نطاق المستخدم في Card والمحاسبة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice` | string | نعم | فاتورة شراء (غير ملغاة، وليست مرتجعًا، وليست ترحيلًا أو ربطًا من Card من قبل). |
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

## link_customer_invoice

`POST /api/method/card.gl.integrity.link_customer_invoice`

يسجّل أن فاتورة مبيعات معتمدة، أُدخلت يدويًا في ERPNext، تفوتر بالفعل هذه الكروت الشهرية للعميل. ولا يُرحَّل شيء ولا تتغير
الفاتورة: فسجل ترحيل **مربوط** يحجز الكروت حتى لا يبنيها Card مرة أخرى أبدًا، ويُظهر كل كرت الفاتورة. ولا يوجد زر في Desk
لهذه الطريقة.

**الصلاحية:** Accounts Manager أو System Manager (ولا يكفي Accounts User)؛ وقراءة الفاتورة وصلاحية **اعتمادها**؛ وقراءة
العميل وكل كرت؛ وأن تكون الشركة ضمن نطاق المستخدم في Card والمحاسبة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice` | string | نعم | فاتورة مبيعات معتمدة بعملة الشركة: غير ملغاة، وليست مرتجعًا (إشعارًا دائنًا)، وليست إشعارًا مدينًا، وليست فاتورة افتتاحية، وليس لها إشعار دائن معتمد، وليست ترحيلًا أو ربطًا من Card من قبل. |
| `cards` | list | نعم | أسماء كروت التشغيل الشهرية، مثل `["<card-name>"]`. كل كرت معتمد، وليس من شهر مفتوح، ويُفوتر لعميل، ومن شركة الفاتورة وعميلها ومشروعها، وليس له فاتورة مبيعات، ولا يحجزه ترحيل آخر لجانب العميل. ولا يتكرر كرت. |
| `reason` | string | نعم | سبب ربط الفاتورة. يُحفظ في السجل وفي التعليقات. |

**قاعدة الإثبات:** يجب أن يساوي صافي الفاتورة (قبل الضريبة) مجموع صافي العميل في الكروت ضمن سماحية المطابقة (إعدادات Card،
0.01 على الأقل)، في الإجمالي ولكل مشروع. ومشروع بند الفاتورة هو المشروع المكتوب في البند؛ والبند الذي ليس فيه مشروع يأخذ
مشروع رأس الفاتورة. ولكل مشروع يجب أن يساوي صافي بنوده صافي العميل في كروت ذلك المشروع المذكورة، ولا يجوز أن يبقى مشروع
في الفاتورة بلا كروت؛ وتُرفض الفاتورة التي ليس فيها مشروع. ويُرفض أي فرق دائمًا؛ وليس في هذه الطريقة `accept_difference`.

**التزامن:** يُقفل صف الفاتورة وصفوف الكروت، وتُقرأ حالتها وروابطها وسجلات الترحيل النشطة مرة أخرى تحت الأقفال قبل إدراج
السجل.

**القيمة المعادة:** اسم سجل الترحيل المحاسبي. **الآثار الجانبية:** إدراج سجل ترحيل واحد مربوط من نوع فاتورة مبيعات فيه صف
مصدر لكل كرت؛ وضبط `sales_invoice` و`posted` و`gl_posting` في كل كرت؛ وإضافة تعليق معلومات واحد على الفاتورة وعلى كل كرت.
ولا تكتب الطريقة أي قيد في الأستاذ العام ولا تحفظ فاتورة المبيعات. ويُرفض الاستدعاء الثاني للفاتورة نفسها ما دام الربط
قائمًا. وللتراجع عن ربط خاطئ انظر [unlink_customer_invoice](#unlink_customer_invoice).

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.link_customer_invoice" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice": "<invoice-name>", "cards": ["<card-name>"], "reason": "Invoice entered in ERPNext before the cards"}'
```

## unlink_customer_invoice

`POST /api/method/card.gl.integrity.unlink_customer_invoice`

تزيل ربطًا خاطئًا أنشأته `link_customer_invoice`. وهي للشركة التي لا تستطيع إلغاء فاتورة مبيعات معتمدة (ZATCA). ولا يُرحَّل شيء
ولا يُلغى ولا يُعدَّل ولا يُحذف: لا تتغير فاتورة المبيعات ولا مبالغ الكروت ولا الدفاتر. ولا يوجد زر في Desk لهذه الطريقة.

**الصلاحية:** System Manager (ولا يكفي Accounts Manager) مع صلاحية قراءة فاتورة المبيعات. ودور System Manager وحده لا يعطي
قراءة فاتورة المبيعات، فيحتاج المستخدم إلى دور محاسبي أيضًا. وكذلك: أن تكون الشركة ضمن نطاق المستخدم في Card والمحاسبة،
وقراءة كل كرت من كروت الربط.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice` | string | نعم | فاتورة مبيعات معتمدة هي مستند الترحيل في سجل ترحيل نشط أصله **مربوط**. |
| `reason` | string | نعم | سبب إزالة الربط. يُحفظ في السجل وفي التعليقات. |

**حالات الرفض:** تُجرى كل الفحوص قبل أول كتابة، فالاستدعاء المرفوض لا يغيّر شيئًا.

- الفاتورة غير معتمدة، أو ليس لها ربط نشط.
- الفاتورة ترحيل بناه Card (الأصل «مبني» أو فارغ) أو إشعار دائن من Card.
- عدم تطابق في سلسلة الإلغاء والتعديل: فاتورة مبيعات أخرى تعدّل هذه الفاتورة، أو فاتورة تعدّلها هذه الفاتورة (صعودًا في
  السلسلة) ما زال لها سجل ترحيل نشط. والتعديل الذي له ربط خاص به يُفك ربطه مثل أي فاتورة أخرى.
- مصدر في السجل ليس كرتًا شهريًا، أو المستخدم لا يستطيع قراءة كرت من كروت الربط.
- كرت تغيّر بعد الربط: غير معتمد، أو ليست عليه علامة «مُرحَّل»، أو قيمة `sales_invoice` فيه ليست هذه الفاتورة، أو قيمة
  `gl_posting` فيه ليست هذا السجل ولا سجل جانب المورد النشط الذي يحجز الكرت (الإيجار من الباطن). وتذكر الرسالة اسم الكرت.

**التزامن:** يُقفل صف الفاتورة ثم صفوف الكروت ثم صف السجل، بترتيب الربط نفسه (الفاتورة ثم الكروت ثم سجلات الترحيل). وتُقرأ
حالة الفاتورة والسجل وحقول الربط في الكروت
تحت الأقفال. أما سلسلة التعديل وسجل جانب المورد لكرت الإيجار من الباطن فتُقرأ قراءة عادية.

**القيمة المعادة:** اسم سجل الترحيل المحاسبي. **الآثار الجانبية:** جعل حالة سجل الترحيل المربوط `Cancelled` ومسح
`posting_key`؛ ويبقى السجل، ويُضاف إلى `remarks` من أزال الربط ومتى والسبب والفاتورة والسجل والكروت بمبالغها. وفي كل كرت:
مسح `sales_invoice`، وجعل `posted` يساوي 0 (ويبقى 1 في كرت الإيجار من الباطن الذي ما زال جانب المورد فيه مرحّلًا بفاتورة شراء أو بقيد يومية استحقاق مربوط)، ومسح
`gl_posting` إذا كان يشير إلى هذا السجل؛ ولا يتغير `modified` في الكرت. وإضافة تعليق معلومات واحد على الفاتورة وعلى كل
كرت. ولا تكتب الطريقة أي قيد في الأستاذ العام ولا تحفظ فاتورة المبيعات. وبعد الاستدعاء تقبل `link_customer_invoice`
الفاتورة والكروت من جديد.

```bash
curl -s -X POST "https://<your-site>/api/method/card.gl.integrity.unlink_customer_invoice" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"invoice": "<invoice-name>", "reason": "The invoice was linked to the cards of another month"}'
```

## unlinked_customer_invoice_candidates

`GET /api/method/card.gl.integrity.unlinked_customer_invoice_candidates`

للقراءة فقط. لكل عميل له كروت تُفوتر لعميل في الشركة، تعرض الطريقة فواتير المبيعات المعتمدة التي لم يبنها Card وليس لها ربط
(لا يوجد لها سجل ترحيل نشط)، الأحدث أولًا. وتُستبعد المرتجعات والإشعارات المدينة والفواتير الافتتاحية والفواتير التي لها إشعار
دائن معتمد والفواتير التي بعملة غير عملة الشركة. وتعرض مع كل فاتورة كروت العميل التي ما زال ربطها ممكنًا والتي تخص مشروعًا من مشاريع الفاتورة (100 كرت على
الأكثر؛ وتكون `more_cards` صحيحة إذا وُجد أكثر).

**الصلاحية:** Accounts Manager أو System Manager؛ وقراءة فواتير المبيعات وكروت التشغيل الشهرية؛ وأن تكون الشركة ضمن نطاق
المستخدم في Card والمحاسبة. وتُستبعد الفواتير والكروت التي لا يستطيع المستخدم قراءتها.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company` | string | نعم | الشركة. |
| `limit_start` | int | لا | أول فاتورة في الصفحة (الافتراضي 0). |
| `limit_page_length` | int | لا | عدد الفواتير في الاستدعاء (الافتراضي 50، والحد الأقصى 200). |

**قاعدة المطابقة:** تُختبر مجموعتان من الكروت بقاعدة الإثبات في `link_customer_invoice` (صافي الفاتورة، في الإجمالي ولكل
مشروع، ضمن سماحية المطابقة): كروت شهر الفاتورة والشهر الذي قبله، ثم كل الكروت التي ما زال ربطها ممكنًا في مشاريع الفاتورة.
وتكون `match` هي `exact` إذا غطّت إحدى المجموعتين الفاتورة، وتكون `cards` عندئذ هي تلك المجموعة. ولا يُختبر أي تركيب آخر:
فالقيمة `none` لا تثبت أنه لا يوجد تركيب مطابق.

**القيمة المعادة:** `{"invoices": [{"invoice", "posting_date", "customer", "projects": [...], "net_total", "cards": [{"name",
"month", "year", "project", "customer_net_amount"}], "more_cards", "match": "exact"|"none", "note"}], "limit_start",
"limit_page_length", "has_more"}`. **الآثار الجانبية:** لا شيء.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.integrity.unlinked_customer_invoice_candidates" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "company=Example Contracting Co."
```

## customer_invoice_link_info

`GET /api/method/card.gl.integrity.customer_invoice_link_info`

للقراءة فقط. بيانات زرَّي **ربط بالكروت الشهرية** و**إلغاء الربط بالكروت الشهرية** في نموذج فاتورة المبيعات. تقول لفاتورة
واحدة إن كان سجل ترحيل نشط يحتجزها. وإن كان، تعيد السجل ومصدره (`Linked` أو `Built`) وكروته. وإن لم يكن، وقبل الربط الفاتورة
(معتمدة، وليست مرتجعًا ولا إشعارًا مدينًا ولا فاتورة افتتاحية، وبعملة الشركة، وليس لها إشعار دائن معتمد)، تعيد `card_count`، وهو
عدد الكروت المعتمدة غير المربوطة لعميل الفاتورة على مشاريعها. ومع `with_cards` تعرضها أيضًا، الأحدث شهرًا أولًا، 100 كرت
على الأكثر (وتكون `more_cards` صحيحة إذا كان `card_count` أكبر).

**الصلاحية:** Accounts Manager أو System Manager؛ وقراءة فاتورة المبيعات وكروت التشغيل الشهرية؛ وأن تكون شركة الفاتورة ضمن
نطاق المستخدم في Card والمحاسبة. وهي بوابات قائمة الفواتير المرشحة نفسها.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `invoice` | string | نعم | اسم فاتورة المبيعات. |
| `with_cards` | int | لا | 1 لعرض الكروت المرشحة (الافتراضي 0: `card_count` فقط). |

**القيمة المعادة:** `{"invoice", "eligible", "linked", "log", "origin", "net_total", "card_count", "cards": [{"name", "month", "year",
"project", "customer_net_amount"}], "more_cards", "linked_cards": [...]}`. **الآثار الجانبية:** لا شيء.

```bash
curl -s -G "https://<your-site>/api/method/card.gl.integrity.customer_invoice_link_info"   -H "Authorization: token <api_key>:<api_secret>"   --data-urlencode "invoice=<invoice-name>"
```

## link_accrual_journal

`POST /api/method/card.gl.journal_link.link_accrual_journal`

يسجّل أن قيد يومية استحقاق معتمدًا لمورد قد اعترف بالفعل بهذه الكروت الشهرية المعتمدة للمورد. ولا يُرحَّل شيء ولا يُنشأ ولا
يُغيَّر في ERPNext. وإلغاء قيد اليومية لاحقًا يحرر الكروت من جديد.

**الصلاحية:** Accounts Manager أو Accounts User أو System Manager؛ وقراءة قيد اليومية وصلاحية اعتماده؛ وقراءة المورد وكل
كرت؛ وأن تكون الشركة ضمن نطاق المستخدم في Card والمحاسبة.

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
