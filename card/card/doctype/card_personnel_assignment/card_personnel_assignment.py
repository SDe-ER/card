# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""R1 (CARD 4.5.0): an employee's work on an equipment or a project over a period.

* Effective-dated and append-only: after submit only the end date may change (closing or
  re-opening), never over days in a locked period; corrections are cancel + amend.
* The shares of one employee on any day may not exceed 100 %.
* The company is the employee's; equipment and project must belong to it.
* Submitted by a Card Manager who did not create it (System Manager excepted).
* HRMS stays the owner of attendance, shifts and pay: nothing of that is stored here.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from card.personnel import max_concurrent_share, sync_equipment_operator

APPROVER_ROLES = {"System Manager", "Card Manager"}


class CardPersonnelAssignment(Document):
	def validate(self):
		emp = frappe.db.get_value(
			"Employee",
			self.employee,
			["company", "status", "date_of_joining", "relieving_date", "employee_name"],
			as_dict=True,
		)
		if not emp:
			frappe.throw(_("Choose the employee."))
		self.company = emp.company
		self.employee_name = emp.employee_name
		self._check_target()
		self._check_dates(emp)
		if not 0 < flt(self.share_percent) <= 100:
			frappe.throw(_("The share must be above 0 and at most 100 %."))

	def before_update_after_submit(self):
		if not APPROVER_ROLES & set(frappe.get_roles()):
			frappe.throw(
				_("Only a Card Manager can change a submitted personnel assignment."), frappe.PermissionError
			)
		emp = frappe.db.get_value(
			"Employee", self.employee, ["date_of_joining", "relieving_date"], as_dict=True
		)
		self._check_dates(emp)
		self._check_after_submit()

	def _check_target(self):
		if self.assignment_type == "Equipment":
			self.project = None
			self.cost_center = None
			if not self.card_equipment:
				frappe.throw(_("Choose the equipment."))
			company = frappe.db.get_value("Card Equipment", self.card_equipment, "company")
			if company != self.company:
				frappe.throw(
					_("Equipment {0} belongs to company {1}; the employee belongs to {2}.").format(
						self.card_equipment, company, self.company
					)
				)
		else:
			self.card_equipment = None
			if not self.project:
				frappe.throw(_("Choose the project."))
			company = frappe.db.get_value("Project", self.project, "company")
			if company != self.company:
				frappe.throw(
					_("Project {0} belongs to company {1}; the employee belongs to {2}.").format(
						self.project, company, self.company
					)
				)
			if self.cost_center:
				cc = frappe.db.get_value(
					"Cost Center", self.cost_center, ["company", "is_group", "disabled"], as_dict=True
				)
				if not cc or cc.company != self.company or cc.is_group or cc.disabled:
					frappe.throw(
						_("Cost center {0} is not an active ledger cost center of {1}.").format(
							self.cost_center, self.company
						)
					)

	def _check_dates(self, emp):
		if self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("The assignment end date is before its start date."))
		if emp.date_of_joining and getdate(self.from_date) < getdate(emp.date_of_joining):
			frappe.throw(
				_("The assignment starts before the employee's joining date {0}.").format(
					frappe.format(emp.date_of_joining, "Date")
				)
			)
		if emp.relieving_date and (not self.to_date or getdate(self.to_date) > getdate(emp.relieving_date)):
			frappe.throw(
				_("The assignment must end by the employee's relieving date {0}.").format(
					frappe.format(emp.relieving_date, "Date")
				)
			)

	def _check_after_submit(self):
		"""Only to_date may change after submit (allow_on_submit); re-check the shares when the
		period grows and refuse a change that reaches into a locked period."""
		before = self.get_doc_before_save()
		if not before:
			return
		old, new = before.to_date, self.to_date
		if (old or None) == (new or None):
			return
		# the days whose assignment changes start the day after the earlier end
		ends = [getdate(d) for d in (old, new) if d]
		first_changed = frappe.utils.add_days(min(ends), 1)
		from card.period_lock import enforce_from

		enforce_from(self, "change", first_changed)
		grew = not new or (old and getdate(new) > getdate(old))
		if grew:
			self._check_share()

	def before_submit(self):
		if self.owner == frappe.session.user and "System Manager" not in frappe.get_roles():
			frappe.throw(_("The creator of an assignment may not submit it."), frappe.PermissionError)
		if not APPROVER_ROLES & set(frappe.get_roles()):
			frappe.throw(_("Only a Card Manager can submit a personnel assignment."), frappe.PermissionError)
		from card.period_lock import enforce_from

		enforce_from(self, "submit", self.from_date)
		self._check_share()

	def _check_share(self):
		# one writer per employee at a time: the check and the save stay consistent
		frappe.db.get_value("Employee", self.employee, "name", for_update=True)
		end = self.to_date or "9999-12-31"
		total = max_concurrent_share(
			self.employee,
			self.from_date,
			end,
			exclude=self.name,
			extra=(self.from_date, self.to_date, self.share_percent),
		)
		if total > 100 + 1e-6:
			frappe.throw(
				_(
					"Employee {0} would be assigned {1} % on a day of this period; at most 100 % is allowed."
				).format(self.employee_name or self.employee, flt(total, 2))
			)

	def on_submit(self):
		sync_equipment_operator(self.card_equipment)

	def on_update_after_submit(self):
		ended = self.to_date and getdate(self.to_date) < getdate(frappe.utils.today())
		sync_equipment_operator(self.card_equipment, released=self.employee if ended else None)

	def before_cancel(self):
		from card.period_lock import enforce_from

		enforce_from(self, "cancel", self.from_date)

	def on_cancel(self):
		sync_equipment_operator(self.card_equipment, released=self.employee)
