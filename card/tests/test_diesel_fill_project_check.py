# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-126 (#124 WP-11, #31): the equipment of a diesel fill must be assigned to the fill's project on
the fill date. Per company in Card Company Settings `diesel_fill_project_check`: Off, Warn only
(default, also when empty: message, saved) or Refuse. Only new fills, or fills whose company,
equipment, project or date changed, are checked; submitted fills are never touched. An assignment
covers a day by the rule of card.transfer._in_force (a from date is needed)."""

import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from card.card.doctype.project_diesel_fill.project_diesel_fill import (
	PROJECT_CHECK_ENFORCE as REFUSE,
)
from card.card.doctype.project_diesel_fill.project_diesel_fill import (
	PROJECT_CHECK_OFF as OFF,
)
from card.card.doctype.project_diesel_fill.project_diesel_fill import (
	PROJECT_CHECK_WARN as WARN,
)
from card.constants import MOVE_DAY_NEXT, MOVE_DAY_SAME
from card.tests import test_transfer as _transfer
from card.tests.diesel_price import approve_fill, set_diesel_price
from card.tests.test_controllers import _ensure_masters
from card.tests.test_settings_wiring import _set

MESSAGE = "has no assignment on project"


def set_mode(company, mode):
	frappe.db.set_value(
		"Card Company Settings",
		{"parent": "Card Settings", "parentfield": "company_settings", "company": company},
		"diesel_fill_project_check",
		mode,
	)


def warned():
	return any(
		MESSAGE in str(m.get("message") if isinstance(m, dict) else m) for m in frappe.local.message_log
	)


def prepare_fill_settings(company):
	_set("period_lock_date", None)
	_set("diesel_supplier", None)
	_set("diesel_supplier_policy", "متغير")
	set_diesel_price(company, 2)


class TestDieselFillProjectCheck(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.company = self._m["company"]
		prepare_fill_settings(self.company)
		set_mode(self.company, None)  # never configured: the default applies
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

	def _company(self):
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-DFPC-C-" + frappe.generate_hash(length=8)
		comp.abbr = "DF" + frappe.generate_hash(length=4)
		comp.default_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		comp.country = frappe.get_cached_value("Company", self.company, "country")
		other = comp.insert(ignore_permissions=True).name
		set_diesel_price(other, 3)
		return other

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

	# ---------- the setting ----------

	def test_setting_values_are_card_specific(self):
		df = frappe.get_meta("Card Company Settings").get_field("diesel_fill_project_check")
		self.assertEqual(df.options.split("\n"), [OFF, WARN, REFUSE])
		self.assertEqual(df.default, WARN)

	# ---------- default and Warn only ----------

	def test_default_is_warn(self):
		f = self._fill(equipment=self.eq)  # no assignment at all
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(warned())

	def test_warn_saves_with_a_message(self):
		set_mode(self.company, WARN)
		f = self._fill(equipment=self.eq)
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(warned())

	def test_assigned_equipment_has_no_message(self):
		self._assign(self.eq, self.project)
		self._fill(equipment=self.eq)
		self.assertFalse(warned())

	def test_project_tank_fill_without_equipment_is_not_checked(self):
		set_mode(self.company, REFUSE)
		self._fill()
		self.assertFalse(warned())

	# ---------- Off ----------

	def test_off_checks_nothing(self):
		set_mode(self.company, OFF)
		self._fill(equipment=self.eq)
		self.assertFalse(warned())

	# ---------- Refuse ----------

	def test_refuse_an_unassigned_equipment(self):
		set_mode(self.company, REFUSE)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq)

	def test_refuse_an_assignment_on_another_project(self):
		set_mode(self.company, REFUSE)
		self._assign(self.eq, self.other_project)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq)

	def test_assignment_without_from_date_covers_no_day(self):
		# the rule of card.transfer._in_force: the equipment location and transports ignore it too
		set_mode(self.company, REFUSE)
		self._assign(self.eq, self.project, from_date=None, to_date="2026-12-31")
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq)

	def test_refuse_period_boundaries(self):
		set_mode(self.company, REFUSE)
		self._assign(self.eq, self.project, "2026-09-01", "2026-09-30")
		for date in ("2026-09-01", "2026-09-30"):
			with self.subTest(date=date):
				self._fill(date=date, equipment=self.eq)
		for date in ("2026-08-31", "2026-10-01"):
			with self.subTest(date=date), self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
				self._fill(date=date, equipment=self.eq)

	def test_refuse_open_ended_assignment(self):
		set_mode(self.company, REFUSE)
		self._assign(self.eq, self.project, "2026-09-01")
		self._fill(date="2027-03-01", equipment=self.eq)

	def test_refuse_checks_every_listed_equipment(self):
		set_mode(self.company, REFUSE)
		second = self._equipment(self.company)
		self._assign(self.eq, self.project)
		with self.assertRaisesRegex(frappe.ValidationError, re.escape(second)):
			self._fill(listed=[self.eq, second])
		self._assign(second, self.project)
		self._fill(listed=[self.eq, second])

	# ---------- only new or changed fills ----------

	def test_unchanged_draft_is_not_checked_again(self):
		set_mode(self.company, OFF)
		f = self._fill(equipment=self.eq)
		set_mode(self.company, REFUSE)
		f.reload()
		f.remarks = "edited"
		f.save()  # company, equipment, project and date unchanged
		f.date = "2026-09-16"
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()

	def test_changed_project_or_equipment_is_checked(self):
		set_mode(self.company, OFF)
		self._assign(self.eq, self.project)
		f = self._fill(equipment=self.eq)
		set_mode(self.company, REFUSE)
		f.reload()
		f.project = self.other_project
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()
		f.reload()
		f.card_equipment = self._equipment(self.company)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()

	def test_changed_company_is_checked(self):
		other = self._company()
		set_mode(other, REFUSE)
		f = self._fill()  # a project-tank fill of this company
		f.reload()
		f.update(
			{"company": other, "project": self._project(other), "card_equipment": self._equipment(other)}
		)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			f.save()

	def test_existing_fill_submits_and_stays_submitted(self):
		set_mode(self.company, OFF)
		f = self._fill(equipment=self.eq)
		set_mode(self.company, REFUSE)
		f.reload()
		approve_fill(f)
		f.submit()  # nothing the check looks at changed
		self.assertEqual(frappe.db.get_value("Project Diesel Fill", f.name, "docstatus"), 1)

	# ---------- multi-company ----------

	def test_mode_is_per_company(self):
		other = self._company()
		set_mode(other, REFUSE)
		set_mode(self.company, WARN)
		other_eq = self._equipment(other)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(company=other, project=self._project(other), equipment=other_eq)
		f = self._fill(equipment=self.eq)  # this company only warns
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		set_mode(self.company, REFUSE)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(equipment=self.eq, date="2026-09-20")


class TestDieselFillProjectCheckMoveDay(IntegrationTestCase):
	"""Review M3: on the day of a project -> project transport the fill belongs to the project the
	company's move-day rule (FR-117) gives that day."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	tearDown = _transfer.TestEquipmentTransfer.tearDown
	_d = _transfer.TestEquipmentTransfer._d
	_project = _transfer.TestEquipmentTransfer._project
	_equipment = _transfer.TestEquipmentTransfer._equipment
	_assign = _transfer.TestEquipmentTransfer._assign
	_transport = _transfer.TestEquipmentTransfer._transport

	def setUp(self):
		_transfer.TestEquipmentTransfer.setUp(self)
		prepare_fill_settings(self.company)
		set_mode(self.company, REFUSE)

	def _rule(self, rule):
		frappe.db.set_value(
			"Card Company Settings",
			{"parent": "Card Settings", "parentfield": "company_settings", "company": self.company},
			"move_day_rule",
			rule,
		)

	def _fill(self, project, date, equipment):
		return frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": date,
				"company": self.company,
				"project": project,
				"supplier": self.supplier,
				"litres": 100,
				"card_equipment": equipment,
			}
		).insert()

	def _moved(self, rule):
		self._rule(rule)
		proj_a, proj_b = self._project("A"), self._project("B")
		eq = self._equipment(current_project=proj_a).name
		self._assign(eq, proj_a, 1)
		self._transport(eq, proj_b, 10)
		return eq, proj_a, proj_b

	def _assert_day(self, eq, day, allowed, refused):
		self._fill(allowed, day, eq)
		with self.assertRaisesRegex(frappe.ValidationError, MESSAGE):
			self._fill(refused, day, eq)

	def test_next_day_rule_keeps_the_move_day_on_the_old_project(self):
		eq, proj_a, proj_b = self._moved(MOVE_DAY_NEXT)
		self._assert_day(eq, self._d(10), allowed=proj_a, refused=proj_b)
		self._assert_day(eq, add_days(self._d(10), 1), allowed=proj_b, refused=proj_a)

	def test_move_day_rule_gives_the_move_day_to_the_new_project(self):
		eq, proj_a, proj_b = self._moved(MOVE_DAY_SAME)
		self._assert_day(eq, self._d(9), allowed=proj_a, refused=proj_b)
		self._assert_day(eq, self._d(10), allowed=proj_b, refused=proj_a)
