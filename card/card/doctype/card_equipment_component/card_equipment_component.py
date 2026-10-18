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
		if before and before.component == self.component:
			return  # e.g. only the role changed: like the unit's save, a legacy row is not blocked
		if before and self.parenttype == "Card Equipment":
			# #59: a direct row update of the component is refused. The unit's own
			# save is serialized (check_if_latest locks the unit) and recorded in the
			# unit's Version history; frappe's row-save path is neither (update_doc
			# re-saves the unit after the row, so the Version diff sees no change).
			frappe.throw(
				_(
					"To change the component, edit unit {0} itself; a direct row update is not allowed."
				).format(self.parent)
			)
		if self.parenttype != "Card Equipment" or not self.parent:
			return
		# for_update: serialize a standalone row insert with the unit's own save (#59)
		unit = frappe.db.get_value(
			"Card Equipment", self.parent, ["company", "is_unit"], as_dict=True, for_update=True
		)
		if not unit:
			return
		rows = frappe.get_all(
			"Card Equipment Component",
			filters={"parenttype": "Card Equipment", "parent": self.parent},
			fields=["name", "component"],
			order_by="idx",
		)
		components = [self.component if row.name == self.name else row.component for row in rows]
		if self.name not in {row.name for row in rows}:
			components.append(self.component)
		check_unit_components(self.parent, unit.company, unit.is_unit, components)
