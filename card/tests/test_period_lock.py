# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Period lock (server-side), submit snapshot, and gated notifications."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, get_last_day, getdate, nowdate

from card.notifications import notify
from card.tests.diesel_price import use_fill_price
from card.tests.test_controllers import _ensure_masters


def _past_month_year():
	today = getdate(nowdate())
	year, month = today.year, today.month - 2
	if month < 1:
		month += 12
		year -= 1
	return "%02d" % month, str(year)


class TestPeriodLockAndSnapshot(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.month_str, self.year_str = _past_month_year()
		self.lock_date = get_last_day(getdate(f"{self.year_str}-{self.month_str}-01"))
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-PL-PROJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-PL-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _set(self, field, value):
		frappe.db.set_single_value("Card Settings", field, value)

	def _make_equipment(self, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = kw.pop("ownership", "إيجار")
		d.supplier = kw.pop("supplier", self.supplier)
		d.equipment_name = kw.pop("equipment_name", "TEST-EQ-" + frappe.generate_hash(length=8))
		for k, v in kw.items():
			setattr(d, k, v)
		d.insert(ignore_permissions=True)
		return d

	def _new_card(self, eq, hours=(10, 10), shift="نهاري"):
		d = frappe.new_doc("Card Monthly Card")
		d.equipment = eq.name
		d.project = self.project
		d.shift = shift
		d.month = self.month_str
		d.year = int(self.year_str)
		for i, h in enumerate(hours, start=1):
			d.append(
				"days",
				{
					"operation_date": "%s-%s-%02d" % (self.year_str, self.month_str, i),
					"day_status": "عمل",
					"working_hours": h,
				},
			)
		return d

	def _equip(self):
		return self._make_equipment(rate_type="باليوم", rate=750, daily_hours=10, **{"الوقود_على": "الشركة"})

	# ---- period lock ----
	def test_no_lock_is_noop(self):
		self._set("period_lock_date", None)
		card = self._new_card(self._equip())
		card.insert(ignore_permissions=True)  # must not raise
		self.assertTrue(card.name)

	def test_lock_blocks_card_without_override(self):
		self._set("period_lock_date", self.lock_date)
		self._set("period_lock_override_role", None)
		card = self._new_card(self._equip())
		with self.assertRaises(frappe.ValidationError):
			card.insert(ignore_permissions=True)

	def test_override_role_allows_card(self):
		self._set("period_lock_date", self.lock_date)
		self._set("period_lock_override_role", "System Manager")  # Administrator holds it
		card = self._new_card(self._equip())
		card.insert(ignore_permissions=True)
		self.assertTrue(card.name)

	def test_lock_blocks_diesel_fill(self):
		self._set("period_lock_date", self.lock_date)
		self._set("period_lock_override_role", None)
		fill = frappe.new_doc("Project Diesel Fill")
		fill.date = self.lock_date
		fill.project = self.project
		fill.supplier = self.supplier
		fill.company = self.company
		fill.litres = 100
		fill.unit_price = 2
		with self.assertRaises(frappe.ValidationError):
			use_fill_price(fill).insert(ignore_permissions=True)

	def test_lock_blocks_cancel(self):
		# submit before the lock, then lock and try to cancel
		self._set("period_lock_date", None)
		card = self._new_card(self._equip())
		card.insert(ignore_permissions=True)
		card.submit()
		self._set("period_lock_date", self.lock_date)
		self._set("period_lock_override_role", None)
		with self.assertRaises(frappe.ValidationError):
			card.cancel()

	def test_lock_blocks_delete(self):
		self._set("period_lock_date", None)
		card = self._new_card(self._equip())
		card.insert(ignore_permissions=True)
		self._set("period_lock_date", self.lock_date)
		self._set("period_lock_override_role", None)
		with self.assertRaises(frappe.ValidationError):
			card.delete()

	# ---- snapshot ----
	def test_snapshot_on_submit(self):
		self._set("period_lock_date", None)
		eq = self._equip()
		card = self._new_card(eq, hours=(10, 10))
		card.insert(ignore_permissions=True)
		net_before = flt(card.net_amount)
		card.submit()
		card.reload()
		self.assertEqual(flt(card.daily_hours_used), 10.0)
		self.assertEqual(flt(card.hourly_rate_used), 75.0)
		self.assertEqual(card.diesel_policy_used, "الشركة")
		self.assertEqual(flt(card.net_amount), net_before)  # snapshot never changes amounts

	# ---- notifications (gating mechanism shared by all notify_* flags) ----
	def test_notify_gating(self):
		user = "nlog-" + frappe.generate_hash(length=6) + "@card.test"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "NLog",
					"send_welcome_email": 0,
					"enabled": 1,
				}
			).insert(ignore_permissions=True)
		self._set("notify_on_card_submit", 0)
		self.assertEqual(notify("notify_on_card_submit", [user], "s", "m"), 0)
		self._set("notify_on_card_submit", 1)
		self.assertEqual(notify("notify_on_card_submit", [user], "s", "m"), 1)
		self.assertTrue(frappe.db.exists("Notification Log", {"for_user": user}))
