# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Standalone writes of Equipment Transport Item rows (found in the D3 security review,
QA-Evidence 2026-10-20-card-d3-fix, probe `d3fix-probe-child-row.json`). POST
/api/resource/Equipment Transport Item (frappe.api.v1.create_doc = new_doc(child).insert())
checks only the parent's permission and does not run the transport's validate. A user of
company A can so add a row with a company-B machine and its assignment to a company-A
transport; cancelling the transport then deletes or reopens that assignment
(card.transfer.reverse_transfer, ignore_permissions). The proofs below fail on main
6a4c6d4 (which ones: QA-Evidence 2026-10-21-card-transport-item-rows); the guards keep
the normal transport and transfer paths working. No role is widened; everything is
rolled back."""

import json

import frappe
from frappe.client import delete as rest_delete
from frappe.client import insert as rest_insert
from frappe.client import save as rest_save
from frappe.desk.form.save import savedocs
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate

from card.tests.test_controllers import _ensure_masters
from card.tests.test_transfer import _past_month_year
from card.tests.transport_parties import company_paid_values

DOCTYPE = "Equipment Transport"
ITEM = "Equipment Transport Item"
ASSIGNMENT = "Card Equipment Assignment"
REFUSED = (frappe.PermissionError, frappe.ValidationError)


class TestTransportItemRows(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.month_str, self.year_str = _past_month_year()
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.other = self._other_company()
		self.sup = self._supplier()
		self.proj_a = self._project("A", self.company)
		self.proj_a2 = self._project("A2", self.company)
		self.proj_b = self._project("B", self.other)
		self.eq_a = self._equipment("A", self.company)
		self.eq_b = self._equipment("B", self.other)
		# company B: a machine on its project, with an open assignment
		self.asg_b = self._assign(self.eq_b, self.proj_b, 1)

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures (Administrator, rolled back) ----------

	def _d(self, day):
		return "%s-%s-%02d" % (self.year_str, self.month_str, day)

	def _other_company(self):
		name = "TEST-TRITEM-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "I" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _supplier(self):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-TRITEM-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _project(self, suffix, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-TRITEM-PRJ-%s-%s" % (suffix, self.token)
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, suffix, company):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-TRITEM-EQ-%s-%s" % (suffix, self.token)
		eq.ownership = "ملك"  # owned: no equipment supplier needed
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _assign(self, equipment, project, from_day, to_day=None):
		a = frappe.new_doc(ASSIGNMENT)
		a.equipment = equipment
		a.project = project
		a.from_date = self._d(from_day)
		if to_day:
			a.to_date = self._d(to_day)
		a.insert(ignore_permissions=True)
		return a.name

	def _transport(self, project, *equipment, day=3, submit=True):
		trn = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"date": self._d(day),
				"company": self.company,
				"project": project,
				"transport_supplier": self.sup,
				"amount": 100,
				"items": [{"card_equipment": eq} for eq in equipment],
				**company_paid_values(self.company),
			}
		).insert(ignore_permissions=True)
		if submit:
			trn.submit()
		return trn.name

	def _user(self, roles=("Card Manager",), restrict=None):
		email = f"tritem-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Transport Item Rows",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _as_company_a(self):
		frappe.set_user(self._user(restrict=self.company))

	def _row(self, transport, equipment, **links):
		"""The row POST /api/resource/Equipment Transport Item builds (frappe.api.v1.create_doc)."""
		return frappe.new_doc(
			ITEM,
			parent=transport,
			parenttype=DOCTYPE,
			parentfield="items",
			card_equipment=equipment,
			**links,
		)

	def _forge_row(self, transport, equipment, **links):
		"""A row written past every controller (legacy data or any path that skips the
		row's validate): what reverse_transfer must still refuse to act on."""
		row = self._row(transport, equipment, **links)
		row.idx = 99
		row.docstatus = 1
		row.db_insert()
		return row.name

	def _refused(self, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
		except REFUSED:
			return True
		return False

	def _cancel(self, transport):
		"""Cancel; a refusal is undone like a failed request (the assignment checks below
		then see the database as the user would)."""
		frappe.db.savepoint("tritem_cancel")
		try:
			frappe.get_doc(DOCTYPE, transport).cancel()
			return True
		except REFUSED:
			frappe.db.rollback(save_point="tritem_cancel")
			return False

	def _assignment(self, name):
		return frappe.db.get_value(ASSIGNMENT, name, ["name", "to_date"], as_dict=True)

	# ---------- proofs: fail on main 6a4c6d4 ----------

	def test_standalone_row_insert_into_submitted_transport_refused(self):
		trn = self._transport(self.proj_a, self.eq_a)
		self._as_company_a()
		self.assertTrue(
			self._refused(self._row(trn, self.eq_b, created_assignment=self.asg_b).insert),
			"a standalone row was added to a submitted transport",
		)

	def test_standalone_row_insert_into_draft_transport_refused(self):
		trn = self._transport(self.proj_a, self.eq_a, submit=False)
		self._as_company_a()
		self.assertTrue(
			self._refused(self._row(trn, self.eq_b, created_assignment=self.asg_b).insert),
			"a standalone row was added to a draft transport",
		)

	def test_standalone_row_insert_own_company_machine_refused(self):
		# even the user's own machine: the row skips the transport's checks (company,
		# movement, duplicates, cost shares), so rows are written through the transport only
		eq_a2 = self._equipment("A2", self.company)
		trn = self._transport(self.proj_a, self.eq_a, submit=False)
		self._as_company_a()
		self.assertTrue(self._refused(self._row(trn, eq_a2).insert))

	def test_standalone_row_save_refused(self):
		# frappe.client.save of a row dict: the row's own save, the transport's validate skipped
		trn = self._transport(self.proj_a, self.eq_a, submit=False)
		row = frappe.get_doc(DOCTYPE, trn).items[0].as_dict()
		row.update({"doctype": ITEM, "card_equipment": self.eq_b})
		self._as_company_a()
		self.assertTrue(self._refused(rest_save, row))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.get_doc(DOCTYPE, trn).items[0].card_equipment, self.eq_a)

	def test_standalone_row_update_of_submitted_transport_refused(self):
		# PUT /api/resource/Equipment Transport Item/<row> (frappe.api.v1.update_doc)
		trn = self._transport(self.proj_a, self.eq_a)
		name = frappe.get_doc(DOCTYPE, trn).items[0].name
		self._as_company_a()
		row = frappe.get_doc(ITEM, name)
		row.update({"created_assignment": self.asg_b, "amount": 1})
		self.assertTrue(self._refused(row.save))
		frappe.set_user("Administrator")
		self.assertNotEqual(frappe.db.get_value(ITEM, name, "created_assignment"), self.asg_b)

	def test_standalone_row_delete_refused(self):
		# DELETE /api/resource/Equipment Transport Item/<row> (frappe.api.v1.delete_doc): a
		# row of a submitted transport would escape the cancel; a draft's cost shares break
		submitted = self._transport(self.proj_a, self.eq_a)
		draft = self._transport(self.proj_a, self._equipment("A2", self.company), submit=False)
		self._as_company_a()
		for trn in (submitted, draft):
			name = frappe.db.get_value(ITEM, {"parent": trn, "parenttype": DOCTYPE}, "name")
			self.assertTrue(self._refused(frappe.delete_doc, ITEM, name), trn)
			self.assertTrue(frappe.db.exists(ITEM, name), trn)

	def test_standalone_row_saved_as_cancel_refused(self):
		# a row of a submitted transport saved alone with docstatus 2 is a "cancel" in
		# frappe (no validate, no update-after-submit check): its values were stored
		trn = self._transport(self.proj_a, self.eq_a)
		name = frappe.get_doc(DOCTYPE, trn).items[0].name
		self._as_company_a()
		row = frappe.get_doc(ITEM, name)
		row.update({"docstatus": 2, "card_equipment": self.eq_b, "amount": 1})
		self.assertTrue(self._refused(row.save))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(ITEM, name, "card_equipment"), self.eq_a)

	def test_cancel_request_cannot_rewrite_rows(self):
		# a cancel sent as a save with docstatus 2 stores the rows the request sent and
		# reverse_transfer then undoes them: company B's assignment would be deleted
		trn = self._transport(self.proj_a, self.eq_a)
		self._as_company_a()
		doc = frappe.get_doc(DOCTYPE, trn)
		doc.items[0].card_equipment = self.eq_b
		doc.items[0].created_assignment = self.asg_b
		doc.docstatus = 2
		frappe.db.savepoint("tritem_cancel_save")
		try:
			doc.save()
		except REFUSED:
			frappe.db.rollback(save_point="tritem_cancel_save")
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists(ASSIGNMENT, self.asg_b), "cancel deleted company B's assignment")
		self.assertEqual(frappe.get_doc(DOCTYPE, trn).items[0].card_equipment, self.eq_a)

	def test_cancel_by_restricted_user_never_deletes_other_company_assignment(self):
		# the probe of the security review, end to end with a forged row
		trn = self._transport(self.proj_a, self.eq_a)
		self._forge_row(trn, self.eq_b, created_assignment=self.asg_b)
		self._as_company_a()
		self._cancel(trn)
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists(ASSIGNMENT, self.asg_b), "cancel deleted company B's assignment")

	def test_cancel_never_reopens_other_company_assignment(self):
		# company B's machine left its project on day 2: no open assignment, so a reopen is accepted
		frappe.delete_doc(ASSIGNMENT, self.asg_b, force=1, ignore_permissions=True)
		closed_b = self._assign(self.eq_b, self.proj_b, 1, 2)
		trn = self._transport(self.proj_a, self.eq_a)
		self._forge_row(trn, self.eq_b, previous_assignment=closed_b)
		self._cancel(trn)
		self.assertEqual(
			getdate(self._assignment(closed_b).to_date),
			getdate(self._d(2)),
			"cancel reopened company B's closed assignment",
		)

	def test_cancel_never_deletes_another_transports_assignment(self):
		# same company: machine X came to A2 with an earlier transport T0; a row forged
		# into a later transport T1 names X and T0's assignment
		eq_x = self._equipment("X", self.company)
		t0 = self._transport(self.proj_a2, eq_x, day=1)
		asg_t0 = frappe.get_doc(DOCTYPE, t0).items[0].created_assignment
		self.assertTrue(asg_t0)
		t1 = self._transport(self.proj_a, self.eq_a, day=5)
		self._forge_row(t1, eq_x, created_assignment=asg_t0)
		self._cancel(t1)
		self.assertTrue(frappe.db.exists(ASSIGNMENT, asg_t0), "cancel deleted another transport's assignment")

	# ---------- guards: the authorised paths keep working ----------

	def test_transport_create_save_submit_cancel_by_restricted_user(self):
		prev = self._assign(self.eq_a, self.proj_a, 1)
		self._as_company_a()
		trn = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"date": self._d(3),
				"company": self.company,
				"project": self.proj_a2,
				"transport_supplier": self.sup,
				"amount": 100,
				"items": [{"card_equipment": self.eq_a}],
				**company_paid_values(self.company),
			}
		).insert()
		trn.append("items", {"card_equipment": self._as_admin(self._equipment, "A3", self.company)})
		trn.save()
		trn.submit()
		trn.reload()
		created = [r.created_assignment for r in trn.items]
		self.assertTrue(all(created))
		self.assertEqual(trn.items[0].previous_assignment, prev)
		self.assertEqual(getdate(self._assignment(prev).to_date), getdate(self._d(3)))
		trn.cancel()
		for name in created:
			self.assertFalse(frappe.db.exists(ASSIGNMENT, name))
		self.assertFalse(self._assignment(prev).to_date)

	def _as_admin(self, fn, *args):
		user = frappe.session.user
		frappe.set_user("Administrator")
		try:
			return fn(*args)
		finally:
			frappe.set_user(user)

	def test_rows_added_through_the_transport_rest_insert(self):
		# frappe.client.insert of a row dict appends it to the transport and saves the
		# transport (its validate runs): the supported REST path stays open for a draft
		trn = self._transport(self.proj_a, self.eq_a, submit=False)
		eq_a2 = self._equipment("A2", self.company)
		self._as_company_a()
		rest_insert(
			{
				"doctype": ITEM,
				"parent": trn,
				"parenttype": DOCTYPE,
				"parentfield": "items",
				"card_equipment": eq_a2,
			}
		)
		frappe.set_user("Administrator")
		self.assertEqual([r.card_equipment for r in frappe.get_doc(DOCTYPE, trn).items], [self.eq_a, eq_a2])

	def test_cancel_after_assignment_change_refused_whole(self):
		# a created assignment changed after the transport: the cancel is refused and
		# nothing is half undone (the previous assignment stays closed)
		prev = self._assign(self.eq_a, self.proj_a, 1)
		trn = self._transport(self.proj_a2, self.eq_a)
		created = frappe.get_doc(DOCTYPE, trn).items[0].created_assignment
		frappe.db.set_value(ASSIGNMENT, created, "from_date", self._d(9))
		self.assertFalse(self._cancel(trn))
		self.assertEqual(frappe.db.get_value(DOCTYPE, trn, "docstatus"), 1)
		self.assertTrue(frappe.db.exists(ASSIGNMENT, created))
		self.assertEqual(getdate(self._assignment(prev).to_date), getdate(self._d(3)))

	def test_cancel_with_missing_created_assignment_still_reopens_previous(self):
		# an assignment deleted since has nothing to undo; the rest of the move is undone
		prev = self._assign(self.eq_a, self.proj_a, 1)
		trn = self._transport(self.proj_a2, self.eq_a)
		created = frappe.get_doc(DOCTYPE, trn).items[0].created_assignment
		frappe.delete_doc(ASSIGNMENT, created, force=1, ignore_permissions=True)
		self.assertTrue(self._cancel(trn))
		self.assertFalse(self._assignment(prev).to_date)

	def test_desk_cancel_of_unchanged_transport(self):
		# Desk sends the loaded transport back as JSON (dates and numbers as text)
		prev = self._assign(self.eq_a, self.proj_a, 1)
		trn = self._transport(self.proj_a2, self.eq_a)
		self._as_company_a()
		doc = frappe.get_doc(DOCTYPE, trn).as_dict()
		doc["docstatus"] = 2
		savedocs(json.dumps(doc, default=str), "Cancel")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DOCTYPE, trn, "docstatus"), 2)
		self.assertFalse(self._assignment(prev).to_date)

	def test_rows_removed_through_the_transport(self):
		# frappe.client.delete_doc of a row removes it from the transport and saves the
		# transport; a draft transport itself can still be deleted with its rows
		eq_a2 = self._equipment("A2", self.company)
		trn = self._transport(self.proj_a, self.eq_a, eq_a2, submit=False)
		doc = frappe.get_doc(DOCTYPE, trn)
		self._as_company_a()
		rest_delete(ITEM, doc.items[1].name)
		frappe.set_user("Administrator")
		self.assertEqual([r.card_equipment for r in frappe.get_doc(DOCTYPE, trn).items], [self.eq_a])
		frappe.delete_doc(DOCTYPE, trn)
		self.assertFalse(frappe.db.exists(ITEM, {"parent": trn, "parenttype": DOCTYPE}))

	def test_rows_added_through_the_transport_still_check_company(self):
		trn = self._transport(self.proj_a, self.eq_a, submit=False)
		doc = frappe.get_doc(DOCTYPE, trn)
		doc.append("items", {"card_equipment": self.eq_b})
		self.assertTrue(self._refused(doc.save))

	def test_amend_after_cancel_moves_again(self):
		trn = self._transport(self.proj_a, self.eq_a)
		frappe.get_doc(DOCTYPE, trn).cancel()
		# like Desk's amend: no_copy fields (the rows' assignment links) are not copied
		amended = frappe.copy_doc(frappe.get_doc(DOCTYPE, trn), ignore_no_copy=False)
		amended.amended_from = trn
		amended.docstatus = 0  # copy_doc keeps the cancelled status
		# the header mirrors are not no_copy; links are checked before validate clears them
		amended.previous_assignment = amended.created_assignment = None
		amended.date = add_days(self._d(3), 1)
		amended.insert(ignore_permissions=True)
		amended.submit()
		amended.reload()
		self.assertTrue(amended.items[0].created_assignment)
		self.assertTrue(frappe.db.exists(ASSIGNMENT, amended.items[0].created_assignment))

	# ---------- two moves of one machine on the same date (review of FR-073) ----------
	# _later_transfer sees only later dates and the claim check only the same link field,
	# so on main a cancel of the first move undid an assignment the second move relies on.

	def _links(self, transport):
		row = frappe.get_doc(DOCTYPE, transport).items[0]
		return row.created_assignment, row.previous_assignment

	def _to_workshop(self, equipment, day=3):
		loc = frappe.new_doc("Location")
		loc.location_name = "TEST-TRITEM-SHOP-" + self.token
		loc.insert(ignore_permissions=True)
		trn = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"date": self._d(day),
				"company": self.company,
				"destination_type": "Workshop",
				"destination_location": loc.name,
				"payer": "Equipment Supplier",
				"cost_bearer": "Equipment Supplier",
				"items": [{"card_equipment": equipment}],
			}
		).insert(ignore_permissions=True)
		trn.submit()
		return trn.name

	def _same_day_chain(self):
		# a machine on no project: T1 opens X on A from day 3; T2 on day 3 closes X and
		# opens Y on A2 from day 4
		eq = self._equipment("SD", self.company)
		t1 = self._transport(self.proj_a, eq)
		t2 = self._transport(self.proj_a2, eq)
		x, _none = self._links(t1)
		y, closed = self._links(t2)
		self.assertEqual(closed, x)
		return eq, t1, t2, x, y

	def test_same_day_first_move_cancel_refused(self):
		_eq, t1, _t2, x, _y = self._same_day_chain()
		self.assertFalse(self._cancel(t1))
		self.assertEqual(frappe.db.get_value(DOCTYPE, t1, "docstatus"), 1)
		self.assertTrue(
			frappe.db.exists(ASSIGNMENT, x), "cancel deleted the assignment the later move closed"
		)
		self.assertEqual(getdate(self._assignment(x).to_date), getdate(self._d(3)))

	def test_same_day_moves_cancel_in_order(self):
		eq, t1, t2, x, y = self._same_day_chain()
		self.assertTrue(self._cancel(t2))
		self.assertFalse(frappe.db.exists(ASSIGNMENT, y))
		self.assertFalse(self._assignment(x).to_date)
		self.assertTrue(self._cancel(t1))
		self.assertFalse(frappe.db.exists(ASSIGNMENT, {"equipment": eq}))

	def test_same_day_workshop_then_project_refused_at_submit(self):
		# the second case of the review cannot happen: back from the workshop to a project
		# on the same date would open an assignment on the day the project one was closed,
		# which the assignment overlap check refuses; the first move still cancels
		prev = self._assign(self.eq_a, self.proj_a, 1)
		t1 = self._to_workshop(self.eq_a)
		self.assertEqual(self._links(t1), (None, prev))
		frappe.db.savepoint("tritem_same_day_submit")
		self.assertTrue(self._refused(self._transport, self.proj_a2, self.eq_a))
		frappe.db.rollback(save_point="tritem_same_day_submit")
		self.assertTrue(self._cancel(t1))
		self.assertFalse(self._assignment(prev).to_date)

	def test_same_day_chain_restricted_user_cannot_cancel_first_move(self):
		_eq, t1, _t2, x, _y = self._same_day_chain()
		self._as_company_a()
		self.assertFalse(self._cancel(t1))
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists(ASSIGNMENT, x))

	def test_cancel_after_created_assignment_closed_by_hand_refused(self):
		prev = self._assign(self.eq_a, self.proj_a, 1)
		trn = self._transport(self.proj_a2, self.eq_a)
		created, _closed = self._links(trn)
		frappe.db.set_value(ASSIGNMENT, created, "to_date", self._d(9))
		self.assertFalse(self._cancel(trn))
		self.assertEqual(getdate(self._assignment(created).to_date), getdate(self._d(9)))
		self.assertEqual(getdate(self._assignment(prev).to_date), getdate(self._d(3)))

	def test_old_transport_without_links_cancels_and_touches_nothing(self):
		# a transport from before the row links (or a machine already on the project) has
		# nothing to undo; a same-day move of the machine does not block its cancel
		_eq, t1, _t2, x, y = self._same_day_chain()
		row = frappe.get_doc(DOCTYPE, t1).items[0]
		frappe.db.set_value(ITEM, row.name, {"created_assignment": None, "previous_assignment": None})
		frappe.db.set_value(DOCTYPE, t1, {"created_assignment": None, "previous_assignment": None})
		self.assertTrue(self._cancel(t1))
		self.assertTrue(frappe.db.exists(ASSIGNMENT, x))
		self.assertTrue(frappe.db.exists(ASSIGNMENT, y))
