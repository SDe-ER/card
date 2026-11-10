# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-145 (#44, #123; WP-K2): draft monthly cards from approved daily logs.

Proven here: day and night hours, stop data and responsible party mapped to the day rows of the day and night shift
cards; only Approved, submitted logs are read; a repeat run changes nothing and a log approved later fills its day;
a machine moved between two projects gets one card per project; a day off the project (yard) and a day as a unit
component are left out and reported; a submitted card is never changed and no card is submitted; a card that fails
its own validation is rolled back alone; cross-company and role refusals; a GET request is refused. Everything is
rolled back; no role is widened."""

import types

import frappe
from frappe.handler import is_valid_http_method
from frappe.utils import add_days, add_months, flt, get_first_day

from card import daily_log
from card.constants import SHIFT_DAY, SHIFT_NIGHT
from card.daily_log_generation import (
	SKIP_OFF_PROJECT,
	SKIP_UNIT_COMPONENT,
	day_name,
	generate_monthly_cards,
)
from card.tests.test_customer import _CustomerCardsBase

LOG = "Card Daily Log"
CARD = "Card Monthly Card"


class TestDailyLogGeneration(_CustomerCardsBase):
	def setUp(self):
		super().setUp()
		self.first = get_first_day(add_months(frappe.utils.nowdate(), -1))
		self.month = str(self.first)[:7]
		self.card_month, self.card_year = "%02d" % self.first.month, self.first.year
		self.eq = self._equipment()
		self.operator = self._user("op", ("Card Operator",))
		self.manager = self._user("mgr", ("Card Manager",))
		self.runner = self._user("run", ("Card Manager",), company=self.company)

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# ---------- builders ----------
	def _user(self, prefix, roles, company=None):
		email = f"k2-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "K2 " + prefix,
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

	def _day(self, n):
		return add_days(self.first, n - 1)

	def _log(self, n, rows, project=None, status=daily_log.APPROVED):
		frappe.set_user(self.operator)
		try:
			doc = frappe.new_doc(LOG)
			doc.update(
				{"company": self.company, "project": project or self.project, "log_date": self._day(n)}
			)
			for row in rows:
				doc.append("rows", row)
			doc.insert()
			doc.submit()
		finally:
			frappe.set_user("Administrator")
		if status != daily_log.PENDING:
			frappe.set_user(self.manager)
			try:
				doc = frappe.get_doc(LOG, doc.name)
				doc.approval_status = status
				if status == daily_log.RETURNED:
					doc.return_reason = "check the hours"
				doc.save()
			finally:
				frappe.set_user("Administrator")
		frappe.clear_messages()
		return doc

	def _row(self, day=8, night=0, **values):
		return {"equipment": self.eq.name, "day_hours": day, "night_hours": night, **values}

	def _run(self, user=None, project=None, equipment=None):
		frappe.set_user(user or self.runner)
		try:
			return generate_monthly_cards(
				company=self.company, project=project or self.project, month=self.month, equipment=equipment
			)
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()

	def _cards(self, shift=None, project=None):
		filters = {"equipment": self.eq.name, "docstatus": ["!=", 2]}
		if shift:
			filters["shift"] = shift
		if project:
			filters["project"] = project
		return frappe.get_all(CARD, filters=filters, pluck="name")

	def _days(self, card):
		return {str(d.operation_date): d for d in frappe.get_doc(CARD, card).days}

	def _project(self, suffix):
		proj = frappe.new_doc("Project")
		proj.project_name = f"TEST-K2-PRJ-{self.token}{suffix}"
		proj.company = self.company
		proj.cost_center = frappe.db.get_value(
			"Cost Center", {"company": self.company, "is_group": 0}, "name"
		)
		proj.insert(ignore_permissions=True)
		return proj.name

	def _assign(self, project, from_n, to_n=None, equipment=None):
		a = frappe.new_doc("Card Equipment Assignment")
		a.update({"equipment": equipment or self.eq.name, "project": project, "from_date": self._day(from_n)})
		if to_n:
			a.to_date = self._day(to_n)
		a.insert(ignore_permissions=True)
		return a

	def _company_b(self):
		name = "TEST-K2-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "K" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	# ---------- mapping ----------
	def test_day_night_and_stop_data_are_mapped(self):
		reason = frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": self.company,
				"reason_name": "TEST-K2-STOP-" + self.token,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		self._log(
			1,
			[
				self._row(
					6,
					5,
					stop_reason=reason.name,
					stopped_hours=2,
					responsible_party_type="Supplier",
					responsible_party=self.supplier,
				)
			],
		)
		log2 = self._log(2, [self._row(9)])
		result = self._run()
		self.assertEqual(len(result["created"]), 2, result)
		self.assertEqual(result["errors"], [])
		(day_card,) = self._cards(SHIFT_DAY)
		(night_card,) = self._cards(SHIFT_NIGHT)
		day_rows, night_rows = self._days(day_card), self._days(night_card)
		first, second = str(self._day(1)), str(self._day(2))
		self.assertEqual(day_rows[first].working_hours, 6)
		self.assertEqual(day_rows[first].stop_reason, reason.name)
		self.assertEqual(day_rows[first].stopped_hours, 2)
		self.assertEqual(day_rows[first].responsible_party_type, "Supplier")
		self.assertEqual(day_rows[first].responsible_party, self.supplier)
		self.assertEqual(day_rows[second].working_hours, 9)
		self.assertEqual(day_rows[second].notes, log2.name)
		self.assertEqual(night_rows[first].working_hours, 5)
		self.assertFalse(night_rows[first].stop_reason)
		self.assertEqual(night_rows[second].working_hours, 0)
		card = frappe.get_doc(CARD, day_card)
		self.assertEqual(card.docstatus, 0)
		self.assertEqual(
			(card.company, card.project, card.month, card.year),
			(self.company, self.project, self.card_month, self.card_year),
		)
		self.assertEqual(card.total_working_hours, 15)

	def test_no_night_card_without_night_hours(self):
		self._log(1, [self._row(8)])
		self._run()
		self.assertEqual(len(self._cards(SHIFT_DAY)), 1)
		self.assertEqual(self._cards(SHIFT_NIGHT), [])

	# ---------- repeat run and later logs ----------
	def test_repeat_run_changes_nothing_and_a_later_log_fills_its_day(self):
		self._log(1, [self._row(8)])
		first = self._run()
		(card,) = first["created"]
		modified = frappe.db.get_value(CARD, card, "modified")
		second = self._run()
		self.assertEqual(second["created"], [])
		self.assertEqual(second["updated"], [])
		self.assertEqual(second["unchanged"], [card])
		self.assertEqual(self._cards(), [card])
		self.assertEqual(len(self._days(card)), 1)
		self.assertEqual(frappe.db.get_value(CARD, card, "modified"), modified)
		self._log(3, [self._row(7)])
		third = self._run()
		self.assertEqual(third["updated"], [card])
		self.assertEqual(self._cards(), [card])
		rows = self._days(card)
		self.assertEqual(sorted(rows), [str(self._day(1)), str(self._day(3))])
		self.assertEqual(rows[str(self._day(3))].working_hours, 7)
		self.assertEqual([d.idx for d in frappe.get_doc(CARD, card).days], [1, 2])

	def test_manual_days_of_a_draft_card_are_kept(self):
		self._log(2, [self._row(8)])
		(card,) = self._run()["created"]
		doc = frappe.get_doc(CARD, card)
		doc.append("days", {"operation_date": self._day(1), "day_status": "عمل", "working_hours": 4})
		doc.save()
		self.assertEqual(self._run()["unchanged"], [card])
		rows = self._days(card)
		self.assertEqual(rows[str(self._day(1))].working_hours, 4)
		self.assertEqual(rows[str(self._day(2))].working_hours, 8)

	# ---------- only approved logs ----------
	def test_only_approved_logs_are_used(self):
		self._log(1, [self._row(8)], status=daily_log.PENDING)
		self._log(2, [self._row(7)], status=daily_log.RETURNED)
		result = self._run()
		self.assertEqual(result["created"], [])
		self.assertEqual(self._cards(), [])
		self._log(3, [self._row(6)])
		(card,) = self._run()["created"]
		self.assertEqual(sorted(self._days(card)), [str(self._day(3))])

	def test_cancelled_approved_log_is_not_used(self):
		log = self._log(1, [self._row(8)])
		frappe.set_user(self.manager)
		frappe.get_doc(LOG, log.name).cancel()
		frappe.set_user("Administrator")
		self.assertEqual(self._run()["created"], [])

	# ---------- submitted cards ----------
	def test_submitted_card_is_untouched_and_never_submitted_by_the_run(self):
		self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		self.assertEqual(frappe.db.get_value(CARD, card, "docstatus"), 0)
		doc = frappe.get_doc(CARD, card)
		doc.submit()
		modified = frappe.db.get_value(CARD, card, "modified")
		self._log(2, [self._row(5)])
		result = self._run()
		self.assertEqual(result["kept_submitted"], [{"card": card, "stale_days": []}])
		self.assertEqual(result["created"] + result["updated"], [])
		self.assertEqual(self._cards(SHIFT_DAY), [card])
		self.assertEqual(sorted(self._days(card)), [str(self._day(1))])
		self.assertEqual(frappe.db.get_value(CARD, card, "modified"), modified)

	# ---------- two projects and yard days ----------
	def test_two_projects_get_one_card_each(self):
		other = self._project("-B")
		self._assign(self.project, 1, 3)
		self._assign(other, 4)
		self._log(1, [self._row(8)])
		self._log(2, [self._row(7)])
		self._log(5, [self._row(6)], project=other)
		first = self._run()
		(card_a,) = first["created"]
		self.assertEqual(self._cards(project=other), [])
		second = self._run(project=other)
		(card_b,) = second["created"]
		self.assertEqual(sorted(self._days(card_a)), [str(self._day(1)), str(self._day(2))])
		self.assertEqual(sorted(self._days(card_b)), [str(self._day(5))])
		self.assertEqual(frappe.db.get_value(CARD, card_b, "project"), other)
		# repeating either run keeps both cards as they are
		self.assertEqual(self._run()["unchanged"], [card_a])
		self.assertEqual(self._run(project=other)["unchanged"], [card_b])
		self.assertEqual(len(self._cards()), 2)

	def test_yard_days_are_left_out(self):
		assignment = self._assign(self.project, 1)
		self._log(1, [self._row(8)])
		self._log(2, [self._row(7)])
		# the machine went back to the yard after day 1 (the move was recorded after the logs were approved)
		frappe.db.set_value("Card Equipment Assignment", assignment.name, "to_date", self._day(1))
		result = self._run()
		(card,) = result["created"]
		self.assertEqual(sorted(self._days(card)), [str(self._day(1))])
		self.assertEqual(
			[(d["date"], d["reason"]) for d in result["skipped_days"]],
			[(str(self._day(2)), SKIP_OFF_PROJECT)],
		)

	def test_all_yard_days_make_no_card(self):
		assignment = self._assign(self.project, 1)
		self._log(2, [self._row(7)])
		frappe.db.set_value("Card Equipment Assignment", assignment.name, "to_date", self._day(1))
		result = self._run()
		self.assertEqual(result["created"], [])
		self.assertEqual(self._cards(), [])

	def test_unit_component_days_are_left_out(self):
		self._log(1, [self._row(8)])
		frappe.db.set_value("Card Equipment", self.eq.name, "is_unit_component", 1)
		result = self._run()
		self.assertEqual(result["created"], [])
		self.assertEqual([d["reason"] for d in result["skipped_days"]], [SKIP_UNIT_COMPONENT])

	def test_a_card_failing_its_validation_is_rolled_back_alone(self):
		other = self._equipment()
		self._log(1, [self._row(8), {"equipment": other.name, "day_hours": 6}])
		frappe.db.set_value("Card Equipment", other.name, "rate_type", "")  # the card refuses: no rate type
		result = self._run()
		self.assertEqual(len(result["created"]), 1)
		self.assertEqual([e["equipment"] for e in result["errors"]], [other.name])
		self.assertEqual(frappe.get_all(CARD, filters={"equipment": other.name}), [])

	def test_equipment_filter(self):
		other = self._equipment()
		self._log(1, [self._row(8), {"equipment": other.name, "day_hours": 6}])
		result = self._run(equipment=other.name)
		self.assertEqual(len(result["created"]), 1)
		self.assertEqual(self._cards(), [])

	# ---------- authorization ----------
	def test_unauthorized_roles_are_refused(self):
		self._log(1, [self._row(8)])
		for roles in ((), ("Card Operator",), ("Card Supervisor",), ("Accounts Manager",)):
			with self.subTest(roles=roles):
				user = self._user("deny", roles)
				with self.assertRaises(frappe.PermissionError):
					self._run(user=user)
		self.assertEqual(self._cards(), [])

	def test_card_user_may_run_it(self):
		self._log(1, [self._row(8)])
		user = self._user("cu", ("Card User",), company=self.company)
		self.assertEqual(len(self._run(user=user)["created"]), 1)

	def test_cross_company_is_refused(self):
		self._log(1, [self._row(8)])
		company_b = self._company_b()
		outsider = self._user("b", ("Card Manager",), company=company_b)
		with self.assertRaises(frappe.PermissionError):
			self._run(user=outsider)
		self.assertEqual(self._cards(), [])
		# a project of another company under this company's name is refused too
		frappe.set_user(self.runner)
		try:
			with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
				generate_monthly_cards(company=company_b, project=self.project, month=self.month)
		finally:
			frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			generate_monthly_cards(company=company_b, project=self.project, month=self.month)
		self.assertEqual(self._cards(), [])

	def test_equipment_of_another_company_is_refused(self):
		company_b = self._company_b()
		eq_b = frappe.new_doc("Card Equipment")
		eq_b.update({"company": company_b, "equipment_name": "TEST-K2-EQB-" + self.token})
		eq_b.name = "TEST-K2-EQB-" + self.token
		eq_b.db_insert()
		with self.assertRaises(frappe.PermissionError):
			self._run(equipment=eq_b.name)

	def test_rest_get_is_refused(self):
		saved = getattr(frappe.local, "request", None)
		try:
			frappe.local.request = types.SimpleNamespace(method="GET")
			with self.assertRaises(frappe.PermissionError):
				is_valid_http_method(generate_monthly_cards)
			frappe.local.request = types.SimpleNamespace(method="POST")
			is_valid_http_method(generate_monthly_cards)
		finally:
			if saved is None:
				try:
					del frappe.local.request
				except AttributeError:
					pass
			else:
				frappe.local.request = saved

	def test_bad_month_is_refused(self):
		frappe.set_user(self.runner)
		try:
			with self.assertRaises(frappe.ValidationError):
				generate_monthly_cards(company=self.company, project=self.project, month="not-a-month")
		finally:
			frappe.set_user("Administrator")

	# ---------- review items (PR #221) ----------
	def _cancel(self, log):
		frappe.set_user(self.manager)
		try:
			frappe.get_doc(LOG, log.name).cancel()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()

	def _amend(self, log, day_hours):
		frappe.set_user(self.operator)
		try:
			doc = frappe.copy_doc(frappe.get_doc(LOG, log.name))
			doc.docstatus = 0
			doc.amended_from = log.name
			doc.rows[0].day_hours = day_hours
			doc.insert()
			doc.submit()
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(self.manager)
		try:
			doc = frappe.get_doc(LOG, doc.name)
			doc.approval_status = daily_log.APPROVED
			doc.save()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		return doc

	def test_cancel_after_generation_clears_the_day(self):
		self._log(1, [self._row(8)])
		log2 = self._log(2, [self._row(5)])
		(card,) = self._run()["created"]
		self._cancel(log2)
		result = self._run()
		self.assertEqual(result["updated"], [card])
		self.assertEqual(
			[(d["date"], d["log"], d["hours"]) for d in result["cleared_days"]],
			[(str(self._day(2)), log2.name, 5)],
		)
		day2 = self._days(card)[str(self._day(2))]
		self.assertEqual((flt(day2.working_hours), day2.notes), (0, None))
		self.assertEqual(frappe.db.get_value(CARD, card, "total_working_hours"), 8)
		# a second run has nothing left to clear
		self.assertEqual(self._run()["unchanged"], [card])
		# the amended, approved log fills the day again
		amended = self._amend(log2, 3)
		self.assertEqual(self._run()["updated"], [card])
		day2 = self._days(card)[str(self._day(2))]
		self.assertEqual((day2.working_hours, day2.notes), (3, amended.name))

	def test_cancel_after_generation_only_reported_on_a_submitted_card(self):
		log = self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		frappe.get_doc(CARD, card).submit()
		modified = frappe.db.get_value(CARD, card, "modified")
		self._cancel(log)
		result = self._run()
		(kept,) = result["kept_submitted"]
		self.assertEqual(kept["card"], card)
		self.assertEqual([(d["date"], d["log"]) for d in kept["stale_days"]], [(str(self._day(1)), log.name)])
		self.assertEqual(result["cleared_days"], [])
		self.assertEqual(frappe.db.get_value(CARD, card, "modified"), modified)
		self.assertEqual(self._days(card)[str(self._day(1))].working_hours, 8)

	def test_a_manual_correction_is_replaced_and_reported(self):
		log = self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		doc = frappe.get_doc(CARD, card)
		doc.days[0].working_hours = 6
		doc.days[0].notes = "corrected by hand"
		doc.save()
		result = self._run()
		self.assertEqual(result["updated"], [card])
		(day,) = result["overwritten_days"]
		self.assertEqual(
			(day["date"], day["old_hours"], day["new_hours"], day["old_notes"], day["new_notes"]),
			(str(self._day(1)), 6, 8, "corrected by hand", log.name),
		)
		self.assertEqual(self._days(card)[str(self._day(1))].working_hours, 8)
		# an unchanged card reports nothing
		again = self._run()
		self.assertEqual((again["unchanged"], again["overwritten_days"]), ([card], []))

	def test_day_name_is_set_on_the_server(self):
		self._log(1, [self._row(8)])
		(card,) = self._run()["created"]
		row = self._days(card)[str(self._day(1))]
		self.assertEqual(row.day_name, day_name(self._day(1)))
		self.assertIn(row.day_name, ("الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"))
		self.assertEqual(day_name("2026-11-13"), "الجمعة")  # a Friday

	def test_other_party_with_a_name(self):
		reason = frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": self.company,
				"reason_name": "TEST-K2-OTH-" + self.token,
				"enabled": 1,
			}
		).insert(ignore_permissions=True)
		self._log(
			1,
			[
				self._row(
					6,
					stop_reason=reason.name,
					stopped_hours=2,
					responsible_party_type="Other",
					responsible_party_name="Site driver",
				)
			],
		)
		(card,) = self._run()["created"]
		row = self._days(card)[str(self._day(1))]
		self.assertEqual(
			(row.responsible_party_type, row.responsible_party, row.responsible_party_name),
			("Other", None, "Site driver"),
		)
		self.assertEqual(self._run()["unchanged"], [card])

	def test_billable_stop_reason_amounts_match_a_hand_entered_card(self):
		reason = frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": self.company,
				"reason_name": "TEST-K2-BILL-" + self.token,
				"enabled": 1,
				"billable": 1,
				"billable_approval_reason": "test agreement",
			}
		).insert(ignore_permissions=True)
		generated, hand = self._sub_rental(), self._sub_rental()
		plan = [
			(1, 8, 0, None, 0, None, None),
			(2, 6, 3, reason.name, 2, "Other", "Site driver"),
			(3, 0, 0, reason.name, 5, "Supplier", self.supplier),
			(4, 0, 7, None, 0, None, None),
		]

		def party(kind, value):
			if kind == "Other":
				return {"responsible_party_type": kind, "responsible_party_name": value}
			return {"responsible_party_type": kind, "responsible_party": value} if kind else {}

		for n, day, night, stop, stopped, kind, value in plan:
			self._log(
				n,
				[
					{
						"equipment": generated.name,
						"day_hours": day,
						"night_hours": night,
						"stop_reason": stop,
						"stopped_hours": stopped,
						**party(kind, value),
					}
				],
			)
		result = self._run(equipment=generated.name)
		self.assertEqual(len(result["created"]), 2, result)
		fields = (
			"amount",
			"customer_amount",
			"net_amount",
			"customer_net_amount",
			"total_working_hours",
			"working_days",
			"billable_stopped_hours",
			"billable_stopped_days",
			"supplier_billable_stopped_hours",
			"customer_billable_stopped_hours",
		)
		for shift in (SHIFT_DAY, SHIFT_NIGHT):
			card = frappe.new_doc(CARD)
			card.update(
				{
					"company": self.company,
					"project": self.project,
					"equipment": hand.name,
					"month": self.card_month,
					"year": self.card_year,
					"shift": shift,
				}
			)
			for n, day, night, stop, stopped, kind, value in plan:
				row = {"operation_date": self._day(n), "day_status": "عمل", "working_hours": night}
				if shift == SHIFT_DAY:
					row.update(
						working_hours=day, stop_reason=stop, stopped_hours=stopped, **party(kind, value)
					)
				card.append("days", row)
			frappe.set_user(self.runner)
			card.insert()
			frappe.set_user("Administrator")
			name = frappe.db.get_value(CARD, {"equipment": generated.name, "shift": shift, "docstatus": 0})
			made = frappe.get_doc(CARD, name)
			with self.subTest(shift=shift):
				self.assertEqual({f: flt(made.get(f)) for f in fields}, {f: flt(card.get(f)) for f in fields})
		self.assertGreater(flt(frappe.db.get_value(CARD, name, "customer_amount")), 0)
		day_card = frappe.db.get_value(CARD, {"equipment": generated.name, "shift": SHIFT_DAY})
		self.assertEqual(flt(frappe.db.get_value(CARD, day_card, "billable_stopped_hours")), 7)

	def test_unit_component_days_from_dated_periods(self):
		for n in (1, 2, 3, 4):
			self._log(n, [self._row(8)])
		unit = self._equipment()
		row = frappe.new_doc("Card Equipment Component")
		row.update(
			{
				"parent": unit.name,
				"parenttype": "Card Equipment",
				"parentfield": "components",
				"component": self.eq.name,
				"from_date": self._day(2),
				"to_date": self._day(3),
				"idx": 1,
			}
		)
		row.db_insert()
		result = self._run()
		(card,) = result["created"]
		self.assertEqual(sorted(self._days(card)), [str(self._day(1)), str(self._day(4))])
		self.assertEqual(
			[(d["date"], d["reason"]) for d in result["skipped_days"]],
			[(str(self._day(2)), SKIP_UNIT_COMPONENT), (str(self._day(3)), SKIP_UNIT_COMPONENT)],
		)

	def test_verified_then_approved_with_the_supervisor_step(self):
		frappe.get_doc(
			{
				"doctype": "Card Daily Log Settings",
				"company": self.company,
				"require_supervisor_verification": 1,
			}
		).insert(ignore_permissions=True)
		supervisor = self._user("sup", ("Card Supervisor",), company=self.company)
		log = self._log(1, [self._row(8)], status=daily_log.PENDING)
		frappe.set_user(supervisor)
		doc = frappe.get_doc(LOG, log.name)
		doc.approval_status = daily_log.VERIFIED
		doc.save()
		frappe.set_user("Administrator")
		self.assertEqual(self._run()["created"], [], "a verified log is not approved yet")
		frappe.set_user(self.manager)
		doc = frappe.get_doc(LOG, log.name)
		doc.approval_status = daily_log.APPROVED
		doc.save()
		frappe.set_user("Administrator")
		frappe.clear_messages()
		(card,) = self._run()["created"]
		self.assertEqual(self._days(card)[str(self._day(1))].working_hours, 8)

	def test_missing_and_foreign_projects_get_the_same_answer(self):
		company_b = self._company_b()
		foreign = frappe.new_doc("Project")
		foreign.update({"project_name": "TEST-K2-FOREIGN-" + self.token, "company": company_b})
		foreign.name = "TEST-K2-FOREIGN-" + self.token
		foreign.db_insert()
		messages = []
		for project in (foreign.name, "TEST-K2-MISSING-" + self.token):
			frappe.set_user(self.runner)
			try:
				with self.assertRaises(frappe.DoesNotExistError) as caught:
					generate_monthly_cards(company=self.company, project=project, month=self.month)
				messages.append(str(caught.exception).replace(project, "<p>"))
			finally:
				frappe.set_user("Administrator")
				frappe.clear_messages()
		self.assertEqual(messages[0], messages[1])
		self.assertNotIn(company_b, messages[0])
