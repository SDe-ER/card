# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Access rules shared by every CARD report and its link-filter queries.

Script reports read with ``frappe.get_all`` / SQL, which apply no document
permissions, so each report must scope itself:

- every report runs for ONE company, validated against the companies the user
  may see for the report's document type (standard Frappe multi-company rule:
  User Permissions on Company restrict the set — honouring ``applicable_for`` —
  and with none, every company is visible);
- ledger figures (GL Entry aggregates) are computed only for users whose ROLES
  grant GL Entry read without an owner restriction, and only for a company they
  may see in the ledger — document shares and ``if_owner`` reads do not count.

Nothing here grants an ERPNext permission: link filters use the CARD-owned
whitelisted queries in ``card.api`` (Frappe calls a whitelisted ``query``
instead of checking the target doctype), each of which calls
``assert_report_role`` and stays inside ``permitted_companies``."""

import frappe
from frappe import _

CARD_DOCTYPE = "Card Monthly Card"


def assert_report_role():
	"""Allow a user who may run at least one CARD report (report roles plus any
	"Role Permission for Page and Report" override, via Report.is_permitted)."""
	if frappe.session.user == "Administrator":
		return
	reports = frappe.get_all(
		"Report", filters={"module": "Card", "is_standard": "Yes", "disabled": 0}, pluck="name"
	)
	for name in reports:
		report = frappe.get_cached_doc("Report", name)
		# a report saved without roles is open to everyone in Frappe; it must not
		# open the CARD queries
		if report.roles and report.is_permitted():
			return
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def permitted_companies(*doctypes):
	"""Companies the session user may see for EVERY one of ``doctypes`` (default:
	Card Monthly Card), sorted. A User Permission on Company counts for a doctype
	when it applies to every doctype or to that one; a report reading several
	doctypes gets the intersection."""
	entries = frappe.permissions.get_user_permissions(frappe.session.user).get("Company") or []
	every = None
	result = None
	for doctype in doctypes or (CARD_DOCTYPE,):
		scoped = {
			entry.get("doc")
			for entry in entries
			if not entry.get("applicable_for") or entry.get("applicable_for") == doctype
		}
		if not scoped:
			if every is None:
				every = set(frappe.get_all("Company", pluck="name"))
			scoped = every
		result = scoped if result is None else result & scoped
	return sorted(result)


def resolve_company(filters, *doctypes):
	"""The single company a report runs for; refuses one the user may not see for
	any of the report's ``doctypes``. Defaults are used only when permitted."""
	allowed = permitted_companies(*doctypes)
	company = (filters or {}).get("company")
	if not company:
		for default in (
			frappe.defaults.get_user_default("Company"),
			frappe.defaults.get_global_default("company"),
		):
			if default and default in allowed:
				company = default
				break
	if not company and len(allowed) == 1:
		company = allowed[0]
	if not company:
		frappe.throw(_("Select a company"))
	if company not in allowed:
		frappe.throw(
			_("You are not permitted to view data of company {0}").format(company),
			frappe.PermissionError,
		)
	return company


def can_view_ledger(company=None):
	"""True when the user's ROLES grant GL Entry read without an owner
	restriction (a shared GL Entry or an if_owner read never qualifies), and —
	when ``company`` is given — the user may see that company's ledger."""
	if frappe.session.user != "Administrator":
		perms = frappe.permissions.get_role_permissions(frappe.get_meta("GL Entry"))
		if not perms.get("read") or "read" in (perms.get("if_owner") or {}):
			return False
	return company is None or company in permitted_companies("GL Entry")


def query_companies(filters, doctype=CARD_DOCTYPE):
	"""Companies a link-filter query may draw from: the requested one when the
	user may see it (else none), otherwise every permitted company."""
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
	allowed = permitted_companies(doctype)
	company = filters.get("company") if isinstance(filters, dict) else None
	if company:
		return [company] if company in allowed else []
	return allowed


def strip_ledger(columns, rows, summary, keys, tile_labels):
	"""Remove ledger columns, row values and summary tiles in place of hiding
	them, so the figures never reach the browser."""
	columns = [c for c in columns if c.get("fieldname") not in keys]
	for row in rows:
		for key in keys:
			row.pop(key, None)
	summary = [t for t in summary if t.get("label") not in tile_labels]
	return columns, summary


def _role_reads(doctype):
	if frappe.session.user == "Administrator":
		return True
	perms = frappe.permissions.get_role_permissions(frappe.get_meta(doctype))
	return bool(perms.get("read")) and "read" not in (perms.get("if_owner") or {})


SHOW_TITLE_FOR = ("Project",)


def readable_links(columns, rows=None):
	"""Link columns to a doctype the user cannot read become Data columns: the
	value still shows, but the Desk does not try to resolve its title (Frappe
	then posts a permission message on every run) or open a record the user may
	not see. With ``rows``, a downgraded Project column shows the project's
	name instead of its record name (PROJ-0001) — the title the Desk would have
	resolved; the rows are already scoped to the user's company. Only Project:
	supplier/customer values feed the summaries' statement drill-downs and are
	named after the party already, and account-like codes must stay intact."""
	result = []
	downgraded = {}
	for column in columns:
		if (
			isinstance(column, dict)
			and column.get("fieldtype") == "Link"
			and column.get("options")
			and not _role_reads(column["options"])
		):
			downgraded[column.get("fieldname")] = column["options"]
			column = {key: value for key, value in column.items() if key != "options"}
			column["fieldtype"] = "Data"
		result.append(column)
	downgraded = {field: dt for field, dt in downgraded.items() if dt in SHOW_TITLE_FOR}
	if rows and downgraded:
		_show_titles(rows, downgraded)
	return result


def _show_titles(rows, downgraded):
	dict_rows = [row for row in rows if isinstance(row, dict)]
	for field, doctype in downgraded.items():
		title_field = frappe.get_meta(doctype).get_title_field()
		if not field or not title_field or title_field == "name":
			continue
		names = list({row.get(field) for row in dict_rows if row.get(field)})
		if not names:
			continue
		titles = dict(
			frappe.get_all(
				doctype, filters={"name": ["in", names]}, fields=["name", title_field], as_list=True
			)
		)
		for row in dict_rows:
			if titles.get(row.get(field)):
				row[field] = titles[row[field]]


def ledger_notice():
	return _("Ledger balances are shown only to users with General Ledger access.")
