# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-122 (#42, #120): an ended Card Equipment (status منتهية) gets no NEW assignment, transport or
monthly card. Per company (Card Company Settings `equipment_status_rule`): Warn, the default and
the value when the company has no row, shows a message and saves; Enforce refuses. Existing
records are never changed or blocked. Data is per test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase

from card.constants import EQUIPMENT_STATUS_ENDED, STATUS_RULE_ENFORCE, STATUS_RULE_WARN
from card.equipment_status import BLOCKED_STATUSES, status_rule
from card.tests import test_transfer as _transfer
from card.tests import test_transport_company_rules as _tcr
from card.tests.test_controllers import _ensure_masters


class TestEquipmentStatusGuard(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	setUp = _transfer.TestEquipmentTransfer.setUp
	tearDown = _transfer.TestEquipmentTransfer.tearDown
	_d = _transfer.TestEquipmentTransfer._d
	_project = _transfer.TestEquipmentTransfer._project
	_equipment = _transfer.TestEquipmentTransfer._equipment
	_assign = _transfer.TestEquipmentTransfer._assign
	_transport = _transfer.TestEquipmentTransfer._transport
	_card = _transfer.TestEquipmentTransfer._card
	_refused = _transfer.TestEquipmentTransfer._refused
	_company_row = _tcr.TestTransportCompanyRules._company_row
	_other_company = _tcr.TestTransportCompanyRules._other_company

	# ---- helpers ----
	def _rule(self, value, company=None):
		self._company_row(company, equipment_status_rule=value)

	def _end(self, equipment, status=EQUIPMENT_STATUS_ENDED):
		frappe.db.set_value("Card Equipment", equipment, "status", status)

	def _ended_equipment(self):
		eq = self._equipment().name
		self._end(eq)
		return eq

	def _clear_messages(self):
		frappe.local.message_log = []

	def _warned(self, text):
		return any(text in str(m) for m in frappe.local.message_log or [])

	# ---- the setting ----
	def test_settings_field_and_default(self):
		field = frappe.get_meta("Card Company Settings").get_field("equipment_status_rule")
		self.assertEqual(field.options.split("\n"), [STATUS_RULE_WARN, STATUS_RULE_ENFORCE])
		self.assertEqual(field.default, STATUS_RULE_WARN)
		self.assertEqual(BLOCKED_STATUSES, (EQUIPMENT_STATUS_ENDED,))

	def test_default_is_warn_for_an_empty_value_and_for_a_company_without_a_row(self):
		self._rule(None)
		self.assertEqual(status_rule(self.company), STATUS_RULE_WARN)
		self.assertEqual(status_rule(self._other_company()), STATUS_RULE_WARN)
		self.assertEqual(status_rule(None), STATUS_RULE_WARN)

	# ---- Warn (default) ----
	def test_default_warns_and_saves_a_new_assignment(self):
		self._rule(None)
		eq = self._ended_equipment()
		self._clear_messages()
		a = self._assign(eq, self._project("A"), 1)
		self.assertTrue(frappe.db.exists("Card Equipment Assignment", a.name))
		self.assertTrue(self._warned("no new assignment"))

	def test_warn_saves_a_new_transport_and_a_new_monthly_card(self):
		self._rule(STATUS_RULE_WARN)
		proj = self._project("A")
		eq = self._equipment().name
		self._assign(eq, proj, 1)
		self._end(eq)
		self._clear_messages()
		card = self._card(eq, proj, [3, 4])
		card.insert(ignore_permissions=True)
		self.assertTrue(self._warned("no new monthly card"))
		self._clear_messages()
		t = self._transport(eq, self._project("B"), 10, submit=False)
		self.assertTrue(frappe.db.exists("Equipment Transport", t.name))
		self.assertTrue(self._warned("no new transport"))

	# ---- Enforce ----
	def test_enforce_refuses_a_new_assignment(self):
		self._rule(STATUS_RULE_ENFORCE)
		eq = self._ended_equipment()
		proj = self._project("A")
		self._refused(lambda: self._assign(eq, proj, 1))
		self.assertFalse(frappe.db.exists("Card Equipment Assignment", {"equipment": eq}))

	def test_enforce_refuses_a_new_transport(self):
		self._rule(STATUS_RULE_ENFORCE)
		eq = self._ended_equipment()
		proj = self._project("A")
		self._refused(lambda: self._transport(eq, proj, 10, submit=False))

	def test_enforce_refuses_a_new_monthly_card(self):
		proj = self._project("A")
		eq = self._equipment().name
		self._assign(eq, proj, 1)
		self._end(eq)
		self._rule(STATUS_RULE_ENFORCE)
		self._refused(lambda: self._card(eq, proj, [3]).insert(ignore_permissions=True))

	def test_enforce_allows_active_stopped_and_maintenance_equipment(self):
		self._rule(STATUS_RULE_ENFORCE)
		for status in ("نشطة", "متوقفة", "في الصيانة"):
			with self.subTest(status=status):
				eq = self._equipment().name
				self._end(eq, status)
				self._clear_messages()
				self._assign(eq, self._project("S" + str(len(status))), 1)
				self.assertFalse(self._warned("has status"))

	def test_enforce_never_blocks_existing_records(self):
		proj = self._project("A")
		eq = self._equipment().name
		a = self._assign(eq, proj, 1)
		card = self._card(eq, proj, [3])
		card.insert(ignore_permissions=True)
		self._end(eq)
		self._rule(STATUS_RULE_ENFORCE)
		# a later save of an existing assignment or draft card is not a new use
		a.reload()
		a.to_date = self._d(20)
		a.save(ignore_permissions=True)
		card.reload()
		card.append("days", {"operation_date": self._d(4), "day_status": "عمل", "working_hours": 8})
		card.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq, "status"), EQUIPMENT_STATUS_ENDED)

	def test_a_transport_saved_before_the_status_change_still_applies(self):
		# the assignment a transport makes is checked through its transport, not again
		eq = self._equipment().name
		proj = self._project("A")
		t = self._transport(eq, proj, 10, submit=False)
		self._end(eq)
		self._rule(STATUS_RULE_ENFORCE)
		t.reload()
		t.submit()
		self.assertTrue(frappe.db.exists("Card Equipment Assignment", {"equipment": eq, "project": proj}))

	def test_a_return_to_the_supplier_is_never_stopped(self):
		self._rule(STATUS_RULE_ENFORCE)
		eq = self._ended_equipment()
		t = frappe.new_doc("Equipment Transport")
		t.update({"company": self.company, "destination_type": "Supplier"})
		t.append("items", {"card_equipment": eq})
		t._check_equipment_status()  # no error

	def test_the_rule_is_per_company(self):
		other = self._other_company()
		self._rule(STATUS_RULE_ENFORCE, other)
		self._rule(None)
		self.assertEqual(status_rule(other), STATUS_RULE_ENFORCE)
		eq = self._ended_equipment()
		self._clear_messages()
		self._assign(eq, self._project("A"), 1)  # this company warns only
		self.assertTrue(self._warned("no new assignment"))
