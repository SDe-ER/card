# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""F.8: the app's print fonts are part of the app (owner 2026-10-14).

wkhtmltopdf's Qt engine cannot SHAPE Arabic from @font-face webfonts — complex
scripts render only from fontconfig (system/user) fonts. So the bundled Noto
faces (card/public/fonts, OFL) are installed into the bench user's ~/.fonts on
install/migrate: user-level, no sudo, idempotent, best-effort (a failure never
breaks migrate — it is logged and the PDF falls back to DejaVu)."""

import os
import shutil
import subprocess

import frappe


def ensure_fonts():
	try:
		src = os.path.join(frappe.get_app_path("card"), "public", "fonts")
		if not os.path.isdir(src):
			return
		dest = os.path.join(os.path.expanduser("~"), ".fonts")
		os.makedirs(dest, exist_ok=True)
		changed = False
		for name in os.listdir(src):
			if not name.lower().endswith(".ttf"):
				continue
			target = os.path.join(dest, name)
			source = os.path.join(src, name)
			if not os.path.exists(target) or os.path.getsize(target) != os.path.getsize(source):
				shutil.copyfile(source, target)
				changed = True
		if changed:
			subprocess.run(["fc-cache", "-f", dest], check=False, timeout=60)
	except Exception:
		frappe.log_error(title="card.fonts.ensure_fonts failed", message=frappe.get_traceback())
