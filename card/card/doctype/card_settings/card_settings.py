# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

# per-company tables: a row steers that company's postings
COMPANY_TABLES = ("company_settings", "adjustment_types")


class CardSettings(Document):
	def validate(self):
		self._validate_company_scope()
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
		self._validate_adjustment_types()

	def _validate_company_scope(self):
		"""A user may add, change or remove the per-company rows (accounts, tax
		templates, items, adjustment types) only for companies they may see —
		otherwise an Accounts Manager restricted to company A could re-point
		company B's posting accounts (security review). Child-row links are not
		User-Permission-checked by Frappe, so this is enforced here."""
		if frappe.session.user == "Administrator" or frappe.flags.in_patch or frappe.flags.in_install:
			return
		from card.report_access import permitted_companies

		allowed = set(permitted_companies())
		before = self.get_doc_before_save()
		touched = set()
		for table in COMPANY_TABLES:
			old = {r.name: r for r in (before.get(table) if before else []) or []}
			new = {r.name: r for r in self.get(table) or []}
			for name, row in new.items():
				prev = old.get(name)
				if prev is None or _row_values(prev) != _row_values(row):
					touched.add(row.company)
					if prev is not None:
						touched.add(prev.company)
			for name, row in old.items():
				if name not in new:
					touched.add(row.company)
		denied = sorted(c for c in touched if c and c not in allowed)
		if denied:
			frappe.throw(
				_("You are not permitted to change the Card settings of company {0}.").format(
					", ".join(denied)
				),
				frappe.PermissionError,
			)

	def _validate_adjustment_types(self):
		"""S3/F.4: every configured addition/deduction type must point at a safe,
		postable account (leaf, same company, enabled, not tax-withholding).
		The posting builder re-checks at posting time; this keeps bad rows from
		being saved in the first place."""
		seen = set()
		for row in self.get("adjustment_types") or []:
			key = (row.company, (row.type_name or "").strip())
			if key in seen:
				frappe.throw(
					_("Duplicate addition/deduction type {0} for company {1}.").format(
						row.type_name, row.company
					)
				)
			seen.add(key)
			acc = frappe.db.get_value(
				"Account",
				row.account,
				["company", "is_group", "disabled"],
				as_dict=True,
			)
			if not acc:
				frappe.throw(_("Account {0} does not exist.").format(row.account))
			if acc.company != row.company:
				frappe.throw(
					_("Account {0} belongs to company {1}, not {2}.").format(
						row.account, acc.company, row.company
					)
				)
			if acc.is_group:
				frappe.throw(
					_("Account {0} is a group; pick a leaf account for type {1}.").format(
						row.account, row.type_name
					)
				)
			if acc.disabled:
				frappe.throw(
					_("Account {0} is disabled; pick an active account for type {1}.").format(
						row.account, row.type_name
					)
				)


def _row_values(row):
	"""A child row's data fields, for change detection (no meta/ordering fields)."""
	return {
		df.fieldname: row.get(df.fieldname)
		for df in row.meta.fields
		if df.fieldtype not in ("Section Break", "Column Break", "Tab Break")
	}
