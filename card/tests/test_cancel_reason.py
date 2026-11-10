# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-123 (WP-07, issues #35 and #51, governance G0): a Card Monthly Card, Equipment Transport or
Project Diesel Fill is cancelled only with a reason; the reason is stored and commented; a cancel
changes no other field or row (FR-050 open gap); a period-lock override leaves a Comment on the
document next to its log."""

import frappe
from frappe.desk.form.save import cancel as desk_cancel
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from card.cancel_reason import (
	DOCTYPES,
	CancelChangesDocumentError,
	CancelReasonRequiredError,
	cancel_with_reason,
)
from card.tests import test_period_lock, test_period_lock_extra_keys

MID_MONTH = test_period_lock_extra_keys.MID_MONTH

REASON = "Wrong project selected"


class TestCancelReason(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = test_period_lock._ensure_masters()

	# the period-lock fixtures (borrowed, not inherited, so their tests are not run twice)
	_base = test_period_lock_extra_keys.TestPeriodLockExtraKeys
	_set = _base._set
	_make_equipment = _base._make_equipment
	_new_card = _base._new_card
	_equip = _base._equip
	_lock = _base._lock
	_unlock = _base._unlock
	_settings = _base._settings
	_fill = _base._fill
	_transport = _base._transport
	_submitted = _base._submitted
	_draft = _base._draft
	_today = _base._today
	_month_days = _base._month_days
	_current_card = _base._current_card
	tearDown = _base.tearDown

	def setUp(self):
		self.enterContext(self.freeze_time(MID_MONTH))
		test_period_lock.TestPeriodLockAndSnapshot.setUp(self)

	def _open_docs(self):
		"""One submitted document of each doctype, dated in the open period; no lock afterwards."""
		docs = [
			self._submitted(self._current_card()),
			self._submitted(self._fill(self._today())),
			self._submitted(self._transport(self._today())),
		]
		self._unlock()
		return docs

	def _docstatus(self, doc):
		return frappe.db.get_value(doc.doctype, doc.name, "docstatus")

	def _comments(self, doc, containing=None):
		filters = {"reference_doctype": doc.doctype, "reference_name": doc.name, "comment_type": "Info"}
		if containing:
			filters["content"] = ("like", f"%{containing}%")
		return frappe.get_all("Comment", filters=filters, fields=["content", "comment_email"])

	def _refused(self, error, fn, *args, **kwargs):
		frappe.db.savepoint("cancel_reason")
		with self.assertRaises(error):
			try:
				fn(*args, **kwargs)
			except Exception:
				frappe.db.rollback(save_point="cancel_reason")
				raise

	# ---- the reason is mandatory, on every path ----
	def test_hooks_and_form_script_cover_the_three_doctypes(self):
		events = frappe.get_hooks("doc_events")
		doctype_js = frappe.get_hooks("doctype_js")
		for doctype in DOCTYPES:
			self.assertIn("card.cancel_reason.before_cancel", events[doctype]["before_cancel"])
			self.assertIn("card.cancel_reason.on_cancel", events[doctype]["on_cancel"])
			self.assertIn("public/js/cancel_reason.js", doctype_js[doctype])
			df = frappe.get_meta(doctype).get_field("cancel_reason")
			self.assertEqual(
				# not allow on submit: the cancel stores it without that (test_reason_is_stored_and_commented)
				(df.fieldtype, df.allow_on_submit, df.no_copy, df.read_only),
				("Small Text", 0, 1, 1),
			)

	def test_empty_reason_refused_through_the_api(self):
		for doc in self._open_docs():
			with self.subTest(doctype=doc.doctype):
				# the Desk cancel endpoint and a Python/API cancel of the stored document
				self._refused(CancelReasonRequiredError, desk_cancel, doc.doctype, doc.name)
				self._refused(CancelReasonRequiredError, frappe.get_doc(doc.doctype, doc.name).cancel)
				# a REST cancel (PUT docstatus 2) without a reason, or with a blank one
				for blank in (None, "", "   "):
					d = frappe.get_doc(doc.doctype, doc.name)
					d.cancel_reason = blank
					d.docstatus = 2
					self._refused(CancelReasonRequiredError, d.save)
				# the form's method with a blank reason
				self._refused(CancelReasonRequiredError, cancel_with_reason, doc.doctype, doc.name, " ")
				self.assertEqual(self._docstatus(doc), 1)
				self.assertFalse(frappe.db.get_value(doc.doctype, doc.name, "cancel_reason"))
				self.assertFalse(self._comments(doc, "Cancelled by"))

	def test_reason_is_stored_and_commented(self):
		for doc in self._open_docs():
			with self.subTest(doctype=doc.doctype):
				out = cancel_with_reason(doc.doctype, doc.name, f"  {REASON}  ")
				self.assertEqual(out["docstatus"], 2)
				self.assertEqual(self._docstatus(doc), 2)
				self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "cancel_reason"), REASON)
				comments = self._comments(doc, REASON)
				self.assertEqual(len(comments), 1)
				self.assertIn(REASON, comments[0].content)
				self.assertIn("Administrator", comments[0].content)
				self.assertIn(str(getdate(MID_MONTH)), comments[0].content)
				self.assertEqual(comments[0].comment_email, "Administrator")

	def test_html_in_the_reason_is_removed(self):
		"""Frappe does not sanitize on cancel; the reason is stored as plain text on every path."""
		payload = '<img src=x onerror="alert(1)">'
		card, fill, t = self._open_docs()
		# only markup: nothing is left, so the cancel is refused
		self._refused(CancelReasonRequiredError, cancel_with_reason, fill.doctype, fill.name, payload)
		d = frappe.get_doc(t.doctype, t.name)
		d.update({"docstatus": 2, "cancel_reason": payload})
		self._refused(CancelReasonRequiredError, d.save)
		# text with markup and an unclosed tag: the text stays, the markup and the brackets go
		cancel_with_reason(fill.doctype, fill.name, f"Wrong {payload} project <img src=x onerror=alert(2)")
		d = frappe.get_doc(t.doctype, t.name)
		d.update({"docstatus": 2, "cancel_reason": f"Duplicate {payload}move"})
		d.save()
		for doc in (fill, t):
			stored = frappe.db.get_value(doc.doctype, doc.name, "cancel_reason")
			self.assertEqual(self._docstatus(doc), 2)
			self.assertNotIn("<", stored)
			self.assertNotIn(">", stored)
			self.assertNotIn("<", "".join(c.content for c in self._comments(doc, "Cancelled by")))
		self.assertTrue(frappe.db.get_value(fill.doctype, fill.name, "cancel_reason").startswith("Wrong"))
		self.assertEqual(frappe.db.get_value(t.doctype, t.name, "cancel_reason"), "Duplicate move")
		self.assertEqual(self._docstatus(card), 1)

	def test_cancel_cannot_fill_an_empty_field_with_its_default(self):
		card = self._open_docs()[0]
		frappe.db.set_value(card.doctype, card.name, "shift", "", update_modified=False)
		d = frappe.get_doc(card.doctype, card.name)
		d.shift = frappe.get_meta(card.doctype).get_field("shift").default
		d.cancel_reason = REASON
		self._refused(CancelChangesDocumentError, d.cancel)
		self.assertEqual(self._docstatus(card), 1)
		self.assertFalse(frappe.db.get_value(card.doctype, card.name, "shift"))
		# a field defaulted to "Today" is compared as a date, not parsed from its default
		fill = self._open_docs()[1]
		d = frappe.get_doc(fill.doctype, fill.name)
		d.date = self._today(-3)
		d.cancel_reason = REASON
		self._refused(CancelChangesDocumentError, d.cancel)

	def test_rest_cancel_with_reason_in_the_request(self):
		t = self._open_docs()[2]
		d = frappe.get_doc(t.doctype, t.name)
		d.update({"docstatus": 2, "cancel_reason": REASON})
		d.save()
		self.assertEqual(self._docstatus(t), 2)
		self.assertEqual(frappe.db.get_value(t.doctype, t.name, "cancel_reason"), REASON)

	def test_cancel_with_reason_checks_cancel_permission_and_doctype(self):
		fill = self._open_docs()[1]
		frappe.set_user("Guest")
		try:
			self._refused(frappe.PermissionError, cancel_with_reason, fill.doctype, fill.name, REASON)
		finally:
			frappe.set_user("Administrator")
		self._refused(frappe.PermissionError, cancel_with_reason, "Purchase Invoice", "X", REASON)
		self.assertEqual(self._docstatus(fill), 1)

	# ---- the reason is written only by the cancel ----
	def test_reason_not_set_by_update_after_submit_or_save(self):
		fill = self._open_docs()[1]
		d = frappe.get_doc(fill.doctype, fill.name)
		d.cancel_reason = REASON
		self._refused(CancelChangesDocumentError, d.save)
		self.assertFalse(frappe.db.get_value(fill.doctype, fill.name, "cancel_reason"))
		draft = self._fill(self._today())
		draft.cancel_reason = REASON
		draft.insert(ignore_permissions=True)
		self.assertFalse(frappe.db.get_value(draft.doctype, draft.name, "cancel_reason"))

	# ---- a cancel changes nothing else (FR-050 open gap) ----
	def test_no_other_field_changes_on_cancel(self):
		card, fill, t = self._open_docs()
		changes = (
			(card, lambda d: d.set("operator_name", "Changed"), "operator_name"),
			(card, lambda d: d.days[0].set("working_hours", 3), None),
			(fill, lambda d: d.set("litres", 999), "litres"),
			(fill, lambda d: d.set("remarks", "Changed"), "remarks"),
			(t, lambda d: d.set("remarks", "Changed"), "remarks"),
		)
		for doc, change, field in changes:
			with self.subTest(doctype=doc.doctype, field=field):
				before = frappe.get_doc(doc.doctype, doc.name).as_dict()
				d = frappe.get_doc(doc.doctype, doc.name)
				change(d)
				d.cancel_reason = REASON
				self._refused(CancelChangesDocumentError, d.cancel)
				after = frappe.get_doc(doc.doctype, doc.name).as_dict()
				self.assertEqual(self._docstatus(doc), 1)
				self.assertFalse(after.cancel_reason)
				if field:
					self.assertEqual(after[field], before[field])
				else:
					self.assertEqual(after.days[0].working_hours, before.days[0].working_hours)
		# an unchanged cancel with a reason goes through and keeps the approved values
		for doc, fields in (
			(card, ("operator_name", "net_amount")),
			(fill, ("litres", "amount")),
			(t, ("remarks", "amount")),
		):
			before = frappe.db.get_value(doc.doctype, doc.name, fields)
			cancel_with_reason(doc.doctype, doc.name, REASON)
			self.assertEqual(self._docstatus(doc), 2)
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, fields), before)

	def test_cancel_cannot_change_standard_columns(self):
		"""The shared guard also compares the document's owner and creation and each row's idx, owner and
		creation (Frappe skips validate_constants on a cancel and writes every column)."""
		card, fill, t = self._open_docs()

		def swap_idx(d):
			d.days[0].idx, d.days[1].idx = d.days[1].idx, d.days[0].idx

		changes = (
			(card, lambda d: d.set("owner", "Administrator" if d.owner != "Administrator" else "Guest")),
			(card, lambda d: d.set("creation", "2020-01-01 00:00:00")),
			(card, lambda d: d.days[0].set("owner", "Guest")),
			(card, lambda d: d.days[0].set("creation", "2020-01-01 00:00:00")),
			(card, swap_idx),
			(fill, lambda d: d.set("creation", "2020-01-01 00:00:00")),
			(t, lambda d: d.set("owner", "Guest")),
		)
		for doc, change in changes:
			with self.subTest(doctype=doc.doctype):
				before = frappe.get_doc(doc.doctype, doc.name).as_dict()
				d = frappe.get_doc(doc.doctype, doc.name)
				if doc is card and len(d.days) < 2 and change is swap_idx:
					continue
				change(d)
				d.cancel_reason = REASON
				self._refused(CancelChangesDocumentError, d.cancel)
				after = frappe.get_doc(doc.doctype, doc.name).as_dict()
				self.assertEqual(self._docstatus(doc), 1)
				self.assertEqual((after.owner, str(after.creation)), (before.owner, str(before.creation)))

	# ---- period-lock override is commented on the document ----
	def test_period_lock_override_adds_a_comment(self):
		fill = self._submitted(self._fill())  # dated on the lock date; locked afterwards
		self._set("period_lock_override_role", "System Manager")  # Administrator holds it
		cancel_with_reason(fill.doctype, fill.name, REASON)
		self.assertEqual(self._docstatus(fill), 2)
		contents = [c.content for c in self._comments(fill)]
		override = [c for c in contents if str(getdate(self.lock_date)) in c]
		self.assertEqual(len(override), 1, contents)
		self.assertIn("Administrator", override[0])
		self.assertEqual(len([c for c in contents if REASON in c]), 1)

	def test_period_lock_override_on_save_adds_a_comment(self):
		draft = self._draft(self._fill())  # a locked draft
		self._set("period_lock_override_role", "System Manager")
		d = frappe.get_doc(draft.doctype, draft.name)
		d.litres = 60
		d.save()
		contents = [c.content for c in self._comments(draft)]
		self.assertTrue([c for c in contents if str(getdate(self.lock_date)) in c], contents)

	def test_no_lock_no_override_comment(self):
		fill = self._open_docs()[1]
		cancel_with_reason(fill.doctype, fill.name, REASON)
		self.assertEqual(len(self._comments(fill)), len(self._comments(fill, REASON)))
