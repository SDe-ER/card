---
title: واجهة API للنقل
description: نقاط نهاية الموقع الحالي للمعدة، والقرار المالي لنقل يتحمل تكلفته العميل أو مورد المعدة.
sidebar:
  order: 5
---

## نظرة عامة

عمليات نقل المعدات هي سجلات **نقل المعدات** (Equipment Transport)، وتُقرأ وتُكتب بواجهة الموارد القياسية
(`/api/resource/Equipment Transport`). ويحدد التحقق الخاص بالنقل في كل حفظ المسؤوليةَ والدافعَ ومتحملَ التكلفة ومشروعَ
التكلفة والمبالغ. وتعرض نقاط النهاية أدناه مكان المعدة الآن، وتتيح لمدير الحسابات تسجيل القرار المالي لنقل معتمد.

## نقاط النهاية

| الطريقة | نقطة النهاية | الغرض |
|---|---|---|
| GET | `card.card.doctype.equipment_transport.equipment_transport.get_equipment_location` | المكان الحالي لمعدة واحدة. |
| GET | `card.card.doctype.equipment_transport.equipment_transport.billing_customer` | مشروع الفوترة والعميل المقترحان لقرار. |
| POST | `card.card.doctype.equipment_transport.equipment_transport.record_financial_decision` | تسجيل القرار المالي لنقل معتمد. |

## get_equipment_location

`GET /api/method/card.card.doctype.equipment_transport.equipment_transport.get_equipment_location`

مكان المعدة الآن: على مشروع تعيينها المفتوح؛ وإلا فحيثما أرسلها آخر نقل معتمد (ورشة أو مخزن أو مورد)؛ وإلا ففي المخزن عند
المكان الابتدائي للشركة المحدد في الإعدادات.

**الصلاحية:** قراءة المعدة.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `equipment` | string | نعم | اسم المعدة. |

**القيمة المعادة:** `{"type": "Project"|"Workshop"|"Storage"|"Supplier", "project": "<project or null>", "location": "<place or
null>"}`، ويضيف المكان الابتدائي `"initial": 1`.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.equipment_transport.equipment_transport.get_equipment_location" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "equipment=EQ-0001"
```

## billing_customer

`GET /api/method/card.card.doctype.equipment_transport.equipment_transport.billing_customer`

مشروع الفوترة المقترح لقرار النقل (مشروع الوجهة إذا كان يذكر عميلًا)، أو عميل المشروع الذي يختاره المحاسب. للقراءة فقط؛
ويؤكد المحاسب الاثنين قبل التسجيل.

**الصلاحية:** دور Accounts Manager، وقراءة النقل.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `transport` | string | نعم | اسم النقل. |
| `project` | string | لا | المشروع المراد فحصه؛ والافتراضي مشروع الوجهة. |

**القيمة المعادة:** `{"project": "<project>", "customer": "<customer>"}`، أو `{}` إذا كان المشروع تابعًا لشركة أخرى أو
ملغى أو لا يذكر عميلًا.

```bash
curl -s -G "https://<your-site>/api/method/card.card.doctype.equipment_transport.equipment_transport.billing_customer" \
  -H "Authorization: token <api_key>:<api_secret>" --data-urlencode "transport=<transport-name>"
```

## record_financial_decision

`POST /api/method/card.card.doctype.equipment_transport.equipment_transport.record_financial_decision`

يسجّل مدير الحسابات القرار المالي لنقل معتمد يتحمل تكلفته العميل أو مورد المعدة وحالته المالية **معلّقة**. والقرار يُسجَّل
فقط: فترحيلات فوترة العميل واسترداد المورد وتحمّل الشركة تبقى معطّلة حتى يقرر المحاسب والمستشار الضريبي.

**الصلاحية:** دور Accounts Manager، وقراءة النقل، وأن تكون شركة النقل مسموحًا بها. **الفصل بين المهام:** لا يجوز أن يكون
المستخدم منشئ النقل أو أحد محرريه أو معتمده، ولا منشئ أي نقل يعدّله هذا النقل أو محرره أو معتمده.

| المعامل | النوع | إلزامي | الوصف |
|---|---|---|---|
| `transport` | string | نعم | نقل معتمد عليه قرار معلّق. |
| `decision` | string | نعم | إذا كان المتحمل هو العميل: `Bill customer` أو `Company absorbs` أو `Return for correction`. وإذا كان مورد المعدة: `Recover from equipment supplier` أو `Return for correction`. |
| `customer` | string | للفوترة | عميل مفعّل يُفوتر؛ والافتراضي عميل مشروع الفوترة، ويجب أن يحق للمستخدم قراءته. |
| `billing_project` | string | للفوترة | مشروع تابع لشركة النقل (غير ملغى). |
| `billing_amount` | float | للفوترة | المبلغ المتفق عليه، أكبر من صفر. |
| `billing_mode` | string | لا | `Monthly invoice` (الافتراضي) أو `Separate invoice`. |
| `billing_reference` | string | للفوترة | مرجع التفويض (عقد أو أمر أو موافقة). |
| `billing_document` | string | لا | ملف خاص مرفق بهذا النقل (JPEG أو PNG أو WebP أو PDF). |
| `confirmed` | int | للفوترة | ‏`1`: أكّد المحاسب العميل ومشروع الفوترة. |
| `absorption_reason` | string | للتحمّل | سبب تحمّل الشركة التكلفة. |
| `recovery_mode` | string | لا | `Deduct from monthly dues` (الافتراضي) أو `Adjustment document`. |
| `recovery_amount` | float | للاسترداد | المبلغ المسترد، أكبر من صفر. |
| `note` | string | للرفض | إلزامي مع `Return for correction`، واختياري فيما سواه. |

**القيمة المعادة:** `{"financial_status": "Approved"|"Rejected", "financial_decision": "<decision>"}`.

**الآثار الجانبية:** كتابة حقول القرار والمعتمد والوقت على النقل المعتمد، وإضافة سجل نسخة (Version) يسجّل تغيّر الحالة،
وتعليق «Financial decision recorded.». ويُرتَّب قراران متزامنان بقفل على الصف. والنقل المرفوض يُلغى بعد ذلك ويُعدَّل.

```bash
curl -s -X POST "https://<your-site>/api/method/card.card.doctype.equipment_transport.equipment_transport.record_financial_decision" \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"transport": "<transport-name>", "decision": "Bill customer", "billing_project": "PROJ-0001", "billing_amount": 1000, "billing_reference": "PO-0001", "confirmed": 1}'
```

## ذو صلة

- [النقل](/card/ar/features/transport/)
- [التعيينات والمواقع](/card/ar/features/assignments-locations/)
- [تقارير النقل والتكاليف](/card/ar/reports/transport-costs/)
