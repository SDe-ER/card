# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now_datetime

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


# P0 (Owner 2026-10-20): fill users hold no select on Project / Cost Center / Supplier, so the Desk's
# standard link search refuses them. The fill form searches through fill_link_query instead; the
# master DocPerms stay unchanged. Per doctype: the title field and the fixed filters.
FILL_LINKS = {
	"Project": ("project_name", {}),
	"Cost Center": ("cost_center_name", {"is_group": 0, "disabled": 0}),
	"Supplier": ("supplier_name", {"disabled": 0}),
}


def _user_permitted(doctype):
	"""Names of `doctype` the session user's User Permissions allow on a diesel fill, or None (no limit)
	— the same entries Frappe applies to the fill's link fields when it saves."""
	entries = frappe.permissions.get_user_permissions(frappe.session.user).get(doctype) or []
	allowed = {
		e.get("doc")
		for e in entries
		if not e.get("applicable_for") or e.get("applicable_for") == "Project Diesel Fill"
	}
	return allowed or None


@frappe.whitelist(methods=["GET"])
@frappe.validate_and_sanitize_search_inputs
def fill_link_query(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: str | dict | None = None,
):
	"""Link search of the diesel fill form for Project, Cost Center and Supplier (read only).

	Only for users who may create or edit a fill. Project and Cost Center come from the form's company,
	which must be one the user may see; a user who may not change the diesel supplier gets the Settings
	supplier only. Every user gets names and titles only, under the same rules as the save."""
	from card.report_access import permitted_companies

	if doctype not in FILL_LINKS:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not (
		frappe.has_permission("Project Diesel Fill", "create")
		or frappe.has_permission("Project Diesel Fill", "write")
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	title, fixed = FILL_LINKS[doctype]
	conditions = dict(fixed)
	if doctype == "Supplier":
		if not can_change_diesel_supplier():
			conditions["name"] = setting("diesel_supplier")
	else:
		filters = frappe.parse_json(filters) if filters else {}
		company = filters.get("company") if isinstance(filters, dict) else None
		if not company or company not in permitted_companies("Project Diesel Fill"):
			return []
		conditions["company"] = company
	# one rule for every user, the same the save applies: authorised above, filtered by company and
	# the user's User Permissions for a diesel fill, and limited to name + title. The read itself does
	# not need the master permission (fill users have none, and some roles hold select only).
	allowed = _user_permitted(doctype)
	if allowed is not None:
		if "name" in conditions:
			allowed &= {conditions["name"]}
		if not allowed:
			return []
		conditions["name"] = ["in", sorted(allowed)]
	like = f"%{txt or ''}%"
	return frappe.get_all(
		doctype,
		filters=conditions,
		or_filters={"name": ["like", like], title: ["like", like]},
		fields=["name", title],
		order_by="name",
		limit_start=start,
		limit=page_len,
		as_list=True,
	)


# FR-002 (Owner 2026-10-19): the price per litre comes from the company's row in Card Settings.
COMPANY_PRICE = "Company Price"
EXCEPTION = "Exception"
NEEDS_REVIEW = "Needs Review"


# Phase 1 (Owner 2026-10-26): session evidence and the operations review
# (the review status reuses NEEDS_REVIEW, the same "Needs Review" value as the price source)
DRAFT = "Draft"
OPERATIONS_APPROVED = "Operations Approved"
REJECTED = "Rejected"
REVIEW_ROLES = ("Card Manager", "System Manager")
REVIEWED_FIELDS = (
	"litres",
	"company",
	"project",
	"date",
	"supplier",
	"card_equipment",
	"cost_center",
	"opening_reading",
	"closing_reading",
	"opening_photo",
	"closing_photo",
	"opening_totalizer",
	"closing_totalizer",
)
NOT_CHECKABLE = "Not Checkable"
CONSISTENT = "Consistent"
INCONSISTENT = "Inconsistent"
# Measured on PIUSI K700M photos: with all totalizer drums readable, closing - reset differs from the
# session counter by 0 or 1 litre (QA-Evidence whatsapp-diesel-analysis TOLERANCE-EVIDENCE, 26 pairs)
TOTALIZER_READ_TOLERANCE = 1
# Frappe names an unsaved form "new-<doctype scrubbed with dashes>-<hash>"
NEW_FORM_PREFIX = "new-project-diesel-fill-"
# FR-086: set by card.diesel_import only, so the source of an imported fill cannot be forged
# (FR-086b: with the supplier invoice that proves a historical price)
SOURCE_FIELDS = (
	"source_key",
	"source_messages",
	"source_caption",
	"supplier_invoice_no",
	"invoiced_litres",
	"invoice_unit_price",
	"delivery_charge_litres",
	"invoice_evidence",
)


def _equipment_rows(doc):
	return [(row.card_equipment, row.reported_name, row.match_status) for row in doc.get("equipment_filled")]


def totalizer_bounds(value):
	"""(low, high) litres a totalizer reading can stand for, or None. Unreadable last drums are written
	as "?" (e.g. "055793?"): each one widens the range by its 0-9 digit, nothing else is assumed."""
	text = (value or "").strip()
	known = text.rstrip("?")
	unknown = len(text) - len(known)
	if not known.isdigit():
		return None
	scale = 10**unknown
	return int(known) * scale, int(known) * scale + scale - 1


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
		self._guard_source()
		self._check_link_values()
		self._enforce_diesel_supplier()
		self._apply_price()
		self._apply_readings()
		# Amount is litres x unit price; the accounting posting (Purchase Invoice on
		# the project) is added in a later stage, gated by owner approval.
		self.amount = flt(flt(self.litres) * flt(self.unit_price), 2)
		self._check_equipment_mode()
		self._check_photos()
		warnings = self._check_totalizer() + self._check_overlaps()
		self.evidence_warnings = "\n".join(warnings) or None
		self._guard_review(warnings)

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
		# Owner 2026-10-26 (Phase 1): the operations review is separate from the accounting submit
		if self.review_status != OPERATIONS_APPROVED:
			frappe.throw(_("The diesel fill needs operations approval before submit."))

	def _guard_source(self):
		"""The source fields (read only on the form) come from the session import only, never from a
		form or REST save, so a fill cannot claim a source key or source photos it was not imported from."""
		if self.flags.diesel_import:
			return
		before = None if self.is_new() else self.get_doc_before_save()
		if self.is_new() and self.amended_from:
			# an amendment keeps its original's source (Desk copies it on amend; FR-086b): the imported
			# session stays out of the posting and keeps its invoice price. The unique source key stays
			# with the original, so a re-import still finds the session.
			self.source_key = None
			if self._inherits_source():
				before = frappe.db.get_value(self.doctype, self.amended_from, SOURCE_FIELDS, as_dict=True)
				before.source_key = None
		for fieldname in SOURCE_FIELDS:
			if (self.get(fieldname) or None) != ((before.get(fieldname) if before else None) or None):
				frappe.throw(_("The source of a diesel fill is set by the session import only."))

	def _apply_readings(self):
		"""Meter readings, when given, are the source of the litres (the session counter is reset to
		zero at the start, so litres = closing - opening). Frappe stores an empty Float as 0, so a
		closing reading counts only when it is above zero."""
		if not self._has_closing_reading():
			return
		opening = flt(self.opening_reading)
		closing = flt(self.closing_reading)
		if closing < opening:
			frappe.throw(_("The closing reading cannot be lower than the opening reading."))
		litres = flt(closing - opening, self.precision("litres"))
		if self.litres and flt(self.litres, self.precision("litres")) != litres:
			frappe.msgprint(
				_("Litres set to {0} from the meter readings.").format(litres), indicator="orange", alert=True
			)
		self.litres = litres

	def _has_closing_reading(self):
		return flt(self.closing_reading) > 0

	def _check_equipment_mode(self):
		"""One measured equipment (card_equipment) or a list of filled equipment, never both: the list
		carries no litres, so the allocation stays recorded (one equipment) or estimated (hours split)."""
		if self.card_equipment and self.equipment_filled:
			frappe.throw(
				_("Choose either one equipment for the whole fill or the list of filled equipment, not both.")
			)
		listed = [row.card_equipment for row in self.equipment_filled if row.card_equipment]
		companies = (
			dict(
				frappe.get_all(
					"Card Equipment",
					filters={"name": ["in", listed]},
					fields=["name", "company"],
					as_list=True,
				)
			)
			if listed
			else {}
		)
		for row in self.equipment_filled:
			if row.match_status == "Matched" and not row.card_equipment:
				frappe.throw(_("Row {0}: a matched row needs its equipment.").format(row.idx))
			if row.card_equipment:
				company = companies.get(row.card_equipment)
				if company and self.company and company != self.company:
					frappe.throw(
						_("Row {0}: company {1} does not match the equipment's company {2}.").format(
							row.idx, self.company, company
						)
					)

	def _check_photos(self):
		"""Meter photos are private files uploaded to this fill, and the same photo (same file or same
		bytes) never proves two live fills. Checked when a photo or the company changes."""
		if not (
			self.is_new()
			or self.has_value_changed("opening_photo")
			or self.has_value_changed("closing_photo")
			or self.has_value_changed("company")
		):
			return
		urls = [u for u in (self.opening_photo, self.closing_photo) if u]
		if not urls:
			return
		temporary = self.get("__temporary_name") if self.is_new() else None
		if temporary and not cstr(temporary).startswith(NEW_FORM_PREFIX):
			# not an unsaved-form name (e.g. another fill's name): never let Frappe relink files from it
			self.__dict__.pop("__temporary_name", None)
			temporary = None
		hashes = {}
		for url in urls:
			filters = {"file_url": url, "is_private": 1, "attached_to_doctype": self.doctype}
			if temporary:
				# uploaded on the unsaved form: attached to its temporary name until insert, and only the
				# uploader's own file (the temporary name comes from the client)
				filters.update({"attached_to_name": temporary, "owner": frappe.session.user})
			else:
				filters["attached_to_name"] = self.name
			row = frappe.db.get_value("File", filters, ["name", "content_hash"], as_dict=True)
			if not row and self._amends_own_cancelled_fill():
				# an amendment keeps the cancelled original's evidence; Frappe copies its attachments after insert
				filters.pop("owner", None)
				filters["attached_to_name"] = self.amended_from
				row = frappe.db.get_value("File", filters, ["name", "content_hash"], as_dict=True)
			if not url.startswith("/private/files/") or not row:
				# Frappe shares one URL and one public state between files with the same bytes
				frappe.throw(_("Meter photos must be private files uploaded to this diesel fill."))
			hashes[url] = row.content_hash
		if len(urls) == 2 and (
			urls[0] == urls[1] or (hashes[urls[0]] and hashes[urls[0]] == hashes[urls[1]])
		):
			frappe.throw(_("The opening and closing meter photos are the same file."))
		same = set(urls)
		known = [h for h in hashes.values() if h]
		if known:
			same.update(frappe.get_all("File", filters={"content_hash": ["in", known]}, pluck="file_url"))
		fill = frappe.qb.DocType("Project Diesel Fill")
		other = (
			frappe.qb.from_(fill)
			.select(fill.name, fill.company)
			.where(fill.docstatus < 2)
			.where(fill.name != (self.name or ""))
			# a rejected entry does not hold its photo: the corrected fill may use it
			.where(fill.review_status.isnull() | (fill.review_status != REJECTED))
			.where(fill.opening_photo.isin(list(same)) | fill.closing_photo.isin(list(same)))
			.limit(1)
			.run(as_dict=True)
		)
		if other and other[0].company == self.company:
			frappe.throw(_("This meter photo is already used by diesel fill {0}.").format(other[0].name))
		if other:
			# never name a record of another company
			frappe.throw(_("This meter photo is already used by another diesel fill."))

	def _inherits_source(self):
		"""SR-1 (security review 2026-10-27): a new fill takes the source of its amended_from only as a
		real amendment: a cancelled fill of the same company the user may read and amend, and the only
		live amendment of it. Frappe checks only that amended_from is cancelled, so a REST insert could
		otherwise copy an imported fill's source to any number of new fills and keep them out of the
		posting."""
		return bool(
			self._amends_own_cancelled_fill()
			and frappe.has_permission(self.doctype, "amend", doc=self.amended_from)
			# called for a new fill only, so every row found is another amendment (Frappe gives a second
			# amendment of the same fill the same name, so the name cannot tell them apart)
			and not frappe.db.exists(self.doctype, {"amended_from": self.amended_from, "docstatus": ["<", 2]})
		)

	def _amends_own_cancelled_fill(self):
		"""A new amendment of a cancelled fill of the same company that the user may read."""
		if not (self.is_new() and self.amended_from):
			return False
		original = frappe.db.get_value(
			self.doctype, self.amended_from, ["docstatus", "company"], as_dict=True
		)
		return bool(
			original
			and original.docstatus == 2
			and original.company == self.company
			and frappe.has_permission(self.doctype, "read", doc=self.amended_from)
		)

	def _check_totalizer(self):
		"""Advisory check of the session against the meter's cumulative totalizer (TOTAL drums)."""
		self.totalizer_check = NOT_CHECKABLE
		if not self._has_closing_reading():
			return []
		opening = totalizer_bounds(self.opening_totalizer)
		closing = totalizer_bounds(self.closing_totalizer)
		if not (opening and closing):
			return []
		session = flt(self.closing_reading) - flt(self.opening_reading)
		low, high = closing[0] - opening[1], closing[1] - opening[0]
		if low - TOTALIZER_READ_TOLERANCE <= session <= high + TOTALIZER_READ_TOLERANCE:
			self.totalizer_check = CONSISTENT
			return []
		self.totalizer_check = INCONSISTENT
		return [
			_("Totalizer moved {0} to {1} litres, the session shows {2}.").format(
				max(low, 0), max(high, 0), flt(session)
			)
		]

	def _check_overlaps(self):
		"""Warnings only: a second session on the same project and day is allowed (never a duplicate by
		itself), and photo times out of order or on another day need a look."""
		warnings = []
		if self.project and self.date:
			other = frappe.get_all(
				"Project Diesel Fill",
				filters={
					"project": self.project,
					"date": self.date,
					"docstatus": ["<", 2],
					"name": ["!=", self.name or ""],
				},
				pluck="name",
				limit=1,
			)
			if other:
				warnings.append(
					_("Another diesel fill exists for this project on this date: {0}.").format(other[0])
				)
		if self.opening_photo_time and self.closing_photo_time:
			if get_datetime(self.closing_photo_time) < get_datetime(self.opening_photo_time):
				warnings.append(_("The closing photo time is before the opening photo time."))
		if self.closing_photo_time and self.date and getdate(self.closing_photo_time) != getdate(self.date):
			warnings.append(_("The closing photo date differs from the fill date."))
		return warnings

	def _guard_review(self, warnings):
		"""The operations review is decided on the server: only the review roles approve or reject, an
		approval needs the closing photo and reading, the reviewer is the session user, and a material
		change after approval sends the fill back to review."""
		before = None if self.is_new() else self.get_doc_before_save()
		old = (before.review_status if before else None) or DRAFT
		self.review_status = self.review_status or DRAFT
		if before is None and self.amended_from:
			# like a price exception, the cancelled fill's review is not a review of its amendment
			self.review_status = DRAFT
		reset = (
			before is not None
			and old == OPERATIONS_APPROVED
			and self.review_status == OPERATIONS_APPROVED
			and (
				any(self.has_value_changed(f) for f in REVIEWED_FIELDS)
				or _equipment_rows(before) != _equipment_rows(self)
			)
		)
		if reset:
			# any user's material edit voids the approval; that needs no review role
			self.review_status = NEEDS_REVIEW
			frappe.msgprint(
				_("The fill changed after operations approval and needs review again."), indicator="orange"
			)
		if self.review_status != old or (before is None and self.review_status != DRAFT):
			if (
				not reset
				and {self.review_status, old} & {OPERATIONS_APPROVED, REJECTED}
				and not (set(REVIEW_ROLES) & set(frappe.get_roles()))
			):
				frappe.throw(
					_("Only {0} may approve or reject the operations review.").format(
						", ".join(REVIEW_ROLES)
					),
					frappe.PermissionError,
				)
			if self.review_status == OPERATIONS_APPROVED and not (
				self.closing_photo and self._has_closing_reading()
			):
				frappe.throw(_("Operations approval needs the closing meter photo and reading."))
			if self.review_status in (OPERATIONS_APPROVED, REJECTED):
				self.ops_reviewed_by, self.ops_reviewed_on = frappe.session.user, now_datetime()
			else:
				self.ops_reviewed_by = self.ops_reviewed_on = None
		else:
			# never taken from the client
			self.ops_reviewed_by = before.ops_reviewed_by if before else None
			self.ops_reviewed_on = before.ops_reviewed_on if before else None
		if self.review_status == DRAFT and (warnings or self.totalizer_check == INCONSISTENT):
			self.review_status = NEEDS_REVIEW

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
			invoice_price = self._invoice_price()
			if invoice_price and self.flags.use_company_price:
				frappe.throw(
					_("This fill keeps the price of its supplier invoice {0}.").format(
						self.supplier_invoice_no
					)
				)
			if invoice_price:
				# FR-086b: an imported historical session returns to its invoice price, waiting again
				self.unit_price = invoice_price
				self.price_source = NEEDS_REVIEW
				self._note_price_change(before, self.flags.price_change_reason)
				return
			self._take_company_price(company_price)
			self._note_price_change(before, self.flags.price_change_reason)
			return
		if before is None:
			if self.amended_from and price != company_price:
				self._needs_review(company_price)  # an amended copy keeps the original price
				return
			if self.flags.historical_price:
				self._keep_invoice_price(price)
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
		if price > 0 and price == self._invoice_price():
			self.price_source = NEEDS_REVIEW
			frappe.msgprint(
				_("This draft keeps the price {0} of supplier invoice {1}; {2} approves it.").format(
					price, self.supplier_invoice_no, setting("diesel_price_exception_role")
				),
				indicator="orange",
			)
			return
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

	def _invoice_price(self):
		"""The price per litre of the imported session's supplier invoice (FR-086b), or 0."""
		if not (self.supplier_invoice_no or "").strip():
			return 0
		return flt(self.invoice_unit_price, self.precision("unit_price") or 2)

	def _keep_invoice_price(self, price):
		"""FR-086b (Owner 2026-10-27): an imported historical session keeps the price of its supplier
		invoice, never the current company price. It waits as Needs Review until the price exception
		role approves it (no automatic price approval)."""
		if not self.flags.diesel_import:
			frappe.throw(_("A historical diesel price is set by the session import only."))
		if not (self.supplier_invoice_no or "").strip():
			frappe.throw(_("A historical diesel price needs its supplier invoice number."))
		if price <= 0 or price != self._invoice_price():
			frappe.throw(_("A historical diesel price must be the price of its supplier invoice."))
		self.price_source = NEEDS_REVIEW

	def _needs_review(self, company_price):
		self.price_source = NEEDS_REVIEW
		frappe.msgprint(
			_(
				"This draft has price {0}; the company price is {1}. Use the company price, or ask {2} to approve an exception."
			).format(flt(self.unit_price), company_price, setting("diesel_price_exception_role")),
			indicator="orange",
		)

	def _check_link_values(self):
		"""P0 (Owner 2026-10-20): the project and the cost center belong to the fill's company, the cost
		center can carry a posting line and a newly chosen supplier is enabled. Frappe's save only checks
		that a linked record exists, so this also stops other companies' values sent through the API."""
		if (
			self.supplier
			and self.has_value_changed("supplier")
			and frappe.db.get_value("Supplier", self.supplier, "disabled")
		):
			frappe.throw(_("Supplier {0} is disabled.").format(self.supplier))
		if not self.company:
			return  # the mandatory check reports the missing company
		if self.project and frappe.db.get_value("Project", self.project, "company") != self.company:
			frappe.throw(_("Project {0} does not belong to company {1}.").format(self.project, self.company))
		if self.cost_center:
			row = frappe.db.get_value(
				"Cost Center", self.cost_center, ["company", "is_group", "disabled"], as_dict=True
			)
			if not row or row.company != self.company or row.is_group or row.disabled:
				frappe.throw(
					_("Cost center {0} must be an enabled, non-group cost center of company {1}.").format(
						self.cost_center, self.company
					)
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
