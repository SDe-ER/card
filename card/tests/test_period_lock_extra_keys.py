# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Period lock must read the document's own date field only. A request (REST PUT, frappe.client
save/submit, desk savedocs incl. Cancel) can carry keys that are not fields of the DocType; Frappe
keeps them as attributes, so an extra "to_date" must never move a locked document out of the lock.
A request may also change a real date field: a save or submit is judged by the stored and the new
date, so no document moves out of (or into) the locked period; Frappe skips validate on cancel and
stores the request's values before on_cancel, so a cancel is judged by the stored date and may not
change it."""

import json

import frappe
from frappe.client import submit as client_submit
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from card.tests import test_period_lock
from card.tests.diesel_price import approve_fill, use_fill_price

FAR_DATE = "2999-01-01"


class TestPeriodLockExtraKeys(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = test_period_lock._ensure_masters()

	# same fixtures as test_period_lock (borrowed, not inherited, so its tests are not run twice)
	_base = test_period_lock.TestPeriodLockAndSnapshot
	setUp = _base.setUp
	tearDown = _base.tearDown
	_set = _base._set
	_make_equipment = _base._make_equipment
	_new_card = _base._new_card
	_equip = _base._equip

	def _lock(self):
		self._set("period_lock_date", self.lock_date)
		self._set("period_lock_override_role", None)

	def _refused(self):
		# the lock message carries the lock date in every language; other validation errors do not
		return self.assertRaisesRegex(frappe.ValidationError, str(getdate(self.lock_date)))

	def _unlock(self):
		self._set("period_lock_date", None)

	def _settings(self):
		# a free diesel supplier, so the fill is refused (or saved) only by the period lock
		self._set("diesel_supplier", None)
		self._set("diesel_supplier_policy", "متغير")

	def _fill(self, date=None):
		self._settings()
		fill = frappe.new_doc("Project Diesel Fill")
		fill.date = date or self.lock_date
		fill.project = self.project
		fill.supplier = self.supplier
		fill.company = self.company
		fill.litres = 100
		fill.unit_price = 2
		return use_fill_price(fill)

	def _transport(self, date=None):
		eq = self._make_equipment(
			ownership="ملك", supplier=None, rate_type="باليوم", rate=750, daily_hours=10
		)
		t = frappe.new_doc("Equipment Transport")
		t.equipment = eq.name
		t.project = self.project
		t.date = date or self.lock_date
		t.transport_supplier = self.supplier
		t.company = self.company
		t.amount = 100
		return t

	def _submitted(self, doc):
		self._unlock()
		doc.insert(ignore_permissions=True)
		doc.submit()
		self._lock()
		return doc

	def _cancel_request(self, doc, **changes):
		"""What Desk sends for Cancel: the whole document JSON (with any changes) plus action=Cancel."""
		d = frappe.get_doc(doc.doctype, doc.name).as_dict()
		d.update(changes or {"to_date": FAR_DATE})
		frappe.db.savepoint("period_lock_cancel")
		try:
			savedocs(json.dumps(d, default=str), "Cancel")
		except Exception:
			# a refused request is rolled back by the request handler; on_cancel runs after the row update
			frappe.db.rollback(save_point="period_lock_cancel")
			raise

	# ---- guards (pass on main) ----
	def test_guard_locked_fill_refused(self):
		self._lock()
		with self._refused():
			self._fill().insert(ignore_permissions=True)

	def test_guard_locked_transport_refused(self):
		self._lock()
		with self._refused():
			self._transport().insert(ignore_permissions=True)

	def test_guard_open_period_saves(self):
		self._lock()
		day = getdate(nowdate())
		self.assertTrue(self._fill(day).insert(ignore_permissions=True).name)
		self.assertTrue(self._transport(day).insert(ignore_permissions=True).name)

	def test_guard_card_extra_to_date_still_locked(self):
		# Card Monthly Card owns a real to_date that before_validate recomputes from month/year
		self._lock()
		card = self._new_card(self._equip())
		card.to_date = FAR_DATE
		with self._refused():
			card.insert(ignore_permissions=True)

	# ---- save with an extra to_date (fail on main) ----
	def test_fill_insert_with_extra_to_date_refused(self):
		self._lock()
		fill = self._fill()
		fill.update({"to_date": FAR_DATE})
		with self._refused():
			fill.insert(ignore_permissions=True)

	def test_transport_insert_with_extra_to_date_refused(self):
		self._lock()
		t = self._transport()
		t.update({"to_date": FAR_DATE})
		with self._refused():
			t.insert(ignore_permissions=True)

	def test_fill_rest_update_with_extra_to_date_refused(self):
		# api/v1 update_doc: get_doc(name) -> doc.update(request data) -> save()
		self._unlock()
		fill = self._fill().insert(ignore_permissions=True)
		self._lock()
		doc = frappe.get_doc("Project Diesel Fill", fill.name)
		doc.update({"litres": 50, "to_date": FAR_DATE})
		with self._refused():
			doc.save(ignore_permissions=True)

	# ---- submit with an extra to_date (fail on main) ----
	def test_fill_client_submit_with_extra_to_date_refused(self):
		self._unlock()
		fill = self._fill().insert(ignore_permissions=True)
		self._lock()
		d = frappe.get_doc("Project Diesel Fill", fill.name).as_dict()
		d["to_date"] = FAR_DATE
		with self._refused():
			client_submit(d)

	def test_transport_client_submit_with_extra_to_date_refused(self):
		self._unlock()
		t = self._transport().insert(ignore_permissions=True)
		self._lock()
		d = frappe.get_doc("Equipment Transport", t.name).as_dict()
		d["to_date"] = FAR_DATE
		with self._refused():
			client_submit(d)

	# ---- cancel through savedocs with an extra to_date (fail on main) ----
	def test_fill_savedocs_cancel_with_extra_to_date_refused(self):
		fill = self._submitted(self._fill())
		with self._refused():
			self._cancel_request(fill)
		self.assertEqual(frappe.db.get_value(fill.doctype, fill.name, "docstatus"), 1)

	def test_transport_savedocs_cancel_with_extra_to_date_refused(self):
		t = self._submitted(self._transport())
		with self._refused():
			self._cancel_request(t)
		self.assertEqual(frappe.db.get_value(t.doctype, t.name, "docstatus"), 1)

	# ---- a request that changes a REAL date field (Save / Submit / Cancel) ----
	# Save and submit are judged by the stored date and the new date; a cancel is judged by the stored
	# date and may not change it. "today" is always after the lock (two months back).

	def _today(self, days=0):
		return add_days(getdate(nowdate()), days)

	def _month_days(self, day):
		return [
			{
				"operation_date": "%s-%02d-%02d" % (day.year, day.month, i),
				"day_status": "عمل",
				"working_hours": 10,
			}
			for i in (1, 2)
		]

	def _current_card(self):
		today = getdate(nowdate())
		d = frappe.new_doc("Card Monthly Card")
		d.equipment = self._equip().name
		d.project = self.project
		d.shift = "نهاري"
		d.month = "%02d" % today.month
		d.year = today.year
		for row in self._month_days(today):
			d.append("days", row)
		return d

	def _draft(self, doc):
		self._unlock()
		doc.insert(ignore_permissions=True)
		self._lock()
		return doc

	def _stored(self, doc, field="date"):
		return getdate(frappe.db.get_value(doc.doctype, doc.name, field))

	def _save_request(self, doc, **changes):
		"""api/v1 update_doc: load, update with the request data, save."""
		d = frappe.get_doc(doc.doctype, doc.name)
		d.update(changes)
		d.save()

	def _submit_request(self, doc, **changes):
		d = frappe.get_doc(doc.doctype, doc.name).as_dict()
		d.update(changes)
		client_submit(d)

	def _refused_cancel(self, doc, field, **changes):
		before = self._stored(doc, field)
		with self.assertRaises(frappe.ValidationError):
			self._cancel_request(doc, **changes)
		self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "docstatus"), 1)
		self.assertEqual(self._stored(doc, field), before)

	# save: a locked draft cannot be moved to an open date (fail before the fix)
	def test_fill_locked_draft_moved_out_refused(self):
		fill = self._draft(self._fill())
		with self._refused():
			self._save_request(fill, date=self._today())
		self.assertEqual(self._stored(fill), getdate(self.lock_date))

	def test_transport_locked_draft_moved_out_refused(self):
		t = self._draft(self._transport())
		with self._refused():
			self._save_request(t, date=self._today())
		self.assertEqual(self._stored(t), getdate(self.lock_date))

	def test_card_locked_draft_moved_out_refused(self):
		card = self._draft(self._new_card(self._equip()))
		today = getdate(nowdate())
		with self._refused():
			self._save_request(
				card, month="%02d" % today.month, year=today.year, days=self._month_days(today)
			)
		self.assertEqual(self._stored(card, "to_date"), getdate(self.lock_date))

	# submit: a locked draft cannot be submitted with an open date (fail before the fix)
	def test_fill_submit_moved_out_refused(self):
		fill = self._draft(self._fill())
		with self._refused():
			self._submit_request(fill, date=str(self._today()))
		self.assertEqual(frappe.db.get_value(fill.doctype, fill.name, "docstatus"), 0)

	def test_transport_submit_moved_out_refused(self):
		t = self._draft(self._transport())
		with self._refused():
			self._submit_request(t, date=str(self._today()))
		self.assertEqual(frappe.db.get_value(t.doctype, t.name, "docstatus"), 0)

	def test_card_submit_moved_out_refused(self):
		card = self._draft(self._new_card(self._equip()))
		today = getdate(nowdate())
		with self._refused():
			self._submit_request(
				card, month="%02d" % today.month, year=today.year, days=self._month_days(today)
			)
		self.assertEqual(frappe.db.get_value(card.doctype, card.name, "docstatus"), 0)
		self.assertEqual(self._stored(card, "to_date"), getdate(self.lock_date))

	# cancel of a locked document with a changed date (fail before the fix)
	def test_card_savedocs_cancel_with_changed_to_date_refused(self):
		card = self._submitted(self._new_card(self._equip()))
		self._refused_cancel(card, "to_date", to_date=FAR_DATE)

	def test_fill_savedocs_cancel_with_changed_date_refused(self):
		fill = self._submitted(self._fill())
		self._refused_cancel(fill, "date", date=FAR_DATE)

	def test_transport_savedocs_cancel_with_changed_date_refused(self):
		t = self._submitted(self._transport())
		self._refused_cancel(t, "date", date=FAR_DATE)

	# cancel in an open period may not leave a changed date (fail before the fix)
	def test_card_open_cancel_with_changed_to_date_refused(self):
		card = self._submitted(self._current_card())
		self._refused_cancel(card, "to_date", to_date=FAR_DATE)

	def test_fill_open_cancel_with_changed_date_refused(self):
		fill = self._submitted(self._fill(self._today()))
		self._refused_cancel(fill, "date", date=str(self._today(1)))

	def test_transport_open_cancel_with_changed_date_refused(self):
		t = self._submitted(self._transport(self._today()))
		self._refused_cancel(t, "date", date=str(self._today(1)))

	def test_override_role_cancel_with_changed_date_refused(self):
		fill = self._submitted(self._fill())
		self._set("period_lock_override_role", "System Manager")  # Administrator holds it
		self._refused_cancel(fill, "date", date=FAR_DATE)

	# ---- guards: normal work and the override role keep working ----
	def test_guard_open_draft_moved_into_lock_refused(self):
		fill = self._draft(self._fill(self._today()))
		with self._refused():
			self._save_request(fill, date=self.lock_date)
		self.assertEqual(self._stored(fill), self._today())

	def test_guard_open_draft_date_change_allowed(self):
		fill = self._draft(self._fill(self._today()))
		t = self._draft(self._transport(self._today()))
		for doc in (fill, t):
			self._save_request(doc, date=self._today(-1))
			self.assertEqual(self._stored(doc), self._today(-1))
		approve_fill(frappe.get_doc(fill.doctype, fill.name)).submit()
		self.assertEqual(frappe.db.get_value(fill.doctype, fill.name, "docstatus"), 1)

	def test_guard_override_role_moves_locked_draft(self):
		fill = self._draft(self._fill())
		self._set("period_lock_override_role", "System Manager")
		self._save_request(fill, date=self._today())
		self.assertEqual(self._stored(fill), self._today())

	def test_guard_submitted_date_change_refused_by_frappe(self):
		# update after submit: date fields are not "allow on submit", so Frappe refuses the change
		fill = self._submitted(self._fill(self._today()))
		with self.assertRaises(frappe.ValidationError):
			self._save_request(fill, date=self._today(1))
		self.assertEqual(self._stored(fill), self._today())

	def test_guard_open_period_savedocs_cancel_allowed(self):
		day = self._today()
		card = self._submitted(self._current_card())
		fill = self._submitted(self._fill(day))
		t = self._submitted(self._transport(day))
		for doc, field in ((card, "to_date"), (fill, "date"), (t, "date")):
			before = self._stored(doc, field)
			d = frappe.get_doc(doc.doctype, doc.name).as_dict()
			savedocs(json.dumps(d, default=str), "Cancel")  # unchanged Desk cancel request
			self.assertEqual(frappe.db.get_value(doc.doctype, doc.name, "docstatus"), 2)
			self.assertEqual(self._stored(doc, field), before)

	def test_guard_locked_plain_cancel_refused(self):
		fill = self._submitted(self._fill())
		with self._refused():
			frappe.get_doc(fill.doctype, fill.name).cancel()

	def test_guard_override_role_allows_locked_cancel(self):
		fill = self._submitted(self._fill())
		self._set("period_lock_override_role", "System Manager")  # Administrator holds it
		frappe.get_doc(fill.doctype, fill.name).cancel()
		self.assertEqual(frappe.db.get_value(fill.doctype, fill.name, "docstatus"), 2)
		self.assertEqual(self._stored(fill), getdate(self.lock_date))
