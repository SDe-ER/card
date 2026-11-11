---
title: التطوير والمساهمة
description: كيفية تشغيل اختبارات CARD، والفحوص التي يجريها كل طلب دمج، وكيفية إصدار النسخ، وكيفية إبقاء هذا التوثيق محدَّثًا.
sidebar:
  order: 4
---

## نظرة عامة

يُطوَّر CARD علنًا على [GitHub](https://github.com/SDe-ER/card)، ويمر كل تغيير بطلب دمج (Pull Request) مع فحوص
تلقائية ومراجعة. توضح هذه الصفحة كيفية تشغيل الاختبارات محليًا، والفحوص التي يجريها كل طلب دمج، وكيفية إصدار
النسخ، وكيف يصل كل تغيير إلى هذا التوثيق.

## تشغيل الاختبارات

شغّل الاختبارات على موقع تطوير أو اختبار فقط، ولا تشغّلها أبدًا على موقع تشغيل فعلي:

```bash
bench --site <dev-site> set-config developer_mode 1
bench --site <dev-site> set-config allow_tests true
bench --site <dev-site> run-tests --app card
```

وهذه الأوامر نفسها التي يشغّلها نظام التكامل المستمر (CI):

```bash
pre-commit run --all-files
cd frontend && yarn install --frozen-lockfile && yarn type-check && yarn test && yarn build
```

## الفحوص في كل طلب دمج

| مسار العمل | ما يفحصه |
|---|---|
| CI | اختبارات وحدات CARD على Frappe وERPNext v16 مع نسبة التغطية؛ وفحص الأنواع والاختبارات والبناء في CARD Mobile |
| Linters | ‏`pre-commit` (ruff وprettier) وSemgrep بقواعد Frappe |
| CodeQL | فحص شيفرة JavaScript وPython، وأسبوعيًا أيضًا |
| PR Title | أن عنوان طلب الدمج يتبع صيغة Conventional Commits |
| Upgrade rehearsal | تجربة الترقية من إصدار سابق عند تغيّر الترقيعات أو أنواع المستندات أو البيانات الثابتة أو الخطافات |
| Docs site | بناء هذا الموقع، ونشره أيضًا من الفرع `main` |
| Release | إنشاء الإصدار على GitHub عند دفع وسم `v*` |

## المساهمة

1. افتح بلاغًا (Issue) يصف التغيير.
2. اعمل على فرع يبدأ بـ `feat/` أو `fix/` أو `docs/`، ولا تعمل أبدًا على `main`.
3. أضف الاختبارات أو حدّثها، وأبقِ `pre-commit` ناجحًا.
4. سجّل التغيير في `CHANGELOG.md` تحت `[Unreleased]` وفي سجل المزايا.
5. أضف التغيير إلى [ما الجديد](/card/ar/releases/whats-new/) بالعربية والإنجليزية (انظر أدناه).
6. افتح طلب دمج بعنوان يتبع صيغة [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

تحتاج كل خطوة في الطريق إلى التشغيل الفعلي موافقة مستقلة: الحفظ المحلي (commit) ليس رفعًا، والدمج ليس إصدارًا،
والإصدار ليس تشغيلًا. راجع [CONTRIBUTING.md](https://github.com/SDe-ER/card/blob/main/CONTRIBUTING.md)
و[ميثاق السلوك](https://github.com/SDe-ER/card/blob/main/CODE_OF_CONDUCT.md)
و[سياسة التغيير والإصدارات والتراجع](https://github.com/SDe-ER/card/blob/main/docs/governance/CHANGE-VERSIONING-ROLLBACK-POLICY.md)
(بالإنجليزية).

## إبقاء التوثيق محدَّثًا

يوجد الموقع في المجلد `website/` من المستودع، ويُعاد بناؤه ونشره تلقائيًا من الفرع `main` كلما تغيّرت شيفرة CARD
أو التوثيق.

| عندما تغيّر… | حدّث |
|---|---|
| أي شيء يلاحظه المستخدمون أو المسؤولون | أضف بندًا إلى [ما الجديد](/card/ar/releases/whats-new/) بالإنجليزية (`website/src/content/docs/releases/whats-new.md`) وبالعربية (`website/src/content/docs/ar/releases/whats-new.md`) |
| نوع مستند أو حقلًا أو تقريرًا أو دالة API | شغّل `cd website && npm run generate` واحفظ صفحات [المرجع](/card/ar/reference/) المولَّدة |
| سلوك ميزة | صفحتها تحت `website/src/content/docs/` ونسختها العربية تحت `.../ar/` |
| شاشة لها صورة | أعد التقاطها من الموقع التجريبي بأدوات `website/scripts/screenshots/` (بيانات وهمية فقط) |

قواعد الكتابة لكل صفحة موجودة في
[`website/WRITING-GUIDE.md`](https://github.com/SDe-ER/card/blob/main/website/WRITING-GUIDE.md). ولمعاينة الموقع
محليًا:

```bash
cd website
npm ci
npm run dev
```

## الإصدارات

يتبع CARD [الترقيم الدلالي للإصدارات](https://semver.org/lang/ar/)، ولكل إصدار ملاحظات خاصة به، وكل الإصدارات
مدرجة في [ما الجديد](/card/ar/releases/whats-new/).

## الأمان

أبلغ عن الثغرات الأمنية بشكل خاص كما هو موضح في
[SECURITY.md](https://github.com/SDe-ER/card/blob/main/SECURITY.md)، ولا تفتح بلاغات عامة بشأنها.

## ذو صلة

- [التثبيت](/card/ar/getting-started/installation/)
- [الأدوار والصلاحيات](/card/ar/features/roles-permissions/)
- [ما الجديد](/card/ar/releases/whats-new/)
