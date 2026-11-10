# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-133 (R-14, #50, owner O-19 default-on): a company-restricted user reads the per-company rows of
Card Settings (``company_settings``, ``diesel_price_schedule``) of his permitted companies only, on
every read path (Desk form, REST v1/v2, frappe.client, the child row on its own, the child list), and
a save by him keeps the stored rows of the other companies. System Manager and users without a
Company User Permission read every row; server code reading the Single is not filtered."""

import json

import frappe
import frappe.model.document
from frappe.tests import IntegrationTestCase

from card.card.doctype.card_settings import card_settings as scope
from card.card.doctype.card_settings.card_settings import settings_company_scope
from card.tests.test_controllers import _ensure_masters

SETTINGS = {"parent": "Card Settings", "parenttype": "Card Settings"}


class TestSettingsCompanyScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=6)
		self.a = self._m["company"]
		self.b = self._company("B")
		self.c = self._company("C")
		for company in (self.a, self.b, self.c):
			self._row(company)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.stored = self._stored()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.response = frappe._dict(docs=[])
		frappe.db.rollback()
		frappe.clear_document_cache("Card Settings", "Card Settings")

	# ---------- fixtures (Administrator, rolled back) ----------

	def _company(self, tag):
		name = f"TEST-SCS-{tag}-{self.token}"
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": tag + self.token[:5].upper(),
				"default_currency": frappe.db.get_value("Company", self.a, "default_currency"),
				"country": frappe.db.get_value("Company", self.a, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _row(self, company):
		"""One company row and one diesel price row per company, written on their own."""
		if not frappe.db.exists("Card Company Settings", {**SETTINGS, "company": company}):
			frappe.get_doc(
				{
					"doctype": "Card Company Settings",
					**SETTINGS,
					"parentfield": "company_settings",
					"idx": 100 + frappe.db.count("Card Company Settings", SETTINGS),
					"company": company,
				}
			).db_insert()
		frappe.get_doc(
			{
				"doctype": "Card Diesel Price",
				**SETTINGS,
				"parentfield": "diesel_price_schedule",
				"idx": 100 + frappe.db.count("Card Diesel Price", SETTINGS),
				"company": company,
				"valid_from": "2020-01-0%d" % (1 + frappe.db.count("Card Diesel Price", SETTINGS) % 9),
				"unit_price": 2,
				"currency": frappe.db.get_value("Company", company, "default_currency"),
			}
		).db_insert()

	def _user(self, *companies, roles=("Accounts Manager",)):
		email = f"scs-{frappe.generate_hash(length=8)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Settings Scope",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		for company in companies:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": company,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		return email

	def _stored(self):
		"""Every stored scoped row as (table, name) -> values, read without permissions."""
		rows = {}
		for doctype, field in (
			("Card Company Settings", "company_settings"),
			("Card Diesel Price", "diesel_price_schedule"),
		):
			for r in frappe.get_all(doctype, filters={**SETTINGS, "parentfield": field}, fields=["*"]):
				rows[(field, r.name)] = {
					k: v for k, v in r.items() if k not in ("modified", "modified_by", "idx")
				}
		return rows

	def _row_name(self, doctype, company):
		return frappe.db.get_value(doctype, {**SETTINGS, "company": company}, "name")

	def _companies(self, doc, table):
		return {r.get("company") for r in doc.get(table) or []}

	def _getdoc(self):
		from frappe.desk.form.load import getdoc

		frappe.local.response = frappe._dict(docs=[])
		getdoc("Card Settings", "Card Settings")
		return frappe.response.docs[0]

	def _all(self):
		return {self.a, self.b, self.c}

	def _card_only_user(self, company):
		"""A Company User Permission limited to CARD documents (Frappe applies none to Card
		Settings itself)."""
		user = self._user()
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": company,
				"apply_to_all_doctypes": 0,
				"applicable_for": "Card Monthly Card",
			}
		).insert(ignore_permissions=True)
		return user

	def _adjustment_row(self, company):
		frappe.get_doc(
			{
				"doctype": "Card Adjustment Type",
				**SETTINGS,
				"parentfield": "adjustment_types",
				"idx": 100 + frappe.db.count("Card Adjustment Type", SETTINGS),
				"company": company,
				"type_name": "TEST-SCS-ADJ-" + self.token,
				"kind": "خصم",
				"account": "TEST-SCS-ACC-" + self.token,
			}
		).db_insert()

	def _other_names(self):
		"""Every name and company of the rows of B and C (what must never reach an A user)."""
		values = set()
		for (_table, name), row in self.stored.items():
			if row["company"] != self.a:
				values.update({name, row["company"]})
		return values

	def _leaks(self, payload):
		text = json.dumps(payload, default=str)
		return sorted(v for v in self._other_names() if v in text)

	# ---------- reads ----------

	def test_desk_form_shows_only_permitted_rows(self):
		frappe.set_user(self._user(self.a))
		doc = self._getdoc()
		self.assertEqual(self._companies(doc, "company_settings"), {self.a})
		self.assertEqual(self._companies(doc, "diesel_price_schedule"), {self.a})
		self.assertEqual([r.idx for r in doc.company_settings], list(range(1, len(doc.company_settings) + 1)))
		self.assertTrue(doc.get_onload().get("card_hidden_company_rows"))

	def test_rest_reads_of_the_settings_hide_other_companies(self):
		import frappe.api.v1
		import frappe.api.v2
		import frappe.client

		frappe.set_user(self._user(self.a))
		for read in (
			lambda: frappe.api.v1.read_doc("Card Settings", "Card Settings"),
			lambda: frappe.api.v2.read_doc("Card Settings", "Card Settings"),
			lambda: frappe.client.get("Card Settings"),
		):
			doc = read()
			doc = doc.as_dict() if isinstance(doc, frappe.model.document.Document) else doc
			self.assertEqual(self._companies(doc, "company_settings"), {self.a})
			self.assertEqual(self._companies(doc, "diesel_price_schedule"), {self.a})
			frappe.clear_document_cache("Card Settings", "Card Settings")

	def test_child_row_rest_read_of_another_company_is_refused(self):
		import frappe.api.v1
		import frappe.client

		frappe.set_user(self._user(self.a))
		for doctype in ("Card Company Settings", "Card Diesel Price"):
			other = self._row_name(doctype, self.b)
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get(doctype, other)
			with self.assertRaises(frappe.PermissionError):
				frappe.api.v1.read_doc(doctype, other)
		# with the user permission limited to CARD documents, Frappe applies none to Card Settings:
		# the row check of CARD still refuses the other company's row and allows his own
		user = self._user()
		frappe.set_user("Administrator")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": self.a,
				"apply_to_all_doctypes": 0,
				"applicable_for": "Card Monthly Card",
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		for doctype in ("Card Company Settings", "Card Diesel Price"):
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get(doctype, self._row_name(doctype, self.b))
			# a row on its own is checked against the whole stored Single (has_settings_permission):
			# while another company has a row, the user reads his rows through Card Settings
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get(doctype, self._row_name(doctype, self.a))
		self.assertEqual(self._companies(frappe.client.get("Card Settings"), "company_settings"), {self.a})

	def test_child_list_and_value_reads_refused_with_a_card_only_permission(self):
		"""Card-only Company User Permission: list, value and report-view reads of the child tables
		are refused (has_settings_permission), also the company-filter oracle."""
		import frappe.client
		import frappe.desk.reportview

		frappe.set_user(self._card_only_user(self.a))
		for doctype in scope.SCOPED_CHILD_DOCTYPES:
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get_list(doctype, fields=["company"], parent="Card Settings")
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get_value(
					doctype, "company", filters={"company": self.b}, parent="Card Settings"
				)
			frappe.local.form_dict = frappe._dict(
				doctype=doctype,
				fields=json.dumps([f"`tab{doctype}`.`name`"]),
				filters=json.dumps([[doctype, "company", "=", self.b]]),
				parent_doctype="Card Settings",
			)
			with self.assertRaises(frappe.PermissionError):
				frappe.desk.reportview.get()
		frappe.local.form_dict = frappe._dict()

	def test_child_list_condition_is_escaped_and_scoped(self):
		"""The second-layer list condition on its own (Frappe 16 does not apply it to a Single's
		child table): own companies only, values escaped, no condition for unrestricted users."""
		odd = self._company("Q'X")
		self._row(odd)
		user = self._user(self.a, odd)
		for doctype in ("Card Company Settings", "Card Diesel Price"):
			condition = scope.settings_row_query_conditions(user, doctype=doctype)
			companies = set(
				frappe.db.sql_list(
					f"select company from `tab{doctype}` where parenttype='Card Settings' and {condition}"
				)
			)
			self.assertEqual(companies, {self.a, odd})
		self.assertEqual(scope.settings_row_query_conditions(self._user(), doctype="Card Diesel Price"), "")
		self.assertEqual(scope.settings_row_query_conditions(user, doctype="Card Monthly Card"), "")

	def test_child_list_rest_read_is_refused_to_a_restricted_user(self):
		"""A Company User Permission for every doctype: Frappe checks the parent Single with all its
		rows, so the child list is refused."""
		import frappe.client

		frappe.set_user(self._user(self.a))
		for doctype in ("Card Company Settings", "Card Diesel Price"):
			with self.assertRaises(frappe.PermissionError):
				frappe.client.get_list(doctype, fields=["company"], parent="Card Settings")

	# ---------- saves ----------

	def test_save_from_the_form_keeps_hidden_rows(self):
		from frappe.desk.form.save import savedocs

		frappe.set_user(self._user(self.a))
		doc = self._getdoc().as_dict()
		cost_center = frappe.db.get_value("Cost Center", {"company": self.a, "is_group": 0}, "name")
		for row in doc["company_settings"]:
			row["cost_center"] = cost_center
		frappe.local.response = frappe._dict(docs=[])
		savedocs(json.dumps(doc, default=str), "Save")
		reply = frappe.response.docs[0]
		self.assertEqual(self._companies(reply, "company_settings"), {self.a})
		frappe.set_user("Administrator")
		after = self._stored()
		self.assertEqual(set(after), set(self.stored))
		for key, values in self.stored.items():
			if values["company"] != self.a:
				self.assertEqual(after[key], values)
		self.assertEqual(
			frappe.db.get_value("Card Company Settings", {**SETTINGS, "company": self.a}, "cost_center"),
			cost_center,
		)

	def test_client_save_keeps_hidden_rows_and_replies_without_them(self):
		import frappe.client

		frappe.set_user(self._user(self.a))
		doc = frappe.client.get("Card Settings")
		reply = frappe.client.save(doc)
		self.assertEqual(self._companies(reply, "company_settings"), {self.a})
		self.assertEqual(self._companies(reply, "diesel_price_schedule"), {self.a})
		frappe.set_user("Administrator")
		self.assertEqual(set(self._stored()), set(self.stored))

	def test_hidden_row_sent_back_changed_is_refused(self):
		import frappe.client

		frappe.set_user(self._user(self.a))
		doc = frappe.client.get("Card Settings")
		name = self._row_name("Card Diesel Price", self.b)
		doc["diesel_price_schedule"].append(
			{"name": name, "company": self.b, "valid_from": "2020-02-01", "unit_price": 9}
		)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.save(doc)

	def test_a_new_row_for_another_company_is_refused(self):
		import frappe.client

		frappe.set_user(self._user(self.a))
		doc = frappe.client.get("Card Settings")
		doc["diesel_price_schedule"].append({"company": self.b, "valid_from": "2020-03-01", "unit_price": 3})
		with self.assertRaises(frappe.PermissionError):
			frappe.client.save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(set(self._stored()), set(self.stored))

	def test_save_reply_keeps_the_hidden_rows_note(self):
		from frappe.desk.form.save import savedocs

		frappe.set_user(self._user(self.a))
		doc = self._getdoc().as_dict()
		frappe.local.response = frappe._dict(docs=[])
		savedocs(json.dumps(doc, default=str), "Save")
		self.assertTrue(frappe.response.docs[0]["__onload"].get("card_hidden_company_rows"))

	def test_site_wide_fields_cannot_be_changed(self):
		import frappe.client

		frappe.set_user(self._user(self.a))
		warehouse = frappe.db.get_value("Warehouse", {"is_group": 0}, "name")
		for field, value in (("repeat_request_days", 7), ("default_store_warehouse", warehouse)):
			doc = frappe.client.get("Card Settings")
			doc[field] = value
			with self.assertRaises(frappe.PermissionError):
				frappe.client.save(doc)
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value("Card Settings", "Card Settings", "tool_custody_warehouse", warehouse)
		frappe.set_user("Administrator")
		self.assertEqual(set(self._stored()), set(self.stored))

	def test_set_value_on_child_rows(self):
		import frappe.client

		frappe.set_user(self._user(self.a))
		with self.assertRaises(frappe.PermissionError):
			frappe.client.set_value(
				"Card Diesel Price", self._row_name("Card Diesel Price", self.b), "unit_price", 9
			)
		reply = frappe.client.set_value(
			"Card Diesel Price", self._row_name("Card Diesel Price", self.a), "unit_price", 5
		)
		self.assertEqual(self._leaks(reply), [])
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value(
				"Card Diesel Price", self._row_name("Card Diesel Price", self.a), "unit_price"
			),
			5,
		)
		for key, values in self.stored.items():
			if values["company"] != self.a:
				self.assertEqual(self._stored()[key], values)

	def test_own_row_moved_to_another_company_is_refused(self):
		import frappe.client

		frappe.set_user(self._user(self.a))
		doc = frappe.client.get("Card Settings")
		for row in doc["diesel_price_schedule"]:
			row["company"] = self.b
		with self.assertRaises(frappe.PermissionError):
			frappe.client.save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(set(self._stored()), set(self.stored))
		self.assertEqual(
			frappe.db.get_value("Card Diesel Price", self._row_name("Card Diesel Price", self.a), "company"),
			self.a,
		)

	def test_reordering_own_rows_keeps_hidden_rows_in_place(self):
		import frappe.client

		self._row(self.a)  # a second A price row, after B and C
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.stored = self._stored()
		order = lambda: frappe.get_all(  # noqa: E731
			"Card Diesel Price",
			filters={**SETTINGS, "parentfield": "diesel_price_schedule"},
			fields=["name", "company"],
			order_by="idx asc",
		)
		hidden_positions = {r.name: i for i, r in enumerate(order()) if r.company != self.a}
		frappe.set_user(self._user(self.a))
		doc = frappe.client.get("Card Settings")
		doc["diesel_price_schedule"].reverse()
		for idx, row in enumerate(doc["diesel_price_schedule"], 1):
			row["idx"] = idx
		frappe.client.save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(set(self._stored()), set(self.stored))
		self.assertEqual({r.name: i for i, r in enumerate(order()) if r.company != self.a}, hidden_positions)

	def test_adjustment_type_of_another_company_is_hidden_not_locking(self):
		import frappe.client

		self._adjustment_row(self.b)
		frappe.set_user(self._user(self.a))
		doc = self._getdoc()
		self.assertNotIn(self.b, self._companies(doc, "adjustment_types"))
		frappe.client.save(frappe.client.get("Card Settings"))
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Card Adjustment Type", {**SETTINGS, "company": self.b}))
		with self.assertRaises(frappe.PermissionError):
			frappe.set_user(self._user(self.a))
			frappe.client.get(
				"Card Adjustment Type",
				frappe.db.get_value("Card Adjustment Type", {**SETTINGS, "company": self.b}),
			)

	def test_hidden_rows_are_not_validated_or_named(self):
		"""An unchanged hidden row that would fail a rule (wrong currency) does not block, and is not
		named to, the restricted user; his own company's FR-125 duplicate date is still refused."""
		import frappe.client

		frappe.db.set_value(
			"Card Diesel Price", self._row_name("Card Diesel Price", self.b), "currency", "TEST-SCS-CUR"
		)
		frappe.set_user(self._user(self.a))
		frappe.client.save(frappe.client.get("Card Settings"))
		doc = frappe.client.get("Card Settings")
		own = doc["diesel_price_schedule"][0]
		doc["diesel_price_schedule"].append(
			{"company": self.a, "valid_from": own["valid_from"], "unit_price": 4}
		)
		frappe.clear_messages()
		with self.assertRaises(frappe.ValidationError) as caught:
			frappe.client.save(doc)
		self.assertEqual(
			self._leaks(str(caught.exception) + json.dumps(frappe.local.message_log, default=str)), []
		)

	# ---------- history ----------

	def _history(self):
		"""Versions with changes to rows of A, B and C, made by Administrator."""
		settings = frappe.get_doc("Card Settings")
		for row in settings.diesel_price_schedule:
			if row.company in self._all():
				row.unit_price = 3
		settings.save(ignore_version=False)
		settings = frappe.get_doc("Card Settings")
		settings.diesel_price_schedule = [r for r in settings.diesel_price_schedule if r.company != self.c]
		settings.save(ignore_version=False)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.stored = self._stored()

	def test_timeline_versions_carry_no_other_company_row(self):
		from frappe.desk.form.save import savedocs

		removed_c = {
			r["name"]
			for (t, _n), r in self.stored.items()
			if t == "diesel_price_schedule" and r["company"] == self.c
		}
		self._history()
		frappe.set_user(self._user(self.a))
		frappe.local.response = frappe._dict(docs=[])
		scope.getdoc("Card Settings", "Card Settings")
		versions = frappe.response.docinfo["versions"]
		self.assertTrue(versions)
		self.assertEqual(self._leaks(versions), [])
		self.assertFalse([n for n in removed_c if n in json.dumps(versions, default=str)])
		self.assertTrue(any(self._row_name("Card Diesel Price", self.a) in v["data"] for v in versions))
		frappe.local.response = frappe._dict(docs=[])
		scope.get_docinfo(doctype="Card Settings", name="Card Settings")
		self.assertEqual(self._leaks(frappe.response.docinfo["versions"]), [])
		frappe.local.response = frappe._dict(docs=[])
		scope.getdoc("Card Settings", "Card Settings")
		doc = frappe.response.docs[0].as_dict()
		frappe.local.response = frappe._dict(docs=[])
		savedocs(json.dumps(doc, default=str), "Save")
		self.assertEqual(self._leaks(frappe.response.docinfo["versions"]), [])

	def test_timeline_is_complete_for_an_unrestricted_user(self):
		self._history()
		frappe.set_user(self._user())
		frappe.local.response = frappe._dict(docs=[])
		scope.getdoc("Card Settings", "Card Settings")
		text = json.dumps(frappe.response.docinfo["versions"], default=str)
		self.assertIn(self._row_name("Card Diesel Price", self.b), text)

	def test_a_user_with_two_companies(self):
		import frappe.client

		frappe.set_user(self._user(self.a, self.b))
		doc = self._getdoc()
		self.assertEqual(self._companies(doc, "company_settings"), {self.a, self.b})
		self.assertEqual(self._companies(doc, "diesel_price_schedule"), {self.a, self.b})
		frappe.clear_document_cache("Card Settings", "Card Settings")
		frappe.client.save(frappe.client.get("Card Settings"))
		frappe.set_user("Administrator")
		self.assertEqual(set(self._stored()), set(self.stored))

	# ---------- users who read everything ----------

	def test_system_manager_sees_every_row(self):
		"""CARD never hides a row from System Manager (a Company User Permission on him stays
		Frappe's own rule)."""
		restricted = self._user(self.a, roles=("System Manager", "Accounts Manager"))
		self.assertIsNone(settings_company_scope(restricted))
		frappe.set_user(self._user(roles=("System Manager",)))
		doc = self._getdoc()
		self.assertTrue(self._all() <= self._companies(doc, "company_settings"))
		self.assertTrue(self._all() <= self._companies(doc, "diesel_price_schedule"))
		self.assertFalse(doc.get_onload().get("card_hidden_company_rows"))

	def test_unrestricted_user_sees_every_row(self):
		import frappe.client

		frappe.set_user(self._user())
		doc = frappe.client.get("Card Settings")
		self.assertTrue(self._all() <= self._companies(doc, "company_settings"))
		self.assertTrue(self._all() <= self._companies(doc, "diesel_price_schedule"))
		row = frappe.client.get("Card Diesel Price", self._row_name("Card Diesel Price", self.c))
		self.assertEqual(row["company"], self.c)

	def test_server_code_reads_every_row(self):
		frappe.set_user(self._user(self.a))
		settings = frappe.get_doc("Card Settings")
		self.assertTrue(self._all() <= self._companies(settings, "company_settings"))
