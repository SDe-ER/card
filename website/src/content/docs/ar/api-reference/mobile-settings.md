---
title: واجهة API للتطبيق والإعدادات
description: نقاط نهاية جلسة CARD Mobile، وكتالوج قطع الغيار وتوافقها، وسجل تغييرات الإعدادات المقيّد بالشركة.
sidebar:
  order: 9
---

## نظرة عامة

يستخدم **CARD Mobile** (`/cdms`) تسجيل الدخول والجلسة والحماية من CSRF في Frappe كما يستخدمها Desk، ويستدعي نقاط النهاية
نفسها التي يستدعيها أي عميل آخر؛ وتحتفظ كل نقطة نهاية بفحوص صلاحياتها. وتسرد هذه الصفحة نقاط النهاية التي لا يستخدمها إلا
التطبيق والكتالوج، إضافةً إلى تجاوزات CARD لمحمّل النماذج في Desk التي تُبقي سجل تغييرات **الإعدادات** ضمن شركات المستخدم.
أما نقاط نهاية طلبات المشغّلين فهي في صفحة [المواد والاحتياجات](/card/ar/api-reference/materials-needs/).

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.mobile.get_session_context` | سياق CARD Mobile للمستخدم المسجّل. |
| GET | `card.catalog.search` | صفحة واحدة من كتالوج القطع، مع التوافق لمعدة اختياريًا. |
| GET | `card.catalog.filter_options` | قيم فلتر مجموعة الأصناف أو العلامة التجارية. |
| GET | `card.fitment.fit_for` | توافق حتى 50 صنفًا لمعدة واحدة. |
| GET | `card.fitment.machines` | المعدات التي يمكن للمستدعي البحث عنها في الكتالوج. |
| GET، POST | `card.card.doctype.card_settings.card_settings.getdoc` | تجاوز لـ `frappe.desk.form.load.getdoc`. |
| GET، POST | `card.card.doctype.card_settings.card_settings.get_docinfo` | تجاوز لـ `frappe.desk.form.load.get_docinfo`. |

## مستخدمو الكتالوج

تقبل نقاط نهاية الكتالوج أي مستخدم مسجل الدخول يحق له قراءة الأصناف، أو يحمل أحد أدوار الكتالوج: Card Operator أو Card
Supervisor أو Card Manager أو System Manager (أدوار البوابة)، أو Card User (مستعرض الكتالوج للقراءة فقط). ومع تحديد معدة،
يجب كذلك أن يستطيع المستدعي قراءتها، أو أن يكون مشغّلها بدور Card Operator.

## get_session_context

`GET /api/method/card.mobile.get_session_context`

**الصلاحية:** أحد أدوار البوابة، أو مستعرض كتالوج للقراءة فقط (Card User بلا دور بوابة). للقراءة فقط. **المعاملات:** لا
توجد.

**القيمة المعادة:** `{"user", "full_name", "roles" (أدوار بوابة CARD لدى المستخدم), "employee" ({name, employee_name, company}
للموظف النشط المرتبط، أو null), "catalog_only": bool, "card_version"}`.

```bash
curl -s "https://<your-site>/api/method/card.mobile.get_session_context" -H "Authorization: token <api_key>:<api_secret>"
```

## search

`GET /api/method/card.catalog.search`

صفحة واحدة من كتالوج أصناف ERPNext لنص البحث (رمز الصنف، أو اسمه، أو الباركود، أو رقم القطعة الأصلي — والرموز من 3 أحرف
فأكثر) وللفلاتر. وتنطبق صلاحيات الأصناف الخاصة بالمستخدم وصلاحيات المستخدم. ولا يُعاد عدد إجمالي.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `txt` | string | لا | نص البحث (يُستخدم منه 140 حرفًا على الأكثر). |
| `item_group` | string | لا | مجموعة الأصناف بما فيها مجموعاتها الفرعية؛ والمجموعة غير المعروفة لا تعرض شيئًا. |
| `brand` | string | لا | العلامة التجارية. |
| `start` | int | لا | الإزاحة (الافتراضي 0). |
| `page_length` | int | لا | حجم الصفحة، الافتراضي 20 والحد الأقصى 50. |
| `equipment` | string | لا | المعدة: فيحمل كل صنف توافقه معها. |
| `fits` | int | لا | مع `equipment`، القيمة `1` لا تعرض إلا الأصناف المؤكدة للمعدة أو لموديلها. |

**القيمة المعادة:** `{"items": [{"item_code", "item_name", "stock_uom", "image", "item_group", "item_group_label", "brand",
"oem": [...], "alternatives": [{"item_code", "item_name"}], "fit", "fit_model"}], "has_more": bool}`. وقيمة `fit` إحدى:
`confirmed_machine` أو `confirmed_model` أو `not_compatible` أو `pending` أو `unknown`؛ وقرار المعدة نفسها يغلب قرار
موديلها، والصف المعلّق لا يُعدّ توافقًا أبدًا.

```bash
curl -s -G "https://<your-site>/api/method/card.catalog.search" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "txt=oil filter" --data-urlencode "equipment=EQ-0001"
```

## filter_options

`GET /api/method/card.catalog.filter_options`

قيم فلتر مجموعة الأصناف أو العلامة التجارية، يُبحث فيها وتُقسَّم صفحات على الخادم بصلاحيات المستخدم. وتُطابَق مجموعات
الأصناف باسمها أو بترجمتها.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `kind` | string | نعم | `item_group` أو `brand`. |
| `txt` | string | لا | نص البحث. |
| `start` | int | لا | الإزاحة. |
| `page_length` | int | لا | حجم الصفحة (الافتراضي 20 والحد الأقصى 50). |

**القيمة المعادة:** قائمة `{"value", "label"}`.

```bash
curl -s -G "https://<your-site>/api/method/card.catalog.filter_options" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "kind=brand"
```

## fit_for

`GET /api/method/card.fitment.fit_for`

توافق حتى 50 صنفًا لمعدة واحدة، لمنتقي الأصناف المضمَّن في CARD Mobile. ولا يُجاب إلا عن الأصناف التي يحق للمستدعي عرضها
في الكتالوج.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `equipment` | string | نعم | المعدة. |
| `items` | list | نعم | رموز الأصناف (قائمة JSON، 50 على الأكثر). |

**القيمة المعادة:** `{<item_code>: {"fit": "<state>", "fit_model": "<model name or null>"}}`.

```bash
curl -s -G "https://<your-site>/api/method/card.fitment.fit_for" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "equipment=EQ-0001" --data-urlencode 'items=["<item-code-1>","<item-code-2>"]'
```

## machines

`GET /api/method/card.fitment.machines`

المعدات التي يمكن للمستدعي البحث عنها في الكتالوج: قائمة قارئ Desk الخاصة (وتنطبق صلاحياته، وتُستبعد المعدات المنتهية)، أو
معدات المشغّل نفسه. ويجري البحث والتقسيم إلى صفحات على الخادم.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `txt` | string | لا | نص البحث (الاسم أو اسم المعدة). |
| `start` | int | لا | الإزاحة؛ والصفحة 20 معدة. |

**القيمة المعادة:** `{"machines": [{"name", "equipment_name", "model"}], "has_more": bool}`.

```bash
curl -s -G "https://<your-site>/api/method/card.fitment.machines" -H "Authorization: token <api_key>:<api_secret>"
```

## أخرى: تجاوزات سجل تغييرات الإعدادات

يسجّل CARD تجاوزين عبر `override_whitelisted_methods` حتى لا يرى المستخدم المقيّد بشركة، في سجل تغييرات نموذج **الإعدادات**،
أي تغيير على صف تابع لشركة أخرى:

| الدالة المتجاوَزة | دالة CARD | المعاملات |
|---|---|---|
| `frappe.desk.form.load.getdoc` | `card.card.doctype.card_settings.card_settings.getdoc` | `doctype`، `name` |
| `frappe.desk.form.load.get_docinfo` | `card.card.doctype.card_settings.card_settings.get_docinfo` | `doc` أو `doctype` + `name` |

يستدعي كل تجاوز أولًا التجاوزَ الذي سجّله تطبيق آخر قبل CARD (أو دالة Frappe الأصلية)، فتبقى السلسلة محفوظة، ثم يحذف من
`docinfo.versions` كل تغيير على صف تابع لشركة لا يحق للمستخدم قراءتها. ولا تتغير الاستجابات لأي نوع مستند آخر. ويواصل
العملاء استدعاء مسارات Frappe القياسية، ولا داعي لاستدعاء دوال CARD مباشرة.

```bash
curl -s -G "https://<your-site>/api/method/frappe.desk.form.load.getdoc" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Card Settings" --data-urlencode "name=Card Settings"
```

## ذو صلة

- [CARD Mobile](/card/ar/features/card-mobile/)
- [الصيانة وقطع الغيار](/card/ar/features/maintenance-parts/)
- [الإعداد](/card/ar/getting-started/configuration/)
