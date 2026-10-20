# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Card Settings layout (Owner 2026-10-20): the simplified tabs keep every field, permission and value.
The baseline is Card Settings on main @ e2ed5b0, before the layout change."""

import frappe
from frappe.tests import IntegrationTestCase

# fieldname: [fieldtype, options, permlevel, default, reqd]
BASELINE_FIELDS = {
	"enable_accounting": ["Check", None, 2, "0", 0],
	"auto_submit": ["Check", None, 2, "0", 0],
	"company_settings": ["Table", "Card Company Settings", 0, None, 0],
	"default_shift": ["Select", "نهاري\nليلي", 2, "نهاري", 0],
	"max_day_shift_hours": ["Float", None, 2, "12", 0],
	"max_night_shift_hours": ["Float", None, 2, "12", 0],
	"default_daily_hours": ["Float", None, 2, "0", 0],
	"default_fuel_charged_to": ["Select", "\nالمؤجر\nالشركة", 2, None, 0],
	"default_operator_on": ["Select", "\nالمؤجر\nالشركة", 2, None, 0],
	"reconciliation_tolerance": ["Currency", None, 2, "0.01", 0],
	"warn_on_shift_hours_exceeded": ["Check", None, 2, "1", 0],
	"warn_outside_rental_period": ["Check", None, 2, "1", 0],
	"default_statement_type": ["Select", "مورد\nمعدات ملك", 2, "مورد", 0],
	"include_draft_in_reports": ["Check", None, 2, "0", 0],
	"period_lock_date": ["Date", None, 2, None, 0],
	"period_lock_override_role": ["Link", "Role", 2, None, 0],
	"notify_on_card_submit": ["Check", None, 2, "0", 0],
	"notify_on_posting": ["Check", None, 2, "0", 0],
	"notify_on_period_lock_override": ["Check", None, 2, "0", 0],
	"default_rate_basis": ["Select", "\nباليوم\nبالساعة\nبالشهر", 2, None, 0],
	"standard_month_hours": ["Float", None, 2, "260", 0],
	"sync_equipment_location_daily": ["Check", None, 2, "0", 0],
	"diesel_supplier_policy": ["Select", "ثابت\nمتغير", 2, "متغير", 0],
	"diesel_supplier": ["Link", "Supplier", 2, None, 0],
	"diesel_supplier_editor_role": ["Link", "Role", 2, "Card Manager", 0],
	"diesel_price_exception_role": ["Link", "Role", 2, "Accounts Manager", 0],
	"diesel_zero_price_role": ["Link", "Role", 2, None, 0],
	"transport_price_editor_role": ["Link", "Role", 2, "Card Manager", 0],
	"project_transport_prices": ["Table", "Card Project Transport Price", 2, None, 0],
	"adjustment_types": ["Table", "Card Adjustment Type", 0, None, 0],
	"location_cost_centers": ["Table", "Card Location Cost Center", 2, None, 0],
	"default_store_warehouse": ["Link", "Warehouse", 0, None, 0],
	"tool_custody_warehouse": ["Link", "Warehouse", 0, None, 0],
	"repeat_request_days": ["Int", None, 0, "30", 0],
}

# [role, permlevel, read, write, create, delete]
BASELINE_PERMS = [
	["Accounts Manager", 0, 1, 1, 0, 0],
	["Accounts Manager", 1, 1, 1, 0, 0],
	["Accounts Manager", 2, 1, 0, 0, 0],
	["Card Manager", 0, 1, 0, 0, 0],
	["Card Manager", 2, 1, 0, 0, 0],
	["System Manager", 0, 1, 1, 1, 0],
	["System Manager", 1, 1, 1, 0, 0],
	["System Manager", 2, 1, 1, 0, 0],
]

# the tab every moved field must sit under
MOVED = {
	"diesel_supplier_policy": "diesel_transport_tab",
	"diesel_supplier": "diesel_transport_tab",
	"project_transport_prices": "transport_tab",
	"location_cost_centers": "warehouse_cost_center_tab",
	"adjustment_types": "accounting_tab",
	"diesel_supplier_editor_role": "advanced_permissions_tab",
	"diesel_price_exception_role": "advanced_permissions_tab",
	"diesel_zero_price_role": "advanced_permissions_tab",
	"transport_price_editor_role": "advanced_permissions_tab",
}


class TestCardSettingsLayout(IntegrationTestCase):
	def setUp(self):
		self.meta = frappe.get_meta("Card Settings")

	def _tab_of(self):
		tab, tabs = None, {}
		for df in self.meta.fields:
			if df.fieldtype == "Tab Break":
				tab = df.fieldname
			tabs[df.fieldname] = tab
		return tabs

	def test_every_field_is_kept_unchanged(self):
		for fieldname, (fieldtype, options, permlevel, default, reqd) in BASELINE_FIELDS.items():
			df = self.meta.get_field(fieldname)
			self.assertIsNotNone(df, fieldname)
			self.assertEqual(
				(df.fieldtype, df.options or None, df.permlevel or 0, df.default or None, df.reqd or 0),
				(fieldtype, options, permlevel, default, reqd),
				fieldname,
			)

	def test_permissions_unchanged(self):
		perms = sorted(
			[p.role, p.permlevel or 0, p.read or 0, p.write or 0, p.create or 0, p.delete or 0]
			for p in self.meta.permissions
		)
		self.assertEqual(perms, BASELINE_PERMS)

	def test_moved_fields_sit_in_their_tabs(self):
		tabs = self._tab_of()
		for fieldname, tab in MOVED.items():
			self.assertEqual(tabs[fieldname], tab, fieldname)

	def test_diesel_settings_top_and_main_section(self):
		order = [df.fieldname for df in self.meta.fields]
		start = order.index("diesel_transport_tab")
		end = order.index("transport_tab")
		data = [
			f
			for f in order[start + 1 : end]
			if self.meta.get_field(f).fieldtype not in ("Section Break", "Column Break")
		]
		self.assertEqual(data, ["diesel_price_html", "diesel_supplier_policy", "diesel_supplier"])
		self.assertEqual(self.meta.get_field("diesel_price_html").fieldtype, "HTML")  # display only
		self.assertFalse(self.meta.get_field("diesel_supplier_policy").description)  # no field help

	def test_price_stays_on_the_company_row(self):
		self.assertIsNone(self.meta.get_field("diesel_unit_price"))  # no second price source
		df = frappe.get_meta("Card Company Settings").get_field("diesel_unit_price")
		self.assertEqual((df.fieldtype, df.permlevel), ("Currency", 1))
		self.assertFalse(df.description)  # no field help (Owner 2026-10-19)
