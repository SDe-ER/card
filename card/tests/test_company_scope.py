# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-131: the generic company scope of card.company_scope and its hooks.

The planned DocTypes do not exist yet, so the functions are exercised on two existing DocTypes:
Project Diesel Fill (a Company ``company`` field plus Project and Card Equipment links) and Card Equipment
Assignment (no company field; Card Equipment and Project links). Company B and its records are inserted raw (no
validation; only the stored company matters to a permission check); no role is widened; everything is rolled
back."""

import json
import pathlib
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card import company_scope
from card.company_scope import (
	company_query_conditions,
	deny_cross_company_share,
	document_companies,
	has_company_permission,
)
from card.tests.test_controllers import _ensure_masters

FILL = "Project Diesel Fill"
ASSIGNMENT = "Card Equipment Assignment"
REPO = pathlib.Path(__file__).resolve().parents[2]


def _repo_doctypes():
	out = {}
	for path in (REPO / "card" / "card" / "doctype").glob("*/*.json"):
		if path.stem == path.parent.name:
			meta = json.loads(path.read_text())
			if meta.get("doctype") == "DocType":
				out[meta["name"]] = meta
	return out


class TestCompanyScopeHooks(IntegrationTestCase):
	"""The registration: every planned DocType, the exact functions, inert while a DocType is absent."""

	def test_hooks_list_matches_the_module(self):
		from card import hooks

		self.assertEqual(tuple(hooks._COMPANY_SCOPED), company_scope.SCOPED_DOCTYPES)
		self.assertEqual(len(set(company_scope.SCOPED_DOCTYPES)), 9)

	def test_every_planned_doctype_is_registered(self):
		has_perm = frappe.get_hooks("has_permission")
		query = frappe.get_hooks("permission_query_conditions")
		for doctype in company_scope.SCOPED_DOCTYPES:
			with self.subTest(doctype=doctype):
				self.assertEqual(has_perm.get(doctype), [company_scope.HAS_PERMISSION])
				self.assertEqual(query.get(doctype), [company_scope.QUERY_CONDITIONS])

	def test_registered_functions_resolve(self):
		for path in (
			company_scope.HAS_PERMISSION,
			company_scope.QUERY_CONDITIONS,
			"card.company_scope.deny_cross_company_share",
		):
			with self.subTest(path=path):
				self.assertTrue(callable(frappe.get_attr(path)))
		self.assertIn(
			"card.company_scope.deny_cross_company_share",
			frappe.get_hooks("doc_events")["DocShare"]["validate"],
		)

	def test_existing_hooks_are_unchanged(self):
		"""No DocType that already has its own hook is moved to the generic functions."""
		from card import hooks

		for doctype, method in {**hooks.has_permission, **hooks.permission_query_conditions}.items():
			if doctype not in company_scope.SCOPED_DOCTYPES:
				with self.subTest(doctype=doctype):
					self.assertFalse(method.startswith("card.company_scope."))

	def test_hooks_of_absent_doctypes_are_inert(self):
		absent = "Card Scope Absent " + frappe.generate_hash(length=6)
		self.assertFalse(frappe.db.exists("DocType", absent))
		self.assertEqual(company_query_conditions(user="Administrator", doctype=absent), "")
		self.assertEqual(company_query_conditions(user="Guest", doctype=absent), "")
		self.assertEqual(company_query_conditions(user="Guest", doctype=None), "")
		# a share of a DocType that is not in the scope list (or not installed) is not checked here
		deny_cross_company_share(frappe._dict(share_doctype=absent, everyone=1, user=None))

	def test_present_planned_doctypes_carry_a_company(self):
		"""A planned DocType, once its package adds it, has a Company ``company`` field or a link to a company
		source; otherwise the generic scope would not isolate it."""
		doctypes = _repo_doctypes()
		for doctype in company_scope.SCOPED_DOCTYPES:
			meta = doctypes.get(doctype)
			if not meta:
				continue  # not merged yet: its hooks are inert
			with self.subTest(doctype=doctype):
				self.assertFalse(meta.get("istable") or meta.get("issingle"))
				links = {
					(f["fieldname"], f.get("options"))
					for f in meta.get("fields") or []
					if f.get("fieldtype") == "Link"
				}
				self.assertTrue(
					("company", "Company") in links
					or any(target in company_scope.COMPANY_SOURCES for _field, target in links)
				)


class TestCompanyScope(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.A = self._m["company"]
		self.B = self._company("TEST-SCOPE-CO-" + self.token)
		self.proj_a = self._raw(
			"Project", "TEST-SCOPE-PA-" + self.token, project_name="PA" + self.token, company=self.A
		)
		self.proj_b = self._raw(
			"Project", "TEST-SCOPE-PB-" + self.token, project_name="PB" + self.token, company=self.B
		)
		self.eq_a = self._raw("Card Equipment", "TEST-SCOPE-EA-" + self.token, company=self.A)
		self.eq_b = self._raw("Card Equipment", "TEST-SCOPE-EB-" + self.token, company=self.B)
		self.fill_a = self._raw(FILL, "TEST-SCOPE-FA-" + self.token, company=self.A, project=self.proj_a)
		self.fill_b = self._raw(FILL, "TEST-SCOPE-FB-" + self.token, company=self.B, project=self.proj_b)
		self.asg_a = self._raw(
			ASSIGNMENT, "TEST-SCOPE-AA-" + self.token, equipment=self.eq_a, project=self.proj_a
		)
		self.asg_b = self._raw(
			ASSIGNMENT, "TEST-SCOPE-AB-" + self.token, equipment=self.eq_b, project=self.proj_b
		)
		self.user = self._user(restrict=self.A)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders ----------
	def _company(self, name):
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "S" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.A, "default_currency"),
				"country": frappe.db.get_value("Company", self.A, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _raw(self, doctype, name, **values):
		doc = frappe.new_doc(doctype)
		doc.update(values)
		doc.name = name
		doc.db_insert()  # no validation: only the stored values matter here
		return name

	def _user(self, restrict=None, roles=("Card User",)):
		email = f"scope-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Company Scope",
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

	def _allowed(self, doc, user=None):
		return has_company_permission(doc, "read", user=user or self.user)

	def _visible(self, doctype, names, user=None):
		condition = company_query_conditions(user=user or self.user, doctype=doctype)
		where = f" and {condition}" if condition else ""
		rows = frappe.db.sql(
			f"select name from `tab{doctype}` where name in %(names)s{where}", {"names": names}, pluck=True
		)
		return set(rows)

	# ---------- company field (Project Diesel Fill) ----------
	def test_company_field_same_company_allowed_other_denied(self):
		self.assertTrue(self._allowed(frappe.get_doc(FILL, self.fill_a)))
		self.assertFalse(self._allowed(frappe.get_doc(FILL, self.fill_b)))

	def test_company_field_create(self):
		self.assertTrue(self._allowed(frappe.new_doc(FILL, company=self.A)))
		self.assertFalse(self._allowed(frappe.new_doc(FILL, company=self.B)))
		# a source link of company B on a company-A record is refused too
		self.assertFalse(self._allowed(frappe.new_doc(FILL, company=self.A, project=self.proj_b)))
		self.assertFalse(self._allowed(frappe.new_doc(FILL, company=self.A, card_equipment=self.eq_b)))
		# nothing chosen yet: no objection (the mandatory fields stop the save)
		self.assertTrue(self._allowed(frappe.new_doc(FILL)))

	def test_company_field_takeover_and_move_denied(self):
		doc = frappe.get_doc(FILL, self.fill_b)
		doc.company = self.A  # take over by sending the user's own company
		self.assertFalse(self._allowed(doc))
		doc = frappe.get_doc(FILL, self.fill_a)
		doc.company = self.B  # move to the other company
		self.assertFalse(self._allowed(doc))
		doc = frappe.get_doc(FILL, self.fill_a)
		doc.project = self.proj_b  # re-point a link to the other company
		self.assertFalse(self._allowed(doc))

	def test_company_field_unchanged_link_not_reread(self):
		doc = frappe.get_doc(FILL, self.fill_a)
		self.assertEqual(document_companies(doc), {self.A})

	def test_company_field_list(self):
		names = (self.fill_a, self.fill_b)
		self.assertEqual(self._visible(FILL, names), {self.fill_a})
		self.assertEqual(self._visible(FILL, names, user="Administrator"), set(names))
		self.assertEqual(self._visible(FILL, names, user=self._user()), set(names))

	def test_company_field_list_through_get_list(self):
		"""Frappe applies the condition when it is registered for the DocType (patched registration)."""
		real = frappe.get_hooks

		def get_hooks(hook=None, default=None, app_name=None):
			result = real(hook, default, app_name)
			if hook == "permission_query_conditions":
				result = dict(result or {})
				result[FILL] = [*result.get(FILL, []), company_scope.QUERY_CONDITIONS]
			return result

		frappe.set_user(self.user)
		with patch.object(frappe, "get_hooks", side_effect=get_hooks):
			names = frappe.get_list(
				FILL,
				filters={"name": ["in", [self.fill_a, self.fill_b]]},
				pluck="name",
				ignore_permissions=False,
			)
		self.assertEqual(set(names), {self.fill_a})

	# ---------- no company field (Card Equipment Assignment) ----------
	def test_link_only_saved_record(self):
		self.assertTrue(self._allowed(frappe.get_doc(ASSIGNMENT, self.asg_a)))
		self.assertFalse(self._allowed(frappe.get_doc(ASSIGNMENT, self.asg_b)))

	def test_link_only_create_move_and_takeover(self):
		self.assertTrue(self._allowed(frappe.new_doc(ASSIGNMENT, equipment=self.eq_a, project=self.proj_a)))
		self.assertFalse(self._allowed(frappe.new_doc(ASSIGNMENT, equipment=self.eq_b, project=self.proj_a)))
		self.assertFalse(self._allowed(frappe.new_doc(ASSIGNMENT, equipment=self.eq_a, project=self.proj_b)))
		doc = frappe.get_doc(ASSIGNMENT, self.asg_a)
		doc.equipment = self.eq_b
		self.assertFalse(self._allowed(doc))
		doc = frappe.get_doc(ASSIGNMENT, self.asg_b)
		doc.equipment, doc.project = self.eq_a, self.proj_a  # take over: the stored links still count
		self.assertFalse(self._allowed(doc))

	def test_link_only_list(self):
		names = (self.asg_a, self.asg_b)
		self.assertEqual(self._visible(ASSIGNMENT, names), {self.asg_a})
		self.assertEqual(self._visible(ASSIGNMENT, names, user="Administrator"), set(names))

	def test_unrestricted_user_not_affected(self):
		user = self._user()
		for doc in (frappe.get_doc(FILL, self.fill_b), frappe.get_doc(ASSIGNMENT, self.asg_b)):
			with self.subTest(doctype=doc.doctype):
				self.assertTrue(self._allowed(doc, user=user))
				self.assertTrue(self._allowed(doc, user="Administrator"))

	def test_user_limited_to_unknown_company_sees_nothing(self):
		"""A restriction whose companies are all absent leaves no permitted company: the list is empty."""
		with patch("card.party_registry._restricted_companies", return_value=[]):
			self.assertEqual(company_query_conditions(user=self.user, doctype=FILL), "1=0")
			self.assertFalse(
				has_company_permission(frappe.get_doc(FILL, self.fill_a), "read", user=self.user)
			)

	def test_unscoped_doctype_gets_no_condition(self):
		"""A DocType without a company field or source link is not scoped (the guard test above refuses such a
		planned DocType)."""
		self.assertFalse(company_scope.is_scoped("ToDo"))
		self.assertEqual(company_query_conditions(user=self.user, doctype="ToDo"), "")

	# ---------- DocShare ----------
	def _share(self, doctype, name, user=None, everyone=0):
		return frappe._dict(share_doctype=doctype, share_name=name, user=user, everyone=everyone)

	def test_share_guard(self):
		with patch.object(company_scope, "SCOPED_DOCTYPES", (ASSIGNMENT, FILL)):
			for doctype, own, other in (
				(ASSIGNMENT, self.asg_a, self.asg_b),
				(FILL, self.fill_a, self.fill_b),
			):
				with self.subTest(doctype=doctype):
					deny_cross_company_share(self._share(doctype, own, user=self.user))
					deny_cross_company_share(self._share(doctype, other, user=self._user()))
					with self.assertRaises(frappe.PermissionError):
						deny_cross_company_share(self._share(doctype, other, user=self.user))
					with self.assertRaises(frappe.PermissionError):
						deny_cross_company_share(self._share(doctype, own, everyone=1))

	def test_share_guard_ignores_other_doctypes(self):
		# Card Equipment Assignment is not in the scope list: its shares are not checked here
		deny_cross_company_share(self._share(ASSIGNMENT, self.asg_b, user=self.user))
