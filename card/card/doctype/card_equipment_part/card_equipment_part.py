# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, today

from card.fitment import (
	APPLIES_TO_MACHINE,
	APPLIES_TO_MODEL,
	CONFIRMED,
	DECISIONS,
	NOT_COMPATIBLE,
	PENDING,
	SECOND_REVIEW,
	is_approver,
)

# Written by the server only. A value sent by the client (form, REST, import) is
# replaced by the stored one before the review rules run.
SERVER_FIELDS = (
	"compatibility_status",
	"review_stage",
	"proposed_by",
	"proposed_on",
	"first_review_by",
	"first_review_on",
	"first_review_decision",
	"first_review_reason",
	"confirmed_by",
	"confirmed_on",
	"retired_by",
	"retired_on",
	"source",
	"source_request",
	"company",
)
# What the row is about. It never changes after insert, so a decision cannot move
# to another item, model or machine. A machine row's model follows the machine.
KEY_FIELDS = ("item_code", "applies_to", "card_equipment")
MODEL_ROW_KEY_FIELDS = (*KEY_FIELDS, "equipment_model")
EVIDENCE_FIELDS = ("evidence_source", "evidence_reference", "evidence_file")


class CardEquipmentPart(Document):
	"""Fitment row (FR-077): an Item fits an equipment model or one machine. States of
	DESIGN v4.1; only an active Confirmed row shows a part as fitting (O6). The proposer
	never makes a final decision: their decision is a first review only and the row
	waits for a second, independent reviewer (Q5). Administrator is not exempt."""

	def validate(self):
		if self.applies_to != "Equipment":
			self.warranty_until = None  # a warranty belongs to a part fitted to one machine
		# the alert date is CARD's: reset when the warranty changes, never set by a user
		before = self.get_doc_before_save()
		if self.is_new() or self.has_value_changed("warranty_until"):
			self.warranty_alerted_on = None
		elif before:
			self.warranty_alerted_on = before.warranty_alerted_on
		before = None if self.is_new() else self.get_doc_before_save()
		requested = self.compatibility_status
		self._keep_server_fields(before)
		self._validate_target(before)
		self._validate_item()
		self._validate_evidence_file()
		self._apply_review(before, requested)
		self._apply_retire(before)

	def on_trash(self):
		frappe.throw(_("Fitment rows are retired, never deleted."))

	# ---------- server-owned values ----------

	def _keep_server_fields(self, before):
		if before:
			for field in SERVER_FIELDS:
				self.set(field, before.get(field))
			return
		for field in SERVER_FIELDS:
			self.set(field, None)
		self.compatibility_status = PENDING
		self.proposed_by = frappe.session.user
		self.proposed_on = now_datetime()
		self.source = "Manual" if is_approver() else "Supervisor proposal"

	# ---------- what the row is about ----------

	def _validate_target(self, before):
		keys = MODEL_ROW_KEY_FIELDS if self.applies_to == APPLIES_TO_MODEL else KEY_FIELDS
		if before and any((before.get(f) or None) != (self.get(f) or None) for f in keys):
			frappe.throw(_("Item, scope, model and equipment of a fitment row cannot change."))
		if self.applies_to == APPLIES_TO_MACHINE:
			if not self.card_equipment:
				frappe.throw(_("Select the equipment."))
			machine = frappe.db.get_value(
				"Card Equipment", self.card_equipment, ["company", "equipment_model"], as_dict=True
			)
			if not machine:
				frappe.throw(_("Equipment {0} does not exist.").format(self.card_equipment))
			self.company = machine.company
			self.equipment_model = machine.equipment_model
			self.compat_key = f"E|{self.card_equipment}|{self.item_code}"
		elif self.applies_to == APPLIES_TO_MODEL:
			if not self.equipment_model:
				frappe.throw(_("Select the equipment model."))
			if not before and frappe.db.get_value("Card Equipment Model", self.equipment_model, "disabled"):
				frappe.throw(_("Equipment model {0} is disabled.").format(self.equipment_model))
			self.card_equipment = None
			self.company = None
			self.compat_key = f"M|{self.equipment_model}|{self.item_code}"
		else:
			frappe.throw(_("Select what the row applies to."))
		if not before:
			other = frappe.db.get_value(
				"Card Equipment Part", {"compat_key": self.compat_key}, ["name", "is_active"], as_dict=True
			)
			if other:
				hint = "" if other.is_active else " " + _("It is retired: make it active again instead.")
				frappe.throw(
					_("Fitment row {0} already exists for this item.").format(other.name) + hint,
					frappe.DuplicateEntryError,
				)

	def _validate_item(self):
		if not self.has_value_changed("item_code") and not self.is_new():
			return
		item = frappe.db.get_value(
			"Item", self.item_code, ["disabled", "end_of_life", "has_variants"], as_dict=True
		)
		if not item:
			frappe.throw(_("Item {0} does not exist.").format(self.item_code))
		if item.disabled:
			frappe.throw(_("Item {0} is disabled.").format(self.item_code))
		if item.end_of_life and getdate(item.end_of_life) < getdate(today()):
			frappe.throw(_("Item {0} has reached its end of life.").format(self.item_code))
		if item.has_variants:
			frappe.throw(_("Item {0} is a template; select one of its variants.").format(self.item_code))

	def _validate_evidence_file(self):
		# checked when it is set, so a file removed later never blocks the row; a file
		# that belongs to another document is not evidence for this one
		if not self.evidence_file or not (self.is_new() or self.has_value_changed("evidence_file")):
			return
		files = frappe.get_all(
			"File",
			filters={"file_url": self.evidence_file, "is_private": 1},
			fields=["attached_to_doctype", "attached_to_name"],
		)
		if not any(
			(f.attached_to_doctype, f.attached_to_name) in ((None, None), (self.doctype, self.name))
			for f in files
		):
			frappe.throw(_("The evidence file must be a private file uploaded to this row."))

	# ---------- review (Q5) ----------

	def _apply_review(self, before, requested):
		user = frappe.session.user
		current = self.compatibility_status
		changed_evidence = before and any(
			(before.get(f) or None) != (self.get(f) or None) for f in EVIDENCE_FIELDS
		)

		if not is_approver(user):
			# Card Supervisor: proposes and documents own rows while they are pending
			if requested != current:
				frappe.throw(_("Only a Card Manager decides the compatibility status."))
			if before and (before.proposed_by != user or current != PENDING):
				frappe.throw(_("You can change only your own pending fitment rows."))
			return

		if requested == current:
			if changed_evidence and (current in DECISIONS or self.review_stage == SECOND_REVIEW):
				# a decision or a first review stands only on the evidence it was made on:
				# new evidence, by anyone, needs a new review
				self.compatibility_status = PENDING
				self.review_stage = None
				self._record_decision(None)
			elif (
				before
				and self.review_stage == SECOND_REVIEW
				and user != self.proposed_by
				and self._new_reason(before)
			):
				# the second reviewer sends a first review back without a decision (the
				# Version log keeps who did it)
				self.review_stage = None
			return

		if requested not in (PENDING, *DECISIONS):
			frappe.throw(_("Select a valid compatibility status."))
		if requested in DECISIONS:
			self._check_evidence()
			self._check_conflict(requested)
		if user == self.proposed_by:
			self._first_review(user, requested, before)
			return
		self.compatibility_status = requested
		self.review_stage = None
		self._record_decision(user if requested in DECISIONS else None)

	def _first_review(self, user, requested, before):
		"""The proposer's own decision: stored, never applied (no final self-approval)."""
		self.compatibility_status = PENDING
		if requested == PENDING:
			# the proposer sets their decided row back to pending: the safe direction
			self.review_stage = None
			self._record_decision(None)
			return
		if not self._new_reason(before):
			frappe.throw(_("Enter the reason for your decision on your own proposal."))
		if not self.evidence_file:
			frappe.throw(_("Attach the evidence file for a decision on your own proposal."))
		self.review_stage = SECOND_REVIEW
		self._record_decision(None)
		self.first_review_by = user
		self.first_review_on = now_datetime()
		self.first_review_decision = requested
		self.first_review_reason = self.decision_reason.strip()

	def _record_decision(self, user):
		"""Who made the decision now in force; empty while the row is pending."""
		self.confirmed_by = user
		self.confirmed_on = now_datetime() if user else None

	def _new_reason(self, before):
		reason = (self.decision_reason or "").strip()
		return bool(reason) and reason != ((before and before.decision_reason) or "").strip()

	def _check_evidence(self):
		if not self.evidence_source or not (self.evidence_reference or "").strip():
			frappe.throw(_("Enter the evidence source and reference before a decision."))

	def _check_conflict(self, requested):
		"""A machine may be Confirmed against its model's Not Compatible row only with a
		technical note that explains the exception."""
		if requested != CONFIRMED or self.applies_to != APPLIES_TO_MACHINE or not self.equipment_model:
			return
		model_row = frappe.db.get_value(
			"Card Equipment Part",
			{"compat_key": f"M|{self.equipment_model}|{self.item_code}", "is_active": 1},
			"compatibility_status",
		)
		if model_row == NOT_COMPATIBLE and not (self.technical_notes or "").strip():
			frappe.throw(_("The model row says Not Compatible: enter technical notes for this exception."))

	# ---------- retire ----------

	def _apply_retire(self, before):
		was_active = 1 if not before else before.is_active
		if bool(self.is_active) == bool(was_active):
			return
		if not is_approver():
			frappe.throw(_("Only a Card Manager retires or restores a fitment row."))
		if not self.is_active:
			if not (self.retire_reason or "").strip():
				frappe.throw(_("Enter the reason for retiring the row."))
			self.retired_by = frappe.session.user
			self.retired_on = now_datetime()
			return
		# restored: the old decision is not reused, the row is reviewed again
		self.compatibility_status = PENDING
		self.review_stage = None
		self._record_decision(None)
		self.retired_by = None
		self.retired_on = None
		self.retire_reason = None


# Company isolation (FR-070 pattern): a machine row belongs to its machine's company.
# A model row is technical data with no company.


def _restricted_companies(user):
	from card.party_registry import _restricted_companies as restricted

	return restricted(user, "Card Equipment Part", "Card Equipment")


def fitment_query_conditions(user=None):
	companies = _restricted_companies(user or frappe.session.user)
	if companies is None:
		return ""
	if not companies:
		return "`tabCard Equipment Part`.`card_equipment` is null"
	values = ", ".join(frappe.db.escape(c) for c in companies)
	return (
		"(`tabCard Equipment Part`.`card_equipment` is null or `tabCard Equipment Part`.`card_equipment` in"
		f" (select e.`name` from `tabCard Equipment` e where e.`company` in ({values})))"
	)


def has_fitment_permission(doc, ptype=None, user=None, debug=False):
	"""Document-level twin of the query conditions: the machine the request sends and
	the machine stored on a saved row must both belong to a permitted company."""
	companies = _restricted_companies(user or frappe.session.user)
	if companies is None:
		return True
	equipment = {doc.get("card_equipment")}
	if not doc.is_new():
		equipment.add(frappe.db.get_value(doc.doctype, doc.name, "card_equipment"))
	equipment.discard(None)
	if not equipment:
		return True
	owners = frappe.get_all("Card Equipment", filters={"name": ["in", list(equipment)]}, pluck="company")
	return len(owners) == len(equipment) and all(company in companies for company in owners)
