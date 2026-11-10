# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-141 (#41, WP-M1): Card Rate Agreement rules and card.agreements.resolve.

Masters (company B, projects, equipment, types, parties) are inserted raw (no validation; only the stored values
matter); agreements go through insert() and submit() as Administrator so every rule runs. Everything is rolled
back."""

import pathlib
import re

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from card import agreements
from card.agreements import AmbiguousAgreementError, OverlappingAgreementError, resolve
from card.company_scope import has_company_permission
from card.tests.test_controllers import _ensure_masters

DT = "Card Rate Agreement"
D = "2026-03-01"
REPO = pathlib.Path(__file__).resolve().parents[2]


class TestRateAgreements(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.t = frappe.generate_hash(length=8)
		self.A = self._m["company"]
		self.B = self._company("TEST-CRA-CO-" + self.t)
		self.type1 = self._raw(
			"Card Equipment Type", "TEST-CRA-T1-" + self.t, equipment_type_name="T1" + self.t
		)
		self.type2 = self._raw(
			"Card Equipment Type", "TEST-CRA-T2-" + self.t, equipment_type_name="T2" + self.t
		)
		self.eq1 = self._raw(
			"Card Equipment", "TEST-CRA-E1-" + self.t, company=self.A, equipment_type=self.type1
		)
		self.eq2 = self._raw(
			"Card Equipment", "TEST-CRA-E2-" + self.t, company=self.A, equipment_type=self.type1
		)
		self.eq3 = self._raw(
			"Card Equipment", "TEST-CRA-E3-" + self.t, company=self.A, equipment_type=self.type2
		)
		self.eq_b = self._raw(
			"Card Equipment", "TEST-CRA-EB-" + self.t, company=self.B, equipment_type=self.type1
		)
		self.proj = self._raw("Project", "TEST-CRA-PA-" + self.t, project_name="PA" + self.t, company=self.A)
		self.proj2 = self._raw(
			"Project", "TEST-CRA-PA2-" + self.t, project_name="PA2" + self.t, company=self.A
		)
		self.proj_b = self._raw(
			"Project", "TEST-CRA-PB-" + self.t, project_name="PB" + self.t, company=self.B
		)
		self.sup = self._raw("Supplier", "TEST-CRA-S-" + self.t, supplier_name="S" + self.t)
		self.sup2 = self._raw("Supplier", "TEST-CRA-S2-" + self.t, supplier_name="S2" + self.t)
		self.cust = self._raw("Customer", "TEST-CRA-C-" + self.t, customer_name="C" + self.t)
		self.cust2 = self._raw("Customer", "TEST-CRA-C2-" + self.t, customer_name="C2" + self.t)
		self.S = ("Supplier", self.sup)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---------- builders ----------
	def _company(self, name):
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "R" + self.t[:6].upper(),
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
		doc.db_insert()
		return name

	def _agreement(self, submit=True, **values):
		data = {
			"doctype": DT,
			"company": self.A,
			"equipment": self.eq1,
			"supplier": self.sup,
			"valid_from": D,
			"daily_rate": 500,
			**values,
		}
		doc = frappe.get_doc(data).insert()
		if submit:
			doc.submit()
		return doc

	# ---------- resolve: none / one / several ----------
	def test_none_when_nothing_matches(self):
		self.assertIsNone(resolve(self.A, self.eq1, self.S, D))
		self._agreement(submit=False)  # a draft never matches
		self.assertIsNone(resolve(self.A, self.eq1, self.S, D))
		self._agreement(equipment=self.eq3)  # other equipment
		self.assertIsNone(resolve(self.A, self.eq1, self.S, D))

	def test_party_is_required(self):
		self._agreement()
		for party in (None, "", ("Supplier", None), {"party_type": "Supplier"}):
			with self.subTest(party=party), self.assertRaises(frappe.ValidationError) as ctx:
				resolve(self.A, self.eq1, party, D)
			self.assertIn("party", str(ctx.exception))

	def test_one_match_by_equipment_and_by_type(self):
		own = self._agreement()
		self.assertEqual(resolve(self.A, self.eq1, self.S, D).name, own.name)
		self.assertEqual(own.equipment_type, self.type1)  # set from the equipment
		by_type = self._agreement(equipment=None, equipment_type=self.type1, daily_rate=400)
		found = resolve(self.A, self.eq2, self.S, D)
		self.assertEqual(found.name, by_type.name)
		self.assertEqual(found.daily_rate, 400)
		self.assertIsNone(resolve(self.A, self.eq3, self.S, D))  # another type

	def test_several_matches_raise(self):
		own = self._agreement()
		by_type = self._agreement(equipment=None, equipment_type=self.type1)
		with self.assertRaises(AmbiguousAgreementError) as ctx:
			resolve(self.A, self.eq1, self.S, D)
		self.assertIn(own.name, str(ctx.exception))
		self.assertIn(by_type.name, str(ctx.exception))
		# two customers on one equipment and project: each customer resolves its own; a plain name that is
		# both an agreement without a project and one for the project is ambiguous
		first = self._agreement(equipment=self.eq3, supplier=None, customer=self.cust)
		second = self._agreement(equipment=self.eq3, supplier=None, customer=self.cust2, project=self.proj)
		self.assertEqual(
			resolve(self.A, self.eq3, ("Customer", self.cust), D, project=self.proj).name, first.name
		)
		self.assertEqual(
			resolve(self.A, self.eq3, ("Customer", self.cust2), D, project=self.proj).name, second.name
		)
		self.assertEqual(resolve(self.A, self.eq3, self.cust2, D, project=self.proj).name, second.name)
		self._agreement(equipment=self.eq3, supplier=None, customer=self.cust, project=self.proj)
		with self.assertRaises(AmbiguousAgreementError):
			resolve(self.A, self.eq3, ("Customer", self.cust), D, project=self.proj)

	def test_party_and_project_filters(self):
		supplier_side = self._agreement(customer=self.cust)
		self.assertEqual(resolve(self.A, self.eq1, self.S, D).name, supplier_side.name)
		self.assertEqual(
			resolve(self.A, self.eq1, {"party_type": "Customer", "party": self.cust}, D).name,
			supplier_side.name,
		)
		self.assertEqual(resolve(self.A, self.eq1, self.cust, D).name, supplier_side.name)
		self.assertIsNone(resolve(self.A, self.eq1, ("Supplier", self.sup2), D))
		self.assertIsNone(resolve(self.A, self.eq1, ("Customer", self.sup), D))
		with self.assertRaises(frappe.ValidationError):
			resolve(self.A, self.eq1, ("Employee", "x"), D)
		# a project agreement needs that project; an agreement without a project serves every project
		in_project = self._agreement(equipment=self.eq2, project=self.proj)
		self.assertIsNone(resolve(self.A, self.eq2, self.S, D))
		self.assertIsNone(resolve(self.A, self.eq2, self.S, D, project=self.proj2))
		self.assertEqual(resolve(self.A, self.eq2, self.S, D, project=self.proj).name, in_project.name)
		self.assertEqual(resolve(self.A, self.eq1, self.S, D, project=self.proj).name, supplier_side.name)

	def test_zone_filter(self):
		zoned = self._agreement(zone="  North ")
		self.assertEqual(zoned.zone, "North")
		# zone=None: agreements without a zone only (as project=None)
		self.assertIsNone(resolve(self.A, self.eq1, self.S, D))
		self.assertIsNone(resolve(self.A, self.eq1, self.S, D, zone="South"))
		for zone in ("North", "north", " NORTH "):
			with self.subTest(zone=zone):
				self.assertEqual(resolve(self.A, self.eq1, self.S, D, zone=zone).name, zoned.name)
		# an agreement without a zone serves every zone
		unzoned = self._agreement(equipment=self.eq2)
		self.assertEqual(resolve(self.A, self.eq2, self.S, D).name, unzoned.name)
		self.assertEqual(resolve(self.A, self.eq2, self.S, D, zone="North").name, unzoned.name)
		# the overlap key compares the zone the same way
		with self.assertRaises(OverlappingAgreementError):
			self._agreement(zone="NORTH")

	# ---------- date edges ----------
	def test_date_edges(self):
		closed = self._agreement(valid_from="2026-03-01", valid_to="2026-03-31")
		self.assertIsNone(resolve(self.A, self.eq1, self.S, "2026-02-28"))
		self.assertEqual(resolve(self.A, self.eq1, self.S, "2026-03-01").name, closed.name)
		self.assertEqual(resolve(self.A, self.eq1, self.S, getdate("2026-03-31")).name, closed.name)
		self.assertIsNone(resolve(self.A, self.eq1, self.S, "2026-04-01"))
		# the next agreement may start the day after; open-ended from then on
		following = self._agreement(valid_from="2026-04-01", daily_rate=550)
		self.assertEqual(resolve(self.A, self.eq1, self.S, "2026-04-01").name, following.name)
		self.assertEqual(resolve(self.A, self.eq1, self.S, "2030-01-01").name, following.name)
		self.assertEqual(resolve(self.A, self.eq1, self.S, "2026-03-31").name, closed.name)
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._agreement(valid_from="2026-05-02", valid_to="2026-05-01", equipment=self.eq2)
		self.assertIn("end date is before the start date", str(ctx.exception))

	# ---------- overlap ----------
	def test_overlap_refused(self):
		first = self._agreement(valid_from="2026-03-01", valid_to="2026-03-31")
		for start, end in (("2026-03-31", None), ("2026-02-01", "2026-03-01"), ("2026-03-10", "2026-03-20")):
			with self.subTest(start=start, end=end), self.assertRaises(OverlappingAgreementError):
				self._agreement(valid_from=start, valid_to=end, daily_rate=600)
		# the same key whether or not the type was typed in (set from the equipment)
		with self.assertRaises(OverlappingAgreementError):
			self._agreement(equipment_type=self.type1, valid_from="2026-03-05")
		# refused already as a draft
		with self.assertRaises(OverlappingAgreementError):
			self._agreement(submit=False, valid_from="2026-03-15")
		# adjacent periods do not overlap
		self._agreement(valid_from="2026-04-01", valid_to="2026-04-30")
		# other keys may overlap: another zone, another customer, another project
		self._agreement(zone="North")
		self._agreement(customer=self.cust)
		self._agreement(project=self.proj)
		# a changed rate: cancel and amend (or a new agreement from a later date)
		first.reload()
		first.cancel()
		amended = frappe.copy_doc(first)
		amended.amended_from = first.name
		amended.docstatus = 0
		amended.daily_rate = 650
		amended.insert()
		amended.submit()
		self.assertEqual(frappe.db.get_value(DT, amended.name, ["docstatus", "daily_rate"]), (1, 650))
		self.assertEqual(frappe.db.get_value(DT, first.name, ["docstatus", "daily_rate"]), (2, 500))

	def test_submitted_agreement_is_never_edited(self):
		doc = self._agreement()
		doc.reload()
		doc.daily_rate = 999
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			doc.save()
		self.assertEqual(frappe.db.get_value(DT, doc.name, "daily_rate"), 500)

	# ---------- scope and content rules ----------
	def test_scope_rules(self):
		for values, message in (
			({"equipment": None}, "choose an equipment or an equipment type"),
			({"supplier": None}, "choose a supplier, a customer or both"),
			({"equipment_type": self.type2}, "is not of equipment type"),
			({"daily_rate": 0}, "enter at least one rate or one cost responsibility row"),
			({"daily_rate": 0, "quantity_rate": 5}, "a rate per quantity needs its unit"),
		):
			with (
				self.subTest(**{k: str(v) for k, v in values.items()}),
				self.assertRaises(frappe.ValidationError) as ctx,
			):
				self._agreement(submit=False, **values)
			self.assertIn(message, str(ctx.exception))
		doc = self._agreement(submit=False, equipment_type=self.type1)
		self.assertEqual(doc.currency, frappe.db.get_value("Company", self.A, "default_currency"))

	# ---------- cross-company ----------
	def test_cross_company_refused(self):
		for values in ({"equipment": self.eq_b}, {"project": self.proj_b}):
			with self.subTest(**values), self.assertRaises(frappe.ValidationError) as ctx:
				self._agreement(submit=False, **values)
			self.assertIn("belongs to another company", str(ctx.exception))
		with self.assertRaises(frappe.ValidationError):
			resolve(self.A, self.eq_b, self.S, D)  # equipment of company B asked for company A
		with self.assertRaises(frappe.ValidationError):
			resolve(self.A, "TEST-CRA-NONE-" + self.t, self.S, D)
		# a company-B agreement for the same type never serves company A
		b_agreement = self._agreement(company=self.B, equipment=None, equipment_type=self.type1)
		self.assertIsNone(resolve(self.A, self.eq1, self.S, D))
		self.assertEqual(resolve(self.B, self.eq_b, self.S, D).name, b_agreement.name)
		# an amendment cannot move a cancelled agreement to another company
		moved = self._agreement(equipment=None, equipment_type=self.type2)
		moved.cancel()
		amendment = frappe.copy_doc(moved)
		amendment.update({"amended_from": moved.name, "docstatus": 0, "company": self.B})
		with self.assertRaises(frappe.ValidationError) as ctx:
			amendment.insert()
		self.assertIn("an amendment keeps the company", str(ctx.exception))
		# the generic company scope (FR-131) isolates the records of a restricted user
		a_agreement = self._agreement()
		user = self._user(restrict=self.A)
		self.assertTrue(has_company_permission(a_agreement, "read", user=user))
		self.assertFalse(has_company_permission(b_agreement, "read", user=user))
		self.assertFalse(frappe.has_permission(DT, "read", doc=b_agreement, user=user))
		self.assertTrue(frappe.has_permission(DT, "read", doc=a_agreement, user=user))

	def test_restricted_user_cannot_write_other_company(self):
		"""A Card Manager limited to company A: no create in B (draft or submitted), no move of a draft to B,
		and the list shows company A only."""
		user = self._user(restrict=self.A, roles=("Card Manager",))
		b_agreement = self._agreement(company=self.B, equipment=None, equipment_type=self.type1)
		b_values = {"company": self.B, "equipment": None, "equipment_type": self.type2}
		for docstatus in (0, 1):
			with self.subTest(docstatus=docstatus):
				frappe.set_user(user)
				doc = frappe.get_doc(
					{
						"doctype": DT,
						"supplier": self.sup,
						"valid_from": D,
						"daily_rate": 500,
						"docstatus": docstatus,
						**b_values,
					}
				)
				with self.assertRaises(frappe.PermissionError):
					doc.insert()
				frappe.set_user("Administrator")
				self.assertFalse(frappe.db.exists(DT, {"owner": user}))
		# the same user's company-A draft works, but cannot be moved to company B
		frappe.set_user(user)
		draft = frappe.get_doc(
			{
				"doctype": DT,
				"company": self.A,
				"equipment": self.eq2,
				"supplier": self.sup,
				"valid_from": D,
				"daily_rate": 500,
			}
		).insert()
		draft.update(b_values)
		with self.assertRaises(frappe.PermissionError):
			draft.save()
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value(DT, draft.name, "company"), self.A)
		frappe.set_user(user)
		listed = set(frappe.get_list(DT, pluck="name"))
		frappe.set_user("Administrator")
		self.assertIn(draft.name, listed)
		self.assertNotIn(b_agreement.name, listed)

	def _user(self, restrict, roles=("Card User",)):
		email = f"cra-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Rate Agreement",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)
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

	# ---------- responsibility rows ----------
	def _rows(self, *rows):
		keys = ("cost_category", "paid_by", "split_percent")
		return [{**dict(zip(keys, row[:3], strict=True)), **(row[3] if len(row) > 3 else {})} for row in rows]

	def test_child_row_company_check(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._agreement(
				submit=False,
				equipment=None,
				equipment_type=self.type1,
				responsibilities=self._rows(("Diesel", "Company", 100, {"equipment": self.eq_b})),
			)
		self.assertIn(self.eq_b, str(ctx.exception))
		# a row for an equipment of another type; any row equipment when the agreement names one
		for agreement_values, row_equipment, message in (
			({"equipment": None, "equipment_type": self.type1}, self.eq3, "is not of equipment type"),
			({}, self.eq2, "leave the equipment empty"),
			({}, self.eq1, "leave the equipment empty"),
		):
			with self.subTest(row=row_equipment), self.assertRaises(frappe.ValidationError) as ctx:
				self._agreement(
					submit=False,
					**agreement_values,
					responsibilities=self._rows(("Diesel", "Company", 100, {"equipment": row_equipment})),
				)
			self.assertIn(message, str(ctx.exception))
		doc = self._agreement(
			equipment=None,
			equipment_type=self.type1,
			daily_rate=0,
			responsibilities=self._rows(
				("Diesel", "Company", 100, {"equipment": self.eq2}),
				("Rental", "Customer", 60, {"customer": self.cust, "supplier": self.sup}),
				("Rental", "Supplier", 40, {"supplier": self.sup}),
				("Transport", "Other party", 100, {"other_party": "Main contractor"}),
			),
		)
		self.assertIsNone(doc.responsibilities[1].supplier)  # only the chosen payer's party is kept
		self.assertEqual(resolve(self.A, self.eq2, self.S, D).name, doc.name)

	def test_responsibility_shares(self):
		for rows, message in (
			(self._rows(("Rental", "Company", 60)), "add up to 60"),
			(
				self._rows(("Rental", "Company", 60), ("Rental", "Company", 40)),
				"the same payer is entered twice",
			),
			(self._rows(("Rental", "Customer", 100)), "name the paying party"),
			(
				self._rows(("Rental", "Company", 0), ("Rental", "Supplier", 100, {"supplier": self.sup})),
				"more than 0% and at most 100%",
			),
		):
			with self.subTest(message=message), self.assertRaises(frappe.ValidationError) as ctx:
				self._agreement(submit=False, responsibilities=rows)
			self.assertIn(message, str(ctx.exception))

	# ---------- not wired (M2 does it) ----------
	def test_nothing_calls_resolve_yet(self):
		pattern = re.compile(r"agreements\.resolve|from card\.agreements import[^\n]*\bresolve\b")
		callers = [
			str(path.relative_to(REPO))
			for path in (REPO / "card").rglob("*.py")
			if "tests" not in path.parts and path.name != "agreements.py" and pattern.search(path.read_text())
		]
		self.assertEqual(callers, [])
		self.assertTrue(callable(agreements.resolve))
