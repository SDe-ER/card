# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document

from card.card.doctype.card_equipment.card_equipment import check_unit_components


class CardEquipmentComponent(Document):
	def validate(self):
		"""#56: runs only when the row itself is saved (REST PUT on the row,
		frappe.client.save); the unit's own save checks its rows in
		CardEquipment.validate_components and does not call this. The row is
		checked as part of its unit, with the unit's rules."""
		if frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		before = self.get_doc_before_save()
		if before and any(before.get(f) != self.get(f) for f in ("parent", "parenttype", "parentfield")):
			frappe.throw(_("A component row cannot be moved to another unit."))
		if before and all(before.get(f) == self.get(f) for f in ("component", "from_date", "to_date")):
			return  # e.g. only the role changed: like the unit's save, a legacy row is not blocked
		if self.parenttype != "Card Equipment":
			return
		unit = frappe.db.get_value("Card Equipment", self.parent, ["company", "is_unit"], as_dict=True)
		if not unit:
			return
		rows = frappe.get_all(
			"Card Equipment Component",
			filters={"parenttype": "Card Equipment", "parent": self.parent},
			fields=["name", "component", "from_date", "to_date"],
			order_by="idx",
		)
		mine = frappe._dict(component=self.component, from_date=self.from_date, to_date=self.to_date)
		components = [mine if row.name == self.name else row for row in rows]
		if self.name not in {row.name for row in rows}:
			components.append(mine)
		check_unit_components(self.parent, unit.company, unit.is_unit, components)
