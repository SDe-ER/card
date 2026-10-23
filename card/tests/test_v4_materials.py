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

	def test_operator_asks_for_a_tool(self):
		# CARD Mobile sends the kind the operator chose on each line; the server keeps it
		name = self._ask(
			[
				{"kind": "Tool", "item_code": self.tool, "qty": 1},
				{"kind": "Part", "item_code": self.filter, "qty": 2},
				{"kind": "anything else", "description": "lamp", "qty": 1},
			]
		)
		kinds = [row.kind for row in frappe.get_doc("Equipment Needs Request", name).items]
		self.assertEqual(kinds, ["Tool", "Part", "Part"])

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
		self.assertEqual(set(mrs), {"Purchase"})  # the tool goes through a custody handover (#113)
		purchase = frappe.get_doc("Material Request", mrs["Purchase"])
		row = purchase.items[0]
		self.assertEqual((row.item_code, flt(row.qty), row.project), (self.filter, 3, self.project))
		self.assertTrue(row.cost_center)
		if frappe.get_meta("Material Request Item").has_field("card_equipment"):
			self.assertEqual(row.card_equipment, self.eq)
		(draft,) = frappe.get_all(
			"Employee Tool Custody", filters={"review": review.name}, fields=["docstatus", "warehouse"]
		)
		self.assertEqual((draft.docstatus, draft.warehouse), (0, self.store))
		self.assertEqual(purchase.docstatus, 0)  # drafts for the buying team
		self.assertEqual(frappe.db.get_value("Equipment Needs Request", request, "review_status"), "Approved")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("Equipment Needs Review", review.name).cancel()

	def test_a_tool_stays_a_tool_through_review_and_approval(self):
		# the review copies the kind from the request; approval makes a handover draft for the tool
		request = self._ask([{"kind": "Tool", "item_code": self.tool, "qty": 1}])
		review = self._review()
		(line,) = [row for row in review.items if row.request == request]
		self.assertEqual(line.kind, "Tool")
		line.kind = "Part"  # read only on the form; the server takes the request's kind again
		review.save()
		review.reload()
		self.assertEqual([row.kind for row in review.items if row.request == request], ["Tool"])
		review.submit()
		created = materials.approve_review(review.name)
		self.assertFalse(
			frappe.get_all("Material Request Item", filters={"parent": ["in", created or [""]]}),
			"a tool from the store needs no Material Request",
		)
		(draft,) = frappe.get_all(
			"Employee Tool Custody",
			filters={"review": review.name},
			fields=["movement", "item_code", "employee", "docstatus", "handover_status"],
		)
		self.assertEqual(
			(draft.movement, draft.item_code, draft.employee, draft.docstatus, draft.handover_status),
			("Handover", self.tool, self.operator, 0, "Awaiting handover"),
		)
		self.assertEqual(
			frappe.db.get_value("Equipment Needs Request Item", {"parent": request}, "kind"), "Tool"
		)

	def test_a_tool_needs_the_custody_store_before_approval(self):
		self._ask([{"kind": "Tool", "item_code": self.tool, "qty": 1}])
		review = self._review()
		# only matched tool lines: the custody store is the one thing approval can miss
		self.assertEqual({(row.kind, bool(row.item_code)) for row in review.items}, {("Tool", True)})
		review.submit()
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", None)
		before = frappe.db.count("Material Request"), frappe.db.count("Employee Tool Custody")
		with self.assertRaises(frappe.ValidationError):
			materials.approve_review(review.name)
		self.assertEqual(
			(frappe.db.count("Material Request"), frappe.db.count("Employee Tool Custody")), before
		)

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
	def _stock_in(self, qty, item_code=None, warehouse=None):
		entry = frappe.get_doc(
			{
				"doctype": "Stock Entry",
				"stock_entry_type": "Material Receipt",
				"purpose": "Material Receipt",
				"company": self.company,
				"items": [
					{
						"item_code": item_code or self.tool,
						"qty": qty,
						"t_warehouse": warehouse or self.store,
						"basic_rate": 10,
					}
				],
			}
		)
		try:
			entry.insert(ignore_permissions=True)
			entry.submit()
		except frappe.ValidationError as e:
			self.skipTest(f"stock entries cannot be posted on this site: {e}")
		return entry

	def _receipt(self, user="Administrator"):
		"""A private file nobody attached yet: the scanned receipt signed by worker and issuer."""
		frappe.set_user(user)
		try:
			return (
				frappe.get_doc(
					{
						"doctype": "File",
						"file_name": f"receipt-{frappe.generate_hash(length=8)}.pdf",
						"is_private": 1,
						"content": b"%PDF-1.4 signed receipt " + self.token.encode(),
					}
				)
				.insert()
				.file_url
			)
		finally:
			frappe.set_user("Administrator")

	def _custody(self, movement, qty=1, employee=None, submit=True, **kw):
		if submit and movement in ("Handover", "Transfer"):
			kw.setdefault("handover_receipt", self._receipt())
		if submit and movement == "Handover" and kw.get("item_code", self.tool) == self.tool:
			self._stock_in(qty, warehouse=kw.get("warehouse"))
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
		if submit:
			doc.submit()
		return doc

	def test_custody_hand_over_return_transfer_and_loss(self):
		hand = self._custody("Handover", qty=2, warehouse=self.store)
		entry = frappe.get_doc("Stock Entry", hand.stock_entry)
		# confirmed: the transfer is submitted together with the custody record (#113 T7)
		self.assertEqual((entry.docstatus, entry.purpose), (1, "Material Transfer"))
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

	def test_a_tool_line_must_be_a_stock_item(self):
		# #113 G4: a tool goes into custody, so the review refuses a non-stock item for it
		rag = self._item("RAG", stock=0)
		request = self._ask(
			[{"kind": "Tool", "item_code": self.tool, "qty": 1}, {"kind": "Part", "item_code": rag, "qty": 1}]
		)
		review = self._review()
		tool_line = next(row for row in review.items if row.request == request and row.kind == "Tool")
		tool_line.item_code, tool_line.approved_qty = rag, 1
		with self.assertRaises(frappe.ValidationError) as refused:
			review.save()
		self.assertIn(rag, str(refused.exception))  # the item message, not another error
		review = frappe.get_doc("Equipment Needs Review", review.name)
		tool_line = next(row for row in review.items if row.request == request and row.kind == "Tool")
		tool_line.item_code, tool_line.approved_qty = rag, 0  # refusing the line stays possible
		review.save()  # and a non-stock Part line is not affected
		self.assertEqual(
			{(row.kind, row.item_code) for row in review.items if row.request == request},
			{("Tool", rag), ("Part", rag)},
		)

	def test_a_tool_line_cannot_be_a_fixed_asset(self):
		drill = self._item("DRILL", fixed_asset=1)
		request = self._ask([{"kind": "Tool", "item_code": self.tool, "qty": 1}])
		review = self._review()
		(line,) = [row for row in review.items if row.request == request]
		line.item_code, line.approved_qty = drill, 1
		with self.assertRaises(frappe.ValidationError) as refused:
			review.save()
		self.assertIn(drill, str(refused.exception))

	def test_approval_checks_the_tool_item_again(self):
		# the Item can change after the review is submitted; approval makes nothing then
		request = self._ask([{"kind": "Tool", "item_code": self.tool, "qty": 1}])
		review = self._review()
		self.assertEqual([row.kind for row in review.items if row.request == request], ["Tool"])
		review.submit()
		frappe.db.set_value("Item", self.tool, "is_stock_item", 0)
		before = frappe.db.count("Material Request")
		with self.assertRaises(frappe.ValidationError) as refused:
			materials.approve_review(review.name)
		self.assertIn(self.tool, str(refused.exception))
		self.assertEqual(frappe.db.count("Material Request"), before)
		self.assertEqual(
			frappe.db.get_value("Equipment Needs Review", review.name, "approval_status"), "Pending"
		)

	def test_custody_refuses_a_non_stock_item(self):
		rag = self._item("RAG", stock=0)
		with self.assertRaises(frappe.ValidationError) as refused:
			# refused when saved, not only later by the Stock Entry
			self._custody("Handover", warehouse=self.store, item_code=rag, submit=False)
		self.assertIn(rag, str(refused.exception))

	def _other_company(self):
		name = f"V4-OTHER-CO-{self.token}"
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "O" + self.token[:5].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _other_warehouse(self, company):
		# made directly: the new company has no inventory account for a Warehouse insert
		warehouse = frappe.new_doc("Warehouse")
		warehouse.update({"warehouse_name": f"V4 far {self.token}", "company": company})
		warehouse.name = f"V4 far {self.token} - {frappe.db.get_value('Company', company, 'abbr')}"
		warehouse.db_insert()
		return warehouse.name

	def test_custody_stays_in_the_employees_company(self):
		# #113 G6: no custody movement links a record of another company
		other = self._other_company()
		foreign = {
			"to_employee": frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": f"V4 far {self.token}",
					"gender": "Male",
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2020-01-01",
					"company": other,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name,
			"warehouse": self._other_warehouse(other),
			"project": frappe.get_doc(
				{"doctype": "Project", "project_name": f"V4 far {self.token}", "company": other}
			)
			.insert(ignore_permissions=True)
			.name,
			"card_equipment": frappe.get_doc(
				{
					"doctype": "Card Equipment",
					"company": other,
					"equipment_name": f"V4-FAR-{self.token}",
					"equipment_type": self._m["etype"],
					"ownership": "ملك",
					"daily_hours": 10,
				}
			)
			.insert(ignore_permissions=True)
			.name,
		}
		self._custody("Handover", qty=2, warehouse=self.store)
		cases = {
			"to_employee": ("Transfer", {}),
			"warehouse": ("Handover", {}),
			"project": ("Loss", {}),
			"card_equipment": ("Handover", {"warehouse": self.store}),
		}
		for field, (movement, extra) in cases.items():
			with self.subTest(field=field):
				with self.assertRaises(frappe.ValidationError) as refused:
					self._custody(movement, submit=False, **extra, **{field: foreign[field]})
				self.assertIn(foreign[field], str(refused.exception))
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 2)
		# the shared custody store too, for every movement that moves stock
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", foreign["warehouse"])
		with self.assertRaises(frappe.ValidationError) as refused:
			self._custody("Return", warehouse=self.store, submit=False)
		self.assertIn(foreign["warehouse"], str(refused.exception))
		_u, colleague = self._operator("mate")
		self._custody("Transfer", to_employee=colleague)  # no stock move: the store does not matter

	def test_a_held_tool_can_still_be_transferred_after_its_item_changed(self):
		self._custody("Handover", warehouse=self.store)
		frappe.db.set_value("Item", self.tool, "is_stock_item", 0)
		_u, colleague = self._operator("mate")
		self._custody("Transfer", to_employee=colleague)
		self.assertEqual(materials.custody_balance(colleague, self.tool), 1)

	def test_cancelling_a_handover_cancels_its_stock_entry(self):
		hand = self._custody("Handover", warehouse=self.store)
		hand.cancel()
		# ERPNext refuses to cancel an entry a submitted custody record links: the record does it
		self.assertEqual(frappe.db.get_value("Stock Entry", hand.stock_entry, "docstatus"), 2)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 0)

	def test_cancelling_a_loss_removes_its_draft_stock_entry(self):
		self._custody("Handover", warehouse=self.store)
		loss = self._custody("Loss", project=self.project)
		entry = loss.stock_entry
		loss.cancel()
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
		self._custody("Handover", warehouse=self.store)
		loss = self._custody("Loss", project=self.project)
		frappe.db.set_value("Employee Tool Custody", loss.name, "stock_entry", other.name)
		loss.reload()
		loss.cancel()
		self.assertTrue(frappe.db.exists("Stock Entry", other.name))

	# ---------- handover confirmation (#113 PR-T2) ----------
	def _approved_tool(self, qty=1, route="From store"):
		"""An approved review with one tool line; returns (review, line, draft)."""
		request = self._ask([{"kind": "Tool", "item_code": self.tool, "qty": qty}])
		review = self._review()
		for row in review.items:
			if row.request == request:
				row.route, row.approved_qty = route, qty
			else:
				row.approved_qty = 0
		review.save()
		review.submit()
		materials.approve_review(review.name)
		line = next(
			row
			for row in frappe.get_doc("Equipment Needs Review", review.name).items
			if row.request == request
		)
		return review, line, frappe.get_doc("Employee Tool Custody", line.tool_custody)

	def _confirm(self, draft, user, **values):
		"""Confirm as `user`; on any error the work is rolled back as a web request would."""
		frappe.db.savepoint("card_confirm")
		frappe.set_user(user)
		try:
			doc = frappe.get_doc("Employee Tool Custody", draft.name)
			doc.update({"handover_receipt": self._receipt(user), **values})
			doc.submit()
			return doc
		except Exception:
			frappe.db.rollback(save_point="card_confirm")
			raise
		finally:
			frappe.set_user("Administrator")

	def _store_keeper(self, prefix="store", roles=("Stock Manager",)):
		return self._user(prefix, list(roles))

	def _entries(self, custody):
		return frappe.get_all(
			"Stock Entry", filters={"remarks": f"CARD tool custody {custody}"}, pluck="docstatus"
		)

	def test_approval_makes_a_handover_draft_and_moves_nothing(self):
		review, line, draft = self._approved_tool()
		self.assertEqual(
			(draft.docstatus, draft.handover_status, draft.employee, draft.qty, draft.warehouse),
			(0, "Awaiting handover", self.operator, 1, self.store),
		)
		self.assertEqual(
			(draft.review, draft.review_item, draft.project, draft.card_equipment),
			(review.name, line.name, self.project, self.eq),
		)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 0)
		self.assertEqual(self._entries(draft.name), [])
		self.assertEqual(
			frappe.db.get_value("Equipment Needs Review", review.name, "approval_status"), "Approved"
		)

	def test_the_store_side_confirms_with_one_submitted_stock_entry(self):
		_review, line, draft = self._approved_tool(qty=2)
		self._stock_in(2)
		keeper = self._store_keeper()
		stale = frappe.get_doc("Employee Tool Custody", draft.name)  # a second form still open
		doc = self._confirm(draft, keeper)
		entry = frappe.get_doc("Stock Entry", doc.stock_entry)
		self.assertEqual((entry.docstatus, entry.purpose), (1, "Material Transfer"))
		self.assertEqual((entry.items[0].s_warehouse, entry.items[0].t_warehouse), (self.store, self.custody))
		doc.reload()
		self.assertEqual((doc.handover_status, doc.handed_by), ("Handed over", keeper))
		self.assertTrue(doc.handed_on)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 2)
		self.assertEqual(frappe.db.get_value("Equipment Needs Review Item", line.name, "handed_qty"), 2)
		frappe.set_user(keeper)
		try:
			stale.handover_receipt = self._receipt(keeper)
			with self.assertRaises(frappe.ValidationError):  # a second confirmation of the same record
				stale.submit()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(self._entries(draft.name), [1])
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 2)

	def test_a_supervisor_prepares_but_cannot_confirm_without_stock_rights(self):
		# Owner H-5: drafts as today; the final confirmation needs custody and Stock Entry rights
		supervisor = self._user("sup", ["Card Supervisor"])
		self._stock_in(1)
		frappe.set_user(supervisor)
		draft = frappe.get_doc(
			{
				"doctype": "Employee Tool Custody",
				"employee": self.operator,
				"movement": "Handover",
				"item_code": self.tool,
				"qty": 1,
				"date": nowdate(),
				"warehouse": self.store,
			}
		).insert()
		draft.notes = "prepared by the supervisor"
		draft.save()
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.PermissionError):
			self._confirm(draft, supervisor)
		self.assertEqual(
			(
				frappe.db.get_value("Employee Tool Custody", draft.name, "docstatus"),
				self._entries(draft.name),
			),
			(0, []),
		)
		with_stock = self._user("supstock", ["Card Supervisor", "Stock User"])
		self._confirm(draft, with_stock)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 1)

	def test_separation_of_duties_on_confirmation(self):
		# Owner H-6: the worker, the requester, who entered it for the worker and the approver never confirm
		supervisor = self._user("onbehalf", ["Card Supervisor", "Stock Manager"])
		_review, line, draft = self._approved_tool()  # approved by Administrator
		request = frappe.get_doc("Equipment Needs Request", line.request)
		frappe.db.set_value("Equipment Needs Request", request.name, "entered_by", supervisor)
		self._stock_in(1)
		frappe.get_doc("User", self.op_user).add_roles("Stock Manager")  # the worker, with stock rights
		for user in (self.op_user, supervisor, "Administrator"):
			with self.subTest(user=user), self.assertRaises(frappe.PermissionError):
				self._confirm(draft, user)
		card_user = self._user("cu", ["Card User"])
		with self.assertRaises(frappe.PermissionError):
			self._confirm(draft, card_user)
		self.assertEqual(
			(
				frappe.db.get_value("Employee Tool Custody", draft.name, "docstatus"),
				self._entries(draft.name),
			),
			(0, []),
		)
		self._confirm(draft, self._store_keeper())
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 1)

	def test_a_partial_handover_keeps_the_rest_waiting(self):
		_review, line, draft = self._approved_tool(qty=3)
		self._stock_in(1)
		keeper = self._store_keeper()
		with self.assertRaises(frappe.ValidationError):  # more than approved
			self._confirm(draft, keeper, qty=4)
		self._confirm(draft, keeper, qty=1)
		row = frappe.db.get_value(
			"Equipment Needs Review Item", line.name, ["handed_qty", "tool_custody"], as_dict=True
		)
		self.assertEqual(row.handed_qty, 1)
		rest = frappe.get_doc("Employee Tool Custody", row.tool_custody)
		self.assertEqual((rest.docstatus, rest.qty, rest.handover_status), (0, 2, "Awaiting handover"))
		self._stock_in(2)
		with self.assertRaises(frappe.ValidationError):  # the remaining balance, not the approved qty
			self._confirm(rest, keeper, qty=3)
		self._confirm(rest, keeper)
		self.assertEqual(frappe.db.get_value("Equipment Needs Review Item", line.name, "handed_qty"), 3)
		self.assertEqual(
			frappe.db.count("Employee Tool Custody", {"review_item": line.name, "docstatus": 0}), 0
		)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 3)

	def test_a_store_without_stock_rolls_the_confirmation_back(self):
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
		_review, line, draft = self._approved_tool()
		with self.assertRaises(frappe.ValidationError):
			self._confirm(draft, self._store_keeper())
		self.assertEqual(frappe.db.get_value("Employee Tool Custody", draft.name, "docstatus"), 0)
		self.assertEqual(self._entries(draft.name), [])
		self.assertEqual(frappe.db.get_value("Equipment Needs Review Item", line.name, "handed_qty"), 0)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 0)

	def test_a_bought_tool_waits_for_its_purchase_receipt(self):
		frappe.db.set_single_value("Stock Settings", "allow_negative_stock", 0)
		_review, _line, draft = self._approved_tool(route="Buy for project")
		mr = frappe.db.get_value("Equipment Needs Review Item", _line.name, "material_request")
		self.assertEqual(frappe.db.get_value("Material Request", mr, "material_request_type"), "Purchase")
		keeper = self._store_keeper()
		with self.assertRaises(frappe.ValidationError):
			self._confirm(draft, keeper)
		self._stock_in(1)  # stands for the Purchase Receipt into the store
		self._confirm(draft, keeper)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 1)

	def test_a_failed_handover_is_closed_and_replaced_by_a_card_manager(self):
		_review, line, draft = self._approved_tool()
		keeper = self._store_keeper()
		frappe.set_user(keeper)
		try:
			with self.assertRaises(frappe.ValidationError):
				materials.close_tool_handover(draft.name, " ")
			materials.close_tool_handover(draft.name, "the worker refused a damaged tool")
			with self.assertRaises(frappe.PermissionError):  # Owner H-2
				materials.make_tool_handover(line.name)
		finally:
			frappe.set_user("Administrator")
		closed = frappe.get_doc("Employee Tool Custody", draft.name)
		self.assertEqual((closed.docstatus, closed.handover_status), (0, "Not handed over"))
		self.assertEqual(closed.not_handed_reason, "the worker refused a damaged tool")
		closed.notes = "changed"
		with self.assertRaises(frappe.ValidationError):
			closed.save()
		self._stock_in(1)
		with self.assertRaises(frappe.ValidationError):
			self._confirm(draft, keeper)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 0)
		manager = self._user("mgr", ["Card Manager"])
		frappe.set_user(manager)
		try:
			new = materials.make_tool_handover(line.name)
			with self.assertRaises(frappe.ValidationError):  # one waiting draft at a time
				materials.make_tool_handover(line.name)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Employee Tool Custody", new, ["qty", "handover_status"]),
			(1, "Awaiting handover"),
		)
		self._confirm(frappe.get_doc("Employee Tool Custody", new), keeper)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 1)

	def test_handover_server_fields_cannot_be_set_by_hand(self):
		_review, line, draft = self._approved_tool()
		forged = frappe.get_doc(
			{
				"doctype": "Employee Tool Custody",
				"employee": self.operator,
				"movement": "Handover",
				"item_code": self.tool,
				"qty": 1,
				"date": nowdate(),
				"warehouse": self.store,
				"review": draft.review,
				"review_item": line.name,
				"handover_status": "Handed over",
				"handed_by": "Administrator",
			}
		).insert()
		self.assertEqual(
			(forged.review, forged.review_item, forged.handed_by, forged.handover_status),
			(None, None, None, "Awaiting handover"),
		)
		draft.reload()
		draft.qty = 0.5  # lowering the quantity is allowed
		draft.save()
		for field, value in (("employee", self._operator("other")[1]), ("warehouse", self.custody)):
			doc = frappe.get_doc("Employee Tool Custody", draft.name)
			doc.set(field, value)
			with self.subTest(field=field), self.assertRaises(frappe.ValidationError):
				doc.save()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Employee Tool Custody", draft.name)

	def test_a_cancelled_handover_goes_back_on_its_line(self):
		_review, line, draft = self._approved_tool()
		self._stock_in(1)
		doc = self._confirm(draft, self._store_keeper())
		frappe.set_user(self._store_keeper("undo"))
		try:
			frappe.get_doc("Employee Tool Custody", doc.name).cancel()
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Stock Entry", doc.stock_entry, "docstatus"), 2)
		self.assertEqual(frappe.db.get_value("Equipment Needs Review Item", line.name, "handed_qty"), 0)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 0)
		amended = frappe.copy_doc(frappe.get_doc("Employee Tool Custody", doc.name))
		amended.amended_from = doc.name
		with self.assertRaises(frappe.ValidationError):  # replaced by a Card Manager, never amended
			amended.insert()

	def test_return_and_transfer_are_confirmed_with_evidence(self):
		self._custody("Handover", qty=3, warehouse=self.store)
		keeper = self._store_keeper()

		def give_back(user):
			frappe.set_user(user)
			try:
				doc = frappe.get_doc(
					{
						"doctype": "Employee Tool Custody",
						"employee": self.operator,
						"movement": "Return",
						"item_code": self.tool,
						"qty": 1,
						"date": nowdate(),
						"warehouse": self.store,
					}
				).insert()
				doc.submit()
				return doc
			finally:
				frappe.set_user("Administrator")

		ret = give_back(keeper)
		self.assertEqual(frappe.db.get_value("Stock Entry", ret.stock_entry, "docstatus"), 1)
		self.assertEqual(frappe.db.get_value("Employee Tool Custody", ret.name, "handed_by"), keeper)
		_u, colleague = self._operator("mate")
		with self.assertRaises(frappe.ValidationError):  # Owner H-3: no silent transfer
			self._custody("Transfer", to_employee=colleague, handover_receipt=None)
		self._custody("Transfer", to_employee=colleague)
		self.assertEqual(materials.custody_balance(colleague, self.tool), 1)
		frappe.get_doc("User", self.op_user).add_roles("Stock Manager")
		with self.assertRaises(frappe.PermissionError):  # the worker never confirms his own return
			give_back(self.op_user)
		self.assertEqual(materials.custody_balance(self.operator, self.tool), 1)

	def test_the_receipt_is_a_private_file_of_this_record(self):
		public = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"public-{self.token}.pdf",
				"is_private": 0,
				"content": b"%PDF public",
			}
		).insert()
		other = self._custody("Handover", warehouse=self.store)
		for url in (public.file_url, other.handover_receipt):
			with self.subTest(url=url), self.assertRaises(frappe.ValidationError):
				self._custody("Handover", warehouse=self.store, handover_receipt=url, submit=False)

	def test_a_user_of_another_company_cannot_confirm(self):
		_review, _line, draft = self._approved_tool()
		self._stock_in(1)
		outsider = self._store_keeper("far")
		other = self._other_company()
		frappe.get_doc(
			{"doctype": "User Permission", "user": outsider, "allow": "Company", "for_value": other}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			self._confirm(draft, outsider)
		self.assertEqual(frappe.db.get_value("Employee Tool Custody", draft.name, "docstatus"), 0)

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
