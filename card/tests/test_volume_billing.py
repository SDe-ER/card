# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Volume billing per m³ and per load (plan 2026-11-14, FR-166).

A customer side on the per-m³ basis ("بالمتر المكعب") bills loads x load volume (m³) x rate per m³
before VAT. The day rate is customer_rate, the night rate customer_rate_night. Hours are recorded but
not billed on this basis, and billable stops add nothing. The supplier side keeps its own rate basis.
Proven here: day and night amounts, zero-hour loads, the working-day rule, mandatory load volume,
permlevels, the submit snapshot, the period-run fingerprint, and unchanged hourly/daily/monthly
pricing. All data is per-test and rolled back."""

import frappe
from frappe.utils import flt

from card.card.report.equipment_customer_statement.equipment_customer_statement import (
	execute as customer_statement,
)
from card.constants import DIR_RENTED_OUT, DIR_SUBRENTAL, OWNED, SHIFT_NIGHT
from card.gl.period_run import document_fingerprint
from card.tests.test_customer import RENTED
from card.tests.test_stop_reasons import CLIENT_STOP, LEAVE, WORK, _StopBase

PER_M3 = "بالمتر المكعب"
LOAD_VOLUME = 16  # m³ per load (worked example: 40 loads x 16 m³ x 2 SAR = 1,280 SAR)


class TestVolumeBilling(_StopBase):
	def _volume_equipment(self, customer_rate=2, load_volume=LOAD_VOLUME, night_rate=None, **kw):
		"""A rented-out machine billed to the customer per m³ (day rate customer_rate)."""
		extra = {}
		if load_volume is not None:
			extra["load_volume_m3"] = load_volume
		if night_rate is not None:
			extra["customer_rate_night"] = night_rate
		return self._equipment(
			OWNED,
			direction=DIR_RENTED_OUT,
			customer=self.customer,
			customer_rate=customer_rate,
			customer_rate_type=PER_M3,
			**extra,
			**kw,
		)

	def _volume_card(self, eq, rows, shift="نهاري", submit=False):
		"""rows: dicts of day-row values; the day number is the position (1-based)."""
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = shift
		c.month = "09"
		c.year = 2026
		for i, values in enumerate(rows, start=1):
			row = {"operation_date": "2026-09-%02d" % i, "day_status": WORK, "working_hours": 0}
			row.update(values)
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	# ---- amounts ----
	def test_day_card_bills_loads_times_volume_times_rate(self):
		eq = self._volume_equipment()
		card = self._volume_card(
			eq,
			[{"loads_count": 25, "working_hours": 10}, {"loads_count": 15, "working_hours": 6}],
			submit=True,
		)
		self.assertEqual(card.total_loads, 40)
		self.assertEqual(flt(card.total_volume_m3), 640.0)
		self.assertEqual(flt(card.load_volume_used), 16.0)
		self.assertEqual(flt(card.customer_rate_used), 2.0)  # SAR per m³ for a per-m³ card
		self.assertEqual(flt(card.customer_amount), 1280.0)
		self.assertEqual(flt(card.customer_net_amount), 1280.0)
		self.assertEqual(flt(card.total_working_hours), 16)  # hours are still recorded

	def test_night_card_uses_customer_rate_night(self):
		eq = self._volume_equipment(customer_rate=2, night_rate=3)
		card = self._volume_card(
			eq, [{"loads_count": 40, "working_hours": 10}], shift=SHIFT_NIGHT, submit=True
		)
		self.assertEqual(flt(card.customer_rate_used), 3.0)
		self.assertEqual(flt(card.customer_amount), 40 * 16 * 3.0)  # 1,920

	def test_stopped_hours_add_nothing(self):
		eq = self._volume_equipment()
		reason = self._reason(billable=1)
		card = self._volume_card(
			eq,
			[
				{"loads_count": 40, "working_hours": 10},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 8},
			],
			submit=True,
		)
		self.assertEqual(flt(card.customer_amount), 1280.0)

	def test_loads_with_zero_hours_are_billed(self):
		eq = self._volume_equipment()
		card = self._volume_card(eq, [{"loads_count": 4, "working_hours": 0}], submit=True)
		self.assertEqual(card.total_loads, 4)
		self.assertEqual(flt(card.customer_amount), 128.0)

	def test_per_m3_supplier_side_keeps_its_own_rate(self):
		# Q2 (approved): per-m³ applies to the customer side only
		eq = self._equipment(
			RENTED,
			direction=DIR_SUBRENTAL,
			customer=self.customer,
			customer_rate=2,
			customer_rate_type=PER_M3,
			load_volume_m3=LOAD_VOLUME,
		)
		card = self._volume_card(
			eq,
			[
				{"loads_count": 40, "working_hours": 4},
				{"working_hours": 10},
				{"working_hours": 12},
			],
			submit=True,
		)
		self.assertEqual(flt(card.amount), 26 * 75.0)  # supplier: 750/day over 10 h, hourly as before
		self.assertEqual(flt(card.customer_amount), 1280.0)

	# ---- validation ----
	def test_loads_on_a_non_working_day_are_refused(self):
		eq = self._volume_equipment()
		with self.assertRaises(frappe.ValidationError):
			self._volume_card(eq, [{"day_status": LEAVE, "loads_count": 3}])

	def test_negative_loads_are_refused(self):
		eq = self._volume_equipment()
		with self.assertRaises(frappe.ValidationError):
			self._volume_card(eq, [{"loads_count": -1, "working_hours": 8}])

	def test_per_m3_equipment_needs_a_load_volume(self):
		with self.assertRaisesRegex(frappe.ValidationError, "(?i)load volume"):
			self._volume_equipment(load_volume=None)

	# ---- permissions and privacy ----
	def test_load_volume_is_a_commercial_field_at_permlevel_1(self):
		from card.card.doctype.card_equipment.card_equipment import COMMERCIAL_FIELDS

		self.assertIn("load_volume_m3", COMMERCIAL_FIELDS)
		self.assertEqual(frappe.get_meta("Card Equipment").get_field("load_volume_m3").permlevel, 1)

	def test_money_is_permlevel_1_and_volumes_are_not_money(self):
		from card.field_privacy import CARD_MONEY_FIELDS

		meta = frappe.get_meta("Card Monthly Card")
		self.assertEqual(meta.get_field("customer_amount").permlevel, 1)
		self.assertEqual(meta.get_field("customer_rate_used").permlevel, 1)
		self.assertEqual(meta.get_field("load_volume_used").permlevel, 1)
		self.assertEqual(meta.get_field("total_loads").permlevel, 0)
		self.assertEqual(meta.get_field("total_volume_m3").permlevel, 0)
		for name in ("load_volume_used", "total_loads", "total_volume_m3"):
			self.assertFalse(meta.get_field(name).allow_on_submit, name)
			self.assertNotIn(name, CARD_MONEY_FIELDS)

	# ---- submitted cards and period runs ----
	def test_submitted_card_is_not_repriced_by_an_equipment_change(self):
		eq = self._volume_equipment()
		card = self._volume_card(eq, [{"loads_count": 40, "working_hours": 10}], submit=True)
		eq.reload()
		eq.load_volume_m3 = 20
		eq.customer_rate = 5
		eq.commercial_change_reason = "TEST volume " + self.token
		eq.save(ignore_permissions=True)
		card.reload()
		self.assertEqual(flt(card.customer_amount), 1280.0)
		self.assertEqual(flt(card.load_volume_used), 16.0)
		self.assertEqual(flt(card.customer_rate_used), 2.0)

	def test_fingerprint_covers_customer_amount(self):
		eq = self._volume_equipment()
		card = self._volume_card(eq, [{"loads_count": 40, "working_hours": 10}], submit=True)
		fingerprint = document_fingerprint(card, 1)
		self.assertEqual(fingerprint, document_fingerprint(frappe.get_doc("Card Monthly Card", card.name), 1))
		card.customer_amount = flt(card.customer_amount) + 1
		self.assertNotEqual(fingerprint, document_fingerprint(card, 1))

	# ---- regression: existing bases unchanged (these pass on current code) ----
	def test_hourly_daily_and_monthly_customer_rates_are_unchanged(self):
		hourly = self._rented_out(customer_rate=100, customer_rate_type="بالساعة")
		self.assertEqual(flt(self._card(hourly, [4, 10, 12], submit=True).customer_amount), 2600.0)
		daily = self._rented_out(customer_rate=1000, customer_rate_type="باليوم")
		self.assertEqual(flt(self._card(daily, [4, 10, 12], submit=True).customer_amount), 2600.0)
		monthly = self._rented_out(customer_rate=26000, customer_rate_type="بالشهر")
		self.assertEqual(flt(self._card(monthly, [4, 10, 12], submit=True).customer_amount), 2600.0)

	# ---- customer statement: a per-m³ row shows loads, m³ and the rate per m³, never an hourly rate ----
	def test_statement_per_m3_rows_show_loads_volume_and_rate_not_hourly(self):
		eq = self._volume_equipment()
		card = self._volume_card(eq, [{"loads_count": 40, "working_hours": 10}], submit=True)
		filters = {
			"company": self.company,
			"customer": self.customer,
			"from_month": 9,
			"from_year": 2026,
			"project": self.project,
		}
		columns, rows, *_ = customer_statement(filters)
		self.assertIn("total_volume_m3", [c["fieldname"] for c in columns])
		row = next(r for r in rows if r.get("card") == card.name)
		self.assertEqual(row["customer_rate_type"], PER_M3)
		self.assertIsNone(row["hourly_rate"])
		self.assertEqual(row["total_loads"], 40)
		self.assertEqual(flt(row["total_volume_m3"]), 640.0)
		self.assertEqual(flt(row["customer_rate"]), 2.0)
		self.assertEqual(flt(row["customer_amount"]), 1280.0)
		equipment_row = next(r for r in rows if str(r.get("row_id", "")).endswith("|E|" + eq.name))
		self.assertIsNone(equipment_row["hourly_rate"])
		self.assertEqual(equipment_row["total_loads"], 40)

	# ---- print format, number cards and the CARD dashboard (plan step 7, D15) ----
	def test_print_format_shows_loads_and_volume_only_on_per_m3_cards(self):
		template = frappe.get_jenv().from_string(frappe.get_doc("Print Format", "كارت تشغيل شهري").html)
		card = self._volume_card(
			self._volume_equipment(), [{"loads_count": 40, "working_hours": 10}], submit=True
		)
		per_m3 = template.render({"doc": frappe.get_doc("Card Monthly Card", card.name), "letter_head": None})
		self.assertIn("Total loads", per_m3)
		self.assertIn("Total volume (m³)", per_m3)
		self.assertIn("640.00", per_m3)
		hourly = self._rented_out(customer_rate=100, customer_rate_type="بالساعة")
		hourly_card = self._card(hourly, [4, 10, 12], submit=True)
		plain = template.render(
			{"doc": frappe.get_doc("Card Monthly Card", hourly_card.name), "letter_head": None}
		)
		self.assertNotIn("Total loads", plain)
		self.assertNotIn("Total volume (m³)", plain)

	def test_number_cards_and_dashboard_show_loads_and_volume_last_month(self):
		import json

		from card.card_value import loads_last_month, volume_last_month

		for name, method in (
			("Loads last month", "card.card_value.loads_last_month"),
			("Volume last month (m³)", "card.card_value.volume_last_month"),
		):
			card = frappe.db.get_value("Number Card", name, ["method", "type", "function"], as_dict=True)
			self.assertIsNotNone(card, name)
			self.assertEqual(card.method, method)
			self.assertEqual(card.type, "Custom")
		with open(frappe.get_app_path("card", "fixtures", "workspace.json"), encoding="utf-8") as fh:
			dashboard = json.load(fh)[0]
		shown = {
			b["data"]["number_card_name"]
			for b in json.loads(dashboard["content"])
			if b["type"] == "number_card"
		}
		self.assertIn("Loads last month", shown)
		self.assertIn("Volume last month (m³)", shown)
		loads = loads_last_month({"company": self.company})
		self.assertEqual(loads["fieldtype"], "Int")
		self.assertEqual(loads["route"], ["List", "Card Monthly Card"])
		self.assertEqual(loads["route_options"]["customer_rate_type"], PER_M3)
		volume = volume_last_month({"company": self.company})
		self.assertEqual(volume["fieldtype"], "Float")
		self.assertGreaterEqual(flt(volume["value"]), 0)

	# ---- translation rule (FR-166): every new CARD msgid has a real translation in every locale ----
	def test_every_new_msgid_is_translated_in_every_locale(self):
		import glob
		import os
		import re

		new = [
			"Load volume (m³)",
			"Load volume (m³) is required for the per-m³ customer rate",
			"Load volume used (m³)",
			"Total loads",
			"Total volume (m³)",
			"Loads",
			"Negative loads on day {0}",
			"Loads can be recorded only on a working day: {0}",
			"Cannot record loads for a future day: {0}",
			"بالمتر المكعب",
			"Loads last month",
			"Volume last month (m³)",
		]
		locale_dir = os.path.join(frappe.get_app_path("card"), "locale")
		for path in glob.glob(os.path.join(locale_dir, "*.po")):
			name = os.path.basename(path)
			with open(path, encoding="utf-8") as fh:
				pairs = dict(re.findall(r'^msgid "(.*)"\nmsgstr "(.*)"$', fh.read(), re.M))
			for msgid in new:
				value = pairs.get(msgid)
				self.assertTrue(value, f"{name}: no translation for {msgid!r}")
				if "{0}" in msgid:
					self.assertIn("{0}", value, f"{name}: placeholder lost in {msgid!r}")
		with open(os.path.join(locale_dir, "main.pot"), encoding="utf-8") as fh:
			pot = dict(re.findall(r'^msgid "(.*)"\nmsgstr "(.*)"$', fh.read(), re.M))
		for msgid in new:
			self.assertTrue(pot.get(msgid), f"main.pot: no source for {msgid!r}")
