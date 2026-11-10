---
title: واجهة API للمواد والاحتياجات
description: نقاط نهاية طلبات المشغّلين، ومراجعات المشرفين، واعتماد الإدارة، وتسليم الأدوات، وشاشة عهدة الأدوات.
sidebar:
  order: 6
---

## نظرة عامة

تمر احتياجات المعدات بثلاث خطوات: يطلب المشغّل قطع غيار أو أدوات لمعدته (**طلب احتياجات معدة**)، ويجمع المشرف طلبات
المشروع (**مراجعة احتياجات المعدات**)، وتعتمد الإدارة المراجعة فتتحول إلى طلبات مواد في ERPNext مسودة وتسليمات أدوات
مسودة. ثم تسجّل عهدة الأدوات (**عهدة أدوات الموظف**) كل تسليم وإرجاع وتحويل، ويؤكدها جانب المخزن. وتشغّل نقاط النهاية
أدناه صفحة المشغّل ونموذج المراجعة وشاشة عهدة الأدوات؛ وكل عملية كتابة تمر عبر صلاحيات المستخدم نفسه.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.materials.get_portal_context` | معدات المشغّل وطلباته الأخيرة. |
| GET | `card.materials.search_items` | الأصناف التي يمكن للمشغّل اختيارها (20 على الأكثر). |
| POST | `card.materials.submit_needs` | اعتماد طلب المشغّل لإحدى معداته. |
| GET | `card.materials.review_stock` | مؤشر المخزون المباشر لكل سطر مراجعة. |
| POST | `card.materials.pull_requests` | إضافة سطور الطلبات المعلّقة للمشروع إلى مراجعة مسودة. |
| POST | `card.materials.approve_review` | اعتماد مراجعة معتمدة إلى طلبات مواد وتسليمات مسودة. |
| POST | `card.materials.close_tool_handover` | إغلاق تسليم منتظر لم يستلم العامل أداته. |
| POST | `card.materials.make_tool_handover` | إعداد مسودة تسليم بديلة لسطر أدوات معتمد. |
| GET | `card.tool_custody.context` | تبويبات شاشة عهدة الأدوات وتبويبها الافتراضي وأزرارها. |
| GET | `card.tool_custody.view` | صفحة واحدة من تبويب في الشاشة (المنتظرة، في العهدة، السجل). |
| GET | `card.tool_custody.employee_query` | استعلام ربط: الموظفون في الشاشة. |
| GET | `card.tool_custody.employee_company` | شركة موظف يمكن للشاشة عرضه. |
| GET | `card.tool_custody.store_query` | استعلام ربط: المخازن (المستودعات). |
| GET | `card.tool_custody.item_query` | استعلام ربط: الأدوات المخزنية. |
| POST | `card.tool_custody.move` | حركة مسودة جديدة (تسليم، إرجاع، تحويل). |
| POST | `card.tool_custody.confirm` | تأكيد (اعتماد) حركة منتظرة. |

## الأدوار المستخدمة في هذه الصفحة

| مجموعة الأدوار | الأدوار |
|---|---|
| أدوار البوابة (صفحة المشغّل وطلبات CARD Mobile) | Card Operator، Card Supervisor، Card Manager، System Manager |
| المعتمدون | Card Manager، System Manager |
| شاشة عهدة الأدوات | Card Supervisor، Card Manager، Stock Manager، System Manager (مع قراءة عهدة أدوات الموظف) |
| جانب المخزن | المستخدمون الذين يحق لهم اعتماد عهدة أدوات الموظف وقيود المخزون معًا |

## get_portal_context

`GET /api/method/card.materials.get_portal_context` — **الصلاحية:** أحد أدوار البوابة. **المعاملات:** لا توجد.

**القيمة المعادة:** `{"employee": "<employee or null>", "allowed": bool, "machines": [{"name", "equipment_name", "project"}],
"requests": [...]}` — وهي أحدث 20 طلبًا للمشغّل، ولكل منها `items` (النوع، ورمز الصنف، والوصف، والكمية).

```bash
curl -s "https://<your-site>/api/method/card.materials.get_portal_context" -H "Authorization: token <api_key>:<api_secret>"
```

## search_items

`GET /api/method/card.materials.search_items` — **الصلاحية:** أحد أدوار البوابة.

الأصناف حسب الرمز أو الاسم أو الباركود أو رقم القطعة الأصلي (OEM)، بقواعد بحث الكتالوج وصلاحيات المستخدم نفسها. والمشغّلون
لا يملكون صلاحية قراءة الأصناف، وهذا هو الاستثناء الوحيد المقصود.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `txt` | string | لا | نص البحث (يُستخدم منه 140 حرفًا على الأكثر). |

**القيمة المعادة:** حتى 20 كائنًا `{"item_code", "item_name", "stock_uom"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.materials.search_items" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "txt=filter"
```

## submit_needs

`POST /api/method/card.materials.submit_needs` — **الصلاحية:** أحد أدوار البوابة، وحساب مرتبط بموظف.

يُنشئ طلب احتياجات المشغّل نفسه لإحدى معداته ويعتمده، بتاريخ اليوم.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `equipment` | string | نعم | معدة المشغّل. |
| `items` | list | نعم | الصفوف: `kind` (`Part` أو `Tool`)، و`item_code` (اختياري)، و`description` (140 حرفًا)، و`qty`، و`reason` (140 حرفًا)، و`fit_reason` (500 حرف). |
| `notes` | string | لا | ملاحظات الطلب. |

**القيمة المعادة:** اسم الطلب. **الآثار الجانبية:** إدراج الطلب واعتماده، مع تطبيق التحقق الخاص به (معدة المشغّل، وفحص
التكرار، والتوافق).

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.submit_needs" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"equipment": "EQ-0001", "items": [{"kind": "Part", "item_code": "<item-code>", "qty": 2, "reason": "Worn"}]}'
```

## review_stock

`GET /api/method/card.materials.review_stock` — **الصلاحية:** قراءة المراجعة.

مؤشر المخزون لكل سطر مراجعة، يُقرأ مباشرة بصلاحيات القارئ ولا يُخزّن في المراجعة أبدًا.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `review` | string | نعم | اسم مراجعة احتياجات المعدات. |

**القيمة المعادة:** `{<review line name>: <quantity or null>}`؛ و`{}` للمستخدم الذي لا يحق له قراءة المخزون. والسطر الذي
لا صنف له، أو الواقع في مستودع لا يحق للقارئ رؤيته، لا مؤشر له.

```bash
curl -s -G "https://<your-site>/api/method/card.materials.review_stock" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "review=<review-name>"
```

## pull_requests

`POST /api/method/card.materials.pull_requests` — **الصلاحية:** كتابة المراجعة، ويجب أن تكون مسودة.

يضيف كل سطر طلب معتمد ومعلّق لمشروع المراجعة (ضمن تواريخها إن وُجدت) لا تحجزه مراجعة أخرى. وتُنسخ الكميات المطلوبة ولا
تُعدَّل أبدًا؛ وتبدأ الكمية المعتمدة مساويةً للمطلوبة، ويكون المسار «From store» (من المخزن) مع مستودع المخزن الخاص
بالشركة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `review` | string | نعم | مراجعة احتياجات مسودة. |

**القيمة المعادة:** عدد السطور المضافة. **الآثار الجانبية:** حفظ المراجعة.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.pull_requests" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"review": "<review-name>"}'
```

## approve_review

`POST /api/method/card.materials.approve_review`

اعتماد الإدارة لمراجعة معتمدة. فيدخل كل سطر معتمد في **مسودة** طلب مواد في ERPNext (شراء لسطور «Buy for project»، وصرف
مواد لقطع الغيار من المخزن) مع الصنف والمشروع ومركز التكلفة وبُعد المعدة في صفوف قطع الغيار. ويحصل كل سطر أدوات معتمد على
**مسودة** تسليم عهدة لعامله. والاعتماد لا يحرّك أي مخزون ولا يعطي أحدًا أداة.

**الصلاحية:** Card Manager أو System Manager؛ وإنشاء طلبات المواد (مثل Stock User)؛ وإنشاء عهدة أدوات الموظف إذا كانت في
المراجعة أدوات؛ وقراءة المراجعة. **الفصل بين المهام:** لا يحق لأي شخص راجع المراجعة أو عدّلها أو اعتمدها أن يعتمدها
إداريًا — ولا يُستثنى أي دور.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `review` | string | نعم | مراجعة احتياجات معتمدة لم يجرِ اعتمادها إداريًا بعد. |

**القيمة المعادة:** قائمة طلبات المواد المُنشأة. **الآثار الجانبية:** إدراج طلبات مواد وتسليمات مسودة، وجعل المراجعة
معتمدة مع اسم المعتمد ووقته، وتعليم كل طلب بأنه معتمد أو مرفوض. ويُرفض الطلب إذا كان في سطرٍ نقصٌ في الصنف أو المستودع، أو
كانت الأداة صنفًا غير مخزني أو أصلًا ثابتًا، أو لم يذكر سطرُ أدواتٍ عاملًا، أو لم يُحدد مخزن عهدة الأدوات في الإعدادات.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.approve_review" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"review": "<review-name>"}'
```

## close_tool_handover

`POST /api/method/card.materials.close_tool_handover`

لم يستلم العامل الأداة: تُغلق مسودة التسليم المنتظرة مع سبب، ولا تُعتمد أبدًا؛ فلا يُحتسب شيء ولا يتحرك شيء.

**الصلاحية:** كتابة سجل العهدة، وأن يكون المستخدم Card Manager أو من جانب المخزن. ولا يحق للمستخدم إغلاق تسليم موجّه إليه
هو.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `custody` | string | نعم | مسودة عهدة أدوات لسطر مراجعة معتمد، حالتها «Awaiting handover» (في انتظار التسليم). |
| `reason` | string | نعم | سبب عدم تسليم الأداة. |

**القيمة المعادة:** اسم العهدة. **الآثار الجانبية:** تعيين حالة التسليم إلى «Not handed over» (لم تُسلَّم) مع السبب.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.close_tool_handover" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"custody": "<custody-name>", "reason": "Worker on leave"}'
```

## make_tool_handover

`POST /api/method/card.materials.make_tool_handover` — **الصلاحية:** Card Manager، وقراءة المراجعة.

مسودة بديلة لأدوات سطر معتمد لم تُسلَّم بعد، بعد تسليم مغلق أو ملغى.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `review_item` | string | نعم | سطر مراجعة احتياجات (سطر أدوات في مراجعة معتمدة). |

**القيمة المعادة:** اسم مسودة العهدة الجديدة. ويُرفض الطلب إذا كان تسليم للسطر منتظرًا بالفعل، أو سُلّمت كل الأدوات، أو تغيّر
السطر في أثناء العمل.

```bash
curl -s -X POST "https://<your-site>/api/method/card.materials.make_tool_handover" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" -d '{"review_item": "<line-name>"}'
```

## شاشة عهدة الأدوات: context

`GET /api/method/card.tool_custody.context` — **الصلاحية:** أحد أدوار الشاشة، وقراءة عهدة أدوات الموظف. **المعاملات:** لا
توجد.

**القيمة المعادة:** `{"tabs": ["awaiting", "held", "history"], "default_tab", "can_confirm", "can_prepare", "default_store",
"default_stores": {<company>: <store>}}`. ويفتح جانب المخزن والمديرون على «awaiting»، وغيرهم على «held».

```bash
curl -s "https://<your-site>/api/method/card.tool_custody.context" -H "Authorization: token <api_key>:<api_secret>"
```

## شاشة عهدة الأدوات: view

`GET /api/method/card.tool_custody.view` — **الصلاحية:** كما في `context`. والقراءة عبر صلاحيات القائمة الخاصة بالمستخدم
فقط.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `tab` | string | لا | `awaiting` (الافتراضي) أو `held` أو `history`. |
| `employee` | string | لا | الترشيح حسب العامل (مرسلًا أو مستلمًا). |
| `item_code` | string | لا | الترشيح حسب الأداة. |
| `start` | int | لا | الإزاحة؛ والصفحة 25 صفًا. |

**القيمة المعادة:** `{"tab", "rows": [...], "more": bool, "start"}`. وتحمل صفوف «المنتظرة» مخزونَ المخزن و
`waiting_for_stock` و`has_serial_no` والإجراءات المسموح بها `actions` (`confirm` و`not_handed` و`replace`)؛ وتحمل صفوف
«في العهدة» الإجراءات `return` و`transfer`. ولا يحصل المستخدم أبدًا على إجراء على عهدته هو.

```bash
curl -s -G "https://<your-site>/api/method/card.tool_custody.view" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "tab=held"
```

## شاشة عهدة الأدوات: استعلامات الربط

`employee_query` و`store_query` و`item_query` استعلامات ربط قياسية (`doctype` و`txt` و`searchfield` و`start` و
`page_len` و`filters`)، وكلها `GET` ومقصورة على أدوار الشاشة. أما `employee_company` فتعيد شركة موظف واحد.

| نقطة النهاية | القيمة المعادة | الفلاتر |
|---|---|---|
| `card.tool_custody.employee_query` | `[name, employee_name]` للموظفين النشطين في شركات عهدة المستخدم وضمن صلاحيات المستخدم على الموظفين | `company`، و`exclude` (العامل نفسه)، و`any_status` (تضمين غير النشطين) |
| `card.tool_custody.store_query` | `[name, warehouse_name]` للمستودعات المفعّلة غير التجميعية في تلك الشركات | `company` |
| `card.tool_custody.item_query` | `[item_code, item_name]` للأصناف المخزنية المفعّلة التي ليست أصولًا ثابتة | تُتجاهل |
| `card.tool_custody.employee_company` (`employee`) | `{"company": "<company>"}` | — |

```bash
curl -s -G "https://<your-site>/api/method/card.tool_custody.employee_company" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "employee=<employee-id>"
```

## شاشة عهدة الأدوات: move

`POST /api/method/card.tool_custody.move` — **الصلاحية:** أحد أدوار الشاشة، وإنشاء عهدة أدوات الموظف لشركة العامل.

حركة جديدة تُحفظ مسودةً مع القيم الافتراضية: مخزن شركة العامل (وإلا المخزن الرئيسي للموقع)، وفي التسليم معدة العامل
ومشروعها. وتُؤكَّد بـ `confirm` بعد طباعة إيصالها وتوقيعه.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `movement` | string | نعم | `Handover` أو `Return` أو `Transfer`. |
| `employee` | string | نعم | العامل. |
| `item_code` | string | نعم | صنف الأداة. |
| `qty` | float | نعم | الكمية. |
| `to_employee` | string | للتحويل | العامل المستلم. |
| `warehouse` | string | لا | المخزن؛ والافتراضي كما سبق (ولا يُستخدم في التحويل). |
| `serial_no` | string | لا | الرقم التسلسلي. |

**القيمة المعادة:** `{"name", "may_confirm", "has_serial_no", "employee_name", "to_employee_name"}`.

```bash
curl -s -X POST "https://<your-site>/api/method/card.tool_custody.move" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"movement": "Handover", "employee": "<employee-id>", "item_code": "<item-code>", "qty": 1}'
```

## شاشة عهدة الأدوات: confirm

`POST /api/method/card.tool_custody.confirm` — **الصلاحية:** أحد أدوار الشاشة، واعتماد سجل العهدة؛ وتحسم القواعدُ الخاصة
بالسجل نفسه (تأكيد جانب المخزن، والإيصال الموقّع، والفصل بين المهام، والمخزون) الأمر.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `custody` | string | نعم | تسليم أو إرجاع أو تحويل في حالة مسودة. |
| `receipt` | string | لا | ملف الإيصال الموقّع. |
| `qty` | float | لا | الكمية النهائية، أكبر من صفر. |
| `serial_no` | string | لا | الرقم التسلسلي. |

**القيمة المعادة:** `{"name", "stock_entry"}`. **الآثار الجانبية:** اعتماد الحركة؛ والتسليم أو الإرجاع المؤكد يُنشئ قيد
مخزونه ويعتمده في المعاملة نفسها.

```bash
curl -s -X POST "https://<your-site>/api/method/card.tool_custody.confirm" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"custody": "<custody-name>", "receipt": "/private/files/receipt.pdf"}'
```

## ذو صلة

- [احتياجات المعدات](/card/ar/features/equipment-needs/)
- [عهدة الأدوات](/card/ar/features/tool-custody/)
- [تقارير التشغيل](/card/ar/reports/operations/)
