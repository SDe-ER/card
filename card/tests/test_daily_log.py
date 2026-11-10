# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-142 (#44, #123, FR-022): the Card Daily Log.

Proven here: the row rules shared with the monthly card day rows (advisory shift limits, assignment on the log
date, equipment status rule, stop reasons of the same company, 24 hours, future day), the duplicate guard (same
date, project and equipment), the approval transitions on every route (form save, REST, ``frappe.client``), the
no-self-approval rule per company (Warn by default, Refuse when set, no role exempt), the REST insert with
docstatus 1, and the company isolation (rows, project, record, list, amendment). All data is per-test and rolled
back; no role is widened."""

from unittest.mock import patch

import frappe
from frappe.client import insert as rest_insert
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from card import daily_log
from card.company_scope import company_query_conditions, has_company_permission
from card.constants import STATUS_RULE_ENFORCE
from card.tests.test_customer import _CustomerCardsBase

LOG = "Card Daily Log"
SETTINGS = "Card Daily Log Settings"


class TestDailyLog(_CustomerCardsBase):
	def setUp(self):
		super().setUp()
		self.day = add_days(nowdate(), -3)
		self.eq = self._equipment()
		self.eq2 = self._equipment()
		self.operator = self._user("op", ("Card Operator",))
		self.supervisor = self._user("sup", ("Card Supervisor",))
		self.manager = self._user("mgr", ("Card Manager",))

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# ---------- builders ----------
	def _user(self, prefix, roles, company=None, applicable_for=None):
		email = f"dl-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Daily log " + prefix,
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
					"apply_to_all_doctypes": 0 if applicable_for else 1,
					"applicable_for": applicable_for,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _doc(self, rows=None, **values):
		doc = frappe.new_doc(LOG)
		doc.update({"company": self.company, "project": self.project, "log_date": self.day, **values})
		for row in rows if rows is not None else [{"equipment": self.eq.name, "day_hours": 8}]:
			doc.append("rows", row)
		return doc

	def _log(self, rows=None, submit=True, user=None, **values):
		frappe.set_user(user or self.operator)
		try:
			doc = self._doc(rows, **values).insert()
			if submit:
				doc.submit()
			return doc
		finally:
			frappe.set_user("Administrator")

	def _set_status(self, doc, status, user, reason=None):
		frappe.set_user(user)
		try:
			doc = frappe.get_doc(LOG, doc.name)
			doc.approval_status = status
			if reason is not None:
				doc.return_reason = reason
			doc.save()
			return doc
		finally:
			frappe.set_user("Administrator")

	def _assign(self, equipment, from_date, to_date=None, project=None):
		a = frappe.new_doc("Card Equipment Assignment")
		a.update({"equipment": equipment, "project": project or self.project, "from_date": from_date})
		if to_date:
			a.to_date = to_date
		a.insert(ignore_permissions=True)
		return a

	def _reason(self, company=None, enabled=1):
		return frappe.get_doc(
			{
				"doctype": "Card Stop Reason",
				"company": company or self.company,
				"reason_name": "TEST-DL-STOP-" + frappe.generate_hash(length=6),
				"enabled": enabled,
			}
		).insert(ignore_permissions=True)

	def _raw(self, doctype, name, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = name
		doc.db_insert()  # no validation: only the stored values matter here
		return name

	def _company_b(self):
		name = "TEST-DL-CO-" + self.token
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

	def _rule(self, rule=None, verification=0):
		frappe.get_doc(
			{
				"doctype": SETTINGS,
				"company": self.company,
				"self_approval_rule": rule or daily_log.RULE_WARN,
				"require_supervisor_verification": verification,
			}
		).insert(ignore_permissions=True)

	# ---------- entry and submit ----------
	def test_operator_enters_and_submits(self):
		doc = self._log()
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.approval_status, daily_log.PENDING)
		self.assertEqual(doc.submitted_by, self.operator)
		self.assertEqual(doc.edited_by, self.operator)
		self.assertFalse(doc.approved_by)

	def test_supervisor_enters_and_submits(self):
		doc = self._log(user=self.supervisor, supervisor=self.supervisor)
		self.assertEqual(doc.submitted_by, self.supervisor)

	def test_every_editor_is_recorded(self):
		doc = self._log(submit=False)
		frappe.set_user(self.supervisor)
		doc = frappe.get_doc(LOG, doc.name)
		doc.rows[0].day_hours = 9
		doc.save()
		doc.submit()
		frappe.set_user("Administrator")
		self.assertEqual(doc.edited_by.split("\n"), [self.operator, self.supervisor])
		self.assertEqual(doc.submitted_by, self.supervisor)
		self.assertEqual(daily_log.log_preparers(doc), {self.operator, self.supervisor})

	def test_rest_insert_with_docstatus_1_stays_pending(self):
		"""A client cannot approve through the insert: every approval field is the server's."""
		frappe.set_user(self.operator)
		result = rest_insert(
			{
				"doctype": LOG,
				"docstatus": 1,
				"company": self.company,
				"project": self.project,
				"log_date": self.day,
				"approval_status": "Approved",
				"approved_by": self.manager,
				"approved_on": "2026-01-01 00:00:00",
				"self_approved": 0,
				"submitted_by": self.manager,
				"edited_by": self.manager,
				"rows": [{"equipment": self.eq.name, "day_hours": 7}],
			}
		)
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(
			LOG,
			result["name"],
			["docstatus", "approval_status", "approved_by", "approved_on", "submitted_by", "edited_by"],
			as_dict=True,
		)
		self.assertEqual(stored.docstatus, 1)
		self.assertEqual(stored.approval_status, daily_log.PENDING)
		self.assertFalse(stored.approved_by)
		self.assertFalse(stored.approved_on)
		self.assertEqual(stored.submitted_by, self.operator)
		self.assertEqual(stored.edited_by, self.operator)
		# and the manager can still approve it (he did not prepare it)
		self.assertEqual(
			self._set_status(frappe._dict(name=result["name"]), "Approved", self.manager).approval_status,
			daily_log.APPROVED,
		)

	def test_card_user_cannot_create(self):
		viewer = self._user("view", ("Card User",))
		frappe.set_user(viewer)
		with self.assertRaises(frappe.PermissionError):
			self._doc().insert()

	# ---------- approval ----------
	def test_manager_approves(self):
		doc = self._set_status(self._log(), "Approved", self.manager)
		self.assertEqual(doc.approval_status, daily_log.APPROVED)
		self.assertEqual(doc.approved_by, self.manager)
		self.assertTrue(doc.approved_on)
		self.assertEqual(doc.self_approved, 0)

	def test_only_an_approver_approves_or_returns(self):
		doc = self._log()
		for user in (self.operator, self.supervisor):
			for status, reason in (("Approved", None), (daily_log.RETURNED, "wrong hours")):
				with self.subTest(user=user, status=status), self.assertRaises(frappe.PermissionError):
					self._set_status(doc, status, user, reason)
		self.assertEqual(frappe.db.get_value(LOG, doc.name, "approval_status"), daily_log.PENDING)

	def test_approval_through_rest_set_value_is_checked(self):
		doc = self._log()
		frappe.set_user(self.supervisor)
		with self.assertRaises(frappe.PermissionError):
			rest_set_value(LOG, doc.name, "approval_status", "Approved")
		frappe.set_user(self.manager)
		rest_set_value(LOG, doc.name, "approval_status", "Approved")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(LOG, doc.name, "approved_by"), self.manager)

	def test_client_cannot_write_approval_fields(self):
		doc = self._log()
		frappe.set_user(self.operator)
		doc = frappe.get_doc(LOG, doc.name)
		doc.approved_by = self.manager
		doc.self_approved = 1
		doc.return_reason = "typed by the client"
		doc.save()
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(
			LOG, doc.name, ["approval_status", "approved_by", "self_approved", "return_reason"], as_dict=True
		)
		self.assertEqual(
			stored,
			{"approval_status": "Pending", "approved_by": None, "self_approved": 0, "return_reason": None},
		)

	def test_return_needs_a_reason_and_is_final(self):
		doc = self._log()
		with self.assertRaises(frappe.ValidationError):
			self._set_status(doc, daily_log.RETURNED, self.manager, "   ")
		doc = self._set_status(doc, daily_log.RETURNED, self.manager, " hours do not match the paper sheet ")
		self.assertEqual(doc.approval_status, daily_log.RETURNED)
		self.assertEqual(doc.return_reason, "hours do not match the paper sheet")
		self.assertEqual(doc.returned_by, self.manager)
		self.assertTrue(doc.returned_on)
		for status in ("Approved", "Pending"):
			with self.subTest(status=status), self.assertRaises(frappe.ValidationError):
				self._set_status(doc, status, self.manager)
		# correction: cancel and amend
		frappe.set_user(self.operator)
		doc = frappe.get_doc(LOG, doc.name)
		doc.cancel()
		amended = frappe.copy_doc(doc)
		amended.docstatus = 0
		amended.amended_from = doc.name
		amended.rows[0].day_hours = 6
		amended.insert()
		frappe.set_user("Administrator")
		self.assertEqual(amended.approval_status, daily_log.PENDING)
		self.assertFalse(amended.return_reason)

	def test_approved_log_is_final(self):
		doc = self._set_status(self._log(), "Approved", self.manager)
		with self.assertRaises(frappe.ValidationError):
			self._set_status(doc, daily_log.RETURNED, self.manager, "late")

	# ---------- no self-approval (FR-121 style, per company) ----------
	def test_self_approval_warns_by_default(self):
		self.assertEqual(daily_log.self_approval_rule(self.company), daily_log.RULE_WARN)
		doc = self._log(user=self.manager)
		doc = self._set_status(doc, "Approved", self.manager)
		self.assertEqual(doc.approval_status, daily_log.APPROVED)
		self.assertEqual(doc.self_approved, 1)
		messages = [m.get("message", m) if isinstance(m, dict) else m for m in frappe.get_message_log()]
		self.assertTrue(any("approve it yourself" in str(m) for m in messages))

	def test_self_approval_refused_when_the_company_says_so(self):
		self._rule(daily_log.RULE_REFUSE)
		doc = self._log(user=self.manager)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, "Approved", self.manager)
		# another approver may
		other = self._user("mgr2", ("Card Manager",))
		self.assertEqual(self._set_status(doc, "Approved", other).self_approved, 0)

	def test_editor_and_submitter_are_preparers_too(self):
		self._rule(daily_log.RULE_REFUSE)
		doc = self._log(submit=False)
		frappe.set_user(self.manager)
		doc = frappe.get_doc(LOG, doc.name)
		doc.notes = "checked"
		doc.save()
		frappe.set_user("Administrator")
		frappe.set_user(self.operator)
		frappe.get_doc(LOG, doc.name).submit()
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, "Approved", self.manager)

	def test_no_role_is_exempt(self):
		self._rule(daily_log.RULE_REFUSE)
		doc = self._log(user="Administrator")
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, "Approved", "Administrator")

	def test_rule_of_another_company_does_not_apply(self):
		other = self._company_b()
		frappe.get_doc(
			{"doctype": SETTINGS, "company": other, "self_approval_rule": daily_log.RULE_REFUSE}
		).insert(ignore_permissions=True)
		self.assertEqual(daily_log.self_approval_rule(self.company), daily_log.RULE_WARN)
		self.assertEqual(daily_log.self_approval_rule(other), daily_log.RULE_REFUSE)

	def test_approved_log_cancelled_by_an_approver_only(self):
		doc = self._set_status(self._log(), "Approved", self.manager)
		frappe.set_user(self.operator)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(LOG, doc.name).cancel()
		frappe.set_user(self.manager)
		frappe.get_doc(LOG, doc.name).cancel()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(LOG, doc.name, "docstatus"), 2)

	# ---------- row rules shared with the monthly card ----------
	def test_shift_limit_only_warns(self):
		doc = self._log([{"equipment": self.eq.name, "day_hours": 14, "night_hours": 9.5}])
		self.assertEqual(doc.docstatus, 1)
		self.assertTrue(any("shift limit" in str(m) for m in frappe.get_message_log()))

	def test_24_hours_and_negative_and_future(self):
		with self.assertRaises(frappe.ValidationError):
			self._log([{"equipment": self.eq.name, "day_hours": 12, "night_hours": 10, "stopped_hours": 3}])
		with self.assertRaises(frappe.ValidationError):
			self._log([{"equipment": self.eq.name, "day_hours": -1}])
		with self.assertRaises(frappe.ValidationError):
			self._log(log_date=add_days(nowdate(), 1))
		# a future log without hours is a plan, as a monthly card row without hours
		self.assertEqual(
			self._log([{"equipment": self.eq.name}], log_date=add_days(nowdate(), 1)).docstatus, 1
		)

	def test_equipment_listed_twice_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._log(
				[{"equipment": self.eq.name, "day_hours": 4}, {"equipment": self.eq.name, "night_hours": 4}]
			)

	def test_assignment_on_the_log_date(self):
		self._assign(self.eq.name, add_days(self.day, 1))
		with self.assertRaises(frappe.ValidationError):
			self._log()
		self._assign(self.eq.name, add_days(self.day, -10), add_days(self.day, 0))
		self.assertEqual(self._log().docstatus, 1)

	def test_assignment_checked_for_stopped_hours_too(self):
		self._assign(self.eq.name, add_days(self.day, 1))
		reason = self._reason()
		with self.assertRaises(frappe.ValidationError):
			self._log([{"equipment": self.eq.name, "stop_reason": reason.name, "stopped_hours": 5}])

	def test_equipment_without_assignment_history_is_not_checked(self):
		# the monthly card rule (backward compatible)
		self.assertFalse(frappe.db.exists("Card Equipment Assignment", {"equipment": self.eq.name}))
		self.assertEqual(self._log().docstatus, 1)

	def test_equipment_status(self):
		frappe.db.set_value(
			"Card Equipment", self.eq.name, {"status": "منتهية", "exit_date": add_days(self.day, -5)}
		)
		# Warn only (the default): saved with a message
		self.assertEqual(self._log().docstatus, 1)
		with patch("card.equipment_status.status_rule", return_value=STATUS_RULE_ENFORCE):
			with self.assertRaises(frappe.ValidationError):
				self._log([{"equipment": self.eq.name, "day_hours": 2}], log_date=add_days(self.day, 1))
			# the exit day itself is the last work, not a new use
			self.assertEqual(self._log(log_date=add_days(self.day, -5)).docstatus, 1)

	def test_stop_reasons(self):
		reason = self._reason()
		doc = self._log([{"equipment": self.eq.name, "stop_reason": reason.name, "stopped_hours": 3}])
		self.assertEqual(doc.rows[0].stop_reason, reason.name)
		disabled = self._reason(enabled=0)
		with self.assertRaises(frappe.ValidationError):
			self._log([{"equipment": self.eq2.name, "stop_reason": disabled.name, "stopped_hours": 3}])
		foreign = self._raw(
			"Card Stop Reason",
			"TEST-DL-FOREIGN-" + self.token,
			company=self._company_b(),
			reason_name="foreign",
			enabled=1,
		)
		with self.assertRaises(frappe.PermissionError):
			self._log([{"equipment": self.eq2.name, "stop_reason": foreign, "stopped_hours": 3}])

	# ---------- duplicates ----------
	def test_duplicate_log_same_date_project_equipment(self):
		first = self._log()
		with self.assertRaises(frappe.DuplicateEntryError):
			self._log(
				[{"equipment": self.eq2.name, "day_hours": 2}, {"equipment": self.eq.name, "day_hours": 3}]
			)
		# a draft counts as well
		draft = self._log([{"equipment": self.eq2.name, "day_hours": 2}], submit=False)
		with self.assertRaises(frappe.DuplicateEntryError):
			self._log([{"equipment": self.eq2.name, "day_hours": 1}])
		# another date or a cancelled log does not
		self.assertEqual(self._log(log_date=add_days(self.day, -1)).docstatus, 1)
		frappe.set_user(self.operator)
		frappe.get_doc(LOG, first.name).cancel()
		frappe.set_user("Administrator")
		frappe.delete_doc(LOG, draft.name)
		self.assertEqual(
			self._log(
				[{"equipment": self.eq.name}, {"equipment": self.eq2.name, "night_hours": 1}]
			).docstatus,
			1,
		)

	def test_saving_the_same_log_again_is_not_a_duplicate(self):
		doc = self._log(
			[{"equipment": self.eq.name, "day_hours": 8}, {"equipment": self.eq2.name}], submit=False
		)
		frappe.set_user(self.operator)
		for hours in (5, 6):
			doc = frappe.get_doc(LOG, doc.name)
			doc.rows[0].day_hours = hours
			doc.save()  # the log's own rows are never a duplicate of themselves
		doc.submit()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(LOG, doc.name, "docstatus"), 1)
		self.assertEqual(getdate(frappe.db.get_value(LOG, doc.name, "log_date")), getdate(self.day))
		rows = frappe.get_all(
			"Card Daily Log Row",
			filters={"parent": doc.name},
			fields=["equipment", "day_hours"],
			order_by="idx",
		)
		self.assertEqual([(r.equipment, r.day_hours) for r in rows], [(self.eq.name, 6), (self.eq2.name, 0)])
		self.assertEqual(
			frappe.db.count(LOG, {"project": self.project, "log_date": self.day, "docstatus": ["<", 2]}), 1
		)

	# ---------- company isolation ----------
	def test_row_equipment_of_another_company_is_refused(self):
		other = self._company_b()
		eq_b = self._raw("Card Equipment", "TEST-DL-EQB-" + self.token, company=other, equipment_name="B")
		with self.assertRaises(frappe.ValidationError):
			self._log([{"equipment": eq_b, "day_hours": 2}])

	def test_project_of_another_company_is_refused(self):
		other = self._company_b()
		proj_b = self._raw(
			"Project", "TEST-DL-PB-" + self.token, project_name="PB" + self.token, company=other
		)
		with self.assertRaises(frappe.ValidationError):
			self._log(project=proj_b)

	def test_cross_company_record_refused_for_a_restricted_user(self):
		other = self._company_b()
		proj_b = self._raw(
			"Project", "TEST-DL-PB-" + self.token, project_name="PB" + self.token, company=other
		)
		log_b = self._raw(
			LOG, "TEST-DL-LB-" + self.token, company=other, project=proj_b, log_date=self.day, docstatus=1
		)
		log_a = self._log()
		user = self._user("restricted-mgr", ("Card Manager",), company=self.company)
		self.assertTrue(frappe.has_permission(LOG, "read", log_a.name, user=user))
		self.assertFalse(frappe.has_permission(LOG, "read", log_b, user=user))
		self.assertFalse(has_company_permission(frappe.get_doc(LOG, log_b), "write", user=user))
		condition = company_query_conditions(user=user, doctype=LOG)
		rows = frappe.db.sql(
			f"select name from `tab{LOG}` where name in %(n)s and {condition}",
			{"n": [log_a.name, log_b]},
			pluck=True,
		)
		self.assertEqual(rows, [log_a.name])
		# nor can he approve it, through any route
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			rest_set_value(LOG, log_b, "approval_status", "Approved")
		# nor create a log in the other company
		with self.assertRaises(frappe.PermissionError):
			self._doc([{"equipment": self.eq.name}], company=other, project=proj_b).insert()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(LOG, log_b, "approval_status"), "Pending")

	def test_amendment_of_another_company_log_is_refused(self):
		other = self._company_b()
		proj_b = self._raw(
			"Project", "TEST-DL-PB-" + self.token, project_name="PB" + self.token, company=other
		)
		log_b = self._raw(
			LOG, "TEST-DL-LB-" + self.token, company=other, project=proj_b, log_date=self.day, docstatus=2
		)
		with self.assertRaises(frappe.PermissionError):
			self._log(amended_from=log_b)

	def test_settings_isolated_by_company_user_permission(self):
		other = self._company_b()
		mine = frappe.get_doc({"doctype": SETTINGS, "company": self.company}).insert(ignore_permissions=True)
		theirs = frappe.get_doc({"doctype": SETTINGS, "company": other}).insert(ignore_permissions=True)
		self.assertEqual(mine.self_approval_rule, daily_log.RULE_WARN)
		user = self._user("restricted-set", ("Card Manager",), company=self.company)
		self.assertTrue(frappe.has_permission(SETTINGS, "read", mine.name, user=user))
		self.assertFalse(frappe.has_permission(SETTINGS, "read", theirs.name, user=user))
		self.assertFalse(frappe.has_permission(SETTINGS, "read", user="Guest"))
		# Card Manager reads its company's rules but may not change them (System Manager does)
		self.assertFalse(frappe.has_permission(SETTINGS, "write", mine.name, user=user))
		self.assertFalse(frappe.has_permission(SETTINGS, "create", user=user))
		self.assertFalse(frappe.has_permission(SETTINGS, "delete", mine.name, user=user))

	def test_settings_isolated_by_applicable_for_user_permission(self):
		"""A Company User Permission that applies to Card Daily Log only (not to every DocType) limits the rules
		too: read, list, change (System Manager restricted the same way)."""
		other = self._company_b()
		mine = frappe.get_doc({"doctype": SETTINGS, "company": self.company}).insert(ignore_permissions=True)
		theirs = frappe.get_doc(
			{"doctype": SETTINGS, "company": other, "self_approval_rule": daily_log.RULE_REFUSE}
		).insert(ignore_permissions=True)
		manager = self._user("app-mgr", ("Card Manager",), company=self.company, applicable_for=LOG)
		admin = self._user("app-sys", ("System Manager",), company=self.company, applicable_for=LOG)
		for user in (manager, admin):
			with self.subTest(user=user):
				self.assertTrue(frappe.has_permission(SETTINGS, "read", mine.name, user=user))
				self.assertFalse(frappe.has_permission(SETTINGS, "read", theirs.name, user=user))
				frappe.set_user(user)
				listed = frappe.get_list(SETTINGS, pluck="name")
				frappe.set_user("Administrator")
				self.assertIn(mine.name, listed)
				self.assertNotIn(theirs.name, listed)
		frappe.set_user(admin)
		with self.assertRaises(frappe.PermissionError):
			rest_set_value(SETTINGS, theirs.name, "self_approval_rule", daily_log.RULE_WARN)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc({"doctype": SETTINGS, "company": other + "-X"}).insert()
		rest_set_value(SETTINGS, mine.name, "require_supervisor_verification", 1)
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(SETTINGS, theirs.name, "self_approval_rule"), daily_log.RULE_REFUSE
		)
		self.assertTrue(daily_log.requires_supervisor_verification(self.company))
		# an unrestricted user is not affected
		self.assertTrue(frappe.has_permission(SETTINGS, "read", theirs.name, user=self.manager))

	# ---------- cancel on every route (review finding 1, 2) ----------
	def _approved(self, offset=0):
		eq = self._equipment()
		doc = self._log([{"equipment": eq.name, "day_hours": 4}], log_date=add_days(self.day, -offset))
		return self._set_status(doc, daily_log.APPROVED, self.manager)

	def _stored(self, name):
		return frappe.db.get_value(
			LOG, name, ["docstatus", "approval_status", "approved_by", "self_approved"], as_dict=True
		)

	def test_cancel_by_rest_put_reads_the_stored_approval(self):
		from frappe.api import v1

		doc = self._approved()
		for data in ({"docstatus": 2, "approval_status": "Pending"}, {"docstatus": 2}):
			with self.subTest(data=data):
				frappe.set_user(self.operator)
				frappe.local.form_dict = frappe._dict(data=frappe.as_json(data))
				with self.assertRaises(frappe.PermissionError):
					v1.update_doc(LOG, doc.name)
				frappe.set_user("Administrator")
				self.assertEqual(self._stored(doc.name).docstatus, 1)

	def test_cancel_by_savedocs_with_a_forged_document(self):
		from frappe.desk.form.save import savedocs

		doc = self._approved()
		frappe.set_user(self.supervisor)
		forged = frappe.get_doc(LOG, doc.name).as_dict()
		forged["approval_status"] = "Pending"
		with self.assertRaises(frappe.PermissionError):
			savedocs(frappe.as_json(forged), "Cancel")
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(doc.name).docstatus, 1)

	def test_cancel_by_bulk_update(self):
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		doc = self._approved()
		frappe.set_user(self.supervisor)
		# the bulk action commits after each document and rolls back a failure: kept inside the test transaction
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			for action, data in (
				("update", {"docstatus": 2, "approval_status": "Pending"}),
				("cancel", None),
			):
				with self.subTest(action=action):
					self.assertEqual(submit_cancel_or_update_docs(LOG, [doc.name], action, data), [doc.name])
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(doc.name).docstatus, 1)
		self.assertEqual(self._stored(doc.name).approval_status, daily_log.APPROVED)

	def test_cancel_keeps_the_stored_approval_fields(self):
		from frappe.api import v1

		doc = self._approved()
		frappe.set_user(self.manager)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json(
				{
					"docstatus": 2,
					"approved_by": self.operator,
					"self_approved": 1,
					"submitted_by": self.manager,
				}
			)
		)
		v1.update_doc(LOG, doc.name)
		frappe.set_user("Administrator")
		stored = frappe.db.get_value(
			LOG, doc.name, ["docstatus", "approved_by", "self_approved", "submitted_by"], as_dict=True
		)
		self.assertEqual(
			stored,
			{"docstatus": 2, "approved_by": self.manager, "self_approved": 0, "submitted_by": self.operator},
		)

	def test_pending_log_cancelled_by_its_operator(self):
		doc = self._log()
		frappe.set_user(self.operator)
		frappe.get_doc(LOG, doc.name).cancel()
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(doc.name).docstatus, 2)

	# ---------- amendment chain (review finding 6) ----------
	def test_amendment_keeps_the_earlier_preparers(self):
		self._rule(daily_log.RULE_REFUSE)
		first = self._log(submit=False)
		frappe.set_user(self.manager)
		edited = frappe.get_doc(LOG, first.name)
		edited.rows[0].day_hours = 9
		edited.save()
		frappe.set_user(self.operator)
		frappe.get_doc(LOG, first.name).submit()
		frappe.get_doc(LOG, first.name).cancel()
		second = frappe.copy_doc(frappe.get_doc(LOG, first.name))
		second.docstatus = 0
		second.amended_from = first.name
		second.insert()
		second.submit()
		second.cancel()
		third = frappe.copy_doc(frappe.get_doc(LOG, second.name))
		third.docstatus = 0
		third.amended_from = second.name
		third.insert()
		third.submit()
		frappe.set_user("Administrator")
		self.assertIn(self.manager, daily_log.log_preparers(frappe.get_doc(LOG, third.name)))
		with self.assertRaises(frappe.PermissionError):
			self._set_status(third, daily_log.APPROVED, self.manager)
		other = self._user("mgr-chain", ("Card Manager",))
		self.assertEqual(
			self._set_status(third, daily_log.APPROVED, other).approval_status, daily_log.APPROVED
		)

	# ---------- supervisor step (opt-in, review finding 7) ----------
	def test_supervisor_step_is_off_by_default(self):
		self.assertFalse(daily_log.requires_supervisor_verification(self.company))
		doc = self._log()
		with self.assertRaises(frappe.ValidationError):
			self._set_status(doc, daily_log.VERIFIED, self.supervisor)
		self.assertEqual(
			self._set_status(doc, daily_log.APPROVED, self.manager).approval_status, daily_log.APPROVED
		)
		self._rule()  # a settings record with the defaults: still two steps
		doc = self._log(log_date=add_days(self.day, -1))
		self.assertEqual(self._set_status(doc, daily_log.APPROVED, self.manager).verified_by, None)

	def test_supervisor_step_when_the_company_asks_for_it(self):
		self._rule(verification=1)
		doc = self._log()
		# a manager cannot skip the supervisor
		with self.assertRaises(frappe.ValidationError):
			self._set_status(doc, daily_log.APPROVED, self.manager)
		# only a Card Supervisor verifies; a manager without the role does not
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, daily_log.VERIFIED, self.manager)
		doc = self._set_status(doc, daily_log.VERIFIED, self.supervisor)
		self.assertEqual(doc.approval_status, daily_log.VERIFIED)
		self.assertEqual(doc.verified_by, self.supervisor)
		self.assertTrue(doc.verified_on)
		# verifying again changes nothing: the first verifier stays
		again = self._set_status(doc, daily_log.VERIFIED, self._user("sup2", ("Card Supervisor",)))
		self.assertEqual(again.verified_by, self.supervisor)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, daily_log.APPROVED, self.supervisor)
		doc = self._set_status(doc, daily_log.APPROVED, self.manager)
		self.assertEqual(
			(doc.approval_status, doc.approved_by, doc.self_approved), (daily_log.APPROVED, self.manager, 0)
		)
		self.assertEqual(doc.verified_by, self.supervisor)

	def test_supervisor_who_prepared_the_log_cannot_verify_it(self):
		self._rule(verification=1)
		doc = self._log(user=self.supervisor)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, daily_log.VERIFIED, self.supervisor)
		other = self._user("sup3", ("Card Supervisor",))
		self.assertEqual(self._set_status(doc, daily_log.VERIFIED, other).verified_by, other)

	def test_verifier_counts_as_a_preparer_for_the_approval(self):
		self._rule(daily_log.RULE_REFUSE, verification=1)
		both = self._user("sup-mgr", ("Card Supervisor", "Card Manager"))
		doc = self._set_status(self._log(), daily_log.VERIFIED, both)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, daily_log.APPROVED, both)
		self.assertEqual(self._set_status(doc, daily_log.APPROVED, self.manager).self_approved, 0)

	def test_supervisor_may_return_a_pending_log_in_that_mode(self):
		doc = self._log()
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, daily_log.RETURNED, self.supervisor, "check")
		self._rule(verification=1)
		doc = self._set_status(doc, daily_log.RETURNED, self.supervisor, "wrong sheet")
		self.assertEqual((doc.approval_status, doc.returned_by), (daily_log.RETURNED, self.supervisor))
		# a verified log is returned by a manager only
		doc = self._set_status(
			self._log(log_date=add_days(self.day, -1)), daily_log.VERIFIED, self.supervisor
		)
		with self.assertRaises(frappe.PermissionError):
			self._set_status(doc, daily_log.RETURNED, self.supervisor, "late")
		self.assertEqual(
			self._set_status(doc, daily_log.RETURNED, self.manager, "late").returned_by, self.manager
		)

	def test_client_cannot_write_verification_fields(self):
		self._rule(verification=1)
		doc = self._log()
		frappe.set_user(self.manager)
		rest_set_value(LOG, doc.name, "verified_by", self.supervisor)
		frappe.set_user("Administrator")
		self.assertIsNone(frappe.db.get_value(LOG, doc.name, "verified_by"))

	# ---------- responsible party (FR-118 parity, no rule yet) ----------
	def test_responsible_party_is_stored(self):
		reason = self._reason()
		doc = self._log(
			[
				{
					"equipment": self.eq.name,
					"stop_reason": reason.name,
					"stopped_hours": 2,
					"responsible_party_type": "Supplier",
					"responsible_party": self.supplier,
				}
			]
		)
		row = frappe.db.get_value(
			"Card Daily Log Row",
			{"parent": doc.name},
			["responsible_party_type", "responsible_party"],
			as_dict=True,
		)
		self.assertEqual(row, {"responsible_party_type": "Supplier", "responsible_party": self.supplier})

	def test_responsible_company_must_be_the_log_company(self):
		other = self._company_b()
		with self.assertRaises(frappe.ValidationError):
			self._log(
				[
					{
						"equipment": self.eq.name,
						"stopped_hours": 2,
						"responsible_party_type": "Company",
						"responsible_party": other,
					}
				]
			)
		doc = self._log(
			[{"equipment": self.eq.name, "stopped_hours": 2, "responsible_party_type": "Company"}]
		)
		self.assertEqual(doc.rows[0].responsible_party, self.company)

	def test_responsible_party_other_keeps_a_name_only(self):
		"""As on a monthly card day row: Other names the party in free text (the record link stays empty)."""
		doc = self._log(
			[
				{
					"equipment": self.eq.name,
					"stopped_hours": 2,
					"responsible_party_type": "Other",
					"responsible_party_name": "Road closure by the municipality",
				}
			]
		)
		row = frappe.db.get_value(
			"Card Daily Log Row",
			{"parent": doc.name},
			["responsible_party_type", "responsible_party", "responsible_party_name"],
			as_dict=True,
		)
		self.assertEqual(
			row,
			{
				"responsible_party_type": "Other",
				"responsible_party": None,
				"responsible_party_name": "Road closure by the municipality",
			},
		)

	def test_responsible_party_defaults_from_the_stop_reason(self):
		reason = self._reason()
		frappe.db.set_value("Card Stop Reason", reason.name, "default_responsible_party_type", "Company")
		doc = self._log([{"equipment": self.eq.name, "stop_reason": reason.name, "stopped_hours": 3}])
		self.assertEqual(
			(doc.rows[0].responsible_party_type, doc.rows[0].responsible_party), ("Company", self.company)
		)
		# no party and no reason: nothing is set
		doc = self._log([{"equipment": self.eq2.name, "day_hours": 3}])
		self.assertFalse(doc.rows[0].responsible_party_type)
		self.assertFalse(doc.rows[0].responsible_party)

	def test_an_earlier_verifier_in_the_chain_is_a_preparer(self):
		self._rule(daily_log.RULE_REFUSE, verification=1)
		both = self._user("sup-mgr-chain", ("Card Supervisor", "Card Manager"))
		first = self._set_status(self._log(), daily_log.VERIFIED, both)
		frappe.set_user(self.manager)
		frappe.get_doc(LOG, first.name).cancel()
		frappe.set_user(self.operator)
		amended = frappe.copy_doc(frappe.get_doc(LOG, first.name))
		amended.docstatus = 0
		amended.amended_from = first.name
		amended.insert()
		amended.submit()
		frappe.set_user("Administrator")
		amended = self._set_status(amended, daily_log.VERIFIED, self._user("sup-chain", ("Card Supervisor",)))
		self.assertIn(both, daily_log.log_preparers(frappe.get_doc(LOG, amended.name)))
		with self.assertRaises(frappe.PermissionError):
			self._set_status(amended, daily_log.APPROVED, both)
		self.assertEqual(
			self._set_status(amended, daily_log.APPROVED, self.manager).approved_by, self.manager
		)

	def test_settings_share_across_companies_is_refused(self):
		from frappe.share import add_docshare

		other = self._company_b()
		theirs = frappe.get_doc(
			{"doctype": SETTINGS, "company": other, "self_approval_rule": daily_log.RULE_REFUSE}
		).insert(ignore_permissions=True)
		mine = frappe.get_doc({"doctype": SETTINGS, "company": self.company}).insert(ignore_permissions=True)
		restricted = self._user("share-mgr", ("Card Manager",), company=self.company, applicable_for=LOG)
		with self.assertRaises(frappe.PermissionError):
			add_docshare(
				SETTINGS, theirs.name, restricted, read=1, write=1, flags={"ignore_share_permission": 1}
			)
		with self.assertRaises(frappe.PermissionError):
			add_docshare(SETTINGS, mine.name, everyone=1, read=1, flags={"ignore_share_permission": 1})
		self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": SETTINGS, "share_name": theirs.name}))
		self.assertFalse(frappe.has_permission(SETTINGS, "read", theirs.name, user=restricted))
		# a share within the user's company, and any share for an unrestricted user, is allowed
		add_docshare(SETTINGS, mine.name, restricted, read=1, flags={"ignore_share_permission": 1})
		add_docshare(SETTINGS, theirs.name, self.manager, read=1, flags={"ignore_share_permission": 1})
		# the guard leaves every other DocType alone
		daily_log.deny_cross_company_settings_share(frappe._dict(share_doctype="ToDo", everyone=1, user=None))


class TestDailyLogConcurrency(IntegrationTestCase):
	"""Review finding 3: two requests that submit a log for the same equipment, project and date at the same time
	never leave two live logs. Modelled on test_assignment_overlap_concurrency: each request has its own
	connection and commits; both take their REPEATABLE READ snapshot before either writes. The records are
	committed and removed in tearDown. MariaDB 11.8 with innodb_snapshot_isolation ON may refuse the locking read
	with error 1020 (a deadlock error in Frappe); the strict case sets the variable OFF in its own sessions only."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.has_snapshot_isolation = bool(frappe.db.sql("show variables like 'innodb_snapshot_isolation'"))

	def setUp(self):
		from card.tests import test_assignment_overlap_concurrency as model

		self.model = model
		self.token = frappe.generate_hash(length=8)
		self.created = {"Card Daily Log": [], "Card Equipment": [], "Project": []}
		self.started = self._committed(frappe.utils.now)
		self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)
		self.assertEqual(self._committed(self._leftovers), 0, "synthetic records left behind")

	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	def _make_records(self):
		company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		etype = frappe.db.get_value("Card Equipment Type", {}, "name", order_by="creation asc")
		if not (company and etype):
			self.skipTest("test masters missing (card.install.before_tests)")
		self.company = company
		self.day = str(add_days(nowdate(), -2))
		self.project = self._new("Project", {"project_name": "DL-RACE-" + self.token, "company": company})
		self.equipment = self._new(
			"Card Equipment",
			{
				"company": company,
				"equipment_type": etype,
				"equipment_name": "DL-RACE-EQ-" + self.token,
				"ownership": "ملك",
				"rate_type": "باليوم",
				"rate": 750,
				"daily_hours": 10,
			},
		)

	def _new(self, doctype, values):
		doc = frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
		self.created[doctype].append(doc.name)
		return doc.name

	def _submit_log(self):
		doc = frappe.get_doc(
			{
				"doctype": LOG,
				"company": self.company,
				"project": self.project,
				"log_date": self.day,
				"rows": [{"equipment": self.equipment, "day_hours": 5}],
			}
		).insert(ignore_permissions=True)
		doc.submit()

	def _live_logs(self):
		return self._committed(
			lambda: frappe.get_all(
				LOG,
				filters={"project": self.project, "log_date": self.day, "docstatus": ["<", 2]},
				pluck="name",
			)
		)

	def _remove_records(self):
		names = frappe.get_all(LOG, filters={"project": self.project}, fields=["name", "docstatus"])
		self.created[LOG] = [n.name for n in names]
		for name in names:
			if name.docstatus == 1:
				frappe.get_doc(LOG, name.name).cancel()
			self.model._delete(LOG, name.name)
		for doctype in ("Card Equipment", "Project"):
			for name in self.created[doctype]:
				self.model._delete(doctype, name)
		mine = [n for names in self.created.values() for n in names] or [""]
		since = {"creation": [">=", self.started]}
		frappe.db.delete("Version", {"docname": ["in", mine], **since})
		frappe.db.delete("Comment", {"reference_name": ["in", mine], **since})
		frappe.db.delete("Deleted Document", {"deleted_name": ["in", mine], **since})
		frappe.db.delete(
			"Comment", {"comment_type": "Deleted", "subject": ["like", "%" + self.token + "%"], **since}
		)

	def _leftovers(self):
		return frappe.db.count(LOG, {"project": self.project}) + sum(
			frappe.db.count(doctype, {"name": ["in", self.created[doctype] or [""]]})
			for doctype in ("Card Equipment", "Project")
		)

	def test_two_concurrent_submits_leave_one_live_log(self):
		_one, two = self._race(self._submit_log, self._submit_log)
		self.assertFalse(two.committed, "the second request was not refused")
		self.assertIsInstance(two.error, frappe.DuplicateEntryError, repr(two.error))
		self.assertEqual(len(self._live_logs()), 1)

	def test_with_the_server_snapshot_setting(self):
		_one, two = self._race(self._submit_log, self._submit_log, snapshot_isolation=None)
		self.assertFalse(two.committed)
		self.assertIsInstance(
			two.error, (frappe.DuplicateEntryError, *self.model.SAFE_ERRORS), repr(two.error)
		)
		self.assertEqual(len(self._live_logs()), 1)


def _bind_model_helpers():
	from card.tests import test_assignment_overlap_concurrency as model

	base = model.TestAssignmentOverlapConcurrency
	TestDailyLogConcurrency._committed = base._committed
	TestDailyLogConcurrency._race = base._race


_bind_model_helpers()
