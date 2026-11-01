# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-100: one service of one machine (replaces Maintenance Request / Maintenance Request
For Asset of equipment_manager)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, getdate

from card.company import validate_equipment_company

ACTIVE, IN_WORKSHOP = "نشطة", "في الصيانة"


class CardMaintenanceOrder(Document):
	def validate(self):
		eq = frappe.db.get_value(
			"Card Equipment",
			self.equipment,
			["company", "current_project", "cost_center", "equipment_name"],
			as_dict=True,
		)
		if not eq:
			frappe.throw(_("Choose the equipment."))
		self.company = eq.company
		validate_equipment_company(self, "equipment")
		if not self.project and eq.current_project:
			self.project = eq.current_project
		if not self.cost_center and eq.cost_center:
			self.cost_center = eq.cost_center
		if flt(self.meter_reading) < 0:
			frappe.throw(_("The meter reading cannot be negative."))
		if getdate(self.service_date) > getdate():
			frappe.throw(_("The service date cannot be in the future."))
		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: the quantity must be above zero.").format(row.idx))
		self._set_downtime()
		self._check_work_status()
		from card.maintenance import plan_for, plan_lines

		plan = plan_for(self.equipment)
		if self.maintenance_plan and (not plan or plan.name != self.maintenance_plan):
			frappe.throw(
				_("Plan {0} is not the active plan of this equipment.").format(self.maintenance_plan)
			)
		if self.services_done:
			names = {line.service_name for line in plan_lines(plan)}
			for row in self.services_done:
				if row.service_name not in names:
					frappe.throw(
						_("Row {0}: {1} is not a service line of the equipment's plan.").format(
							row.idx, row.service_name
						)
					)

	def _check_work_status(self):
		"""The work status moves only through approve / start / submit / cancel (never by
		editing the field); a new order is Approved unless the due scan created it."""
		before = self.get_doc_before_save()
		if self.flags.get("card_status_change"):
			return
		if self.is_new() or not before:
			from card.settings import setting

			# with the due workflow on, every scheduled service needs a Card Manager's approval
			due_flow = frappe.utils.cint(setting("auto_create_due_orders"))
			self.work_status = "Due" if due_flow and self.service_type == "Scheduled Service" else "Approved"
			self.auto_created = 0
			self.approved_by = self.approved_on = None
			return
		for field in ("work_status", "approved_by", "approved_on", "auto_created"):
			if (before.get(field) or None) != (self.get(field) or None):
				self.set(field, before.get(field))

	def before_submit(self):
		if self.work_status == "Due":
			frappe.throw(_("Approve the maintenance order first."))
		self.work_status = "Completed"

	def before_cancel(self):
		self.work_status = "Cancelled"

	def _set_downtime(self):
		if self.service_type not in ("Repair", "Breakdown"):
			self.out_of_service_from = self.back_in_service_on = None
			self.downtime_hours = 0
			return
		if self.back_in_service_on and self.out_of_service_from:
			if get_datetime(self.back_in_service_on) < get_datetime(self.out_of_service_from):
				frappe.throw(_("Back in service cannot be before out of service."))
			from frappe.utils import time_diff_in_hours

			self.downtime_hours = flt(
				time_diff_in_hours(self.back_in_service_on, self.out_of_service_from), 1
			)
		else:
			self.downtime_hours = 0

	def before_update_after_submit(self):
		self._set_downtime()

	def on_update_after_submit(self):
		self._sync_availability()

	def _sync_availability(self):
		"""A breakdown or repair takes the machine out of service (في الصيانة) until it is back."""
		if self.service_type not in ("Repair", "Breakdown"):
			return
		status = frappe.db.get_value("Card Equipment", self.equipment, "status")
		if self.back_in_service_on and status == IN_WORKSHOP and not _other_open_breakdown(self):
			frappe.db.set_value("Card Equipment", self.equipment, "status", ACTIVE)
		elif not self.back_in_service_on and status == ACTIVE:
			frappe.db.set_value("Card Equipment", self.equipment, "status", IN_WORKSHOP)

	def on_submit(self):
		from card.maintenance import refresh_status
		from card.meter import add_reading, refresh_current_meter

		# the status is refreshed once below, after the last service has moved (a refresh in
		# between would see the new meter with the old baseline and raise a false "due")
		reading = add_reading(
			self.equipment,
			self.meter_reading,
			get_datetime(self.service_date).replace(hour=12),
			"Maintenance Order",
			self.doctype,
			self.name,
			refresh=False,
		)
		before = frappe.db.get_value(
			"Card Equipment", self.equipment, ["last_service_meter", "last_service_date"], as_dict=True
		)
		self.db_set(
			{
				"meter_reading_record": reading.name,
				"previous_service_meter": before.last_service_meter,
				"previous_service_date": before.last_service_date,
			}
		)
		if self.service_type == "Scheduled Service":
			_recompute_last_service(self.equipment)
		refresh_current_meter(self.equipment)
		refresh_status(self.equipment)
		self._sync_availability()

	def on_cancel(self):
		from card.maintenance import refresh_status
		from card.meter import reject_for_source

		reject_for_source(
			self.doctype, self.name, _("The maintenance order {0} was cancelled.").format(self.name)
		)
		if self.service_type == "Scheduled Service":
			_recompute_last_service(self.equipment)
		if self.service_type in ("Repair", "Breakdown") and not self.back_in_service_on:
			if frappe.db.get_value("Card Equipment", self.equipment, "status") == IN_WORKSHOP:
				if not _other_open_breakdown(self):
					frappe.db.set_value("Card Equipment", self.equipment, "status", ACTIVE)
		refresh_status(self.equipment)


def _other_open_breakdown(order):
	"""Another submitted repair/breakdown of the machine still keeps it out of service."""
	return bool(
		frappe.db.exists(
			"Card Maintenance Order",
			{
				"equipment": order.equipment,
				"docstatus": 1,
				"name": ["!=", order.name],
				"service_type": ["in", ["Repair", "Breakdown"]],
				"back_in_service_on": ["is", "not set"],
			},
		)
	)


def _recompute_last_service(equipment):
	"""Last service = the latest submitted Scheduled Service order whose meter reading is
	Valid (a back-dated or implausible order never moves it); without one, the value the
	equipment had before its first CARD order."""
	orders = frappe.get_all(
		"Card Maintenance Order",
		filters={"equipment": equipment, "service_type": "Scheduled Service", "docstatus": ["!=", 0]},
		fields=[
			"name",
			"docstatus",
			"service_date",
			"meter_reading",
			"meter_reading_record",
			"previous_service_meter",
			"previous_service_date",
		],
		order_by="creation asc",
	)
	if not orders:
		return
	valid = set(
		frappe.get_all(
			"Card Meter Reading",
			filters={
				"name": ["in", [o.meter_reading_record for o in orders if o.meter_reading_record]],
				"status": "Valid",
			},
			pluck="name",
		)
	)
	live = [o for o in orders if o.docstatus == 1 and o.meter_reading_record in valid]
	if live:
		last = max(live, key=lambda o: (getdate(o.service_date), flt(o.meter_reading)))
		values = {"last_service_meter": flt(last.meter_reading), "last_service_date": last.service_date}
	else:
		values = {
			"last_service_meter": flt(orders[0].previous_service_meter),
			"last_service_date": orders[0].previous_service_date,
		}
	frappe.db.set_value("Card Equipment", equipment, values)
