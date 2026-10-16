# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

# far future for an open-ended (to_date empty) assignment
OPEN_END = "9999-12-31"


class CardEquipmentAssignment(Document):
	"""An equipment's presence on a project over a period. It decides a monthly
	card's project and which card days are valid, so it is written by Card
	Manager (and Equipment Transport), never by Card User, and validated here."""

	def validate(self):
		self.validate_dates()
		# only what changed is re-validated, so a legacy row is not blocked by an
		# unrelated save (security review LOW-2)
		if self.is_new() or self.has_value_changed("equipment") or self.has_value_changed("project"):
			self.validate_company()
		if self._period_grew():
			self.validate_no_overlap()

	def _period_grew(self):
		"""True for a new row, a changed equipment, or a period that now covers
		days it did not cover (an earlier start or a later/open end). Shortening a
		period — what a transfer does when it closes an assignment — cannot create
		an overlap, so it is not re-checked."""
		if self.is_new() or self.has_value_changed("equipment"):
			return True
		before = self.get_doc_before_save()
		if not before:
			return True
		if self.from_date and before.from_date and getdate(self.from_date) < getdate(before.from_date):
			return True
		if not self.to_date and before.to_date:
			return True  # reopened (open-ended)
		if self.to_date and before.to_date and getdate(self.to_date) > getdate(before.to_date):
			return True
		return bool(self.from_date and not before.from_date)

	def validate_dates(self):
		if self.from_date and self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("The assignment end date is before its start date."))

	def validate_company(self):
		if not (self.equipment and self.project):
			return
		eq_company = frappe.db.get_value("Card Equipment", self.equipment, "company")
		project_company = frappe.db.get_value("Project", self.project, "company")
		if eq_company and project_company and eq_company != project_company:
			frappe.throw(
				_("Equipment {0} belongs to company {1}; project {2} belongs to {3}.").format(
					self.equipment, eq_company, self.project, project_company
				)
			)

	def validate_no_overlap(self):
		if not (self.equipment and self.from_date):
			return
		start = str(getdate(self.from_date))
		end = str(getdate(self.to_date)) if self.to_date else OPEN_END
		clash = frappe.db.sql(
			"""
			select name, project, from_date, to_date from `tabCard Equipment Assignment`
			where equipment = %(equipment)s and name != %(name)s and from_date is not null
				and from_date <= %(end)s and ifnull(to_date, %(open_end)s) >= %(start)s
			limit 1
			""",
			{
				"equipment": self.equipment,
				"name": self.name or "",
				"start": start,
				"end": end,
				"open_end": OPEN_END,
			},
			as_dict=True,
		)
		if clash:
			c = clash[0]
			frappe.throw(
				_("Equipment {0} is already assigned to project {1} from {2} to {3}.").format(
					self.equipment, c.project, c.from_date, c.to_date or _("(open)")
				)
			)
