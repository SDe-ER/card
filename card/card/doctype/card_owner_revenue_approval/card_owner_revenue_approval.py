# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""The customer's approval of a conditional customer-side addition of a monthly card (for example a
generator rental), which counts as the crusher owner's revenue only once approved (Owner 2026-11-10).

The record is kept OUTSIDE the card, so an approval given after the card was submitted never changes
the card, its Sales Invoice or any amount. It is information only: nothing here posts or invoices.
Only the approved amount reaches the owner's revenue (Crusher Owner Statement); VAT is never the
owner's."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.attachment_validator import check_attachment_content, require_record_file
from card.constants import THIRD_PARTY

PENDING = "Pending"
APPROVED = "Approved"
PARTIAL = "Partially approved"
REJECTED = "Rejected"
STATUSES = (PENDING, APPROVED, PARTIAL, REJECTED)
ADDITION = "إضافة"


class CardOwnerRevenueApproval(Document):
	def validate(self):
		card = self._card()
		self._set_from_card(card)
		self._set_from_row(card)
		self._validate_status()
		self._validate_unique()
		self._validate_evidence_file()

	def _card(self):
		card = frappe.db.get_value(
			"Card Monthly Card",
			self.monthly_card,
			["name", "company", "equipment", "supplier", "docstatus"],
			as_dict=True,
		)
		if not card:
			frappe.throw(_("Monthly card {0} does not exist.").format(self.monthly_card))
		# the approval describes the card's money: only a user who may read the card records it
		if not frappe.has_permission("Card Monthly Card", "read", card.name):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		if card.docstatus == 2:
			frappe.throw(_("Monthly card {0} is cancelled.").format(card.name))
		return card

	def _set_from_card(self, card):
		equipment = frappe.db.get_value(
			"Card Equipment", card.equipment, ["ownership", "supplier"], as_dict=True
		)
		if not equipment or equipment.ownership != THIRD_PARTY:
			frappe.throw(_("Only a card of third-party equipment has an owner revenue approval."))
		self.company = card.company
		self.equipment = card.equipment
		# a submitted card keeps the owner it was submitted with; a draft follows the equipment
		self.owner_supplier = card.supplier if card.docstatus == 1 and card.supplier else equipment.supplier

	def _set_from_row(self, card):
		row = frappe.db.get_value(
			"Card Monthly Card Adjustment",
			{"name": self.adjustment_row, "parent": card.name, "parenttype": "Card Monthly Card"},
			["side", "adjustment_type", "amount", "description"],
			as_dict=True,
		)
		if not row:
			frappe.throw(_("Row {0} is not an addition of card {1}.").format(self.adjustment_row, card.name))
		if row.side != "Customer" or row.adjustment_type != ADDITION:
			frappe.throw(_("Only a customer-side addition of the card needs the customer's approval."))
		self.gross_amount = flt(row.amount, 2)
		self.description = row.description

	def _validate_status(self):
		if self.approval_status not in STATUSES:
			frappe.throw(_("Invalid approval status {0}.").format(self.approval_status))
		gross = flt(self.gross_amount, 2)
		if self.approval_status == APPROVED:
			self.approved_amount = gross
		elif self.approval_status in (PENDING, REJECTED):
			self.approved_amount = 0
		elif not 0 < flt(self.approved_amount, 2) < gross:
			frappe.throw(
				_("A partial approval is more than zero and less than the card amount {0}.").format(gross)
			)
		# approval is never inferred: the customer's approval date and its evidence are required
		if self.approval_status in (APPROVED, PARTIAL):
			if not self.approval_date:
				frappe.throw(_("Enter the date of the customer's approval."))
			if not self.evidence:
				frappe.throw(_("Attach the customer's approval as evidence."))

	def _validate_unique(self):
		other = frappe.db.get_value(
			"Card Owner Revenue Approval",
			{
				"monthly_card": self.monthly_card,
				"adjustment_row": self.adjustment_row,
				"name": ["!=", self.name or ""],
			},
			"name",
		)
		if other:
			frappe.throw(
				_("Card row {0} already has approval record {1}.").format(self.adjustment_row, other)
			)

	def _validate_evidence_file(self):
		# checked when it is set or changed: private, and this record's own file or the user's own upload
		if not self.evidence or not (self.is_new() or self.has_value_changed("evidence")):
			return
		row = require_record_file(self.evidence, self.doctype, self.name)
		check_attachment_content(self.evidence, file_row=row)
