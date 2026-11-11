#!/usr/bin/env python3
"""Place captured screenshots under their <!-- screenshot: name --> markers in the docs pages.

The marker stays in the page; the line after it holds the image and is rewritten on every run, so re-running after a
new capture is safe. English pages use src/assets/screenshots/en/, Arabic pages src/assets/screenshots/ar/.
A marker whose image does not exist yet is left without an image.
"""

import os
import re
from pathlib import Path

WEBSITE = Path(__file__).resolve().parents[2]
DOCS = WEBSITE / "src" / "content" / "docs"
SHOTS = WEBSITE / "src" / "assets" / "screenshots"
MARK = re.compile(r"^<!-- screenshot: ([a-z0-9-]+) -->\s*$")

CAPTIONS = {
	"introduction-workspace": ("The CARD workspace", "مساحة عمل CARD"),
	"workspace-dashboard-overview": (
		"Workspace number cards and charts",
		"بطاقات الأرقام والرسوم في مساحة العمل",
	),
	"workspace-dashboard-shortcuts": ("Shortcuts and report links", "الاختصارات وروابط التقارير"),
	"languages-workspace-arabic": ("The CARD workspace in Arabic", "مساحة عمل CARD باللغة العربية"),
	"reports-overview-sidebar": ("Reports in the CARD workspace", "التقارير في مساحة عمل CARD"),
	"configuration-card-settings": ("Card Settings", "إعدادات الكارت"),
	"roles-permissions-role-list": ("The CARD roles", "أدوار CARD"),
	"notifications-alerts-bell": ("Notifications in the desk", "الإشعارات في الواجهة"),
	"equipment-form": ("A rented machine in the equipment form", "معدة مستأجرة في نموذج المعدات"),
	"equipment-create-from-asset": ("The equipment list", "قائمة المعدات"),
	"units-components-unit-form": ("A crusher in the equipment form", "كسارة في نموذج المعدات"),
	"assignments-locations-assignment-form": ("An equipment assignment", "تعيين معدة لمشروع"),
	"assignments-locations-location-history": (
		"Equipment Location History report",
		"تقرير سجل مواقع المعدات",
	),
	"operations-location-history": ("Equipment Location History report", "تقرير سجل مواقع المعدات"),
	"transport-form": ("An equipment transport", "عملية نقل معدات"),
	"transport-print": ("Transport print format", "قالب طباعة النقل"),
	"transport-accounting-review": ("Transport Accounting Review report", "تقرير مراجعة محاسبة النقل"),
	"tool-custody-form": ("A tool custody handover", "تسليم عهدة أداة"),
	"tool-custody-screen": ("The tool custody screen", "شاشة عهدة الأدوات"),
	"daily-logs-form": ("A daily log with its rows", "يومية تشغيل بصفوفها"),
	"daily-logs-generation-result": ("Daily log rows", "صفوف اليومية"),
	"monthly-cards-form": ("A monthly card", "كارت تشغيل شهري"),
	"adjustments-card-table": (
		"Additions and deductions on a monthly card",
		"الإضافات والخصومات في الكارت الشهري",
	),
	"print-formats-monthly-card": ("Monthly card print format", "قالب طباعة الكارت الشهري"),
	"rate-agreements-form": ("A rate agreement", "اتفاقية أسعار"),
	"invoicing-posting-page": ("The CARD Monthly Posting page", "صفحة الترحيل الشهري"),
	"invoicing-posting-preview": ("Monthly posting preview", "معاينة الترحيل الشهري"),
	"suppliers-customers-registry": ("The equipment supplier registry", "سجل موردي المعدات"),
	"suppliers-customers-figures": ("Supplier figures", "أرقام المورد"),
	"suppliers-customers-a4": ("Equipment Supplier Statement", "كشف حساب مورد المعدات"),
	"statements-supplier-statement": ("Equipment Supplier Statement report", "تقرير كشف حساب مورد المعدات"),
	"statements-settlement-status": ("Card Settlement Status report", "تقرير حالة تسوية الكروت"),
	"diesel-form": ("A project diesel fill", "تعبئة ديزل لمشروع"),
	"diesel-meter-photos": ("Meter readings on a diesel fill", "قراءات العداد في تعبئة الديزل"),
	"diesel-analysis": ("Equipment Diesel Analysis report", "تقرير تحليل ديزل المعدات"),
	"diesel-invoice-reconciliation": ("Diesel Invoice Reconciliation report", "تقرير مطابقة فواتير الديزل"),
	"meter-readings-form": ("An equipment meter reading", "قراءة عداد معدة"),
	"meter-readings-reconciliation": ("Equipment Meter Reconciliation report", "تقرير مطابقة عدادات المعدات"),
	"operations-equipment-downtime": ("Equipment Downtime report", "تقرير توقف المعدات"),
	"maintenance-parts-catalog": ("Equipment models", "موديلات المعدات"),
	"maintenance-parts-fitment": ("Parts fitment records", "سجلات توافق قطع الغيار"),
	"asset-mapping-review": ("Asset Mapping Review report", "تقرير مراجعة ربط الأصول"),
	"equipment-needs-review": ("An equipment needs request", "طلب احتياجات معدة"),
	"equipment-needs-portal": ("The equipment needs page", "صفحة احتياجات المعدات"),
	"accounting-partial-margin": ("Equipment Partial Margin report", "تقرير الهامش الجزئي للمعدات"),
	"accounting-posting-source-integrity": ("Posting Source Integrity report", "تقرير سلامة مصادر الترحيل"),
	"card-mobile-home": ("CARD Mobile home screen", "الشاشة الرئيسية في CARD Mobile"),
	"card-mobile-new-request": ("CARD Mobile requests", "الطلبات في CARD Mobile"),
}


def main():
	placed = missing = 0
	for md in sorted(DOCS.rglob("*.md")):
		rel = md.relative_to(DOCS)
		lang = "ar" if rel.parts[0] == "ar" else "en"
		lines = md.read_text(encoding="utf-8").split("\n")
		out, i, changed = [], 0, False
		while i < len(lines):
			line = lines[i]
			out.append(line)
			m = MARK.match(line)
			if not m:
				i += 1
				continue
			name = m.group(1)
			nxt = lines[i + 1] if i + 1 < len(lines) else ""
			skip = 0
			if nxt.startswith("!["):
				skip = 1
				if i + 2 < len(lines) and lines[i + 2].startswith("*") and lines[i + 2].endswith("*"):
					skip = 2
			img = SHOTS / lang / f"{name}.webp"
			if img.exists():
				cap = CAPTIONS.get(name, (name.replace("-", " ").capitalize(),) * 2)[0 if lang == "en" else 1]
				path = os.path.relpath(img, md.parent).replace(os.sep, "/")
				new = f"![{cap}]({path})"
				if not skip or nxt != new:
					changed = True
				out.append(new)
				out.append(f"*{cap}*")
				placed += 1
			else:
				missing += 1
				if skip:
					changed = True
			i += 1 + skip
		if changed:
			md.write_text("\n".join(out), encoding="utf-8")
	print(f"placed {placed} screenshots, {missing} markers without an image")


if __name__ == "__main__":
	main()
