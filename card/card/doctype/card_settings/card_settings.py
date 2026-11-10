# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, formatdate, getdate

from card.settings import validate_company_warehouses

# per-company tables: a row steers that company's postings (FR-125: and its diesel prices)
COMPANY_TABLES = ("company_settings", "adjustment_types", "diesel_price_schedule")

# FR-133 (R-14, O-19): the per-company tables a company-restricted user reads only for the companies
# he is permitted; the rows of other companies are hidden on every read and kept on every save
SCOPED_TABLES = ("company_settings", "adjustment_types", "diesel_price_schedule")
SCOPED_CHILD_DOCTYPES = ("Card Company Settings", "Card Adjustment Type", "Card Diesel Price")
LAYOUT_FIELDTYPES = ("Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold")


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


def has_settings_permission(doc, ptype=None, user=None, debug=False):
	"""FR-133 ``has_permission`` hook: a company-restricted user may use the Card Settings Single
	only as CARD scopes it (``CardSettings.has_permission`` removes the other companies' rows before
	Frappe's checks run). A check on the whole stored Single — the child-table list and value reads
	(``frappe.client.get_list`` / ``get_value``, ``frappe.desk.reportview.get`` with
	``parent="Card Settings"``) and a child row read on its own — is refused to him while another
	company has a row. Frappe 16 applies no list condition to a child table of a Single
	(``frappe/database/query.py`` ``add_permission_conditions``), so this is the list control."""
	allowed = settings_company_scope(user)
	if allowed is None:
		return True
	return all(row.get("company") in allowed for table in SCOPED_TABLES for row in (doc.get(table) or []))


def settings_row_query_conditions(user=None, doctype=None):
	"""FR-133 ``permission_query_conditions`` for the scoped child DocTypes, as a second layer: a
	company-restricted user lists only his companies' Card Settings rows (rows of any other parent
	are not touched). Frappe 16 does not apply it to a child table of a Single (see
	``has_settings_permission``); it applies if Frappe ever does."""
	allowed = settings_company_scope(user)
	if allowed is None or doctype not in SCOPED_CHILD_DOCTYPES:
		return ""
	table = f"`tab{doctype}`"
	companies = ", ".join(frappe.db.escape(c) for c in sorted(allowed)) or "''"
	return f"({table}.`parenttype` != 'Card Settings' or {table}.`company` in ({companies}))"


# ---------- FR-133: the change history (Version) of Card Settings in the form timeline ----------


GETDOC = "frappe.desk.form.load.getdoc"
GET_DOCINFO = "frappe.desk.form.load.get_docinfo"
CARD_OVERRIDES = {
	GETDOC: "card.card.doctype.card_settings.card_settings.getdoc",
	GET_DOCINFO: "card.card.doctype.card_settings.card_settings.get_docinfo",
}


def _previous_override(original):
	"""The method CARD's override of ``original`` wraps: the override registered before CARD's in
	``override_whitelisted_methods`` (an app installed before CARD, e.g. DAWM's own security
	filter), else Frappe's original. Frappe calls only the last registered override
	(``frappe.override_whitelisted_method``), so CARD keeps the earlier ones in the chain. Never
	CARD's own entry; a re-entry (an earlier override that itself calls the last override) gets
	Frappe's original, so the chain cannot loop."""
	own = CARD_OVERRIDES[original]
	active = frappe.local.flags.setdefault("card_override_active", set())
	if original in active:
		return frappe.get_attr(original)
	chain = list((frappe.get_hooks("override_whitelisted_methods", {}) or {}).get(original) or [])
	position = max((i for i, method in enumerate(chain) if method == own), default=len(chain))
	for method in reversed(chain[:position]):
		if method not in (own, original):
			return frappe.get_attr(method)
	return frappe.get_attr(original)


def _call_previous(original, **kwargs):
	method = _previous_override(original)
	active = frappe.local.flags.setdefault("card_override_active", set())
	entered = original not in active
	active.add(original)
	try:
		return method(**kwargs)
	finally:
		if entered:
			active.discard(original)


@frappe.whitelist(methods=["GET", "POST"])
def getdoc(doctype: str, name: str | int):
	"""Override of ``frappe.desk.form.load.getdoc``: calls the previous override in the hook chain
	(or Frappe's method), then removes from the Card Settings timeline of a company-restricted user
	every row of another company."""
	_call_previous(GETDOC, doctype=doctype, name=name)
	scope_docinfo_versions()
	mask_docinfo_versions_by_level()


@frappe.whitelist(methods=["GET", "POST"])
def get_docinfo(
	doc: Document | dict | str | None = None,
	doctype: str | None = None,
	name: str | int | None = None,
):
	"""Override of ``frappe.desk.form.load.get_docinfo``: as ``getdoc``."""
	_call_previous(GET_DOCINFO, doc=doc, doctype=doctype, name=name)
	scope_docinfo_versions()
	mask_docinfo_versions_by_level()


def scope_docinfo_versions():
	"""Remove from ``frappe.response.docinfo.versions`` every change of a row of a company the user
	may not read (added, removed, changed, or moved from or to such a company)."""
	docinfo = frappe.response.get("docinfo")
	if not docinfo or docinfo.get("doctype") != "Card Settings" or not docinfo.get("versions"):
		return
	allowed = settings_company_scope()
	if allowed is None:
		return
	companies = {}
	for child in SCOPED_CHILD_DOCTYPES:
		for row in frappe.get_all(child, filters={"parenttype": "Card Settings"}, fields=["name", "company"]):
			companies[row.name] = row.company
	docinfo["versions"] = [
		{**version, "data": _scoped_version_data(version.get("data"), allowed, companies)}
		for version in docinfo["versions"]
	]


def _scoped_version_data(data, allowed, companies):
	import json

	try:
		changes = json.loads(data or "{}")
	except (TypeError, ValueError):
		return "{}"
	if not isinstance(changes, dict):
		return "{}"

	def visible_row(entry):
		if not isinstance(entry, list) or not entry or not isinstance(entry[0], str):
			return False
		table, row = entry[0], entry[1] if len(entry) > 1 else None
		return table not in SCOPED_TABLES or (isinstance(row, dict) and row.get("company") in allowed)

	def visible_change(entry):
		# [table, idx, row name, [[field, old, new], ...]]
		if not isinstance(entry, list) or not entry or not isinstance(entry[0], str):
			return False
		if entry[0] not in SCOPED_TABLES:
			return True
		if companies.get(entry[2] if len(entry) > 2 else None) not in allowed:
			return False
		row_changes = entry[3] if len(entry) > 3 and isinstance(entry[3], list) else []
		return all(
			isinstance(c, list)
			and len(c) > 2
			and (c[0] != "company" or (c[1] in allowed and c[2] in allowed))
			for c in row_changes
		)

	for key in ("added", "removed"):
		if changes.get(key):
			entries = changes[key] if isinstance(changes[key], list) else []
			changes[key] = [e for e in entries if visible_row(e)]
	if changes.get("row_changed"):
		entries = changes["row_changed"] if isinstance(changes["row_changed"], list) else []
		changes["row_changed"] = [e for e in entries if visible_change(e)]
	return frappe.as_json(changes, indent=None, separators=(",", ":"))


# ---------- FR-148: the Card Settings timeline follows the reader's permission levels ----------


def _hidden_settings_fields(user=None):
	"""FR-148: (fields, {table: child fields}) of Card Settings that ``user`` (default: the session user) may
	not read: a field at a level he has no read on, every field of a table at such a level, and every child
	field at such a level. None for Administrator (Frappe applies no level to him)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return None
	meta = frappe.get_meta("Card Settings")
	levels = set(meta.get_permlevel_access("read", user=user))
	fields = {
		df.fieldname
		for df in meta.fields
		if df.fieldtype not in LAYOUT_FIELDTYPES and cint(df.permlevel) not in levels
	}
	tables = {}
	for table in meta.get_table_fields():
		child = [df for df in frappe.get_meta(table.options).fields if df.fieldtype not in LAYOUT_FIELDTYPES]
		hidden_table = cint(table.permlevel) not in levels
		hidden = {df.fieldname for df in child if hidden_table or cint(df.permlevel) not in levels}
		if hidden:
			tables[table.fieldname] = hidden
	return fields, tables


def mask_docinfo_versions_by_level():
	"""FR-148: in ``frappe.response.docinfo.versions`` of Card Settings, mask (``card.field_privacy.MASKED``)
	the old and new values of every field, and every child row value, at a level the reader cannot read: in
	``changed``, ``added``, ``removed`` and ``row_changed``. Who changed what and when stays. The Versions
	are stored unmasked (a reader of the level, e.g. Accounts Manager, sees the real values); this is a
	read-time mask for Card Settings only."""
	docinfo = frappe.response.get("docinfo")
	if not docinfo or docinfo.get("doctype") != "Card Settings" or not docinfo.get("versions"):
		return
	hidden = _hidden_settings_fields()
	if not hidden or not (hidden[0] or hidden[1]):
		return
	docinfo["versions"] = [
		{**version, "data": _masked_version_data(version.get("data"), *hidden)}
		for version in docinfo["versions"]
	]


def _masked_version_data(data, fields, tables):
	"""The Version ``data`` with the hidden values masked. Data that is not a JSON object becomes ``{}``;
	a malformed entry (not a list, a field or table name that is not a string) is dropped, never shown."""
	import json

	from card.field_privacy import MASKED

	try:
		changes = json.loads(data or "{}")
	except (TypeError, ValueError):
		return "{}"
	if not isinstance(changes, dict):
		return "{}"

	def named(entry):
		return isinstance(entry, list) and entry and isinstance(entry[0], str)

	def masked_changes(entries, hidden):
		# [[field, old, new], ...]
		kept = []
		for change in entries if isinstance(entries, list) else []:
			if not named(change):
				continue
			if change[0] in hidden:
				change[1:] = [MASKED] * (len(change) - 1)
			kept.append(change)
		return kept

	if "changed" in changes:
		changes["changed"] = masked_changes(changes.get("changed"), fields)
	for key in ("added", "removed"):
		if key not in changes:
			continue
		kept = []
		for entry in changes.get(key) if isinstance(changes.get(key), list) else []:
			# [table, row]
			if not named(entry) or len(entry) < 2 or not isinstance(entry[1], dict):
				continue
			for field in tables.get(entry[0], ()):
				if field in entry[1]:
					entry[1][field] = MASKED
			kept.append(entry)
		changes[key] = kept
	if "row_changed" in changes:
		kept = []
		for entry in changes.get("row_changed") if isinstance(changes.get("row_changed"), list) else []:
			# [table, idx, row name, [[field, old, new], ...]]
			if not named(entry) or len(entry) < 4:
				continue
			entry[3] = masked_changes(entry[3], tables.get(entry[0], ()))
			kept.append(entry)
		changes["row_changed"] = kept
	return frappe.as_json(changes, indent=None, separators=(",", ":"))


def _normalised(df, value):
	if df.fieldtype in ("Int", "Check"):
		return cint(value)
	if df.fieldtype in ("Float", "Currency", "Percent", "Duration"):
		return flt(value)
	if df.fieldtype in ("Date", "Datetime") and value:
		return str(getdate(value)) if df.fieldtype == "Date" else str(value)
	return value or None


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
		# the form save (savedocs) builds the timeline before this call
		scope_docinfo_versions()
		mask_docinfo_versions_by_level()
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
				(position, r)
				for position, r in enumerate(sorted(before.get(table) or [], key=lambda r: cint(r.idx)))
				if r.get("company") not in allowed and r.name not in present
			]
			if not hidden:
				continue
			rows = list(self.get(table) or [])
			for position, row in hidden:
				rows.insert(min(position, len(rows)), row.as_dict())
			self.set(table, [])
			for idx, row in enumerate(rows, 1):
				row = self.append(table, row)
				row.idx = idx

	def on_change(self):
		# FR-133: frappe.client.save, frappe.client.set_value, frappe.client.insert of a row and the
		# REST v1 PUT reply with this very object; a restricted user gets his companies' rows only.
		# Nothing is written, and the document cache is already cleared (clear_cache runs before
		# on_change), so no cached copy changes; the object is the reply of the request.
		self._hide_other_company_rows()

	def _hidden_names(self):
		"""Names of the rows of companies the session user may not read (they reach validate
		unchanged: ``_validate_company_scope`` refuses any change first)."""
		allowed = settings_company_scope()
		if allowed is None:
			return set()
		return {r.name for t in SCOPED_TABLES for r in self.get(t) or [] if r.get("company") not in allowed}

	def _rows(self, table):
		"""FR-133: the rows ``validate`` checks: a restricted user's save does not re-check (and
		never names in a message) the unchanged rows of other companies; every rule is per company,
		so his own companies' rows are checked in full."""
		hidden = self.flags.card_hidden_names or set()
		return [r for r in self.get(table) or [] if r.name not in hidden]

	def validate(self):
		self._validate_company_scope()
		self.flags.card_hidden_names = self._hidden_names()
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
		for row in self._rows("company_settings"):
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
		validate_company_warehouses(_ScopedRows(self))  # FR-135; FR-133: visible rows only

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
		for row in self._rows("company_settings") if before else []:
			# review M1: with a schedule the company's price changes only by a dated schedule row
			if row.company in scheduled and flt(row.diesel_unit_price) != old_prices.get(row.company, 0):
				frappe.throw(
					_(
						"Company {0} has a Diesel price schedule: change its diesel price by adding a dated row to the schedule, not in the diesel unit price."
					).format(row.company)
				)
		for row in self._rows("diesel_price_schedule"):
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
		# FR-133: a company-restricted user maintains his companies' rows only; every site-wide
		# field (warehouses, request days, policies, ...) stays as stored
		if before and settings_company_scope() is not None:
			changed = [
				df.label or df.fieldname
				for df in self.meta.fields
				if df.fieldtype not in LAYOUT_FIELDTYPES
				and df.fieldtype not in frappe.model.table_fields
				and _normalised(df, self.get(df.fieldname)) != _normalised(df, before.get(df.fieldname))
			]
			if changed:
				frappe.throw(
					_(
						"Your Card Settings access is limited to your companies' rows; you cannot change the site-wide fields: {0}."
					).format(", ".join(_(label) for label in changed)),
					frappe.PermissionError,
				)
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
		for row in self._rows("adjustment_types"):
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


class _ScopedRows:
	"""FR-133: the Card Settings a restricted user's save validates: the scoped tables give only the
	rows ``CardSettings._rows`` checks (unchanged rows of other companies are neither re-checked nor
	named); every other value is the document's."""

	def __init__(self, doc):
		self._doc = doc

	def get(self, key, default=None):
		return self._doc._rows(key) if key in SCOPED_TABLES else self._doc.get(key, default)

	def get_doc_before_save(self):
		return self._doc.get_doc_before_save()


def _row_values(row):
	"""A child row's data fields, for change detection (no meta/ordering fields)."""
	return {
		df.fieldname: row.get(df.fieldname)
		for df in row.meta.fields
		if df.fieldtype not in ("Section Break", "Column Break", "Tab Break")
	}
