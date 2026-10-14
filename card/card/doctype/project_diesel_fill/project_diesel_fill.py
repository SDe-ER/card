# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

from frappe.model.document import Document
from frappe.utils import flt


class ProjectDieselFill(Document):
	def validate(self):
		# Default the unit price from Card Company Settings only when left blank;
		# an explicitly entered price is kept. Independent of enable_accounting.
		if not self.unit_price and self.company:
			from card.accounting_settings import get_company_settings

			row = get_company_settings(self.company, throw=False)
			price = row.get("diesel_unit_price") if row else None
			if price:
				self.unit_price = price
		# Amount is litres x unit price; the accounting posting (Purchase Invoice on
		# the project) is added in a later stage, gated by owner approval.
		self.amount = flt(flt(self.litres) * flt(self.unit_price), 2)
