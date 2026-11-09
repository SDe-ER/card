# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""P0 company isolation of Equipment Transport (Owner 2026-10-20, defect D3 of
QA-Evidence 2026-10-20-card-p0-tests, probe S14). A transport checks that each machine
belongs to the transport's company, but never checks the destination project's company:
a company-A transport can point company-A equipment at a company-B project (its cost
center is then taken from the company-B project). Frappe also checks write permission
on the values the client sends, so a user of company A can take over a company-B draft
transport by sending company A. The D3 proofs below fail on main e7ee3e9; the guards keep
the authorised paths working. No role is widened; everything is rolled back."""

import frappe
from frappe.client import get as rest_get
from frappe.client import insert as rest_insert
from frappe.client import save as rest_save
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase

from card.tests.test_controllers import _ensure_masters
from card.tests.test_transfer import _past_month_year
from card.tests.transport_parties import company_paid_values

DOCTYPE = "Equipment Transport"
REFUSED = (frappe.PermissionError, frappe.ValidationError)


class TestTransportCompanyIsolation(IntegrationTestCase):
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
		self.trn_a = self._transport(self.company, self.proj_a, self.eq_a)
		self.trn_b = self._transport(self.other, self.proj_b, self.eq_b)

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
		name = "TEST-TRNISO-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "T" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _supplier(self):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-TRNISO-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _project(self, suffix, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-TRNISO-PRJ-%s-%s" % (suffix, self.token)
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, suffix, company):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-TRNISO-EQ-%s-%s" % (suffix, self.token)
		eq.ownership = "ملك"  # owned: no equipment supplier needed
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _transport_doc(self, company, project, *equipment):
		return {
			"doctype": DOCTYPE,
			"date": self._d(3),
			"company": company,
			"project": project,
			"transport_supplier": self.sup,
			"amount": 100,
			"items": [{"card_equipment": eq} for eq in equipment],
			# the other test company has no cost center: its moves are recorded as not charged
			**(company_paid_values(company) if company == self.company else {"payer": "No charge"}),
		}

	def _transport(self, company, project, *equipment):
		return (
			frappe.get_doc(self._transport_doc(company, project, *equipment))
			.insert(ignore_permissions=True)
			.name
		)

	def _user(self, roles, restrict=None):
		email = f"trniso-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Transport Isolation",
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

	def _as(self, roles, **kw):
		frappe.set_user(self._user(roles, **kw))

	def _refused(self, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
		except REFUSED:
			return True
		finally:
			frappe.clear_messages()
		return False

	def _stored(self, name, field):
		frappe.set_user("Administrator")
		return frappe.db.get_value(DOCTYPE, name, field)

	# ---------- D3 proofs (fail on main e7ee3e9) ----------

	def test_destination_project_of_other_company_refused(self):
		"""S14: a company-A transport moving company-A equipment onto a company-B project."""
		for who in ("Administrator", "Card Manager", "Card User restricted to A"):
			with self.subTest(who=who):
				frappe.set_user("Administrator")
				eq = self._equipment("P-" + who[:6], self.company)
				if who == "Card Manager":
					self._as(["Card Manager"])
				elif who != "Administrator":
					self._as(["Card User"], restrict=self.company)
				self.assertTrue(
					self._refused(rest_insert, self._transport_doc(self.company, self.proj_b, eq))
				)
				frappe.set_user("Administrator")
				self.assertFalse(
					frappe.db.exists(
						"Equipment Transport Item", {"card_equipment": eq, "parenttype": DOCTYPE}
					)
				)

	def test_set_value_cannot_point_transport_to_other_company_project(self):
		self._as(["Card User"], restrict=self.company)
		self.assertTrue(self._refused(rest_set_value, DOCTYPE, self.trn_a, "project", self.proj_b))
		self.assertEqual(self._stored(self.trn_a, "project"), self.proj_a)

	def test_other_company_transport_cannot_be_taken_over(self):
		"""Save path: B's draft transport re-pointed to company A by a user of A."""
		frappe.set_user("Administrator")
		eq_a2 = self._equipment("A2", self.company)
		doc = frappe.get_doc(DOCTYPE, self.trn_b).as_dict()
		self._as(["Card User"], restrict=self.company)
		doc.update({"company": self.company, "project": self.proj_a, "items": [{"card_equipment": eq_a2}]})
		self.assertTrue(self._refused(rest_save, doc))
		self.assertEqual(self._stored(self.trn_b, "company"), self.other)
		self.assertEqual(self._stored(self.trn_b, "project"), self.proj_b)

	def test_other_company_project_cost_center_never_used(self):
		"""A company-A transport must not take a company-B project's cost center."""
		frappe.set_user("Administrator")
		cc_b = frappe.db.get_value("Project", self.proj_b, "cost_center")
		eq = self._equipment("CC", self.company)
		try:
			name = rest_insert(self._transport_doc(self.company, self.proj_b, eq))["name"]
		except REFUSED:
			frappe.clear_messages()
			return  # refused: nothing stored
		cc = frappe.db.get_value(DOCTYPE, name, "cost_center")
		self.fail(
			f"saved {name} for company A with project of B (cost center {cc}, project B cost center {cc_b})"
		)

	def test_hook_decides_on_stored_company_for_every_action(self):
		"""The hook uses the stored company for read, write, submit and cancel."""
		from card.card.doctype.equipment_transport.equipment_transport import has_transport_permission

		self.assertIn(
			"card.card.doctype.equipment_transport.equipment_transport.has_transport_permission",
			frappe.get_hooks("has_permission").get(DOCTYPE, []),
		)
		payload = frappe.get_doc(DOCTYPE, self.trn_b).as_dict()
		payload.update({"company": self.company, "project": self.proj_a})
		user = self._user(["Card Manager"], restrict=self.company)
		for ptype in ("read", "write", "submit", "cancel"):
			with self.subTest(ptype=ptype):
				self.assertFalse(has_transport_permission(frappe.get_doc(payload), ptype, user))
				self.assertTrue(has_transport_permission(frappe.get_doc(DOCTYPE, self.trn_a), ptype, user))

	def test_empty_company_with_other_company_machines_refused(self):
		"""No company sent: the machines' company decides before validate defaults one."""
		frappe.set_user("Administrator")
		eq_b5 = self._equipment("B5", self.other)
		user = self._user(["Card User"], restrict=self.company)
		from card.card.doctype.equipment_transport.equipment_transport import has_transport_permission

		for doc in (self._transport_doc("", self.proj_a, eq_b5), self._transport_doc("", self.proj_b)):
			with self.subTest(doc=doc["items"]):
				self.assertFalse(has_transport_permission(frappe.get_doc(doc), "create", user))
		self.assertTrue(
			has_transport_permission(frappe.get_doc(self._transport_doc("", self.proj_a)), "create", user)
		)
		frappe.set_user(user)
		self.assertTrue(self._refused(rest_insert, self._transport_doc("", self.proj_b, eq_b5)))

	# ---------- guards (pass before and after the fix) ----------

	def test_other_company_transport_read_refused(self):
		self._as(["Card User"], restrict=self.company)
		self.assertEqual(rest_get(DOCTYPE, self.trn_a)["name"], self.trn_a)
		self.assertTrue(self._refused(rest_get, DOCTYPE, self.trn_b))

	def test_other_company_typed_explicitly_refused(self):
		frappe.set_user("Administrator")
		eq_b2 = self._equipment("B2", self.other)
		self._as(["Card User"], restrict=self.company)
		self.assertTrue(self._refused(rest_insert, self._transport_doc(self.other, self.proj_b, eq_b2)))

	def test_other_company_equipment_row_refused(self):
		frappe.set_user("Administrator")
		eq_b3 = self._equipment("B3", self.other)
		self._as(["Card User"], restrict=self.company)
		self.assertTrue(self._refused(rest_insert, self._transport_doc(self.company, self.proj_a, eq_b3)))

	def test_own_company_transport_allowed(self):
		frappe.set_user("Administrator")
		eq_a3 = self._equipment("A3", self.company)
		self._as(["Card User"], restrict=self.company)
		name = rest_insert(self._transport_doc(self.company, self.proj_a2, eq_a3))["name"]
		self.assertEqual(self._stored(name, "project"), self.proj_a2)
		self._as(["Card User"], restrict=self.company)
		rest_set_value(DOCTYPE, self.trn_a, "project", self.proj_a2)
		self.assertEqual(self._stored(self.trn_a, "project"), self.proj_a2)

	def test_unrestricted_users_keep_every_company(self):
		for role in ("Card User", "Card Manager"):
			with self.subTest(role=role):
				frappe.set_user("Administrator")
				eq_b4 = self._equipment("B4" + role[5:], self.other)
				self._as([role])
				name = rest_insert(self._transport_doc(self.other, self.proj_b, eq_b4))["name"]
				self.assertEqual(self._stored(name, "company"), self.other)
