# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-099: append-only meter reading (see card.meter)."""

import frappe
from frappe import _
from frappe.model.document import Document

from card.meter import REJECTED, VALID, assess, refresh_current_meter

# what may change on a saved reading: its status and the reason, nothing else
STATUS_FIELDS = {"status", "status_reason"}
STATUS_ROLES = {"System Manager", "Card Manager"}
SYSTEM_SOURCES = {
	"Diesel Fill",
	"Maintenance Order",
	"Legacy Fueling Log",
	# 4.4.0: field apps (DAWM) through card.integration_v1
	"Field Operation",
	"Field Fuelling",
}
# filled by CARD only; a Manual reading sent with them through REST gets them cleared
SYSTEM_FIELDS = (
	"source_doctype",
	"source_name",
	"source_key",
	"litres",
	"legacy_record",
	"legacy_created",
	"legacy_owner",
	"legacy_docstatus",
	"legacy_values",
)
# a reading may be up to this many hours ahead of the server clock (time zones, clock drift)
FUTURE_TOLERANCE_HOURS = 1


class CardMeterReading(Document):
	def validate(self):
		self._check_source()
		self._link_company()
		if self.is_new():
			if self.status == REJECTED and not self.status_reason:
				frappe.throw(_("A rejected reading needs a reason."))
			if self.flt_reading() < 0:
				frappe.throw(_("A meter reading cannot be negative."))
			self._check_time()
			assess(self)
		else:
			self._only_status_changes()

	def _check_time(self):
		from frappe.utils import add_to_date, get_datetime, now_datetime

		if not self.reading_time:
			self.reading_time = now_datetime()
		if self.source_type == "Legacy Fueling Log":
			return  # history is copied as it was; assess() flags it
		limit = add_to_date(now_datetime(), hours=FUTURE_TOLERANCE_HOURS)
		if get_datetime(self.reading_time) > limit:
			frappe.throw(_("A meter reading cannot be in the future."))

	def on_update(self):
		from card.maintenance import refresh_status

		if self.flags.get("card_skip_refresh"):
			return  # bulk import refreshes each equipment once at the end
		refresh_current_meter(self.equipment)
		before = self.get_doc_before_save()
		if before and before.get("equipment") and before.equipment != self.equipment:
			refresh_current_meter(before.equipment)
		if self.equipment:
			refresh_status(self.equipment)

	def on_trash(self):
		frappe.throw(_("Meter readings are never deleted; mark the reading Rejected with a reason."))

	def flt_reading(self):
		from frappe.utils import flt

		return flt(self.reading)

	def _check_source(self):
		"""Diesel fill, maintenance order and legacy readings are written by CARD only; a
		user enters Manual readings."""
		if self.flags.get("card_system_source"):
			return
		if self.is_new() and self.source_type in SYSTEM_SOURCES:
			frappe.throw(
				_("Readings from {0} are recorded by CARD from their document.").format(_(self.source_type))
			)
		if self.is_new():
			for field in SYSTEM_FIELDS:
				self.set(field, None)
			if not self.equipment:
				frappe.throw(_("Choose the equipment."))
			# the Asset of a Manual reading is always its equipment's Asset (set in _link_company)
			self.asset = None
		if not self.equipment:
			frappe.throw(_("Choose the equipment."))

	def _link_company(self):
		if self.equipment:
			eq = frappe.db.get_value(
				"Card Equipment", self.equipment, ["company", "meter_type", "الأصل_في_erpnext"], as_dict=True
			)
			if eq:
				self.company = eq.company
				if self.is_new() and not self.asset:
					self.asset = eq.get("الأصل_في_erpnext")
				if self.is_new() and eq.meter_type == "كيلومترات":
					self.reading_type = "Kilometres"
		elif self.asset:
			self.company = frappe.db.get_value("Asset", self.asset, "company")

	def _only_status_changes(self):
		"""Append-only: a saved reading changes only its status (with a reason), by a
		Card Manager / System Manager or by CARD itself (cancelled source)."""
		before = self.get_doc_before_save()
		changed = {
			df.fieldname
			for df in self.meta.fields
			if df.fieldtype not in ("Section Break", "Column Break", "Tab Break")
			and _norm(df, before.get(df.fieldname)) != _norm(df, self.get(df.fieldname))
		}
		# CARD attaches legacy readings of an Asset to the equipment linked to it later
		allowed = STATUS_FIELDS | (
			{"equipment", "company"} if self.flags.get("card_system_source") else set()
		)
		if changed - allowed:
			frappe.throw(
				_("A meter reading cannot be changed; record a new reading and mark this one Rejected.")
			)
		if not changed:
			return
		if not self.flags.get("card_system_source") and not (STATUS_ROLES & set(frappe.get_roles())):
			frappe.throw(
				_("Only a Card Manager can change the status of a meter reading."), frappe.PermissionError
			)
		if self.status != VALID and not self.status_reason:
			frappe.throw(_("Give the reason for the status {0}.").format(_(self.status)))
		if "status" in changed and self.status == VALID:
			self._check_revalidation()

	def _check_revalidation(self):
		"""A reading made Valid again is checked again: never for a cancelled source, and
		the plausibility rules decide (a Suspect result needs a Card Manager's reason)."""
		if self.source_doctype and self.source_name:
			if frappe.db.get_value(self.source_doctype, self.source_name, "docstatus") == 2:
				frappe.throw(
					_("The source document {0} is cancelled; its reading stays Rejected.").format(
						self.source_name
					)
				)
		if self.source_type == "Legacy Fueling Log" and frappe.utils.cint(self.legacy_docstatus) == 2:
			frappe.throw(_("The legacy Fueling Log was cancelled; its reading stays Rejected."))
		if self.source_doctype and self.source_name:
			newer = frappe.db.exists(
				"Card Meter Reading",
				{
					"source_doctype": self.source_doctype,
					"source_name": self.source_name,
					"source_key": self.source_key or ["is", "not set"],
					"status": ["!=", "Rejected"],
					"name": ["!=", self.name],
				},
			)
			if newer:
				frappe.throw(_("This reading was replaced by {0}; it stays Rejected.").format(newer))
		probe = frappe._dict(
			name=self.name,
			equipment=self.equipment,
			asset=self.asset,
			reading=self.reading,
			reading_time=self.reading_time,
			litres=self.litres,
			status=VALID,
		)
		assess(probe)  # on a copy: the saved reading keeps its recorded values
		if probe.status != VALID:
			frappe.throw(_("The reading is still implausible: {0}").format(probe.status_reason))


def _norm(df, value):
	"""Compare a stored value with the value a form or REST sends (types differ)."""
	from frappe.utils import cint, flt, get_datetime

	if value in (None, ""):
		return None
	if df.fieldtype in ("Datetime", "Date"):
		return get_datetime(value)
	if df.fieldtype in ("Float", "Currency", "Percent"):
		return flt(value, 6) or None
	if df.fieldtype in ("Int", "Check"):
		return cint(value) or None
	return str(value)
