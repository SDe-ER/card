# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-150 (#44, #123): the CARD Mobile daily log screens use Frappe's standard REST routes only
(frappe.api.v1: list, read, insert, update), under the operator's own permissions. No CARD endpoint
was added for them.

Proven here, as a Card Operator and with the exact bodies frontend/src/data/dailyLog.ts sends (its
unit tests pin the same keys): create a draft, list only his own logs, read one, save a draft with
its ``modified`` stamp (a stale one is refused), submit it by sending only the docstatus, correct a
returned log (cancel by docstatus only, then an amending draft), and the refusal of the company's
stop reasons that hides the picker. The server keeps every approval field whatever the body says.
All data is per-test and rolled back; no role is widened."""

import frappe
from frappe.api import v1
from frappe.utils import add_days, nowdate

# a module import: a TestCase class imported by name would be collected (and run) here again
from card.tests import test_daily_log as daily_log_tests
from card.tests.test_customer import _CustomerCardsBase

LOG = "Card Daily Log"
# frontend/src/data/dailyLog.ts LIST_FIELDS
LIST_FIELDS = ["name", "project", "log_date", "approval_status", "docstatus", "modified"]


class TestMobileDailyLogRest(_CustomerCardsBase):
	_user = daily_log_tests.TestDailyLog._user
	_set_status = daily_log_tests.TestDailyLog._set_status
	_reason = daily_log_tests.TestDailyLog._reason

	def setUp(self):
		super().setUp()
		self.day = add_days(nowdate(), -2)
		self.eq = self._equipment()
		self.operator = self._user("mop", ("Card Operator",))
		self.other = self._user("mop2", ("Card Operator",))
		self.manager = self._user("mmgr", ("Card Manager",))

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()
		super().tearDown()

	# ---------- the REST routes, as the browser calls them ----------
	def _as(self, user, fn, *args, form=None, data=None):
		frappe.set_user(user)
		frappe.local.form_dict = frappe._dict(form or {})
		if data is not None:
			frappe.local.form_dict.data = frappe.as_json(data)
		try:
			return fn(*args)
		finally:
			frappe.set_user("Administrator")
			frappe.local.form_dict = frappe._dict()

	def _row(self, **values):
		# frontend/src/data/dailyLog.ts rowPayload: ROW_FIELDS only
		row = {
			"equipment": self.eq.name,
			"day_hours": 8,
			"night_hours": 0,
			"stopped_hours": 1.5,
			"stop_reason": None,
			"responsible_party_type": None,
			"responsible_party": None,
			"responsible_party_name": None,
			"notes": "hydraulic leak",
		}
		row.update(values)
		return row

	def _create(self, user=None, **extra):
		body = {
			"company": self.company,
			"project": self.project,
			"log_date": self.day,
			"notes": None,
			"rows": [self._row()],
			**extra,
		}
		return self._as(user or self.operator, v1.create_doc, LOG, data=body)

	def _stored(self, name):
		return frappe.get_doc(LOG, name)

	# ---------- tests ----------
	def test_operator_creates_a_draft(self):
		doc = self._create()
		stored = self._stored(doc.name)
		self.assertEqual(stored.docstatus, 0)
		self.assertEqual(stored.approval_status, "Pending")
		self.assertEqual(stored.owner, self.operator)
		self.assertEqual(stored.rows[0].stopped_hours, 1.5)

	def test_list_shows_only_his_own_logs(self):
		mine = self._create()
		other = self._create(user=self.other, rows=[self._row(equipment=self._equipment().name)])
		form = {
			"fields": frappe.as_json(LIST_FIELDS),
			"filters": frappe.as_json([["owner", "=", self.operator], ["docstatus", "<", 2]]),
		}
		rows = self._as(self.operator, v1.document_list, LOG, form=form)
		self.assertEqual([r["name"] for r in rows], [mine.name])
		self.assertEqual(sorted(rows[0]), sorted(LIST_FIELDS))
		# without the owner filter the server still lists only his own (Card Operator: if_owner)
		form.pop("filters")
		names = [r["name"] for r in self._as(self.operator, v1.document_list, LOG, form=form)]
		self.assertIn(mine.name, names)
		self.assertNotIn(other.name, names)

	def test_operator_reads_his_log_not_another_operators(self):
		mine = self._create()
		other = self._create(user=self.other, rows=[self._row(equipment=self._equipment().name)])
		self.assertEqual(self._as(self.operator, v1.read_doc, LOG, mine.name).name, mine.name)
		with self.assertRaises(frappe.PermissionError):
			self._as(self.operator, v1.read_doc, LOG, other.name)

	def test_draft_saved_with_its_modified_stamp(self):
		doc = self._create()
		body = {
			"project": self.project,
			"log_date": self.day,
			"notes": "corrected",
			"rows": [self._row(name=doc.rows[0].name, day_hours=9)],
			"modified": str(doc.modified),
		}
		saved = self._as(self.operator, v1.update_doc, LOG, doc.name, data=body)
		self.assertEqual(self._stored(doc.name).rows[0].day_hours, 9)
		# the same body again carries the old stamp: a newer version is never overwritten
		with self.assertRaises(frappe.TimestampMismatchError):
			self._as(self.operator, v1.update_doc, LOG, doc.name, data=body)
		self.assertEqual(self._stored(saved.name).notes, "corrected")

	def test_submit_sends_only_the_docstatus(self):
		doc = self._create()
		self._as(
			self.operator,
			v1.update_doc,
			LOG,
			doc.name,
			data={"docstatus": 1, "modified": str(self._stored(doc.name).modified)},
		)
		stored = self._stored(doc.name)
		self.assertEqual(stored.docstatus, 1)
		self.assertEqual(stored.approval_status, "Pending")
		self.assertEqual(stored.submitted_by, self.operator)
		self.assertFalse(stored.approved_by)

	def test_server_keeps_the_approval_whatever_the_body_says(self):
		# the screens never send these (dailyLog.spec.ts); the server must not rely on that either
		forged = {
			"approval_status": "Approved",
			"approved_by": self.manager,
			"submitted_by": self.manager,
			"edited_by": self.manager,
		}
		doc = self._create(**forged)
		stored = self._stored(doc.name)
		self.assertEqual(stored.approval_status, "Pending")
		self.assertFalse(stored.approved_by)
		self.assertEqual(stored.edited_by, self.operator)

	def test_operator_cannot_read_stop_reasons_so_no_picker(self):
		self._reason()
		form = {"fields": frappe.as_json(["name", "reason_name"])}
		with self.assertRaises(frappe.PermissionError):
			self._as(self.operator, v1.document_list, "Card Stop Reason", form=form)

	def test_correct_a_returned_log(self):
		doc = self._create()
		self._as(
			self.operator,
			v1.update_doc,
			LOG,
			doc.name,
			data={"docstatus": 1, "modified": str(self._stored(doc.name).modified)},
		)
		self._set_status(self._stored(doc.name), "Returned for correction", self.manager, "Too many hours")
		returned = self._stored(doc.name)
		self.assertEqual(returned.return_reason, "Too many hours")
		# 1. cancel: the docstatus and the stamp only
		self._as(
			self.operator,
			v1.update_doc,
			LOG,
			doc.name,
			data={"docstatus": 2, "modified": str(returned.modified)},
		)
		cancelled = self._stored(doc.name)
		self.assertEqual(cancelled.docstatus, 2)
		self.assertEqual(cancelled.approval_status, "Returned for correction")
		# 2. the amending draft, with the same header and rows (no row names)
		amended = self._create(amended_from=doc.name, rows=[self._row(day_hours=7)])
		stored = self._stored(amended.name)
		self.assertEqual(stored.amended_from, doc.name)
		self.assertEqual(stored.docstatus, 0)
		self.assertEqual(stored.approval_status, "Pending")
		self.assertFalse(stored.return_reason)

	def _returned_and_cancelled(self):
		doc = self._create()
		self._as(
			self.operator,
			v1.update_doc,
			LOG,
			doc.name,
			data={"docstatus": 1, "modified": str(self._stored(doc.name).modified)},
		)
		self._set_status(self._stored(doc.name), "Returned for correction", self.manager, "Too many hours")
		self._as(
			self.operator,
			v1.update_doc,
			LOG,
			doc.name,
			data={"docstatus": 2, "modified": str(self._stored(doc.name).modified)},
		)
		return doc.name

	def _amendments(self, name):
		# frontend/src/data/dailyLog.ts amendmentOf
		form = {
			"fields": frappe.as_json(["name", "docstatus", "approval_status"]),
			"filters": frappe.as_json([["amended_from", "=", name]]),
		}
		return self._as(self.operator, v1.document_list, LOG, form=form)

	def test_failed_correction_is_listed_and_recovered(self):
		# the cancel went through, the amending draft did not: the operator still finds the log
		name = self._returned_and_cancelled()
		form = {
			"fields": frappe.as_json([*LIST_FIELDS, "amended_from"]),
			"filters": frappe.as_json([["owner", "=", self.operator], ["docstatus", "=", 2]]),
		}
		cancelled = self._as(self.operator, v1.document_list, LOG, form=form)
		self.assertEqual(
			[(r["name"], r["approval_status"]) for r in cancelled], [(name, "Returned for correction")]
		)
		self.assertEqual(self._amendments(name), [])
		# "Create corrected draft": the amendment only
		amended = self._create(amended_from=name)
		self.assertEqual(self._stored(amended.name).amended_from, name)
		self.assertEqual([r["name"] for r in self._amendments(name)], [amended.name])

	def test_a_second_correction_is_refused_by_the_server(self):
		# the client checks first (amendmentOf); the server refuses a second amendment anyway: Frappe gives
		# it the same name, and the log's duplicate guard refuses the same equipment, project and date
		name = self._returned_and_cancelled()
		self._create(amended_from=name)
		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			self._create(amended_from=name)
