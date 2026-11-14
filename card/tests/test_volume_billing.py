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

	def _volume_card(self, eq, rows, shift="نهاري", submit=False, adjustments=None, ym=("09", 2026)):
		"""rows: dicts of day-row values; the day number is the position (1-based). ym: (month, year) of the card."""
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = shift
		c.month = ym[0]
		c.year = ym[1]
		for i, values in enumerate(rows, start=1):
			row = {"operation_date": "%s-%s-%02d" % (ym[1], ym[0], i), "day_status": WORK, "working_hours": 0}
			row.update(values)
			c.append("days", row)
		for adj in adjustments or []:
			c.append("adjustments", adj)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _interactive(self):
		"""The next save is an interactive form save (an HTTP request); restored after the test."""
		saved = getattr(frappe.local, "request", None)
		frappe.local.request = frappe._dict(method="POST")
		self.addCleanup(setattr, frappe.local, "request", saved)

	def _flag(self, name):
		saved = frappe.flags.get(name)
		frappe.flags[name] = True
		self.addCleanup(frappe.flags.__setitem__, name, saved)

	def _hours_then_cleared_loads_card(self):
		# day 1: hours with no loads; day 2: loads on a non-working day, cleared on save
		eq = self._volume_equipment()
		return self._volume_card(
			eq, [{"loads_count": 0, "working_hours": 10}, {"day_status": LEAVE, "loads_count": 3}]
		)

	def _assert_quiet_save(self):
		frappe.local.message_log = []
		card = self._hours_then_cleared_loads_card()
		self.assertEqual(card.days[1].loads_count, 0)  # the clearing still happens
		self.assertEqual(card.docstatus, 0)
		shown = " ".join(str(m) for m in frappe.local.message_log)
		self.assertNotIn("Loads were cleared on these non-working days", shown)
		self.assertNotIn("This card has operating hours but no loads", shown)

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
	def test_loads_are_cleared_when_the_day_becomes_a_non_working_day(self):
		# FR-166 (review F1): loads are zeroed with the hours on a non-working day; the save succeeds
		eq = self._volume_equipment()
		card = self._volume_card(eq, [{"loads_count": 3, "working_hours": 8}])
		card.days[0].day_status = LEAVE
		card.save(ignore_permissions=True)
		card.reload()
		self.assertEqual(card.days[0].loads_count, 0)
		self.assertEqual(card.total_loads, 0)
		self.assertEqual(flt(card.customer_amount), 0.0)

	def test_loads_on_a_new_non_working_day_are_zeroed_on_save(self):
		eq = self._volume_equipment()
		card = self._volume_card(eq, [{"day_status": LEAVE, "loads_count": 3}])
		self.assertEqual(card.days[0].loads_count, 0)
		self.assertEqual(card.total_loads, 0)

	def test_priced_volume_is_exact_before_rounding(self):
		# FR-166 (review F2): 7 x 1.2345 x 3 = 25.9245, rounded once to 25.92 (no intermediate rounding)
		eq = self._volume_equipment(customer_rate=3, load_volume=1.2345)
		card = self._volume_card(eq, [{"loads_count": 7, "working_hours": 10}], submit=True)
		self.assertEqual(flt(card.customer_amount), 25.92)
		self.assertEqual(flt(card.load_volume_used, 4), 1.2345)

	def test_loads_last_month_refuses_card_operator(self):
		# FR-166 (review F4): the aggregate keeps the read check; Card Operator has no read on monthly cards
		from card.card_value import loads_last_month
		from card.tests.test_card_money_privacy import _user

		frappe.set_user(_user(["Card Operator"], restrict=self.company))
		try:
			with self.assertRaises(frappe.PermissionError):
				loads_last_month({"company": self.company})
		finally:
			frappe.set_user("Administrator")

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
		self.assertEqual(
			meta.get_field("total_volume_m3").permlevel, 1
		)  # owner D2: volume is restricted like money
		self.assertEqual(frappe.get_meta("Card Monthly Card Day").get_field("loads_count").permlevel, 0)
		for name in ("load_volume_used", "total_loads", "total_volume_m3"):
			self.assertFalse(meta.get_field(name).allow_on_submit, name)
			self.assertNotIn(name, CARD_MONEY_FIELDS)

	# ---- owner D1 and D2 (review of 2026-11-14) ----
	def test_loads_are_refused_on_a_card_not_billed_per_m3(self):
		eq = self._rented_out(customer_rate=1000)  # per-day customer rate, not per m³
		with self.assertRaisesRegex(frappe.ValidationError, "customer rate type is per m"):
			self._volume_card(eq, [{"loads_count": 3, "working_hours": 10}])

	def test_hours_without_loads_warn_and_still_save_and_submit(self):
		# owner decision (2026-11-14): hours with no loads on a per-m³ card = customer amount 0; warn, never refuse
		eq = self._volume_equipment()
		self._interactive()
		frappe.local.message_log = []
		card = self._volume_card(eq, [{"loads_count": 0, "working_hours": 10}], submit=True)
		self.assertEqual(card.docstatus, 1)  # save and submit both succeed
		self.assertEqual(flt(card.customer_amount), 0)
		self.assertEqual(flt(card.total_working_hours), 10)  # hours stay recorded for cost
		shown = " ".join(str(m) for m in frappe.local.message_log)
		self.assertIn("This card has operating hours but no loads", shown)

	def test_interactive_save_says_which_loads_were_cleared(self):
		# FR-166 (owner 2026-11-14): the clearing stays, but the operator is told the non-working dates
		self._interactive()
		frappe.local.message_log = []
		card = self._hours_then_cleared_loads_card()
		self.assertEqual(card.days[1].loads_count, 0)
		shown = " ".join(str(m) for m in frappe.local.message_log)
		self.assertIn("Loads were cleared on these non-working days: 2026-09-02", shown)
		self.assertIn("This card has operating hours but no loads", shown)

	def test_in_import_flag_silences_both_messages(self):
		self._interactive()
		self._flag("in_import")
		self._assert_quiet_save()

	def test_in_patch_flag_silences_both_messages(self):
		self._interactive()
		self._flag("in_patch")
		self._assert_quiet_save()

	def test_in_migrate_flag_silences_both_messages(self):
		self._interactive()
		self._flag("in_migrate")
		self._assert_quiet_save()

	def test_mute_messages_flag_silences_both_messages(self):
		self._interactive()
		self._flag("mute_messages")
		self._assert_quiet_save()

	def test_background_save_without_a_request_is_quiet(self):
		# a background job or console run has no HTTP request
		saved = getattr(frappe.local, "request", None)
		frappe.local.request = None
		self.addCleanup(setattr, frappe.local, "request", saved)
		self._assert_quiet_save()

	def test_no_warning_when_loads_are_present(self):
		# the warning is for hours with NO loads only: a normal per-m³ card with loads must stay silent
		eq = self._volume_equipment()
		frappe.local.message_log = []
		card = self._volume_card(eq, [{"loads_count": 40, "working_hours": 10}], submit=True)
		self.assertEqual(card.docstatus, 1)
		shown = " ".join(str(m) for m in frappe.local.message_log)
		self.assertNotIn("This card has operating hours but no loads", shown)

	def test_zero_loads_are_allowed_on_a_card_not_billed_per_m3(self):
		eq = self._rented_out(customer_rate=1000)
		card = self._volume_card(eq, [{"loads_count": 0, "working_hours": 10}])
		self.assertEqual(card.total_loads, 0)

	def test_card_operator_gets_no_total_volume_through_get_list(self):
		from card.tests.test_card_money_privacy import _user

		frappe.set_user(_user(["Card Operator"], restrict=self.company))
		try:
			with self.assertRaises(frappe.PermissionError):
				frappe.get_list("Card Monthly Card", fields=["total_volume_m3"], limit=1)
		finally:
			frappe.set_user("Administrator")

	def test_loads_number_card_needs_no_permlevel_1(self):
		# FR-166 owner decision: total_loads is permlevel 0, so the loads card works for a user who may not read the
		# permlevel-1 total volume (the field-level rule is overridden only inside this test; no DocPerm is changed)
		from unittest import mock

		from frappe.utils import getdate

		from card.card_value import loads_last_month
		from card.tests.test_card_money_privacy import _user

		eq = self._volume_equipment()
		self._volume_card(eq, [{"loads_count": 40, "working_hours": 10}], submit=True)
		meta_cls = type(frappe.get_meta("Card Monthly Card"))
		original = meta_cls.get_permitted_fieldnames

		def without_level_1(self, *args, **kwargs):
			return [f for f in original(self, *args, **kwargs) if f != "total_volume_m3"]

		frappe.set_user(_user(["Card User"], restrict=self.company))
		try:
			# the card is September 2026; pin "last month" to it so the test does not depend on today's date
			last_month = (getdate("2026-09-01"), getdate("2026-09-30"))
			with (
				mock.patch.object(meta_cls, "get_permitted_fieldnames", without_level_1),
				mock.patch("card.card_value._last_month", return_value=last_month),
			):
				result = loads_last_month({"company": self.company})
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(result["fieldtype"], "Int")
		self.assertEqual(result["value"], 40)

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

	def test_loads_number_card_and_dashboard_show_loads_last_month(self):
		import json

		from card.card_value import loads_last_month

		card = frappe.db.get_value(
			"Number Card", "Loads last month", ["method", "type", "function"], as_dict=True
		)
		self.assertIsNotNone(card)
		self.assertEqual(card.method, "card.card_value.loads_last_month")
		self.assertEqual(card.type, "Custom")
		with open(frappe.get_app_path("card", "fixtures", "workspace.json"), encoding="utf-8") as fh:
			dashboard = json.load(fh)[0]
		shown = {
			b["data"]["number_card_name"]
			for b in json.loads(dashboard["content"])
			if b["type"] == "number_card"
		}
		self.assertIn("Loads last month", shown)
		self.assertNotIn("Volume last month (m³)", shown)
		loads = loads_last_month({"company": self.company})
		self.assertEqual(loads["fieldtype"], "Int")
		self.assertEqual(loads["route"], ["List", "Card Monthly Card"])
		self.assertEqual(loads["route_options"]["customer_rate_type"], PER_M3)

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
			"Cannot record loads for a future day: {0}",
			"بالمتر المكعب",
			"Loads last month",
			"Loads can be recorded only on a card whose customer rate type is per m³",
			"This card has operating hours but no loads, so the customer amount is zero. Check the loads.",
			"Loads were cleared on these non-working days: {0}",
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

	# ---- standard print (Card Monthly Card Print): money only for a user with money read (FR-162) ----
	def test_standard_print_hides_rate_and_amount_without_money_read(self):
		from card.tests.test_card_money_privacy import _user

		template = frappe.get_jenv().from_string(
			frappe.get_doc("Print Format", "Card Monthly Card Print").html
		)
		deduction = {"adjustment_type": "خصم", "amount": 100, "description": "TEST deduction"}
		card = self._volume_card(
			self._volume_equipment(),
			[{"loads_count": 40, "working_hours": 10}],
			submit=True,
			adjustments=[deduction],
		)
		doc = frappe.get_doc("Card Monthly Card", card.name)
		amount = frappe.utils.fmt_money(doc.customer_amount)
		rate = frappe.utils.fmt_money(doc.customer_rate)

		def render(role):
			frappe.set_user(_user([role], restrict=self.company))
			try:
				return template.render({"doc": doc, "letter_head": None})
			finally:
				frappe.set_user("Administrator")

		# users with money read: the amount, rate, settlement and money columns are in the HTML
		for role in ("Card User", "Card Manager"):
			html = render(role)
			self.assertIn(amount, html, role)
			self.assertIn(rate, html, role)
			self.assertIn("Total amount", html, role)
			self.assertIn("Customer settlement", html, role)
			self.assertIn("Adjustment amount", html, role)
			self.assertIn("Total volume (m³)", html, role)
			self.assertIn('class="emc-sum-m"', html, role)
			self.assertIn('class="emc-sum-g"', html, role)
		# Card Operator: the money columns are absent from the HTML (header, cells and totals column)
		operator = render("Card Operator")
		self.assertNotIn(amount, operator)
		self.assertNotIn(rate, operator)
		self.assertNotIn("Total amount", operator)
		self.assertNotIn("Customer settlement", operator)
		self.assertNotIn("Adjustment amount", operator)
		self.assertNotIn('class="emc-sum-m"', operator)
		self.assertNotIn('class="emc-sum-g"', operator)
		self.assertNotIn("Supplier settlement", operator)
		# non-money content stays: the adjustment description, the loads, the hours
		self.assertIn("TEST deduction", operator)
		self.assertIn("Total loads", operator)
		self.assertNotIn("Total volume (m³)", operator)  # owner D2: the volume is money-level
		self.assertIn("Total operating hours", operator)
