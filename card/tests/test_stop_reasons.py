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
from frappe.utils import flt

from card.card.report.equipment_downtime.equipment_downtime import execute as downtime
from card.patches.v4_6_0 import seed_stop_reasons
from card.tests.test_customer import _CustomerCardsBase

WORK, LEAVE, BREAKDOWN, CLIENT_STOP = "عمل", "إجازة", "عطل", "توقف من العميل"
PERIOD = {"from_date": "2026-09-01", "to_date": "2026-09-30"}


class _StopBase(_CustomerCardsBase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _reason(self, name=None, company=None, billable=0, enabled=1, party_type=None):
		return frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": company or self.company,
				"reason_name": name or ("TEST-STOP-" + frappe.generate_hash(length=6)),
				"billable": billable,
				"enabled": enabled,
				"default_responsible_party_type": party_type,
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
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "responsible_party": self.customer},
				{"day_status": BREAKDOWN, "responsible_party_type": "Company"},
				{
					"day_status": BREAKDOWN,
					"responsible_party_type": "Other",
					"responsible_party_name": "Road closure",
				},
				{"day_status": LEAVE, "responsible_party_name": "dropped"},
			],
		)
		self.assertEqual(card.days[0].responsible_party_type, "Customer")  # the reason's default
		self.assertEqual(card.days[0].responsible_party, self.customer)
		self.assertEqual(card.days[1].responsible_party, self.company)  # the card's company
		self.assertEqual(card.days[2].responsible_party_name, "Road closure")
		self.assertFalse(card.days[2].responsible_party)
		self.assertFalse(card.days[3].responsible_party_name)
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
				{"working_hours": 6, "stop_reason": billable.name, "stopped_hours": 2},
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
