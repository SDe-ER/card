# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document
from frappe.utils import flt


class ProjectDieselFill(Document):
	def validate(self):
		# Amount is litres x unit price; the accounting posting (Purchase Invoice on
		# the project) is added in a later stage, gated by owner approval.
		self.amount = flt(flt(self.litres) * flt(self.unit_price), 2)
