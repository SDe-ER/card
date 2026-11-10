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
	check_child_companies,
	company_query_conditions,
	deny_cross_company_share,
	document_companies,
	has_company_permission,
)
from card.tests.test_controllers import _ensure_masters

FILL = "Project Diesel Fill"
ASSIGNMENT = "Card Equipment Assignment"
REPO = pathlib.Path(__file__).resolve().parents[2]


def _field_target_meta(target, doctypes):
	"""The fields of ``target`` as {fieldname: field}: from the repository JSON (a planned DocType may link
	another one not installed yet), else from the site."""
	if target in doctypes:
		return {f["fieldname"]: f for f in doctypes[target].get("fields") or []}
	if frappe.db.exists("DocType", target):
		return {f.fieldname: f.as_dict() for f in frappe.get_meta(target).fields}
	return {}


def scope_problems(meta, doctypes):
	"""What keeps the generic company scope from isolating the DocType ``meta`` (a DocType JSON dict)."""
	problems = []
	if meta.get("istable") or meta.get("issingle"):
		problems.append("child table or single")
	fields = {f["fieldname"]: f for f in meta.get("fields") or []}
	company = fields.get("company")
	if not company or company.get("fieldtype") != "Link" or company.get("options") != "Company":
		problems.append("no Company `company` field")
	else:
		if not company.get("reqd"):
			problems.append("`company` is not mandatory")
		fetch = company.get("fetch_from")
		if fetch:
			source = fields.get(fetch.split(".", 1)[0]) or {}
			if (
				source.get("fieldtype") != "Link"
				or source.get("options") not in company_scope.COMPANY_SOURCES
			):
				problems.append(f"`company` is fetched from {fetch}, not from a company source link")
	for field in fields.values():
		target = field.get("options")
		if field.get("fieldtype") != "Link" or target in (None, "Company") or field["fieldname"] == "company":
			continue
		if field["fieldname"] == "amended_from" and target == meta.get("name"):
			# Frappe's own amend link of a submittable DocType (DocType.make_amendable): the record's company
			# field governs; the package controller must refuse an amendment of another company's record
			continue
		target_company = _field_target_meta(target, doctypes).get("company") or {}
		if target_company.get("fieldtype") == "Link" and target_company.get("options") == "Company":
			if target not in company_scope.COMPANY_SOURCES:
				problems.append(
					f"link `{field['fieldname']}` to {target} (has a company) is not in COMPANY_SOURCES"
				)
	return problems


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
		"""A planned DocType, once its package adds it: a mandatory Company ``company`` field, not fetched or
		fetched from a company source link, and every link to a company-owned DocType listed in COMPANY_SOURCES;
		otherwise the generic scope would not isolate it."""
		doctypes = _repo_doctypes()
		self.assertEqual(
			{
				name: meta.get("module")
				for name, meta in doctypes.items()
				if name in company_scope.SCOPED_DOCTYPES
			},
			{name: "Card" for name in doctypes if name in company_scope.SCOPED_DOCTYPES},
		)
		for doctype in company_scope.SCOPED_DOCTYPES:
			meta = doctypes.get(doctype)
			if not meta:
				continue  # not merged yet: its hooks are inert
			with self.subTest(doctype=doctype):
				self.assertEqual(scope_problems(meta, doctypes), [])

	def test_scope_guard_itself(self):
		"""The guard above, on synthetic DocTypes (no planned DocType exists yet)."""

		def meta(*fields, **props):
			return {"name": "Card Scope Probe", "module": "Card", "fields": list(fields), **props}

		company = {"fieldname": "company", "fieldtype": "Link", "options": "Company", "reqd": 1}
		equipment = {"fieldname": "equipment", "fieldtype": "Link", "options": "Card Equipment"}
		self.assertEqual(scope_problems(meta(company, equipment), {}), [])
		fetched = {**company, "fetch_from": "equipment.company"}
		self.assertEqual(scope_problems(meta(fetched, equipment), {}), [])
		amend = {"fieldname": "amended_from", "fieldtype": "Link", "options": "Card Scope Probe"}
		self.assertEqual(scope_problems(meta(company, amend), {"Card Scope Probe": meta(company)}), [])
		# any other link to the DocType itself still needs the company check
		self_link = {**amend, "fieldname": "previous_reading"}
		self.assertTrue(scope_problems(meta(company, self_link), {"Card Scope Probe": meta(company)}))
		cases = {
			"no company": meta(equipment),
			"not mandatory": meta({**company, "reqd": 0}),
			"fetched from a non-source": meta(
				{**company, "fetch_from": "employee.company"},
				{"fieldname": "employee", "fieldtype": "Link", "options": "Employee"},
			),
			"unlisted company-owned link": meta(
				company, {"fieldname": "cost_center", "fieldtype": "Link", "options": "Cost Center"}
			),
			"child table": meta(company, istable=1),
		}
		for label, probe in cases.items():
			with self.subTest(case=label):
				self.assertTrue(scope_problems(probe, {}))


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
		# no company yet: refused for a restricted user (the server could set one he may not use) ...
		self.assertFalse(self._allowed(frappe.new_doc(FILL)))
		# ... but a source link resolves it
		self.assertTrue(self._allowed(frappe.new_doc(FILL, card_equipment=self.eq_a)))
		self.assertTrue(self._allowed(frappe.new_doc(FILL), user=self._user()))

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
		self.assertFalse(self._allowed(frappe.new_doc(ASSIGNMENT)))  # no link yet: no company

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

	# ---------- CARD module only ----------
	def test_other_modules_are_never_checked(self):
		todo = frappe.new_doc("ToDo")  # Desk module, no company: would be refused as a new CARD record
		self.assertTrue(has_company_permission(todo, "create", user=self.user))
		self.assertTrue(company_scope.is_scoped("Sales Invoice"))
		self.assertEqual(company_query_conditions(user=self.user, doctype="Sales Invoice"), "")
		with patch.object(company_scope, "SCOPED_DOCTYPES", ("ToDo",)):
			deny_cross_company_share(self._share("ToDo", "x", everyone=1))

	# ---------- child rows (package helper) ----------
	def test_check_child_companies(self):
		doc = frappe.new_doc(FILL, company=self.A)
		doc.append("equipment_filled", {"card_equipment": self.eq_a})
		check_child_companies(doc, "equipment_filled", "card_equipment")
		doc.append("equipment_filled", {"card_equipment": self.eq_b})
		with self.assertRaises(frappe.ValidationError):
			check_child_companies(doc, "equipment_filled", "card_equipment")
		with self.assertRaises(frappe.ValidationError):
			check_child_companies(doc, "equipment_filled", "name")  # not a company source link

	# ---------- end to end through Frappe (patched registration) ----------
	def _generic_only(self):
		"""Project Diesel Fill with the generic hook as its only controller check."""
		real = frappe.get_hooks

		def get_hooks(hook=None, default=None, app_name=None):
			result = real(hook, default, app_name)
			if hook == "has_permission":
				result = dict(result or {})
				result[FILL] = [company_scope.HAS_PERMISSION]
			return result

		return patch.object(frappe, "get_hooks", side_effect=get_hooks)

	def test_end_to_end_read(self):
		with self._generic_only():
			self.assertFalse(
				frappe.has_permission(FILL, "read", doc=frappe.get_doc(FILL, self.fill_b), user=self.user)
			)
			self.assertTrue(
				frappe.has_permission(FILL, "read", doc=frappe.get_doc(FILL, self.fill_a), user=self.user)
			)

	def test_end_to_end_insert(self):
		user = self._user(restrict=self.A, roles=("Card Manager",))
		refused = (
			{"company": self.B, "project": self.proj_b},
			# company A passes the standard Company User Permission; the company-B project is caught by the hook
			{"company": self.A, "project": self.proj_b},
			{"company": self.A, "card_equipment": self.eq_b},
		)
		with self._generic_only():
			for docstatus in (0, 1):
				for values in refused:
					with self.subTest(docstatus=docstatus, **values):
						frappe.set_user(user)
						doc = frappe.get_doc({"doctype": FILL, "docstatus": docstatus, **values})
						with self.assertRaises(frappe.PermissionError):
							doc.insert()
						frappe.set_user("Administrator")
						self.assertFalse(
							frappe.db.exists(FILL, {"project": values.get("project") or "-", "owner": user})
						)
				with self.subTest(docstatus=docstatus, control="company A"):
					# positive control: the same user's company-A record passes the permission check (it may
					# still fail later validation, which is not a permission error)
					frappe.set_user(user)
					frappe.db.savepoint("scope_e2e")
					try:
						frappe.get_doc(
							{
								"doctype": FILL,
								"docstatus": docstatus,
								"company": self.A,
								"project": self.proj_a,
							}
						).insert()
					except frappe.PermissionError:
						self.fail("company-A insert refused by a permission check")
					except Exception:
						pass
					finally:
						frappe.db.rollback(save_point="scope_e2e")
						frappe.set_user("Administrator")
