# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime

from card.company import single_company, validate_equipment_company
from card.settings import setting


def can_change_diesel_supplier():
	"""The F.1 rules of ProjectDieselFill._enforce_diesel_supplier, for the form: no Settings
	supplier → free; ثابت → nobody; متغير → Administrator or the editor role."""
	if not setting("diesel_supplier"):
		return True
	if (setting("diesel_supplier_policy") or "متغير") == "ثابت":
		return False
	role = setting("diesel_supplier_editor_role") or "Card Manager"
	return frappe.session.user == "Administrator" or role in frappe.get_roles()


@frappe.whitelist(methods=["GET"])
def get_supplier_editable():
	"""Whether the fill form lets the current user change the diesel supplier (read only).
	Fill users cannot read Card Settings, so only this yes/no leaves the server."""
	frappe.has_permission("Project Diesel Fill", "read", throw=True)
	return can_change_diesel_supplier()


# FR-002 (Owner 2026-10-19): the price per litre comes from the company's row in Card Settings.
COMPANY_PRICE = "Company Price"
EXCEPTION = "Exception"
NEEDS_REVIEW = "Needs Review"


def diesel_price(company):
	"""The diesel price per litre of `company` from Card Settings, or 0."""
	if not company:
		return 0
	from card.accounting_settings import get_company_settings

	row = get_company_settings(company, throw=False)
	return flt(row.get("diesel_unit_price")) if row else 0


def _holds(fieldname):
	"""The session user holds the role named in Card Settings `fieldname`; an empty role = nobody."""
	role = setting(fieldname)
	return bool(role) and role in frappe.get_roles()


def can_except_price():
	return _holds("diesel_price_exception_role")


def can_zero_price():
	return _holds("diesel_zero_price_role")


@frappe.whitelist(methods=["GET"])
def get_diesel_price_context(company: str | None = None):
	"""What the fill form needs before saving (read only): the company price and whether the
	current user may grant a price exception. Fill users cannot read Card Settings."""
	from card.report_access import permitted_companies

	frappe.has_permission("Project Diesel Fill", "read", throw=True)
	if not company or company not in permitted_companies("Project Diesel Fill"):
		return {"price": 0, "can_except": False, "can_zero": False, "exception_role": None}
	return {
		"price": diesel_price(company),
		"can_except": can_except_price(),
		"can_zero": can_zero_price(),
		"exception_role": setting("diesel_price_exception_role"),
	}


@frappe.whitelist(methods=["POST"])
def use_company_price(name: str, reason: str | None = None):
	"""Explicit choice on a draft without an exception (the form offers it on Needs Review drafts):
	replace its price with the current company price.
	Owner 2026-10-20: changing a saved draft's price needs the exception role, a reason and an audit."""
	doc = frappe.get_doc("Project Diesel Fill", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft diesel fill can change its price."))
	if not can_except_price():
		frappe.throw(
			_("Only users with role {0} may change the price of a saved diesel fill.").format(
				setting("diesel_price_exception_role")
			),
			frappe.PermissionError,
		)
	if cint(doc.price_exception):
		frappe.throw(
			_("This fill has a price exception; only {0} can change it.").format(
				setting("diesel_price_exception_role")
			)
		)
	if not (reason or "").strip():
		frappe.throw(_("A reason is required to change the price of a saved diesel fill."))
	doc.flags.use_company_price = True
	doc.flags.price_change_reason = reason.strip()
	doc.save()
	return {"unit_price": doc.unit_price, "price_source": doc.price_source}


@frappe.whitelist(methods=["POST"])
def remove_price_exception(name: str, reason: str | None = None):
	"""End the price exception of a saved draft: it returns to the current company price.
	Owner 2026-10-20: needs the exception role and a written reason; audited like every price change."""
	doc = frappe.get_doc("Project Diesel Fill", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft diesel fill can change its price."))
	if not cint(doc.price_exception):
		frappe.throw(_("This fill has no price exception."))
	if not can_except_price():
		frappe.throw(
			_("Only users with role {0} may change the price of a saved diesel fill.").format(
				setting("diesel_price_exception_role")
			),
			frappe.PermissionError,
		)
	if not (reason or "").strip():
		frappe.throw(_("A reason is required to change the price of a saved diesel fill."))
	doc.price_exception = 0
	doc.flags.remove_price_exception = True
	doc.flags.price_change_reason = reason.strip()
	doc.save()
	return {"unit_price": doc.unit_price, "price_source": doc.price_source}


class ProjectDieselFill(Document):
	def validate(self):
		if not self.company:
			self.company = single_company()  # F.8: default to THE company
		validate_equipment_company(self, "card_equipment")  # F.8 consistency
		self._enforce_diesel_supplier()
		self._apply_price()
		# Amount is litres x unit price; the accounting posting (Purchase Invoice on
		# the project) is added in a later stage, gated by owner approval.
		self.amount = flt(flt(self.litres) * flt(self.unit_price), 2)

	def on_update(self):
		audit = self.flags.pop("card_price_audit", None)
		if not audit:
			return
		# server-side audit of a saved draft's price change (Owner 2026-10-20); the Version row keeps
		# the field values, this comment keeps the reason with them
		self.add_comment(
			"Info",
			_("Diesel price changed from {0} to {1}. Reason: {2}").format(
				audit["from"], audit["to"], audit["reason"]
			),
		)
		frappe.logger("card.diesel_price_change").warning(
			json.dumps(
				{"user": frappe.session.user, "fill": self.name, "on": str(now_datetime()), **audit},
				ensure_ascii=False,
				default=str,
			)
		)

	def before_submit(self):
		if self.price_source == NEEDS_REVIEW:
			frappe.throw(
				_(
					"The diesel price of this fill needs a decision before submit: use the company price, or ask {0} to approve an exception."
				).format(setting("diesel_price_exception_role"))
			)

	def _apply_price(self):
		"""FR-002 price lock (Owner Q1–Q4). Submitted and cancelled fills never reach validate."""
		before = None if self.is_new() else self.get_doc_before_save()
		precision = self.precision("unit_price") or 2
		company_price = flt(diesel_price(self.company), precision)
		price = flt(self.unit_price, precision)
		self.company_price = company_price
		if before is None and self.amended_from and cint(self.price_exception):
			self._drop_copied_exception()

		if self._exception_changed(before):
			self._check_exception(price, before)
		elif cint(self.price_exception):
			# unchanged exception (e.g. litres edited by a Card User): keep its price, stamps and
			# the company price it replaced (the audited original value)
			self.exception_by, self.exception_on = before.exception_by, before.exception_on
			self.company_price = before.company_price
		if cint(self.price_exception):
			self.price_source = EXCEPTION
			self._note_price_change(before, self.exception_reason)
			return
		self.exception_reason = self.exception_by = self.exception_on = None

		if before is not None and cint(before.price_exception) and not self.flags.remove_price_exception:
			# a plain save (form or REST) cannot end an exception: it changes the price, so it needs a reason
			frappe.throw(_("To end a price exception, use «Remove price exception» and give a reason."))
		if self.flags.use_company_price or self.flags.remove_price_exception:
			self._take_company_price(company_price)
			self._note_price_change(before, self.flags.price_change_reason)
			return
		if before is None:
			if self.amended_from and price != company_price:
				self._needs_review(company_price)  # an amended copy keeps the original price
				return
			if price and price != company_price:
				self._refuse_typed_price(company_price)
			self._take_company_price(company_price)
			return
		if price != flt(before.unit_price, precision):
			self._refuse_typed_price(company_price)
		if before.price_source == COMPANY_PRICE:
			# Owner 2026-10-20: a saved draft keeps the price it was created with; a later company price
			# change only warns (new fills take the new price)
			if self.company != before.company:
				if price != company_price:
					self._needs_review(company_price)  # its price belonged to the old company
				else:
					self.price_source = COMPANY_PRICE
				return
			self.price_source = COMPANY_PRICE
			self.company_price = before.company_price
			if price != company_price:
				frappe.msgprint(
					_("This draft keeps its price {0}; the current company price is {1}.").format(
						price, company_price
					),
					indicator="orange",
					alert=True,
				)
			return
		# a draft saved before the price lock, or still waiting for a decision: never repriced silently
		if price > 0 and price == company_price:
			self.price_source = COMPANY_PRICE
		else:
			self._needs_review(company_price)

	def _drop_copied_exception(self):
		"""Amend copies every field, the exception included: an exception approved on the cancelled
		fill is not an approval of its amendment, so the copy goes to Needs Review instead."""
		original = frappe.db.get_value(
			"Project Diesel Fill", self.amended_from, ["price_exception", "exception_reason"], as_dict=True
		)
		if (
			original
			and cint(original.price_exception)
			and (original.exception_reason or "").strip() == (self.exception_reason or "").strip()
		):
			self.price_exception = 0

	def _exception_changed(self, before):
		if before is None:
			return bool(cint(self.price_exception))
		precision = self.precision("unit_price") or 2
		return bool(
			cint(self.price_exception) != cint(before.price_exception)
			or (self.exception_reason or "").strip() != (before.exception_reason or "").strip()
			or (
				cint(self.price_exception)
				and (
					flt(self.unit_price, precision) != flt(before.unit_price, precision)
					or self.company != before.company  # an approved price belongs to its company
				)
			)
		)

	def _check_exception(self, price, before=None):
		"""A price exception is set, changed or removed: role, price and reason are checked here."""
		if not cint(self.price_exception):
			if not can_except_price():
				self._refuse_exception_change()
			return
		if price < 0:
			frappe.throw(_("The diesel price cannot be negative."))
		if price == 0 and not can_zero_price():
			frappe.throw(_("A zero diesel price is not allowed."), frappe.PermissionError)
		if price > 0 and not can_except_price():
			self._refuse_exception_change()
		if not (self.exception_reason or "").strip():
			frappe.throw(_("A reason is required for a diesel price exception."))
		precision = self.precision("unit_price") or 2
		if (
			before is not None
			and cint(before.price_exception)
			and price != flt(before.unit_price, precision)
			and (self.exception_reason or "").strip() == (before.exception_reason or "").strip()
		):
			# a new price on an existing exception needs its own reason
			frappe.throw(_("Write the reason for the new diesel price."))
		self.exception_by = frappe.session.user
		self.exception_on = now_datetime()
		frappe.logger("card.diesel_price_exception").warning(
			json.dumps(
				{
					"user": frappe.session.user,
					"fill": self.name,
					"company": self.company,
					"company_price": self.company_price,
					"price": price,
				},
				ensure_ascii=False,
				default=str,
			)
		)

	def _note_price_change(self, before, reason):
		"""Queue the audit of a saved draft's price change for on_update (new fills are not audited
		here: they take the company price, or an exception stamped with its own reason)."""
		if before is None:
			return
		precision = self.precision("unit_price") or 2
		old, new = flt(before.unit_price, precision), flt(self.unit_price, precision)
		if old == new and cint(before.price_exception) == cint(self.price_exception):
			return
		self.flags.card_price_audit = {"from": old, "to": new, "reason": (reason or "").strip()}

	def _refuse_exception_change(self):
		frappe.throw(
			_("Only users with role {0} may set or change a diesel price exception.").format(
				setting("diesel_price_exception_role")
			),
			frappe.PermissionError,
		)

	def _refuse_typed_price(self, company_price):
		frappe.throw(
			_(
				"The diesel price comes from the company price in Card Settings ({0}); use a price exception to change it."
			).format(company_price)
		)

	def _take_company_price(self, company_price):
		if company_price <= 0:
			frappe.throw(
				_(
					"No approved diesel price for company {0}. Accounts must set it in Card Settings, company settings."
				).format(self.company)
			)
		self.unit_price = company_price
		self.price_source = COMPANY_PRICE

	def _needs_review(self, company_price):
		self.price_source = NEEDS_REVIEW
		frappe.msgprint(
			_(
				"This draft has price {0}; the company price is {1}. Use the company price, or ask {2} to approve an exception."
			).format(flt(self.unit_price), company_price, setting("diesel_price_exception_role")),
			indicator="orange",
		)

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
				_("The diesel supplier is fixed in Settings ({0}) and cannot be changed.").format(
					default_supplier
				)
			)
		role = setting("diesel_supplier_editor_role") or "Card Manager"
		if frappe.session.user != "Administrator" and role not in frappe.get_roles():
			frappe.throw(_("Only users with role {0} may change the diesel supplier.").format(role))
