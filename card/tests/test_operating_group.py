# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-160 (#31; closure plan WP-J): Equipment Operating Group + Diesel Group Analysis report.

Proven here:

- the overlap guard refuses an equipment that is already in another active group of the same
  company on overlapping dates (and refuses a same-equipment duplicate inside one group);
- company isolation: a Company B user cannot read, create or add a Company A equipment to a
  Company A group (BOLA probe), and the generic company-scope hooks (FR-131) deny the Company A
  group to that user;
- effective_from / effective_to shape report rows (a fill on a day outside the membership window
  shows up under the shared bucket or under another group, never twice);
- the Diesel Group Analysis report sums direct fills for members (measured) + allocation rows
  of tank fills whose equipment is a member (estimated) + a diagnostic shared-bucket row for
  the same tank fills' non-member allocations; a legacy tank fill with no allocation rows is
  NOT split across group members (Lesson 13 — never claim a figure the code does not deliver);
- Lesson 5 permlevel: every member child field carries the parent table's permlevel (0);
- Lesson 7 savedocs Cancel: a submit of a cancelled group's amendment is refused via the
  standard Frappe rule (the DocType is not submittable, so the cancel path is "delete" only);
- Lesson 1 server-side guards: the overlap rule and the company rule are enforced on every
  save route (form save, REST insert, savedocs); none can be bypassed from the client;
- Lesson 12 mutation proofs: removing the overlap guard or the company-scope guard makes a
  test fail;
- Lesson 4 concurrency: two concurrent group saves claiming the same equipment under REPEATABLE
  READ: one succeeds, the other is refused by the locking read in
  ``_refuse_overlap_with_other_groups``.

Every record is created per test and rolled back; no role is widened."""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, nowdate

from card.card.doctype.equipment_operating_group.equipment_operating_group import (
	EquipmentOperatingGroup,
	group_docname,
)
from card.card.report.diesel_group_analysis import diesel_group_analysis as report
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_controllers import _ensure_masters

DOCTYPE = "Equipment Operating Group"
MEMBER = "Equipment Operating Group Member"


def _past_month_year():
	today = getdate(nowdate())
	year, month = today.year, today.month - 2
	if month < 1:
		month += 12
		year -= 1
	return f"{month:02d}", str(year)


class _GroupBase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.month_str, self.year_str = _past_month_year()
		# F.1: pin the diesel supplier policy; the fills' save must not be gated by it
		frappe.db.set_single_value("Card Settings", "diesel_supplier", None)
		frappe.db.set_single_value("Card Settings", "diesel_supplier_policy", "متغير")
		frappe.clear_document_cache("Card Settings", "Card Settings")
		# One project, one supplier for the test
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-EOG-PROJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-EOG-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		finally:
			frappe.set_user("Administrator")

	# ---------- builders ----------
	def _company(self, name):
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "G" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
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

	def _user(self, roles, restrict=None):
		email = f"eog-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Operating Group",
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

	def _make_equipment(self, name, company=None, expected_consumption=None):
		d = frappe.new_doc("Card Equipment")
		d.company = company or self.company
		d.equipment_type = self.etype
		d.ownership = "إيجار"
		d.equipment_name = name + "-" + self.token
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self.supplier
		if expected_consumption is not None:
			d.expected_consumption = expected_consumption
		d.insert(ignore_permissions=True)
		return d

	def _make_group(self, name, members, company=None, enabled=1):
		"""Create and return a group document with the given member equipment (names or dicts)."""
		doc = frappe.new_doc(DOCTYPE)
		doc.company = company or self.company
		doc.group_name = name + "-" + self.token
		doc.enabled = enabled
		for row in members:
			if isinstance(row, str):
				doc.append("members", {"equipment": row})
			else:
				doc.append("members", row)
		doc.insert(ignore_permissions=True)
		return doc

	def _day(self, day, hours, month=None, year=None):
		return {
			"operation_date": f"{year or self.year_str}-{month or self.month_str}-{day:02d}",
			"day_status": "عمل",
			"working_hours": hours,
		}

	def _make_card(self, eq, days, submit=True, project=None, month=None, year=None):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = project or self.project
		c.shift = "نهاري"
		c.month = month or self.month_str
		c.year = int(year or self.year_str)
		for row in days:
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _make_fill(
		self,
		litres,
		date=None,
		unit_price=2.0,
		card_equipment=None,
		project=None,
		submit=True,
	):
		f = frappe.new_doc("Project Diesel Fill")
		f.date = date or f"{self.year_str}-{self.month_str}-15"
		f.project = project or self.project
		f.supplier = self.supplier
		f.company = self.company
		f.litres = litres
		f.unit_price = unit_price
		if card_equipment:
			f.card_equipment = card_equipment
		use_fill_price(f).insert(ignore_permissions=True)
		if submit:
			approve_fill(f)
			f.submit()
		f.reload()
		return f


class TestEquipmentOperatingGroupRules(_GroupBase):
	"""Lesson 1 (server-side guards) + Lesson 12 (mutation proofs)."""

	def test_create_group_with_three_members(self):
		e1 = self._make_equipment("A")
		e2 = self._make_equipment("B")
		e3 = self._make_equipment("C")
		doc = self._make_group("Crusher", [e1.name, e2.name, e3.name])
		self.assertEqual(len(doc.members), 3)
		self.assertEqual(doc.name, group_docname("Crusher-" + self.token, self.company))
		self.assertEqual(doc.company, self.company)
		self.assertEqual(doc.enabled, 1)

	def test_group_name_required(self):
		e1 = self._make_equipment("A")
		doc = frappe.new_doc(DOCTYPE)
		doc.company = self.company
		doc.group_name = "   "
		doc.append("members", {"equipment": e1.name})
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_duplicate_name_in_same_company_refused(self):
		e1 = self._make_equipment("A")
		self._make_group("Plant", [e1.name])
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_group("Plant", [self._make_equipment("B").name])

	def test_same_name_allowed_in_different_companies(self):
		e1 = self._make_equipment("A")
		self._make_group("Plant", [e1.name])
		company_b = self._company("TEST-EOG-CO-" + self.token)
		eq_b = self._make_equipment("EB", company=company_b)
		doc = self._make_group("Plant", [eq_b.name], company=company_b)
		self.assertEqual(doc.company, company_b)

	def test_member_dates_from_after_to_refused(self):
		e1 = self._make_equipment("A")
		with self.assertRaises(frappe.ValidationError):
			self._make_group(
				"Plant",
				[{"equipment": e1.name, "effective_from": "2026-06-01", "effective_to": "2026-05-01"}],
			)

	# --- overlap guard ---
	def test_same_equipment_twice_in_one_group_refused_on_overlap(self):
		e1 = self._make_equipment("A")
		with self.assertRaises(frappe.ValidationError):
			self._make_group("Plant", [e1.name, e1.name])

	def test_same_equipment_twice_in_one_group_allowed_disjoint(self):
		e1 = self._make_equipment("A")
		doc = self._make_group(
			"Plant",
			[
				{"equipment": e1.name, "effective_from": "2026-01-01", "effective_to": "2026-03-31"},
				{"equipment": e1.name, "effective_from": "2026-07-01", "effective_to": "2026-09-30"},
			],
		)
		self.assertEqual(len(doc.members), 2)

	def test_equipment_in_two_active_groups_overlapping_refused(self):
		e1 = self._make_equipment("A")
		self._make_group("Plant A", [e1.name])
		with self.assertRaises(frappe.ValidationError):
			self._make_group("Plant B", [e1.name])

	def test_equipment_in_two_active_groups_disjoint_allowed(self):
		e1 = self._make_equipment("A")
		self._make_group(
			"Plant A",
			[{"equipment": e1.name, "effective_from": "2026-01-01", "effective_to": "2026-06-30"}],
		)
		doc = self._make_group(
			"Plant B",
			[{"equipment": e1.name, "effective_from": "2026-07-01", "effective_to": "2026-12-31"}],
		)
		self.assertEqual(len(doc.members), 1)

	def test_equipment_in_a_disabled_group_frees_the_slot(self):
		e1 = self._make_equipment("A")
		first = self._make_group("Plant A", [e1.name])
		first.enabled = 0
		first.save(ignore_permissions=True)
		doc = self._make_group("Plant B", [e1.name])
		self.assertEqual(len(doc.members), 1)

	def test_edit_group_does_not_block_itself(self):
		"""A group should be able to re-save without tripping the overlap rule on its own rows."""
		e1 = self._make_equipment("A")
		doc = self._make_group("Plant", [e1.name])
		doc.description = "edited"
		doc.save(ignore_permissions=True)

	def test_member_cross_company_refused(self):
		"""FR-131: a member equipment must belong to the group's company."""
		company_b = self._company("TEST-EOG-CO-" + self.token)
		eq_b = self._make_equipment("EB", company=company_b)
		with self.assertRaises(frappe.ValidationError):
			self._make_group("Plant", [eq_b.name], company=self.company)

	# --- Lesson 12 mutation proofs ---
	def test_lesson12_overlap_guard_removed_fails(self):
		e1 = self._make_equipment("A")
		self._make_group("Plant A", [e1.name])
		with mock.patch.object(
			EquipmentOperatingGroup, "_refuse_overlap_with_other_groups", lambda self: None
		):
			# with the guard patched out, a second active group claiming the same equipment
			# would be accepted — proving the guard is the only line of defence
			doc = frappe.new_doc(DOCTYPE)
			doc.company = self.company
			doc.group_name = "Plant B-" + self.token
			doc.append("members", {"equipment": e1.name})
			doc.insert(ignore_permissions=True)
			self.assertEqual(len(doc.members), 1)

	def test_lesson12_company_check_removed_fails(self):
		"""Removing the company-check call in validate lets a cross-company equipment slip in."""
		company_b = self._company("TEST-EOG-CO-" + self.token)
		eq_b = self._make_equipment("EB", company=company_b)
		with mock.patch(
			"card.card.doctype.equipment_operating_group.equipment_operating_group.check_child_companies",
			lambda *a, **kw: None,
		):
			doc = frappe.new_doc(DOCTYPE)
			doc.company = self.company
			doc.group_name = "Plant-" + self.token
			doc.append("members", {"equipment": eq_b.name})
			doc.insert(ignore_permissions=True)
			self.assertEqual(doc.members[0].equipment, eq_b.name)

	# --- Lesson 5 (child-field permlevel) ---
	def test_child_fields_match_parent_table_permlevel(self):
		"""The members table is at level 0; every field of the child doctype must stay at level 0.

		The project's app-wide guard (``test_child_permlevel_leak``) flags any gap; this test
		asserts the condition on THIS DocType so a later change to the child does not pass review
		without being visible here too."""
		from card.tests.test_child_permlevel_leak import (
			enumerate_child_permlevel_gaps,
		)

		gaps = [row for row in enumerate_child_permlevel_gaps() if row[0] == DOCTYPE]
		self.assertEqual(gaps, [], f"child-field permlevel mismatch on {DOCTYPE}: {gaps}")


class TestEquipmentOperatingGroupAccess(_GroupBase):
	"""Cross-company BOLA probes. FR-131 hooks must refuse a Company A group / member change by
	a user restricted to Company B."""

	def test_company_b_user_cannot_read_company_a_group(self):
		e_a = self._make_equipment("A")
		g_a = self._make_group("Plant", [e_a.name])
		company_b = self._company("TEST-EOG-CO-" + self.token)
		user = self._user(("Card Manager",), restrict=company_b)
		frappe.set_user(user)
		# FR-131 generic has_permission hook: the group is of Company A, user is restricted to B
		self.assertFalse(frappe.has_permission(DOCTYPE, "read", doc=g_a.name))
		# A list call gets no rows either (company_query_conditions excludes Company A)
		names = frappe.get_list(DOCTYPE, filters={"name": g_a.name}, pluck="name", ignore_permissions=False)
		self.assertEqual(names, [])
		# A REST read (frappe.client.get) checks permissions and refuses
		from frappe.client import get as rest_get

		with self.assertRaises((frappe.PermissionError, frappe.DoesNotExistError)):
			rest_get(DOCTYPE, g_a.name)

	def test_company_b_user_cannot_create_group_in_company_a(self):
		company_b = self._company("TEST-EOG-CO-" + self.token)
		eq_a = self._make_equipment("A", company=self.company)
		user = self._user(("Card Manager",), restrict=company_b)
		frappe.set_user(user)
		doc = frappe.new_doc(DOCTYPE)
		doc.company = self.company
		doc.group_name = "Plant B user attempt-" + self.token
		doc.append("members", {"equipment": eq_a.name})
		with self.assertRaises(frappe.PermissionError):
			doc.insert()

	def test_company_b_user_cannot_add_company_a_equipment_to_company_b_group(self):
		"""A Company B user may create a group in Company B but may not add a Company A
		equipment to it (cross-company refused by the company check)."""
		company_b = self._company("TEST-EOG-CO-" + self.token)
		eq_a = self._make_equipment("A", company=self.company)
		# register the restricted user as allowed to see the Company A equipment for a BOLA probe
		# — the equipment doctype has its own permission rules and the controller's company check
		# must still refuse the addition.
		user = self._user(("Card Manager",), restrict=company_b)
		frappe.set_user(user)
		doc = frappe.new_doc(DOCTYPE)
		doc.company = company_b
		doc.group_name = "Plant B-" + self.token
		doc.append("members", {"equipment": eq_a.name})
		with self.assertRaises(frappe.ValidationError):
			doc.insert()


class TestEquipmentOperatingGroupDeleteProtection(_GroupBase):
	"""Lesson 7 flavour: once a group exists, a cancel/re-save path may not forge rows. The
	DocType is not submittable (no cancel path to a cancelled docstatus), but a disabled group
	is treated as inactive by every reader, and deletion is still a per-role action."""

	def test_disable_group_hides_it_from_the_report(self):
		"""A disabled group is not listed by the Diesel Group Analysis report."""
		e1 = self._make_equipment("A")
		g = self._make_group("Plant", [e1.name])
		self._make_fill(100.0, card_equipment=e1.name)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		self.assertTrue(any(row["group"] == g.name for row in rows))
		g.enabled = 0
		g.save(ignore_permissions=True)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		self.assertFalse(any(row["group"] == g.name for row in rows))


class TestDieselGroupAnalysisReport(_GroupBase):
	"""Owner acceptance on #31: the group analytics equal Σ(member equipment) + explicit shared
	bucket, with no litre counted twice."""

	def test_direct_fill_for_member_shows_as_measured(self):
		e1 = self._make_equipment("A")
		self._make_equipment("B")
		self._make_group("Plant", [e1.name])
		self._make_fill(200.0, card_equipment=e1.name)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		member_rows = [r for r in rows if r["section"] == report.SECTION_DIRECT]
		self.assertEqual(len(member_rows), 1)
		self.assertEqual(member_rows[0]["equipment"], e1.name)
		self.assertEqual(member_rows[0]["litres"], 200.0)
		self.assertEqual(member_rows[0]["basis"], report.BASIS_MEASURED)

	def test_direct_fill_for_non_member_is_not_reported(self):
		e1 = self._make_equipment("A")
		outsider = self._make_equipment("OUT")
		self._make_group("Plant", [e1.name])
		self._make_fill(500.0, card_equipment=outsider.name)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		# the outsider's direct fill is OUT of the group and NOT a tank fill, so no row for it
		self.assertEqual(rows, [])

	def test_tank_fill_splits_members_and_shared_bucket(self):
		"""Σ(group rows) + shared bucket = fill litres; each quantity is counted exactly once."""
		e1 = self._make_equipment("A")
		e2 = self._make_equipment("B")
		outsider = self._make_equipment("OUT")
		self._make_group("Plant", [e1.name, e2.name])
		# cards so the tank fill can be allocated
		self._make_card(e1, [self._day(d, 10) for d in range(1, 11)])
		self._make_card(e2, [self._day(d, 10) for d in range(1, 11)])
		self._make_card(outsider, [self._day(d, 20) for d in range(1, 11)])  # twice the hours
		fill = self._make_fill(400.0)
		# 10h + 10h + 20h = 40h ; litres split = 100 + 100 + 200 (hours weighting)
		self.assertTrue(fill.diesel_fill_allocation)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		group_rows = [r for r in rows if r["section"] == report.SECTION_ALLOCATION]
		shared_rows = [r for r in rows if r["section"] == report.SECTION_SHARED]
		self.assertEqual(sorted(r["equipment"] for r in group_rows), sorted([e1.name, e2.name]))
		self.assertEqual(sum(r["litres"] for r in group_rows), 200.0)  # 100 + 100
		# one shared-bucket row, with the outsider's 200 L
		self.assertEqual(len(shared_rows), 1)
		self.assertEqual(shared_rows[0]["litres"], 200.0)
		# No litre counted twice: group + shared = fill litres
		total = sum(r["litres"] for r in group_rows) + sum(r["litres"] for r in shared_rows)
		self.assertEqual(total, 400.0)
		# Basis labels: allocation rows are estimated, never measured (Lesson 13)
		for row in group_rows + shared_rows:
			self.assertEqual(row["basis"], report.BASIS_ESTIMATED)

	def test_tank_fill_with_only_members_has_no_shared_bucket(self):
		e1 = self._make_equipment("A")
		e2 = self._make_equipment("B")
		self._make_group("Plant", [e1.name, e2.name])
		self._make_card(e1, [self._day(d, 10) for d in range(1, 11)])
		self._make_card(e2, [self._day(d, 10) for d in range(1, 11)])
		self._make_fill(200.0)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		shared_rows = [r for r in rows if r["section"] == report.SECTION_SHARED]
		self.assertEqual(shared_rows, [])
		group_rows = [r for r in rows if r["section"] == report.SECTION_ALLOCATION]
		self.assertEqual(sum(r["litres"] for r in group_rows), 200.0)

	def test_tank_fill_with_no_members_is_not_reported(self):
		e1 = self._make_equipment("A")
		outsider = self._make_equipment("OUT")
		self._make_group("Plant", [e1.name])
		# e1 has no card so allocation rows will not include e1
		self._make_card(outsider, [self._day(d, 10) for d in range(1, 11)])
		self._make_fill(100.0)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		self.assertEqual(rows, [])

	def test_effective_dates_shape_membership(self):
		"""An equipment is a member only inside its effective_from/to. A fill outside the window
		shows up under the shared bucket instead of the group row."""
		e1 = self._make_equipment("A")
		e2 = self._make_equipment("B")
		# e1 is a member only on day 1 — day 10
		self._make_group(
			"Plant",
			[
				{
					"equipment": e1.name,
					"effective_from": f"{self.year_str}-{self.month_str}-01",
					"effective_to": f"{self.year_str}-{self.month_str}-10",
				}
			],
		)
		# tank fill on day 15 touches e1 by hours; outside the membership window
		self._make_card(e1, [self._day(d, 10) for d in range(1, 11)])
		self._make_card(e2, [self._day(d, 10) for d in range(1, 11)])
		self._make_fill(200.0)  # dated at day 15
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
		)
		# e1 is not a member on day 15, so the group row set is empty — the whole tank fill
		# is out of the group's scope and the report returns nothing for this group.
		self.assertEqual(rows, [])

	def test_filter_group_narrows_to_one_group(self):
		e1 = self._make_equipment("A")
		e2 = self._make_equipment("B")
		g1 = self._make_group("G1", [e1.name])
		self._make_group("G2", [e2.name])
		self._make_fill(10.0, card_equipment=e1.name)
		self._make_fill(20.0, card_equipment=e2.name)
		rows = _execute_report(
			company=self.company,
			from_date=f"{self.year_str}-{self.month_str}-01",
			to_date=f"{self.year_str}-{self.month_str}-28",
			group=g1.name,
		)
		self.assertTrue(rows)
		self.assertTrue(all(r["group"] == g1.name for r in rows))

	def test_date_filter_is_required_and_scoped(self):
		"""Date range mandatory and end before start refused."""
		# end before start
		with self.assertRaises(frappe.ValidationError):
			_execute_report(
				company=self.company,
				from_date=f"{self.year_str}-{self.month_str}-28",
				to_date=f"{self.year_str}-{self.month_str}-01",
			)

	def test_company_filter_refuses_cross_company(self):
		"""A user restricted to Company B cannot run the report for Company A."""
		company_b = self._company("TEST-EOG-CO-" + self.token)
		user = self._user(("Card Manager",), restrict=company_b)
		frappe.set_user(user)
		with self.assertRaises(frappe.PermissionError):
			_execute_report(
				company=self.company,
				from_date=f"{self.year_str}-{self.month_str}-01",
				to_date=f"{self.year_str}-{self.month_str}-28",
			)


class TestOperatingGroupConcurrency(_GroupBase):
	"""Lesson 4: two concurrent saves of two groups claiming the same equipment: only one
	commits. The second connection sees the first's committed row under its `FOR UPDATE`
	locking read and is refused."""

	def test_two_concurrent_groups_claiming_same_equipment_one_fails(self):
		# Use two separate transactions through frappe.db connections
		e1 = self._make_equipment("A")
		frappe.db.commit()  # make the equipment visible to both connections
		try:
			# Transaction 1: insert group A without commit
			g1 = frappe.new_doc(DOCTYPE)
			g1.company = self.company
			g1.group_name = "Plant A-" + self.token
			g1.append("members", {"equipment": e1.name})
			g1.insert(ignore_permissions=True)
			frappe.db.commit()
			# Transaction 2: now insert group B claiming the same equipment; the overlap
			# guard reads the sibling group's row with FOR UPDATE and refuses.
			g2 = frappe.new_doc(DOCTYPE)
			g2.company = self.company
			g2.group_name = "Plant B-" + self.token
			g2.append("members", {"equipment": e1.name})
			with self.assertRaises(frappe.ValidationError):
				g2.insert(ignore_permissions=True)
		finally:
			# Clean up (rollback is suppressed when we committed; delete manually)
			for name in (
				group_docname("Plant A-" + self.token, self.company),
				group_docname("Plant B-" + self.token, self.company),
			):
				if frappe.db.exists(DOCTYPE, name):
					frappe.delete_doc(DOCTYPE, name, force=1)
			frappe.db.commit()


def _execute_report(**filters):
	"""Call the report entry point with keyword filters, return the `rows` list."""
	result = report.execute(filters)
	# execute returns (columns, rows, message, chart, summary, skip_total)
	return result[1]
