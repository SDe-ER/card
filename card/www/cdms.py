# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD Mobile page (/cdms). The page itself is built from frontend/ into cdms.html.

As hrms/www/hrms.py: Guests get the page too, for the in-app login view; the boot carries the
session's CSRF token, the language and its direction, and Frappe's translations.
"""

import frappe
from frappe import _
from frappe.boot import load_translations
from frappe.sessions import get_csrf_token

from card.mobile import has_app_permission

no_cache = 1

RTL_LANGUAGES = {"ar", "ur"}


def get_context(context):
	if frappe.session.user != "Guest" and not has_app_permission(require_employee=False):
		frappe.throw(_("You are not permitted to access this page."), frappe.PermissionError)

	lang = str(frappe.local.lang or "en")
	boot = frappe._dict(lang=lang)
	load_translations(boot)
	context.boot = {
		"csrf_token": get_csrf_token(),
		"lang": lang,
		"dir": "rtl" if lang.split("-")[0] in RTL_LANGUAGES else "ltr",
		"__messages": dict(boot.get("__messages") or {}),
	}
	return context
