# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-172: the Additions & deductions table of the Monthly Card works end to end.

- The grid shows the required Adjustment date column, also to users who saved their own columns
  before v4.10.0 (patch v4_10_1.show_adjustment_date_in_saved_grid_columns).
- Additions and deductions change the total of their side on every save: supplier side ->
  net_amount (Purchase Invoice), customer side -> customer_net_amount (Sales Invoice).
- The server is the authority: amounts must be positive, dates inside the card period, and a
  submitted card cannot be changed.
- Saving and submitting a card creates no Journal Entry, GL Entry or Payment Ledger Entry.
All data is per-test and rolled back."""

import json

import frappe
from frappe.model.utils.user_settings import clear_user_settings_cache

from card.card.doctype.card_monthly_card.card_monthly_card import configured_adjustment_types
from card.patches.v4_10_1.show_adjustment_date_in_saved_grid_columns import (
	CHILD,
	PARENT,
	add_date_column,
)
from card.patches.v4_10_1.show_adjustment_date_in_saved_grid_columns import (
	execute as run_grid_patch,
)
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase
from card.tests.test_s3_config import _AdjBase

ADD, DED = "إضافة", "خصم"
LEDGERS = ("Journal Entry", "GL Entry", "Payment Ledger Entry", "Purchase Invoice", "Sales Invoice")


def _row(kind, amount, description, side=None, date="2026-09-01"):
	row = {"adjustment_date": date, "adjustment_type": kind, "amount": amount, "description": description}
	if side:
		row["side"] = side
	return row


class TestAdjustmentGridConfig(_CustomerCardsBase):
	def test_date_column_is_a_required_list_view_date_field(self):
		meta = frappe.get_meta(CHILD)
		f = meta.get_field("adjustment_date")
		self.assertEqual((f.fieldtype, f.reqd, f.in_list_view, f.hidden), ("Date", 1, 1, 0))
		listed = [d.fieldname for d in meta.fields if d.in_list_view]
		self.assertEqual(listed[:5], ["adjustment_date", "adjustment_type", "description", "side", "amount"])

	def test_type_amount_and_description_are_required(self):
		meta = frappe.get_meta(CHILD)
		self.assertEqual(meta.get_field("adjustment_type").options.split("\n"), [ADD, DED])
		self.assertTrue(meta.get_field("amount").reqd and meta.get_field("amount").non_negative)
		self.assertTrue(meta.get_field("description").reqd)


SAVED_COLUMNS = ({"fieldname": "side", "width": 140, "sticky": 0}, {"fieldname": "amount", "width": 100})


class TestSavedGridColumnsPatch(_CustomerCardsBase):
	def test_date_column_is_put_first_and_the_rest_is_kept(self):
		data = {"GridView": {CHILD: list(SAVED_COLUMNS)}, "last_view": "Form"}
		out = add_date_column(data)
		self.assertEqual(out["GridView"][CHILD][0]["fieldname"], "adjustment_date")
		self.assertEqual(out["GridView"][CHILD][1:], list(SAVED_COLUMNS))
		self.assertEqual(out["last_view"], "Form")

	def test_nothing_changes_without_saved_columns_or_with_the_date(self):
		self.assertIsNone(add_date_column({}))
		self.assertIsNone(add_date_column({"GridView": {"Card Monthly Card Day": [{"fieldname": "x"}]}}))
		self.assertIsNone(add_date_column({"GridView": {CHILD: [{"fieldname": "adjustment_date"}]}}))
		self.assertIsNone(add_date_column("corrupt"))

	def test_date_column_goes_after_pinned_columns(self):
		pinned = {"fieldname": "side", "width": 140, "sticky": 1}
		out = add_date_column({"GridView": {CHILD: [pinned, {"fieldname": "amount", "sticky": 0}]}})
		self.assertEqual(
			[c["fieldname"] for c in out["GridView"][CHILD]], ["side", "adjustment_date", "amount"]
		)

	def test_patch_updates_saved_settings_once(self):
		user = "Administrator"
		# a cached copy of this user's settings would be synced over the test row by the patch
		clear_user_settings_cache(PARENT)
		frappe.db.sql("delete from `__UserSettings` where `user`=%s and `doctype`=%s", (user, PARENT))
		frappe.db.sql(
			"insert into `__UserSettings` (`user`, `doctype`, `data`) values (%s, %s, %s)",
			(user, PARENT, json.dumps({"GridView": {CHILD: list(SAVED_COLUMNS)}})),
		)
		run_grid_patch()
		first = frappe.db.sql(
			"select data from `__UserSettings` where `user`=%s and `doctype`=%s", (user, PARENT)
		)[0][0]
		cols = json.loads(first)["GridView"][CHILD]
		self.assertEqual([c["fieldname"] for c in cols], ["adjustment_date", "side", "amount"])
		run_grid_patch()  # idempotent: a second migrate changes nothing
		second = frappe.db.sql(
			"select data from `__UserSettings` where `user`=%s and `doctype`=%s", (user, PARENT)
		)[0][0]
		self.assertEqual(json.loads(second), json.loads(first))


class TestAdjustmentEffects(_CustomerCardsBase):
	"""Sub-rental card: supplier 75/h, customer 120/h, 48 h -> amounts 3,600 / 5,760."""

	def _card(self, rows, eq=None):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = (eq or self._sub_rental()).name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days([10, 10, 10, 10, 8]):
			c.append("days", row)
		for row in rows:
			c.append("adjustments", row)
		c.insert(ignore_permissions=True)
		return c

	def _figures(self, c):
		return (c.total_additions, c.total_deductions, c.net_amount, c.customer_net_amount)

	def test_multiple_rows_on_both_sides(self):
		c = self._card(
			[
				_row(ADD, 100, "S overtime", "Supplier"),
				_row(DED, 40, "S fuel", "Supplier"),
				_row(ADD, 300, "C standby", "Customer"),
				_row(DED, 60, "C damage", "Customer"),
			]
		)
		self.assertEqual((c.amount, c.customer_amount), (3600, 5760))
		# net = base + additions - deductions, per side
		self.assertEqual(self._figures(c), (400, 100, 3600 + 100 - 40, 5760 + 300 - 60))

	def test_rented_out_card_rows_default_to_the_customer_side(self):
		c = self._card([_row(ADD, 500, "C extra"), _row(DED, 200, "C discount")], eq=self._rented_out())
		self.assertEqual([r.side for r in c.adjustments], ["Customer", "Customer"])
		self.assertEqual(c.net_amount, 0)  # owned equipment: no supplier amount
		self.assertEqual(c.customer_net_amount, flt_sum(c.customer_amount, 500, -200))

	def test_editing_and_deleting_rows_recalculates(self):
		c = self._card([_row(ADD, 100, "S1", "Supplier"), _row(DED, 50, "S2", "Supplier")])
		self.assertEqual(c.net_amount, 3650)
		c.adjustments[0].amount = 250
		c.save(ignore_permissions=True)
		self.assertEqual((c.total_additions, c.net_amount), (250, 3800))
		c.remove(c.adjustments[1])
		c.save(ignore_permissions=True)
		self.assertEqual((c.total_deductions, c.net_amount), (0, 3850))
		c.adjustments[0].adjustment_type = DED
		c.save(ignore_permissions=True)
		self.assertEqual((c.total_additions, c.total_deductions, c.net_amount), (0, 250, 3350))

	def test_currency_rounding(self):
		# 10.10 + 20.20 is 30.299999... in binary floating point; the stored totals are rounded to 2 places
		c = self._card([_row(ADD, 10.10, "S r1", "Supplier"), _row(ADD, 20.20, "S r2", "Supplier")])
		self.assertEqual(c.total_additions, 30.3)
		self.assertEqual(c.net_amount, 3630.3)

	def test_zero_and_negative_amounts_are_refused(self):
		for bad in (0, -10):
			with self.assertRaises(frappe.ValidationError):
				self._card([_row(ADD, bad, "bad", "Supplier")])

	def test_dates_outside_the_period_are_refused(self):
		for bad in ("2026-08-31", "2026-10-01"):
			with self.assertRaises(frappe.ValidationError):
				self._card([_row(ADD, 10, "bad date", "Supplier", date=bad)])
		with self.assertRaises(frappe.ValidationError):
			self._card([_row(ADD, 10, "no date", "Supplier", date=None)])

	def test_sub_rental_row_needs_its_side(self):
		with self.assertRaises(frappe.ValidationError):
			self._card([_row(ADD, 10, "no side")])

	def test_submitted_card_rows_cannot_change(self):
		c = self._card([_row(ADD, 100, "S1", "Supplier")])
		c.submit()
		c.reload()
		c.adjustments[0].amount = 999
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			c.save(ignore_permissions=True)
		c.reload()
		c.append("adjustments", _row(ADD, 5, "late", "Supplier"))
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			c.save(ignore_permissions=True)

	def test_save_and_submit_post_nothing(self):
		before = {dt: frappe.db.count(dt) for dt in LEDGERS}
		c = self._card([_row(ADD, 100, "S1", "Supplier"), _row(DED, 30, "C1", "Customer")])
		c.adjustments[0].amount = 120
		c.save(ignore_permissions=True)
		c.submit()
		self.assertEqual({dt: frappe.db.count(dt) for dt in LEDGERS}, before)


class TestDraftSaveWithAdjustments(_CustomerCardsBase):
	"""The refused save seen on Production on 2026-11-20 (a Draft supplier card, HTTP 417 on save). A dry run
	of that card's validation (writes blocked) showed: valid dated additions and deductions pass; the reachable
	refusals are a free-text Adjustment type that is not configured in Card Settings and a date outside the
	card period. These tests keep both: valid rows save; each refusal says how to fix it."""

	def _draft(self, rows):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = self._equipment().name  # rented from a supplier, as the Production card
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days([10, 10, 10, 10, 8]):
			c.append("days", row)
		for row in rows:
			c.append("adjustments", row)
		c.insert(ignore_permissions=True)
		return c

	def test_draft_with_addition_and_deduction_saves(self):
		c = self._draft(
			[_row(ADD, 100, "overtime", date="2026-09-30"), _row(DED, 40, "fuel", date="2026-09-01")]
		)
		self.assertEqual(c.docstatus, 0)
		self.assertEqual((c.total_additions, c.total_deductions, c.net_amount), (100, 40, 3660))
		self.assertEqual([r.side for r in c.adjustments], ["Supplier", "Supplier"])
		c.append("adjustments", _row(ADD, 10, "later row", date="2026-09-15"))
		c.save(ignore_permissions=True)
		self.assertEqual(c.net_amount, 3670)

	def test_free_text_adjustment_type_is_refused_with_the_way_out(self):
		unknown = "TEST-UNCONFIGURED-" + self.token
		row = _row(DED, 40, "fuel", date="2026-09-05")
		row["adjustment_type_ref"] = unknown
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._draft([row])
		self.assertIn(unknown, str(ctx.exception))
		self.assertIn("clear the Adjustment type", str(ctx.exception))
		row["adjustment_type_ref"] = None  # what the message asks: the same row then saves
		self.assertEqual(self._draft([row]).total_deductions, 40)

	def test_date_outside_the_period_names_the_period(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			self._draft([_row(ADD, 10, "late", date="2026-10-01")])
		self.assertIn("2026-09-01", str(ctx.exception))
		self.assertIn("2026-09-30", str(ctx.exception))


def flt_sum(*values):
	return frappe.utils.flt(sum(frappe.utils.flt(v) for v in values), 2)


class TestOptionalClassification(_AdjBase):
	"""FR-173: the optional Adjustment type (`adjustment_type_ref`) never blocks a plain row. Production on
	2026-11-21: no type configured, the user's saved columns showed the free-text Adjustment type next to Type,
	and a value typed there refused the save. The form now shows that field only when the card's company has
	types (or a row already has one); the server keeps refusing an unconfigured value that is sent."""

	def setUp(self):
		super().setUp()
		self._clear_types()

	def _draft(self, rows=()):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = self._equipment().name  # rented from a supplier
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days([10, 10, 10, 10, 8]):
			c.append("days", row)
		for row in rows:
			c.append("adjustments", row)
		c.insert(ignore_permissions=True)
		return c

	def _onload_types(self, card):
		card.run_onload()
		return card.get_onload().get("adjustment_types")

	def test_no_type_configured_form_gets_an_empty_list(self):
		self.assertEqual(self._onload_types(self._draft()), [])

	def test_onload_lists_the_enabled_types_of_the_card_company_only(self):
		self._add_type("Fuel-" + self.token, kind=DED)
		self._add_type("Old-" + self.token, kind=DED, disabled=1)
		card = self._draft()
		self.assertEqual(self._onload_types(card), ["Fuel-" + self.token])
		self.assertEqual(configured_adjustment_types(None), [])
		self.assertEqual(configured_adjustment_types("TEST-NO-SUCH-COMPANY-" + self.token), [])

	def test_plain_rows_save_without_classification(self):
		c = self._draft(
			[_row(ADD, 100, "overtime", date="2026-09-10"), _row(DED, 40, "fuel", date="2026-09-11")]
		)
		self.assertEqual([r.adjustment_type_ref for r in c.adjustments], [None, None])
		self.assertEqual((c.total_additions, c.total_deductions, c.net_amount), (100, 40, 3660))

	def test_configured_classification_saves_and_is_kept(self):
		name = "Fuel-" + self.token
		self._add_type(name, kind=DED)
		row = _row(ADD, 40, "fuel", date="2026-09-05")
		row["adjustment_type_ref"] = name
		c = self._draft([row])
		# the type sets the kind (a deduction) and the classification stays on the row
		self.assertEqual(
			(c.adjustments[0].adjustment_type_ref, c.adjustments[0].adjustment_type), (name, DED)
		)
		c.save(ignore_permissions=True)
		c.reload()
		self.assertEqual(c.adjustments[0].adjustment_type_ref, name)

	def test_unconfigured_classification_is_refused_and_the_card_is_unchanged(self):
		c = self._draft()
		row = _row(DED, 40, "fuel", date="2026-09-05")
		row["adjustment_type_ref"] = (
			DED  # what was typed on Production: the word "deduction" in the free-text field
		)
		c.append("adjustments", row)
		with self.assertRaises(frappe.ValidationError) as ctx:
			c.save(ignore_permissions=True)
		self.assertIn("clear the Adjustment type", str(ctx.exception))
		self.assertEqual(frappe.db.count("Card Monthly Card Adjustment", {"parent": c.name}), 0)
		c.reload()
		c.append(
			"adjustments", _row(DED, 40, "fuel", date="2026-09-05")
		)  # the same row without the classification
		c.save(ignore_permissions=True)
		self.assertEqual((len(c.adjustments), c.total_deductions), (1, 40))

	def test_saved_grid_columns_do_not_affect_the_server(self):
		# a saved column list that shows the classification changes nothing on the server: a row without it saves
		frappe.db.sql(
			"delete from `__UserSettings` where `user`=%s and `doctype`=%s", ("Administrator", PARENT)
		)
		cols = [
			{"fieldname": f}
			for f in ("adjustment_date", "adjustment_type_ref", "side", "adjustment_type", "amount")
		]
		frappe.db.sql(
			"insert into `__UserSettings` (`user`, `doctype`, `data`) values (%s, %s, %s)",
			("Administrator", PARENT, json.dumps({"GridView": {CHILD: cols}})),
		)
		c = self._draft([_row(ADD, 25, "standby", date="2026-09-20")])
		self.assertEqual(c.total_additions, 25)
