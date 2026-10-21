# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Period lock must read the document's own date field only. A request (REST PUT, frappe.client
save/submit, desk savedocs incl. Cancel) can carry keys that are not fields of the DocType; Frappe
keeps them as attributes, so an extra "to_date" must never move a locked document out of the lock."""

import json

import frappe
from frappe.client import submit as client_submit
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, nowdate

from card.tests import test_period_lock
from card.tests.diesel_price import use_fill_price

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

	def _cancel_request(self, doc):
		"""What Desk sends for Cancel: the whole document JSON plus action=Cancel."""
		d = frappe.get_doc(doc.doctype, doc.name).as_dict()
		d["to_date"] = FAR_DATE
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
