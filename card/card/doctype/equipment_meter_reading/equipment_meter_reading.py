# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-140 (#31 D6): an engine-hour meter reading of one equipment, entered by the site supervisor (weekly, at a
handover or at a service visit).

Rules, enforced on the server for every entry point (Desk, REST, import):

- the company is always the equipment's company (the form value is replaced, never trusted);
- readings of one equipment rise with time: compared with the submitted readings just before and just after
  this one's date and time, a lower reading is refused unless it is marked as a meter reset with a reason, and a
  backdated reading may not exceed the next submitted one (unless that one is a reset); two submitted readings of
  the same equipment never share a date and time. The check runs on every save and again on submit under a lock on
  the equipment row, so two parallel submits cannot both pass;
- an amendment amends a cancelled reading of the same company that the user may read;
- the attachment is a private JPEG, PNG, WebP or PDF of this record (card.attachment_validator).

Company isolation comes from the generic company scope (card.company_scope, FR-131). A reading feeds nothing yet:
the monthly card, the billable hours and every posting are unchanged."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, cstr, flt, get_datetime

from card.attachment_validator import (
	check_attachment_content,
	claim_file,
	new_form_prefix,
	require_record_file,
)

DOCTYPE = "Equipment Meter Reading"


def neighbour_readings(equipment, reading_datetime, exclude=None, for_update=False):
	"""The submitted readings of ``equipment`` just before, at and just after ``reading_datetime``
	(``exclude`` is left out), as (previous, same_time, next) rows or None. ``for_update`` makes them locking
	reads: under REPEATABLE READ a plain read after a lock wait still sees the transaction's old snapshot, a locking
	read sees the latest committed rows."""
	moment = get_datetime(reading_datetime)
	base = {"equipment": equipment, "docstatus": 1}
	if exclude:
		base["name"] = ["!=", exclude]
	fields = ["name", "reading_datetime", "engine_hours", "is_meter_reset"]

	def first(condition, order):
		rows = frappe.db.get_values(
			DOCTYPE,
			{**base, "reading_datetime": condition},
			fields,
			as_dict=True,
			order_by=f"reading_datetime {order}, creation {order}",
			limit=1,
			for_update=for_update,
		)
		return rows[0] if rows else None

	return (
		first(["<", moment], "desc"),
		first(["=", moment], "asc"),
		first([">", moment], "asc"),
	)


class EquipmentMeterReading(Document):
	def validate(self):
		self._set_company()
		self._validate_amended_from()
		self._validate_reset()
		self._validate_attachment()
		self._check_sequence()

	def before_submit(self):
		# serialise submits of the same equipment: a parallel submit waits here and then sees this reading
		frappe.db.get_value("Card Equipment", self.equipment, "name", for_update=True)
		self._check_sequence(for_update=True)

	def on_update(self):
		if self.flags.get("attachment_row"):
			claim_file(self.flags.attachment_row, self.doctype, self.name, "attachment")

	# ---------- rules ----------
	def _set_company(self):
		company = frappe.db.get_value("Card Equipment", self.equipment, "company") if self.equipment else None
		if self.equipment and not company:
			frappe.throw(
				_("Equipment {0} has no company; set its company before recording a meter reading.").format(
					self.equipment
				)
			)
		self.company = company

	def _validate_amended_from(self):
		if not self.amended_from or not (self.is_new() or self.has_value_changed("amended_from")):
			return
		source = frappe.db.get_value(DOCTYPE, self.amended_from, ["company", "docstatus"], as_dict=True)
		if not source or cint(source.docstatus) != 2:
			frappe.throw(_("Only a cancelled meter reading can be amended."))
		if source.company != self.company or not frappe.has_permission(DOCTYPE, "read", self.amended_from):
			frappe.throw(
				_("An amendment of a meter reading stays in the company of the reading it amends."),
				frappe.PermissionError,
			)

	def _validate_reset(self):
		self.reset_reason = cstr(self.reset_reason).strip() or None
		if cint(self.is_meter_reset) and not self.reset_reason:
			frappe.throw(_("Enter the reason for the meter reset."))
		if not cint(self.is_meter_reset):
			self.reset_reason = None
		if flt(self.engine_hours) < 0:
			frappe.throw(_("Engine hours cannot be negative."))

	def _validate_attachment(self):
		"""A private file of this record (or the user's own upload, which this record then claims), checked when it
		is set or changed; an amendment keeps the file of the cancelled reading it amends."""
		self.flags.attachment_row = None
		temporary = self.get("__temporary_name") if self.is_new() else None
		if temporary and not cstr(temporary).startswith(new_form_prefix(self.doctype)):
			# not an unsaved-form name (e.g. another record's name): never let Frappe relink files from it
			self.__dict__.pop("__temporary_name", None)
			temporary = None
		url = self.attachment
		if not url or not (self.is_new() or self.has_value_changed("attachment")):
			return
		if (
			self.is_new()
			and self.amended_from
			and url == frappe.db.get_value(DOCTYPE, self.amended_from, "attachment")
		):
			require_record_file(url, self.doctype, self.amended_from, attached_only=True)
			return
		row = require_record_file(url, self.doctype, self.name, temporary)
		check_attachment_content(url, file_row=row)
		self.flags.attachment_row = row

	def _check_sequence(self, for_update=False):
		if not self.equipment or not self.reading_datetime:
			return
		previous, same_time, following = neighbour_readings(
			self.equipment,
			self.reading_datetime,
			exclude=None if self.is_new() else self.name,
			for_update=for_update,
		)
		if same_time:
			frappe.throw(
				_("Equipment {0} already has the submitted meter reading {1} at {2}.").format(
					self.equipment, same_time.name, self.reading_datetime
				)
			)
		self.previous_reading = previous.name if previous else None
		self.previous_engine_hours = flt(previous.engine_hours) if previous else 0
		hours = flt(self.engine_hours)
		if cint(self.is_meter_reset):
			if not previous or hours >= flt(previous.engine_hours):
				frappe.throw(
					_("Mark a meter reset only when the reading is lower than the previous reading.")
				)
		elif previous and hours < flt(previous.engine_hours):
			frappe.throw(
				_(
					"Engine hours {0} are lower than the previous reading {1} ({2}). Mark the reading as a meter reset and enter the reason, or correct it."
				).format(hours, previous.name, flt(previous.engine_hours))
			)
		if following and not cint(following.is_meter_reset) and hours > flt(following.engine_hours):
			frappe.throw(
				_("Engine hours {0} are higher than the later reading {1} ({2}).").format(
					hours, following.name, flt(following.engine_hours)
				)
			)
