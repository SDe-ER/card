# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""A documented amount deducted from a third-party equipment owner's dues (Owner 2026-11-10): a
recorded share of a shared expense (managed partner), or an amount the company paid on the owner's
behalf (self-operating owner). Every line names its submitted source document, so each economic
expense is deducted once: the lines of one source never exceed the source's amount, and a source that
already charges the owner's party in the ledger is not deducted again.

Information only: only submitted lines count in the Crusher Owner Statement; nothing here posts."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from card.constants import OWNER_MODEL_MANAGED, THIRD_PARTY

# the source amount each line may share (before VAT where the document has one; the company keeps input VAT)
SOURCE_AMOUNT_FIELDS = {
	"Journal Entry": "total_debit",
	"Purchase Invoice": "base_net_total",
	"Payment Entry": "base_paid_amount",
	"Expense Claim": "total_sanctioned_amount",
	"Stock Entry": "total_outgoing_value",
	"Salary Slip": "gross_pay",
}


class CardOwnerDeduction(Document):
	def validate(self):
		equipment = frappe.db.get_value(
			"Card Equipment",
			self.equipment,
			["ownership", "supplier", "company", "owner_model"],
			as_dict=True,
		)
		if not equipment or equipment.ownership != THIRD_PARTY:
			frappe.throw(_("Owner deductions are recorded only for third-party equipment."))
		owner, model = self._owner_on_date(equipment)
		# a self-operating owner bears only the documented amounts paid on its behalf (Owner 2026-11-10)
		if self.deduction_type == "Shared expense" and model != OWNER_MODEL_MANAGED:
			frappe.throw(_("A shared expense is deducted only from a managed partner."))
		self.company = equipment.company
		self.owner_supplier = owner
		if flt(self.amount, 2) <= 0:
			frappe.throw(_("The deduction amount must be more than zero."))
		self._source()

	def _owner_on_date(self, equipment):
		"""The owner and owner model in force on the posting date: those of the machine's submitted
		third-party card covering that date (the card is the history), else the machine's current ones."""
		card = None
		if self.posting_date:
			card = frappe.db.get_value(
				"Card Monthly Card",
				{
					"equipment": self.equipment,
					"docstatus": 1,
					"ownership": THIRD_PARTY,
					"from_date": ["<=", self.posting_date],
					"to_date": [">=", self.posting_date],
				},
				["supplier", "owner_model"],
				as_dict=True,
				order_by="from_date desc, name desc",
			)
		if card and card.supplier:
			return card.supplier, card.owner_model or equipment.owner_model
		return equipment.supplier, equipment.owner_model

	def before_submit(self):
		source = self._source()
		self._refuse_owner_ledger_source()
		self._refuse_automatic_deduction()
		self._refuse_over_allocation(source)

	def _refuse_automatic_deduction(self):
		"""The statement already deducts the wages of the machine's card operators (Salary Slip) and,
		for a managed partner, the expenses on the machine's cost center: such a source is not recorded
		again."""
		if self.source_doctype == "Salary Slip":
			slip = frappe.db.get_value(
				"Salary Slip", self.source_name, ["employee", "start_date", "end_date"], as_dict=True
			)
			operated = frappe.db.exists(
				"Card Monthly Card",
				{
					# any machine: the statement shares the slip over every card of the period
					"operator": slip.employee,
					"docstatus": ["in", [0, 1]],
					"from_date": ["<=", slip.end_date],
					"to_date": [">=", slip.start_date],
				},
			)
			if operated:
				frappe.throw(
					_(
						"The wages of {0} are deducted from the cards automatically; they are not recorded again."
					).format(slip.employee)
				)
		equipment = frappe.db.get_value(
			"Card Equipment", self.equipment, ["cost_center", "supplier", "owner_model"], as_dict=True
		)
		cost_center = equipment.cost_center
		if not cost_center or self._owner_on_date(equipment)[1] != OWNER_MODEL_MANAGED:
			return
		# only the rows the statement deducts on its own: Expense accounts without diesel and payroll
		# (a creditor or tax row that carries the header cost center is not a machine expense)
		from card.owner_statement import deductible_expense_accounts

		accounts = deductible_expense_accounts(self.company)
		if accounts and frappe.db.exists(
			"GL Entry",
			{
				"voucher_type": self.source_doctype,
				"voucher_no": self.source_name,
				"cost_center": cost_center,
				"account": ["in", accounts],
				"is_cancelled": 0,
			},
		):
			frappe.throw(
				_(
					"{0} {1} is booked on the equipment's cost center, which the statement already deducts; it is not recorded again."
				).format(self.source_doctype, self.source_name)
			)

	def _source(self):
		if self.source_doctype not in SOURCE_AMOUNT_FIELDS:
			frappe.throw(_("Invalid source type {0}.").format(self.source_doctype))
		if not frappe.db.exists("DocType", self.source_doctype):
			frappe.throw(_("{0} is not installed on this site.").format(self.source_doctype))
		fields = ["name", "docstatus", SOURCE_AMOUNT_FIELDS[self.source_doctype]]
		if frappe.get_meta(self.source_doctype).has_field("company"):
			fields.append("company")
		source = frappe.db.get_value(self.source_doctype, self.source_name, fields, as_dict=True)
		if not source:
			frappe.throw(_("{0} {1} does not exist.").format(self.source_doctype, self.source_name))
		if not frappe.has_permission(self.source_doctype, "read", self.source_name):
			frappe.throw(_("Not permitted"), frappe.PermissionError)
		if source.docstatus != 1:
			frappe.throw(_("The source document {0} must be submitted.").format(self.source_name))
		if source.get("company") and source.company != self.company:
			frappe.throw(_("The source document belongs to another company."))
		return source

	def _refuse_owner_ledger_source(self):
		# the ledger already charges the owner: the statement counts that line once, as a recharge
		charged = frappe.db.exists(
			"GL Entry",
			{
				"voucher_type": self.source_doctype,
				"voucher_no": self.source_name,
				"party_type": "Supplier",
				"party": self.owner_supplier,
				"is_cancelled": 0,
			},
		)
		if charged:
			frappe.throw(
				_(
					"{0} {1} already charges the owner in the ledger; it is counted from there and is not deducted again."
				).format(self.source_doctype, self.source_name)
			)

	def _refuse_over_allocation(self, source):
		total = flt(source.get(SOURCE_AMOUNT_FIELDS[self.source_doctype]), 2)
		used = flt(
			frappe.db.sql(
				"""select coalesce(sum(amount), 0) from `tabCard Owner Deduction`
				where docstatus = 1 and source_doctype = %s and source_name = %s and name != %s
				for update""",
				(self.source_doctype, self.source_name, self.name),
			)[0][0],
			2,
		)
		if flt(used + flt(self.amount, 2), 2) > total:
			frappe.throw(
				_("{0} {1}: the deductions ({2}) would be more than the document amount {3}.").format(
					self.source_doctype, self.source_name, flt(used + flt(self.amount, 2), 2), total
				)
			)
