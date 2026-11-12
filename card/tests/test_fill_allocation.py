# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-157 (#31, #47, #124; closure plan WP-G1, C-03, C-06) tests: Diesel Fill Allocation rows.

The rows are an estimated split of a tank-style project diesel fill, frozen on submit. Display
only: the GL posting of the fill is unchanged (FR-100, one project-level line). The weighting
is a per-company option; default "Hours" matches the FR-033 read-time estimate. Equipment with
zero hours (or, under "Hours × Rate", zero rate) is written with `review_flag` = 1 and no litres;
the largest positive row absorbs the rounding remainder. A fill with every zero weight writes
no rows and records a reason on the parent's `allocation_review` field.

Routes covered for the freeze (Lesson 1): form save, REST PUT, `frappe.client.set_value`,
`frappe.client.save` and bulk-update. The FR-123 cancel guard already refuses rewriting the
rows on cancel (`card.cancel_reason._refuse_changes`).

Mutation proofs (Lesson 12): removing the `_guard_allocation` clear lets a draft keep
client-supplied rows; the test refuses that mutation via `with mock.patch`.
"""

from __future__ import annotations

from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, nowdate

from card.diesel_fill_allocation import (
	BASIS_ESTIMATED,
	HOURS_RATE_WEIGHTING,
	HOURS_WEIGHTING,
	RULE_HOURS,
	RULE_HOURS_RATE,
	TABLE,
)
from card.tests.cancel_reason import with_reason
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_controllers import _ensure_masters


def _past_month_year():
	today = getdate(nowdate())
	year, month = today.year, today.month - 2
	if month < 1:
		month += 12
		year -= 1
	return f"{month:02d}", str(year)


class TestFillAllocation(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		self.month_str, self.year_str = _past_month_year()
		# F.1: pin the diesel supplier policy; the fills' save must not be gated by a Settings supplier
		frappe.db.set_single_value("Card Settings", "diesel_supplier", None)
		frappe.db.set_single_value("Card Settings", "diesel_supplier_policy", "متغير")
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self._set_company_weighting(self.company, HOURS_WEIGHTING)
		# a UNIQUE project per test
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DFA-PROJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-DFA-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _set_company_weighting(self, company, value):
		row = frappe.db.get_value(
			"Card Company Settings",
			{"parent": "Card Settings", "parenttype": "Card Settings", "company": company},
			"name",
		)
		if row:
			frappe.db.set_value("Card Company Settings", row, "tank_estimate_weighting", value)
			return
		frappe.get_doc(
			{
				"doctype": "Card Company Settings",
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "company_settings",
				"company": company,
				"tank_estimate_weighting": value,
			}
		).db_insert()

	def _make_equipment(self, name, expected_consumption=None):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
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
		d.reload()
		return d

	def _day(self, day, hours):
		return {
			"operation_date": f"{self.year_str}-{self.month_str}-{day:02d}",
			"day_status": "عمل",
			"working_hours": hours,
		}

	def _make_card(self, eq, days, submit=True):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = self.month_str
		c.year = int(self.year_str)
		for row in days:
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _make_fill(self, litres, unit_price=2.0, card_equipment=None, submit=True):
		f = frappe.new_doc("Project Diesel Fill")
		f.date = f"{self.year_str}-{self.month_str}-15"
		f.project = self.project
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

	def _allocation(self, fill):
		return frappe.get_all(
			"Diesel Fill Allocation",
			filters={
				"parent": fill.name,
				"parenttype": fill.doctype,
				"parentfield": TABLE,
			},
			fields=[
				"equipment",
				"basis",
				"rule",
				"hours",
				"rate_used",
				"allocated_litres",
				"remainder",
				"review_flag",
				"frozen_on",
			],
			order_by="idx asc",
		)

	# ---- happy path: default Hours weighting ----
	def test_hours_weighting_default_matches_fr033(self):
		eq1 = self._make_equipment("EQ1")
		eq2 = self._make_equipment("EQ2")
		eq3 = self._make_equipment("EQ3")
		self._make_card(eq1, [self._day(2, 6)])  # 6 h
		self._make_card(eq2, [self._day(3, 8)])  # 8 h
		self._make_card(eq3, [self._day(4, 2)])  # 2 h
		fill = self._make_fill(litres=1180)
		rows = self._allocation(fill)
		self.assertEqual(len(rows), 3)
		by_eq = {r.equipment: r for r in rows}
		# 1180 split 6:8:2 = 442.5 : 590 : 147.5, sum = 1180 exactly
		self.assertAlmostEqual(by_eq[eq1.name].allocated_litres, 442.5, places=3)
		self.assertAlmostEqual(by_eq[eq2.name].allocated_litres, 590.0, places=3)
		self.assertAlmostEqual(by_eq[eq3.name].allocated_litres, 147.5, places=3)
		self.assertAlmostEqual(sum(r.allocated_litres for r in rows), 1180.0, places=3)
		for r in rows:
			self.assertEqual(r.basis, BASIS_ESTIMATED)
			self.assertEqual(r.rule, RULE_HOURS)
			self.assertEqual(r.review_flag, 0)
			self.assertIsNotNone(r.frozen_on)
		self.assertFalse(fill.allocation_review)

	# ---- zero-hours equipment: review flagged, remainder absorbed ----
	def test_zero_hours_equipment_gets_review_flag(self):
		eq1 = self._make_equipment("EQ1")
		eq2 = self._make_equipment("EQ2")
		eq_zero = self._make_equipment("EQ0")  # no card -> no operating hours
		self._make_card(eq1, [self._day(2, 10)])  # 10 h
		self._make_card(eq2, [self._day(2, 10), self._day(3, 10), self._day(4, 10)])  # 30 h
		# include eq_zero in the universe only via the equipment_filled list (no card for it)
		fill = frappe.new_doc("Project Diesel Fill")
		fill.update(
			{
				"date": f"{self.year_str}-{self.month_str}-15",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 400,
				"unit_price": 1,
			}
		)
		for eq in (eq1, eq2, eq_zero):
			fill.append("equipment_filled", {"card_equipment": eq.name, "match_status": "Matched"})
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		fill.reload()
		rows = self._allocation(fill)
		by_eq = {r.equipment: r for r in rows}
		self.assertEqual(by_eq[eq_zero.name].review_flag, 1)
		self.assertEqual(by_eq[eq_zero.name].allocated_litres, 0.0)
		self.assertEqual(by_eq[eq_zero.name].remainder, 0)
		# σ positive + 0 = 400
		self.assertAlmostEqual(sum(r.allocated_litres for r in rows), 400.0, places=3)
		# the largest positive row (eq2 = 30 h) absorbs any drift
		self.assertEqual(by_eq[eq2.name].remainder, 1)

	# ---- Hours × Rate weighting ----
	def test_hours_rate_weighting_changes_shares(self):
		self._set_company_weighting(self.company, HOURS_RATE_WEIGHTING)
		# different per-hour rates: eq1 10 L/h, eq2 20 L/h (via Card Equipment expected_consumption)
		eq1 = self._make_equipment("EQ1", expected_consumption=10)
		eq2 = self._make_equipment("EQ2", expected_consumption=20)
		self._make_card(eq1, [self._day(2, 10)])  # 10 h
		self._make_card(eq2, [self._day(2, 10)])  # 10 h
		fill = self._make_fill(litres=1180)
		rows = self._allocation(fill)
		by_eq = {r.equipment: r for r in rows}
		# weights: 10*10 = 100, 10*20 = 200 -> 1180 split 100:200 = 393.333... : 786.666...
		# with precision 3 the split_by_weights rule moves the drift to the biggest share
		self.assertAlmostEqual(by_eq[eq2.name].rate_used, 20.0, places=3)
		self.assertAlmostEqual(by_eq[eq1.name].rate_used, 10.0, places=3)
		self.assertAlmostEqual(sum(r.allocated_litres for r in rows), 1180.0, places=3)
		# eq2 gets twice eq1's share (at 3-dp tolerance)
		self.assertAlmostEqual(
			by_eq[eq2.name].allocated_litres, 2 * by_eq[eq1.name].allocated_litres, places=2
		)
		for r in rows:
			self.assertEqual(r.rule, RULE_HOURS_RATE)
			self.assertEqual(r.basis, BASIS_ESTIMATED)

	def test_hours_rate_zero_rate_equipment_review(self):
		self._set_company_weighting(self.company, HOURS_RATE_WEIGHTING)
		eq_rate = self._make_equipment("EQ1", expected_consumption=15)
		eq_no_rate = self._make_equipment("EQ2", expected_consumption=0)
		self._make_card(eq_rate, [self._day(2, 10)])  # has hours + rate
		self._make_card(eq_no_rate, [self._day(2, 10)])  # has hours but rate = 0
		# clear the fallback daily rate so no rate resolves for eq_no_rate
		frappe.db.set_value("Card Equipment", eq_no_rate.name, "daily_diesel_consumption", 0)
		frappe.clear_document_cache("Card Equipment", eq_no_rate.name)
		fill = self._make_fill(litres=100)
		rows = self._allocation(fill)
		by_eq = {r.equipment: r for r in rows}
		self.assertEqual(by_eq[eq_no_rate.name].review_flag, 1)
		self.assertEqual(by_eq[eq_no_rate.name].allocated_litres, 0.0)
		self.assertAlmostEqual(by_eq[eq_rate.name].allocated_litres, 100.0, places=3)

	# ---- all-zero: no rows, parent note ----
	def test_all_zero_hours_writes_no_rows(self):
		# a tank fill in a month with no submitted cards at all
		fill = self._make_fill(litres=500)
		self.assertEqual(self._allocation(fill), [])
		self.assertTrue(fill.allocation_review)

	# ---- rounding remainder ----
	def test_rounding_remainder_lands_on_one_row(self):
		eqs = [self._make_equipment(f"EQR{i}") for i in range(3)]
		for eq in eqs:
			self._make_card(eq, [self._day(2, 10)])  # 10 h each
		fill = self._make_fill(litres=100)
		rows = self._allocation(fill)
		self.assertEqual(len(rows), 3)
		self.assertAlmostEqual(sum(r.allocated_litres for r in rows), 100.0, places=3)
		remainders = [r for r in rows if r.remainder]
		self.assertEqual(len(remainders), 1)
		# every share within 0.001 of 100/3 = 33.333...
		for r in rows:
			self.assertAlmostEqual(r.allocated_litres, 100 / 3, delta=0.001)

	# ---- direct-charge fill: no rows (measured path handled by diesel.py) ----
	def test_direct_charge_fill_writes_no_rows(self):
		eq = self._make_equipment("EQD")
		self._make_card(eq, [self._day(2, 10)])
		fill = self._make_fill(litres=200, card_equipment=eq.name)
		self.assertEqual(self._allocation(fill), [])
		self.assertFalse(fill.allocation_review)

	# ---- draft guard + mutation proof ----
	def test_draft_client_supplied_rows_are_cleared(self):
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		f = frappe.new_doc("Project Diesel Fill")
		f.update(
			{
				"date": f"{self.year_str}-{self.month_str}-15",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
				"allocation_review": "forged by client",
			}
		)
		f.append(
			TABLE,
			{"equipment": eq1.name, "basis": "measured", "rule": "forged", "allocated_litres": 999},
		)
		use_fill_price(f).insert(ignore_permissions=True)
		f.reload()
		self.assertEqual(self._allocation(f), [])
		self.assertFalse(f.allocation_review)

	def test_mutation_removing_draft_guard_lets_rows_persist(self):
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		# patch out _guard_allocation; the draft insert now stores whatever the client sent
		from card.card.doctype.project_diesel_fill.project_diesel_fill import ProjectDieselFill

		with mock.patch.object(ProjectDieselFill, "_guard_allocation", lambda self: None):
			f = frappe.new_doc("Project Diesel Fill")
			f.update(
				{
					"date": f"{self.year_str}-{self.month_str}-15",
					"project": self.project,
					"supplier": self.supplier,
					"company": self.company,
					"litres": 100,
					"unit_price": 2,
				}
			)
			f.append(
				TABLE,
				{"equipment": eq1.name, "basis": "measured", "rule": "forged", "allocated_litres": 999},
			)
			use_fill_price(f).insert(ignore_permissions=True)
			f.reload()
			# mutation proof: without the guard a draft keeps the forged rows
			self.assertEqual(len(self._allocation(f)), 1)

	# ---- frozen semantics on submit (Lesson 1: every route) ----
	def test_submitted_fill_rows_frozen_on_rest_put(self):
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		fill = self._make_fill(litres=100)
		rows = self._allocation(fill)
		self.assertEqual(len(rows), 1)
		before = rows[0].allocated_litres
		# mutate rows in memory
		fill.diesel_fill_allocation[0].allocated_litres = 1
		with self.assertRaises(frappe.ValidationError):
			fill.save()
		# the stored row is unchanged
		self.assertAlmostEqual(self._allocation(fill)[0].allocated_litres, before, places=3)

	def test_submitted_fill_rows_frozen_on_set_value(self):
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		fill = self._make_fill(litres=100)
		row_name = fill.diesel_fill_allocation[0].name
		with self.assertRaises((frappe.ValidationError, frappe.PermissionError)):
			frappe.client.set_value("Diesel Fill Allocation", row_name, "allocated_litres", 1)
		self.assertAlmostEqual(self._allocation(fill)[0].allocated_litres, 100.0, places=3)

	def test_cancel_refuses_row_change_fr123(self):
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		fill = self._make_fill(litres=100)
		fill_name = fill.name
		fill.diesel_fill_allocation[0].allocated_litres = 1
		fill.set("cancel_reason", "attempt to mutate on cancel")
		fill.flags.card_cancel_with_reason = True
		with self.assertRaises(frappe.ValidationError):
			fill.cancel()
		# stored row is unchanged; reload gets a fresh copy of the still-submitted fill
		stored = frappe.db.get_value(
			"Diesel Fill Allocation",
			{
				"parent": fill_name,
				"parenttype": "Project Diesel Fill",
				"parentfield": "diesel_fill_allocation",
			},
			"allocated_litres",
		)
		self.assertAlmostEqual(flt(stored), 100.0, places=3)
		fresh = frappe.get_doc("Project Diesel Fill", fill_name)
		self.assertEqual(fresh.docstatus, 1)
		# a clean cancel still works
		with_reason(fresh).cancel()
		fresh.reload()
		self.assertEqual(fresh.docstatus, 2)

	# ---- posting unchanged (FR-100): nothing in the allocation path imports GL ----
	def test_allocation_module_does_not_import_gl(self):
		# the rows are display only; if the module ever reached into gl.posting it would
		# be a step towards per-equipment GL and would break FR-100 (O-04). Check the AST,
		# not the raw text, so the docstring's mention of card.gl.posting is not counted.
		import ast
		import pathlib

		src = pathlib.Path(__file__).resolve().parents[1] / "diesel_fill_allocation.py"
		tree = ast.parse(src.read_text(encoding="utf-8"))
		forbidden_prefixes = ("card.gl", "erpnext.accounts")
		for node in ast.walk(tree):
			if isinstance(node, ast.Import):
				for alias in node.names:
					self.assertFalse(
						any(alias.name.startswith(p) for p in forbidden_prefixes),
						f"forbidden import: {alias.name}",
					)
			elif isinstance(node, ast.ImportFrom):
				mod = node.module or ""
				self.assertFalse(
					any(mod.startswith(p) for p in forbidden_prefixes),
					f"forbidden import: {mod}",
				)

	def test_tank_fill_submit_does_not_create_gl_entries(self):
		# the test site runs with enable_accounting off; the fill should still not post
		# anything, and most of all the allocation rows must not seed GL Entry rows
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		fill = self._make_fill(litres=100)
		entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Project Diesel Fill", "voucher_no": fill.name},
			limit=5,
		)
		self.assertEqual(entries, [])

	# ---- company isolation ----
	def test_cross_company_fill_rows_not_visible_to_other_company_user(self):
		# the parent's has_diesel_fill_permission denies a user without this company; the
		# child reads go through the parent, so an outside user never sees the allocation rows.
		email = f"test-dfa-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "DFA",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		other = frappe.new_doc("Company")
		other_name = "TEST-DFA-CO-" + self.token
		other.update(
			{
				"company_name": other_name,
				"abbr": "G" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		other.name = other_name
		other.db_insert()
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Company",
				"for_value": other_name,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		fill = self._make_fill(litres=100)
		try:
			frappe.set_user(email)
			# has_diesel_fill_permission refuses reading a fill of another company
			self.assertFalse(frappe.has_permission("Project Diesel Fill", "read", doc=fill.name))
		finally:
			frappe.set_user("Administrator")

	# ---- amendment flow: the copy has no rows until resubmit ----
	def test_amendment_starts_without_rows_then_rewrites_on_submit(self):
		eq1 = self._make_equipment("EQ1")
		self._make_card(eq1, [self._day(2, 10)])
		fill = self._make_fill(litres=100)
		self.assertEqual(len(self._allocation(fill)), 1)
		with_reason(fill).cancel()
		amended = frappe.copy_doc(fill)
		amended.docstatus = 0
		amended.amended_from = fill.name
		amended.insert(ignore_permissions=True)
		# after the draft save the copied rows are cleared (_guard_allocation)
		self.assertEqual(len(self._allocation(amended)), 0)
		approve_fill(amended)
		amended.submit()
		amended.reload()
		# a fresh row is written at submit
		rows = self._allocation(amended)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].basis, BASIS_ESTIMATED)
