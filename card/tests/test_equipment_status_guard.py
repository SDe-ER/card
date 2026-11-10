# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-122 (#42, #120): an ended Card Equipment (status منتهية) gets no NEW assignment, transport or
monthly card. Per company (Card Company Settings `equipment_status_rule`): "Warn only", the default
and the value when the company has no row, shows a message and saves; "Refuse" stops it. A transport
is checked again on submit. Never stopped: a return to the supplier, an owned machine moved to
storage or a workshop, a monthly card whose period starts on or before the exit date. Existing
records are never changed. Data is per test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from card.constants import EQUIPMENT_STATUS_ENDED, STATUS_RULE_ENFORCE, STATUS_RULE_WARN
from card.equipment_status import BLOCKED_STATUSES, check_equipment_status, status_rule
from card.tests import test_transfer as _transfer
from card.tests import test_transport_company_rules as _tcr
from card.tests.test_controllers import _ensure_masters
from card.tests.transport_parties import company_paid, paid_by

RENTED = "إيجار"


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
	_company_row = _tcr.TestTransportCompanyRules._company_row
	_other_company = _tcr.TestTransportCompanyRules._other_company
	_place = _tcr.TestTransportCompanyRules._place

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

	def _refused(self, action, text="has status"):
		# a refused write leaves its rows in the test transaction (a request rolls back)
		frappe.db.savepoint("card_refused")
		with self.assertRaisesRegex(frappe.ValidationError, text):
			action()
		frappe.db.rollback(save_point="card_refused")

	def _draft(self, equipment, destination="Project", project=None, day=10):
		"""A draft transport of one machine (company paid)."""
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"company": self.company,
				"date": self._d(day),
				"destination_type": destination,
				"project": project if destination == "Project" else None,
			}
		)
		if destination in ("Workshop", "Storage"):
			# as test_transfer._move: no charge for the company, so no place cost center is needed
			t.destination_location = self._place(destination.upper())
			paid_by(t, "Equipment Supplier", "Equipment Supplier")
		else:
			t.transport_supplier, t.amount = self.supplier, 100
			company_paid(t)
		t.append("items", {"card_equipment": equipment})
		t.insert(ignore_permissions=True)
		return t

	def _on_project(self, label="A", rented=False):
		"""An active machine (owned, or rented from the test supplier) assigned to a project, then
		ended: (equipment, project)."""
		proj = self._project(label)
		kw = {"ownership": RENTED, "supplier": self.supplier} if rented else {}
		eq = self._equipment(**kw).name
		self._assign(eq, proj, 1)
		self._end(eq)
		return eq, proj

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
		eq, proj = self._on_project()
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
		self._refused(lambda: self._assign(eq, proj, 1), "no new assignment")
		self.assertFalse(frappe.db.exists("Card Equipment Assignment", {"equipment": eq}))

	def test_enforce_refuses_a_new_transport(self):
		self._rule(STATUS_RULE_ENFORCE)
		eq = self._ended_equipment()
		proj = self._project("A")
		self._refused(lambda: self._transport(eq, proj, 10, submit=False), "no new transport")

	def test_enforce_refuses_a_new_monthly_card_without_an_end_date(self):
		eq, proj = self._on_project()
		self._rule(STATUS_RULE_ENFORCE)
		self._refused(
			lambda: self._card(eq, proj, [3]).insert(ignore_permissions=True), "no new monthly card"
		)

	def test_the_card_of_the_exit_month_is_allowed_a_later_one_refused(self):
		self._rule(STATUS_RULE_ENFORCE)
		# exit inside the card month: the final partial month is its last work
		eq, proj = self._on_project("EXIT")
		frappe.db.set_value("Card Equipment", eq, "exit_date", self._d(15))
		self._clear_messages()
		self._card(eq, proj, [3]).insert(ignore_permissions=True)
		self.assertFalse(self._warned("has status"))
		# exit before the card month: a new use, refused
		eq2, proj2 = self._on_project("GONE")
		frappe.db.set_value("Card Equipment", eq2, "exit_date", add_days(self._d(1), -1))
		self._refused(
			lambda: self._card(eq2, proj2, [3]).insert(ignore_permissions=True), "no new monthly card"
		)

	def test_without_an_exit_date_only_a_passed_rental_end_allows_the_final_month(self):
		self._rule(STATUS_RULE_ENFORCE)
		# rental end inside the card month and already passed: the final partial month is allowed
		eq, proj = self._on_project("RPAST")
		frappe.db.set_value("Card Equipment", eq, {"exit_date": None, "rental_end_date": self._d(15)})
		self._clear_messages()
		self._card(eq, proj, [3]).insert(ignore_permissions=True)
		self.assertFalse(self._warned("has status"))
		# rental end still ahead (a contract end, not an exit): no allowance, refused
		eq2, proj2 = self._on_project("RFUT")
		frappe.db.set_value(
			"Card Equipment", eq2, {"exit_date": None, "rental_end_date": add_days(nowdate(), 365)}
		)
		self._refused(
			lambda: self._card(eq2, proj2, [3]).insert(ignore_permissions=True), "no new monthly card"
		)

	def test_the_exit_date_wins_over_the_rental_end(self):
		self._rule(STATUS_RULE_ENFORCE)
		# exit before the card month, rental end far ahead: refused (the exit date decides)
		eq, proj = self._on_project("EXWIN")
		frappe.db.set_value(
			"Card Equipment",
			eq,
			{"exit_date": add_days(self._d(1), -1), "rental_end_date": add_days(nowdate(), 365)},
		)
		self._refused(
			lambda: self._card(eq, proj, [3]).insert(ignore_permissions=True), "no new monthly card"
		)

	def test_a_card_of_another_company_fails_on_the_company_not_the_status(self):
		self._rule(STATUS_RULE_ENFORCE)
		eq, proj = self._on_project("CO")
		card = self._card(eq, proj, [3])
		card.company = self._other_company()
		frappe.db.savepoint("card_refused")
		with self.assertRaises(frappe.ValidationError) as ctx:
			card.insert(ignore_permissions=True)
		frappe.db.rollback(save_point="card_refused")
		self.assertIn("does not match the equipment's company", str(ctx.exception))
		self.assertNotIn("has status", str(ctx.exception))

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

	def test_changing_the_equipment_of_an_assignment_or_card_is_a_new_use(self):
		proj = self._project("A")
		active = self._equipment().name
		ended, _proj = self._on_project("B")
		a = self._assign(active, proj, 1)
		card = self._card(active, proj, [3])
		card.insert(ignore_permissions=True)
		self._rule(STATUS_RULE_ENFORCE)
		a.reload()
		a.equipment = ended
		self._refused(lambda: a.save(ignore_permissions=True), "no new assignment")
		frappe.db.set_value("Card Equipment Assignment", {"equipment": ended}, "project", proj)
		card.reload()
		card.equipment = ended
		self._refused(lambda: card.save(ignore_permissions=True), "no new monthly card")

	# ---- transports: submit, destination change, added rows ----
	def test_a_transport_drafted_before_the_status_change_is_checked_on_submit(self):
		eq = self._equipment().name
		proj = self._project("A")
		t = self._transport(eq, proj, 10, submit=False)
		self._end(eq)
		self._rule(STATUS_RULE_ENFORCE)
		t.reload()
		self._refused(t.submit, "no new transport")
		self.assertFalse(frappe.db.exists("Card Equipment Assignment", {"equipment": eq, "project": proj}))
		# Warn only: the submit goes through with a message, and the move applies
		self._rule(STATUS_RULE_WARN)
		t.reload()
		self._clear_messages()
		t.submit()
		self.assertTrue(self._warned("no new transport"))
		self.assertTrue(frappe.db.exists("Card Equipment Assignment", {"equipment": eq, "project": proj}))

	def test_a_supplier_draft_switched_to_a_project_is_refused(self):
		eq, _proj = self._on_project(rented=True)
		self._rule(STATUS_RULE_ENFORCE)
		t = self._draft(eq, "Supplier")  # a return to the supplier is never stopped
		t.reload()
		t.destination_type, t.project = "Project", self._project("B")
		self._refused(lambda: t.save(ignore_permissions=True), "no new transport")
		# the submit checks every machine again even if the draft had been switched unchecked
		frappe.db.set_value(
			"Equipment Transport", t.name, {"destination_type": "Project", "project": t.project}
		)
		t.reload()
		self._refused(t.submit, "no new transport")

	def test_a_return_to_the_supplier_is_saved_and_submitted(self):
		eq, _proj = self._on_project(rented=True)
		self._rule(STATUS_RULE_ENFORCE)
		self._clear_messages()
		t = self._draft(eq, "Supplier")
		t.submit()
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "docstatus"), 1)
		self.assertFalse(self._warned("has status"))

	def test_an_owned_machine_moved_to_storage_or_a_workshop_is_never_stopped(self):
		self._rule(STATUS_RULE_ENFORCE)
		for destination in ("Storage", "Workshop"):
			with self.subTest(destination=destination):
				eq, _proj = self._on_project(destination[:3])
				self._clear_messages()
				t = self._draft(eq, destination)
				t.submit()
				self.assertFalse(self._warned("has status"))

	def test_a_rented_machine_moved_to_storage_or_a_workshop_is_refused(self):
		# only an owned machine is retired through storage or a workshop; a rented one returns to its supplier
		self._rule(STATUS_RULE_ENFORCE)
		for destination in ("Storage", "Workshop"):
			with self.subTest(destination=destination):
				eq, _proj = self._on_project("R" + destination[:3], rented=True)
				self._refused(lambda eq=eq, d=destination: self._draft(eq, d), "no new transport")

	def test_a_row_added_to_an_existing_draft_is_checked(self):
		active = self._equipment().name
		proj = self._project("A")
		t = self._transport(active, proj, 10, submit=False)
		ended = self._ended_equipment()
		self._rule(STATUS_RULE_ENFORCE)
		t.reload()
		t.append("items", {"card_equipment": ended})
		self._refused(lambda: t.save(ignore_permissions=True), "no new transport")

	# ---- per company ----
	def test_the_rule_is_per_company(self):
		other = self._other_company()
		self._rule(STATUS_RULE_ENFORCE, other)
		self._rule(None)
		self.assertEqual(status_rule(other), STATUS_RULE_ENFORCE)
		eq = self._ended_equipment()
		self._clear_messages()
		self._assign(eq, self._project("A"), 1)  # this company warns only
		self.assertTrue(self._warned("no new assignment"))
		# the other company's rule refuses
		with self.assertRaisesRegex(frappe.ValidationError, "refuses it"):
			check_equipment_status(eq, "assignment", company=other)
