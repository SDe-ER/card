# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-160 (#31; closure plan WP-J): Equipment Operating Group.

A group of equipment of ONE company that operates together (for example a crusher plant made
of a crusher, a generator and an excavator). The group is a report-only grouping — it writes
no GL, changes no card, no fill and no allocation (FR-100 preserved). The Diesel Group
Analysis report (``card.card.report.diesel_group_analysis``) uses the group to display
Σ litres of its member equipment + a shared bucket for the same tank fills' non-member
allocations, so a litre is never counted twice (owner acceptance criterion on #31).

Rules enforced here on every write path (form save, REST insert / PUT with docstatus = 0,
``frappe.client.set_value``, savedocs, bulk update):

- ``group_name`` and ``company`` are required; both are ``set_only_once`` and the record's
  name derives from them (``<group> - <abbr>``, like Card Stop Reason). A second group with
  the same ``group_name`` in the same company is refused by the DB (unique name).
- Every ``members`` row names a Card Equipment. Each equipment belongs to at most ONE active
  group of its company at a time: a second membership whose date range overlaps with any
  existing active group's row for the same equipment is refused, under a locking read on
  ``tabEquipment Operating Group Member`` joined to the parent (Lesson 4 concurrency).
- Member equipment must belong to the group's company (``check_child_companies``, FR-131).
  An equipment of another company is refused with a clear message.
- ``effective_from`` and ``effective_to``, when both set on a row, require from <= to.
- A disabled (``enabled = 0``) group is treated as inactive: its members are free for another
  group. The default is ``enabled = 1``.

No DocPerm or role is widened beyond O-09/16/20 (AGENTS.md): the permissions on the JSON mirror
the master DocTypes of the same wave (Card Stop Reason, Card Diesel Price), read-only to
Supervisor, User and Accounts Manager; write to Card Manager and System Manager. Scoping to
the company is picked up from ``card.company_scope`` (FR-131) through the hooks registered
for this DocType in ``card/hooks.py`` ``_COMPANY_SCOPED``."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate

from card.company_scope import check_child_companies


def group_docname(group_name, company):
	"""Company-aware name: ``<group> - <abbr>``; same pattern as Card Stop Reason / ERPNext masters."""
	abbr = frappe.get_cached_value("Company", company, "abbr") or company
	return "{0} - {1}".format((group_name or "").strip(), abbr)


class EquipmentOperatingGroup(Document):
	def autoname(self):
		self.group_name = (self.group_name or "").strip()
		self.name = group_docname(self.group_name, self.company)
		if frappe.db.exists(self.doctype, self.name):
			frappe.throw(
				_("Operating group {0} already exists for company {1}.").format(
					self.group_name, self.company
				),
				frappe.DuplicateEntryError,
			)

	def validate(self):
		if not (self.group_name or "").strip():
			frappe.throw(_("Enter the operating group name."))
		if not self.company:
			frappe.throw(_("Select the company."))
		# FR-131: every member equipment must belong to the group's company. check_child_companies
		# walks the stored company of each linked Card Equipment and refuses a cross-company row
		# with the row indexes in the error message.
		check_child_companies(self, "members", "equipment")
		self._validate_member_dates()
		self._refuse_duplicate_equipment_in_group()
		self._refuse_overlap_with_other_groups()

	def _validate_member_dates(self):
		for row in self.get("members") or []:
			if row.effective_from and row.effective_to and getdate(row.effective_from) > getdate(
				row.effective_to
			):
				frappe.throw(
					_(
						"Row {0}: Effective from ({1}) is after Effective to ({2})."
					).format(row.idx, row.effective_from, row.effective_to),
					frappe.ValidationError,
				)

	def _refuse_duplicate_equipment_in_group(self):
		"""An equipment on two member rows of THIS group with overlapping dates is refused: it
		would be counted twice by the Diesel Group Analysis sums on the overlap days."""
		seen = []
		for row in self.get("members") or []:
			if not row.equipment:
				continue
			start = getdate(row.effective_from) if row.effective_from else None
			end = getdate(row.effective_to) if row.effective_to else None
			for other_idx, other_eq, other_start, other_end in seen:
				if other_eq != row.equipment:
					continue
				if _ranges_overlap(start, end, other_start, other_end):
					frappe.throw(
						_(
							"Rows {0} and {1} name the same equipment {2} on overlapping dates."
						).format(other_idx, row.idx, row.equipment),
						frappe.ValidationError,
					)
			seen.append((row.idx, row.equipment, start, end))

	def _refuse_overlap_with_other_groups(self):
		"""Every member equipment belongs to at most ONE active group of its company at a time.

		Lesson 4 concurrency: read the sibling groups' member rows with ``frappe.qb ... .for_update()``
		through a join to ``tabEquipment Operating Group`` so under REPEATABLE READ the second of two
		concurrent saves sees the first one's committed rows and is refused. A disabled group is not
		active and never blocks another group."""
		if not cint(self.enabled):
			return
		members = [row for row in (self.get("members") or []) if row.equipment]
		if not members:
			return
		equipment = sorted({row.equipment for row in members})
		Parent = frappe.qb.DocType("Equipment Operating Group")
		Member = frappe.qb.DocType("Equipment Operating Group Member")
		query = (
			frappe.qb.from_(Member)
			.inner_join(Parent)
			.on(Member.parent == Parent.name)
			.select(
				Parent.name.as_("group_name"),
				Parent.group_name.as_("group_label"),
				Member.equipment.as_("equipment"),
				Member.effective_from.as_("effective_from"),
				Member.effective_to.as_("effective_to"),
			)
			.where(Parent.company == self.company)
			.where(Parent.enabled == 1)
			.where(Member.equipment.isin(equipment))
			.for_update()
		)
		if not self.is_new():
			query = query.where(Parent.name != self.name)
		rows = query.run(as_dict=True)
		clashes = []
		for row in self.get("members") or []:
			if not row.equipment:
				continue
			start = getdate(row.effective_from) if row.effective_from else None
			end = getdate(row.effective_to) if row.effective_to else None
			for other in rows:
				if other.equipment != row.equipment:
					continue
				other_start = getdate(other.effective_from) if other.effective_from else None
				other_end = getdate(other.effective_to) if other.effective_to else None
				if _ranges_overlap(start, end, other_start, other_end):
					clashes.append((row.idx, row.equipment, other.group_name))
					break
		if clashes:
			frappe.throw(
				_(
					"Equipment is already in another active operating group of this company on overlapping dates: {0}"
				).format(
					", ".join(
						"{0} (row {1}, other group: {2})".format(eq, idx, other)
						for idx, eq, other in clashes
					)
				),
				frappe.ValidationError,
			)


def _ranges_overlap(a_start, a_end, b_start, b_end):
	"""Two half-open date ranges overlap. Empty start = -infinity; empty end = +infinity."""
	if a_end and b_start and a_end < b_start:
		return False
	if b_end and a_start and b_end < a_start:
		return False
	return True
