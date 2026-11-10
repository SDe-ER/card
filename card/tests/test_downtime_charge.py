# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-134 (#45, C-07): the explicit, audited route to charge for downtime, and FR-020 retired.

Proven here: an adjustment type is not a downtime charge by default; a card row of a type
flagged ``is_downtime_charge`` must name an enabled stop reason of the card's company, the
responsible party and the agreement reference; other rows keep their behaviour; the charge
is an ordinary addition on its side; a charge whose reason is also billable on the days is
flagged for review; Card Equipment ``min_hours`` stays in the schema but is hidden, read only
and labelled as not used. All data is per-test and rolled back."""

import frappe
from frappe.utils import flt

from card.constants import DIR_SUBRENTAL
from card.tests.test_s3_config import _AdjBase

CLIENT_STOP = "توقف من العميل"
ADDITION = "إضافة"


class _DowntimeBase(_AdjBase):
	def setUp(self):
		super().setUp()
		self._clear_types()
		self.charge_type = "Downtime-" + self.token
		self.plain_type = "Mobilization-" + self.token
		self._add_type(self.charge_type, kind=ADDITION)
		self._add_type(self.plain_type, kind=ADDITION)
		s = frappe.get_doc("Card Settings")
		for row in s.adjustment_types:
			if row.type_name == self.charge_type:
				row.is_downtime_charge = 1
		s.save(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _reason(self, company=None, enabled=1, billable=0):
		return frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": company or self.company,
				"reason_name": "TEST-DTC-" + frappe.generate_hash(length=6),
				"enabled": enabled,
				"billable": billable,
				"billable_approval_reason": "TEST approval" if billable else None,
			}
		).insert(ignore_permissions=True)

	def _card(self, eq, adjustments, days=None):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for i, values in enumerate(days or [{"working_hours": 8}, {"working_hours": 8}], start=1):
			row = {"operation_date": "2026-09-%02d" % i, "day_status": "عمل", "working_hours": 0}
			row.update(values)
			c.append("days", row)
		for r in adjustments:
			c.append("adjustments", r)
		c.insert(ignore_permissions=True)
		c.reload()
		return c

	def _charge(self, reason=None, **kw):
		row = {
			"adjustment_type_ref": self.charge_type,
			"description": "Standby charge",
			"amount": 500,
			"stop_reason": reason,
			"responsible_party_type": "Customer",
			"responsible_party": self.customer,
			"agreement_reference": "AGR-" + self.token,
		}
		row.update(kw)
		return row


class TestDowntimeChargeDefaults(_DowntimeBase):
	def test_flag_is_off_by_default(self):
		self._add_type("Other-" + self.token, kind=ADDITION)
		row = [
			t
			for t in frappe.get_doc("Card Settings").adjustment_types
			if t.type_name == "Other-" + self.token
		]
		self.assertEqual(row[0].is_downtime_charge, 0)

	def test_plain_typed_and_legacy_rows_need_no_downtime_fields(self):
		eq = self._equipment()
		card = self._card(
			eq,
			[
				{"adjustment_type_ref": self.plain_type, "description": "Mob", "amount": 100},
				{"adjustment_type": ADDITION, "description": "legacy", "amount": 50},
			],
		)
		self.assertEqual(flt(card.total_additions), 150)
		self.assertEqual(flt(card.net_amount), 16 * 75.0 + 150)


class TestDowntimeChargeRules(_DowntimeBase):
	def test_complete_downtime_charge_is_an_addition_on_its_side(self):
		eq = self._sub_rental()
		reason = self._reason()
		card = self._card(eq, [self._charge(reason.name, side="Customer")])
		row = card.adjustments[0]
		self.assertEqual(row.adjustment_type, ADDITION)
		self.assertEqual(row.stop_reason, reason.name)
		self.assertEqual(row.agreement_reference, "AGR-" + self.token)
		self.assertEqual(flt(card.customer_net_amount), 16 * 120.0 + 500)
		self.assertEqual(flt(card.net_amount), 16 * 75.0)
		# the downtime itself bills nothing: the charge is the only route
		self.assertEqual(flt(card.billable_stopped_hours), 0)

	def test_missing_stop_reason_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "needs"):
			self._card(self._equipment(), [self._charge(None)])

	def test_missing_agreement_reference_is_refused(self):
		reason = self._reason()
		with self.assertRaisesRegex(frappe.ValidationError, "needs"):
			self._card(self._equipment(), [self._charge(reason.name, agreement_reference="  ")])

	def test_missing_responsible_party_is_refused(self):
		reason = self._reason()
		with self.assertRaisesRegex(frappe.ValidationError, "needs"):
			self._card(
				self._equipment(),
				[self._charge(reason.name, responsible_party_type=None, responsible_party=None)],
			)
		with self.assertRaisesRegex(frappe.ValidationError, "needs"):
			self._card(
				self._equipment(),
				[self._charge(reason.name, responsible_party_type="Supplier", responsible_party=None)],
			)
		with self.assertRaisesRegex(frappe.ValidationError, "needs"):
			self._card(
				self._equipment(),
				[self._charge(reason.name, responsible_party_type="Other", responsible_party=None)],
			)

	def test_company_and_other_party_are_normalised(self):
		reason = self._reason()
		card = self._card(
			self._equipment(),
			[
				self._charge(reason.name, responsible_party_type="Company", responsible_party=None),
				self._charge(
					reason.name,
					responsible_party_type="Other",
					responsible_party=None,
					responsible_party_name="Port authority",
				),
			],
		)
		self.assertEqual(card.adjustments[0].responsible_party, self.company)
		self.assertEqual(card.adjustments[1].responsible_party_name, "Port authority")
		self.assertFalse(card.adjustments[1].responsible_party)

	def test_reason_of_another_company_is_refused(self):
		other = self._other_company()
		reason = self._reason(company=other)
		with self.assertRaises(frappe.PermissionError):
			self._card(self._equipment(), [self._charge(reason.name)])
		# also on a row that is not a downtime charge
		with self.assertRaises(frappe.PermissionError):
			self._card(
				self._equipment(),
				[
					{
						"adjustment_type_ref": self.plain_type,
						"description": "Mob",
						"amount": 100,
						"stop_reason": reason.name,
					}
				],
			)

	def test_disabled_reason_is_refused(self):
		reason = self._reason(enabled=0)
		with self.assertRaisesRegex(frappe.ValidationError, "disabled"):
			self._card(self._equipment(), [self._charge(reason.name)])

	def test_charge_on_a_billable_reason_is_flagged_not_blocked(self):
		eq = self._equipment()
		reason = self._reason(billable=1)
		frappe.clear_messages()
		card = self._card(
			eq,
			[self._charge(reason.name, responsible_party_type="Company", responsible_party=None)],
			days=[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
		)
		self.assertTrue(card.name)
		messages = " ".join(str(m) for m in frappe.message_log)
		self.assertIn("charged twice", messages)

	def test_sub_rental_charge_still_needs_a_side(self):
		eq = self._equipment(direction=DIR_SUBRENTAL, customer=self.customer, customer_rate=1200)
		reason = self._reason()
		with self.assertRaisesRegex(frappe.ValidationError, "choose the side"):
			self._card(eq, [self._charge(reason.name)])

	def _other_company(self):
		name = "TEST-DTC-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "D" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name


class TestMinHoursRetired(_DowntimeBase):
	def test_min_hours_is_hidden_read_only_and_labelled_not_used(self):
		field = frappe.get_meta("Card Equipment").get_field("min_hours")
		self.assertIsNotNone(field, "the column is kept")
		self.assertEqual(field.hidden, 1)
		self.assertEqual(field.read_only, 1)
		self.assertEqual(field.label, "Deprecated – not used")
