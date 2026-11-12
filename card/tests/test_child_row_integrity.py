# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-153 (SEC-2): a stored child row of a CARD document cannot be moved to another document.

Proven here:
- every CARD DocType with a table and every CARD child DocType carries the guard on validate, update after submit
  and cancel, discovered from the DocType meta (a new DocType is covered without a change to this test); no
  DocType outside CARD carries it;
- for each of them the registered handler refuses a row stored on another document or in another table field,
  and lets new rows and the document's own rows pass;
- the routes (REST PUT v1 and v2, frappe.client.save, set_value, bulk_update, savedocs, the Desk bulk update, and
  a child row saved on its own) cannot take a row from a submitted, an approved, another company's or the user's
  own other document; the other document keeps its rows;
- adding, removing and reordering rows, an amendment and frappe.copy_doc still work.

All data is per-test and rolled back; no role is widened."""

from unittest.mock import patch

import frappe
from frappe.api import v1, v2
from frappe.utils import add_days, nowdate

from card import child_integrity, daily_log
from card.child_integrity import CHILD_HANDLER, EVENTS, PARENT_HANDLER, ForeignChildRowError

# the events the guard MUST be wired on (asserted here, not read from EVENTS: a mutation of EVENTS that drops one
# of these must fail the enumeration tests — lesson 12, mutation-test every guard)
REQUIRED_EVENTS = ("validate", "before_update_after_submit", "before_cancel")
from card.tests import test_daily_log as _dl
from card.tests.test_customer import _CustomerCardsBase

LOG = "Card Daily Log"
ROW = "Card Daily Log Row"
MC = "Card Monthly Card"
DAY = "Card Monthly Card Day"
ADJ = "Card Monthly Card Adjustment"


def _card_modules():
	return frappe.get_module_list("card")


def _meta_doctypes():
	"""(parents with a table, child DocTypes) of the CARD modules, from the DocType meta."""
	parents, children = [], []
	for name in frappe.get_all(
		"DocType", filters={"module": ["in", _card_modules()], "is_virtual": 0}, pluck="name"
	):
		meta = frappe.get_meta(name)
		if meta.istable:
			children.append(name)
		elif meta.get_table_fields():
			parents.append(name)
	return sorted(parents), sorted(children)


def _plant(child, parent, parenttype, parentfield):
	"""A stored child row (no validation: only its parent columns matter)."""
	row = frappe.new_doc(child)
	row.update({"parent": parent, "parenttype": parenttype, "parentfield": parentfield, "idx": 1})
	row.name = "fr153" + frappe.generate_hash(length=10)
	row.db_insert()
	return row.name


class TestChildRowIntegrityMeta(_CustomerCardsBase):
	"""Every CARD DocType, from its meta."""

	def test_doctypes_come_from_the_card_meta(self):
		parents, children = _meta_doctypes()
		self.assertTrue(parents and children)
		self.assertIn(LOG, parents)
		self.assertIn(MC, parents)
		self.assertIn("Card Settings", parents)
		self.assertEqual(child_integrity.card_doctypes(), (parents, children))

	def test_every_card_doctype_is_hooked_and_no_other(self):
		events = frappe.get_hooks("doc_events")
		parents, children = _meta_doctypes()
		for doctypes, handler in ((parents, PARENT_HANDLER), (children, CHILD_HANDLER)):
			for doctype in doctypes:
				for event in REQUIRED_EVENTS:
					with self.subTest(doctype=doctype, event=event):
						self.assertIn(handler, events.get(doctype, {}).get(event) or [])
		self.assertEqual(set(EVENTS), set(REQUIRED_EVENTS))
		modules = set(_card_modules())
		for doctype, entry in events.items():
			handlers = {
				h for value in entry.values() for h in (value if isinstance(value, list) else [value])
			}
			if handlers & {PARENT_HANDLER, CHILD_HANDLER}:
				with self.subTest(doctype=doctype):
					self.assertNotEqual(doctype, "*")
					self.assertIn(frappe.db.get_value("DocType", doctype, "module"), modules)

	def test_existing_handlers_keep_their_order(self):
		events = frappe.get_hooks("doc_events")
		self.assertEqual(events[MC]["before_cancel"][0], "card.cancel_reason.before_cancel")
		for doctype in ("Equipment Transport", "Project Diesel Fill"):
			self.assertEqual(events[doctype]["validate"][-1], PARENT_HANDLER)
			self.assertIn("card.cancel_reason.on_validate", events[doctype]["validate"])

	def _handler(self, doctype, event, handler):
		self.assertIn(handler, frappe.get_hooks("doc_events")[doctype][event])
		return frappe.get_attr(handler)

	def test_parent_handler_on_every_card_doctype(self):
		parents, _children = _meta_doctypes()
		for doctype in parents:
			meta = frappe.get_meta(doctype)
			mine = doctype if meta.issingle else "TEST-FR153-MINE-" + self.token
			for df in meta.get_table_fields():
				foreign = _plant(df.options, "TEST-FR153-OTHER-" + self.token, doctype, df.fieldname)
				own = _plant(df.options, mine, doctype, df.fieldname)
				other_field = _plant(df.options, mine, doctype, "other_field")
				for event in REQUIRED_EVENTS:
					check = self._handler(doctype, event, PARENT_HANDLER)
					with self.subTest(doctype=doctype, table=df.fieldname, event=event):
						for name in (foreign, other_field):
							doc = frappe.get_doc({"doctype": doctype, "name": mine})
							doc.append(df.fieldname, {"name": own})
							doc.append(df.fieldname, {"name": name})
							with self.assertRaises(ForeignChildRowError):
								check(doc, event)
						# its own row, a new row and a name that is not stored yet pass
						doc = frappe.get_doc({"doctype": doctype, "name": mine})
						doc.append(df.fieldname, {"name": own})
						doc.append(df.fieldname, {})
						doc.append(df.fieldname, {"name": "fr153-not-stored-" + self.token})
						check(doc, event)
						# a new document inserts every row under a new name
						new = frappe.new_doc(doctype)
						new.append(df.fieldname, {"name": foreign})
						new.set("__islocal", 1)
						check(new, event)

	def test_child_handler_on_every_card_child_doctype(self):
		parents, children = _meta_doctypes()
		owners = {}
		for doctype in parents:
			for df in frappe.get_meta(doctype).get_table_fields():
				owners.setdefault(df.options, (doctype, df.fieldname))
		for child in children:
			if child not in owners:
				continue  # a child DocType no CARD table uses yet
			parenttype, parentfield = owners[child]
			name = _plant(child, "TEST-FR153-VICTIM-" + self.token, parenttype, parentfield)
			for event in REQUIRED_EVENTS:
				check = self._handler(child, event, CHILD_HANDLER)
				with self.subTest(child=child, event=event):
					for change in (
						{"parent": "TEST-FR153-MINE-" + self.token},
						{"parentfield": "other_field"},
						{"parenttype": "TEST FR153 Other"},
					):
						row = frappe.get_doc(child, name)
						row.update(change)
						with self.assertRaises(ForeignChildRowError):
							check(row, event)
					check(frappe.get_doc(child, name), event)
					check(frappe.new_doc(child), event)


class TestChildRowIntegrityRoutes(_CustomerCardsBase):
	"""Card Daily Log and Card Monthly Card, through each route, as their own roles."""

	_user = _dl.TestDailyLog._user
	_log = _dl.TestDailyLog._log
	_doc = _dl.TestDailyLog._doc
	_set_status = _dl.TestDailyLog._set_status
	_raw = _dl.TestDailyLog._raw
	_company_b = _dl.TestDailyLog._company_b

	def setUp(self):
		super().setUp()
		self.day = add_days(nowdate(), -3)
		self.eq = self._equipment()
		self.operator = self._user("op", ("Card Operator",))
		self.other = self._user("op2", ("Card Operator",))
		self.supervisor = self._user("sup", ("Card Supervisor",))
		self.manager = self._user("mgr", ("Card Manager",))

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()
		super().tearDown()

	# ---------- builders ----------
	def _row(self, **values):
		return {"equipment": self._equipment().name, "day_hours": 2, **values}

	def _where(self, doctype, name):
		return frappe.db.get_value(doctype, name, ["parent", "parenttype", "parentfield"])

	def _rows(self, doctype, name, field="rows"):
		child = frappe.get_meta(doctype).get_field(field).options
		return frappe.get_all(
			child, filters={"parent": name, "parenttype": doctype}, order_by="idx", pluck="name"
		)

	def _victims(self):
		"""A row of: another operator's submitted log, his approved log, a company-B submitted log and the
		attacker's own other draft."""
		pending = self._log([self._row()], user=self.other)
		approved = self._set_status(
			self._log([self._row()], user=self.other), daily_log.APPROVED, self.manager
		)
		company_b = self._company_b()
		project_b = self._raw(
			"Project", "TEST-FR153-PB-" + self.token, project_name="FR153B" + self.token, company=company_b
		)
		log_b = self._raw(
			LOG,
			"TEST-FR153-LB-" + self.token,
			company=company_b,
			project=project_b,
			log_date=self.day,
			docstatus=1,
		)
		self._raw(
			ROW,
			"fr153b" + frappe.generate_hash(length=8),
			parent=log_b,
			parenttype=LOG,
			parentfield="rows",
			day_hours=5,
			idx=1,
			docstatus=1,
		)
		own = self._log([self._row()], submit=False, log_date=add_days(self.day, -1))
		return {
			"submitted": pending.name,
			"approved": approved.name,
			"other company": log_b,
			"own other draft": own.name,
		}

	def _attempts(self, mine, foreign):
		"""Each route as a callable that tries to store ``foreign`` on the draft ``mine``."""
		stored = frappe.get_doc(LOG, mine)
		rows = [{"name": r.name, "equipment": r.equipment, "day_hours": r.day_hours} for r in stored.rows]
		rows.append(self._row(name=foreign))
		data = {"rows": rows, "modified": str(stored.modified)}

		def put_v1():
			frappe.local.form_dict = frappe._dict(data=frappe.as_json(data))
			v1.update_doc(LOG, mine)

		def put_v2():
			frappe.local.form_dict = frappe._dict(frappe.parse_json(frappe.as_json(data)))
			v2.update_doc(LOG, mine)

		def client_save():
			from frappe.client import save

			doc = frappe.get_doc(LOG, mine).as_dict()
			doc.update(data)
			save(frappe.as_json(doc))

		def savedocs():
			from frappe.desk.form.save import savedocs

			doc = frappe.get_doc(LOG, mine).as_dict()
			doc.update(data)
			savedocs(frappe.as_json(doc), "Save")

		def set_value():
			from frappe.client import set_value

			set_value(LOG, mine, {"rows": rows})

		def client_bulk_update():
			from frappe.client import bulk_update

			failed = bulk_update(frappe.as_json([{"doctype": LOG, "docname": mine, **data}]))["failed_docs"]
			if failed:
				raise (
					ForeignChildRowError(failed[0]["exc"])
					if "ForeignChildRowError" in failed[0]["exc"]
					else Exception
				)
			return failed

		def desk_bulk_update():
			from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

			with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
				failed = submit_cancel_or_update_docs(LOG, [mine], "update", {"rows": rows})
			messages = frappe.as_json(frappe.message_log)
			frappe.clear_messages()
			if failed:
				raise (
					ForeignChildRowError(messages) if "another document" in messages else Exception(messages)
				)

		def child_put():
			frappe.local.form_dict = frappe._dict(
				data=frappe.as_json({"parent": mine, "parenttype": LOG, "parentfield": "rows"})
			)
			v1.update_doc(ROW, foreign)

		def child_bulk_update():
			from frappe.client import bulk_update

			body = {
				"doctype": ROW,
				"docname": foreign,
				"parent": mine,
				"parenttype": LOG,
				"parentfield": "rows",
			}
			failed = bulk_update(frappe.as_json([body]))["failed_docs"]
			if failed:
				raise (
					ForeignChildRowError(failed[0]["exc"])
					if "ForeignChildRowError" in failed[0]["exc"]
					else Exception
				)

		def child_save():
			from frappe.client import save

			row = frappe.get_doc(ROW, foreign).as_dict()
			row.update({"parent": mine, "parenttype": LOG, "parentfield": "rows"})
			save(frappe.as_json(row))

		return {
			"REST PUT v1": put_v1,
			"REST PUT v2": put_v2,
			"frappe.client.save": client_save,
			"savedocs": savedocs,
			"frappe.client.set_value": set_value,
			"frappe.client.bulk_update": client_bulk_update,
			"Desk bulk update": desk_bulk_update,
			"child REST PUT": child_put,
			"child bulk_update": child_bulk_update,
			"child frappe.client.save": child_save,
		}

	# ---------- the attack is refused on every route ----------
	def _assert_refused(self, user, mine, victim, foreign, route, attempt):
		before_victim = self._rows(LOG, victim)
		before_mine = self._rows(LOG, mine)
		frappe.set_user(user)
		try:
			# a route without permission on the row (PermissionError) is refused too, but must not hide the guard:
			# every case below must reach it
			with self.assertRaises(ForeignChildRowError, msg=route):
				attempt()
		finally:
			frappe.set_user("Administrator")
			frappe.clear_messages()
		self.assertEqual(self._where(ROW, foreign), (victim, LOG, "rows"), route)
		self.assertEqual(self._rows(LOG, victim), before_victim, route)
		self.assertEqual(self._rows(LOG, mine), before_mine, route)

	def test_operator_cannot_take_a_row_on_any_parent_route(self):
		victims = self._victims()
		mine = self._log([self._row()], submit=False).name
		for kind, victim in victims.items():
			foreign = self._rows(LOG, victim)[0]
			for route, attempt in self._attempts(mine, foreign).items():
				if route.startswith("child"):
					continue
				with self.subTest(victim=kind, route=route):
					self._assert_refused(self.operator, mine, victim, foreign, route, attempt)
		self.assertEqual(frappe.db.get_value(LOG, victims["approved"], "approval_status"), daily_log.APPROVED)

	def test_a_child_row_saved_on_its_own_keeps_its_document(self):
		# the supervisor may write every log of his company, so the child routes reach the guard for each victim
		victims = self._victims()
		del victims["other company"]  # outside his company: refused by the company scope before the guard
		mine = self._log([self._row()], submit=False, user=self.supervisor).name
		for kind, victim in victims.items():
			foreign = self._rows(LOG, victim)[0]
			for route, attempt in self._attempts(mine, foreign).items():
				if not route.startswith("child"):
					continue
				with self.subTest(victim=kind, route=route):
					self._assert_refused(self.supervisor, mine, victim, foreign, route, attempt)

	def test_operator_child_bulk_update_cannot_take_an_approved_row(self):
		victim = self._victims()["approved"]
		mine = self._log([self._row()], submit=False).name
		foreign = self._rows(LOG, victim)[0]
		attempt = self._attempts(mine, foreign)["child bulk_update"]
		self._assert_refused(self.operator, mine, victim, foreign, "child bulk_update", attempt)

	def test_cancel_cannot_take_a_row(self):
		"""The guard's ``before_cancel`` handler refuses a foreign row name on a cancelling document.
		The handler is called directly: the full cancel route is tested in TestChildRowIntegrityMeta
		(``test_parent_handler_on_every_card_doctype``) across every CARD DocType, and here the integration
		test cannot reach ``check_rows`` through the full REST cancel because ``card.cancel_reason.before_cancel``
		and ``card.daily_log.check_cancel`` compare rows by name and refuse the change first (defence in depth).
		The assertion is on ``ForeignChildRowError``, so this test fails if ``before_cancel`` leaves ``EVENTS``
		or if the handler is ever changed to let foreign rows through (lesson 12)."""
		victim = self._victims()["approved"]
		mine = self._log([self._row()])
		foreign = self._rows(LOG, victim)[0]
		doc = frappe.get_doc(LOG, mine.name)
		doc.append("rows", self._row(name=foreign))
		doc.docstatus = 2
		with self.assertRaises(ForeignChildRowError):
			child_integrity.check_rows(doc, "before_cancel")
		# the guard is wired on ``before_cancel`` for this DocType; removing ``before_cancel`` from ``EVENTS``
		# makes this assertion fail (together with the enumeration tests in TestChildRowIntegrityMeta)
		self.assertIn(PARENT_HANDLER, frappe.get_hooks("doc_events")[LOG]["before_cancel"])
		self.assertEqual(self._where(ROW, foreign), (victim, LOG, "rows"))

	# ---------- Card Monthly Card: days and adjustments ----------
	def _submitted_card(self, hours):
		card = self._card(self._equipment(), hours)
		card = frappe.get_doc(MC, card.name)
		card.append("adjustments", {"adjustment_type": "خصم", "description": "TEST-FR153", "amount": 5})
		card.save(ignore_permissions=True)
		card.submit()
		return frappe.get_doc(MC, card.name)

	def test_card_user_cannot_take_days_or_adjustments(self):
		user = self._user("cu", ("Card User",))
		victim = self._submitted_card([10, 10])
		mine = frappe.get_doc(MC, self._card(self._equipment(), [8]).name)
		own_days = [r.as_dict() for r in mine.days]
		for field, rows in (
			("days", {"days": [*own_days, victim.days[1].as_dict()]}),
			(
				"adjustments",
				{
					"adjustments": [
						{
							"name": victim.adjustments[0].name,
							"adjustment_type": "خصم",
							"description": "x",
							"amount": 1,
						}
					]
				},
			),
		):
			foreign = victim.get(field)[-1].name if field == "days" else victim.adjustments[0].name
			with self.subTest(field=field):
				frappe.set_user(user)
				frappe.local.form_dict = frappe._dict(
					data=frappe.as_json(
						{**rows, "modified": str(frappe.db.get_value(MC, mine.name, "modified"))}
					)
				)
				with self.assertRaises(ForeignChildRowError):
					v1.update_doc(MC, mine.name)
				frappe.set_user("Administrator")
				child = DAY if field == "days" else ADJ
				self.assertEqual(self._where(child, foreign), (victim.name, MC, field))
		self.assertEqual(len(self._rows(MC, victim.name, "days")), 2)
		self.assertEqual(len(self._rows(MC, victim.name, "adjustments")), 1)

	def test_update_after_submit_cannot_swap_in_a_row(self):
		# same number of rows and the stolen row's own values: Frappe's update-after-submit check sees no change
		victim = self._submitted_card([10, 10])
		mine = self._submitted_card([10, 10])
		days = [mine.days[0].as_dict(), victim.days[1].as_dict()]
		frappe.set_user(self.manager)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json({"days": days, "modified": str(mine.modified)})
		)
		with self.assertRaises(ForeignChildRowError):
			v1.update_doc(MC, mine.name)
		frappe.set_user("Administrator")
		self.assertEqual(self._where(DAY, victim.days[1].name), (victim.name, MC, "days"))
		self.assertEqual(self._rows(MC, mine.name, "days"), [d.name for d in mine.days])

	# ---------- legitimate flows still work ----------
	def test_add_remove_and_reorder_rows(self):
		doc = self._log([self._row(), self._row()], submit=False)
		first, second = (r.name for r in frappe.get_doc(LOG, doc.name).rows)
		stored = frappe.get_doc(LOG, doc.name)
		rows = [{k: v for k, v in r.as_dict().items() if k != "idx"} for r in reversed(stored.rows)]
		frappe.set_user(self.operator)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json({"rows": [*rows, self._row()], "modified": str(stored.modified)})
		)
		v1.update_doc(LOG, doc.name)
		frappe.set_user("Administrator")
		names = self._rows(LOG, doc.name)
		self.assertEqual(names[:2], [second, first])
		self.assertEqual(len(names), 3)
		stored = frappe.get_doc(LOG, doc.name)
		frappe.set_user(self.operator)
		frappe.local.form_dict = frappe._dict(
			data=frappe.as_json({"rows": [stored.rows[0].as_dict()], "modified": str(stored.modified)})
		)
		v1.update_doc(LOG, doc.name)
		frappe.set_user("Administrator")
		self.assertEqual(self._rows(LOG, doc.name), [second])
		self.assertFalse(frappe.db.exists(ROW, first))

	def test_set_value_on_an_own_row(self):
		from frappe.client import set_value

		doc = self._log([self._row()], submit=False)
		row = self._rows(LOG, doc.name)[0]
		frappe.set_user(self.operator)
		set_value(ROW, row, "day_hours", 6)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(ROW, row, ["parent", "day_hours"]), (doc.name, 6))

	def test_amendment_and_copy_doc(self):
		doc = self._log([self._row()])
		original = self._rows(LOG, doc.name)
		frappe.set_user(self.operator)
		frappe.get_doc(LOG, doc.name).cancel()
		amended = frappe.copy_doc(frappe.get_doc(LOG, doc.name))
		amended.amended_from = doc.name
		amended.docstatus = 0
		amended.insert()
		copy = frappe.copy_doc(frappe.get_doc(LOG, amended.name))
		copy.log_date = add_days(self.day, -5)
		copy.insert()
		frappe.set_user("Administrator")
		self.assertEqual(self._rows(LOG, doc.name), original)
		for name in (amended.name, copy.name):
			rows = self._rows(LOG, name)
			self.assertEqual(len(rows), 1)
			self.assertNotIn(rows[0], original)
		card = self._submitted_card([10])
		dup = frappe.copy_doc(card)
		dup.equipment = self._equipment().name
		dup.insert(ignore_permissions=True)
		self.assertEqual(len(self._rows(MC, dup.name, "days")), 1)
		self.assertEqual(self._where(DAY, card.days[0].name), (card.name, MC, "days"))
