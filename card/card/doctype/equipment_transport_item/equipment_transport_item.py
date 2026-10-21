# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class EquipmentTransportItem(Document):
	"""The hooks below run only when the row itself is written: POST/PUT/DELETE
	/api/resource/Equipment Transport Item (frappe.api.v1), frappe.client.save of a row,
	frappe.delete_doc of a row, also when sent as a cancel (docstatus 2). Such a write
	checks only the transport's permission and skips the transport's validate (company, movement, duplicates, cost shares, assignment
	links), and a cancel then acts on the row (card.transfer.reverse_transfer). The
	transport's own save, submit, cancel and delete write its rows without calling them,
	as do frappe.client.insert/set_value/delete_doc of a row (they go through the
	transport). So rows are written through the transport only, like #59 for unit
	components."""

	def validate(self):
		self._refuse_standalone_write()

	def before_update_after_submit(self):
		self._refuse_standalone_write()

	def before_cancel(self):
		# a row saved alone with docstatus 2 is a "cancel" in frappe: no validate runs
		self._refuse_standalone_write()

	def on_trash(self):
		self._refuse_standalone_write()

	def _refuse_standalone_write(self):
		if frappe.flags.in_patch or frappe.flags.in_install or frappe.flags.in_migrate:
			return
		frappe.throw(
			_(
				"To change the equipment, edit transport {0} itself; a direct row write is not allowed."
			).format(self.parent),
			frappe.PermissionError,
		)
