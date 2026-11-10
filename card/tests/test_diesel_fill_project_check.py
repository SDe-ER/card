# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-126 (#124 WP-11, #31): the equipment of a diesel fill must be assigned to the fill's project on
the fill date. Per company in Card Company Settings `diesel_fill_project_check`: Off, Warn (default,
also when empty: message, saved) or Enforce (refused). Only new fills, or fills whose equipment,
project or date changed, are checked; submitted fills are never touched."""

import re

import frappe
from frappe.tests import IntegrationTestCase

from card.tests.diesel_price import approve_fill, set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _set

MESSAGE = "has no assignment on project"


class TestDieselFillProjectCheck(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.company = self._m["company"]
		_set("period_lock_date", None)
		_set("diesel_supplier", None)
		_set("diesel_supplier_policy", "متغير")
		set_diesel_price(self.company, 2)
		self._mode(self.company, None)  # never configured: the default applies
		self.project = self._project(self.company)
		self.other_project = self._project(self.company)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DFPC-SUP-" + frappe.generate_hash(length=8)
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		self.eq = self._equipment(self.company)
		frappe.clear_messages()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- helpers ----------

	def _mode(self, company, mode):
		frappe.db.set_value(
			"Card Company Settings",
			{"parent": "Card Settings", "parentfield": "company_settings", "company": company},
			"diesel_fill_project_check",
			mode,
		)

	def _project(self, company):
		p = frappe.new_doc("Project")
		p.project_name = "TEST-DFPC-PRJ-" + frappe.generate_hash(length=8)
		p.company = company
		return p.insert(ignore_permissions=True).name

	def _equipment(self, company):
		d = frappe.new_doc("Card Equipment")
		d.company = company
		d.equipment_type = self._m["etype"]
		d.ownership = "ملك"
		d.equipment_name = "TEST-DFPC-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		return d.insert(ignore_permissions=True).name

	def _assign(self, equipment, project, from_date="2026-09-01", to_date=None):
		return frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": equipment,
				"project": project,
				"from_date": from_date,
				"to_date": to_date,
			}
		).insert(ignore_permissions=True)

	def _fill(self, date="2026-09-15", company=None, project=None, equipment=None, listed=None):
		data = {
			"doctype": "Project Diesel Fill",
			"date": date,
			"company": company or self.company,
			"project": project or self.project,
			"supplier": self.supplier,
			"litres": 100,
		}
		if equipment:
			data["card_equipment"] = equipment
		if listed:
			data["equipment_filled"] = [
				{"card_equipment": e, "match_status": "Matched", "reported_name": e} for e in listed
			]
		return frappe.get_doc(data).insert()

	def _warned(self):
		return any(
			MESSAGE in str(m.get("message") if isinstance(m, dict) else m) for m in frappe.local.message_log
		)

	# ---------- default and Warn ----------

	def test_default_is_warn(self):
		f = self._fill(equipment=self.eq)  # no assignment at all
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(self._warned())

	def test_warn_saves_with_a_message(self):
		self._mode(self.company, "Warn")
		f = self._fill(equipment=self.eq)
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(self._warned())

	def test_assigned_equipment_has_no_message(self):
		self._assign(self.eq, self.project)
		self._fill(equipment=self.eq)
		self.assertFalse(self._warned())

	def test_project_tank_fill_without_equipment_is_not_checked(self):
		self._mode(self.company, "Enforce")
		self._fill()
		self.assertFalse(self._warned())

	# ---------- Off ----------

	def test_off_checks_nothing(self):
		self._mode(self.company, "Off")
		self._fill(equipment=self.eq)
		self.assertFalse(self._warned())

	# ---------- Enforce ----------

	def test_enforce_refuses_an_unassigned_equipment(self):
		self._mode(self.company, "Enforce")
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq)

	def test_enforce_refuses_an_assignment_on_another_project(self):
		self._mode(self.company, "Enforce")
		self._assign(self.eq, self.other_project)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq)

	def test_enforce_period_boundaries(self):
		self._mode(self.company, "Enforce")
		self._assign(self.eq, self.project, "2026-09-01", "2026-09-30")
		for date in ("2026-09-01", "2026-09-30"):
			with self.subTest(date=date):
				self._fill(date=date, equipment=self.eq)
		for date in ("2026-08-31", "2026-10-01"):
			with self.subTest(date=date), self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
				self._fill(date=date, equipment=self.eq)

	def test_enforce_open_ended_assignment(self):
		self._mode(self.company, "Enforce")
		self._assign(self.eq, self.project, "2026-09-01")
		self._fill(date="2027-03-01", equipment=self.eq)

	def test_enforce_checks_every_listed_equipment(self):
		self._mode(self.company, "Enforce")
		second = self._equipment(self.company)
		self._assign(self.eq, self.project)
		with self.assertRaisesRegex(frappe.ValidationError, re.escape(second)):
			self._fill(listed=[self.eq, second])
		self._assign(second, self.project)
		self._fill(listed=[self.eq, second])

	# ---------- only new or changed fills ----------

	def test_unchanged_draft_is_not_checked_again(self):
		self._mode(self.company, "Off")
		f = self._fill(equipment=self.eq)
		self._mode(self.company, "Enforce")
		f.reload()
		f.remarks = "edited"
		f.save()  # equipment, project and date unchanged
		f.date = "2026-09-16"
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()

	def test_changed_project_or_equipment_is_checked(self):
		self._mode(self.company, "Off")
		self._assign(self.eq, self.project)
		f = self._fill(equipment=self.eq)
		self._mode(self.company, "Enforce")
		f.reload()
		f.project = self.other_project
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()
		f.reload()
		f.card_equipment = self._equipment(self.company)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()

	def test_existing_fill_submits_and_stays_submitted(self):
		self._mode(self.company, "Off")
		f = self._fill(equipment=self.eq)
		self._mode(self.company, "Enforce")
		f.reload()
		approve_fill(f)
		f.submit()  # nothing the check looks at changed
		self.assertEqual(frappe.db.get_value("Project Diesel Fill", f.name, "docstatus"), 1)

	# ---------- multi-company ----------

	def test_mode_is_per_company(self):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-DFPC-C-" + frappe.generate_hash(length=8)
		comp.abbr = "DF" + frappe.generate_hash(length=4)
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		other = comp.insert(ignore_permissions=True).name
		set_diesel_price(other, 3)
		self._mode(other, "Enforce")
		self._mode(self.company, "Warn")
		other_eq = self._equipment(other)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(company=other, project=self._project(other), equipment=other_eq)
		f = self._fill(equipment=self.eq)  # this company only warns
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		# Enforce on this company now refuses its own unassigned equipment too
		self._mode(self.company, "Enforce")
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq, date="2026-09-20")
