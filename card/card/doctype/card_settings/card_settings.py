# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class CardSettings(Document):
	def validate(self):
		seen = set()
		account_fields = [
			f.fieldname
			for f in frappe.get_meta("Card Company Settings").fields
			if f.fieldtype == "Link" and f.options == "Account"
		]
		for row in self.get("company_settings") or []:
			if row.company in seen:
				frappe.throw(_("Duplicate company in Card Company Settings: {0}").format(row.company))
			seen.add(row.company)
			# F.8: every configured account must belong to its row's company
			for fieldname in account_fields:
				account = row.get(fieldname)
				if not account:
					continue
				account_company = frappe.db.get_value("Account", account, "company")
				if account_company and account_company != row.company:
					frappe.throw(
						_("Account {0} belongs to company {1}, not {2}.").format(
							account, account_company, row.company
						)
					)
		# F.1: a fixed diesel-supplier policy is meaningless without the supplier
		# (server-side: mandatory_depends_on is client-only)
		if (self.get("diesel_supplier_policy") or "").strip() == "ثابت" and not self.get("diesel_supplier"):
			frappe.throw(_("Diesel supplier policy is fixed; set the diesel supplier."))
		# F.1: one transport price per project
		projects = set()
		for row in self.get("project_transport_prices") or []:
			if row.project in projects:
				frappe.throw(_("Duplicate project in transport prices: {0}").format(row.project))
			projects.add(row.project)
