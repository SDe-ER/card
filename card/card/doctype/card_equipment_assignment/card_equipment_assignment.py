# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, getdate

from card.transfer import sync_equipment_location

# far future for an open-ended (to_date empty) assignment
OPEN_END = "9999-12-31"


class CardEquipmentAssignment(Document):
	"""An equipment's presence on a project over a period. It decides a monthly
	card's project and which card days are valid, so it is written by Card
	Manager (and Equipment Transport), never by Card User, and validated here."""

	def validate(self):
		if (self.is_new() or self.has_value_changed("from_date")) and not self.from_date:
			# R1: an undated row would escape the overlap check and every resolution
			frappe.throw(_("Set the start date of the assignment."))
		self.validate_dates()
		self.company = frappe.db.get_value("Card Equipment", self.equipment, "company")
		self._default_cost_center()
		self._check_period_lock()
		# only what changed is re-validated, so a legacy row is not blocked by an
		# unrelated save (security review LOW-2)
		if self.is_new() or self.has_value_changed("equipment") or self.has_value_changed("project"):
			self.validate_company()
		if self._period_grew():
			self.validate_no_overlap()
		for dropped in self._dropped_periods():
			_refuse_dropped_card_days(*dropped)

	def on_update(self):
		# #56: the equipment's current project / assignment date follow the
		# assignment in force today (a transfer syncs once itself)
		if not frappe.flags.get("card_defer_location_sync"):
			sync_equipment_location(self.equipment)
			before = self.get_doc_before_save()
			if before and before.equipment and before.equipment != self.equipment:
				sync_equipment_location(before.equipment)

	def _default_cost_center(self):
		"""R1: a new assignment (or one moved to another project) names its cost center, the
		project's unless chosen; an existing row keeps what it has (a transport closing it must
		not fail on a project setting that changed since)."""
		if self.cost_center and (self.is_new() or self.has_value_changed("cost_center")):
			if not _valid_cost_center(self.cost_center, self.company):
				frappe.throw(
					_("Cost center {0} is not an active ledger cost center of {1}.").format(
						self.cost_center, self.company
					)
				)
		if not self.cost_center and self.project and (self.is_new() or self.has_value_changed("project")):
			project_cc = frappe.db.get_value("Project", self.project, "cost_center")
			if project_cc and _valid_cost_center(project_cc, self.company):
				self.cost_center = project_cc

	def _check_period_lock(self):
		"""R1: no change may reach a day in the locked period of the equipment's company."""
		from card.period_lock import enforce_from

		before = None if self.is_new() else self.get_doc_before_save()
		if not before:
			enforce_from(self, "save", self.from_date)
			return
		changed = [d[2] for d in self._dropped_periods()]
		if (
			before.project != self.project
			or before.equipment != self.equipment
			or _effective_cc(before) != _effective_cc(self)
		):
			changed.append(min(getdate(x) for x in (before.from_date, self.from_date) if x))
		if self.from_date and before.from_date and getdate(self.from_date) < getdate(before.from_date):
			changed.append(self.from_date)
		if before.to_date and (not self.to_date or getdate(self.to_date) > getdate(before.to_date)):
			changed.append(add_days(before.to_date, 1))
		if changed:
			enforce_from(self, "save", min(getdate(d) for d in changed))

	def on_trash(self):
		if self.from_date:
			from card.period_lock import enforce_from

			enforce_from(self, "delete", self.from_date)
		if self.from_date:
			_refuse_dropped_card_days(self.equipment, self.project, self.from_date, self.to_date)
		if not frappe.flags.get("card_defer_location_sync"):
			sync_equipment_location(self.equipment, exclude=self.name)

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

	def _dropped_periods(self):
		"""(equipment, project, from, to) periods the saved row covered and no longer covers:
		a later start, an earlier or new end (what a transport does when it closes the row),
		or another equipment or project. A to of None is open-ended."""
		before = None if self.is_new() else self.get_doc_before_save()
		if not before or not before.from_date:
			return []
		if before.equipment != self.equipment or before.project != self.project:
			return [(before.equipment, before.project, before.from_date, before.to_date)]
		dropped = []
		if self.from_date and getdate(self.from_date) > getdate(before.from_date):
			dropped.append((self.equipment, self.project, before.from_date, add_days(self.from_date, -1)))
		if self.to_date and (not before.to_date or getdate(self.to_date) < getdate(before.to_date)):
			dropped.append((self.equipment, self.project, add_days(self.to_date, 1), before.to_date))
		return dropped

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
		# D4: one writer per machine at a time. The equipment row lock queues a concurrent
		# writer; the locking read then returns the latest committed rows, which a
		# REPEATABLE READ snapshot read would miss.
		frappe.db.get_value("Card Equipment", self.equipment, "name", for_update=True)
		clash = frappe.db.sql(
			"""
			select name, project, from_date, to_date from `tabCard Equipment Assignment`
			where equipment = %(equipment)s and name != %(name)s and from_date is not null
				and from_date <= %(end)s and ifnull(to_date, %(open_end)s) >= %(start)s
			limit 1 for update
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


def _valid_cost_center(cost_center, company):
	cc = frappe.db.get_value("Cost Center", cost_center, ["company", "is_group", "disabled"], as_dict=True)
	return bool(cc and not cc.is_group and not cc.disabled and (not company or cc.company == company))


def _effective_cc(doc):
	"""The cost center the row stands for (its own, else its project's)."""
	return doc.cost_center or (
		frappe.db.get_value("Project", doc.project, "cost_center") if doc.project else None
	)


def _refuse_dropped_card_days(equipment, project, start, end):
	"""A submitted card day must stay inside an assignment of its project (validate_card_days
	checked it at submit), for the machine itself and for each component of a unit card. The
	equipment row lock queues writers of this machine (D4) and the locking read returns the
	latest committed cards."""
	if not (equipment and project and start):
		return
	frappe.db.get_value("Card Equipment", equipment, "name", for_update=True)
	day = frappe.db.sql(
		"""
		select c.name, d.operation_date from `tabCard Monthly Card Day` d
		join `tabCard Monthly Card` c on c.name = d.parent and d.parenttype = 'Card Monthly Card'
		where c.docstatus = 1 and c.project = %(project)s and d.working_hours > 0
			and d.operation_date between %(start)s and %(end)s
			and (c.equipment = %(equipment)s or exists (
				select 1 from `tabCard Equipment Component` u
				where u.parent = c.equipment and u.parenttype = 'Card Equipment'
					and u.component = %(equipment)s
					and (u.from_date is null or u.from_date <= d.operation_date)
					and (u.to_date is null or u.to_date >= d.operation_date)))
		order by d.operation_date limit 1 for update
		""",
		{
			"equipment": equipment,
			"project": project,
			"start": str(getdate(start)),
			"end": str(getdate(end)) if end else OPEN_END,
		},
		as_dict=True,
	)
	if day:
		frappe.throw(
			_(
				"Submitted card {0} has an operation day of equipment {1} on project {2} on {3}, outside the assignment after this change. Keep the day in the assignment (for a transport, use a later date)."
			).format(day[0].name, equipment, project, frappe.format(day[0].operation_date, "Date"))
		)


# P0 company isolation (Owner 2026-10-20): an assignment has no Company field, so a
# Company User Permission never reaches it. Its company is its equipment's company.


def _restricted_companies(user):
	"""None when ``user`` sees every company; else the companies allowed for BOTH
	assignments and equipment, so an assignment never shows equipment the user cannot open."""
	from card.party_registry import _restricted_companies as restricted

	return restricted(user, "Card Equipment Assignment", "Card Equipment")


def assignment_query_conditions(user=None):
	companies = _restricted_companies(user or frappe.session.user)
	if companies is None:
		return ""
	if not companies:
		return "1=0"
	values = ", ".join(frappe.db.escape(c) for c in companies)
	return (
		"`tabCard Equipment Assignment`.`equipment` in"
		f" (select e.`name` from `tabCard Equipment` e where e.`company` in ({values}))"
	)


def has_assignment_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level twin of the query conditions, for every path (read, REST save,
	create): the equipment the request sends AND, for a saved row, the equipment it
	has in the database must both belong to a permitted company, so a row of another
	company can neither be read, changed, nor moved into the user's company. A
	controller can only deny (Frappe 16 treats a falsy return as a denial)."""
	companies = _restricted_companies(user or frappe.session.user)
	if companies is None:
		return True
	equipment = {doc.get("equipment")}
	if not doc.is_new():
		equipment.add(frappe.db.get_value(doc.doctype, doc.name, "equipment"))
	equipment.discard(None)
	if not equipment:
		return True  # nothing chosen yet; the mandatory field stops the save
	owners = frappe.get_all("Card Equipment", filters={"name": ["in", list(equipment)]}, pluck="company")
	return all(company in companies for company in owners)
