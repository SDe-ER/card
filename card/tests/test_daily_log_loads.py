# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-188 (#44): loads on the daily log, opt-in per company (Card Company Settings ``daily_log_loads``, default 0).

Proven here. Off (the default, also with no settings row): a daily log row with loads is refused, and the
generation neither writes nor clears the loads of a monthly card, so a hand-entered load count is kept. On: the
day shift loads go to the day shift card and the night shift loads to the night shift card, and the customer
amount equals loads x load volume x rate (FR-166); a night with loads and no hours gets its card; loads on
equipment not billed per m³, negative loads and loads on a future day are refused on the log; a repeat run changes
nothing; a log without loads does not erase a hand-entered load count; an amended log replaces the loads (zero
included) and the day is reported; a cancelled log clears the loads of its day on a draft card; a submitted card
is never changed. The two row fields are plain counts (Int, level 0) and the setting is a level-1 Check that
defaults to 0.

A client that does not send the two load fields (CARD Mobile) cannot erase them: a save of an existing row without
the keys keeps the stored loads, a corrected draft (a new log that amends a cancelled one) without the keys takes
the loads of the log it amends, and an explicit 0 clears them. After the switch is turned off, a log that holds
loads is still saved while its loads are unchanged (or cleared); only new or changed loads are refused. A day
cleared because its log was cancelled loses the loads the generation copied from that log, also with the switch
off; loads typed by hand on a card are kept. Everything is rolled back; no role is widened."""

import frappe
from frappe.utils import add_days, add_months, flt, get_first_day, nowdate

from card import daily_log
from card.constants import DIR_RENTED_OUT, OWNED, SHIFT_DAY, SHIFT_NIGHT
from card.daily_log_generation import generate_monthly_cards
from card.tests.test_customer import _CustomerCardsBase

LOG = "Card Daily Log"
CARD = "Card Monthly Card"
COMPANY_SETTINGS = "Card Company Settings"
PER_M3 = "بالمتر المكعب"
LOAD_VOLUME = 16  # m³ per load
RATE = 2  # per m³


class TestDailyLogLoads(_CustomerCardsBase):
	def setUp(self):
		super().setUp()
		self.first = get_first_day(add_months(nowdate(), -1))
		self.month = str(self.first)[:7]
		self.eq = self._volume_equipment()
		self.operator = self._user("op", ("Card Operator",))
		self.manager = self._user("mgr", ("Card Manager",))
		self.runner = self._user("run", ("Card Manager",), company=self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# ---------- builders ----------
	def _volume_equipment(self):
		"""A rented-out machine billed to the customer per m³."""
		return self._equipment(
			OWNED,
			direction=DIR_RENTED_OUT,
			customer=self.customer,
			customer_rate=RATE,
			customer_rate_type=PER_M3,
			load_volume_m3=LOAD_VOLUME,
		)

	def _user(self, prefix, roles, company=None):
		email = f"dll-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "DLL " + prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if company:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": company,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _loads_setting(self, on=1):
		"""Set ``daily_log_loads`` on the company's Card Company Settings row (created when the company has none)."""
		filters = {
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": "company_settings",
			"company": self.company,
		}
		name = frappe.db.get_value(COMPANY_SETTINGS, filters, "name")
		if name:
			frappe.db.set_value(COMPANY_SETTINGS, name, "daily_log_loads", on)
			return
		row = frappe.new_doc(COMPANY_SETTINGS)
		row.update({**filters, "idx": 999, "daily_log_loads": on})
		row.name = "TEST-DLL-ROW-" + self.token
		row.db_insert()

	def _day(self, n):
		return add_days(self.first, n - 1)

	def _row(self, day=8, night=0, **values):
		return {"equipment": self.eq.name, "day_hours": day, "night_hours": night, **values}

	def _draft(self, rows, log_date):
		doc = frappe.new_doc(LOG)
		doc.update({"company": self.company, "project": self.project, "log_date": log_date})
		for row in rows:
			doc.append("rows", row)
		return doc

	def _approve(self, name):
		frappe.set_user(self.manager)
		try:
			doc = frappe.get_doc(LOG, name)
			doc.approval_status = daily_log.APPROVED
			doc.save()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		return doc

	def _log(self, n, rows):
		"""An Approved, submitted daily log of day ``n`` of last month."""
		frappe.set_user(self.operator)
		try:
			doc = self._draft(rows, self._day(n))
			doc.insert()
			doc.submit()
		finally:
			frappe.set_user("Administrator")
		return self._approve(doc.name)

	def _refused(self, rows, log_date=None):
		frappe.set_user(self.operator)
		try:
			with self.assertRaises(frappe.ValidationError):
				self._draft(rows, log_date or self._day(1)).insert()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()

	def _cancel(self, log):
		frappe.set_user(self.manager)
		try:
			frappe.get_doc(LOG, log.name).cancel()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()

	def _amend(self, log, **row_values):
		frappe.set_user(self.operator)
		try:
			doc = frappe.copy_doc(frappe.get_doc(LOG, log.name))
			doc.docstatus = 0
			doc.amended_from = log.name
			doc.rows[0].update(row_values)
			doc.insert()
			doc.submit()
		finally:
			frappe.set_user("Administrator")
		return self._approve(doc.name)

	def _run(self):
		frappe.set_user(self.runner)
		try:
			return generate_monthly_cards(company=self.company, project=self.project, month=self.month)
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()

	def _cards(self, shift):
		return frappe.get_all(
			CARD,
			filters={"equipment": self.eq.name, "docstatus": ["!=", 2], "shift": shift},
			pluck="name",
		)

	def _card_day(self, card, n):
		return {str(d.operation_date): d for d in frappe.get_doc(CARD, card).days}[str(self._day(n))]

	def _type_loads(self, card, loads):
		"""A hand-entered load count on the first day row of a draft card."""
		doc = frappe.get_doc(CARD, card)
		doc.days[0].loads_count = loads
		doc.save()
		frappe.clear_messages()

	# ---------- the fields and the setting ----------
	def test_setting_is_a_level_1_check_that_defaults_to_off(self):
		field = frappe.get_meta(COMPANY_SETTINGS).get_field("daily_log_loads")
		self.assertEqual((field.fieldtype, str(field.default), field.permlevel), ("Check", "0", 1))
		self.assertFalse(field.description)

	def test_load_fields_are_plain_counts(self):
		meta = frappe.get_meta("Card Daily Log Row")
		for fieldname in ("day_loads", "night_loads"):
			field = meta.get_field(fieldname)
			self.assertEqual((field.fieldtype, field.permlevel, field.non_negative), ("Int", 0, 1))
			self.assertFalse(field.description)

	def test_each_company_follows_its_own_setting(self):
		self.assertFalse(daily_log.loads_enabled(self.company))
		self._loads_setting(1)
		self.assertTrue(daily_log.loads_enabled(self.company))
		self.assertFalse(daily_log.loads_enabled("TEST-DLL-NO-ROW-" + self.token))
		self.assertFalse(daily_log.loads_enabled(None))
		self._loads_setting(0)
		self.assertFalse(daily_log.loads_enabled(self.company))

	def test_the_form_gets_the_setting_on_load(self):
		log = self._log(1, [self._row(8)])
		doc = frappe.get_doc(LOG, log.name)
		doc.run_method("onload")
		self.assertEqual(doc.get_onload("daily_log_loads"), 0)
		self._loads_setting(1)
		doc = frappe.get_doc(LOG, log.name)
		doc.run_method("onload")
		self.assertEqual(doc.get_onload("daily_log_loads"), 1)

	# ---------- off: the behaviour before FR-188 ----------
	def test_off_a_log_with_loads_is_refused(self):
		self._refused([self._row(8, day_loads=3)])
		self._refused([self._row(0, 6, night_loads=2)])
		self._loads_setting(0)  # an explicit 0 is the same as no row
		self._refused([self._row(8, day_loads=3)])

	def test_off_a_log_without_loads_is_saved_as_before(self):
		log = self._log(1, [self._row(8, 6)])
		row = frappe.get_doc(LOG, log.name).rows[0]
		self.assertEqual((row.day_loads, row.night_loads), (0, 0))

	def test_off_the_generation_keeps_hand_entered_loads(self):
		self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		self.assertEqual(self._card_day(card, 1).loads_count, 0)
		self._type_loads(card, 5)
		result = self._run()
		self.assertEqual((result["unchanged"], result["updated"]), ([card], []))
		self.assertEqual(self._card_day(card, 1).loads_count, 5)

	def test_off_stored_log_loads_are_not_copied(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, day_loads=7)])
		self._loads_setting(0)
		(card,) = self._run()["created"]
		self.assertEqual(self._card_day(card, 1).loads_count, 0)
		self.assertEqual(frappe.db.get_value(CARD, card, "total_loads"), 0)

	# ---------- on: the log ----------
	def test_on_negative_loads_are_refused(self):
		self._loads_setting(1)
		self._refused([self._row(8, day_loads=-1)])
		self._refused([self._row(8, 6, night_loads=-2)])

	def test_on_loads_on_a_future_day_are_refused(self):
		self._loads_setting(1)
		self._refused([self._row(0, 0, day_loads=3)], log_date=add_days(nowdate(), 1))

	def test_on_loads_on_equipment_not_billed_per_m3_are_refused(self):
		self._loads_setting(1)
		hourly = self._rented_out()  # billed to the customer per day
		self._refused([{"equipment": hourly.name, "day_hours": 8, "day_loads": 3}])
		self._refused([{"equipment": hourly.name, "night_hours": 8, "night_loads": 3}])

	def test_on_a_log_with_loads_is_saved(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, 6, day_loads=25, night_loads=15)])
		row = frappe.get_doc(LOG, log.name).rows[0]
		self.assertEqual((row.day_loads, row.night_loads), (25, 15))

	# ---------- on: the generation ----------
	def test_on_day_and_night_loads_go_to_their_shift_cards(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, 6, day_loads=25, night_loads=15)])
		result = self._run()
		self.assertEqual(len(result["created"]), 2)
		self.assertEqual(result["errors"], [])
		(day_card,) = self._cards(SHIFT_DAY)
		(night_card,) = self._cards(SHIFT_NIGHT)
		self.assertEqual(self._card_day(day_card, 1).loads_count, 25)
		self.assertEqual(self._card_day(night_card, 1).loads_count, 15)
		day, night = frappe.get_doc(CARD, day_card), frappe.get_doc(CARD, night_card)
		self.assertEqual((day.total_loads, night.total_loads), (25, 15))
		# FR-166: loads x load volume x rate per m³; the night rate is empty, so the day rate applies
		self.assertEqual(flt(day.customer_amount), 25 * LOAD_VOLUME * RATE)
		self.assertEqual(flt(night.customer_amount), 15 * LOAD_VOLUME * RATE)
		# no card is submitted by the run
		self.assertEqual((day.docstatus, night.docstatus), (0, 0))

	def test_on_a_night_with_loads_and_no_hours_gets_its_card(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, 0, night_loads=4)])
		self._run()
		(night_card,) = self._cards(SHIFT_NIGHT)
		day = self._card_day(night_card, 1)
		self.assertEqual((flt(day.working_hours), day.loads_count), (0, 4))

	def test_on_a_repeat_run_changes_nothing(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, day_loads=25)])
		(card,) = self._run()["created"]
		again = self._run()
		self.assertEqual((again["unchanged"], again["updated"], again["overwritten_days"]), ([card], [], []))
		self.assertEqual(self._card_day(card, 1).loads_count, 25)

	def test_on_a_log_without_loads_keeps_hand_entered_loads(self):
		# the log was approved before the company used loads on daily logs; the office typed the loads on the card
		self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		self._type_loads(card, 9)
		self._loads_setting(1)
		result = self._run()
		self.assertEqual((result["unchanged"], result["overwritten_days"]), ([card], []))
		self.assertEqual(self._card_day(card, 1).loads_count, 9)

	def test_on_log_loads_replace_hand_entered_loads_and_are_reported(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, day_loads=25)])
		(card,) = self._run()["created"]
		self._type_loads(card, 30)
		result = self._run()
		self.assertEqual(result["updated"], [card])
		(day,) = result["overwritten_days"]
		self.assertEqual((day["date"], day["old_loads"], day["new_loads"]), (str(self._day(1)), 30, 25))
		self.assertEqual(self._card_day(card, 1).loads_count, 25)

	def test_on_an_amended_log_replaces_the_loads(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, day_loads=5)])
		(card,) = self._run()["created"]
		self._cancel(log)
		amended = self._amend(log, day_loads=8)
		result = self._run()
		self.assertEqual(result["updated"], [card])
		(day,) = result["overwritten_days"]
		self.assertEqual((day["old_loads"], day["new_loads"], day["new_notes"]), (5, 8, amended.name))
		self.assertEqual(self._card_day(card, 1).loads_count, 8)

	def test_on_an_amended_log_without_loads_clears_the_loads_of_the_earlier_log(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, day_loads=5)])
		(card,) = self._run()["created"]
		self._cancel(log)
		self._amend(log, day_loads=0)
		self.assertEqual(self._run()["updated"], [card])
		self.assertEqual(self._card_day(card, 1).loads_count, 0)
		self.assertEqual(frappe.db.get_value(CARD, card, "total_loads"), 0)

	def test_on_a_cancelled_log_clears_the_loads_of_its_day(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, day_loads=6)])
		log2 = self._log(2, [self._row(5, day_loads=4)])
		(card,) = self._run()["created"]
		self.assertEqual(frappe.db.get_value(CARD, card, "total_loads"), 10)
		self._cancel(log2)
		result = self._run()
		self.assertEqual(result["updated"], [card])
		(cleared,) = result["cleared_days"]
		self.assertEqual(
			(cleared["date"], cleared["log"], cleared["loads"]), (str(self._day(2)), log2.name, 4)
		)
		self.assertEqual(self._card_day(card, 2).loads_count, 0)
		self.assertEqual(frappe.db.get_value(CARD, card, "total_loads"), 6)

	def test_on_a_submitted_card_is_never_changed(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, day_loads=5)])
		(card,) = self._run()["created"]
		frappe.get_doc(CARD, card).submit()
		frappe.clear_messages()
		modified = frappe.db.get_value(CARD, card, "modified")
		self._cancel(log)
		self._amend(log, day_loads=8)
		result = self._run()
		self.assertEqual([k["card"] for k in result["kept_submitted"]], [card])
		self.assertEqual((result["updated"], result["overwritten_days"]), ([], []))
		self.assertEqual(frappe.db.get_value(CARD, card, "modified"), modified)
		self.assertEqual(self._card_day(card, 1).loads_count, 5)

	# ---------- a client that does not send the load fields (CARD Mobile) ----------
	def _draft_log(self, n, rows):
		"""A saved draft daily log of day ``n`` of last month, by the operator."""
		frappe.set_user(self.operator)
		try:
			doc = self._draft(rows, self._day(n))
			doc.insert()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		return doc

	def _rest_update(self, name, row_values, user=None):
		"""Save the log as a REST update does (``doc.update(data)`` with the rows as plain dicts, then ``save``):
		a key that the client did not send is not in the row."""
		frappe.set_user(user or self.operator)
		try:
			doc = frappe.get_doc(LOG, name)
			stored = doc.rows[0]
			row = {"name": stored.name, "equipment": stored.equipment, **row_values}
			doc.update({"rows": [row]})
			doc.save()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		return frappe.get_doc(LOG, name).rows[0]

	def _corrected_draft(self, log, row_values):
		"""The corrected draft CARD Mobile creates: a new log that amends the cancelled one, rows without names."""
		frappe.set_user(self.operator)
		try:
			doc = self._draft([{"equipment": self.eq.name, **row_values}], log.log_date)
			doc.amended_from = log.name
			doc.insert()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		return frappe.get_doc(LOG, doc.name).rows[0]

	def test_a_save_without_the_load_keys_keeps_the_stored_loads(self):
		self._loads_setting(1)
		log = self._draft_log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		row = self._rest_update(log.name, {"day_hours": 7, "night_hours": 6})
		self.assertEqual((flt(row.day_hours), row.day_loads, row.night_loads), (7, 5, 2))
		# one key sent, the other not: the sent one is stored, the other is kept
		row = self._rest_update(log.name, {"day_hours": 7, "night_hours": 6, "day_loads": 9})
		self.assertEqual((row.day_loads, row.night_loads), (9, 2))

	def test_a_save_with_explicit_zero_loads_clears_them(self):
		self._loads_setting(1)
		log = self._draft_log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		row = self._rest_update(
			log.name, {"day_hours": 8, "night_hours": 6, "day_loads": 0, "night_loads": 0}
		)
		self.assertEqual((row.day_loads, row.night_loads), (0, 0))

	def test_a_form_save_of_the_loaded_log_stores_the_loads_it_sends(self):
		self._loads_setting(1)
		log = self._draft_log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		frappe.set_user(self.operator)
		try:
			doc = frappe.get_doc(LOG, log.name)
			doc.rows[0].day_loads = 11
			doc.save()
			# the form sends every field of every row
			doc = frappe.get_doc(LOG, log.name)
			rows = [r.as_dict() for r in doc.rows]
			rows[0]["night_loads"] = 0
			doc.update({"rows": rows})
			doc.save()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		row = frappe.get_doc(LOG, log.name).rows[0]
		self.assertEqual((row.day_loads, row.night_loads), (11, 0))

	def test_a_new_row_without_the_load_keys_has_no_loads(self):
		self._loads_setting(1)
		log = self._draft_log(1, [self._row(8, 6)])
		row = frappe.get_doc(LOG, log.name).rows[0]
		self.assertEqual((row.day_loads, row.night_loads), (0, 0))

	def test_a_corrected_draft_without_the_load_keys_keeps_the_loads_of_the_cancelled_log(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		self._cancel(log)
		row = self._corrected_draft(log, {"day_hours": 7, "night_hours": 6})
		self.assertEqual((flt(row.day_hours), row.day_loads, row.night_loads), (7, 5, 2))

	def test_a_corrected_draft_with_explicit_zero_loads_has_none(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		self._cancel(log)
		row = self._corrected_draft(log, {"day_hours": 7, "night_hours": 6, "day_loads": 0, "night_loads": 0})
		self.assertEqual((row.day_loads, row.night_loads), (0, 0))

	def test_loads_of_a_row_of_another_log_are_not_taken(self):
		self._loads_setting(1)
		other = self._draft_log(2, [self._row(8, 6, day_loads=5, night_loads=2)])
		log = self._draft_log(1, [self._row(8, 6)])
		frappe.set_user(self.operator)
		try:
			doc = frappe.get_doc(LOG, log.name)
			# a forged row name (a row of another log) is not a stored row of this log
			doc.update({"rows": [{"name": other.rows[0].name, "equipment": self.eq.name, "day_hours": 8}]})
			row = doc.rows[0]
			daily_log.keep_unsent_loads(doc)
		finally:
			frappe.set_user("Administrator")
		self.assertFalse(row.day_loads)
		self.assertFalse(row.night_loads)

	# ---------- the switch turned off after loads were stored ----------
	def test_off_after_on_a_log_with_unchanged_loads_is_still_saved(self):
		self._loads_setting(1)
		log = self._draft_log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		self._loads_setting(0)
		# the form: every field sent, loads unchanged
		frappe.set_user(self.operator)
		try:
			doc = frappe.get_doc(LOG, log.name)
			doc.rows[0].day_hours = 9
			doc.save()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		# CARD Mobile: the load keys are not sent
		row = self._rest_update(log.name, {"day_hours": 7, "night_hours": 6})
		self.assertEqual((flt(row.day_hours), row.day_loads, row.night_loads), (7, 5, 2))

	def test_off_after_on_changed_loads_are_refused_and_cleared_loads_are_accepted(self):
		self._loads_setting(1)
		log = self._draft_log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		self._loads_setting(0)
		with self.assertRaises(frappe.ValidationError):
			self._rest_update(log.name, {"day_hours": 8, "night_hours": 6, "day_loads": 6})
		row = self._rest_update(log.name, {"day_hours": 8, "night_hours": 6, "day_loads": 0})
		self.assertEqual((row.day_loads, row.night_loads), (0, 2))

	def test_off_after_on_a_corrected_draft_keeps_the_loads_of_the_cancelled_log(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, 6, day_loads=5, night_loads=2)])
		self._loads_setting(0)
		self._cancel(log)
		row = self._corrected_draft(log, {"day_hours": 7, "night_hours": 6})
		self.assertEqual((row.day_loads, row.night_loads), (5, 2))

	# ---------- a cancelled log and the switch turned off ----------
	def test_off_after_on_a_cancelled_log_clears_the_loads_it_gave_the_card(self):
		self._loads_setting(1)
		self._log(1, [self._row(8, day_loads=6)])
		log2 = self._log(2, [self._row(5, day_loads=4)])
		(card,) = self._run()["created"]
		self._loads_setting(0)
		self._cancel(log2)
		result = self._run()
		self.assertEqual(result["updated"], [card])
		(cleared,) = result["cleared_days"]
		self.assertEqual(
			(cleared["date"], cleared["log"], cleared["loads"]), (str(self._day(2)), log2.name, 4)
		)
		day2 = self._card_day(card, 2)
		self.assertEqual((flt(day2.working_hours), day2.loads_count), (0, 0))
		self.assertEqual(frappe.db.get_value(CARD, card, "total_loads"), 6)

	def test_off_a_cancelled_log_keeps_loads_typed_on_the_card(self):
		# the company never used loads on daily logs: the log holds none, so the loads of the day are a hand entry
		log = self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		self._type_loads(card, 5)
		self._cancel(log)
		result = self._run()
		self.assertEqual(result["updated"], [card])
		(cleared,) = result["cleared_days"]
		self.assertNotIn("loads", cleared)
		day = self._card_day(card, 1)
		self.assertEqual((flt(day.working_hours), day.loads_count), (0, 5))

	def test_off_after_on_a_cancelled_log_keeps_other_loads_typed_on_the_card(self):
		self._loads_setting(1)
		log = self._log(1, [self._row(8, day_loads=4)])
		(card,) = self._run()["created"]
		self._loads_setting(0)
		self._type_loads(card, 7)  # not the loads of the log: a hand entry
		self._cancel(log)
		self._run()
		self.assertEqual(self._card_day(card, 1).loads_count, 7)
