# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Controller-logic tests for the CARD app (app-level so Frappe does not
auto-build dependency test records). All records are created explicitly
against the site's existing master data and rolled back by the test
transaction."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt


def _ensure_masters():
	# ERPNext Company.on_insert builds default warehouses that reference the
	# "Transit" Warehouse Type, which a clean test_site does not have.
	if not frappe.db.exists("Warehouse Type", "Transit"):
		frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(ignore_permissions=True)

	company = frappe.get_all("Company", pluck="name", limit=1)
	company = company[0] if company else None
	if not company:
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "Test Equipment Co",
				"abbr": "TEC",
				"default_currency": "SAR",
				"country": "Saudi Arabia",
			}
		).insert(ignore_permissions=True)
		company = "Test Equipment Co"

	category = "Test Category"
	if not frappe.db.exists("Card Equipment Category", category):
		frappe.get_doc({"doctype": "Card Equipment Category", "category_name": category}).insert(
			ignore_permissions=True
		)

	etype = "Test Type"
	if not frappe.db.exists("Card Equipment Type", etype):
		frappe.get_doc(
			{
				"doctype": "Card Equipment Type",
				"equipment_type_name": etype,
				"equipment_category": category,
				"meter_type": "ساعات",
			}
		).insert(ignore_permissions=True)

	project = frappe.get_all("Project", pluck="name", limit=1)
	project = project[0] if project else None
	if not project:
		frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "Test Project",
				"status": "Open",
				"company": company,
			}
		).insert(ignore_permissions=True)
		project = "Test Project"

	supplier_group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
	if not supplier_group:
		root = "All Supplier Groups"
		if not frappe.db.exists("Supplier Group", root):
			frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": root, "is_group": 1}).insert(
				ignore_permissions=True
			)
		supplier_group = "Test Supplier Group"
		if not frappe.db.exists("Supplier Group", supplier_group):
			frappe.get_doc(
				{
					"doctype": "Supplier Group",
					"supplier_group_name": supplier_group,
					"parent_supplier_group": root,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)

	# Persist across the per-test transaction rollback (setUpClass runs outside it).
	frappe.db.commit()
	return {
		"company": company,
		"category": category,
		"etype": etype,
		"project": project,
		"supplier_group": supplier_group,
	}


def _days(hours_list, year=2026, month=9):
	return [
		{"operation_date": "%04d-%02d-%02d" % (year, month, i), "day_status": "عمل", "working_hours": h}
		for i, h in enumerate(hours_list, start=1)
	]


class TestCardEquipment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def _make_equipment(self, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self._m["company"]
		d.equipment_type = self._m["etype"]
		d.ownership = kw.pop("ownership", "إيجار")
		d.equipment_name = kw.pop("equipment_name", "TEST-EQ-" + frappe.generate_hash(length=8))
		for key, value in kw.items():
			setattr(d, key, value)
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def test_hourly_rate_from_daily(self):
		eq = self._make_equipment(rate_type="باليوم", rate=750, daily_hours=10)
		self.assertEqual(flt(eq.approved_hourly_rate), 75.0)

	def test_hourly_rate_direct(self):
		# daily_hours is a mandatory field but is ignored for the "بالساعة" rate type.
		eq = self._make_equipment(rate_type="بالساعة", rate=60, daily_hours=8)
		self.assertEqual(flt(eq.approved_hourly_rate), 60.0)

	def test_daily_without_hours_raises(self):
		with self.assertRaises(frappe.ValidationError):
			self._make_equipment(rate_type="باليوم", rate=750, daily_hours=0)


class TestCardMonthlyCard(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.project = self._m["project"]
		sg = self._m["supplier_group"]
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-SUP-" + self.token
		sup.supplier_group = sg
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def _equipment(self, ownership="إيجار", rate=750, daily_hours=10):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self.etype
		d.ownership = ownership
		d.equipment_name = "TEST-EQ-" + self.token
		d.rate_type = "باليوم"
		d.rate = rate
		d.daily_hours = daily_hours
		if ownership != "ملك":
			d.supplier = self.supplier
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _card(self, eq, hours_list, shift="نهاري", adjustments=None, submit=False):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = shift
		c.month = "09"
		c.year = 2026
		for row in _days(hours_list):
			c.append("days", row)
		for adj in adjustments or []:
			c.append("adjustments", adj)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def test_amount_daily_rate(self):
		eq = self._equipment(rate=750, daily_hours=10)  # hourly 75
		c = self._card(eq, [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 9])  # 109h
		self.assertEqual(flt(c.total_working_hours), 109.0)
		self.assertEqual(c.working_days, 11)
		self.assertEqual(flt(c.amount), 8175.0)
		self.assertEqual(flt(c.net_amount), 8175.0)

	def test_owned_equipment_zero_amount(self):
		eq = self._equipment(ownership="ملك", rate=750, daily_hours=10)
		c = self._card(eq, [10, 10, 10])
		self.assertEqual(flt(c.amount), 0.0)
		self.assertEqual(flt(c.net_amount), 0.0)

	def test_adjustments_net(self):
		eq = self._equipment(rate=750, daily_hours=10)
		c = self._card(
			eq,
			[10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 9],  # 8175
			adjustments=[
				{"adjustment_type": "إضافة", "description": "add", "amount": 500},
				{"adjustment_type": "خصم", "description": "ded", "amount": 200},
			],
		)
		self.assertEqual(flt(c.total_additions), 500.0)
		self.assertEqual(flt(c.total_deductions), 200.0)
		self.assertEqual(flt(c.net_amount), 8475.0)

	def test_net_amount_backfill(self):
		# Reproduce EOMC-2026-09-0240: amount 5,280 (88h x 600/10), net wiped to 0
		# by the legacy pre-v1.0 submit. The v1.0.1 backfill restores net = amount.
		from card.patches.v1_0 import backfill_net_amount

		eq = self._equipment(rate=600, daily_hours=10)  # hourly 60
		c = self._card(eq, [8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8], submit=True)  # 88h
		self.assertEqual(flt(c.amount), 5280.0)
		# simulate the legacy submitted row with net_amount wiped
		frappe.db.set_value("Card Monthly Card", c.name, "net_amount", 0, update_modified=False)
		backfill_net_amount.execute()
		self.assertEqual(flt(frappe.db.get_value("Card Monthly Card", c.name, "net_amount")), 5280.0)
		# idempotent: a second run changes nothing
		backfill_net_amount.execute()
		self.assertEqual(flt(frappe.db.get_value("Card Monthly Card", c.name, "net_amount")), 5280.0)

	def test_owned_card_net_not_backfilled(self):
		# genuinely-zero cards (owned equipment, amount 0) must stay 0 after backfill
		from card.patches.v1_0 import backfill_net_amount

		eq = self._equipment(ownership="ملك", rate=600, daily_hours=10)
		c = self._card(eq, [8, 8, 8], submit=True)
		self.assertEqual(flt(c.amount), 0.0)
		backfill_net_amount.execute()
		self.assertEqual(flt(frappe.db.get_value("Card Monthly Card", c.name, "net_amount")), 0.0)

	def test_duplicate_card_raises(self):
		eq = self._equipment()
		self._card(eq, [10, 10])
		with self.assertRaises(frappe.ValidationError):
			self._card(eq, [10, 10, 10])

	def test_date_outside_month_raises(self):
		eq = self._equipment()
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		c.append("days", {"operation_date": "2026-10-01", "day_status": "عمل", "working_hours": 8})
		with self.assertRaises(frappe.ValidationError):
			c.insert(ignore_permissions=True)

	def test_supplier_sync_on_submit(self):
		eq = self._equipment(rate=750, daily_hours=10)
		self._card(eq, [10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 9], submit=True)  # 109h -> 8175
		self.assertTrue(frappe.db.exists("Card Equipment Supplier", self.supplier))
		rec = frappe.get_doc("Card Equipment Supplier", self.supplier)
		self.assertEqual(rec.card_count, 1)
		self.assertEqual(rec.equipment_count, 1)
		self.assertEqual(flt(rec.total_hours), 109.0)
		self.assertEqual(flt(rec.total_net), 8175.0)
