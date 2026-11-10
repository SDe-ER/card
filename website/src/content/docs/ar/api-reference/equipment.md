---
title: واجهة API للمعدات
description: نقاط نهاية الوحدات ومكوّناتها، وإنشاء المعدات من أصل في ERPNext، والخريطة الحرارية للتشغيل، وفحوص سلامة الوحدات.
sidebar:
  order: 2
---

## نظرة عامة

تخدم نقاط النهاية هذه نموذج **المعدات** (Card Equipment): تغييرات مكوّنات الوحدة، والتعبئة المسبقة من أصل في ERPNext،
والخريطة الحرارية لكل وردية، وفحص سلامة الوحدات. أما سجلات المعدات العادية فتُقرأ وتُكتب بواجهة الموارد القياسية
(`/api/resource/Card Equipment`). وانظر [نظرة عامة على الـ API](/card/ar/api-reference/overview/) للمصادقة والأخطاء.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.api.get_asset_prefill` | القيم التي يأخذها نموذج المعدة من أصل معتمد. |
| POST | `card.api.create_equipment_from_asset` | إنشاء معدة (أو تعبئتها مسبقًا) من أصل معتمد. |
| GET | `card.api.available_assets_query` | استعلام ربط: الأصول المعتمدة غير المربوطة بمعدة بعد. |
| GET | `card.api.get_only_company` | الشركة التي يأخذها نموذج CARD الجديد إذا كان المستخدم يرى شركة واحدة. |
| GET | `card.card.doctype.card_equipment.card_equipment.get_shift_heatmap` | ساعات التشغيل اليومية لكل وردية. |
| GET | `card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues` | السجلات المخالفة لقواعد الوحدات. |
| POST | `card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag` | إعادة ضبط علامة «مكوّن وحدة» لقطعة واحدة. |
| POST | `card.card.doctype.card_equipment.card_equipment.replace_component` | استبدال مكوّن في وحدة ابتداءً من تاريخ. |
| POST | `card.card.doctype.card_equipment.card_equipment.move_component` | نقل مكوّن إلى وحدة أخرى ابتداءً من تاريخ. |

## get_asset_prefill

`GET /api/method/card.api.get_asset_prefill`

يعيد قيم المعدة التي يملؤها النموذج من أصل معتمد في ERPNext. للقراءة فقط.

**الصلاحية:** قراءة المعدات، وقراءة الأصل.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `asset` | string | نعم | اسم أصل معتمد. |

**القيمة المعادة:** كائن بحقول المعدة المأخوذة من الأصل — `company` و`image` و`cost_center` و`operator` (أمين العهدة)
و`insurance_company` و`insurance_policy_no` و`insurance_expiry` و`equipment_name` و`brand` (من صنف الأصل)
و`equipment_type` (المقابل لفئة الأصل) — إضافةً إلى `equipment_type_from_asset` (1 أو 0). ولا تُعاد إلا الحقول التي
يحق للمستخدم قراءتها في المعدات (فلا يُعاد مركز التكلفة مثلًا دون مستوى الصلاحية المناسب).

```bash
curl -s -G "https://<your-site>/api/method/card.api.get_asset_prefill" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "asset=<asset-name>"
```

## create_equipment_from_asset

`POST /api/method/card.api.create_equipment_from_asset`

يبني معدة من أصل معتمد بأقل قدر من الإدخال. ومع `save` وعدم بقاء ما يُسأل عنه، تُنشأ المعدة بصلاحيات المستخدم نفسه
وبالتحقق الكامل؛ وإلا فلا يُدرج شيء وتُعاد القيم المعبأة مسبقًا مع الحقول التي ما زالت ناقصة.

**الصلاحية:** إنشاء المعدات، وقراءة الأصل.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `asset` | string | نعم | الأصل المعتمد المراد ربطه. |
| `ownership` | string | لا | «ملك» (الافتراضي) أو «طرف ثالث». والمعدة المستأجرة لا يكون لها أصل أبدًا وتُرفض. |
| `save` | int | لا | ‏`1` للإنشاء فورًا متى أمكن؛ والافتراضي `0`. |

**القيمة المعادة:** `{"name": "<equipment>"}` عند الإنشاء؛ وإلا الحقول المعبأة المقروءة مع `missing` — قائمة تضم
`equipment_type` و`daily_hours`، و`rental_direction` للمعدة التابعة لطرف ثالث.

**الآثار الجانبية:** مع `save=1` تُدرج معدة مربوطة بالأصل. والمعدة الملك تُجعل الشركةُ فيها جهةَ التشغيل والوقود، وتأخذ
ساعات اليوم قيمتها الافتراضية من الإعدادات. ويُرفض الأصل المربوط بمعدة من قبل، ويُرتَّب إنشاءان متزامنان للأصل نفسه
بقفل على الصف.

```bash
curl -s -X POST "https://<your-site>/api/method/card.api.create_equipment_from_asset" \
  -H "Authorization: token <api_key>:<api_secret>" \
  -H "Content-Type: application/json" \
  -d '{"asset": "<asset-name>", "ownership": "ملك", "save": 1}'
```

## available_assets_query

`GET /api/method/card.api.available_assets_query`

بحث حقل الربط لحقل الأصل في المعدة: الأصول المعتمدة للشركة المحددة التي ليست مُكهّنة أو مباعة وليست مربوطة بمعدة.

**الصلاحية:** دور يحق له إنشاء المعدات أو تعديلها، وصلاحية قراءة (لا اختيار فقط) على الأصول؛ والشركات مقصورة على ما
يحق للمستخدم رؤيته في المعدات.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `doctype` | string | نعم | وسيط استعلام الربط القياسي (`Asset`). |
| `txt` | string | نعم | نص البحث (الاسم أو اسم الأصل). |
| `searchfield` | string | نعم | وسيط استعلام الربط القياسي. |
| `start` | int | نعم | الإزاحة. |
| `page_len` | int | نعم | حجم الصفحة (القيمة 0 تعني 20). |
| `filters` | object | نعم | `{"company": "<company>"}`، والشركة اختيارية. |

**القيمة المعادة:** قائمة أزواج `[name, asset_name]`.

```bash
curl -s -G "https://<your-site>/api/method/card.api.available_assets_query" \
  -H "Authorization: token <api_key>:<api_secret>" \
  --data-urlencode "doctype=Asset" --data-urlencode "txt=" --data-urlencode "searchfield=name" \
  --data-urlencode "start=0" --data-urlencode "page_len=20" \
  --data-urlencode 'filters={"company":"Example Contracting Co."}'
```

## get_only_company

`GET /api/method/card.api.get_only_company`

الشركة التي يملؤها نموذج CARD الجديد إذا كان المستخدم يستطيع عرض شركة واحدة بالضبط؛ وإلا `null`. ويبقى الحقل قابلًا
للتعديل.

**الصلاحية:** أي مستخدم مسجل الدخول؛ وتعيد `null` دون صلاحية قراءة أو اختيار على الشركة.

**المعاملات:** لا توجد. **القيمة المعادة:** اسم شركة أو `null`.

```bash
curl -s "https://<your-site>/api/method/card.api.get_only_company" \
  -H "Authorization: token <api_key>:<api_secret>"
```

## get_shift_heatmap

`GET /api/method/card.card.doctype.card_equipment.card_equipment.get_shift_heatmap`

ساعات التشغيل اليومية لمعدة واحدة من كروتها الشهرية المعتمدة، مقسّمة حسب الوردية، للخريطتين الحراريتين في نموذج
المعدة. وتُستبعد الأيام ذات الساعات الصفرية.

**الصلاحية:** قراءة المعدة، وقراءة كروت التشغيل الشهرية.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `name` | string | نعم | اسم المعدة. |

**القيمة المعادة:** `{"day": {<unix timestamp>: hours}, "night": {<unix timestamp>: hours}, "has_night": true|false}`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.get_shift_heatmap" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "name=EQ-0001"
```

## get_unit_integrity_issues

`GET /api/method/card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues`

السجلات القائمة التي تخالف قاعدة «الوحدة لا تكون إلا ملكًا»، أو لا تطابق علامةُ «مكوّن وحدة» فيها جداولَ المكوّنات، من
بين المعدات التي يحق للمستخدم قراءتها. للقراءة فقط.

**الصلاحية:** قراءة المعدات (وتنطبق صلاحيات المستخدم على الشركة).

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `company` | string | لا | قصر النتائج على شركة واحدة. |

**القيمة المعادة:** قائمة `{issue, message, equipment, company, unit}`. والمشكلات: «Unit is not owned» (وحدة غير
مملوكة)، و«Component is not owned» (مكوّن غير مملوك)، و«Component flag without a unit» (علامة مكوّن بلا وحدة)،
و«Component flag after leaving its unit» (علامة مكوّن بعد مغادرة وحدته)، و«Current component without the flag» (مكوّن
حالي بلا علامة).

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.get_unit_integrity_issues" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "company=Example Contracting Co."
```

## resync_unit_component_flag

`POST /api/method/card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag`

يضبط علامة «مكوّن وحدة» لمعدة واحدة على القيمة التي تعطيها صفوف المكوّنات.

**الصلاحية:** كتابة المعدة، وصلاحية كتابة على مستوى صلاحية العلامة (مستوى Card Manager).

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `equipment` | string | نعم | اسم المعدة. |

**القيمة المعادة:** العلامة المستنتجة `1` أو `0`. **الآثار الجانبية:** تخزين العلامة، ويترك التغيير تعليقًا على القطعة.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.resync_unit_component_flag" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"equipment": "EQ-0002"}'
```

## replace_component

`POST /api/method/card.card.doctype.card_equipment.card_equipment.replace_component`

ابتداءً من `date` يحل `new_component` محل `component` في `unit`. وتبقى الوحدة معدة واحدة في كرتها الشهري، ولا يتغير إلا
السجل المؤرخ لقطعها.

**الصلاحية:** كتابة الوحدة وصلاحية الكتابة على جدول مكوّناتها (مستوى Card Manager)، وقراءة المكوّن الجديد.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `unit` | string | نعم | الوحدة (معدة مُعلَّمة بأنها وحدة). |
| `component` | string | نعم | المكوّن الحالي المراد إغلاقه. |
| `new_component` | string | نعم | المكوّن البديل. |
| `date` | date | نعم | أول يوم للمكوّن الجديد، ويجب أن يأتي بعد بداية الصف الحالي. |
| `reason` | string | لا | سبب التغيير، ويُخزن في الصفين. |

**القيمة المعادة:** اسم الوحدة. **الآثار الجانبية:** يُغلق الصف الحالي في اليوم السابق لـ `date` ويُضاف صف جديد. ويُرفض
الطلب إذا كان للوحدة كرت معتمد ينتهي في `date` أو بعده، أو لم يكن المكوّن الجديد على مشروع الوحدة في ذلك اليوم.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.replace_component" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"unit": "EQ-0001", "component": "EQ-0002", "new_component": "EQ-0003", "date": "2026-02-01", "reason": "Engine swap"}'
```

## move_component

`POST /api/method/card.card.doctype.card_equipment.card_equipment.move_component`

ابتداءً من `date` يغادر `component` الوحدةَ `unit` ويعمل في `target_unit` على المشروع نفسه.

**الصلاحية:** صلاحية كتابة المكوّنات (مستوى Card Manager) على الوحدتين.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `unit` | string | نعم | الوحدة الحالية. |
| `component` | string | نعم | المكوّن المراد نقله. |
| `target_unit` | string | نعم | وحدة أخرى. |
| `date` | date | نعم | أول يوم في الوحدة الهدف. |
| `reason` | string | لا | سبب التغيير. |

**القيمة المعادة:** اسم الوحدة الهدف. **الآثار الجانبية:** يُغلق الصف في الوحدة المصدر، ويُضاف إلى الوحدة الهدف، وتُزامَن
علامات المكوّنات مرة واحدة. ويُرفض الطلب إذا كان لأيّ من الوحدتين كرت معتمد يغطي `date` أو ما بعده، أو لم يكن المكوّن على
مشروع الوحدة الهدف في ذلك اليوم.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.card_equipment.card_equipment.move_component" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"unit": "EQ-0001", "component": "EQ-0002", "target_unit": "EQ-0004", "date": "2026-02-01"}'
```

## ذو صلة

- [المعدات](/card/ar/features/equipment/)
- [الوحدات والمكوّنات](/card/ar/features/units-components/)
- [تقارير الصيانة والأصول](/card/ar/reports/maintenance-assets/)
