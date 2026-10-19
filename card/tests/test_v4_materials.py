# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.0.0 equipment materials: operator request -> supervisor review -> management approval ->
standard ERPNext Material Requests, tool custody, reports and the operator page."""

import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, nowdate

from card import materials
from card.tests.test_controllers import _ensure_masters


class TestV4Materials(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]
		self.project = self._m["project"]
		leaves = frappe.get_all(
			"Warehouse", filters={"company": self.company, "is_group": 0}, pluck="name", order_by="name"
		)
		if len(leaves) < 2:
			self.skipTest("the test company needs two warehouses")
		self.store, self.custody = leaves[0], leaves[1]
		# the ERPNext setup wizard makes these on a real site; a clean CI test site has none
		for purpose in ("Material Receipt", "Material Transfer", "Material Issue"):
			if not frappe.db.exists("Stock Entry Type", purpose):
				frappe.get_doc({"doctype": "Stock Entry Type", "name": purpose, "purpose": purpose}).insert(
					ignore_permissions=True
				)
		frappe.db.set_single_value("Card Settings", "default_store_warehouse", self.store)
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", self.custody)
		frappe.db.set_single_value("Card Settings", "repeat_request_days", 30)
		self.op_user, self.operator = self._operator("op")
		self.eq = self._equipment(self.operator)
		self.filter = self._item("FILTER", stock=1)
		self.tool = self._item("WRENCH", stock=1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders ----------
	def _user(self, prefix, roles):
		email = f"v4-{prefix}-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		return email

	def _operator(self, prefix):
		user = self._user(prefix, ["Card Operator"])
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"V4 {prefix} {self.token}",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": "Active",
				"user_id": user,
			}
		).insert(ignore_permissions=True)
		return user, emp.name

	def _equipment(self, operator):
		eq = frappe.get_doc(
			{
				"doctype": "Card Equipment",
				"company": self.company,
				"equipment_name": f"V4-EQ-{frappe.generate_hash(length=6)}",
				"equipment_type": self._m["etype"],
				"ownership": "ملك",
				"daily_hours": 10,
				"operator_on": "الشركة",
				"operator": operator,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": eq.name,
				"project": self.project,
				"from_date": "2026-01-01",
			}
		).insert(ignore_permissions=True)
		return eq.name

	def _item(self, name, stock=1, fixed_asset=0):
		code = f"V4-{name}-{self.token}"
		doc = {
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": stock,
			"valuation_rate": 10,
		}
		if fixed_asset:
			category = frappe.db.get_value("Asset Category", {}, "name")
			if not category:
				self.skipTest("no Asset Category on this site")
			doc.update({"is_stock_item": 0, "is_fixed_asset": 1, "asset_category": category})
		frappe.get_doc(doc).insert(ignore_permissions=True)
		return code

	def _ask(self, items, equipment=None):
		frappe.set_user(self.op_user)
		try:
			return materials.submit_needs(equipment or self.eq, json.dumps(items))
		finally:
			frappe.set_user("Administrator")

	# ---------- operator ----------
	def test_operator_asks_for_his_own_machine(self):
		name = self._ask([{"kind": "Part", "item_code": self.filter, "qty": 2, "reason": "service"}])
		doc = frappe.get_doc("Equipment Needs Request", name)
		self.assertEqual((doc.docstatus, doc.operator, doc.project), (1, self.operator, self.project))
		self.assertEqual((doc.entered_by, doc.on_behalf), (self.op_user, 0))
		self.assertEqual(doc.review_status, "Pending")

	def test_operator_cannot_ask_for_another_machine(self):
		_other_user, other_operator = self._operator("other")
		other_eq = self._equipment(other_operator)
		with self.assertRaises(frappe.PermissionError):
			self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}], equipment=other_eq)

	def test_supervisor_enters_on_behalf_and_both_names_are_kept(self):
		supervisor = self._user("sup", ["Card Supervisor"])
		frappe.set_user(supervisor)
		doc = frappe.get_doc(
			{
				"doctype": "Equipment Needs Request",
				"equipment": self.eq,
				"operator": self.operator,
				"items": [{"kind": "Part", "item_code": self.filter, "qty": 1}],
			}
		).insert()
		frappe.set_user("Administrator")
		self.assertEqual((doc.entered_by, doc.on_behalf, doc.operator), (supervisor, 1, self.operator))

	def test_operator_sees_only_his_requests(self):
		mine = self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		other_user, other_operator = self._operator("seen")
		other_eq = self._equipment(other_operator)
		frappe.set_user(other_user)
		theirs = materials.submit_needs(
			other_eq, json.dumps([{"kind": "Part", "description": "lamp", "qty": 2}])
		)
		visible = frappe.get_list("Equipment Needs Request", pluck="name")
		self.assertIn(theirs, visible)
		self.assertNotIn(mine, visible)
		self.assertFalse(frappe.has_permission("Equipment Needs Request", "read", doc=mine))
		frappe.set_user("Administrator")

	def test_repeated_request_is_flagged_for_review_only(self):
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		second = frappe.get_doc(
			"Equipment Needs Request", self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		)
		self.assertEqual(second.items[0].repeat_flag, 1)
		self.assertTrue(second.items[0].last_requested_on)
		from card.card.report.repeat_equipment_requests.repeat_equipment_requests import execute

		self.assertIn(second.name, [r.request for r in execute({"equipment": self.eq})[1]])

	# ---------- supervisor + management ----------
	def _review(self):
		review = frappe.get_doc({"doctype": "Equipment Needs Review", "project": self.project}).insert()
		materials.pull_requests(review.name)
		return frappe.get_doc("Equipment Needs Review", review.name)

	def test_full_cycle_to_material_requests(self):
		request = self._ask(
			[
				{"kind": "Part", "item_code": self.filter, "qty": 4},
				{"kind": "Part", "description": "unknown lamp", "qty": 2},
				{"kind": "Tool", "item_code": self.tool, "qty": 1},
			]
		)
		review = self._review()
		lines = {line.request_item: line for line in review.items if line.request == request}
		self.assertEqual(len(lines), 3)
		by_kind = {(line.kind, line.item_code or line.description): line for line in review.items}
		filter_line = by_kind[("Part", self.filter)]
		lamp_line = by_kind[("Part", "unknown lamp")]
		filter_line.found_qty, filter_line.approved_qty = 1, 3
		filter_line.route = "Buy for project"
		filter_line.inspection = "Inspected"
		filter_line.requested_qty = 99  # cannot be changed: it is what the operator asked
		lamp_line.approved_qty = 0  # refused
		review.save()
		review.reload()
		filter_line = next(line for line in review.items if line.item_code == self.filter)
		self.assertEqual(
			(filter_line.requested_qty, filter_line.found_qty, filter_line.approved_qty), (4, 1, 3)
		)
		self.assertEqual(filter_line.inspected_by, "Administrator")
		review.submit()
		self.assertEqual(
			frappe.db.get_value("Equipment Needs Request", request, "review_status"), "In review"
		)

		card_user = self._user("cu", ["Card User"])
		frappe.set_user(card_user)
		with self.assertRaises(frappe.PermissionError):
			materials.approve_review(review.name)
		frappe.set_user("Administrator")

		created = materials.approve_review(review.name)
		mrs = {frappe.db.get_value("Material Request", n, "material_request_type"): n for n in created}
		self.assertEqual(set(mrs), {"Purchase", "Material Transfer"})
		purchase = frappe.get_doc("Material Request", mrs["Purchase"])
		row = purchase.items[0]
		self.assertEqual((row.item_code, flt(row.qty), row.project), (self.filter, 3, self.project))
		self.assertTrue(row.cost_center)
		if frappe.get_meta("Material Request Item").has_field("card_equipment"):
			self.assertEqual(row.card_equipment, self.eq)
		transfer = frappe.get_doc("Material Request", mrs["Material Transfer"])
		self.assertEqual(
			(transfer.items[0].warehouse, transfer.items[0].from_warehouse), (self.custody, self.store)
		)
		self.assertEqual(purchase.docstatus, 0)  # drafts for the buying team
		self.assertEqual(frappe.db.get_value("Equipment Needs Request", request, "review_status"), "Approved")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Equipment Needs Review", review.name).cancel()

	def test_card_manager_approves_with_his_own_erpnext_rights(self):
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		review = self._review()
		review.submit()
		manager = self._user("mgr", ["Card Manager"])
		before = frappe.db.count("Material Request")
		frappe.set_user(manager)
		with self.assertRaises(frappe.PermissionError):
			materials.approve_review(review.name)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.count("Material Request"), before)
		self.assertNotEqual(
			frappe.db.get_value("Equipment Needs Review", review.name, "approval_status"), "Approved"
		)

		frappe.get_doc("User", manager).add_roles("Stock User")
		frappe.set_user(manager)
		try:
			(name,) = materials.approve_review(review.name)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Material Request", name, ["owner", "docstatus"]), (manager, 0))

	def test_supervisor_reads_equipment_without_editing_it(self):
		supervisor = self._user("sup3", ["Card Supervisor"])
		self.assertTrue(frappe.has_permission("Card Equipment", "read", self.eq, user=supervisor))
		self.assertFalse(frappe.has_permission("Card Equipment", "write", self.eq, user=supervisor))

	def test_reports_follow_the_supervisors_project_permission(self):
		from card.card.report.equipment_needs_summary import equipment_needs_summary as summary
		from card.card.report.repeat_equipment_requests import repeat_equipment_requests as repeat

		other = frappe.get_doc(
			{"doctype": "Project", "project_name": f"V4 other {self.token}", "company": self.company}
		).insert(ignore_permissions=True)
		other_user, other_operator = self._operator("op2")
		other_eq = self._equipment(other_operator)
		frappe.db.set_value(
			"Card Equipment Assignment", {"equipment": other_eq}, "project", other.name, update_modified=False
		)
		for user, eq in ((self.op_user, self.eq), (other_user, other_eq)):
			frappe.set_user(user)
			for _i in range(2):  # the second one is a repeat
				materials.submit_needs(eq, json.dumps([{"kind": "Part", "item_code": self.filter, "qty": 1}]))
			frappe.set_user("Administrator")
		for project in (self.project, other.name):
			review = frappe.get_doc({"doctype": "Equipment Needs Review", "project": project}).insert()
			materials.pull_requests(review.name)
			frappe.get_doc("Equipment Needs Review", review.name).submit()

		supervisor = self._user("sup4", ["Card Supervisor"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": supervisor, "allow": "Project", "for_value": self.project}
		).insert(ignore_permissions=True)
		frappe.set_user(supervisor)
		try:
			repeats = repeat.execute({})[1]
			lines = summary.execute({})[1]
		finally:
			frappe.set_user("Administrator")
		self.assertTrue(repeats)
		self.assertEqual({r["equipment"] for r in repeats}, {self.eq})
		shares = " ".join(str(r.get("equipment")) for r in lines)
		self.assertIn(self.eq, shares)
		self.assertNotIn(other_eq, shares)

	def test_free_text_line_must_be_matched_before_approval(self):
		self._ask([{"kind": "Part", "description": "odd seal", "qty": 1}])
		review = self._review()
		review.submit()
		with self.assertRaises(frappe.ValidationError):
			materials.approve_review(review.name)

	def test_store_issue_keeps_equipment_through_erpnext_mapping(self):
		if not frappe.get_meta("Stock Entry Detail").has_field("card_equipment"):
			self.skipTest("Card Equipment dimension not on this site")
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 2}])
		review = self._review()
		review.submit()
		(name,) = materials.approve_review(review.name)
		mr = frappe.get_doc("Material Request", name)
		self.assertEqual(mr.material_request_type, "Material Issue")
		mr.submit()
		from erpnext.stock.doctype.material_request.material_request import make_stock_entry

		entry = make_stock_entry(mr.name)
		self.assertEqual(entry.items[0].card_equipment, self.eq)
		self.assertEqual(entry.items[0].project, self.project)

	def test_summary_lists_each_machines_share(self):
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 4}])
		review = self._review()
		review.submit()
		from card.card.report.equipment_needs_summary.equipment_needs_summary import execute

		rows = {r["item_code"]: r for r in execute({"project": self.project})[1] if r["item_code"]}
		self.assertEqual(rows[self.filter]["approved_qty"], 4)
		self.assertIn(self.eq, rows[self.filter]["equipment"])

	def test_consumption_counts_the_issue_not_the_purchase(self):
		if not frappe.get_meta("Stock Entry Detail").has_field("card_equipment"):
			self.skipTest("Card Equipment dimension not on this site")

		def entry(purpose, row):
			doc = frappe.get_doc(
				{
					"doctype": "Stock Entry",
					"stock_entry_type": purpose,
					"purpose": purpose,
					"company": self.company,
					"items": [dict(row, item_code=self.filter, basic_rate=10)],
				}
			)
			try:
				doc.insert(ignore_permissions=True)
				doc.submit()
			except frappe.ValidationError as e:
				self.skipTest(f"stock entries cannot be posted on this site: {e}")
			return doc

		entry("Material Receipt", {"qty": 5, "t_warehouse": self.store})
		entry(
			"Material Issue",
			{"qty": 2, "s_warehouse": self.store, "project": self.project, "card_equipment": self.eq},
		)
		from card.card.report.equipment_consumption.equipment_consumption import execute

		rows = execute({"equipment": self.eq})[1]
		self.assertEqual([(r["item_code"], r["qty"]) for r in rows], [(self.filter, 2)])
		self.assertEqual(rows[0]["project"], self.project)
		self.assertGreater(rows[0]["amount"], 0)

	def test_review_takes_operator_requests_only(self):
		review = frappe.get_doc({"doctype": "Equipment Needs Review", "project": self.project})
		review.append("items", {"item_code": self.filter, "approved_qty": 5})
		with self.assertRaises(frappe.ValidationError):
			review.insert()

	def test_supervisor_edit_keeps_who_entered_it(self):
		frappe.set_user(self.op_user)
		doc = frappe.get_doc(
			{
				"doctype": "Equipment Needs Request",
				"equipment": self.eq,
				"operator": self.operator,
				"review_status": "Approved",  # not the client's to set
				"items": [{"kind": "Part", "item_code": self.filter, "qty": 1}],
			}
		).insert()
		frappe.set_user(self._user("sup2", ["Card Supervisor"]))
		doc = frappe.get_doc("Equipment Needs Request", doc.name)
		doc.items[0].qty = 2
		doc.save()
		frappe.set_user("Administrator")
		self.assertEqual((doc.entered_by, doc.on_behalf, doc.review_status), (self.op_user, 0, "Pending"))

	# ---------- tool custody ----------
	def _custody(self, movement, qty=1, employee=None, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Employee Tool Custody",
				"employee": employee or self.operator,
				"movement": movement,
				"item_code": self.tool,
				"qty": qty,
				"date": nowdate(),
				**kw,
			}
		).insert()
		doc.submit()
		return doc

	def test_custody_hand_over_return_transfer_and_loss(self):
		hand = self._custody("Handover", qty=2, warehouse=self.store)
		entry = frappe.get_doc("Stock Entry", hand.stock_entry)
		self.assertEqual((entry.docstatus, entry.purpose), (0, "Material Transfer"))
		self.assertEqual((entry.items[0].s_warehouse, entry.items[0].t_warehouse), (self.store, self.custody))
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 2)
		with self.assertRaises(frappe.ValidationError):
			self._custody("Return", qty=3, warehouse=self.store)
		_u, other = self._operator("recv")
		self._custody("Transfer", qty=1, to_employee=other)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 1)
		self.assertEqual(materials.custody_balance(other, self.tool), 1)
		loss = self._custody("Loss", qty=1, project=self.project)
		self.assertEqual(loss.review_required, 1)
		self.assertEqual(frappe.db.get_value("Stock Entry", loss.stock_entry, "purpose"), "Material Issue")
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 0)
		from card.card.report.worker_custody.worker_custody import execute

		held = {(r["employee"], r["item_code"]): r["qty"] for r in execute({})[1]}
		self.assertEqual(held.get((other, self.tool)), 1)
		self.assertNotIn((self.operator, self.tool), held)

	def test_capital_tool_goes_to_the_asset(self):
		asset_item = self._item("DRILL", fixed_asset=1)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Employee Tool Custody",
					"employee": self.operator,
					"movement": "Handover",
					"item_code": asset_item,
					"qty": 1,
					"warehouse": self.store,
				}
			).insert()

	def test_cancelling_a_handover_removes_its_draft_stock_entry(self):
		hand = self._custody("Handover", warehouse=self.store)
		entry = hand.stock_entry
		hand.cancel()
		self.assertFalse(frappe.db.exists("Stock Entry", entry))

	def test_approval_fields_cannot_be_set_by_hand(self):
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		review = self._review()
		review.submit()
		review.approval_status = "Approved"
		with self.assertRaises(frappe.ValidationError):
			review.save()  # update after submit refuses it

	def test_cancel_deletes_only_its_own_stock_entry(self):
		other = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": self.company,
				"items": [{"item_code": self.tool, "qty": 1, "t_warehouse": self.store, "basic_rate": 10}],
			}
		).insert(ignore_permissions=True)
		hand = self._custody("Handover", warehouse=self.store)
		frappe.db.set_value("Employee Tool Custody", hand.name, "stock_entry", other.name)
		hand.reload()
		hand.cancel()
		self.assertTrue(frappe.db.exists("Stock Entry", other.name))

	# ---------- operator page ----------
	def test_operator_page_context(self):
		frappe.set_user(self.op_user)
		ctx = materials.get_portal_context()
		frappe.set_user("Administrator")
		self.assertTrue(ctx["allowed"])
		self.assertEqual([m["name"] for m in ctx["machines"]], [self.eq])
		self.assertEqual(ctx["machines"][0]["project"], self.project)

	def test_operator_page_gives_the_session_a_csrf_token(self):
		import importlib

		page = importlib.import_module("card.www.equipment-needs.index")
		frappe.set_user(self.op_user)
		try:
			frappe.local.session.data.csrf_token = None
			page.get_context(frappe._dict())
			self.assertTrue(frappe.local.session.data.csrf_token)
		finally:
			frappe.set_user("Administrator")

	def test_page_endpoints_refuse_users_without_a_card_role(self):
		outsider = self._user("out", [])
		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			materials.get_portal_context()
		with self.assertRaises(frappe.PermissionError):
			materials.search_items("V4")
		frappe.set_user("Administrator")

	def test_operator_role_has_no_desk(self):
		from card.patches.v4_0_0 import ensure_materials_roles

		ensure_materials_roles.execute()
		self.assertEqual(frappe.db.get_value("Role", "Card Operator", "desk_access"), 0)
		self.assertEqual(frappe.db.get_value("Role", "Card Supervisor", "desk_access"), 1)
