# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, formatdate, getdate

# per-company tables: a row steers that company's postings (FR-125: and its diesel prices)
COMPANY_TABLES = ("company_settings", "adjustment_types", "diesel_price_schedule")

# FR-133 (R-14, O-19): the per-company tables a company-restricted user reads only for the companies
# he is permitted; the rows of other companies are hidden on every read and kept on every save
SCOPED_TABLES = ("company_settings", "diesel_price_schedule")


def settings_company_scope(user=None):
	"""FR-133: the companies whose Card Settings rows ``user`` (default: the session user) may read,
	or None when he may read every row: Administrator, System Manager, and a user without a User
	Permission on Company that applies to CARD (the standard Frappe multi-company rule, the same set
	the save check ``_validate_company_scope`` uses)."""
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return None
	from card.report_access import CARD_DOCTYPE, permitted_companies

	entries = frappe.permissions.get_user_permissions(user).get("Company") or []
	if not any(not e.get("applicable_for") or e.get("applicable_for") == CARD_DOCTYPE for e in entries):
		return None
	return set(permitted_companies(user=user))


def settings_row_readable(row, user=None):
	"""FR-133: False when ``row`` is a Card Settings row of a company ``user`` may not read."""
	if row.get("parenttype") != "Card Settings" or row.get("parentfield") not in SCOPED_TABLES:
		return True
	allowed = settings_company_scope(user)
	return allowed is None or row.get("company") in allowed


class CardSettings(Document):
	def has_permission(self, permtype="read", *, debug=False, user=None) -> bool:
		"""FR-133: for a company-restricted user, Frappe's User Permission check on the child rows'
		Company links runs on his companies' rows only. Without this, any row of another company
		refuses him the whole Single (Frappe 16 checks child links on read and write), and the
		filter below could never apply. The other rows are never shown to him
		(``apply_fieldlevel_read_permissions``) and never changed by him (``before_validate`` puts
		them back, ``_validate_company_scope`` refuses a change); every other check is Frappe's."""
		allowed = None if self.flags.ignore_permissions else settings_company_scope(user)
		if allowed is None:
			return super().has_permission(permtype, debug=debug, user=user)
		stored = {table: self.get(table) for table in SCOPED_TABLES}
		try:
			for table, rows in stored.items():
				self.__dict__[table] = [r for r in rows or [] if r.get("company") in allowed]
			return super().has_permission(permtype, debug=debug, user=user)
		finally:
			for table, rows in stored.items():
				self.__dict__[table] = rows

	def apply_fieldlevel_read_permissions(self):
		"""FR-133: every read path (Desk form, REST v1/v2, frappe.client.get and the reply to a
		save) removes the rows of the companies the user may not read before the permlevel rules
		run (they clear ``company`` for a user without level 1, so the filter comes first)."""
		self._hide_other_company_rows()
		super().apply_fieldlevel_read_permissions()
		if self.flags.card_hidden_company_rows:
			# the form shows a note (card_settings.js); set here, as the form save resets __onload
			# after on_change
			self.set_onload("card_hidden_company_rows", self.flags.card_hidden_company_rows)

	def _hide_other_company_rows(self):
		allowed = settings_company_scope()
		if allowed is None:
			return 0
		hidden = 0
		for table in SCOPED_TABLES:
			rows = self.get(table) or []
			kept = [r for r in rows if r.get("company") in allowed]
			if len(kept) != len(rows):
				hidden += len(rows) - len(kept)
				self.set(table, [])
				for idx, row in enumerate(kept, 1):
					row.idx = idx
					self.append(table, row)
		self.flags.card_hidden_company_rows = (self.flags.card_hidden_company_rows or 0) + hidden
		return hidden

	def before_validate(self):
		self._reattach_hidden_company_rows()

	def _reattach_hidden_company_rows(self):
		"""FR-133: a company-restricted user saves a form without the rows of other companies;
		Frappe deletes every stored row missing from a save, so the stored rows of the companies he
		may not read are put back unchanged, at their stored position. A row he sends under such a
		row's name is not replaced here: ``_validate_company_scope`` refuses it when it differs."""
		if frappe.flags.in_patch or frappe.flags.in_install:
			return
		allowed = settings_company_scope()
		before = self.get_doc_before_save()
		if allowed is None or not before:
			return
		for table in SCOPED_TABLES:
			present = {r.name for r in self.get(table) or []}
			hidden = [
				r
				for r in sorted(before.get(table) or [], key=lambda r: cint(r.idx))
				if r.get("company") not in allowed and r.name not in present
			]
			if not hidden:
				continue
			rows = list(self.get(table) or [])
			for row in hidden:
				rows.insert(min(max(cint(row.idx) - 1, 0), len(rows)), row.as_dict())
			self.set(table, [])
			for idx, row in enumerate(rows, 1):
				row = self.append(table, row)
				row.idx = idx

	def on_change(self):
		# FR-133: frappe.client.save and the REST v1 PUT reply with this document; a restricted
		# user gets his companies' rows only (the rows are already stored, nothing is written)
		self._hide_other_company_rows()

	def validate(self):
		self._validate_company_scope()
		seen = set()
		account_fields = [
			f.fieldname
			for f in frappe.get_meta("Card Company Settings").fields
			if f.fieldtype == "Link"
			and f.options == "Account"
			# FR-124: a retired field (hidden and read only) is never checked: a stored old value
			# could otherwise block every save while nobody can see the field to clear it
			and not (f.hidden and f.read_only)
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
		self._validate_diesel_price_schedule()

	def _validate_diesel_price_schedule(self):
		"""FR-125: one price per company and date, above zero, in the company's currency (a fill
		is priced in its company currency, so another currency is refused rather than converted).
		A new or changed row dated on or before submitted fills never changes them: they keep their
		saved price; the user is told how many there are."""
		seen = set()
		before = self.get_doc_before_save()
		old = {r.name: _row_values(r) for r in (before.get("diesel_price_schedule") if before else []) or []}
		scheduled = {r.company for r in self.get("diesel_price_schedule") or []}
		old_prices = {
			r.company: flt(r.diesel_unit_price)
			for r in (before.get("company_settings") if before else []) or []
		}
		for row in (self.get("company_settings") or []) if before else []:
			# review M1: with a schedule the company's price changes only by a dated schedule row
			if row.company in scheduled and flt(row.diesel_unit_price) != old_prices.get(row.company, 0):
				frappe.throw(
					_(
						"Company {0} has a Diesel price schedule: change its diesel price by adding a dated row to the schedule, not in the diesel unit price."
					).format(row.company)
				)
		for row in self.get("diesel_price_schedule") or []:
			key = (row.company, str(getdate(row.valid_from)) if row.valid_from else None)
			if key in seen:
				frappe.throw(
					_("Diesel price schedule: company {0} has two prices valid from {1}.").format(
						row.company, formatdate(row.valid_from)
					)
				)
			seen.add(key)
			if flt(row.unit_price) <= 0:
				frappe.throw(
					_("Diesel price schedule row {0}: the price must be greater than zero.").format(row.idx)
				)
			company_currency = frappe.get_cached_value("Company", row.company, "default_currency")
			if not row.currency:
				row.currency = company_currency
			elif company_currency and row.currency != company_currency:
				frappe.throw(
					_(
						"Diesel price schedule row {0}: the currency must be {1}, the currency of company {2}."
					).format(row.idx, company_currency, row.company)
				)
			if row.valid_from and old.get(row.name) != _row_values(row):
				submitted = frappe.db.count(
					"Project Diesel Fill",
					{"company": row.company, "docstatus": 1, "date": [">=", row.valid_from]},
				)
				if submitted:
					frappe.msgprint(
						_(
							"{0} submitted diesel fills of company {1} are dated on or after {2}. They keep their saved price; the new price applies to new fills only."
						).format(submitted, row.company, formatdate(row.valid_from)),
						indicator="orange",
					)

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
