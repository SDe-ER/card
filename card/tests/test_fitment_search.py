# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Catalog phase 2b (FR-078): the fit of an Item for one machine in the catalog search, the
read-only catalog of a Card User, and the Q10 reason on request lines (Owner decisions A-D,
2026-10-23). Real users with their real rights; the data is rolled back."""

import json

import frappe

from card import catalog, fitment, materials, mobile
from card.fitment import CONFIRMED, NOT_COMPATIBLE
from card.tests.test_fitment import PART, FitmentTestCase

FIT_KEYS = {"fit", "fit_model"}
PHASE1_KEYS = {
	"item_code",
	"item_name",
	"stock_uom",
	"image",
	"item_group",
	"item_group_label",
	"brand",
	"oem",
	"alternatives",
}


class FitmentSearchCase(FitmentTestCase):
	def _decided(self, status, item, machine=None, notes=None):
		"""A Supervisor's proposal decided by a Card Manager (the normal two-person path)."""
		values = {"item_code": item}
		if machine:
			values.update({"applies_to": "Equipment", "card_equipment": machine})
		row = self._row(self.supervisor, **values)
		extra = {"technical_notes": notes} if notes else {}
		return self._decide(self.manager, row.name, status, **extra)

	def _call(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _restrict(self, user, company):
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": company,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)

	def _other_company(self):
		name = "TEST-FIT2B-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "G" + self.token[:5].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _operator(self, machine):
		user = self._user("opr", ["Card Operator"])
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"Fit2b {self.token}",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": "Active",
				"user_id": user,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Card Equipment", machine, {"operator_on": "الشركة", "operator": emp.name}, update_modified=False
		)
		return user


class TestEffectiveFit(FitmentSearchCase):
	def test_four_states_stay_apart_and_the_machine_row_wins(self):
		items = {key: self._item(key) for key in "ABCDEFGHI"}
		# A: no row
		self._row(self.supervisor, item_code=items["B"])  # B: pending
		own = self._row(self.manager, item_code=items["C"])  # C: first review only
		self._decide(
			self.manager, own.name, CONFIRMED, decision_reason="seen", evidence_file=self._evidence_file()
		)
		self._decided(CONFIRMED, items["D"])  # D: model Confirmed
		self._decided(CONFIRMED, items["E"], machine=self.machine)  # E: machine Confirmed
		self._decided(CONFIRMED, items["F"])
		self._decided(NOT_COMPATIBLE, items["F"], machine=self.machine)  # F: machine NC wins
		self._decided(NOT_COMPATIBLE, items["G"])
		self._decided(CONFIRMED, items["G"], machine=self.machine, notes="long bolt")  # G: machine C wins
		retired = self._decided(CONFIRMED, items["H"])  # H: retired
		frappe.set_user(self.manager)
		doc = frappe.get_doc(PART, retired.name)
		doc.update({"is_active": 0, "retire_reason": "superseded"})
		doc.save()
		frappe.set_user("Administrator")
		self._decided(CONFIRMED, items["I"])
		self._row(self.supervisor, item_code=items["I"], applies_to="Equipment", card_equipment=self.machine)

		fits = fitment.effective_fit(self.machine, list(items.values()))
		model_name = frappe.db.get_value("Card Equipment Model", self.model, "model_name")
		expected = {
			"A": ("unknown", None),
			"B": ("pending", None),
			"C": ("pending", None),
			"D": ("confirmed_model", model_name),
			"E": ("confirmed_machine", None),
			"F": ("not_compatible", None),
			"G": ("confirmed_machine", None),
			"H": ("unknown", None),
			"I": ("confirmed_model", model_name),  # a pending machine row is no decision
		}
		for key, (fit, model) in expected.items():
			self.assertEqual(fits[items[key]], {"fit": fit, "fit_model": model}, key)
		self.assertEqual(
			fitment.compatible_items(self.machine), sorted(items[k] for k in "DEGI"), "compatible list"
		)

	def test_machine_without_a_model_uses_its_own_rows_only(self):
		self._decided(CONFIRMED, self.item)
		bare = self._machine()
		self.assertEqual(fitment.effective_fit(bare, [self.item])[self.item]["fit"], "unknown")
		self.assertEqual(fitment.compatible_items(bare), [])


class TestCatalogFitSearch(FitmentSearchCase):
	def setUp(self):
		super().setUp()
		self.items = [self._item(f"S{i}") for i in range(4)]
		for code in self.items[:3]:
			self._decided(CONFIRMED, code)
		self._decided(NOT_COMPATIBLE, self.items[3])

	def test_search_without_a_machine_keeps_the_phase1_answer(self):
		page = self._call(self.manager, catalog.search, txt=self.token)
		self.assertTrue(page["items"])
		for item in page["items"]:
			self.assertEqual(set(item), PHASE1_KEYS)

	def test_search_with_a_machine_adds_only_the_fit(self):
		page = self._call(self.card_user, catalog.search, txt=self.token, equipment=self.machine)
		by_code = {item["item_code"]: item for item in page["items"]}
		self.assertEqual(by_code[self.items[0]]["fit"], "confirmed_model")
		self.assertEqual(by_code[self.items[3]]["fit"], "not_compatible")  # shown, with a warning
		self.assertEqual(by_code[self.item]["fit"], "unknown")
		for item in page["items"]:
			self.assertEqual(set(item), PHASE1_KEYS | FIT_KEYS)  # no evidence, reason or reviewer

	def test_fits_lists_only_confirmed_items_and_pages(self):
		first = self._call(
			self.card_user, catalog.search, txt=self.token, equipment=self.machine, fits=1, page_length=2
		)
		second = self._call(
			self.card_user,
			catalog.search,
			txt=self.token,
			equipment=self.machine,
			fits=1,
			start=2,
			page_length=2,
		)
		codes = [i["item_code"] for i in first["items"] + second["items"]]
		self.assertEqual(sorted(codes), sorted(self.items[:3]))
		self.assertTrue(first["has_more"])
		self.assertFalse(second["has_more"])
		self.assertNotIn(self.items[3], codes)  # Not Compatible is never in the compatible list

	def test_fits_for_a_machine_without_fit_data_is_empty(self):
		bare = self._machine()
		page = self._call(self.manager, catalog.search, txt=self.token, equipment=bare, fits=1)
		self.assertEqual(page, {"items": [], "has_more": False})

	def test_fit_for_gives_the_same_answer_and_nothing_else(self):
		answer = self._call(self.card_user, fitment.fit_for, self.machine, json.dumps(self.items))
		self.assertEqual(answer, fitment.effective_fit(self.machine, self.items))
		for value in answer.values():
			self.assertEqual(set(value), FIT_KEYS)
		with self.assertRaises(frappe.ValidationError):
			self._call(self.card_user, fitment.fit_for, self.machine, json.dumps(["X"] * 51))
		# an Item outside the caller's catalog gets no answer at all
		disabled = self._item("OFF", disabled=1)
		self.assertEqual(
			self._call(self.card_user, fitment.fit_for, self.machine, json.dumps([disabled])), {}
		)

	def test_endpoints_are_get_only(self):
		for fn in (fitment.fit_for, fitment.machines, catalog.search):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[fn], ["GET"])

	def test_search_never_changes_fitment_rows(self):
		before = frappe.get_all(PART, fields=["name", "modified", "compatibility_status"], order_by="name")
		self._call(self.card_user, catalog.search, txt=self.token, equipment=self.machine)
		self._call(self.card_user, fitment.fit_for, self.machine, json.dumps(self.items))
		after = frappe.get_all(PART, fields=["name", "modified", "compatibility_status"], order_by="name")
		self.assertEqual(before, after)


class TestFitAccess(FitmentSearchCase):
	def test_card_user_of_another_company_cannot_use_the_machine(self):
		other = self._other_company()
		self._restrict(self.card_user, other)
		for fn, args in (
			(catalog.search, {"equipment": self.machine}),
			(fitment.fit_for, {"equipment": self.machine, "items": json.dumps([self.item])}),
		):
			with self.assertRaises(frappe.PermissionError):
				self._call(self.card_user, fn, **args)
		names = [m["name"] for m in self._call(self.card_user, fitment.machines)["machines"]]
		self.assertNotIn(self.machine, names)

	def test_operator_uses_only_his_own_machines(self):
		operator = self._operator(self.machine)
		other = self._machine()
		self.assertTrue(self._call(operator, fitment.fit_for, self.machine, json.dumps([self.item])))
		with self.assertRaises(frappe.PermissionError):
			self._call(operator, fitment.fit_for, other, json.dumps([self.item]))
		names = [m["name"] for m in self._call(operator, fitment.machines)["machines"]]
		self.assertEqual(names, [self.machine])

	def test_users_without_a_catalog_role_are_refused(self):
		outsider = self._user("out", [])
		for fn, args in (
			(catalog.search, {"equipment": self.machine}),
			(fitment.fit_for, {"equipment": self.machine, "items": "[]"}),
			(fitment.machines, {}),
		):
			with self.assertRaises(frappe.PermissionError):
				self._call(outsider, fn, **args)

	def test_card_user_is_a_catalog_viewer_without_requests(self):
		self.assertTrue(self._call(self.card_user, mobile.has_app_permission))  # no Employee needed
		ctx = self._call(self.card_user, mobile.get_session_context)
		self.assertTrue(ctx["catalog_only"])
		self.assertIsNone(ctx["employee"])
		self.assertFalse(self._call(self.supervisor, mobile.get_session_context)["catalog_only"])
		for fn, args in (
			(materials.get_portal_context, {}),
			(materials.search_items, {"txt": "fit"}),
			(materials.submit_needs, {"equipment": self.machine, "items": "[]"}),
		):
			with self.assertRaises(frappe.PermissionError):
				self._call(self.card_user, fn, **args)
		self.assertFalse(frappe.has_permission(PART, "read", user=self.card_user))


class TestRequestFitReason(FitmentSearchCase):
	def setUp(self):
		super().setUp()
		masters = self._m
		frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": self.machine,
				"project": masters["project"],
				"from_date": "2026-01-01",
			}
		).insert(ignore_permissions=True)
		self.operator = self._operator(self.machine)
		self.confirmed = self._item("OK")
		self._decided(CONFIRMED, self.confirmed)
		self.wrong = self._item("NC")
		self._decided(NOT_COMPATIBLE, self.wrong)
		self.pending = self._item("PEND")
		self._row(self.supervisor, item_code=self.pending)

	def _ask(self, **line):
		row = {"kind": "Part", "qty": 1, **line}
		return self._call(self.operator, materials.submit_needs, self.machine, json.dumps([row]))

	def test_confirmed_item_needs_no_reason(self):
		doc = frappe.get_doc("Equipment Needs Request", self._ask(item_code=self.confirmed))
		self.assertEqual(doc.items[0].fit_status, "Confirmed for model")

	def test_items_without_a_confirmed_fit_need_the_reason(self):
		for code, status in (
			(self.wrong, "Not compatible"),
			(self.pending, "Pending review"),
			(self.item, "No fitment record"),
		):
			with self.assertRaises(frappe.ValidationError, msg=code):
				self._ask(item_code=code)
			doc = frappe.get_doc(
				"Equipment Needs Request", self._ask(item_code=code, fit_reason="asked by mechanic")
			)
			self.assertEqual(
				(doc.items[0].fit_status, doc.items[0].fit_reason), (status, "asked by mechanic")
			)

	def test_free_text_line_needs_no_fit_reason(self):
		doc = frappe.get_doc("Equipment Needs Request", self._ask(description="unknown lamp"))
		self.assertIsNone(doc.items[0].fit_status)

	def test_request_and_review_never_change_fitment_rows(self):
		before = frappe.get_all(PART, fields=["name", "modified", "compatibility_status"], order_by="name")
		versions = frappe.db.count("Version", {"ref_doctype": PART})
		self._ask(item_code=self.wrong, fit_reason="only one in store")
		review = frappe.get_doc({"doctype": "Equipment Needs Review", "project": self._m["project"]}).insert(
			ignore_permissions=True
		)
		materials.pull_requests(review.name)
		line = next(
			i
			for i in frappe.get_doc("Equipment Needs Review", review.name).items
			if i.item_code == self.wrong
		)
		self.assertEqual((line.fit_status, line.fit_reason), ("Not compatible", "only one in store"))
		after = frappe.get_all(PART, fields=["name", "modified", "compatibility_status"], order_by="name")
		self.assertEqual(before, after)
		self.assertEqual(frappe.db.count("Version", {"ref_doctype": PART}), versions)
