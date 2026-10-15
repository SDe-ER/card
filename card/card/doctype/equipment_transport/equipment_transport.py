# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.company import single_company, validate_equipment_company
from card.settings import setting
from card.transfer import apply_transfer, check_cancel_allowed, reverse_transfer


class EquipmentTransport(Document):
	def validate(self):
		if not self.company:
			self.company = single_company()  # F.8: default to THE company
		validate_equipment_company(self)  # F.8: consistency, never a creation block
		self._apply_transport_price()

	def _apply_transport_price(self):
		"""F.1: the amount defaults from the Settings per-project price table;
		changing a configured price needs the permitted role. Projects without a
		row keep free manual entry. Historical docs resaved unchanged pass."""
		if not self.project:
			return
		rows = frappe.get_all(
			"Card Project Transport Price",
			filters={"parent": "Card Settings", "project": self.project},
			fields=["amount"],
			limit=1,
			parent_doctype="Card Settings",
		)
		if not rows:
			return
		configured = flt(rows[0].amount)
		if not flt(self.amount):
			self.amount = configured
			return
		if flt(self.amount) == configured:
			return
		before = self.get_doc_before_save()
		# "unchanged" only counts for the SAME project: switching an amount typed
		# under free entry onto a configured project must re-pass the role gate.
		if (
			before is not None
			and flt(before.get("amount")) == flt(self.amount)
			and before.get("project") == self.project
		):
			return
		role = setting("transport_price_editor_role") or "Card Manager"
		if frappe.session.user != "Administrator" and role not in frappe.get_roles():
			frappe.throw(
				_("Only users with role {0} may change the transport amount for project {1} (configured: {2}).").format(
					role, self.project, configured
				)
			)

	# The accounting posting (Purchase Invoice to the transport supplier, cost on the
	# project) is added in a later stage, gated by owner approval.
	def on_submit(self):
		# Transport = a location transfer: move the equipment to the new project.
		apply_transfer(self)

	def before_cancel(self):
		# Guards run before docstatus flips, so a block keeps the doc submitted.
		check_cancel_allowed(self)

	def on_cancel(self):
		reverse_transfer(self)
