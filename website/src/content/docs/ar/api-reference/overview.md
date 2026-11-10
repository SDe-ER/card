---
title: نظرة عامة على الـ API
description: كيفية استدعاء دوال CARD على الخادم وأنواع مستنداته عبر واجهة Frappe REST القياسية — المصادقة، وطرق HTTP، والاستجابات، والأخطاء، وقواعد الصلاحيات.
sidebar:
  order: 1
---

## نظرة عامة

ليس لـ CARD خادم API مستقل. فكل نقطة نهاية (Endpoint) في CARD هي دالة Python مُعلَّمة بـ `@frappe.whitelist` تقدّمها
واجهة REST القياسية في Frappe، وكل سجل في CARD هو نوع مستند (DocType) يمكن الوصول إليه عبر واجهة الموارد القياسية في
Frappe. وتنطبق قواعد الصلاحيات نفسها المطبقة في Desk وفي CARD Mobile: فمستدعي الـ API يستطيع أن يفعل بالضبط ما يستطيع
المستخدم نفسه فعله على الشاشة، ولا يزيد عليه.

يسرد هذا القسم كل دالة مسموح باستدعائها في CARD، مجمّعة حسب المجال. أما الدوال المساعدة الخاصة غير المسموح باستدعائها
فلا يمكن استدعاؤها ولا تُذكر هنا.

## المفاهيم الأساسية

| المفهوم | المعنى |
|---|---|
| نقطة نهاية الدالة | `POST` أو `GET` على `https://<your-site>/api/method/<dotted.path>` لتشغيل دالة مسموح بها. |
| نقطة نهاية المورد | `https://<your-site>/api/resource/<DocType>` لعرض السجلات وقراءتها وإنشائها وتعديلها وحذفها. |
| مفتاح الـ API وسرّه | يُولَّدان لكل مستخدم في ERPNext (**المستخدم ← الإعدادات ← الوصول إلى API ← توليد المفاتيح**)، ويعمل المستدعي بصفة ذلك المستخدم. |
| طرق HTTP المعلنة | تعلن كل دالة في CARD عن `methods=`: ‏`GET` للقراءة دون آثار جانبية، و`POST` لكل ما يكتب. وبعض دوال القراءة تقبل `POST` لأن عنصرًا في Desk يستدعيها بهذه الطريقة. |
| نطاق الشركة | الشركات التي يحق للمستخدم رؤيتها، المستمدة من صلاحيات المستخدم على الشركة. ويُرفض الوصول عبر الشركات دائمًا على الخادم. |

## المزايا

### المصادقة

استخدم المصادقة بالرمز (Token) بمفتاح وسرّ المستخدم الذي يعمل التكامل باسمه:

```bash
curl -s "https://<your-site>/api/method/card.mobile.get_session_context" \
  -H "Authorization: token <api_key>:<api_secret>"
```

- طلبات الرمز لا تحتاج إلى رمز CSRF.
- تعمل جلسة المتصفح (تسجيل الدخول بملفات تعريف الارتباط) أيضًا، وعندئذ يشترط Frappe الترويسة `X-Frappe-CSRF-Token` في
  طلبات `POST`.
- أنشئ مستخدمًا مخصصًا لكل تكامل وامنحه الأدوار التي يحتاجها فقط، ولا تشارك المفاتيح أبدًا.

### استدعاء دالة

- **القراءة (`GET`)** – مرّر الوسائط معاملاتِ استعلام. وتُرسل القوائم والكائنات نصوصَ JSON:

  ```bash
  curl -s -G "https://<your-site>/api/method/card.diesel.get_card_diesel" \
    -H "Authorization: token <api_key>:<api_secret>" \
    --data-urlencode "card=<monthly-card-name>"
  ```

- **الكتابة (`POST`)** – أرسل جسم طلب بصيغة JSON (أو حقول نموذج):

  ```bash
  curl -s -X POST "https://<your-site>/api/method/card.cancel_reason.cancel_with_reason" \
    -H "Authorization: token <api_key>:<api_secret>" \
    -H "Content-Type: application/json" \
    -d '{"doctype": "Equipment Transport", "name": "<transport-name>", "reason": "Entered twice"}'
  ```

- الاستدعاء بطريقة HTTP لا تعلنها الدالة يُرفض بخطأ صلاحية.

### الاستجابات

يعيد الاستدعاء الناجح حالة HTTP ‏200 وقيمةَ ما تعيده الدالة تحت المفتاح `message`:

```json
{ "message": { "name": "EQ-0001", "docstatus": 2 } }
```

الدالة التي لا تعيد شيئًا تعيد `{}` أو `{"message": null}`. أما التقارير وتنزيل الملفات (مثل ملف PDF لكشف المورد)
فتعيد الملف نفسه.

### الأخطاء

تتبع الأخطاء الصيغة القياسية في Frappe: حالة HTTP، ونوع الاستثناء، والرسائل الموجهة إلى المستخدم في `_server_messages`
(قائمة مرمّزة بصيغة JSON تضم كائنات مرمّزة بصيغة JSON). وتُترجم الرسائل إلى لغة المستخدم.

| حالة HTTP | `exc_type` | السبب المعتاد |
|---|---|---|
| 403 | `PermissionError` | دور مفقود، أو لا صلاحية قراءة/كتابة على السجل، أو شركة غير مسموح بها، أو طريقة HTTP خاطئة، أو عدم تسجيل الدخول. |
| 404 | `DoesNotExistError` | السجل غير موجود. |
| 417 | `ValidationError` (أو صنف فرعي منه) | قاعدة عمل رفضت الطلب، مثل «فترة غير صحيحة: النهاية قبل البداية». |
| 409 | `DuplicateEntryError` / عدم تطابق الطابع الزمني | تغيير متزامن للسجل نفسه. |

```json
{
  "exc_type": "PermissionError",
  "_server_messages": "[\"{\\\"message\\\": \\\"Not permitted\\\", \\\"indicator\\\": \\\"red\\\"}\"]"
}
```

### قواعد الصلاحيات

- **الأدوار أولًا.** تفحص كل دالة الأدوار أو صلاحيات أنواع المستندات التي تحتاجها قبل أي قراءة أو كتابة، والدور المطلوب
  مذكور لكل نقطة نهاية في هذا المرجع.
- **صلاحيات السجل.** تمر القراءة والكتابة عبر صلاحيات المستخدم نفسه (`frappe.get_list` و`check_permission`)، بما في
  ذلك صلاحيات المستخدم ومستويات الصلاحية. ولا تُعاد الحقول الواقعة في مستوى صلاحية لا يملكه المستخدم.
- **نطاق الشركة.** تُرفض الشركة أو المشروع أو المعدة أو الطرف التابع لشركة لا يحق للمستخدم رؤيتها، ولا يُقرأ.
- **الفصل بين المهام.** ترفض بعض عمليات الكتابة المستخدمَ الذي أعدّ السجل (مثل اعتماد مراجعة احتياجات عدّلها المستخدم،
  أو تسجيل القرار المالي لنقل أنشأه).
- **لا كتابة في دفتر الأستاذ.** لا تكتب أي نقطة نهاية في CARD قيدًا في دفتر الأستاذ. فنقاط الترحيل تُنشئ فواتير ERPNext
  في حالة مسودة، ولا تظهر صفوف الدفتر إلا عندما يعتمدها شخص في ERPNext.

### واجهة الموارد القياسية لأنواع المستندات

تستخدم أنواع مستندات CARD واجهة الموارد في Frappe بالصلاحيات نفسها:

| الإجراء | الطلب |
|---|---|
| عرض قائمة | `GET /api/resource/Card Equipment?fields=["name","equipment_name"]&filters=[["company","=","Example Contracting Co."]]` |
| قراءة | `GET /api/resource/Card Monthly Card/<name>` |
| إنشاء | `POST /api/resource/Project Diesel Fill` مع المستند بصيغة JSON |
| تعديل | `PUT /api/resource/Equipment Transport/<name>` مع الحقول المعدلة |
| حذف | `DELETE /api/resource/<DocType>/<name>` |
| اعتماد / إلغاء | `POST /api/method/frappe.client.submit` / `frappe.client.cancel` |

أنواع مستندات CARD الرئيسية: Card Equipment، وCard Equipment Assignment، وCard Monthly Card، وCard Daily Log، وProject
Diesel Fill، وEquipment Transport، وEquipment Needs Request، وEquipment Needs Review، وEmployee Tool Custody، وEquipment
Meter Reading، وCard Equipment Supplier، وCard Equipment Customer، وCard Stop Reason، وCard Settings، وCard Company
Settings، وGL Posting Log. ويجري التحقق على الخادم في كل مسار: REST، ونموذج Desk، والاستيراد.

:::caution
السجلات التي يكتبها CARD من الخادم وحده (حقول الاعتماد، وسجلات الترحيل، وروابط التسوية) تُرفض أو تُتجاهل إذا أُرسلت عبر
واجهة الموارد. استخدم الدوال الموثقة بدلًا من ذلك.
:::

## مجموعات نقاط النهاية

| الصفحة | المجال |
|---|---|
| [المعدات](/card/ar/api-reference/equipment/) | الوحدات ومكوّناتها، والتعبئة المسبقة من الأصل والإنشاء منه، والخريطة الحرارية، وسلامة الوحدات. |
| [الكروت واليوميات](/card/ar/api-reference/cards-daily-logs/) | سياق الكرت، والإنشاء من اليوميات، والإلغاء مع السبب، وقيم لوحة المعلومات. |
| [الديزل](/card/ar/api-reference/diesel/) | ديزل الكرت، ومساعدات نموذج التعبئة، واستثناءات السعر، وفلتر المطابقة. |
| [النقل](/card/ar/api-reference/transport/) | الموقع الحالي، والقرارات المالية. |
| [المواد والاحتياجات](/card/ar/api-reference/materials-needs/) | طلبات المشغّلين، والمراجعات، والاعتماد، وتسليم الأدوات، وشاشة عهدة الأدوات. |
| [الأطراف والكشوف](/card/ar/api-reference/parties-statements/) | سجل الأطراف، وخيارات فلاتر التقارير وقيمها الافتراضية، وملف PDF للكشف. |
| [الترحيل والمحاسبة](/card/ar/api-reference/posting-accounting/) | الترحيل الشهري، والمعاينات، والتصحيحات، وربط الفواتير وقيود اليومية. |
| [التطبيق والإعدادات](/card/ar/api-reference/mobile-settings/) | جلسة CARD Mobile، والكتالوج والتوافق، وسجل تغييرات الإعدادات. |

## ذو صلة

- [نظرة عامة على التقارير](/card/ar/reports/overview/)
- [الأدوار والصلاحيات](/card/ar/features/roles-permissions/)
- [CARD Mobile](/card/ar/features/card-mobile/)
