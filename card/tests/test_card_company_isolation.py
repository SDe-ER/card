# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""P0 company isolation of Card Monthly Card (Owner 2026-10-20, defect D2 of
QA-Evidence 2026-10-20-card-p0-tests, probe S9). Frappe checks create/write
permission on the values the client sends (frappe/model/document.py insert: 478
check_permission before 480 _validate_links; _save: 585 before 594), and only then
fetch_from fills `company` from the equipment. A user restricted to company A who
leaves `company` empty therefore passes the check and the card is stored in the
equipment's company B. The D2 proofs below fail on main d52ae45; the guards keep the
authorised paths working (own company, unrestricted users, Card Manager, Administrator).
No role is widened; the second company row is inserted raw; everything is rolled back."""

import frappe
from frappe.client import get as rest_get
from frappe.client import insert as rest_insert
from frappe.client import save as rest_save
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase

from card.tests.test_controllers import _ensure_masters
from card.tests.test_transfer import _past_month_year

DOCTYPE = "Card Monthly Card"
REFUSED = (frappe.PermissionError, frappe.ValidationError)


class TestCardCompanyIsolation(IntegrationTestCase):
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
		self.proj_a = self._project("A", self.company)
		self.proj_b = self._project("B", self.other)
		self.eq_a = self._equipment("A", self.company)
		self.eq_b = self._equipment("B", self.other)
		self._assign(self.eq_a, self.proj_a)
		self._assign(self.eq_b, self.proj_b)
		self.card_a = self._card(self.eq_a, self.proj_a)
		self.card_b = self._card(self.eq_b, self.proj_b)

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
		name = "TEST-CRDISO-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "K" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _project(self, suffix, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-CRDISO-PRJ-%s-%s" % (suffix, self.token)
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _equipment(self, suffix, company):
		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-CRDISO-EQ-%s-%s" % (suffix, self.token)
		eq.ownership = "ملك"  # owned: no supplier needed
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		return eq.name

	def _assign(self, equipment, project):
		a = frappe.new_doc("Card Equipment Assignment")
		a.equipment = equipment
		a.project = project
		a.from_date = self._d(1)
		a.insert(ignore_permissions=True)
		return a.name

	def _card_doc(self, equipment, project, shift="نهاري", **extra):
		doc = {
			"doctype": DOCTYPE,
			"equipment": equipment,
			"project": project,
			"shift": shift,
			"month": self.month_str,
			"year": int(self.year_str),
			"days": [{"operation_date": self._d(5), "day_status": "عمل", "working_hours": 8}],
		}
		doc.update(extra)
		return doc

	def _card(self, equipment, project, shift="نهاري"):
		return frappe.get_doc(self._card_doc(equipment, project, shift)).insert(ignore_permissions=True).name

	def _user(self, roles, restrict=None):
		email = f"crdiso-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Card Isolation",
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

	def _stored(self, card, field):
		frappe.set_user("Administrator")
		return frappe.db.get_value(DOCTYPE, card, field)

	# ---------- D2 proofs (fail on main d52ae45) ----------

	def test_create_with_empty_company_for_other_company_equipment_refused(self):
		"""S9: company left empty -> fetched from the B equipment after the permission check."""
		for role in ("Card User", "Card Manager"):
			with self.subTest(role=role):
				frappe.set_user("Administrator")
				eq_b2 = self._equipment("B-" + role[5:], self.other)
				self._assign(eq_b2, self.proj_b)
				self._as([role], restrict=self.company)
				self.assertTrue(self._refused(rest_insert, self._card_doc(eq_b2, self.proj_b)))
				frappe.set_user("Administrator")
				self.assertEqual(frappe.db.count(DOCTYPE, {"equipment": eq_b2}), 0)

	def test_own_card_cannot_be_moved_to_other_company_equipment(self):
		"""Save path: own draft card re-pointed to B equipment with company emptied."""
		self._as(["Card User"], restrict=self.company)
		doc = frappe.get_doc(DOCTYPE, self.card_a).as_dict()
		doc.update({"equipment": self.eq_b, "project": self.proj_b, "company": "", "shift": "ليلي"})
		self.assertTrue(self._refused(rest_save, doc))
		self.assertEqual(self._stored(self.card_a, "company"), self.company)
		self.assertEqual(self._stored(self.card_a, "equipment"), self.eq_a)

	def test_other_company_card_cannot_be_taken_over(self):
		"""Save path: B's draft card re-pointed to A equipment by a user of A."""
		frappe.set_user("Administrator")
		doc = frappe.get_doc(DOCTYPE, self.card_b).as_dict()
		self._as(["Card User"], restrict=self.company)
		doc.update({"equipment": self.eq_a, "project": self.proj_a, "company": "", "shift": "ليلي"})
		self.assertTrue(self._refused(rest_save, doc))
		self.assertEqual(self._stored(self.card_b, "company"), self.other)
		self.assertEqual(self._stored(self.card_b, "equipment"), self.eq_b)

	def test_set_value_cannot_move_card_to_other_company(self):
		self._as(["Card User"], restrict=self.company)
		self.assertTrue(
			self._refused(
				rest_set_value,
				DOCTYPE,
				self.card_a,
				{"equipment": self.eq_b, "project": self.proj_b, "company": "", "shift": "ليلي"},
			)
		)
		self.assertEqual(self._stored(self.card_a, "company"), self.company)

	def test_takeover_payload_denied_for_submit_and_cancel(self):
		"""The hook decides on the stored company for every action, not only save."""
		from card.card.doctype.card_monthly_card.card_monthly_card import has_card_permission

		self.assertIn(
			"card.card.doctype.card_monthly_card.card_monthly_card.has_card_permission",
			frappe.get_hooks("has_permission").get(DOCTYPE, []),
		)
		payload = frappe.get_doc(DOCTYPE, self.card_b).as_dict()
		payload.update({"equipment": self.eq_a, "project": self.proj_a, "company": ""})
		user = self._user(["Card Manager"], restrict=self.company)
		for ptype in ("read", "write", "submit", "cancel"):
			with self.subTest(ptype=ptype):
				self.assertFalse(has_card_permission(frappe.get_doc(payload), ptype, user))
				self.assertTrue(has_card_permission(frappe.get_doc(DOCTYPE, self.card_a), ptype, user))

	# ---------- guards (pass before and after the fix) ----------

	def test_other_company_card_read_refused(self):
		self._as(["Card User"], restrict=self.company)
		self.assertEqual(rest_get(DOCTYPE, self.card_a)["name"], self.card_a)
		self.assertTrue(self._refused(rest_get, DOCTYPE, self.card_b))

	def test_other_company_typed_explicitly_refused(self):
		self._as(["Card User"], restrict=self.company)
		self.assertTrue(
			self._refused(rest_insert, self._card_doc(self.eq_b, self.proj_b, "ليلي", company=self.other))
		)

	def test_other_company_card_edit_refused(self):
		frappe.set_user("Administrator")
		doc = frappe.get_doc(DOCTYPE, self.card_b).as_dict()
		self._as(["Card User"], restrict=self.company)
		doc["days"][0]["working_hours"] = 9
		self.assertTrue(self._refused(rest_save, doc))

	def test_own_company_card_create_and_edit_allowed(self):
		self._as(["Card User"], restrict=self.company)
		name = rest_insert(self._card_doc(self.eq_a, self.proj_a, "ليلي"))["name"]
		self.assertEqual(self._stored(name, "company"), self.company)
		self._as(["Card User"], restrict=self.company)
		doc = frappe.get_doc(DOCTYPE, self.card_a).as_dict()
		doc["days"][0]["working_hours"] = 9
		rest_save(doc)
		self.assertEqual(
			frappe.db.get_value("Card Monthly Card Day", {"parent": self.card_a}, "working_hours"), 9
		)

	def test_unrestricted_users_keep_every_company(self):
		for role in ("Card User", "Card Manager"):
			with self.subTest(role=role):
				frappe.set_user("Administrator")
				frappe.db.delete(DOCTYPE, {"equipment": self.eq_b, "shift": "ليلي"})
				self._as([role])
				name = rest_insert(self._card_doc(self.eq_b, self.proj_b, "ليلي"))["name"]
				self.assertEqual(self._stored(name, "company"), self.other)

	def test_administrator_unaffected(self):
		frappe.set_user("Administrator")
		name = rest_insert(self._card_doc(self.eq_b, self.proj_b, "ليلي"))["name"]
		self.assertEqual(frappe.db.get_value(DOCTYPE, name, "company"), self.other)
