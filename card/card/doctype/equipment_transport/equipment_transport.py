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
		self._sync_items()
		for row in self.items:
			validate_equipment_company(frappe._dict(company=self.company, equipment=row.card_equipment))
		self._apply_transport_price()
		self._split_amount()

	def _sync_items(self):
		"""v3.0.0: the equipment table is the source; the header `equipment` mirrors its
		first row for links and older readers. A caller that still sets only the header
		(older API/tests) gets it moved into the table."""
		if self.docstatus == 0:
			# only submit writes these (card.transfer); a draft must not carry links typed
			# through the API, or a later cancel would delete/reopen someone else's assignment
			self.previous_assignment = self.created_assignment = None
			for row in self.items:
				row.previous_assignment = row.created_assignment = None
		if not self.items and self.equipment:
			self.append("items", {"card_equipment": self.equipment})
		seen = set()
		for row in self.items:
			if row.card_equipment in seen:
				frappe.throw(_("Equipment {0} is listed twice in this transport.").format(row.card_equipment))
			seen.add(row.card_equipment)
		self.equipment = self.items[0].card_equipment if self.items else None

	def _split_amount(self):
		"""Owner decision 2026-10-18: the trip cost is split equally over the equipment;
		any share may be edited, but the shares must add up to the trip cost. A share typed
		by hand is remembered (`manual_share`) and kept; every other share is recomputed
		on each save from what the typed ones leave, so editing one share or the trip
		cost rebalances the rest. Clearing a share hands it back to the equal split."""
		if not self.items:
			return
		total = flt(self.amount, 2)
		before = self.get_doc_before_save()
		previous = {r.name: flt(r.amount, 2) for r in (before.get("items") or [])} if before else {}
		for row in self.items:
			amount = flt(row.amount, 2)
			if not amount:
				row.manual_share = 0
			elif before is None or previous.get(row.name) != amount:
				row.manual_share = 1  # typed now (a new document's rows count as typed)
			if not row.manual_share:
				row.amount = 0
		self._fill_empty_shares(total)
		shares = self._shares()
		if shares != total:
			frappe.throw(
				_("The equipment cost shares add up to {0}, but the transport cost is {1}.").format(
					shares, total
				)
			)
		for row in self.items:
			if flt(row.amount) < 0:
				frappe.throw(_("A cost share cannot be negative ({0}).").format(row.card_equipment))

	def _shares(self):
		return flt(sum(flt(r.amount, 2) for r in self.items), 2)

	def _fill_empty_shares(self, total):
		empty = [row for row in self.items if not flt(row.amount)]
		if not empty:
			return
		remaining = flt(total - self._shares(), 2)
		share = flt(remaining / len(empty), 2)
		for row in empty:
			row.amount = share
		# rounding cents go to the last empty row so the shares add up exactly
		empty[-1].amount = flt(remaining - share * (len(empty) - 1), 2)

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
				_(
					"Only users with role {0} may change the transport amount for project {1} (configured: {2})."
				).format(role, self.project, configured)
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
