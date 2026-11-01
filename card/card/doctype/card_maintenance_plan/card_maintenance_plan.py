# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-100: service interval and parts kit for an equipment model or one machine."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class CardMaintenancePlan(Document):
	def validate(self):
		if self.applies_to == "Equipment":
			self.equipment_model = None
			if not self.card_equipment:
				frappe.throw(_("Choose the equipment of this plan."))
		else:
			self.card_equipment = None
			if not self.equipment_model:
				frappe.throw(_("Choose the equipment model of this plan."))
		if flt(self.interval_hours) <= 0 and flt(self.interval_litres) <= 0 and not self.service_lines:
			frappe.throw(_("Set the service interval in hours or in litres."))
		seen = set()
		for line in self.service_lines:
			name = (line.service_name or "").strip()
			if name in seen:
				frappe.throw(_("Service line {0}: {1} is listed twice.").format(line.idx, name))
			seen.add(name)
			line.service_name = name
			if flt(line.interval_hours) <= 0 or flt(line.warn_before_hours) < 0:
				frappe.throw(_("Service line {0}: set an interval above zero.").format(line.idx))
			if flt(line.warn_before_hours) >= flt(line.interval_hours):
				frappe.throw(
					_("Service line {0}: the warning must come before the service interval.").format(line.idx)
				)
		if flt(self.interval_hours) < 0 or flt(self.interval_litres) < 0 or flt(self.warn_before_hours) < 0:
			frappe.throw(_("Intervals cannot be negative."))
		if flt(self.interval_hours) and flt(self.warn_before_hours) >= flt(self.interval_hours):
			frappe.throw(_("The warning must come before the service interval."))
		for row in self.kit:
			if flt(row.qty) <= 0:
				frappe.throw(_("Kit row {0}: the quantity must be above zero.").format(row.idx))
		# one active plan per model or machine
		target = self.card_equipment or self.equipment_model
		self.plan_key = f"{self.applies_to}:{target}" if self.is_active else None

	def on_update(self):
		from card.maintenance import refresh_status

		for equipment in self._equipment():
			refresh_status(equipment)

	def _equipment(self):
		if self.card_equipment:
			return [self.card_equipment]
		return frappe.get_all(
			"Card Equipment", filters={"equipment_model": self.equipment_model}, pluck="name"
		)
