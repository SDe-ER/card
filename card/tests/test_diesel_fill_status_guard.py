# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-128 (#124, #42): an ended Card Equipment (status منتهية) gets no NEW Project Diesel Fill, by the
FR-122 rule of card.equipment_status (Card Company Settings `equipment_status_rule`: Warn only, the
default and the value when empty; Refuse). The direct-charge equipment and every listed equipment
are checked on a new fill, on a changed company or date (all) and for an equipment added to a draft;
an unchanged saved draft is not checked again on save, and every equipment is checked again on
submit, as a transport. A fill dated on or before the equipment's exit date (else its rental end,
once passed) is its last work: never stopped. An amendment is a new fill and is checked (an ended
equipment without an exit date is refused under Refuse; set its exit date). Another company's
equipment fails on the company match before its status is read. Data is per test and rolled back."""

import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from card.card.doctype.project_diesel_fill.project_diesel_fill import PROJECT_CHECK_OFF
from card.constants import EQUIPMENT_STATUS_ENDED, STATUS_RULE_ENFORCE, STATUS_RULE_WARN
from card.tests.cancel_reason import with_reason
from card.tests.diesel_price import approve_fill
from card.tests.test_controllers import _ensure_masters
from card.tests.test_diesel_fill_project_check import TestDieselFillProjectCheck, prepare_fill_settings
from card.tests.test_diesel_fill_project_check import set_mode as set_project_check

MESSAGE = "no new diesel fill"
DAY = "2026-09-15"


def set_rule(company, value):
	frappe.db.set_value(
		"Card Company Settings",
		{"parent": "Card Settings", "parentfield": "company_settings", "company": company},
		"equipment_status_rule",
		value,
	)


def messages(text=MESSAGE):
	return sum(
		text in str(m.get("message") if isinstance(m, dict) else m) for m in frappe.local.message_log or []
	)


def warned(text=MESSAGE):
	return any(
		text in str(m.get("message") if isinstance(m, dict) else m) for m in frappe.local.message_log or []
	)


class TestDieselFillStatusGuard(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.company = self._m["company"]
		prepare_fill_settings(self.company)
		set_project_check(self.company, PROJECT_CHECK_OFF)  # FR-126 apart: only the status guard speaks
		set_rule(self.company, None)  # never configured: the default applies
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-DFSG-PRJ-" + frappe.generate_hash(length=8),
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DFSG-SUP-" + frappe.generate_hash(length=8)
		sup.supplier_group = self._m["supplier_group"]
		self.supplier = sup.insert(ignore_permissions=True).name
		frappe.clear_messages()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- helpers ----------

	_company = TestDieselFillProjectCheck._company  # another company with a diesel price row

	def _project(self, company):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-DFSG-PRJ-" + frappe.generate_hash(length=8),
					"company": company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _equipment(self, ended=False, company=None, **values):
		d = frappe.new_doc("Card Equipment")
		d.company = company or self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "ملك"
		d.equipment_name = "TEST-DFSG-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		name = d.insert(ignore_permissions=True).name
		if ended:
			self._end(name, **values)
		return name

	def _end(self, equipment, **values):
		frappe.db.set_value("Card Equipment", equipment, {"status": EQUIPMENT_STATUS_ENDED, **values})

	def _fill(self, date=DAY, equipment=None, listed=None):
		data = {
			"doctype": "Project Diesel Fill",
			"date": date,
			"company": self.company,
			"project": self.project,
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

	def _refused(self, action, text=MESSAGE):
		frappe.db.savepoint("card_refused")
		with self.assertRaisesRegex(frappe.ValidationError, text):
			action()
		frappe.db.rollback(save_point="card_refused")

	# ---------- default and Warn only ----------

	def test_default_warns_and_saves(self):
		eq = self._equipment(ended=True)
		f = self._fill(equipment=eq)
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(warned())

	def test_warn_saves_direct_and_listed_with_a_message(self):
		set_rule(self.company, STATUS_RULE_WARN)
		f = self._fill(equipment=self._equipment(ended=True))
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(warned())
		frappe.clear_messages()
		f = self._fill(listed=[self._equipment(), self._equipment(ended=True)])
		self.assertTrue(frappe.db.exists("Project Diesel Fill", f.name))
		self.assertTrue(warned())

	def test_active_stopped_and_maintenance_equipment_get_no_message(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		for status in ("نشطة", "متوقفة", "في الصيانة"):
			with self.subTest(status=status):
				eq = self._equipment()
				frappe.db.set_value("Card Equipment", eq, "status", status)
				self._fill(equipment=eq)
				self.assertFalse(warned("has status"))

	def test_project_tank_fill_without_equipment_is_not_checked(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		self._fill()
		self.assertFalse(warned("has status"))

	# ---------- Refuse ----------

	def test_refuse_a_direct_charge_equipment(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		eq = self._equipment(ended=True)
		self._refused(lambda: self._fill(equipment=eq))
		self.assertFalse(frappe.db.exists("Project Diesel Fill", {"card_equipment": eq}))

	def test_refuse_checks_every_listed_equipment(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		active, ended = self._equipment(), self._equipment(ended=True)
		self._refused(lambda: self._fill(listed=[active, ended]), re.escape(ended))
		self._fill(listed=[active])

	def test_refuse_names_the_company_rule(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		eq = self._equipment(ended=True)
		self._refused(
			lambda: self._fill(equipment=eq), "equipment status rule of company " + re.escape(self.company)
		)

	# ---------- changed and unchanged fills ----------

	def test_a_changed_equipment_is_checked(self):
		f = self._fill(equipment=self._equipment())
		set_rule(self.company, STATUS_RULE_ENFORCE)
		f.reload()
		f.card_equipment = self._equipment(ended=True)
		self._refused(f.save)
		# a listed equipment added to a draft is checked too
		g = self._fill(listed=[self._equipment()])
		g.reload()
		ended = self._equipment(ended=True)
		g.append(
			"equipment_filled", {"card_equipment": ended, "match_status": "Matched", "reported_name": ended}
		)
		self._refused(g.save, re.escape(ended))

	def test_a_changed_date_rechecks_every_equipment(self):
		eq = self._equipment(ended=True)
		f = self._fill(equipment=eq)  # Warn (default): saved with a message
		set_rule(self.company, STATUS_RULE_ENFORCE)
		f.reload()
		f.date = "2026-09-16"
		self._refused(f.save)

	def test_an_unchanged_saved_fill_is_not_checked_again_on_save(self):
		f = self._fill(equipment=self._equipment(ended=True))  # Warn: saved
		set_rule(self.company, STATUS_RULE_ENFORCE)
		frappe.clear_messages()
		f.reload()
		f.remarks = "edited"
		f.save()  # company, date and equipment unchanged: not a new use
		self.assertFalse(warned())

	def test_submit_checks_every_equipment_again(self):
		eq = self._equipment()
		f = self._fill(equipment=eq)
		approve_fill(f)
		self._end(eq)  # ended after the draft was saved
		set_rule(self.company, STATUS_RULE_ENFORCE)
		f.reload()
		self._refused(f.submit)
		self.assertEqual(frappe.db.get_value("Project Diesel Fill", f.name, "docstatus"), 0)
		# Warn only: the submit goes through with a message
		set_rule(self.company, STATUS_RULE_WARN)
		f.reload()
		frappe.clear_messages()
		f.submit()
		self.assertTrue(warned())
		self.assertEqual(frappe.db.get_value("Project Diesel Fill", f.name, "docstatus"), 1)

	# ---------- final-day allowance (card.equipment_status._last_work_day) ----------

	def test_a_fill_on_or_before_the_exit_date_is_allowed_a_later_one_refused(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		eq = self._equipment(ended=True, exit_date=DAY)
		for date in (add_days(DAY, -1), DAY):
			with self.subTest(date=date):
				self._fill(date=date, equipment=eq)
				self.assertFalse(warned("has status"))
		self._refused(lambda: self._fill(date=add_days(DAY, 1), equipment=eq))

	def test_without_an_exit_date_only_a_passed_rental_end_allows_the_final_day(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		eq = self._equipment(ended=True, exit_date=None, rental_end_date=DAY)  # passed
		self._fill(date=DAY, equipment=eq)
		self._refused(lambda: self._fill(date=add_days(DAY, 1), equipment=eq))
		# a rental end still ahead is a contract end, not an exit: no allowance
		ahead = self._equipment(ended=True, exit_date=None, rental_end_date=add_days(nowdate(), 365))
		self._refused(lambda: self._fill(date=DAY, equipment=ahead))

	def test_the_exit_date_wins_over_the_rental_end(self):
		set_rule(self.company, STATUS_RULE_ENFORCE)
		eq = self._equipment(ended=True, exit_date=add_days(DAY, -1), rental_end_date=DAY)
		self._refused(lambda: self._fill(date=DAY, equipment=eq))

	# ---------- review notes (L1, L3) ----------

	def test_a_changed_company_rechecks_every_equipment(self):
		other = self._company()
		set_project_check(other, PROJECT_CHECK_OFF)
		set_rule(other, STATUS_RULE_ENFORCE)
		eq = self._equipment(ended=True)
		f = self._fill(equipment=eq)  # this company: Warn (default), saved
		# the same equipment record, now of the other company (only the company of the fill changes)
		frappe.db.set_value("Card Equipment", eq, "company", other)
		f.reload()
		f.company, f.project = other, self._project(other)
		self._refused(f.save, "equipment status rule of company " + re.escape(other))

	def test_an_amended_copy_is_checked(self):
		eq = self._equipment()
		f = self._fill(equipment=eq)
		approve_fill(f)
		f.submit()
		self._end(eq)  # ended after the submit, without an exit date
		set_rule(self.company, STATUS_RULE_ENFORCE)
		with_reason(f).cancel()

		def amend():
			a = frappe.copy_doc(f)
			a.amended_from, a.docstatus = f.name, 0
			return a.insert()

		self._refused(amend)
		# the workaround (consistent with FR-122): record the exit date; the fill day is its last work
		frappe.db.set_value("Card Equipment", eq, "exit_date", DAY)
		frappe.clear_messages()  # the refused attempt left its message
		a = amend()
		self.assertEqual(a.amended_from, f.name)
		self.assertFalse(warned())

	def test_another_companys_equipment_fails_on_the_company_not_the_status(self):
		other = self._company()
		set_rule(other, STATUS_RULE_ENFORCE)
		set_rule(self.company, STATUS_RULE_ENFORCE)
		foreign = self._equipment(ended=True, company=other)
		for kw in ({"equipment": foreign}, {"listed": [foreign]}):
			with self.subTest(**{k: str(v) for k, v in kw.items()}):
				frappe.db.savepoint("card_company_order")
				with self.assertRaises(frappe.ValidationError) as ctx:
					self._fill(**kw)
				frappe.db.rollback(save_point="card_company_order")
				self.assertIn("does not match the equipment's company", str(ctx.exception))
				self.assertNotIn("has status", str(ctx.exception))
				self.assertFalse(warned("has status"))

	def test_warn_shows_the_message_exactly_once(self):
		eq = self._equipment(ended=True)
		f = self._fill(equipment=eq)
		self.assertEqual(messages(), 1)
		# a submit whose validate would re-check (date changed) still shows it once: before_submit only
		approve_fill(f)
		f.reload()
		f.date = add_days(DAY, 1)
		frappe.clear_messages()
		f.submit()
		self.assertEqual(messages(), 1)
