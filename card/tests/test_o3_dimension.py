# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""O3: the "Card Equipment" accounting dimension on official ERPNext documents.

Covers: the custom field reaching the GL-bearing doctypes, the automatic
Asset <-> equipment dimension sync, the depreciation path (the Asset's
dimension flows into the depreciation Journal Entry's GL), the official GL
report filtered by the dimension, and the "Equipment Expenses Without
Equipment" guard report. Everything skips cleanly on a site where the
dimension (a manual bench-execute step) or the Asset masters do not exist,
so fresh/demo benches stay green. All data is per-test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

from card.dimension import DIMENSION_FIELD, gl_has_dimension_field, has_dimension
from card.tests.test_controllers import _ensure_masters


class TestCardEquipmentDimension(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		if not has_dimension() or not gl_has_dimension_field():
			self.skipTest("Card Equipment accounting dimension is not set up on this site")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.cost_center = frappe.db.get_value("Company", self.company, "cost_center")

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- helpers ----
	def _equipment(self, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "ملك"
		d.equipment_name = "TEST-O3-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		for k, v in kw.items():
			d.set(k, v)
		d.insert(ignore_permissions=True)
		return d

	def _fixed_asset_masters(self):
		item = frappe.db.get_value("Item", {"is_fixed_asset": 1}, "name")
		location = frappe.db.get_value("Location", {"is_group": 0}, "name") or frappe.db.get_value(
			"Location", {}, "name"
		)
		if not item or not location:
			self.skipTest("No fixed-asset Item/Location masters on this site (O3 seed missing)")
		return item, location

	def _asset(self, depreciate=False):
		item, location = self._fixed_asset_masters()
		start = get_first_day(add_months(getdate(nowdate()), -1))
		a = frappe.new_doc("Asset")
		a.company = self.company
		a.item_code = item
		a.asset_name = "TEST-O3-ASSET-" + self.token
		a.location = location
		a.is_existing_asset = 1
		a.gross_purchase_amount = 120000
		a.net_purchase_amount = 120000  # v16 mandatory; purchase_amount derives from it
		a.asset_quantity = 1
		a.purchase_date = start
		a.available_for_use_date = start
		a.cost_center = self.cost_center
		if depreciate:
			a.calculate_depreciation = 1
			a.append(
				"finance_books",
				{
					"depreciation_method": "Straight Line",
					"frequency_of_depreciation": 1,
					"total_number_of_depreciations": 12,
					"depreciation_start_date": get_last_day(start),
				},
			)
		a.insert(ignore_permissions=True)
		return a

	# ---- 1. the dimension field reached the official doctypes ----
	def test_dimension_field_on_official_doctypes(self):
		for dt in ("GL Entry", "Journal Entry Account", "Purchase Invoice", "Sales Invoice", "Asset"):
			self.assertTrue(
				frappe.get_meta(dt).has_field(DIMENSION_FIELD),
				"missing {0} on {1}".format(DIMENSION_FIELD, dt),
			)
		dim = frappe.get_doc("Accounting Dimension", {"document_type": "Card Equipment"})
		for d in dim.dimension_defaults:
			self.assertFalse(d.mandatory_for_bs)
			self.assertFalse(d.mandatory_for_pl)

	# ---- 2. Asset <-> equipment dimension sync ----
	def test_asset_sync_on_link_and_relink(self):
		asset1 = self._asset()
		asset2 = self._asset()
		eq = self._equipment(**{"الأصل_في_erpnext": asset1.name})
		self.assertEqual(frappe.db.get_value("Asset", asset1.name, DIMENSION_FIELD), eq.name)
		# relink -> old asset cleared, new asset set
		eq.set("الأصل_في_erpnext", asset2.name)
		eq.save(ignore_permissions=True)
		self.assertFalse(frappe.db.get_value("Asset", asset1.name, DIMENSION_FIELD))
		self.assertEqual(frappe.db.get_value("Asset", asset2.name, DIMENSION_FIELD), eq.name)

	# ---- 3. depreciation path: the Asset's dimension flows into the JE GL ----
	def test_depreciation_gl_carries_equipment(self):
		from erpnext.assets.doctype.asset.depreciation import make_depreciation_entry

		asset = self._asset(depreciate=True)
		eq = self._equipment(**{"الأصل_في_erpnext": asset.name})
		asset.reload()
		self.assertEqual(asset.get(DIMENSION_FIELD), eq.name)
		asset.submit()

		schedule = frappe.db.get_value(
			"Asset Depreciation Schedule", {"asset": asset.name, "docstatus": 1}, "name"
		)
		self.assertTrue(schedule, "no depreciation schedule created on submit")
		first_row = frappe.get_all(
			"Depreciation Schedule",
			filters={"parent": schedule},
			fields=["name", "schedule_date"],
			order_by="idx asc",
			limit=1,
			parent_doctype="Asset Depreciation Schedule",
		)[0]
		make_depreciation_entry(schedule, str(first_row.schedule_date))

		je = frappe.db.get_value(
			"Depreciation Schedule", first_row.name, "journal_entry"
		)
		self.assertTrue(je, "depreciation journal entry was not created")
		gl_rows = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Journal Entry", "voucher_no": je, "is_cancelled": 0},
			fields=["account", "debit", "credit", DIMENSION_FIELD],
		)
		self.assertTrue(gl_rows)
		for g in gl_rows:
			self.assertEqual(g.get(DIMENSION_FIELD), eq.name, "GL row without the equipment dimension")

		# ---- the official GL report sees the dimension ----
		from erpnext.accounts.report.general_ledger.general_ledger import execute as gl_report

		filters = frappe._dict(
			{
				"company": self.company,
				"from_date": str(get_first_day(getdate(first_row.schedule_date))),
				"to_date": str(get_last_day(getdate(first_row.schedule_date))),
				"group_by": "Group by Voucher (Consolidated)",
				DIMENSION_FIELD: [eq.name],
			}
		)
		_cols, rows = gl_report(filters)
		vouchers = {r.get("voucher_no") for r in rows if isinstance(r, dict) and r.get("voucher_no")}
		self.assertIn(je, vouchers, "GL report filtered by the dimension misses the depreciation JE")

	# ---- 4. guard report: expense lines without the dimension ----
	def test_expenses_without_equipment_report(self):
		from card.card.report.equipment_expenses_without_equipment.equipment_expenses_without_equipment import (
			EXPENSE_ACCOUNT_FIELDS,
			execute,
		)

		row = frappe.db.get_value(
			"Card Company Settings",
			{"company": self.company},
			list(EXPENSE_ACCOUNT_FIELDS),
			as_dict=True,
		)
		accounts = [row.get(f) for f in EXPENSE_ACCOUNT_FIELDS if row and row.get(f)]
		if not accounts:
			self.skipTest("CARD expense accounts not configured for this company (O3 seed missing)")
		expense = accounts[0]
		cash = frappe.db.get_value("Account", {"account_type": "Cash", "is_group": 0, "company": self.company}, "name")
		eq = self._equipment()
		posting = get_first_day(add_months(getdate(nowdate()), -1))

		def make_je(with_equipment):
			je = frappe.new_doc("Journal Entry")
			je.company = self.company
			je.posting_date = posting
			je.append(
				"accounts",
				{
					"account": expense,
					"debit_in_account_currency": 100,
					"cost_center": self.cost_center,
					DIMENSION_FIELD: eq.name if with_equipment else None,
				},
			)
			je.append("accounts", {"account": cash, "credit_in_account_currency": 100})
			je.insert(ignore_permissions=True)
			je.submit()
			return je

		je_without = make_je(False)
		je_with = make_je(True)
		_cols, rows, _msg, _chart, summary, _flag = execute(
			{"company": self.company, "from_date": str(posting), "to_date": str(posting)}
		)
		listed = {r.voucher_no for r in rows}
		self.assertIn(je_without.name, listed)
		self.assertNotIn(je_with.name, listed)
		count = [s for s in summary if s["label"] == frappe._("Lines without equipment")][0]
		self.assertGreaterEqual(count["value"], 1)

	# ---- 5. first-run guard: no traceback without configuration ----
	def test_report_guard_messages(self):
		from card.card.report.equipment_expenses_without_equipment.equipment_expenses_without_equipment import (
			execute,
		)

		# unknown company row -> translated "configure" message, no crash
		comp = frappe.new_doc("Company")
		comp.company_name = "TEST-O3-NOCFG-" + self.token
		comp.abbr = "T" + self.token[:4]
		comp.default_currency = "SAR"
		comp.country = "Saudi Arabia"
		comp.insert(ignore_permissions=True)
		_cols, rows, msg, _chart, _summary, _flag = execute({"company": comp.name})
		self.assertEqual(rows, [])
		self.assertTrue(msg)
