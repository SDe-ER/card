# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-135 (#50, #126): main store, tool custody store and the repeated-request window per company.

A company's row in Card Settings > Company settings wins; an empty value falls back to the site-wide
Card Settings value, so a company without the new values behaves exactly as before. A warehouse on a
company row must belong to that company."""

import frappe
from frappe.utils import add_days, nowdate

from card import materials, settings
from card.tests import test_v4_materials as v4


class TestCompanyWarehouses(v4.TestV4Materials):
	"""Reuses the v4 materials builders; only the tests below run (the inherited ones are removed at
	the end of this module)."""

	def setUp(self):
		super().setUp()
		self.company_store = self._warehouse("store")
		self.company_custody = self._warehouse("custody")
		self.row = self._company_row()

	# ---------- builders ----------
	def _warehouse(self, label):
		parent = frappe.db.get_value("Warehouse", self.store, "parent_warehouse")
		doc = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": f"FR135 {label} {self.token}",
				"company": self.company,
				"parent_warehouse": parent,
			}
		)
		try:
			doc.insert(ignore_permissions=True)
		except frappe.ValidationError as e:
			self.skipTest(f"warehouses cannot be made on this site: {e}")
		return doc.name

	def _company_row(self):
		name = frappe.db.get_value(
			"Card Company Settings",
			{"parent": "Card Settings", "parentfield": "company_settings", "company": self.company},
		)
		if name:
			return name
		row = frappe.get_doc(
			{
				"doctype": "Card Company Settings",
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "company_settings",
				"company": self.company,
				"idx": 99,
			}
		)
		row.db_insert()
		return row.name

	def _set_row(self, **values):
		frappe.db.set_value("Card Company Settings", self.row, values, update_modified=False)

	def _row_doc(self, company, **values):
		return frappe._dict(company_settings=[frappe._dict(company=company, **values)])

	# ---------- defaults: the site value when the company has none ----------
	def test_empty_company_values_fall_back_to_the_site_values(self):
		self._set_row(store_warehouse=None, custody_warehouse=None, repeat_request_days=0)
		self.assertEqual(settings.store_warehouse(self.company), self.store)
		self.assertEqual(settings.custody_warehouse(self.company), self.custody)
		self.assertEqual(settings.repeat_request_days(self.company), 30)
		frappe.db.set_single_value("Card Settings", "repeat_request_days", 12)
		self.assertEqual(settings.repeat_request_days(self.company), 12)
		self.assertEqual(materials.repeat_days(self.company), 12)

	def test_a_company_without_a_row_and_no_company_use_the_site_values(self):
		other = self._other_company()
		for company in (other, None, ""):
			with self.subTest(company=company):
				self.assertEqual(settings.store_warehouse(company), self.store)
				self.assertEqual(settings.custody_warehouse(company), self.custody)
				self.assertEqual(settings.repeat_request_days(company), 30)

	def test_nothing_configured_anywhere_stays_empty_and_30_days(self):
		self._set_row(store_warehouse=None, custody_warehouse=None, repeat_request_days=0)
		frappe.db.set_single_value("Card Settings", "default_store_warehouse", None)
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", None)
		frappe.db.set_single_value("Card Settings", "repeat_request_days", None)
		self.assertIsNone(settings.store_warehouse(self.company))
		self.assertIsNone(settings.custody_warehouse(self.company))
		self.assertEqual(settings.repeat_request_days(self.company), 30)

	# ---------- the company value wins ----------
	def test_company_values_win_over_the_site_values(self):
		self._set_row(
			store_warehouse=self.company_store, custody_warehouse=self.company_custody, repeat_request_days=7
		)
		self.assertEqual(settings.store_warehouse(self.company), self.company_store)
		self.assertEqual(settings.custody_warehouse(self.company), self.company_custody)
		self.assertEqual(settings.repeat_request_days(self.company), 7)
		# another company keeps the site values
		self.assertEqual(settings.store_warehouse(self._other_company()), self.store)

	def test_the_repeat_window_of_the_machines_company_flags_requests(self):
		self._set_row(repeat_request_days=3)
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		self.assertIsNotNone(materials.last_asked_on(self.eq, self.filter))
		old = frappe.get_all(
			"Equipment Needs Request", filters={"equipment": self.eq}, pluck="name", limit=1
		)[0]
		frappe.db.set_value("Equipment Needs Request", old, "request_date", add_days(nowdate(), -5))
		# 5 days ago is outside the company's 3 days, inside the site's 30
		self.assertIsNone(materials.last_asked_on(self.eq, self.filter))
		self._set_row(repeat_request_days=0)
		self.assertIsNotNone(materials.last_asked_on(self.eq, self.filter))

	def test_a_review_pulls_lines_with_the_companys_store(self):
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		self._set_row(store_warehouse=self.company_store)
		review = self._review()
		self.assertEqual({row.warehouse for row in review.items}, {self.company_store})

	def test_a_review_without_a_company_store_pulls_the_site_store(self):
		self._set_row(store_warehouse=None)
		self._ask([{"kind": "Part", "item_code": self.filter, "qty": 1}])
		review = self._review()
		self.assertEqual({row.warehouse for row in review.items}, {self.store})

	def test_tool_approval_accepts_a_company_custody_store_without_a_site_one(self):
		self._ask([{"kind": "Tool", "item_code": self.tool, "qty": 1}])
		review = self._review()
		review.submit()
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", None)
		self._set_row(custody_warehouse=self.company_custody)
		self._approve(review.name)
		self.assertEqual(
			frappe.db.get_value("Equipment Needs Review", review.name, "approval_status"), "Approved"
		)

	def test_custody_moves_through_the_companys_custody_store(self):
		self._set_row(custody_warehouse=self.company_custody)
		hand = self._custody("Handover", qty=2, warehouse=self.store)
		entry = frappe.get_doc("Stock Entry", hand.stock_entry)
		self.assertEqual(
			(entry.items[0].s_warehouse, entry.items[0].t_warehouse), (self.store, self.company_custody)
		)
		back = self._custody("Return", qty=1, warehouse=self.store)
		entry = frappe.get_doc("Stock Entry", back.stock_entry)
		self.assertEqual(
			(entry.items[0].s_warehouse, entry.items[0].t_warehouse), (self.company_custody, self.store)
		)

	def test_custody_without_a_company_store_uses_the_site_store(self):
		self._set_row(custody_warehouse=None)
		hand = self._custody("Handover", qty=1, warehouse=self.store)
		self.assertEqual(
			frappe.db.get_value("Stock Entry Detail", {"parent": hand.stock_entry}, "t_warehouse"),
			self.custody,
		)

	def test_a_company_custody_store_is_enough_for_a_stock_move(self):
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", None)
		with self.assertRaises(frappe.ValidationError):
			self._custody("Handover", warehouse=self.store, submit=False)
		self._set_row(custody_warehouse=self.company_custody)
		self.assertTrue(self._custody("Handover", warehouse=self.store, submit=False).name)

	def test_the_screen_offers_each_companys_store(self):
		self._set_row(store_warehouse=self.company_store)
		ctx = self._screen("Administrator", "context")
		self.assertEqual(ctx["default_store"], self.store)  # unchanged site value
		self.assertEqual(ctx["default_stores"].get(self.company), self.company_store)
		made = self._screen(
			"Administrator", "move", movement="Handover", employee=self.operator, item_code=self.tool, qty=1
		)
		self.assertEqual(
			frappe.db.get_value("Employee Tool Custody", made["name"], "warehouse"), self.company_store
		)

	# ---------- a company warehouse belongs to its company ----------
	def test_a_warehouse_of_another_company_is_refused(self):
		other = self._other_company()
		foreign = self._other_warehouse(other)
		for fieldname in settings.COMPANY_WAREHOUSE_FIELDS:
			with self.subTest(field=fieldname):
				with self.assertRaises(frappe.ValidationError) as refused:
					settings.validate_company_warehouses(self._row_doc(self.company, **{fieldname: foreign}))
				self.assertIn(foreign, str(refused.exception))

	def test_own_or_empty_warehouses_are_accepted(self):
		settings.validate_company_warehouses(
			self._row_doc(
				self.company, store_warehouse=self.company_store, custody_warehouse=self.company_custody
			)
		)
		settings.validate_company_warehouses(self._row_doc(self.company))
		settings.validate_company_warehouses(frappe._dict())

	def test_a_foreign_company_warehouse_is_refused_at_read_time(self):
		# stored before the save check (or moved since): the readers refuse it, the screen does not offer it
		foreign = self._other_warehouse(self._other_company())
		self._set_row(store_warehouse=foreign, custody_warehouse=foreign)
		for reader in (settings.store_warehouse, settings.custody_warehouse):
			with self.subTest(reader=reader.__name__):
				with self.assertRaises(frappe.ValidationError) as refused:
					reader(self.company)
				self.assertIn(foreign, str(refused.exception))
				self.assertIsNone(reader(self.company, strict=False))
		self.assertIsNone(self._screen("Administrator", "context")["default_stores"].get(self.company))
		with self.assertRaises(frappe.ValidationError):
			self._custody("Handover", warehouse=self.store, submit=False)

	def test_card_settings_save_refuses_a_foreign_company_warehouse(self):
		foreign = self._other_warehouse(self._other_company())
		doc = frappe.get_doc("Card Settings")
		row = next(r for r in doc.company_settings if r.company == self.company)
		row.store_warehouse = foreign
		with self.assertRaises(frappe.ValidationError) as refused:
			doc.save()
		self.assertIn(foreign, str(refused.exception))

	# ---------- schema and labels ----------
	def test_new_fields_are_optional_and_empty_by_default(self):
		meta = frappe.get_meta("Card Company Settings")
		for fieldname, fieldtype in (
			("store_warehouse", "Link"),
			("custody_warehouse", "Link"),
			("repeat_request_days", "Int"),
		):
			with self.subTest(field=fieldname):
				field = meta.get_field(fieldname)
				self.assertEqual(field.fieldtype, fieldtype)
				self.assertFalse(field.reqd)
				self.assertFalse(field.default)
		self.assertEqual(meta.get_field("store_warehouse").options, "Warehouse")
		self.assertEqual(meta.get_field("custody_warehouse").options, "Warehouse")

	def test_no_label_names_a_fixed_vat_rate(self):
		# FR-127: the rate comes from the company's tax templates; only the 0% template is fixed
		for doctype in ("Card Company Settings", "Card Settings"):
			for field in frappe.get_meta(doctype).fields:
				if field.fieldname == "vat_zero_item_tax_template":
					continue
				with self.subTest(doctype=doctype, field=field.fieldname):
					self.assertNotIn("15%", (field.label or "") + (field.description or ""))


# only the FR-135 tests run in this module; the inherited v4 tests run in their own module
for _name in dir(v4.TestV4Materials):
	if _name.startswith("test_") and _name not in TestCompanyWarehouses.__dict__:
		setattr(TestCompanyWarehouses, _name, None)
