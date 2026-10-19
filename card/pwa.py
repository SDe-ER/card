# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Serve CARD Mobile's service worker at /cdms/sw.js so its scope is /cdms/ and no wider.

A service worker controls only the paths under its own URL. Frappe HR registers
/assets/hrms/frontend/sw.js, whose scope is /assets/hrms/frontend/, so it never controls /hrms;
an app cannot add Service-Worker-Allowed to /assets. Frappe's static page renderer refuses .js
files from www, so this uses the official `page_renderer` hook. The file is the one
vite-plugin-pwa builds, as in Frappe HR.
"""

import os

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer
from werkzeug.wrappers import Response

ENDPOINT = "cdms-sw"


class ServiceWorkerRenderer(BaseRenderer):
	@staticmethod
	def file_path():
		return frappe.get_app_path("card", "public", "frontend", "sw.js")

	def can_render(self):
		return self.path == ENDPOINT and os.path.isfile(self.file_path())

	def render(self):
		with open(self.file_path(), "rb") as f:
			response = Response(f.read(), mimetype="application/javascript")
		# the browser re-checks the worker on every load, so a new build is picked up
		response.headers["Cache-Control"] = "no-cache"
		return response
