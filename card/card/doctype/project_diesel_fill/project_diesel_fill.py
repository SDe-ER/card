# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.company import single_company
from card.settings import setting


class ProjectDieselFill(Document):
	def validate(self):
		if not self.company:
			self.company = single_company()  # F.8: single-company system
		self._enforce_diesel_supplier()
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

	def _enforce_diesel_supplier(self):
		"""F.1 diesel supplier policy. Fixed: the Settings supplier is forced and
		NOBODY may change it. Variable: it is the default; only the permitted role
		may pick another. A legacy fill resaved with its historical supplier
		unchanged is always allowed. No-op while Settings has no supplier."""
		default_supplier = setting("diesel_supplier")
		if not default_supplier:
			return
		if not self.supplier:
			self.supplier = default_supplier
			return
		if self.supplier == default_supplier:
			return
		before = self.get_doc_before_save()
		if before is not None and before.get("supplier") == self.supplier:
			return  # unchanged on this save (historical data)
		policy = setting("diesel_supplier_policy") or "متغير"
		if policy == "ثابت":
			frappe.throw(
				_("The diesel supplier is fixed in Settings ({0}) and cannot be changed.").format(default_supplier)
			)
		role = setting("diesel_supplier_editor_role") or "Card Manager"
		if frappe.session.user != "Administrator" and role not in frappe.get_roles():
			frappe.throw(_("Only users with role {0} may change the diesel supplier.").format(role))
