# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document


class GLPostingSource(Document):
	"""#57: the rows are written once, with their log's insert (which does not
	run these methods); a row saved or deleted on its own (REST on the row,
	frappe.client) is refused."""

	def validate(self):
		frappe.throw(_("The sources of a posting log cannot be changed."))

	def on_trash(self):
		frappe.throw(_("The sources of a posting log cannot be changed."))
