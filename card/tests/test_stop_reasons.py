# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-118 (#45, #123; WP-09): configurable stop reasons, the responsible party of a
stopped day and the Equipment Downtime report.

Proven here: a card without a reason bills exactly as before; a reason bills its stopped
hours only when it is explicitly billable; reasons are company-scoped; the seeding patch
is idempotent and touches no day row; the report is company-scoped, permission-aware and
writes nothing. All data is per-test and rolled back."""

from unittest.mock import patch

import frappe
from frappe.utils import flt, getdate

from card.card.report.equipment_downtime.equipment_downtime import execute as downtime
from card.patches.v4_6_0 import seed_stop_reasons
from card.patches.v4_8_0 import stop_reason_billable_side
from card.tests.test_customer import _CustomerCardsBase

WORK, LEAVE, BREAKDOWN, CLIENT_STOP = "عمل", "إجازة", "عطل", "توقف من العميل"
PERIOD = {"from_date": "2026-09-01", "to_date": "2026-09-30"}


class _StopBase(_CustomerCardsBase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _reason(
		self, name=None, company=None, billable=0, enabled=1, party_type=None, side=None, approval=None
	):
		return frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": company or self.company,
				"reason_name": name or ("TEST-STOP-" + frappe.generate_hash(length=6)),
				"billable": billable,
				"enabled": enabled,
				"default_responsible_party_type": party_type,
				"billable_side": side,
				# FR-134: a billable reason records its approval
				"billable_approval_reason": approval
				if approval is not None
				else ("TEST approval " + self.token if billable else None),
			}
		).insert(ignore_permissions=True)

	def _stop_card(self, eq, rows, submit=False):
		"""rows: dicts of day-row values; the day number is the position (1-based)."""
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
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

	def _other_company(self):
		name = "TEST-STOP-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "S" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _user(self, roles, restrict_to=None):
		email = f"stop-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Stop",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email


class TestDefaultsUnchanged(_StopBase):
	def test_card_without_reasons_bills_as_before(self):
		eq = self._sub_rental()  # supplier 75/h, customer 120/h
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": BREAKDOWN, "working_hours": 5},  # zeroed, as before
				{"day_status": CLIENT_STOP},
				{"day_status": LEAVE},
				# stopped hours without a reason are recorded only, never billed
				{"working_hours": 6, "stopped_hours": 2},
			],
		)
		self.assertEqual(flt(card.total_working_hours), 14)
		self.assertEqual(card.working_days, 2)
		self.assertEqual(flt(card.billable_stopped_hours), 0)
		self.assertEqual(flt(card.amount), 14 * 75.0)
		self.assertEqual(flt(card.customer_amount), 14 * 120.0)
		self.assertEqual(flt(card.days[1].working_hours), 0)
		self.assertFalse(any(row.reason_billable for row in card.days))
		# the fixed statuses are kept as they were
		self.assertEqual([row.day_status for row in card.days], [WORK, BREAKDOWN, CLIENT_STOP, LEAVE, WORK])

	def test_default_reason_is_not_billable(self):
		reason = frappe.get_doc(
			{"doctype": "Card Stop Reason", "company": self.company, "reason_name": "TEST-DEF-" + self.token}
		).insert(ignore_permissions=True)
		self.assertEqual(reason.billable, 0)
		self.assertEqual(reason.enabled, 1)
		self.assertTrue(reason.name.startswith("TEST-DEF-" + self.token + " - "))

	def test_non_billable_reason_earns_nothing(self):
		eq = self._sub_rental()
		reason = self._reason(billable=0)
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": BREAKDOWN, "stop_reason": reason.name, "stopped_hours": 10},
			],
		)
		self.assertEqual(flt(card.billable_stopped_hours), 0)
		self.assertEqual(flt(card.amount), 8 * 75.0)
		self.assertEqual(flt(card.customer_amount), 8 * 120.0)
		self.assertEqual(card.days[1].reason_billable, 0)


class TestBillableReason(_StopBase):
	def test_billable_reason_bills_its_stopped_hours_on_both_sides(self):
		eq = self._sub_rental()
		reason = self._reason(billable=1)
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"working_hours": 6, "stop_reason": reason.name, "stopped_hours": 2},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
			submit=True,
		)
		self.assertEqual(flt(card.total_working_hours), 14)  # operating hours only
		self.assertEqual(flt(card.billable_stopped_hours), 6)
		self.assertEqual(card.billable_stopped_days, 1)  # day 3 only; day 2 is a working day
		self.assertEqual(card.working_days, 2)
		self.assertEqual(flt(card.amount), 20 * 75.0)
		self.assertEqual(flt(card.customer_amount), 20 * 120.0)
		# the submitted card keeps the reason's billable flag of submit time
		frappe.db.set_value("Card Stop Reason", reason.name, "billable", 0)
		card.reload()
		self.assertEqual(card.days[2].reason_billable, 1)
		self.assertEqual(flt(card.amount), 20 * 75.0)

	def test_billable_stopped_day_outside_the_assignment_is_refused(self):
		eq = self._equipment()
		frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": eq.name,
				"project": self.project,
				"from_date": "2026-09-01",
				"to_date": "2026-09-01",
			}
		).insert(ignore_permissions=True)
		reason = self._reason(billable=1)
		# a non-billable stopped day there is fine (recorded only) ...
		self._stop_card(
			eq,
			[{"working_hours": 8}, {"day_status": CLIENT_STOP, "stopped_hours": 4}],
		).delete()
		# ... a billable one would bill a day the equipment was not on the project
		with self.assertRaisesRegex(frappe.ValidationError, "outside the equipment's assignment period"):
			self._stop_card(
				eq,
				[
					{"working_hours": 8},
					{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
				],
			)

	def test_stopped_hours_on_a_future_day_are_refused(self):
		eq = self._equipment()
		c = frappe.new_doc("Card Monthly Card")
		c.update(
			{"equipment": eq.name, "project": self.project, "shift": "نهاري", "month": "12", "year": 2026}
		)
		c.append("days", {"operation_date": "2026-12-30", "day_status": BREAKDOWN, "stopped_hours": 3})
		with patch(
			"card.card.doctype.card_monthly_card.card_monthly_card.nowdate", return_value="2026-12-01"
		):
			with self.assertRaisesRegex(frappe.ValidationError, "future day"):
				c.insert(ignore_permissions=True)


class TestReasonCompanyAndParty(_StopBase):
	def test_reason_of_another_company_is_refused(self):
		other = self._other_company()
		reason = self._reason(company=other)
		with self.assertRaises(frappe.PermissionError):
			self._stop_card(self._equipment(), [{"day_status": BREAKDOWN, "stop_reason": reason.name}])

	def test_disabled_reason_is_refused(self):
		reason = self._reason(enabled=0)
		with self.assertRaisesRegex(frappe.ValidationError, "disabled"):
			self._stop_card(self._equipment(), [{"day_status": BREAKDOWN, "stop_reason": reason.name}])

	def test_same_reason_name_is_allowed_once_per_company(self):
		other = self._other_company()
		self._reason(name="TEST-SAME-" + self.token)
		self._reason(name="TEST-SAME-" + self.token, company=other)
		with self.assertRaises(frappe.DuplicateEntryError):
			self._reason(name="TEST-SAME-" + self.token)

	def test_responsible_party_rules(self):
		reason = self._reason(party_type="Customer")
		other = self._other_company()
		card = self._stop_card(
			self._equipment(),
			[
				# no type given: the reason's default type is taken (the form picks the record)
				{"day_status": CLIENT_STOP, "stop_reason": reason.name},
				{"day_status": BREAKDOWN, "responsible_party_type": "Company"},
				{
					"day_status": BREAKDOWN,
					"responsible_party_type": "Other",
					"responsible_party_name": "Road closure",
				},
				{"day_status": LEAVE, "responsible_party_name": "dropped"},
				{
					"day_status": CLIENT_STOP,
					"stop_reason": reason.name,
					"responsible_party_type": "Customer",
					"responsible_party": self.customer,
					"responsible_party_name": "dropped",
				},
			],
		)
		self.assertEqual(card.days[0].responsible_party_type, "Customer")  # the reason's default
		self.assertEqual(card.days[1].responsible_party, self.company)  # the card's company
		self.assertEqual(card.days[2].responsible_party_name, "Road closure")
		self.assertFalse(card.days[2].responsible_party)
		self.assertFalse(card.days[3].responsible_party_name)
		self.assertEqual(card.days[4].responsible_party, self.customer)
		self.assertFalse(card.days[4].responsible_party_name)
		with self.assertRaises(frappe.ValidationError):
			self._stop_card(
				self._equipment(),
				[{"day_status": BREAKDOWN, "responsible_party_type": "Company", "responsible_party": other}],
			)

	def test_reasons_are_company_isolated_and_managed_by_card_managers(self):
		other = self._other_company()
		mine = self._reason()
		theirs = self._reason(company=other)
		user = self._user(["Card User"], restrict_to=self.company)
		frappe.set_user(user)
		names = frappe.get_list("Card Stop Reason", pluck="name", limit_page_length=0)
		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)
		self.assertFalse(frappe.has_permission("Card Stop Reason", "read", doc=theirs.name))
		self.assertFalse(frappe.has_permission("Card Stop Reason", "write", doc=mine.name))
		frappe.set_user("Administrator")
		manager = self._user(["Card Manager"], restrict_to=self.company)
		frappe.set_user(manager)
		self.assertTrue(frappe.has_permission("Card Stop Reason", "write", doc=mine.name))
		self.assertFalse(frappe.has_permission("Card Stop Reason", "write", doc=theirs.name))


class TestSeedPatch(_StopBase):
	def _seeded(self):
		return frappe.get_all(
			"Card Stop Reason",
			filters={"company": self.company, "day_status": ["is", "set"]},
			fields=["name", "day_status", "billable", "enabled"],
			order_by="name asc",
		)

	def test_seed_is_idempotent_and_keeps_billing_and_rows(self):
		eq = self._sub_rental()
		card = self._stop_card(
			eq, [{"working_hours": 8}, {"day_status": BREAKDOWN}, {"day_status": CLIENT_STOP}], submit=True
		)
		before = frappe.get_all(
			"Card Monthly Card Day",
			filters={"parent": card.name},
			fields=["name", "day_status", "working_hours", "stop_reason", "modified"],
			order_by="idx",
		)
		frappe.db.delete("Card Stop Reason", {"company": self.company})
		seed_stop_reasons.execute()
		seeded = self._seeded()
		self.assertEqual(sorted(r.day_status for r in seeded), sorted([LEAVE, BREAKDOWN, CLIENT_STOP]))
		self.assertTrue(all(r.billable == 0 and r.enabled == 1 for r in seeded))
		# an office change to a seeded reason survives a second run, and nothing is added
		frappe.db.set_value("Card Stop Reason", seeded[0].name, "enabled", 0)
		seed_stop_reasons.execute()
		again = self._seeded()
		self.assertEqual(len(again), 3)
		self.assertEqual(frappe.db.get_value("Card Stop Reason", seeded[0].name, "enabled"), 0)
		# no day row was rewritten
		after = frappe.get_all(
			"Card Monthly Card Day",
			filters={"parent": card.name},
			fields=["name", "day_status", "working_hours", "stop_reason", "modified"],
			order_by="idx",
		)
		self.assertEqual(before, after)
		self.assertEqual(flt(frappe.db.get_value("Card Monthly Card", card.name, "amount")), 8 * 75.0)

	def test_seeded_reasons_bill_what_the_statuses_bill(self):
		eq = self._sub_rental()
		self._stop_card(eq, [{"working_hours": 8}], submit=True)
		frappe.db.delete("Card Stop Reason", {"company": self.company})
		seed_stop_reasons.execute()
		by_status = {r.day_status: r.name for r in self._seeded()}
		plain = self._stop_card(
			self._sub_rental(),
			[{"working_hours": 8}, {"day_status": BREAKDOWN, "stopped_hours": 8}],
		)
		tagged = self._stop_card(
			self._sub_rental(),
			[
				{"working_hours": 8},
				{"day_status": BREAKDOWN, "stopped_hours": 8, "stop_reason": by_status[BREAKDOWN]},
			],
		)
		self.assertEqual(flt(plain.amount), flt(tagged.amount))
		self.assertEqual(flt(plain.customer_amount), flt(tagged.customer_amount))


class TestDowntimeReport(_StopBase):
	def _fixture(self):
		eq = self._sub_rental()
		billable = self._reason(name="TEST-BILL-" + self.token, billable=1, party_type="Customer")
		plain = self._reason(name="TEST-PLAIN-" + self.token)
		self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": BREAKDOWN},  # older style: no reason
				{
					"working_hours": 6,
					"stop_reason": billable.name,
					"stopped_hours": 2,
					"responsible_party_type": "Customer",
					"responsible_party": self.customer,
				},
				{"day_status": BREAKDOWN, "stop_reason": plain.name, "stopped_hours": 10},
			],
			submit=True,
		)
		return eq, billable, plain

	def test_hours_and_days_by_reason(self):
		eq, billable, plain = self._fixture()
		_cols, data, _msg, _chart, summary = downtime({"company": self.company, **PERIOD})
		groups = {row["group"]: row for row in data}
		# a row without a reason is shown under its (translated) day status
		self.assertEqual(groups[frappe._(BREAKDOWN)]["days"], 1)
		self.assertEqual(groups[billable.name]["stopped_hours"], 2)
		self.assertEqual(groups[billable.name]["billable_hours"], 2)
		self.assertEqual(groups[plain.name]["stopped_hours"], 10)
		self.assertEqual(groups[plain.name]["billable_hours"], 0)
		tiles = {t["label"]: t["value"] for t in summary}
		self.assertEqual(tiles["Stopped days"], 3)
		self.assertEqual(tiles["Stopped hours"], 12)
		self.assertEqual(tiles["Billable stopped hours"], 2)
		# by responsible party, equipment, project, month and each day
		_c, by_party, *_ = downtime({"company": self.company, "group_by": "Responsible party", **PERIOD})
		self.assertEqual({r["group"]: r["stopped_hours"] for r in by_party}["Customer: " + self.customer], 2)
		_c, by_eq, *_ = downtime({"company": self.company, "group_by": "Equipment", **PERIOD})
		self.assertEqual({r["group"]: r["days"] for r in by_eq}[eq.name], 3)
		_c, by_month, *_ = downtime({"company": self.company, "group_by": "Month", **PERIOD})
		self.assertEqual({r["group"]: r["days"] for r in by_month}["2026-09"], 3)
		_c, detail, *_ = downtime(
			{"company": self.company, "group_by": "Detail", "stop_reason": plain.name, **PERIOD}
		)
		self.assertEqual([r["stopped_hours"] for r in detail], [10])
		# draft cards only on request
		self._stop_card(self._sub_rental(), [{"day_status": LEAVE}])
		_c, drafts, *_ = downtime({"company": self.company, "group_by": "Detail", **PERIOD})
		self.assertFalse(any(r["draft"] for r in drafts))
		_c, drafts, *_ = downtime(
			{"company": self.company, "group_by": "Detail", "include_drafts": 1, **PERIOD}
		)
		self.assertTrue(any(r["draft"] for r in drafts))

	def test_company_scope_and_access(self):
		self._fixture()
		other = self._other_company()
		user = self._user(["Card User"], restrict_to=self.company)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			downtime({"company": other, **PERIOD})
		_c, data, *_ = downtime({"company": self.company, **PERIOD})
		self.assertTrue(data)
		frappe.set_user("Administrator")
		# a role that cannot read monthly cards may not run it
		frappe.set_user(self._user(["Card Supervisor"]))
		with self.assertRaises(frappe.PermissionError):
			downtime({"company": self.company, **PERIOD})

	def test_nothing_is_written(self):
		self._fixture()
		with (
			patch.object(frappe.db, "set_value", side_effect=AssertionError("write")),
			patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql,
		):
			for group_by in ("Reason", "Responsible party", "Equipment", "Project", "Month", "Detail"):
				downtime({"company": self.company, "group_by": group_by, **PERIOD})
		for call in sql.call_args_list:
			statement = str(call.args[0]).lstrip().lower() if call.args else ""
			self.assertFalse(statement.startswith(("insert", "update", "delete")), statement)


def _messages():
	return " | ".join(str(m.get("message", "")) for m in frappe.get_message_log())


STATEMENT = {"statement_type": "مورد", "from_month": 9, "from_year": 2026}


class TestReviewFixes(_StopBase):
	"""Review of PR #194 (M1, M2, M3, L1, L2, L3)."""

	def _set(self, field, value):
		frappe.db.set_single_value("Card Settings", field, value)
		frappe.clear_document_cache("Card Settings", "Card Settings")

	def _billable_stop_card(self, eq, submit=True, include_hours=True):
		reason = self._reason(billable=1)
		rows = [{"working_hours": 8}] if include_hours else [{"day_status": LEAVE}]
		rows.append({"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4})
		return self._stop_card(eq, rows, submit=submit)

	def _plain_stop_card(self, eq):
		plain = self._reason(billable=0)
		return self._stop_card(
			eq,
			[
				{"day_status": LEAVE},
				{"day_status": CLIENT_STOP, "stop_reason": plain.name, "stopped_hours": 4},
			],
			submit=True,
		)

	# ---- M1: a submitted billable stopped day keeps its assignment ----
	def test_card_day_after_sees_billable_stopped_days(self):
		from card.transfer import _card_day_after

		eq = self._equipment()
		self._billable_stop_card(eq, include_hours=False)  # day 2: billable stopped only
		self.assertTrue(_card_day_after(eq.name, self.project, getdate("2026-09-01")))
		other = self._equipment()
		self._plain_stop_card(other)
		self.assertFalse(_card_day_after(other.name, self.project, getdate("2026-09-01")))

	def test_assignment_change_refuses_to_drop_a_billable_stopped_day(self):
		from card.card.doctype.card_equipment_assignment.card_equipment_assignment import (
			_refuse_dropped_card_days,
		)

		eq = self._equipment()
		self._billable_stop_card(eq, include_hours=False)
		with self.assertRaisesRegex(frappe.ValidationError, "outside the assignment"):
			_refuse_dropped_card_days(eq.name, self.project, "2026-09-02", "2026-09-30")
		other = self._equipment()
		self._plain_stop_card(other)
		_refuse_dropped_card_days(other.name, self.project, "2026-09-02", "2026-09-30")  # nothing billed

	# ---- M2: 24-hour day and the shift warning ----
	def test_operating_and_stopped_hours_over_24_are_refused(self):
		reason = self._reason(billable=0)
		with self.assertRaisesRegex(frappe.ValidationError, "exceed 24 hours"):
			self._stop_card(
				self._equipment(), [{"working_hours": 20, "stop_reason": reason.name, "stopped_hours": 5}]
			)
		card = self._stop_card(
			self._equipment(), [{"working_hours": 20, "stop_reason": reason.name, "stopped_hours": 4}]
		)
		self.assertEqual(flt(card.total_working_hours), 20)  # exactly 24 is a full day

	def test_billable_stopped_hours_count_in_the_shift_warning(self):
		self._set("max_day_shift_hours", 12)
		billable = self._reason(billable=1)
		plain = self._reason(billable=0)
		frappe.local.message_log = []
		self._stop_card(
			self._equipment(),
			[
				{"working_hours": 10, "stop_reason": billable.name, "stopped_hours": 4},
				{"working_hours": 10, "stop_reason": plain.name, "stopped_hours": 4},
			],
		)
		messages = _messages()
		self.assertIn("2026-09-01 (14.0)", messages)
		self.assertNotIn("2026-09-02", messages)

	# ---- L1: the client cannot make a stop billable ----
	def test_client_sent_billable_flag_is_ignored(self):
		plain = self._reason(billable=0)
		card = self._stop_card(
			self._sub_rental(),
			[
				{"working_hours": 8},
				{
					"day_status": BREAKDOWN,
					"stop_reason": plain.name,
					"stopped_hours": 4,
					"reason_billable": 1,
				},
				{"day_status": BREAKDOWN, "stopped_hours": 4, "reason_billable": 1},
			],
		)
		self.assertEqual(flt(card.billable_stopped_hours), 0)
		self.assertEqual([row.reason_billable for row in card.days], [0, 0, 0])
		self.assertEqual(flt(card.amount), 8 * 75.0)
		self.assertEqual(flt(card.customer_amount), 8 * 120.0)

	# ---- L2: a foreign responsible party is flagged, never blocked ----
	def test_foreign_responsible_party_warns(self):
		other = self._customer("-B")
		frappe.local.message_log = []
		card = self._stop_card(
			self._rented_out(),
			[
				{"day_status": CLIENT_STOP, "responsible_party_type": "Customer", "responsible_party": other},
				{
					"day_status": CLIENT_STOP,
					"responsible_party_type": "Customer",
					"responsible_party": self.customer,
				},
			],
		)
		self.assertTrue(card.name)
		messages = _messages()
		self.assertIn("not the card's own supplier or customer", messages)
		self.assertIn(other, messages)
		self.assertNotIn("2026-09-02", messages)

	# ---- M3: statements and summaries ----
	def test_supplier_statement_shows_billable_stopped_hours(self):
		from card.card.report.equipment_supplier_statement.equipment_supplier_statement import (
			execute as supplier_statement,
		)

		card = self._billable_stop_card(self._equipment())  # rented in: 75/h
		filters = {**STATEMENT, "company": self.company, "supplier": self.supplier, "project": self.project}
		columns, rows, *_ = supplier_statement(filters)
		self.assertIn("stopped_hours", [c["fieldname"] for c in columns])
		row = next(r for r in rows if r.get("card") == card.name)
		self.assertEqual(row["hours"], 8)
		self.assertEqual(row["stopped_hours"], 4)
		self.assertEqual(row["working_days"], 2)  # the billable stopped day counts
		self.assertEqual(row["hourly_rate"], 75.0)  # 900 over 12 billed hours
		self.assertEqual(row["amount"], 12 * 75.0)
		total = next(r for r in rows if r.get("row_id") == "TOTAL")
		self.assertEqual(total["stopped_hours"], 4)
		# a draft: its amount over every billed hour
		draft = self._billable_stop_card(self._equipment(), submit=False)
		_c, rows, *_ = supplier_statement({**filters, "include_draft": 1})
		self.assertEqual(next(r for r in rows if r.get("card") == draft.name)["hourly_rate"], 75.0)

	def test_statement_column_is_hidden_without_billable_stops(self):
		from card.card.report.equipment_supplier_statement.equipment_supplier_statement import (
			execute as supplier_statement,
		)
		from card.card.report.equipment_supplier_statement.statement_pdf import MONEY_FIELDS, _shown_fields

		card = self._stop_card(self._equipment(), [{"working_hours": 8}], submit=True)
		columns, rows, *_ = supplier_statement(
			{**STATEMENT, "company": self.company, "supplier": self.supplier, "project": self.project}
		)
		self.assertNotIn("stopped_hours", [c["fieldname"] for c in columns])
		self.assertEqual(next(r for r in rows if r.get("card") == card.name)["hourly_rate"], 75.0)
		# the print keeps the approved columns; the stopped hours column joins only when a row has a value
		plain = _shown_fields(MONEY_FIELDS, [{"hours": 8}])
		self.assertNotIn("stopped_hours", [f[0] for f in plain])
		with_stops = _shown_fields(MONEY_FIELDS, [{"hours": 8, "stopped_hours": 4}])
		names = [f[0] for f in with_stops]
		self.assertEqual(names[names.index("hours") + 1], "stopped_hours")
		self.assertAlmostEqual(sum(f[1] for f in with_stops), 97, places=0)

	def test_customer_statement_and_summaries_show_billable_stopped_hours(self):
		from card.card.report.equipment_customer_statement.equipment_customer_statement import (
			execute as customer_statement,
		)
		from card.card.report.equipment_customers_summary.equipment_customers_summary import (
			execute as customers_summary,
		)
		from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import (
			execute as suppliers_summary,
		)

		card = self._billable_stop_card(self._sub_rental())  # supplier 75/h, customer 120/h
		period = {"company": self.company, "from_month": 9, "from_year": 2026, "project": self.project}
		columns, rows, *_ = customer_statement({**period, "customer": self.customer})
		self.assertIn("stopped_hours", [c["fieldname"] for c in columns])
		row = next(r for r in rows if r.get("card") == card.name)
		self.assertEqual(row["stopped_hours"], 4)
		self.assertEqual(row["working_days"], 2)
		self.assertEqual(flt(row["hourly_rate"]), 120.0)
		self.assertEqual(row["customer_amount"], 12 * 120.0)
		for report, key, party in (
			(customers_summary, "customer", self.customer),
			(suppliers_summary, "supplier", self.supplier),
		):
			columns, rows, *_ = report(period)
			self.assertIn("stopped_hours", [c["fieldname"] for c in columns], key)
			row = next(r for r in rows if r.get(key) == party)
			self.assertEqual(row["stopped_hours"], 4, key)
			self.assertEqual(row["working_days"], 2, key)
			total = next(r for r in rows if r.get("is_total"))
			self.assertGreaterEqual(total["stopped_hours"], 4, key)

	# ---- L3: the internal value counts billable stopped hours per hour ----
	def test_internal_value_counts_billable_stopped_hours(self):
		from card.card_value import card_value
		from card.constants import DIR_INTERNAL, OWNED

		card = frappe._dict(
			ownership=OWNED,
			card_direction=DIR_INTERNAL,
			total_working_hours=8,
			billable_stopped_hours=4,
			working_days=1,
		)
		per_hour = frappe._dict(internal_rate=10, internal_rate_basis="بالساعة")
		per_day = frappe._dict(internal_rate=100, internal_rate_basis="باليوم")
		self.assertEqual(card_value(card, per_hour)["internal"], 120.0)
		self.assertEqual(card_value(card, per_day)["internal"], 100.0)
		# per day, a day billed only by a billable stop counts like a working day
		card.billable_stopped_days = 1
		self.assertEqual(card_value(card, per_day)["internal"], 200.0)
		card.billable_stopped_days = 0
		card.billable_stopped_hours = 0
		self.assertEqual(card_value(card, per_hour)["internal"], 80.0)

	def test_supplier_statement_hourly_rate_is_amount_over_hours_not_the_snapshot(self):
		"""Re-review of PR #194: an older submit snapshot (v1.2 backfill) can differ from amount / hours; the
		statement keeps showing amount / hours for a card without billable stops, as before."""
		from card.card.report.equipment_supplier_statement.equipment_supplier_statement import (
			execute as supplier_statement,
		)

		eq = self._equipment(rate_type="باليوم", rate=1000, daily_hours=9)  # 111.111.../h
		card = self._stop_card(eq, [{"working_hours": 7}], submit=True)
		self.assertEqual(flt(card.amount), 777.78)
		frappe.db.set_value("Card Monthly Card", card.name, "hourly_rate_used", 120, update_modified=False)
		_c, rows, *_ = supplier_statement(
			{**STATEMENT, "company": self.company, "supplier": self.supplier, "project": self.project}
		)
		row = next(r for r in rows if r.get("card") == card.name)
		self.assertEqual(row["hourly_rate"], flt(777.78 / 7, 2))
		self.assertNotEqual(row["hourly_rate"], 120)


class TestBillableSide(_StopBase):
	"""FR-134 (#45, C-07): a billable reason names its side and its approval reason."""

	def test_default_side_is_both_and_billable_stays_off(self):
		reason = self._reason()
		self.assertEqual(reason.billable, 0)
		self.assertEqual(reason.billable_side, "Both")
		self.assertFalse(reason.billable_approval_reason)

	def test_billable_reason_needs_an_approval_reason(self):
		with self.assertRaisesRegex(frappe.ValidationError, "billable approval reason"):
			self._reason(billable=1, approval="  ")
		reason = self._reason(billable=0)
		reason.billable = 1
		with self.assertRaisesRegex(frappe.ValidationError, "billable approval reason"):
			reason.save(ignore_permissions=True)
		reason.reload()
		reason.billable = 1
		reason.billable_approval_reason = "Agreed with the customer, letter 12"
		reason.save(ignore_permissions=True)
		self.assertEqual(reason.billable_side, "Both")

	def test_invalid_side_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._reason(billable=1, side="Nobody")

	def test_both_side_bills_both_amounts_as_before(self):
		eq = self._sub_rental()  # 75/h supplier, 120/h customer
		reason = self._reason(billable=1, side="Both")
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
		)
		self.assertEqual(flt(card.billable_stopped_hours), 4)
		self.assertEqual(flt(card.amount), 12 * 75.0)
		self.assertEqual(flt(card.customer_amount), 12 * 120.0)

	def test_supplier_side_on_sub_rental_bills_the_supplier_only(self):
		eq = self._sub_rental()
		reason = self._reason(billable=1, side="Supplier")
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
		)
		self.assertEqual(card.days[1].reason_billable, 1)
		self.assertEqual(flt(card.amount), 12 * 75.0)
		self.assertEqual(flt(card.customer_amount), 8 * 120.0)

	def test_customer_side_on_sub_rental_bills_the_customer_only(self):
		eq = self._sub_rental()
		reason = self._reason(billable=1, side="Customer")
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
		)
		self.assertEqual(flt(card.amount), 8 * 75.0)
		self.assertEqual(flt(card.customer_amount), 12 * 120.0)

	def test_side_the_card_does_not_bill_is_not_billable(self):
		# a rented-in card bills the supplier only: a Customer reason earns nothing on it
		eq = self._equipment()
		reason = self._reason(billable=1, side="Customer")
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
		)
		self.assertEqual(card.days[1].reason_billable, 0)
		self.assertEqual(flt(card.billable_stopped_hours), 0)
		self.assertEqual(card.billable_stopped_days, 0)
		self.assertEqual(flt(card.amount), 8 * 75.0)

	def test_matching_side_on_single_side_card_bills(self):
		eq = self._equipment()
		reason = self._reason(billable=1, side="Supplier")
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
		)
		self.assertEqual(card.days[1].reason_billable, 1)
		self.assertEqual(flt(card.amount), 12 * 75.0)

	def test_patch_sets_both_on_rows_without_a_side_and_is_idempotent(self):
		reason = self._reason(billable=1, side="Supplier")
		legacy = self._reason()
		frappe.db.set_value("Card Stop Reason", legacy.name, "billable_side", None, update_modified=False)
		stop_reason_billable_side.execute()
		stop_reason_billable_side.execute()
		self.assertEqual(frappe.db.get_value("Card Stop Reason", legacy.name, "billable_side"), "Both")
		self.assertEqual(frappe.db.get_value("Card Stop Reason", reason.name, "billable_side"), "Supplier")
		self.assertEqual(frappe.db.get_value("Card Stop Reason", legacy.name, "billable"), 0)

	def test_stop_reason_is_audited(self):
		self.assertEqual(frappe.get_meta("Card Stop Reason").track_changes, 1)
