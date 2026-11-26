# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-192 (#48): who pays the maintenance of an equipment, recorded on the equipment master.

Proven here: `Card Equipment.maintenance_on` is the same kind of field as "Fuel charged to"
(Select, the same two parties, the same permission level, no help text, empty by default, next to
"Operator charged to"); the label has an Arabic translation; an equipment saves with each party
and with no value; an unknown value is refused; Card Manager fills an empty field on a saved
equipment without a reason; a later change, also back to empty, is refused without a new reason;
a save by Card User does not change the field. All data is per-test and rolled back."""

import json
import os

import frappe

from card.tests.test_customer import RENTED, _CustomerCardsBase

FIELD = "maintenance_on"
FUEL_FIELD = "الوقود_على"
LESSOR = "المؤجر"
COMPANY = "الشركة"


def _doctype_json():
	path = os.path.join(
		frappe.get_app_path("card"), "card", "doctype", "card_equipment", "card_equipment.json"
	)
	with open(path, encoding="utf-8") as f:
		return json.load(f)


def _field(data, fieldname):
	return next((f for f in data["fields"] if f.get("fieldname") == fieldname), None)


class TestEquipmentMaintenancePayer(_CustomerCardsBase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _login(self, roles):
		email = f"mp-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Maintenance",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)

	def _value(self, eq):
		return frappe.db.get_value("Card Equipment", eq.name, FIELD) or ""

	def test_field_mirrors_the_fuel_field(self):
		data = _doctype_json()
		field = _field(data, FIELD)
		self.assertIsNotNone(field, "Card Equipment has no maintenance_on field")
		fuel = _field(data, FUEL_FIELD)
		self.assertEqual(field["fieldtype"], "Select")
		self.assertEqual(field["label"], "Maintenance charged to")
		self.assertEqual(field["options"], fuel["options"])
		self.assertEqual(field["options"], f"\n{LESSOR}\n{COMPANY}")
		self.assertEqual(field.get("permlevel"), fuel.get("permlevel"))
		for key in ("description", "default", "reqd", "depends_on", "mandatory_depends_on"):
			self.assertFalse(field.get(key), key)

	def test_field_sits_next_to_operator_charged_to(self):
		order = _doctype_json()["field_order"]
		self.assertIn(FIELD, order)
		self.assertEqual(order[order.index(FIELD) - 1], "operator_on")

	def test_label_has_an_arabic_translation(self):
		path = os.path.join(frappe.get_app_path("card"), "locale", "ar.po")
		with open(path, encoding="utf-8") as f:
			text = f.read()
		self.assertIn('msgid "Maintenance charged to"\nmsgstr "الصيانة على"\n', text)

	def test_equipment_saves_with_each_party_and_with_no_value(self):
		for value in (LESSOR, COMPANY, ""):
			eq = self._equipment(RENTED, **{FIELD: value})
			self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, FIELD) or "", value)

	def test_unknown_value_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(RENTED, **{FIELD: "Customer"})

	def test_card_manager_fills_an_empty_field_without_a_reason(self):
		eq = self._equipment(RENTED)
		self._login(["Card Manager"])
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.set(FIELD, LESSOR)
		doc.save()
		self.assertEqual(self._value(eq), LESSOR)

	def test_later_change_needs_a_new_reason(self):
		from card.card.doctype.card_equipment.card_equipment import COMMERCIAL_FIELDS

		self.assertIn(FIELD, COMMERCIAL_FIELDS)
		eq = self._equipment(RENTED, **{FIELD: LESSOR})
		self._login(["Card Manager"])
		for value in (COMPANY, ""):
			doc = frappe.get_doc("Card Equipment", eq.name)
			doc.set(FIELD, value)
			with self.assertRaises(frappe.ValidationError):
				doc.save()
			self.assertEqual(self._value(eq), LESSOR)
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.set(FIELD, COMPANY)
		doc.commercial_change_reason = "Maintenance terms changed"
		doc.save()
		self.assertEqual(self._value(eq), COMPANY)

	def test_card_user_cannot_change_the_field(self):
		eq = self._equipment(RENTED, **{FIELD: LESSOR})
		self._login(["Card User"])
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.set(FIELD, COMPANY)
		doc.commercial_change_reason = "Not allowed"
		try:
			doc.save()
		except (frappe.PermissionError, frappe.ValidationError):
			pass
		frappe.set_user("Administrator")
		self.assertEqual(self._value(eq), LESSOR)
