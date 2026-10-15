# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3/P1: configured adjustment types (Card Settings) + typed, sided card
adjustment rows + the sided net split (supplier net vs customer_net_amount).

Legacy rows (no adjustment_type_ref, side backfilled Supplier) must keep the
exact v1.1 arithmetic — the stored-values baseline depends on it."""

import frappe
from frappe.utils import flt

from card.constants import DIR_RENTED_IN, DIR_RENTED_OUT, DIR_SUBRENTAL
from card.tests.test_customer import _CustomerCardsBase


def _expense_account(company):
	acc = frappe.db.get_value(
		"Account",
		{"company": company, "root_type": "Expense", "is_group": 0, "disabled": 0},
		"name",
	)
	if not acc:
		parent = frappe.db.get_value(
			"Account", {"company": company, "root_type": "Expense", "is_group": 1}, "name"
		)
		doc = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Test Adjustment Expense",
				"parent_account": parent,
				"company": company,
				"root_type": "Expense",
			}
		).insert(ignore_permissions=True)
		acc = doc.name
	return acc


def _group_account(company):
	return frappe.db.get_value("Account", {"company": company, "is_group": 1}, "name")


class _AdjBase(_CustomerCardsBase):
	def _clear_types(self):
		s = frappe.get_doc("Card Settings")
		s.set("adjustment_types", [])
		s.save(ignore_permissions=True)
		return s

	def _add_type(self, type_name, kind="خصم", account=None, taxable=1, disabled=0, company=None):
		s = frappe.get_doc("Card Settings")
		s.append(
			"adjustment_types",
			{
				"company": company or self.company,
				"type_name": type_name,
				"kind": kind,
				"account": account or _expense_account(company or self.company),
				"taxable": taxable,
				"disabled": disabled,
			},
		)
		s.save(ignore_permissions=True)
		return s


class TestAdjustmentTypeConfig(_AdjBase):
	def test_valid_type_row_saves(self):
		self._clear_types()
		s = self._add_type("Mobilization-" + self.token, kind="إضافة")
		row = s.adjustment_types[-1]
		self.assertEqual(row.kind, "إضافة")
		self.assertTrue(row.account)

	def test_duplicate_type_name_rejected(self):
		self._clear_types()
		self._add_type("Dup-" + self.token)
		with self.assertRaises(frappe.ValidationError):
			self._add_type("Dup-" + self.token)

	def test_group_account_rejected(self):
		self._clear_types()
		group = _group_account(self.company)
		self.assertTrue(group)
		with self.assertRaises(frappe.ValidationError):
			self._add_type("Grp-" + self.token, account=group)

	def test_tax_withholding_account_rejected(self):
		self._clear_types()
		acc = frappe.get_doc("Account", _expense_account(self.company))
		twh = frappe.get_doc(
			{
				"doctype": "Account",
				"account_name": "Test TWH " + self.token,
				"parent_account": acc.parent_account,
				"company": self.company,
				"root_type": "Expense",
				"is_tax_withholding_account": 1,
			}
		).insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			self._add_type("TWH-" + self.token, account=twh.name)


class TestAdjustmentSides(_AdjBase):
	def _typed_card(self, eq, rows, **presets):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for k, v in presets.items():
			setattr(c, k, v)
		from card.tests.test_controllers import _days

		for row in _days([8, 8]):
			c.append("days", row)
		for r in rows:
			c.append("adjustments", r)
		c.insert(ignore_permissions=True)
		c.reload()
		return c

	def test_side_defaults_supplier_on_rented_in(self):
		self._clear_types()
		eq = self._equipment(direction=DIR_RENTED_IN)
		c = self._typed_card(eq, [{"adjustment_type": "خصم", "description": "x", "amount": 100}])
		self.assertEqual(c.adjustments[0].side, "Supplier")

	def test_side_defaults_customer_on_rented_out(self):
		self._clear_types()
		eq = self._rented_out()
		c = self._typed_card(eq, [{"adjustment_type": "إضافة", "description": "x", "amount": 50}])
		self.assertEqual(c.adjustments[0].side, "Customer")

	def test_subrental_requires_explicit_side(self):
		self._clear_types()
		eq = self._sub_rental()
		with self.assertRaises(frappe.ValidationError):
			self._typed_card(eq, [{"adjustment_type": "خصم", "description": "x", "amount": 10}])

	def test_customer_side_needs_customer_for_typed_rows(self):
		self._clear_types()
		self._add_type("CustOnly-" + self.token, kind="إضافة")
		eq = self._equipment(direction=DIR_RENTED_IN)  # no customer anywhere
		with self.assertRaises(frappe.ValidationError):
			self._typed_card(
				eq,
				[
					{
						"adjustment_type_ref": "CustOnly-" + self.token,
						"side": "Customer",
						"description": "x",
						"amount": 10,
					}
				],
			)

	def test_unknown_or_disabled_type_ref_rejected(self):
		self._clear_types()
		eq = self._equipment(direction=DIR_RENTED_IN)
		with self.assertRaises(frappe.ValidationError):
			self._typed_card(
				eq,
				[{"adjustment_type_ref": "NoSuchType-" + self.token, "description": "x", "amount": 10}],
			)
		self._add_type("Off-" + self.token, disabled=1)
		with self.assertRaises(frappe.ValidationError):
			self._typed_card(
				eq, [{"adjustment_type_ref": "Off-" + self.token, "description": "x", "amount": 10}]
			)

	def test_kind_mirrors_type_on_typed_rows(self):
		self._clear_types()
		self._add_type("Mob-" + self.token, kind="إضافة")
		eq = self._equipment(direction=DIR_RENTED_IN)
		c = self._typed_card(
			eq,
			[
				{
					"adjustment_type_ref": "Mob-" + self.token,
					"adjustment_type": "خصم",  # wrong on purpose: the type's kind must win
					"description": "x",
					"amount": 40,
				}
			],
		)
		self.assertEqual(c.adjustments[0].adjustment_type, "إضافة")


class TestSidedNets(_AdjBase):
	def test_legacy_rows_keep_supplier_net_formula(self):
		self._clear_types()
		eq = self._equipment(direction=DIR_RENTED_IN)  # 750/day over 10h = 75/h
		c = TestAdjustmentSides._typed_card(
			self,
			eq,
			[
				{"adjustment_type": "إضافة", "description": "a", "amount": 200},
				{"adjustment_type": "خصم", "description": "d", "amount": 50},
			],
		)
		# 16h * 75 = 1200; net = 1200 + 200 - 50
		self.assertEqual(flt(c.amount), 1200.0)
		self.assertEqual(flt(c.net_amount), 1350.0)
		self.assertEqual(flt(c.customer_net_amount), 0.0)

	def test_customer_rows_feed_customer_net_only(self):
		self._clear_types()
		self._add_type("CMob-" + self.token, kind="إضافة")
		eq = self._rented_out(customer_rate=1000)  # 100/h
		c = TestAdjustmentSides._typed_card(
			self,
			eq,
			[
				{
					"adjustment_type_ref": "CMob-" + self.token,
					"side": "Customer",
					"description": "c",
					"amount": 300,
				}
			],
		)
		# 16h * 100 = 1600 customer_amount; customer_net = 1600 + 300
		self.assertEqual(flt(c.amount), 0.0)
		self.assertEqual(flt(c.net_amount), 0.0)
		self.assertEqual(flt(c.customer_amount), 1600.0)
		self.assertEqual(flt(c.customer_net_amount), 1900.0)

	def test_subrental_mixed_sides_split(self):
		self._clear_types()
		self._add_type("SupDed-" + self.token, kind="خصم")
		self._add_type("CustAdd-" + self.token, kind="إضافة")
		eq = self._sub_rental(customer_rate=1200)  # supplier 75/h, customer 120/h
		c = TestAdjustmentSides._typed_card(
			self,
			eq,
			[
				{
					"adjustment_type_ref": "SupDed-" + self.token,
					"side": "Supplier",
					"description": "s",
					"amount": 100,
				},
				{
					"adjustment_type_ref": "CustAdd-" + self.token,
					"side": "Customer",
					"description": "c",
					"amount": 250,
				},
			],
		)
		self.assertEqual(flt(c.amount), 1200.0)  # 16h * 75
		self.assertEqual(flt(c.net_amount), 1100.0)  # supplier side only
		self.assertEqual(flt(c.customer_amount), 1920.0)  # 16h * 120
		self.assertEqual(flt(c.customer_net_amount), 2170.0)  # customer side only

	def test_backfill_patch_sets_supplier_side(self):
		self._clear_types()
		eq = self._equipment(direction=DIR_RENTED_IN)
		c = TestAdjustmentSides._typed_card(
			self, eq, [{"adjustment_type": "خصم", "description": "old", "amount": 10}]
		)
		frappe.db.set_value(
			"Card Monthly Card Adjustment", c.adjustments[0].name, "side", "", update_modified=False
		)
		from card.patches.v1_2.backfill_adjustment_side import execute

		execute()
		execute()  # idempotent
		self.assertEqual(
			frappe.db.get_value("Card Monthly Card Adjustment", c.adjustments[0].name, "side"),
			"Supplier",
		)
