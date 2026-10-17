# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Wiring tests for Card Settings -> equipment defaults and report behaviour
(app-level so Frappe does not auto-build dependency test records). Each test
proves that changing the setting changes behaviour AND that the baseline
value reproduces the pre-settings behaviour. Setting writes and all records
are rolled back by the test transaction."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.constants import DIR_RENTED_OUT
from card.settings import setting
from card.tests.test_controllers import _days, _ensure_masters

FUEL_FIELD = "الوقود_على"
LESSOR = "المؤجر"
COMPANY = "الشركة"
OWNED = "ملك"
SUPPLIER_STATEMENT = "مورد"
OWNED_STATEMENT = "معدات ملك"


def _set(field, value):
	frappe.db.set_single_value("Card Settings", field, value)
	# flipping single values mid-test: drop any cached single value so the next
	# setting() read is fresh (production rarely re-reads within one request).
	frappe.clear_document_cache("Card Settings", "Card Settings")


def _statement(filters):
	from card.card.report.equipment_supplier_statement.equipment_supplier_statement import execute

	columns, rows, message, _chart, summary, _flag = execute(filters)
	return columns, rows, message, summary


def _summary_report(filters):
	from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute

	columns, rows, message, _chart, summary, _flag = execute(filters)
	return columns, rows, message, summary


def _indicator(summary, label):
	for item in summary:
		if item["label"] == frappe._(label):
			return item["indicator"]
	return None


class TestCardSettingsWiring(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.etype = self._m["etype"]
		# A project of its own so report assertions are not polluted by other site data.
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		frappe.db.rollback()

	# ---------- helpers ----------

	def _equipment(self, name_suffix="", ownership="إيجار"):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self.etype
		d.ownership = ownership
		d.equipment_name = "TEST-EQ-" + self.token + name_suffix
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		if ownership != OWNED:
			d.supplier = self.supplier
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _card(self, eq, hours_list, submit=False, shift="نهاري"):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = shift
		c.month = "09"
		c.year = 2026
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	def _statement_filters(self, **kw):
		f = {"from_month": 9, "from_year": 2026, "project": self.project}
		f.update(kw)
		return f

	# ---------- 1. equipment new-record defaults ----------

	def test_equipment_defaults_from_settings(self):
		_set("default_daily_hours", 8)
		_set("default_fuel_charged_to", COMPANY)
		_set("default_operator_on", COMPANY)

		def make(**kw):
			d = frappe.new_doc("Card Equipment")
			d.company = self.company
			d.equipment_type = self.etype
			d.ownership = "إيجار"
			d.supplier = self.supplier
			# F.7: a rented direction requires the supplier rate on the equipment
			d.rate_type = "باليوم"
			d.rate = 750
			d.equipment_name = "TEST-EQ-" + frappe.generate_hash(length=8)
			for key, value in kw.items():
				d.set(key, value)
			d.insert(ignore_permissions=True)
			d.reload()
			return d

		# daily_hours / fuel / operator_on left blank -> defaulted from settings.
		# operator_on no longer carries a hardcoded DocType default, so the
		# Card Settings value governs a new record.
		eq = make()
		self.assertEqual(flt(eq.daily_hours), 8.0)
		self.assertEqual(eq.get(FUEL_FIELD), COMPANY)
		self.assertEqual(eq.operator_on, COMPANY)

		# a provided value is never overridden
		eq2 = make(daily_hours=5, operator_on=LESSOR, **{FUEL_FIELD: LESSOR})
		self.assertEqual(flt(eq2.daily_hours), 5.0)
		self.assertEqual(eq2.operator_on, LESSOR)
		self.assertEqual(eq2.get(FUEL_FIELD), LESSOR)

		# existing (not new) equipment is untouched when settings change later
		_set("default_daily_hours", 12)
		_set("default_fuel_charged_to", LESSOR)
		_set("default_operator_on", LESSOR)
		eq.save(ignore_permissions=True)
		eq.reload()
		self.assertEqual(flt(eq.daily_hours), 8.0)
		self.assertEqual(eq.get(FUEL_FIELD), COMPANY)
		self.assertEqual(eq.operator_on, COMPANY)

		# baseline (0 / blank) reproduces current behaviour: no daily_hours default,
		# so the mandatory field still rejects an empty value.
		_set("default_daily_hours", 0)
		_set("default_fuel_charged_to", "")
		_set("default_operator_on", "")
		with self.assertRaises(frappe.ValidationError):
			make()
		eq4 = make(daily_hours=7)
		self.assertFalse(eq4.get(FUEL_FIELD))
		self.assertFalse(eq4.operator_on)  # no hardcoded default; blank setting -> stays empty

	# ---------- 2a. statement_type default ----------

	def test_statement_type_default_from_settings(self):
		eq = self._equipment(ownership=OWNED)
		card = self._card(eq, [10, 10, 10], submit=True)

		# baseline: "مورد" with no supplier -> empty statement (no rows), supplier-style columns
		_set("default_statement_type", SUPPLIER_STATEMENT)
		cols_default, rows_default, _msg, _summary = _statement(self._statement_filters())
		self.assertEqual(rows_default, [])

		# setting -> owned-equipment branch: our owned card is listed, fewer columns (no money columns)
		_set("default_statement_type", OWNED_STATEMENT)
		cols_owned, rows_owned, _msg, _summary = _statement(self._statement_filters())
		self.assertIn(card.name, [r.get("card") for r in rows_owned])
		self.assertLess(len(cols_owned), len(cols_default))

		# an explicit filter still wins over the setting
		_cols, rows_explicit, _msg, _summary = _statement(
			self._statement_filters(statement_type=SUPPLIER_STATEMENT)
		)
		self.assertEqual(rows_explicit, [])

	# ---------- 2b. include_draft default ----------

	def test_include_draft_default_from_settings(self):
		submitted = self._card(self._equipment("-A"), [10, 10], submit=True)
		draft = self._card(self._equipment("-B"), [10, 10], submit=False)
		self.assertEqual(draft.docstatus, 0)

		def card_names(**kw):
			filters = self._statement_filters(supplier=self.supplier, statement_type=SUPPLIER_STATEMENT, **kw)
			_cols, rows, _msg, _summary = _statement(filters)
			return [r.get("card") for r in rows]

		# baseline (0): draft excluded when the filter is not provided
		_set("include_draft_in_reports", 0)
		names = card_names()
		self.assertIn(submitted.name, names)
		self.assertNotIn(draft.name, names)

		# setting on: draft included when the filter is not provided
		_set("include_draft_in_reports", 1)
		names = card_names()
		self.assertIn(submitted.name, names)
		self.assertIn(draft.name, names)

		# an explicitly provided filter wins over the setting
		self.assertNotIn(draft.name, card_names(include_draft=0))
		_set("include_draft_in_reports", 0)
		self.assertIn(draft.name, card_names(include_draft=1))

	# ---------- 2c. reconciliation tolerance ----------

	def test_reconciliation_tolerance_from_settings(self):
		# A submitted card with NO supplier GL entries: net cards > 0, accrual = 0, so the
		# reconciliation difference is large (2,250). The report exposes the flag as the
		# "indicator" of the summary item labelled "Not invoiced through Card"
		# (Green = within tolerance, Red = over tolerance); that is what is asserted.
		# The summary report is limited to this test's own project so other data cannot
		# offset the total difference.
		self._card(self._equipment(), [10, 10, 10], submit=True)

		# default reproduces the old hardcoded 0.01 when the setting is unset
		frappe.db.delete("Singles", {"doctype": "Card Settings", "field": "reconciliation_tolerance"})
		self.assertEqual(flt(setting("reconciliation_tolerance")), 0.01)

		label = "Not invoiced through Card"
		statement_filters = self._statement_filters(supplier=self.supplier, statement_type=SUPPLIER_STATEMENT)
		summary_filters = {"from_month": 9, "from_year": 2026, "project": self.project}

		# baseline tolerance (0.01): the large difference IS flagged in both reports
		_set("reconciliation_tolerance", 0.01)
		self.assertEqual(_indicator(_statement(statement_filters)[3], label), "Red")
		self.assertEqual(_indicator(_summary_report(summary_filters)[3], label), "Red")

		# huge tolerance: nothing is flagged (kept below the Currency column limit)
		_set("reconciliation_tolerance", 1000000000)
		self.assertEqual(_indicator(_statement(statement_filters)[3], label), "Green")
		self.assertEqual(_indicator(_summary_report(summary_filters)[3], label), "Green")

	# ---------- 3. empty operator_on / الوقود_على handled where read ----------

	def test_empty_fuel_company_bears(self):
		from card.diesel import get_card_diesel

		eq = self._equipment()
		card = self._card(eq, [10, 10], submit=True)
		# empty fuel -> the company does not bear the diesel (no crash)
		frappe.db.set_value("Card Equipment", eq.name, "الوقود_على", "")
		self.assertFalse(get_card_diesel(card.name)["company_bears"])
		# المؤجر (the restored default) also means the company does not bear it
		frappe.db.set_value("Card Equipment", eq.name, "الوقود_على", "المؤجر")
		self.assertFalse(get_card_diesel(card.name)["company_bears"])
		# الشركة -> company bears
		frappe.db.set_value("Card Equipment", eq.name, "الوقود_على", "الشركة")
		self.assertTrue(get_card_diesel(card.name)["company_bears"])

	# ---------- 4. per-shift hour limits are ADVISORY (warn, never block) ----------
	# Owner 2026-10-14: every recorded hour is billed; a day over the shift limit
	# is flagged for review (orange warning) but must still save AND submit.

	def _shift_messages(self):
		return " | ".join(str(m.get("message", "")) for m in frappe.get_message_log())

	def test_day_shift_over_limit_warns_not_blocks(self):
		_set("max_day_shift_hours", 12)
		frappe.local.message_log = []
		card = self._card(self._equipment("-D13"), [13])  # 13 > 12: must NOT raise
		self.assertEqual(flt(card.total_working_hours), 13.0)  # every hour recorded/billed
		self.assertIn("13", self._shift_messages())  # a warning was shown
		card.submit()  # never blocked on submit either
		card.reload()
		self.assertEqual(card.docstatus, 1)
		# a day within the limit saves with no shift-limit warning
		self.assertEqual(flt(self._card(self._equipment("-D12"), [12]).total_working_hours), 12.0)

	def test_night_over_limit_warns_not_blocks(self):
		_set("max_day_shift_hours", 12)
		_set("max_night_shift_hours", 8)
		# a 10h night day exceeds the night limit (8) but still saves and submits
		card = self._card(self._equipment("-N10"), [10], shift="ليلي")
		self.assertEqual(flt(card.total_working_hours), 10.0)
		card.submit()
		card.reload()
		self.assertEqual(card.docstatus, 1)
		# the same 10h on a day-shift card is within the day limit (12) -> also fine
		self.assertEqual(flt(self._card(self._equipment("-D10"), [10]).total_working_hours), 10.0)

	def test_over_shift_limit_is_billed(self):
		# the over-limit hours flow into the billed amount (rented equipment: 750/day over 10h = 75/h)
		_set("max_day_shift_hours", 12)
		card = self._card(self._equipment("-BILL"), [13], submit=True)
		self.assertEqual(flt(card.total_working_hours), 13.0)
		self.assertEqual(flt(card.net_amount), flt(13 * (750.0 / 10.0), 2))  # 975.0

	def test_shift_limits_default_to_12_when_unset(self):
		frappe.db.delete(
			"Singles",
			{"doctype": "Card Settings", "field": ("in", ("max_day_shift_hours", "max_night_shift_hours"))},
		)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.assertEqual(setting("max_day_shift_hours"), 12.0)
		self.assertEqual(setting("max_night_shift_hours"), 12.0)
		# over the default limit: warns, still saves (never raises) on both shifts
		self.assertEqual(flt(self._card(self._equipment("-U13"), [13]).total_working_hours), 13.0)
		self.assertEqual(
			flt(self._card(self._equipment("-U13N"), [13], shift="ليلي").total_working_hours), 13.0
		)
		self._card(self._equipment("-U12"), [12])
		self._card(self._equipment("-U12N"), [12], shift="ليلي")


# =====================================================================
# F-phase settings (F.1 diesel/transport policies, F.5 bases, F.8 company)
# =====================================================================


def _leaf(doctype, name_field, root):
	"""A non-group row of a tree master (Customer needs leaf group/territory)."""
	leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if leaf:
		return leaf
	leaf = "Test " + doctype
	if not frappe.db.exists(doctype, leaf):
		frappe.get_doc(
			{"doctype": doctype, name_field: leaf, "parent_" + frappe.scrub(doctype): root, "is_group": 0}
		).insert(ignore_permissions=True)
	return leaf


def _role_user(*roles):
	"""A throwaway user carrying exactly the given roles, for the F.1 role gates.
	Callers switch with frappe.set_user and MUST restore Administrator in finally."""
	u = frappe.new_doc("User")
	u.email = "test-wiring-" + frappe.generate_hash(length=8) + "@example.com"
	u.first_name = "Test Wiring User"
	u.send_welcome_email = 0
	for role in roles:
		u.append("roles", {"role": role})
	u.flags.ignore_permissions = True
	u.insert(ignore_permissions=True)
	return u.name


class TestDieselSupplierPolicy(IntegrationTestCase):
	"""F.1: the Settings diesel supplier is the default (متغير) or forced (ثابت);
	changing it away from the default needs the editor role (Administrator is
	exempt under متغير, nobody is exempt under ثابت); a historical fill resaved
	with its supplier unchanged always passes."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-F1D-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.default_supplier = self._supplier("-DEF")
		self.other_supplier = self._supplier("-OTH")
		_set("diesel_supplier", self.default_supplier)
		_set("diesel_supplier_policy", "متغير")

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _supplier(self, suffix):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-F1D-SUP-" + self.token + suffix
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _fill(self, supplier=None):
		f = frappe.new_doc("Project Diesel Fill")
		f.date = "2026-09-15"
		f.project = self.project
		f.company = self.company
		f.litres = 100
		f.unit_price = 2
		if supplier:
			f.supplier = supplier
		f.insert(ignore_permissions=True)
		f.reload()
		return f

	# ---------- متغير (variable) ----------

	def test_variable_policy_defaults_blank_supplier(self):
		self.assertEqual(self._fill().supplier, self.default_supplier)

	def test_variable_policy_administrator_changes_freely(self):
		self.assertEqual(self._fill(supplier=self.other_supplier).supplier, self.other_supplier)

	def test_variable_policy_blocks_user_without_role(self):
		user = _role_user("Card User")
		try:
			frappe.set_user(user)
			with self.assertRaises(frappe.ValidationError):
				self._fill(supplier=self.other_supplier)
		finally:
			frappe.set_user("Administrator")

	def test_variable_policy_allows_default_editor_role(self):
		# the editor role falls back to "Card Manager" when never configured
		frappe.db.delete("Singles", {"doctype": "Card Settings", "field": "diesel_supplier_editor_role"})
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.assertEqual(setting("diesel_supplier_editor_role"), "Card Manager")
		user = _role_user("Card User", "Card Manager")
		try:
			frappe.set_user(user)
			f = self._fill(supplier=self.other_supplier)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(f.supplier, self.other_supplier)

	# ---------- ثابت (fixed) ----------

	def test_fixed_policy_blocks_any_change(self):
		_set("diesel_supplier_policy", "ثابت")
		with self.assertRaises(frappe.ValidationError):
			self._fill(supplier=self.other_supplier)  # even as Administrator

	def test_fixed_policy_forces_blank_supplier(self):
		_set("diesel_supplier_policy", "ثابت")
		self.assertEqual(self._fill().supplier, self.default_supplier)

	def test_legacy_fill_resaved_unchanged_passes(self):
		# built while the policy allows the historical supplier...
		f = self._fill(supplier=self.other_supplier)
		# ...then the policy is locked down: a resave that does NOT touch the
		# supplier must still pass (historical data keeps saving)
		_set("diesel_supplier_policy", "ثابت")
		f.remarks = "legacy resave"
		f.save(ignore_permissions=True)
		f.reload()
		self.assertEqual(f.supplier, self.other_supplier)


class TestTransportPricePolicy(IntegrationTestCase):
	"""F.1: the per-project transport price table defaults the amount; overriding
	a configured price needs the editor role (default "Card Manager", Administrator
	exempt); projects without a row keep free manual entry."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)

		def make_project(label):
			return (
				frappe.get_doc(
					{
						"doctype": "Project",
						"project_name": "TEST-F1T-" + label + "-" + self.token,
						"status": "Open",
						"company": self.company,
					}
				)
				.insert(ignore_permissions=True)
				.name
			)

		self.project = make_project("A")
		self.free_project = make_project("B")  # no configured transport price
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-F1T-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		eq = frappe.new_doc("Card Equipment")
		eq.company = self.company
		eq.equipment_type = self._m["etype"]
		eq.ownership = OWNED
		eq.equipment_name = "TEST-F1T-EQ-" + self.token
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.insert(ignore_permissions=True)
		self.equipment = eq.name
		# configure the price table: project A costs 500 per transport
		settings = frappe.get_single("Card Settings")
		settings.append("project_transport_prices", {"project": self.project, "amount": 500})
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Card Settings", "Card Settings")

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def _transport(self, project, amount=None):
		t = frappe.new_doc("Equipment Transport")
		t.equipment = self.equipment
		t.project = project
		t.date = "2026-09-15"
		t.transport_supplier = self.supplier
		t.company = self.company
		if amount is not None:
			t.amount = amount
		t.insert(ignore_permissions=True)  # draft only: no transfer side effects
		t.reload()
		return t

	def test_blank_amount_defaults_from_settings(self):
		self.assertEqual(flt(self._transport(self.project).amount), 500.0)

	def test_administrator_overrides_configured_amount(self):
		self.assertEqual(flt(self._transport(self.project, amount=600).amount), 600.0)

	def test_non_role_user_cannot_override(self):
		user = _role_user("Card User")
		try:
			frappe.set_user(user)
			with self.assertRaises(frappe.ValidationError):
				self._transport(self.project, amount=600)
		finally:
			frappe.set_user("Administrator")

	def test_project_without_configured_row_is_free(self):
		# no row for this project: any amount passes, even without the editor role
		user = _role_user("Card User")
		try:
			frappe.set_user(user)
			t = self._transport(self.free_project, amount=777)
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(flt(t.amount), 777.0)


class TestRateBasisSettings(IntegrationTestCase):
	"""F.5 calculation bases: بالشهر spreads the rate over standard_month_hours
	(Card Settings, default 260) on BOTH billing sides; بالساعة passes through;
	باليوم keeps the legacy daily behaviour; default_rate_basis pre-fills the
	rate types of NEW equipment only."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		# deterministic F.5 baseline (the site may be configured otherwise)
		_set("standard_month_hours", 260)
		_set("default_rate_basis", "")
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-F5-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-F5-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		cust = frappe.new_doc("Customer")
		cust.customer_name = "TEST-F5-CUST-" + self.token
		cust.customer_group = _leaf("Customer Group", "customer_group_name", "All Customer Groups")
		cust.territory = _leaf("Territory", "territory_name", "All Territories")
		cust.insert(ignore_permissions=True)
		self.customer = cust.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _equipment(self, ownership="إيجار", rate_type="باليوم", rate=750, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = ownership
		d.equipment_name = "TEST-F5-EQ-" + frappe.generate_hash(length=6)
		if rate_type:
			d.rate_type = rate_type
		if rate is not None:
			d.rate = rate
		d.daily_hours = 10
		if ownership != OWNED:
			d.supplier = self.supplier
		for k, v in kw.items():
			setattr(d, k, v)
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _card(self, eq, hours_list, submit=False):
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	# ---------- بالشهر on both sides ----------

	def test_monthly_basis_prices_supplier_side(self):
		eq = self._equipment(rate_type="بالشهر", rate=26000)
		self.assertEqual(flt(eq.approved_hourly_rate), 100.0)  # 26000 / 260
		card = self._card(eq, [10], submit=True)
		self.assertEqual(flt(card.amount), 1000.0)  # 10h x 100/h
		self.assertEqual(flt(card.net_amount), 1000.0)
		self.assertEqual(flt(card.hourly_rate_used), 100.0)
		self.assertEqual(card.rate_basis_used, "بالشهر")

	def test_monthly_basis_prices_customer_side(self):
		eq = self._equipment(
			ownership=OWNED,
			rental_direction=DIR_RENTED_OUT,
			default_customer=self.customer,
			customer_rate_type="بالشهر",
			customer_rate=52000,
		)
		card = self._card(eq, [10], submit=True)
		self.assertEqual(flt(card.amount), 0)  # rented-out: no supplier billing
		self.assertEqual(flt(card.customer_amount), 2000.0)  # 52000/260 = 200/h x 10h
		self.assertEqual(flt(card.customer_rate_used), 200.0)

	# ---------- the other bases ----------

	def test_hourly_basis_passes_through(self):
		eq = self._equipment(rate_type="بالساعة", rate=60)
		self.assertEqual(flt(eq.approved_hourly_rate), 60.0)
		card = self._card(eq, [10], submit=True)
		self.assertEqual(flt(card.amount), 600.0)
		self.assertEqual(flt(card.hourly_rate_used), 60.0)

	def test_daily_basis_unchanged(self):
		card = self._card(self._equipment(), [10], submit=True)  # legacy: 750/day over 10h
		self.assertEqual(flt(card.amount), 750.0)
		self.assertEqual(flt(card.hourly_rate_used), 75.0)

	# ---------- standard_month_hours wiring ----------

	def test_month_hours_change_reprices_draft_not_submitted(self):
		draft = self._card(self._equipment(rate_type="بالشهر", rate=26000), [10])
		submitted = self._card(self._equipment(rate_type="بالشهر", rate=26000), [10], submit=True)
		self.assertEqual(flt(draft.amount), 1000.0)
		self.assertEqual(flt(submitted.amount), 1000.0)
		_set("standard_month_hours", 130)
		draft.save(ignore_permissions=True)
		draft.reload()
		self.assertEqual(flt(draft.amount), 2000.0)  # 26000/130 = 200/h x 10h
		submitted.reload()
		self.assertEqual(flt(submitted.amount), 1000.0)  # submitted card stays frozen
		self.assertEqual(flt(submitted.hourly_rate_used), 100.0)

	def test_standard_month_hours_defaults_to_260(self):
		frappe.db.delete("Singles", {"doctype": "Card Settings", "field": "standard_month_hours"})
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.assertEqual(setting("standard_month_hours"), 260.0)
		eq = self._equipment(rate_type="بالشهر", rate=26000)
		self.assertEqual(flt(eq.approved_hourly_rate), 100.0)

	# ---------- default_rate_basis pre-fill ----------

	def test_default_rate_basis_prefills_new_equipment_only(self):
		_set("default_rate_basis", "بالشهر")
		eq = self._equipment(ownership=OWNED, rate_type=None, rate=0)
		self.assertEqual(eq.rate_type, "بالشهر")
		self.assertEqual(eq.customer_rate_type, "بالشهر")
		# a provided value is never overridden (the blank side is still pre-filled)
		eq2 = self._equipment(ownership=OWNED)
		self.assertEqual(eq2.rate_type, "باليوم")
		self.assertEqual(eq2.customer_rate_type, "بالشهر")
		# existing equipment is untouched when the setting changes later
		_set("default_rate_basis", "بالساعة")
		eq.save(ignore_permissions=True)
		eq.reload()
		self.assertEqual(eq.rate_type, "بالشهر")
		self.assertEqual(eq.customer_rate_type, "بالشهر")
		# blank setting pre-fills nothing (baseline behaviour)
		_set("default_rate_basis", "")
		eq3 = self._equipment(ownership=OWNED, rate_type=None, rate=0)
		self.assertFalse(eq3.rate_type)
		self.assertFalse(eq3.customer_rate_type)


class TestSingleCompanyDefaults(IntegrationTestCase):
	"""F.8: documents created without a company get THE single company."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		# keep the F.1 diesel supplier policy out of this test's way
		_set("diesel_supplier", "")
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-F8-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-F8-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def test_diesel_fill_defaults_to_the_company(self):
		from card.company import single_company

		f = frappe.new_doc("Project Diesel Fill")
		f.date = "2026-09-15"
		f.project = self.project
		f.supplier = self.supplier
		f.litres = 10
		f.unit_price = 2
		f.insert(ignore_permissions=True)  # company left blank on purpose
		self.assertTrue(f.company)
		self.assertEqual(f.company, single_company())
