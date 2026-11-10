---
title: الأدوار والصلاحيات
description: أدوار CARD، وما يستطيع كل دور فعله، وعزل الشركات، وخصوصية الحقول وظهور المبالغ، وفصل المهام.
sidebar:
  order: 18
---

## نظرة عامة

يضيف CARD أدواره الخاصة فوق أدوار ERPNext القياسية، ويعتمد على نظام الصلاحيات في Frappe في كل شيء: صلاحيات أنواع
المستندات، ومستويات الصلاحية على الحقول، وصلاحيات المستخدم (User Permissions)، وخطافات الصلاحية على الخادم. ويفحص
الخادم كل إجراء؛ فلا يعدّ CARD الحقل المخفي أو الزر المخفي صلاحيةً أبدًا، ولا يوسّع أبدًا صلاحيات المستخدم في
ERPNext. وتُنفَّذ عمليات الترحيل والاعتماد بصلاحيات المستخدم نفسه.

<!-- screenshot: roles-permissions-role-list -->

## المفاهيم الأساسية

| المفهوم | المعنى |
|---|---|
| **دور CARD** | دور ينشئه CARD عند التثبيت: Card Manager وCard User وCard Supervisor وCard Operator وCard Reviewer. |
| **دور ERPNext** | الأدوار القياسية التي يستخدمها CARD أيضًا: System Manager وAccounts Manager وAccounts User وStock Manager وStock User وPurchase User. |
| **مستوى الصلاحية** | الحقول في المستوى 1 أو 2 لا يقرؤها أو يكتبها إلا الأدوار الممنوحة ذلك المستوى. |
| **عزل الشركات** | المستخدم المقيَّد ببعض الشركات عبر صلاحيات المستخدم على الشركة لا يقرأ سجلات CARD لشركة أخرى ولا يكتبها أبدًا. |
| **السجلات الخاصة** | صلاحية «إن كان المالك» (if owner): لا يتصرف المستخدم إلا في السجلات التي أنشأها. |

## المزايا

### أدوار CARD

| الدور | Desk | الغرض |
|---|---|---|
| **Card Manager** | نعم | إدارة CARD: المعدات، والتعيينات، وعمليات النقل، والكروت الشهرية، والديزل، والإعدادات (قراءة)، والترحيل الشهري، واعتماد احتياجات المعدات |
| **Card User** | نعم | الإدخال اليومي: المعدات، والكروت الشهرية، وعمليات النقل، وتعبئات الديزل (إنشاء وحفظ دون اعتماد)؛ وكتالوج للقراءة فقط في CARD Mobile |
| **Card Supervisor** | نعم | المشرف الميداني: اليوميات، وقراءات العدادات، ومراجعات احتياجات المعدات، وتوافق القطع، وعهدة الأدوات |
| **Card Operator** | لا | المشغّل: يستخدم CARD Mobile فقط — معداته، وطلبات احتياجات معداته، وكذلك يومياته الخاصة |
| **Card Reviewer** | نعم | دور المراجع في مسار الاعتماد. يُنشأ في كل موقع لكنه غير ممنوح لأحد، ولم يُذكر بعد في صلاحيات أي نوع مستند |

:::note
يُنشأ دور Card Operator دون صلاحية الدخول إلى Desk. لكن المشغّل الذي يحمل أيضًا دور Employee في ERPNext يظل قادرًا
على الوصول إلى Desk من خلال ذلك الدور؛ فامنح المشغّلين الأدوار التي يحتاجونها فقط.
:::

### ما يستطيع كل دور فعله

أهم أنواع المستندات وصلاحيات المستوى 0 (من مصفوفة الأدوار والإجراءات المشحونة مع الشيفرة):

| نوع المستند | القراءة | الكتابة / الإنشاء | الاعتماد / الإلغاء |
|---|---|---|---|
| المعدات | System Manager وCard Manager وCard User وAccounts Manager وCard Supervisor | الكتابة: System Manager وCard Manager وCard User. الإنشاء: System Manager وCard Manager | — |
| تعيين معدة على مشروع | System Manager وCard Manager وCard User وAccounts Manager | System Manager وCard Manager | — |
| كارت التشغيل الشهري | System Manager وCard Manager وCard User وAccounts Manager | System Manager وCard Manager وCard User | System Manager وCard Manager |
| نقل المعدات | System Manager وCard Manager وCard User وAccounts Manager | System Manager وCard Manager وCard User | System Manager وCard Manager |
| تعبئة ديزل للمشروع | System Manager وCard Manager وCard User وAccounts Manager | System Manager وCard Manager وCard User | System Manager وCard Manager |
| اليومية | System Manager وCard Manager وCard Supervisor وCard User وCard Operator (سجلاته) | System Manager وCard Manager وCard Supervisor وCard Operator (سجلاته) | مثل الكتابة |
| قراءة عداد المعدة | Card Manager وCard Supervisor وCard User | Card Manager وCard Supervisor | Card Manager وCard Supervisor |
| اتفاقية أسعار المعدة | System Manager وCard Manager وAccounts Manager وCard User | System Manager وCard Manager | System Manager وCard Manager |
| سبب توقف المعدة | System Manager وCard Manager وCard Supervisor وCard User وAccounts Manager | System Manager وCard Manager | — |
| طلب احتياجات معدة | System Manager وCard Manager وCard Supervisor وCard Operator وCard User | System Manager وCard Manager وCard Supervisor وCard Operator | الاعتماد: مثل الكتابة. الإلغاء: System Manager وCard Manager وCard Supervisor |
| مراجعة احتياجات المعدات | System Manager وCard Manager وCard Supervisor وCard User | System Manager وCard Manager وCard Supervisor | System Manager وCard Manager وCard Supervisor |
| عهدة أدوات الموظف | System Manager وCard Manager وStock Manager وCard Supervisor وCard User | System Manager وCard Manager وStock Manager وCard Supervisor | الاعتماد: مثل الكتابة. الإلغاء: System Manager وCard Manager وStock Manager |
| مورد المعدات / عميل المعدات | System Manager وCard Manager وCard User وAccounts Manager | System Manager وCard Manager | — |
| توافق القطع (Card Equipment Part) | System Manager وCard Manager وCard Supervisor | System Manager وCard Manager وCard Supervisor | — |
| سجل الترحيل المحاسبي | System Manager وAccounts Manager وCard Manager | لا أحد (يكتبه CARD وحده) | — |
| الإعدادات | System Manager وAccounts Manager وCard Manager | System Manager وAccounts Manager | — |

ويقتصر الحذف في معظم أنواع المستندات على System Manager (ويملكه Card Manager أيضًا في احتياجات المعدات وعهدة الأدوات).

### إجراءات مقصورة على أدوار محددة

| الإجراء | من يجوز له |
|---|---|
| بناء الفواتير الشهرية المسودة وترحيلها، وفتح صفحة الترحيل الشهري CARD | Card Manager وSystem Manager |
| اعتماد مراجعة احتياجات المعدات إلى طلبات مواد مسودة | Card Manager وSystem Manager (مع صلاحية إنشاء طلب المواد) — ولا يجوز أبدًا لمُعِدّ المراجعة |
| تسجيل القرار المالي لنقل مُعاد تحميله | Accounts Manager — ولا يجوز أبدًا لمنشئ النقل أو محرّره أو معتمده |
| قبول تصحيح فاتورة مسودة من CARD عُدِّلت | Accounts Manager وSystem Manager، مع ذكر السبب |
| ربط فاتورة مورد مسجّلة يدويًا أو قيد يومية استحقاق للمورد بمصادر CARD | Accounts Manager وAccounts User وSystem Manager |
| تجاوز قفل الفترة | **دور تجاوز قفل الفترة** المحدد في الإعدادات؛ ويُسجَّل كل تجاوز |
| تغيير مورد الديزل / اعتماد استثناء سعر الديزل / حفظ سعر صفري / تغيير أسعار النقل | الأدوار المحددة في تبويب «صلاحيات متقدمة» في الإعدادات |
| تحديث سجلات الموردين والعملاء | System Manager |

### عزل الشركات

ينتمي كل سجل تشغيلي في CARD إلى شركة واحدة، ويفصل الخادم بين الشركات:

- تتبع السجلات التي لها حقل **الشركة** صلاحياتِ المستخدم على الشركة، كما في سائر ERPNext.
- يضيف CARD خطافات صلاحية على الخادم حيث تُستمد الشركة من سجل آخر: التعيين ينتمي إلى شركة معدته، والكارت الشهري
  إلى شركة معدته، والنقل إلى شركة مشروعه، ومراجعة احتياجات المعدات إلى شركة مشروعها، وعهدة الأدوات إلى شركة
  موظفيها، وتعبئة الديزل إلى شركتها. وتنطبق هذه الخطافات على القوائم، وعروض التقارير، والبحث في الروابط، والعدّ،
  والقراءة المفردة، والحفظ، والاعتماد، والإلغاء، وعلى استدعاءات REST.
- يُفحص السجل الجديد مقابل الشركة التي *سيضبطها* الخادم، فلا يستطيع المستخدم المقيَّد بالشركة «أ» إنشاء سجل للشركة
  «ب» بترك حقل الشركة فارغًا.
- تُرفض مشاركة السجل (DocShare) مع مستخدم من شركة أخرى في أنواع المستندات الخاضعة للعزل.
- سجلات الموردين والعملاء عامة، لكن المستخدم المقيَّد ببعض الشركات لا يرى إلا الأطراف التي لها كروت في تلك الشركات،
  ولا يرى أرقامها إلا لتلك الشركات.
- في الإعدادات، لا يرى المستخدم المقيَّد بالشركات إلا صفوف شركاته وأنواع إضافاتها وخصوماتها وأسعار ديزلها، حتى في
  سجل التغييرات.
- لا تقرأ التقارير وأرقام لوحة القيادة إلا سجلات الشركات المسموح بها للمستخدم.

وتثبت اختبارات العزل بين الشركات في الشيفرة، لكل دالة خادم، أن مستخدم الشركة «أ» الذي يوجّهها إلى الشركة «ب» يُرفض
أو لا يتلقى أي قيمة من الشركة «ب»، وأن شيئًا لا يُكتب.

### خصوصية الحقول وظهور المبالغ

لسجل **المعدات** ثلاثة مستويات للحقول:

| المستوى | الحقول | القراءة | الكتابة |
|---|---|---|---|
| 0 | الهوية والنوع والحالة والوثائق والمشغّل | كل القرّاء | Card Manager وCard User وSystem Manager |
| 1 | الشروط التجارية: الملكية، واتجاه الإيجار، والمؤجِّر، والعميل، والأسعار وأنواعها، والعقد، وتواريخ الإيجار، والساعات اليومية، والوقود والمشغّل على حساب من، والأصل، والماركة والموديل، والوحدة ومكوّناتها | System Manager وCard Manager وCard User وAccounts Manager | System Manager وCard Manager |
| 2 | البيانات المالية: مركز تكلفة المعدة، ومركز تكلفة الأصل، وقيمة شراء الأصل، والسعر الداخلي بالساعة، وسعر التشغيل الداخلي وأساسه | System Manager وCard Manager وAccounts Manager | System Manager وCard Manager |

- يتطلب تغيير أي حقل تجاري في المستوى 1 إدخال **سبب تغيير الشروط التجارية** جديد.
- يطبّق Frappe هذه المستويات على النموذج وواجهة REST وعروض القوائم والتقارير والتصدير. كما يُخفي CARD قيم كل حقل فوق
  المستوى 0 في صفوف سجل التغييرات (Version) الجديدة لسجل المعدات، مع الإبقاء على من غيّر الحقل ومتى.
- القيم التي ينسخها CARD من الأصل إلى نموذج المعدات لا تتضمن إلا الحقول التي يجوز للمستخدم قراءتها.
- تُخفى أرقام لوحة القيادة التي تستخدم السعر الداخلي عن المستخدمين الذين لا يستطيعون قراءة المستوى 2.
- **نقل المعدات**: حقول قرار التكلفة والفوترة والاسترداد في المستوى 1، ويقرؤها System Manager وCard Manager وAccounts
  Manager، ولا يكتبها أحد في النموذج (يضبطها إجراء القرار المالي).
- **تعبئة ديزل للمشروع**: حقول المراجعة في المستوى 1.

:::caution[مخطَّط له]
المبالغ في الكروت الشهرية غير مقيَّدة بالدور بعد: فكل من يستطيع قراءة الكارت يرى مبالغه. أما تقييد ظهور المبالغ في
الكروت الشهرية حسب الدور، وإعداد «إخفاء الأسعار عن دور» على الخادم، فمخطَّط لهما.
:::

### فصل المهام

المنفَّذ حاليًا:

- **احتياجات المعدات** — المشرف الذي اعتمد المراجعة، وكل من عدّل مسودتها، لا يجوز لهم اعتمادها نهائيًا.
- **القرار المالي للنقل** — لا يجوز أن يكون مدير الحسابات الذي يسجّله هو منشئ النقل أو محرّره أو معتمده.
- **سبب الإلغاء** — يتطلب إلغاء الكارت الشهري أو النقل أو تعبئة الديزل ذكر سبب، يُخزَّن ويُكتب تعليقًا على المستند.
- **تجاوزات قفل الفترة** تُسجَّل وتُكتب تعليقًا على المستند.

:::caution[مخطَّط له]
في الكروت الشهرية، قاعدة «من أنشأ الكارت أو أدخله لا يعتمده أبدًا» مخطَّط لها. واليوم يعتمد Card Manager أو System
Manager الكارت دون فحص لمنشئه.
:::

### الوصول إلى CARD Mobile

يُفتح CARD Mobile للمستخدمين الذين لديهم دور بوابة (Card Operator أو Card Supervisor أو Card Manager أو System
Manager) وموظف نشط مرتبط بالمستخدم؛ أما مستخدم Card User الذي ليس له دور بوابة فلا يفتح إلا الكتالوج. راجع
[CARD Mobile](/card/ar/features/card-mobile/).

## سير العمل

1. أنشئ مستخدمي ERPNext، واربط كل مشغّل بـ**موظف** نشط (معرّف المستخدم).
2. امنح كل مستخدم دور CARD المناسب لعمله، إضافة إلى أدوار ERPNext التي يحتاجها (مثل Accounts Manager للمحاسبين،
   وStock Manager لموظفي المخازن).
3. أضف **صلاحيات المستخدم على الشركة** للمستخدمين الذين يعملون لبعض الشركات فقط.
4. في الإعدادات، اضبط **دور تجاوز قفل الفترة** وأدوار تبويب «صلاحيات متقدمة».

## صفحات ذات صلة

- [الإعداد](/card/ar/getting-started/configuration/)
- [CARD Mobile](/card/ar/features/card-mobile/)
- [الفوترة والترحيل](/card/ar/features/invoicing-posting/)
- [احتياجات المعدات](/card/ar/features/equipment-needs/)
