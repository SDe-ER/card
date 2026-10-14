# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class CardSettings(Document):
	def validate(self):
		seen = set()
		for row in self.get("company_settings") or []:
			if row.company in seen:
				frappe.throw(_("Duplicate company in Card Company Settings: {0}").format(row.company))
			seen.add(row.company)
		# F.1: one transport price per project
		projects = set()
		for row in self.get("project_transport_prices") or []:
			if row.project in projects:
				frappe.throw(_("Duplicate project in transport prices: {0}").format(row.project))
			projects.add(row.project)
