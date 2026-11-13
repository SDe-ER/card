# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-160 (#31; closure plan WP-J): Diesel Group Analysis report.

Read-only; writes nothing, posts no GL, changes no card and no fill (FR-100 preserved). For one
company, one date range and (optionally) one Equipment Operating Group it displays the group's
diesel in two sections:

1. **Group rows** — litres that belong to a member equipment of the group:
   - **Direct fills (measured):** a submitted Project Diesel Fill with ``card_equipment`` set to
     a member equipment. The whole fill litres count for the group on the fill date. Basis is
     ``measured`` (FR-033: a direct fill is RECORDED for that equipment).
   - **Allocations (estimated):** a submitted Project Diesel Fill with no ``card_equipment``
     (tank-style, FR-157) whose ``diesel_fill_allocation`` child row names a member equipment.
     The row's ``allocated_litres`` count for the group on the fill date. Basis is the row's
     own basis, which FR-157 stores as ``estimated`` (its only value today). A legacy tank fill
     submitted before FR-157 carries no allocation rows and so contributes no group row — the
     owner acceptance "a litre belongs to exactly one equipment or to an explicit shared bucket,
     never both" is kept (we do not re-derive an estimate here; the FR-033 read-time split lives
     in ``card.diesel.allocate_project_diesel`` and the Equipment Diesel Analysis report).

2. **Shared-bucket rows** — the other side of the same tank fills that touched the group:
   their allocation rows whose equipment is NOT a member of the group. Aggregated per fill as
   one row with equipment "(outside)", basis ``estimated``. These rows do NOT add to the group
   total; they are a diagnostic so the reader sees that a 1 000 L tank fill split 600 L to
   group members and 400 L to non-members was accounted correctly (owner acceptance on #31:
   "no litre counted twice").

The totals line sums the group rows only. The shared-bucket rows are totalled on their own
summary tile ("Shared bucket (outside the group)") so the reader never adds the two by hand.

Basis labels are translated literals: ``_("measured")`` and ``_("estimated")`` (Lesson 13:
never relabel an estimated row as measured). The FR-033 + FR-157 convention lives in one place,
``BASIS_MEASURED`` and ``BASIS_ESTIMATED``.

Access:

- Report roles: System Manager, Card Manager, Card User, Accounts Manager (same as Equipment
  Diesel Analysis / Diesel Variance Anomaly).
- One company the user may see for every doctype the report reads (``resolve_company``).
- The groups shown are those the user may read (list filtered by ``has_permission``: the
  generic company-scope hooks of FR-131 limit the user's view already).
- Amounts are NOT included in this report: the scope asks for litres and basis only (closure
  plan WP-J); currency labelling is therefore not needed. A later wave adds a cost column if
  the owner requests it.

Every read is batched (a fixed number of queries whatever the number of groups or fills)."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.report_access import permitted_companies, resolve_company

DOCTYPES = ("Equipment Operating Group", "Project Diesel Fill", "Card Equipment")
GROUP = "Equipment Operating Group"
FILL = "Project Diesel Fill"
MAX_DAYS = 400  # roughly one year + one month, same ballpark as Diesel Variance Anomaly

BASIS_MEASURED = "measured"
BASIS_ESTIMATED = "estimated"

SECTION_DIRECT = "direct_fill"
SECTION_ALLOCATION = "allocation"
SECTION_SHARED = "shared_bucket"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	company = resolve_company(filters, *DOCTYPES)
	filters.company = company
	start, end = _period(filters)

	groups = _groups_in_scope(company, filters.get("group"))
	if not groups:
		return _columns(), [], _message_no_groups(), None, _empty_summary()

	# {equipment: [(group, effective_from_or_None, effective_to_or_None), ...]}: every active
	# membership row of every readable group of the company, so the report can decide
	# per-fill-date to which group an equipment belongs.
	memberships = _memberships(groups)

	direct_rows = _direct_fill_rows(company, start, end, groups, memberships)
	alloc_rows, shared_rows = _allocation_rows(company, start, end, groups, memberships)

	rows = sorted(
		direct_rows + alloc_rows + shared_rows,
		key=lambda r: (
			r["group"] or "",
			r["date"] or "",
			r["section"],
			r["fill"] or "",
			r["equipment"] or "",
		),
	)

	summary = _summary(rows)
	return _columns(), rows, None, None, summary, True


# ---------- filters and periods ----------


def _period(filters):
	start = getdate(filters.get("from_date"))
	end = getdate(filters.get("to_date"))
	if end < start:
		frappe.throw(_("Invalid period: end is before start."))
	from frappe.utils import date_diff

	if date_diff(end, start) + 1 > MAX_DAYS:
		frappe.throw(
			_("Select a period of at most {0} days for the Diesel Group Analysis report.").format(MAX_DAYS)
		)
	return start, end


def _groups_in_scope(company, group_filter):
	"""Enabled groups of ``company`` the user may read, honoured through ``has_permission``.

	With a group filter: refuse one outside the user's scope or not of the company (defence in
	depth; the Link filter already blocks them in the form)."""
	filters = {"company": company, "enabled": 1}
	if group_filter:
		if not frappe.has_permission(GROUP, "read", doc=group_filter):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		row = frappe.db.get_value(GROUP, group_filter, ["name", "company", "enabled"], as_dict=True)
		if not row or row.company != company or not row.enabled:
			return []
		return [row.name]
	# every readable enabled group of the company — the generic company-scope hooks (FR-131)
	# already limit a restricted user to their own companies; this is an ordinary list call.
	return frappe.get_all(GROUP, filters=filters, pluck="name", order_by="group_name asc")


def _memberships(groups):
	"""{equipment: [(group, from, to), …]} for every member row of every group in ``groups``."""
	rows = frappe.get_all(
		"Equipment Operating Group Member",
		filters={"parenttype": GROUP, "parent": ["in", groups]},
		fields=["parent", "equipment", "effective_from", "effective_to"],
	)
	out = defaultdict(list)
	for row in rows:
		if not row.equipment:
			continue
		out[row.equipment].append(
			(
				row.parent,
				getdate(row.effective_from) if row.effective_from else None,
				getdate(row.effective_to) if row.effective_to else None,
			)
		)
	return out


def _group_for_equipment_on(memberships, equipment, on_date):
	"""The group ``equipment`` belongs to on ``on_date``, or None. An equipment cannot be in two
	active groups of the same company on the same day (refused on save by
	``_refuse_overlap_with_other_groups``), so there is at most one match."""
	if not equipment:
		return None
	candidates = memberships.get(equipment) or []
	for group, from_date, to_date in candidates:
		if from_date and on_date < from_date:
			continue
		if to_date and on_date > to_date:
			continue
		return group
	return None


# ---------- direct fills (measured) ----------


def _direct_fill_rows(company, start, end, groups, memberships):
	"""One row per submitted direct fill (``card_equipment`` set) whose equipment is a member of
	one of ``groups`` on the fill date. Basis ``measured``, litres = fill.litres."""
	# `card_equipment` set is the direct-fill case. The parent fill's company and docstatus = 1
	# are the standard filters; ``card_equipment in <group members>`` keeps the query bounded.
	all_members = sorted(memberships.keys())
	if not all_members:
		return []
	fills = frappe.get_all(
		FILL,
		filters={
			"company": company,
			"docstatus": 1,
			"date": ["between", [start, end]],
			"card_equipment": ["in", all_members],
		},
		fields=["name", "date", "project", "card_equipment", "litres"],
	)
	rows = []
	for fill in fills:
		on_date = getdate(fill.date)
		group = _group_for_equipment_on(memberships, fill.card_equipment, on_date)
		if not group or group not in groups:
			continue
		rows.append(
			{
				"date": on_date,
				"group": group,
				"section": SECTION_DIRECT,
				"section_label": _("Direct fill (member)"),
				"basis": BASIS_MEASURED,
				"basis_label": _(BASIS_MEASURED),
				"equipment": fill.card_equipment,
				"fill": fill.name,
				"project": fill.project,
				"litres": flt(fill.litres, 3),
			}
		)
	return rows


# ---------- tank fills: allocations + shared bucket (estimated) ----------


def _allocation_rows(company, start, end, groups, memberships):
	"""Two lists of rows:

	- ``alloc_rows``: one row per diesel_fill_allocation row whose equipment is a group member on
	  the fill date (basis from the stored row; FR-157 stores ``estimated``).
	- ``shared_rows``: one aggregated row per tank fill whose allocation set touched the group:
	  the sum of its other allocation rows (non-members or members of other groups that are
	  outside the report scope). These rows do NOT add to the group total.
	"""
	# Pull candidate tank fills first (no card_equipment), then their allocation rows. One
	# query per shape, so the row count stays bounded.
	tank_fills = frappe.get_all(
		FILL,
		filters={
			"company": company,
			"docstatus": 1,
			"date": ["between", [start, end]],
			"card_equipment": ["in", ["", None]],
		},
		fields=["name", "date", "project"],
	)
	if not tank_fills:
		return [], []
	fill_index = {fill.name: fill for fill in tank_fills}
	allocation_rows = frappe.get_all(
		"Diesel Fill Allocation",
		filters={"parenttype": FILL, "parent": ["in", list(fill_index)]},
		fields=["parent", "equipment", "allocated_litres", "basis"],
	)
	# group the allocation rows by their parent fill, so the shared-bucket computation sees the
	# whole split for one fill at a time.
	by_fill = defaultdict(list)
	for row in allocation_rows:
		by_fill[row.parent].append(row)
	alloc_rows = []
	shared_rows = []
	for fill_name, rows in by_fill.items():
		fill = fill_index[fill_name]
		on_date = getdate(fill.date)
		# split the fill's allocation rows into in-scope (member of a group in ``groups``) and
		# out-of-scope (every other row of the same fill).
		in_scope = defaultdict(list)  # {group: [row, ...]}
		out_of_scope_litres = 0.0
		for row in rows:
			group = _group_for_equipment_on(memberships, row.equipment, on_date)
			if group and group in groups:
				in_scope[group].append(row)
			else:
				out_of_scope_litres += flt(row.allocated_litres)
		if not in_scope:
			continue  # no group row touched → the fill is not shown
		for group, group_rows in in_scope.items():
			for row in group_rows:
				basis = row.basis or BASIS_ESTIMATED
				alloc_rows.append(
					{
						"date": on_date,
						"group": group,
						"section": SECTION_ALLOCATION,
						"section_label": _("Allocation (member)"),
						"basis": basis,
						"basis_label": _(basis),
						"equipment": row.equipment,
						"fill": fill_name,
						"project": fill.project,
						"litres": flt(row.allocated_litres, 3),
					}
				)
			if out_of_scope_litres > 0:
				shared_rows.append(
					{
						"date": on_date,
						"group": group,
						"section": SECTION_SHARED,
						"section_label": _("Shared bucket (outside the group)"),
						"basis": BASIS_ESTIMATED,
						"basis_label": _(BASIS_ESTIMATED),
						"equipment": None,
						"fill": fill_name,
						"project": fill.project,
						"litres": flt(out_of_scope_litres, 3),
					}
				)
	return alloc_rows, shared_rows


# ---------- columns and summary ----------


def _columns():
	return [
		{
			"label": _("Date"),
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"label": _("Operating group"),
			"fieldname": "group",
			"fieldtype": "Link",
			"options": GROUP,
			"width": 220,
		},
		{
			"label": _("Section"),
			"fieldname": "section_label",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": _("Basis"),
			"fieldname": "basis_label",
			"fieldtype": "Data",
			"width": 110,
		},
		{
			"label": _("Equipment"),
			"fieldname": "equipment",
			"fieldtype": "Link",
			"options": "Card Equipment",
			"width": 160,
		},
		{
			"label": _("Fill"),
			"fieldname": "fill",
			"fieldtype": "Link",
			"options": FILL,
			"width": 160,
		},
		{
			"label": _("Project"),
			"fieldname": "project",
			"fieldtype": "Link",
			"options": "Project",
			"width": 160,
		},
		{
			"label": _("Litres"),
			"fieldname": "litres",
			"fieldtype": "Float",
			"width": 110,
			"precision": 3,
		},
	]


def _summary(rows):
	"""Group litres and shared-bucket litres as two separate tiles; totals never mixed."""
	group_litres = 0.0
	shared_litres = 0.0
	for row in rows:
		if row["section"] == SECTION_SHARED:
			shared_litres += flt(row["litres"])
		else:
			group_litres += flt(row["litres"])
	return [
		{
			"label": _("Group litres"),
			"value": flt(group_litres, 3),
			"indicator": "Blue",
			"datatype": "Float",
		},
		{
			"label": _("Shared bucket (outside the group)"),
			"value": flt(shared_litres, 3),
			"indicator": "Grey",
			"datatype": "Float",
		},
	]


def _empty_summary():
	return [
		{"label": _("Group litres"), "value": 0.0, "indicator": "Blue", "datatype": "Float"},
		{
			"label": _("Shared bucket (outside the group)"),
			"value": 0.0,
			"indicator": "Grey",
			"datatype": "Float",
		},
	]


def _message_no_groups():
	return _("No operating group of this company is readable to you, or the chosen group is disabled.")


__all__ = [
	"BASIS_ESTIMATED",
	"BASIS_MEASURED",
	"SECTION_ALLOCATION",
	"SECTION_DIRECT",
	"SECTION_SHARED",
	"execute",
	"permitted_companies",
]
