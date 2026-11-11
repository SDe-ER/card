#!/usr/bin/env python3
"""Generate the CARD documentation "Reference" section from the app's own code.

Reads, from the repository root:
  - card/card/doctype/*/*.json   -> one page per DocType (fields grouped by tab and section)
  - card/card/report/*/*.{json,js} -> one page listing every report, its filters and roles
  - card/**/*.py (AST)           -> one page listing every @frappe.whitelist endpoint
  - card/locale/ar.po            -> Arabic labels for the Arabic pages

Writes English pages to website/src/content/docs/reference/ and Arabic pages to
website/src/content/docs/ar/reference/. The pages are generated: edit the code, not the pages.

Usage:
  python3 scripts/generate_reference.py          # write the pages
  python3 scripts/generate_reference.py --check  # exit 1 if the committed pages are out of date

Standard library only, so it runs in CI without installing anything.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

WEBSITE = Path(__file__).resolve().parent.parent
ROOT = WEBSITE.parent
APP = ROOT / "card"
DOCS = WEBSITE / "src" / "content" / "docs"
OUT = {"en": DOCS / "reference", "ar": DOCS / "ar" / "reference"}
LAYOUT = {"Section Break", "Column Break", "Tab Break"}
GENERATED_NOTE = {
	"en": "This page is generated from the CARD source code on every build. Edit the code, not this page.",
	"ar": "تُولَّد هذه الصفحة من الشيفرة المصدرية لـ CARD في كل عملية بناء. عدّل الشيفرة لا هذه الصفحة.",
}

T = {
	"en": {
		"ref": "Reference",
		"ref_desc": "Generated reference for every CARD DocType, report and API endpoint.",
		"doctypes": "DocTypes",
		"reports": "Reports",
		"api": "API endpoints",
		"label": "Label",
		"field": "Field name",
		"type": "Type",
		"options": "Options / link",
		"req": "Required",
		"yes": "Yes",
		"hidden": "hidden",
		"read_only": "read only",
		"main": "Main",
		"kind": "Kind",
		"child": "Child table (rows inside another document)",
		"single": "Single (one settings record)",
		"submittable": "Submittable (Draft → Submitted → Cancelled)",
		"master": "Document",
		"module": "Module",
		"fields": "Fields",
		"perms": "Permissions",
		"role": "Role",
		"rights": "Rights",
		"no_perms": "No own permissions: access follows the parent document.",
		"used_in": "Child tables",
		"filters": "Filters",
		"roles": "Roles",
		"ref_doctype": "Based on",
		"report_type": "Type",
		"no_filters": "No filters.",
		"path": "Method path",
		"methods": "HTTP methods",
		"args": "Arguments",
		"none": "none",
		"guest": "Guest access",
		"module_h": "Module",
		"count_dt": "DocTypes",
		"count_rp": "Reports",
		"count_api": "API endpoints",
		"summary": "Summary",
		"intro": "This section is built from the code itself, so it always matches the current version of CARD. "
		"For explanations, workflows and examples, see the Features, Reports and API Reference sections.",
		"desc_doctype": "Fields, layout and permissions of the {name} DocType.",
		"desc_reports": "Every CARD report with its filters and the roles that can run it.",
		"desc_api": "Every whitelisted CARD API method with its HTTP methods and arguments.",
		"open": "Open in Desk",
	},
	"ar": {
		"ref": "المرجع",
		"ref_desc": "مرجع مولَّد لكل أنواع المستندات والتقارير ونقاط الـ API في CARD.",
		"doctypes": "أنواع المستندات",
		"reports": "التقارير",
		"api": "نقاط الـ API",
		"label": "التسمية",
		"field": "اسم الحقل",
		"type": "النوع",
		"options": "الخيارات / الربط",
		"req": "إلزامي",
		"yes": "نعم",
		"hidden": "مخفي",
		"read_only": "للقراءة فقط",
		"main": "الرئيسي",
		"kind": "النوع",
		"child": "جدول فرعي (صفوف داخل مستند آخر)",
		"single": "مفرد (سجل إعدادات واحد)",
		"submittable": "قابل للتقديم (مسودة ← مقدَّم ← ملغى)",
		"master": "مستند",
		"module": "الوحدة",
		"fields": "الحقول",
		"perms": "الصلاحيات",
		"role": "الدور",
		"rights": "الحقوق",
		"no_perms": "لا صلاحيات مستقلة: يتبع الوصول المستند الأب.",
		"used_in": "الجداول الفرعية",
		"filters": "عوامل التصفية",
		"roles": "الأدوار",
		"ref_doctype": "مبني على",
		"report_type": "النوع",
		"no_filters": "لا توجد عوامل تصفية.",
		"path": "مسار الدالة",
		"methods": "طرق HTTP",
		"args": "المعاملات",
		"none": "لا يوجد",
		"guest": "وصول الزائر",
		"module_h": "الوحدة",
		"count_dt": "أنواع المستندات",
		"count_rp": "التقارير",
		"count_api": "نقاط الـ API",
		"summary": "الملخص",
		"intro": "يُبنى هذا القسم من الشيفرة نفسها، لذا يطابق دائمًا الإصدار الحالي من CARD. "
		"وللشرح وسير العمل والأمثلة راجع أقسام المزايا والتقارير ومرجع الـ API.",
		"desc_doctype": "حقول نوع المستند {name} وتخطيطه وصلاحياته.",
		"desc_reports": "كل تقارير CARD مع عوامل التصفية والأدوار التي يمكنها تشغيلها.",
		"desc_api": "كل دوال الـ API المسموح باستدعائها في CARD مع طرق HTTP والمعاملات.",
		"open": "فتح في الواجهة",
	},
}

RIGHTS = [
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"report",
	"export",
	"print",
	"email",
]
RIGHTS_AR = {
	"read": "قراءة",
	"write": "كتابة",
	"create": "إنشاء",
	"delete": "حذف",
	"submit": "تقديم",
	"cancel": "إلغاء",
	"amend": "تعديل",
	"report": "تقرير",
	"export": "تصدير",
	"print": "طباعة",
	"email": "بريد",
}


# --------------------------------------------------------------------------- translations
def load_po(path: Path) -> dict[str, str]:
	"""Parse a gettext .po file into {msgid: msgstr} (no context, non-empty translations only)."""
	if not path.exists():
		return {}
	out: dict[str, str] = {}
	cur: dict[str, str] = {}
	key = None

	def unq(s: str) -> str:
		return json.loads(s) if s.startswith('"') else s

	def flush():
		mid, mstr = cur.get("msgid", ""), cur.get("msgstr", "")
		if mid and mstr and "msgctxt" not in cur:
			out.setdefault(mid, mstr)

	for raw in path.read_text(encoding="utf-8").splitlines():
		line = raw.strip()
		if not line or line.startswith("#"):
			if cur:
				flush()
				cur, key = {}, None
			continue
		m = re.match(r'^(msgctxt|msgid|msgstr)\s+(".*")$', line)
		if m:
			key = m.group(1)
			cur[key] = unq(m.group(2))
		elif line.startswith('"') and key:
			cur[key] += unq(line)
	if cur:
		flush()
	return out


AR = load_po(APP / "locale" / "ar.po")

# Standard Frappe / ERPNext terms that CARD's own ar.po does not carry (CARD's file holds CARD strings only).
# ar.po always wins; this list is the fallback for core labels, link targets and role names.
CORE_AR = {
	"Account": "الحساب",
	"Accounts Manager": "مدير الحسابات",
	"Active": "نشط",
	"Amended From": "معدّل من",
	"Amount": "المبلغ",
	"Asset": "الأصل",
	"Asset Category": "فئة الأصل",
	"Billing": "الفوترة",
	"Brand": "العلامة التجارية",
	"Company": "الشركة",
	"Component": "المكوّن",
	"Connections": "الارتباطات",
	"Cost Center": "مركز التكلفة",
	"Currency": "العملة",
	"Date": "التاريخ",
	"Day": "اليوم",
	"Days": "الأيام",
	"Defaults": "الافتراضيات",
	"Description": "الوصف",
	"Disabled": "معطّل",
	"Documents": "المستندات",
	"Downtime": "التوقف",
	"Employee": "الموظف",
	"Enabled": "مفعّل",
	"Exit": "الخروج",
	"Image": "الصورة",
	"In stock": "في المخزون",
	"Integrity": "السلامة",
	"Item": "الصنف",
	"Item Tax Template": "قالب ضريبة الصنف",
	"Items": "الأصناف",
	"Links": "الروابط",
	"Material Request": "طلب المواد",
	"Meter": "العداد",
	"Mode of Payment": "طريقة الدفع",
	"Model": "الموديل",
	"Month": "الشهر",
	"Movement": "الحركة",
	"Notifications": "الإشعارات",
	"Operations": "التشغيل",
	"Operator": "المشغّل",
	"Origin": "المصدر",
	"Owner": "المالك",
	"Party": "الطرف",
	"Policy": "السياسة",
	"Posted": "مرحَّل",
	"Pricing": "التسعير",
	"Project": "المشروع",
	"Purchase Invoice": "فاتورة الشراء",
	"Purchase Taxes and Charges Template": "قالب ضرائب ورسوم الشراء",
	"Quantity": "الكمية",
	"Rate": "السعر",
	"Reason": "السبب",
	"Role": "الدور",
	"Route": "المسار",
	"Sales Invoice": "فاتورة المبيعات",
	"Sales Taxes and Charges Template": "قالب ضرائب ورسوم المبيعات",
	"Sequence": "التسلسل",
	"Show": "عرض",
	"Source": "المصدر",
	"Sources": "المصادر",
	"Statistics": "الإحصاءات",
	"Stock Entry": "قيد المخزون",
	"Stock Manager": "مدير المخزون",
	"System Manager": "مدير النظام",
	"Taxable": "خاضع للضريبة",
	"Totals": "الإجماليات",
	"UOM": "وحدة القياس",
	"User": "المستخدم",
	"View": "العرض",
	"Warehouse": "المستودع",
	"Warnings": "التحذيرات",
	"Year": "السنة",
	"Card Manager": "مدير الكروت",
	"Card Supervisor": "مشرف الكروت",
	"Card User": "مستخدم الكروت",
	"Card Operator": "مشغّل الكروت",
	"Card Reviewer": "مراجع الكروت",
	"Card Adjustment Type": "نوع الإضافة والخصم",
	"Card Consumption Rate": "معدل الاستهلاك",
	"Card Diesel Price": "سعر الديزل",
	"Card Equipment Component": "مكوّن المعدة",
	"Card Monthly Card Adjustment": "إضافة أو خصم الكارت الشهري",
	"Card Monthly Card Day": "يوم الكارت الشهري",
	"Card Project Transport Price": "سعر النقل للمشروع",
	"Card Type Consumption Rate": "معدل استهلاك النوع",
	"GL Posting Source": "مصدر الترحيل",
	"Asset Mapping Review": "مراجعة ربط الأصول",
	"Equipment Meter Reconciliation": "مطابقة عدادات المعدات",
}


def tr(text: str, lang: str) -> str:
	if lang == "en" or not text:
		return text
	return AR.get(text) or CORE_AR.get(text, text)


# --------------------------------------------------------------------------- helpers
def slug(name: str) -> str:
	return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def md_cell(text) -> str:
	s = str(text if text is not None else "")
	s = s.replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()
	return s


def code(text: str) -> str:
	text = str(text).replace("|", "\\|")
	return f"`{text}`" if text else ""


def frontmatter(title: str, description: str, order: int | None = None, label: str | None = None) -> str:
	lines = [
		"---",
		f"title: {json.dumps(title, ensure_ascii=False)}",
		f"description: {json.dumps(description, ensure_ascii=False)}",
	]
	lines.append("editUrl: false")
	if order is not None or label:
		lines.append("sidebar:")
		if order is not None:
			lines.append(f"  order: {order}")
		if label:
			lines.append(f"  label: {json.dumps(label, ensure_ascii=False)}")
	lines.append("---")
	return "\n".join(lines) + "\n"


def note(lang: str) -> str:
	return f":::note\n{GENERATED_NOTE[lang]}\n:::\n"


def link(lang: str, path: str) -> str:
	return f"/card/{'ar/' if lang == 'ar' else ''}{path}"


# --------------------------------------------------------------------------- DocTypes
def load_doctypes() -> list[dict]:
	out = []
	for f in sorted((APP / "card" / "doctype").glob("*/*.json")):
		if f.stem != f.parent.name:
			continue
		d = json.loads(f.read_text(encoding="utf-8"))
		if d.get("doctype") == "DocType":
			out.append(d)
	return out


def kind(d: dict, lang: str) -> str:
	t = T[lang]
	if d.get("istable"):
		return t["child"]
	if d.get("issingle"):
		return t["single"]
	if d.get("is_submittable"):
		return t["submittable"]
	return t["master"]


def doctype_page(d: dict, lang: str, names: set[str]) -> str:
	t = T[lang]
	name = d["name"]
	title = tr(name, lang)
	parts = [frontmatter(title, t["desc_doctype"].format(name=title), label=title), note(lang)]
	if lang == "ar" and title != name:
		parts.append(f"**{name}**\n")
	desc = d.get("description")
	if desc:
		parts.append(md_cell(tr(desc, lang)) + "\n")
	meta = f"| | |\n|---|---|\n| {t['kind']} | {kind(d, lang)} |\n| {t['module']} | {md_cell(d.get('module', ''))} |\n"
	if not d.get("istable"):
		meta += f"| {t['open']} | `/app/{slug(name)}` |\n"
	parts.append(meta)

	# fields grouped by tab / section
	parts.append(f"\n## {t['fields']}\n")
	tab, rows, out_rows = None, [], []

	def flush_rows():
		if rows:
			out_rows.append(
				f"| {t['label']} | {t['field']} | {t['type']} | {t['options']} | {t['req']} |\n|---|---|---|---|---|\n"
				+ "\n".join(rows)
				+ "\n"
			)
			rows.clear()

	for fld in d.get("fields", []):
		ft = fld.get("fieldtype")
		if ft == "Tab Break":
			flush_rows()
			tab = tr(fld.get("label") or "", lang) or fld["fieldname"]
			out_rows.append(f"\n### {md_cell(tab)}\n")
			continue
		if ft == "Section Break":
			flush_rows()
			lbl = tr(fld.get("label") or "", lang)
			if lbl:
				out_rows.append(f"\n**{md_cell(lbl)}**\n")
			continue
		if ft in LAYOUT or ft in {"HTML", "Button", "Fold", "Heading"}:
			continue
		label = tr(fld.get("label") or "", lang) or fld["fieldname"]
		opts = fld.get("options") or ""
		if ft in {"Link", "Table", "Table MultiSelect"} and opts in names:
			o = f"[{md_cell(tr(opts, lang))}]({link(lang, 'reference/doctypes/' + slug(opts) + '/')})"
		elif ft == "Select" and opts:
			vals = [tr(v, lang) for v in opts.split("\n") if v.strip()]
			o = md_cell(" · ".join(vals))
		elif opts:
			o = md_cell(tr(opts, lang) if ft in {"Link", "Table"} else opts)
		else:
			o = ""
		flags = []
		if fld.get("hidden"):
			flags.append(t["hidden"])
		if fld.get("read_only"):
			flags.append(t["read_only"])
		lbl = md_cell(label) + (f" <small>({', '.join(flags)})</small>" if flags else "")
		rows.append(
			f"| {lbl} | {code(fld['fieldname'])} | {ft} | {o} | {t['yes'] if fld.get('reqd') else ''} |"
		)
	flush_rows()
	parts.extend(out_rows)

	children = [
		f.get("options")
		for f in d.get("fields", [])
		if f.get("fieldtype") == "Table" and f.get("options") in names
	]
	if children:
		parts.append(f"\n## {t['used_in']}\n")
		for c in dict.fromkeys(children):
			parts.append(f"- [{tr(c, lang)}]({link(lang, 'reference/doctypes/' + slug(c) + '/')})")
		parts.append("")

	parts.append(f"\n## {t['perms']}\n")
	perms = d.get("permissions") or []
	if not perms:
		parts.append(t["no_perms"] + "\n")
	else:
		parts.append(f"| {t['role']} | {t['rights']} |\n|---|---|")
		for p in perms:
			rights = [r for r in RIGHTS if p.get(r)]
			if lang == "ar":
				rights = [RIGHTS_AR[r] for r in rights]
			lvl = p.get("permlevel") or 0
			role = tr(p.get("role", ""), lang) + (f" (permlevel {lvl})" if lvl else "")
			parts.append(f"| {md_cell(role)} | {', '.join(rights)} |")
		parts.append("")
	return "\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- Reports
FILTER_RE = re.compile(r"\{[^{}]*?fieldname:\s*\"([^\"]+)\"[^{}]*?\}", re.S)


def report_filters(js: Path) -> list[dict]:
	if not js.exists():
		return []
	src = js.read_text(encoding="utf-8")
	out = []
	# walk top-level filter objects: find each fieldname and the nearby label / fieldtype / reqd
	for m in re.finditer(r"fieldname:\s*\"([^\"]+)\"", src):
		chunk = src[m.start() : m.start() + 600]
		end = chunk.find("\n\t\t},")
		chunk = chunk if end < 0 else chunk[:end]
		lab = re.search(r"label:\s*__\(\s*\"([^\"]+)\"", chunk)
		ft = re.search(r"fieldtype:\s*\"([^\"]+)\"", chunk)
		opt = re.search(r"options:\s*\"([^\"]+)\"", chunk)
		req = re.search(r"reqd:\s*1", chunk)
		out.append(
			{
				"fieldname": m.group(1),
				"label": lab.group(1) if lab else m.group(1),
				"fieldtype": ft.group(1) if ft else "",
				"options": opt.group(1) if opt and (ft and ft.group(1) == "Link") else "",
				"reqd": bool(req),
			}
		)
	return out


def load_reports() -> list[dict]:
	out = []
	for f in sorted((APP / "card" / "report").glob("*/*.json")):
		if f.stem != f.parent.name:
			continue
		r = json.loads(f.read_text(encoding="utf-8"))
		if r.get("doctype") != "Report":
			continue
		r["_filters"] = report_filters(f.with_suffix(".js"))
		out.append(r)
	return out


def reports_page(reports: list[dict], lang: str, names: set[str]) -> str:
	t = T[lang]
	parts = [frontmatter(t["reports"], t["desc_reports"], order=2), note(lang)]
	parts.append(f"| {t['reports']} | {t['ref_doctype']} | {t['roles']} |\n|---|---|---|")
	for r in reports:
		nm = r["name"]
		rd = r.get("ref_doctype") or ""
		rd_md = (
			f"[{tr(rd, lang)}]({link(lang, 'reference/doctypes/' + slug(rd) + '/')})"
			if rd in names
			else md_cell(tr(rd, lang))
		)
		roles = ", ".join(tr(x["role"], lang) for x in r.get("roles", []))
		parts.append(f"| [{md_cell(tr(nm, lang))}](#{slug(nm)}) | {rd_md} | {md_cell(roles)} |")
	parts.append("")
	for r in reports:
		nm = r["name"]
		title = tr(nm, lang)
		parts.append(f'\n<h2 id="{slug(nm)}">{md_cell(title)}</h2>\n')
		if lang == "ar" and title != nm:
			parts.append(f"**{nm}**\n")
		parts.append(f"- {t['report_type']}: {r.get('report_type', '')}")
		rd = r.get("ref_doctype")
		if rd:
			parts.append(f"- {t['ref_doctype']}: {tr(rd, lang)}")
		parts.append(
			f"- {t['roles']}: {', '.join(tr(x['role'], lang) for x in r.get('roles', [])) or t['none']}\n"
		)
		fl = r["_filters"]
		if not fl:
			parts.append(t["no_filters"] + "\n")
			continue
		parts.append(f"| {t['label']} | {t['field']} | {t['type']} | {t['req']} |\n|---|---|---|---|")
		for x in fl:
			typ = x["fieldtype"] + (f" → {tr(x['options'], lang)}" if x["options"] else "")
			parts.append(
				f"| {md_cell(tr(x['label'], lang))} | {code(x['fieldname'])} | {md_cell(typ)} | {t['yes'] if x['reqd'] else ''} |"
			)
		parts.append("")
	return "\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- API
INTERNAL_REF = re.compile(
	r"\b(?:FR|WS|WP|R|O|D|Q)-[0-9A-Za-z]+(?:[/-][0-9A-Za-z]+)*\b|#\d+(?:/[A-Z]+-[0-9A-Za-z-]+)*"
)


def clean_doc(text: str) -> str:
	"""Drop internal tracking references (registry ids, issue numbers, plan codes) from a docstring summary."""
	t = INTERNAL_REF.sub("", text)
	t = re.sub(r"\(\s*[;,]?\s*(?:[;,]\s*)*\)", "", t)  # empty or comma-only parentheses left behind
	t = re.sub(r"\(\s*[;,]\s*", "(", t)
	t = re.sub(r"\s*[;,]\s*\)", ")", t)
	t = re.sub(r"^[\s:,;]+", "", t)
	t = re.sub(r"\s+([:,;.])", r"\1", t)
	t = re.sub(r"\s{2,}", " ", t).strip()
	return t[:1].upper() + t[1:] if t else t


def whitelist_info(dec) -> dict | None:
	fn = dec.func if isinstance(dec, ast.Call) else dec
	name = ast.unparse(fn)
	if name not in {"frappe.whitelist", "whitelist"}:
		return None
	info = {"methods": [], "allow_guest": False}
	if isinstance(dec, ast.Call):
		for kw in dec.keywords:
			if kw.arg == "methods":
				try:
					info["methods"] = list(ast.literal_eval(kw.value))
				except Exception:
					info["methods"] = [ast.unparse(kw.value)]
			elif kw.arg == "allow_guest":
				try:
					info["allow_guest"] = bool(ast.literal_eval(kw.value))
				except Exception:
					info["allow_guest"] = True
	return info


def load_api() -> list[dict]:
	out = []
	for py in sorted(APP.rglob("*.py")):
		rel = py.relative_to(ROOT)
		if "tests" in rel.parts or py.name.startswith("test_") or "patches" in rel.parts:
			continue
		try:
			tree = ast.parse(py.read_text(encoding="utf-8"))
		except SyntaxError:
			continue
		module = ".".join(rel.with_suffix("").parts)
		for node in tree.body:
			if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			info = None
			for dec in node.decorator_list:
				info = whitelist_info(dec) or info
			if info is None:
				continue
			args = []
			a = node.args
			defaults = [None] * (len(a.args) - len(a.defaults)) + list(a.defaults)
			for arg, default in zip(a.args, defaults, strict=True):
				if arg.arg in {"self", "cls"}:
					continue
				ann = ast.unparse(arg.annotation) if arg.annotation else ""
				s = (
					arg.arg
					+ (f": {ann}" if ann else "")
					+ (f" = {ast.unparse(default)}" if default is not None else "")
				)
				args.append(s)
			for arg, default in zip(a.kwonlyargs, a.kw_defaults, strict=True):
				ann = ast.unparse(arg.annotation) if arg.annotation else ""
				args.append(
					arg.arg
					+ (f": {ann}" if ann else "")
					+ (f" = {ast.unparse(default)}" if default is not None else "")
				)
			doc = clean_doc((ast.get_docstring(node) or "").strip().split("\n\n")[0].replace("\n", " "))
			out.append(
				{
					"path": f"{module}.{node.name}",
					"module": module,
					"methods": info["methods"],
					"guest": info["allow_guest"],
					"args": args,
					"doc": doc,
				}
			)
	return out


def api_page(api: list[dict], lang: str) -> str:
	t = T[lang]
	parts = [frontmatter(t["api"], t["desc_api"], order=3), note(lang)]
	by_mod: dict[str, list[dict]] = {}
	for e in api:
		by_mod.setdefault(e["module"], []).append(e)
	parts.append(f"| {t['module_h']} | {t['count_api']} |\n|---|---|")
	for m, es in by_mod.items():
		parts.append(f"| [{code(m)}](#{slug(m)}) | {len(es)} |")
	parts.append("")
	for m, es in by_mod.items():
		parts.append(f'\n<h2 id="{slug(m)}"><code>{m}</code></h2>\n')
		parts.append(f"| {t['path']} | {t['methods']} | {t['args']} |\n|---|---|---|")
		for e in es:
			methods = ", ".join(e["methods"]) or "GET, POST"
			if e["guest"]:
				methods += f" ({t['guest']})"
			args = "<br/>".join(code(x) for x in e["args"]) or t["none"]
			parts.append(f"| {code(e['path'])} | {methods} | {args} |")
		parts.append("")
		docs = [e for e in es if e["doc"]]
		if docs and lang == "en":
			for e in docs:
				parts.append(f"- {code(e['path'].rsplit('.', 1)[1])} — {md_cell(e['doc'])}")
			parts.append("")
	return "\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- index
def index_page(lang: str, n_dt: int, n_rp: int, n_api: int, doctypes: list[dict]) -> str:
	t = T[lang]
	parts = [frontmatter(t["ref"], t["ref_desc"], order=1, label=t["summary"]), note(lang), t["intro"] + "\n"]
	parts.append(
		f"| | |\n|---|---|\n"
		f"| [{t['count_dt']}]({link(lang, 'reference/doctypes/' + slug(doctypes[0]['name']) + '/')}) | {n_dt} |\n"
		f"| [{t['count_rp']}]({link(lang, 'reference/reports/')}) | {n_rp} |\n"
		f"| [{t['count_api']}]({link(lang, 'reference/api-endpoints/')}) | {n_api} |\n"
	)
	parts.append(f"\n## {t['doctypes']}\n")
	parts.append(f"| {t['doctypes']} | {t['kind']} |\n|---|---|")
	for d in doctypes:
		parts.append(
			f"| [{md_cell(tr(d['name'], lang))}]({link(lang, 'reference/doctypes/' + slug(d['name']) + '/')}) | {kind(d, lang)} |"
		)
	return "\n".join(parts).rstrip() + "\n"


# --------------------------------------------------------------------------- main
def build() -> dict[Path, str]:
	doctypes = load_doctypes()
	names = {d["name"] for d in doctypes}
	reports = load_reports()
	api = load_api()
	files: dict[Path, str] = {}
	for lang, out in OUT.items():
		files[out / "index.md"] = index_page(lang, len(doctypes), len(reports), len(api), doctypes)
		files[out / "reports.md"] = reports_page(reports, lang, names)
		files[out / "api-endpoints.md"] = api_page(api, lang)
		for d in doctypes:
			files[out / "doctypes" / f"{slug(d['name'])}.md"] = doctype_page(d, lang, names)
	return files


def main() -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("--check", action="store_true", help="fail if the committed pages are out of date")
	args = ap.parse_args()
	files = build()
	existing = {p for out in OUT.values() if out.exists() for p in out.rglob("*.md")}
	stale = [p for p, txt in files.items() if not p.exists() or p.read_text(encoding="utf-8") != txt]
	extra = sorted(existing - set(files))
	if args.check:
		if stale or extra:
			for p in stale:
				print(f"out of date: {p.relative_to(ROOT)}")
			for p in extra:
				print(f"no longer generated: {p.relative_to(ROOT)}")
			print("Run: cd website && npm run generate", file=sys.stderr)
			return 1
		print(f"reference pages up to date ({len(files)} files)")
		return 0
	for p in extra:
		p.unlink()
	for p, txt in files.items():
		p.parent.mkdir(parents=True, exist_ok=True)
		p.write_text(txt, encoding="utf-8")
	print(f"wrote {len(files)} reference pages ({len(stale)} changed, {len(extra)} removed)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
