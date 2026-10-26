# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Report access regression tests (issue #13): every CARD report runs for one
validated company, ledger figures reach only users whose ROLES read GL Entry,
the link-filter queries are role-checked and company-scoped, and diesel
allocation never mixes companies. No test grants an ERPNext permission — the
point is that none is needed. A real second Company row is inserted raw (no
chart of accounts needed) so every refusal has a positive control; everything
is rolled back."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card import api
from card.constants import DIR_RENTED_OUT, OWNED
from card.diesel import allocate_project_diesel, project_operating_hours
from card.report_access import can_view_ledger, permitted_companies, readable_links, resolve_company
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_controllers import _days, _ensure_masters, _registry_figures
from card.tests.test_customer_reports import _leaf

RENTED = "إيجار"
LEDGER_KEYS = {
	"equipment_suppliers_summary": {
		"accrued",
		"invoiced_net",
		"diff",
		"external_net",
		"opening",
		"paid",
		"closing",
	},
	"equipment_customers_summary": {
		"invoiced",
		"invoiced_net",
		"diff",
		"external_net",
		"opening",
		"received",
		"closing",
	},
}
NOTICE = "Ledger balances are shown only to users with General Ledger access."


def _run(module, filters):
	execute = frappe.get_attr(f"card.card.report.{module}.{module}.execute")
	result = execute(filters)
	message = result[2] if len(result) > 2 else None
	summary = result[4] if len(result) > 4 else None
	return result[0], result[1], message, summary


def _labels(summary):
	return {item["label"] for item in summary or []}


def _value(summary, label):
	for item in summary or []:
		if item["label"] == frappe._(label):
			return item["value"]
	return None


def _js_filters(module):
	"""The report's filter definitions as its JS declares them — the same
	fieldname/fieldtype/options the Desk sends to query_report.run as js_filters."""
	import os

	path = os.path.join(frappe.get_app_path("card"), "card", "report", module, module + ".js")
	filters, current = [], None
	for line in open(path, encoding="utf-8"):
		for key in ("fieldname", "fieldtype", "options"):
			marker = key + ': "'
			if marker in line:
				value = line.split(marker, 1)[1].split('"', 1)[0]
				if key == "fieldname":
					current = {"fieldname": value}
					filters.append(current)
				elif current is not None and key not in current:
					current[key] = value
	return [f for f in filters if f.get("fieldtype")]


REPORT_MODULES = (
	"equipment_supplier_statement",
	"equipment_suppliers_summary",
	"equipment_customer_statement",
	"equipment_customers_summary",
	"equipment_diesel_analysis",
	"equipment_diesel_consumption",
	"equipment_expenses_without_equipment",
	"operating_cost_by_project",
	"transport_cost_by_project",
)


def _fieldnames(columns):
	return {c["fieldname"] if isinstance(c, dict) else c for c in columns}


class TestReportAccess(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.db.set_single_value("Card Settings", "diesel_supplier", None)
		frappe.db.set_single_value("Card Settings", "diesel_supplier_policy", "متغير")
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.other = self._other_company()
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-RACC-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.supplier = self._supplier("A")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.request = None
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures ----------

	def _other_company(self):
		name = "TEST-RACC-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "R" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _supplier(self, suffix):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-RACC-SUP-" + self.token + suffix
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _user(self, roles, restrict_to=None, applicable_for=None, website=False):
		email = f"racc-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Report Access",
				"send_welcome_email": 0,
				"user_type": "Website User" if website else "System User",
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 0 if applicable_for else 1,
					"applicable_for": applicable_for,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _equipment(self, suffix, supplier=None, customer=None):
		eq = frappe.new_doc("Card Equipment")
		eq.company = self.company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-RACC-EQ-" + self.token + suffix
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		if customer:
			eq.ownership = OWNED
			eq.rental_direction = DIR_RENTED_OUT
			eq.default_customer = customer
			eq.customer_rate_type = "باليوم"
			eq.customer_rate = 1000
		else:
			eq.ownership = RENTED
			eq.supplier = supplier or self.supplier
		eq.insert(ignore_permissions=True)
		return eq

	def _card(self, eq, hours, submit=True):
		card = frappe.new_doc("Card Monthly Card")
		card.equipment = eq.name
		card.project = self.project
		card.shift = "نهاري"
		card.month = "09"
		card.year = 2026
		for row in _days(hours):
			card.append("days", row)
		card.insert(ignore_permissions=True)
		if submit:
			card.submit()
		card.reload()
		return card

	def _move_to_other(self, card):
		frappe.db.set_value("Card Monthly Card", card.name, "company", self.other, update_modified=False)

	def _customer(self, suffix=""):
		cust = frappe.new_doc("Customer")
		cust.customer_name = "TEST-RACC-CUST-" + self.token + suffix
		cust.customer_group = _leaf("Customer Group", "customer_group_name", "All Customer Groups")
		cust.territory = _leaf("Territory", "territory_name", "All Territories")
		cust.insert(ignore_permissions=True)
		return cust.name

	def _raw_gl(self, company, credit=0.0, debit=0.0, party_type="Supplier", party=None):
		gl = frappe.new_doc("GL Entry")
		gl.update(
			{
				"company": company,
				"posting_date": "2026-09-15",
				"party_type": party_type,
				"party": party or self.supplier,
				"credit": credit,
				"debit": debit,
				"is_cancelled": 0,
				"voucher_type": "Journal Entry",
				"voucher_no": "TEST-RACC-" + self.token,
			}
		)
		gl.name = frappe.generate_hash(length=12)
		gl.db_insert()
		return gl.name

	def _statement(self, **kw):
		f = {
			"company": self.company,
			"statement_type": "مورد",
			"supplier": self.supplier,
			"from_month": 9,
			"from_year": 2026,
			"project": self.project,
		}
		f.update(kw)
		return _run("equipment_supplier_statement", f)

	def _fill(self, litres, unit_price, company=None):
		fill = frappe.new_doc("Project Diesel Fill")
		fill.date = "2026-09-15"
		fill.project = self.project
		fill.supplier = self.supplier
		fill.company = company or self.company
		fill.litres = litres
		fill.unit_price = unit_price
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		return fill

	# ---------- ledger gating ----------

	def test_card_user_statement_shows_card_figures_but_no_ledger(self):
		card = self._card(self._equipment("L1"), [10, 10])
		self._raw_gl(self.company, credit=999)
		frappe.set_user(self._user(["Card User"]))
		_cols, rows, message, summary = self._statement()
		self.assertIn(card.name, [r.get("card") for r in rows])
		self.assertEqual(flt(_value(summary, "Net cards")), flt(card.net_amount))
		self.assertNotIn(frappe._("Accrual entries (Credit)"), _labels(summary))
		self.assertNotIn(frappe._("Supplier closing balance"), _labels(summary))
		self.assertIn(frappe._(NOTICE), message)

	def test_accounts_manager_sees_ledger_of_its_company_only(self):
		self._card(self._equipment("L2"), [10])
		self._raw_gl(self.company, credit=400)
		self._raw_gl(self.other, credit=7000)
		frappe.set_user(self._user(["Card User", "Accounts Manager"]))
		_cols, _rows, _msg, summary = self._statement()
		self.assertEqual(flt(_value(summary, "Accrual entries (Credit)")), 400.0)

	def test_shared_gl_entry_does_not_unlock_the_ledger(self):
		self._card(self._equipment("L3"), [10])
		gl = self._raw_gl(self.company, credit=999)
		user = self._user(["Card User"])
		frappe.share.add("GL Entry", gl, user, read=1, flags={"ignore_share_permission": True})
		frappe.set_user(user)
		self.assertTrue(frappe.has_permission("GL Entry", "read"), "premise: the share alone passes")
		self.assertFalse(can_view_ledger(self.company))
		_cols, _rows, _msg, summary = self._statement()
		self.assertNotIn(frappe._("Accrual entries (Credit)"), _labels(summary))

	def test_summaries_drop_ledger_columns_and_values_for_card_user(self):
		self._card(self._equipment("S1"), [10])
		self._card(self._equipment("S2", customer=self._customer()), [10])
		self._raw_gl(self.company, credit=999)
		frappe.set_user(self._user(["Card User"]))
		for module, keys in LEDGER_KEYS.items():
			cols, rows, _msg, summary = _run(
				module, {"company": self.company, "from_month": 9, "from_year": 2026, "project": self.project}
			)
			self.assertTrue(rows, module)
			self.assertFalse(keys & _fieldnames(cols), module)
			for row in rows:
				self.assertFalse(keys & set(row), module)
			self.assertNotIn(frappe._("Not invoiced through Card"), _labels(summary), module)
			self.assertNotIn(
				frappe._("ERPNext invoices outside Card — to reconcile (net before VAT)"),
				_labels(summary),
				module,
			)

	def test_customer_statement_hides_ledger_for_card_user(self):
		customer = self._customer()
		card = self._card(self._equipment("C1", customer=customer), [10])
		frappe.set_user(self._user(["Card User"]))
		_cols, rows, message, summary = _run(
			"equipment_customer_statement",
			{"company": self.company, "from_month": 9, "from_year": 2026, "customer": customer},
		)
		self.assertIn(card.name, [r.get("card") for r in rows])
		self.assertNotIn(frappe._("Invoiced entries (Debit)"), _labels(summary))
		self.assertIn(frappe._(NOTICE), message)

	def test_expenses_without_equipment_is_ledger_only(self):
		roles = {r.role for r in frappe.get_doc("Report", "Equipment Expenses Without Equipment").roles}
		self.assertFalse(roles & {"Card User", "Card Manager"})
		frappe.set_user(self._user(["Card User"]))
		with self.assertRaises(frappe.PermissionError):
			_run("equipment_expenses_without_equipment", {"company": self.company})

	# ---------- company scoping ----------

	def test_cards_of_another_company_are_not_listed(self):
		kept = self._card(self._equipment("K1"), [10])
		moved = self._card(self._equipment("K2"), [10])
		self._move_to_other(moved)
		_cols, rows, _msg, _summary = self._statement()
		listed = [r.get("card") for r in rows]
		self.assertIn(kept.name, listed)
		self.assertNotIn(moved.name, listed)

	def test_restricted_user_is_refused_another_company(self):
		reports = {
			"equipment_supplier_statement": {"statement_type": "مورد", "supplier": self.supplier},
			"equipment_suppliers_summary": {},
			"equipment_customer_statement": {"customer": "x"},
			"equipment_customers_summary": {},
			"equipment_diesel_analysis": {},
			"equipment_diesel_consumption": {},
			"operating_cost_by_project": {},
			"transport_cost_by_project": {},
		}
		period = {"from_month": 9, "from_year": 2026}
		# positive control: an unrestricted user runs every report for the other company
		for module, extra in reports.items():
			_run(module, {**period, **extra, "company": self.other})
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		self.assertEqual(permitted_companies(), [self.company])
		for module, extra in reports.items():
			with self.assertRaises(frappe.PermissionError, msg=module):
				_run(module, {**period, **extra, "company": self.other})

	def test_ledger_follows_gl_entry_user_permissions(self):
		frappe.set_user(self._user(["Accounts Manager"], restrict_to=self.company, applicable_for="GL Entry"))
		self.assertTrue(can_view_ledger(self.company))
		self.assertFalse(can_view_ledger(self.other))

	def test_user_permission_honours_applicable_for(self):
		frappe.set_user(self._user(["Card User"], restrict_to=self.company, applicable_for="Sales Invoice"))
		self.assertIn(self.other, permitted_companies())
		frappe.set_user("Administrator")
		frappe.set_user(
			self._user(["Card User"], restrict_to=self.company, applicable_for="Card Monthly Card")
		)
		self.assertEqual(permitted_companies(), [self.company])

	# ---------- diesel allocation ----------

	def test_diesel_allocation_never_mixes_companies(self):
		eq_a = self._equipment("D1")
		self._card(eq_a, [10])
		eq_b = self._equipment("D2")
		self._move_to_other(self._card(eq_b, [10]))
		self._fill(100, 1)
		other_fill = self._fill(40, 1)
		frappe.db.set_value(
			"Project Diesel Fill", other_fill.name, "company", self.other, update_modified=False
		)
		self.assertEqual(set(project_operating_hours(self.project, 9, 2026, self.company)), {eq_a.name})
		alloc = allocate_project_diesel(self.project, "09", "2026", self.company)
		self.assertEqual(set(alloc), {eq_a.name})
		self.assertEqual(flt(alloc[eq_a.name]["amount"]), 100.0)

	# ---------- link-filter queries ----------

	def test_queries_refuse_users_without_card_role(self):
		frappe.set_user(self._user([], website=True))
		# real doctypes: the search decorator returns [] early for an unknown one
		for query, doctype in (
			(api.card_suppliers_query, "Supplier"),
			(api.card_customers_query, "Customer"),
			(api.available_assets_query, "Asset"),
		):
			with self.assertRaises(frappe.PermissionError, msg=doctype):
				query(doctype, "", "name", 0, 20, {})
		for method in (api.card_project_options, api.card_company_options, api.report_defaults):
			with self.assertRaises(frappe.PermissionError, msg=method.__name__):
				method()

	def test_supplier_query_hides_parties_seen_only_in_other_companies(self):
		self._card(self._equipment("Q1"), [10])
		other_only = self._supplier("B")
		self._move_to_other(self._card(self._equipment("Q2", supplier=other_only), [10]))
		frappe.set_user(self._user(["Card User"]))
		unrestricted = [r[0] for r in api.card_suppliers_query("Supplier", "", "name", 0, 500, {})]
		self.assertIn(other_only, unrestricted)
		frappe.set_user("Administrator")
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		restricted = [r[0] for r in api.card_suppliers_query("Supplier", "", "name", 0, 500, {})]
		self.assertIn(self.supplier, restricted)
		self.assertNotIn(other_only, restricted)
		self.assertEqual(api.card_company_options(), [self.company])
		self.assertEqual(api.card_project_options(company=self.other), [])
		self.assertIn(self.project, [o["value"] for o in api.card_project_options(txt=self.project)])

	def test_link_filters_work_through_frappe_link_validation(self):
		"""The real path the supplier filter takes: search_link for the dropdown and
		validate_link_and_fetch on blur — with no Supplier read/select grant."""
		from frappe.client import validate_link_and_fetch
		from frappe.desk.search import search_link

		self._card(self._equipment("V1"), [10])
		frappe.set_user(self._user(["Card User"]))
		self.assertFalse(frappe.has_permission("Supplier", "select"), "premise: no Supplier grant")
		query = "card.api.card_suppliers_query"
		filters = {"company": self.company}
		found = search_link("Card Equipment Supplier", self.supplier, query=query, filters=filters)
		self.assertIn(self.supplier, [r.get("value") for r in found])
		frappe.local.request = frappe._dict(method="POST")
		validated = validate_link_and_fetch(
			"Card Equipment Supplier", self.supplier, query=query, filters=filters
		)
		self.assertEqual(validated.get("name"), self.supplier)

	def test_no_report_filter_links_to_an_erpnext_master(self):
		# Frappe validates report Link filter values against the user's own
		# permissions; operational roles cannot read these masters
		for module in REPORT_MODULES:
			for f in _js_filters(module):
				if f["fieldtype"] == "Link":
					self.assertNotIn(
						f.get("options"), {"Supplier", "Customer", "Project", "Company"}, (module, f)
					)

	def test_card_user_runs_filtered_reports_through_query_report(self):
		"""The exact server path the Desk uses, with the UI's own filter
		definitions: Link filter values are permission-checked by Frappe."""
		import json

		from frappe.desk.query_report import run

		customer = self._customer()
		self._card(self._equipment("R1"), [10])
		self._card(self._equipment("R2", customer=customer), [10])
		frappe.set_user(self._user(["Card User"]))
		period = {"company": self.company, "from_month": "09", "from_year": 2026, "project": self.project}
		cases = {
			"Equipment Supplier Statement": {**period, "statement_type": "مورد", "supplier": self.supplier},
			"Equipment Customer Statement": {**period, "customer": customer},
			"Equipment Suppliers Summary": period,
			"Equipment Customers Summary": period,
			"Equipment Diesel Analysis": period,
			"Equipment Diesel Consumption": {"company": self.company, "project": self.project},
			"Operating Cost by Project": {"company": self.company, "project": self.project},
			"Transport Cost by Project": {"company": self.company, "project": self.project},
		}
		for report, filters in cases.items():
			module = frappe.scrub(report)
			frappe.local.message_log = []
			result = run(
				report,
				filters=json.dumps(filters),
				js_filters=json.dumps(_js_filters(module)),
				ignore_prepared_report=True,
			)
			self.assertIn("result", result, report)
			# master Link columns the user cannot read come back as Data, so the
			# Desk posts no permission message resolving their titles
			for column in result["columns"]:
				if isinstance(column, dict) and column.get("fieldname") in (
					"project",
					"supplier",
					"customer",
				):
					self.assertNotEqual(column.get("fieldtype"), "Link", (report, column))
			self.assertFalse([m for m in frappe.local.message_log if "role permission" in str(m)], report)
		defaults = api.report_defaults()
		self.assertIn("include_draft_in_reports", defaults)

	def test_first_draft_card_makes_the_party_selectable(self):
		supplier = self._supplier("DRAFT")
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", supplier))
		self._card(self._equipment("DR1", supplier=supplier), [10], submit=False)
		self.assertTrue(frappe.db.exists("Card Equipment Supplier", supplier))
		frappe.set_user(self._user(["Card User"]))
		names = [r[0] for r in api.card_suppliers_query("Card Equipment Supplier", "", "name", 0, 500, {})]
		self.assertIn(supplier, names)

	def test_registry_backfill_patch_is_idempotent(self):
		from card.patches.v1_2_1.ensure_party_registries import execute

		supplier = self._supplier("PATCH")
		self._card(self._equipment("PT1", supplier=supplier), [10], submit=False)
		frappe.db.delete("Card Equipment Supplier", {"name": supplier})
		execute()
		self.assertTrue(frappe.db.exists("Card Equipment Supplier", supplier))
		execute()
		self.assertEqual(frappe.db.count("Card Equipment Supplier", {"name": supplier}), 1)

	def test_registry_follows_supplier_rename(self):
		supplier = self._supplier("REN")
		self._card(self._equipment("RN1", supplier=supplier), [10])
		renamed = supplier + "-NEW"
		frappe.rename_doc("Supplier", supplier, renamed, force=True)
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", supplier))
		self.assertEqual(frappe.db.get_value("Card Equipment Supplier", renamed, "supplier"), renamed)
		names = [r[0] for r in api.card_suppliers_query("Card Equipment Supplier", "", "name", 0, 500, {})]
		self.assertIn(renamed, names)

	def test_registry_survives_supplier_merge(self):
		keep = self._supplier("KEEP")
		gone = self._supplier("GONE")
		self._card(self._equipment("MG1", supplier=keep), [10])
		self._card(self._equipment("MG2", supplier=gone), [10])
		frappe.rename_doc("Supplier", gone, keep, merge=True, force=True)
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", gone))
		row = _registry_figures("Supplier", keep)
		self.assertEqual((row.card_count, row.equipment_count, row.total_hours), (2, 2, 20))

	def _misname(self, registry, name):
		# what a rename before the hooks existed left behind: row name != party
		frappe.db.sql(f"update `tab{registry}` set name = %s where name = %s", (name + "-OLD", name))

	def test_merge_drops_a_misnamed_row_of_the_merged_party(self):
		keep = self._supplier("MKEEP")
		gone = self._supplier("MGONE")
		self._card(self._equipment("MM1", supplier=keep), [10])
		self._card(self._equipment("MM2", supplier=gone), [10])
		self._misname("Card Equipment Supplier", gone)
		# the misnamed row's link would be rewritten onto keep's unique link
		frappe.rename_doc("Supplier", gone, keep, merge=True, force=True)
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", gone + "-OLD"))
		self.assertEqual(frappe.db.count("Card Equipment Supplier", {"supplier": keep}), 1)
		self.assertEqual(_registry_figures("Supplier", keep).card_count, 2)

	def test_rename_realigns_a_misnamed_row(self):
		supplier = self._supplier("RMIS")
		self._card(self._equipment("RM1", supplier=supplier), [10])
		self._misname("Card Equipment Supplier", supplier)
		renamed = supplier + "-NEW"
		frappe.rename_doc("Supplier", supplier, renamed, force=True)
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", supplier + "-OLD"))
		self.assertEqual(frappe.db.get_value("Card Equipment Supplier", renamed, "supplier"), renamed)

	def test_rename_onto_a_name_held_by_a_stale_row(self):
		supplier = self._supplier("STL")
		other = self._supplier("STX")
		self._card(self._equipment("ST1", supplier=supplier), [10])
		self._card(self._equipment("ST2", supplier=other), [10])
		renamed = supplier + "-NEW"
		# a stale row holds the target name while linking another party
		frappe.db.sql("update `tabCard Equipment Supplier` set name = %s where name = %s", (renamed, other))
		frappe.rename_doc("Supplier", supplier, renamed, force=True)
		self.assertEqual(frappe.db.get_value("Card Equipment Supplier", renamed, "supplier"), renamed)
		self.assertEqual(frappe.db.count("Card Equipment Supplier", {"supplier": renamed}), 1)
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", supplier))

	def test_registry_follows_customer_rename_and_merge(self):
		customer = self._customer()
		self._card(self._equipment("CR1", customer=customer), [10])
		renamed = customer + "-NEW"
		frappe.rename_doc("Customer", customer, renamed, force=True)
		self.assertFalse(frappe.db.exists("Card Equipment Customer", customer))
		self.assertEqual(frappe.db.get_value("Card Equipment Customer", renamed, "customer"), renamed)

		other = frappe.new_doc("Customer")
		other.customer_name = renamed + "-B"
		other.customer_group = _leaf("Customer Group", "customer_group_name", "All Customer Groups")
		other.territory = _leaf("Territory", "territory_name", "All Territories")
		other.insert(ignore_permissions=True)
		self._card(self._equipment("CR2", customer=other.name), [10])
		frappe.rename_doc("Customer", renamed, other.name, merge=True, force=True)
		self.assertFalse(frappe.db.exists("Card Equipment Customer", renamed))
		self.assertEqual(_registry_figures("Customer", other.name).card_count, 2)

	def test_backfill_realigns_a_misnamed_registry_row(self):
		from card.patches.v1_2_1.ensure_party_registries import execute

		supplier = self._supplier("MIS")
		self._card(self._equipment("MS1", supplier=supplier), [10])
		# what a rename before the hooks existed left behind: row name != party
		frappe.db.sql(
			"update `tabCard Equipment Supplier` set name = %s where name = %s", (supplier + "-OLD", supplier)
		)
		execute()
		self.assertTrue(frappe.db.exists("Card Equipment Supplier", supplier))
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", supplier + "-OLD"))

	def test_unreadable_project_column_shows_the_project_name(self):
		# a project whose record name differs from its title (naming series)
		code = "TEST-RACC-PCODE-" + self.token
		project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "TEST-RACC-PTITLE-" + self.token,
				"status": "Open",
				"company": self.company,
			}
		)
		project.name = code
		project.db_insert()
		columns = [{"fieldname": "project", "fieldtype": "Link", "options": "Project"}]
		rows = [{"project": code}, {"project": None}, ["a list row is left alone"]]
		frappe.set_user(self._user(["Card User"]))
		result = readable_links(columns, rows)
		self.assertEqual(result[0]["fieldtype"], "Data")
		self.assertEqual(rows[0]["project"], "TEST-RACC-PTITLE-" + self.token)
		self.assertIsNone(rows[1]["project"])
		# party values stay record names: the summaries' statement drill-downs use them
		party_columns = [
			{"fieldname": "customer", "fieldtype": "Link", "options": "Customer"},
			{"fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"},
		]
		party_rows = [{"customer": self._customer(), "supplier": self.supplier}]
		before = dict(party_rows[0])
		readable_links(party_columns, party_rows)
		self.assertEqual(party_rows[0], before)
		# a role-based Project reader keeps the Link column and the record name
		frappe.set_user("Administrator")
		reader = self._user(["Card User", "Projects User"])
		frappe.set_user(reader)
		rows = [{"project": code}]
		self.assertEqual(readable_links(columns, rows)[0]["fieldtype"], "Link")
		self.assertEqual(rows[0]["project"], code)

	def test_registry_is_scoped_to_the_users_companies(self):
		"""#23: registry rows are per party across companies; a restricted user
		sees only parties with cards in their companies, and figures only for
		those companies — in the list, the document, REST and party_figures."""
		from frappe.client import get as client_get

		shared = self._supplier("SHR")
		other_only = self._supplier("OTH")
		self._card(self._equipment("SH1", supplier=shared), [10])
		self._move_to_other(self._card(self._equipment("SH2", supplier=shared), [10, 10]))
		self._move_to_other(self._card(self._equipment("OT1", supplier=other_only), [10]))
		for party in (shared, other_only):
			api.recompute_supplier(party)
			self.assertFalse(frappe.db.get_value("Card Equipment Supplier", party, "total_net"))

		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		listed = frappe.get_list("Card Equipment Supplier", pluck="name", limit_page_length=0)
		self.assertIn(shared, listed)
		self.assertNotIn(other_only, listed)
		self.assertTrue(frappe.has_permission("Card Equipment Supplier", "read", shared))
		self.assertFalse(frappe.has_permission("Card Equipment Supplier", "read", other_only))
		with self.assertRaises(frappe.PermissionError):
			client_get("Card Equipment Supplier", other_only)
		with self.assertRaises(frappe.PermissionError):
			api.party_figures("Supplier", other_only)
		figures = api.party_figures("Supplier", shared)
		self.assertEqual([f["company"] for f in figures], [self.company])
		self.assertEqual(figures[0]["card_count"], 1)

		# an unrestricted reader sees both parties and both companies' figures
		frappe.set_user("Administrator")
		frappe.set_user(self._user(["Card User"]))
		listed = frappe.get_list("Card Equipment Supplier", pluck="name", limit_page_length=0)
		self.assertIn(other_only, listed)
		self.assertEqual(
			sorted(f["company"] for f in api.party_figures("Supplier", shared)),
			sorted([self.company, self.other]),
		)

	def test_customer_registry_is_scoped_to_the_users_companies(self):
		"""#23, customer side of the test above: a restricted user sees only the
		customers with cards in their companies — in the list (Desk, REST,
		frappe.client), the document (REST, frappe.client), party_figures and
		the reports' link query — and figures only for those companies."""
		import json

		from frappe.api.v1 import document_list, read_doc
		from frappe.client import get as client_get
		from frappe.client import get_list as client_get_list
		from frappe.desk.reportview import get as reportview_get

		registry = "Card Equipment Customer"
		shared = self._customer("SHR")
		other_only = self._customer("OTH")
		self._card(self._equipment("CS1", customer=shared), [10])
		self._move_to_other(self._card(self._equipment("CS2", customer=shared), [10, 10]))
		self._move_to_other(self._card(self._equipment("CO1", customer=other_only), [10]))
		for party in (shared, other_only):
			api.recompute_customer(party)
			self.assertFalse(frappe.db.get_value(registry, party, "total_accrued"))
		parties = json.dumps([["name", "in", [shared, other_only]]])

		def rest(fn, *args, **form):
			frappe.local.form_dict = frappe._dict(form)
			try:
				return fn(*args)
			finally:
				frappe.local.form_dict = frappe._dict()

		def listed_on_every_path():
			return {
				"frappe.get_list": set(
					frappe.get_list(registry, filters={"name": ["in", [shared, other_only]]}, pluck="name")
				),
				"REST GET /api/resource": {r["name"] for r in rest(document_list, registry, filters=parties)},
				"frappe.client.get_list": {
					r["name"]
					for r in client_get_list(registry, filters={"name": ["in", [shared, other_only]]})
				},
				"list view (reportview)": {
					v[0]
					for v in rest(reportview_get, doctype=registry, fields='["name"]', filters=parties)[
						"values"
					]
				},
			}

		def queried():
			return {r[0] for r in api.card_customers_query("Customer", "", "name", 0, 500, {})}

		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		for path, names in listed_on_every_path().items():
			self.assertEqual(names, {shared}, path)
		self.assertTrue(frappe.has_permission(registry, "read", shared))
		self.assertFalse(frappe.has_permission(registry, "read", other_only))
		self.assertEqual(client_get(registry, shared)["name"], shared)
		self.assertEqual(read_doc(registry, shared).name, shared)
		for path, fn in {
			"REST GET /api/resource/<name>": lambda: read_doc(registry, other_only),
			"frappe.client.get": lambda: client_get(registry, other_only),
			"party_figures": lambda: api.party_figures("Customer", other_only),
		}.items():
			with self.assertRaises(frappe.PermissionError, msg=path):
				fn()
		figures = api.party_figures("Customer", shared)
		self.assertEqual([f["company"] for f in figures], [self.company])
		self.assertEqual(figures[0]["card_count"], 1)
		self.assertIn(shared, queried())
		self.assertNotIn(other_only, queried())
		self.assertEqual(api.card_company_options(), [self.company])

		# an unrestricted reader sees both customers and both companies' figures
		frappe.set_user("Administrator")
		frappe.set_user(self._user(["Card User"]))
		for path, names in listed_on_every_path().items():
			self.assertEqual(names, {shared, other_only}, path)
		self.assertEqual(client_get(registry, other_only)["name"], other_only)
		self.assertLessEqual({shared, other_only}, queried())
		self.assertEqual(
			sorted(f["company"] for f in api.party_figures("Customer", shared)),
			sorted([self.company, self.other]),
		)

	def test_card_roles_gain_no_erpnext_grants(self):
		frappe.set_user(self._user(["Card User"]))
		for doctype in ("GL Entry", "Project", "Supplier", "Customer"):
			self.assertFalse(frappe.has_permission(doctype, "read"), doctype)

	# ---------- H3: registry refresh endpoints and party figures ----------

	def test_refresh_endpoints_are_for_system_managers_only(self):
		supplier, customer = self._supplier("RF0"), self._customer("RF0")
		frappe.set_user(self._user(["Card Manager"]))
		for call, party in ((api.refresh_supplier, supplier), (api.refresh_customer, customer)):
			for args in ((party,), ()):
				# the endpoints currently raise ValidationError (frappe.throw); the contract is the denial
				with self.assertRaisesRegex(
					(frappe.PermissionError, frappe.ValidationError), "System Managers only"
				):
					call(*args)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.exists("Card Equipment Supplier", supplier))
		self.assertFalse(frappe.db.exists("Card Equipment Customer", customer))

	def test_refresh_supplier_single_party_and_all_parties(self):
		counted, draft_only, lone = self._supplier("RF1"), self._supplier("RF2"), self._supplier("RF3")
		self._card(self._equipment("RF1", supplier=counted), [10])
		self._card(self._equipment("RF2", supplier=draft_only), [10], submit=False)
		frappe.set_user(self._user(["System Manager"]))
		self.assertEqual(api.refresh_supplier(lone), [{"supplier": lone}])
		self.assertTrue(frappe.db.exists("Card Equipment Supplier", lone))
		done = api.refresh_supplier()
		parties = [row["supplier"] for row in done]
		self.assertEqual(done, [{"supplier": party} for party in parties])
		self.assertEqual(parties, sorted(parties))
		self.assertIn(counted, parties)  # a submitted non-owned card
		self.assertNotIn(draft_only, parties)  # a draft card does not count
		self.assertNotIn(lone, parties)  # no card at all

	def test_refresh_customer_single_party_and_all_parties(self):
		billed, draft_only, lone = self._customer("RF1"), self._customer("RF2"), self._customer("RF3")
		self._card(self._equipment("RC1", customer=billed), [10])
		self._card(self._equipment("RC2", customer=draft_only), [10], submit=False)
		frappe.set_user(self._user(["System Manager"]))
		self.assertEqual(api.refresh_customer(lone), [{"customer": lone}])
		self.assertTrue(frappe.db.exists("Card Equipment Customer", lone))
		done = api.refresh_customer()
		parties = [row["customer"] for row in done]
		self.assertEqual(done, [{"customer": party} for party in parties])
		self.assertEqual(parties, sorted(parties))
		self.assertIn(billed, parties)
		self.assertNotIn(draft_only, parties)
		self.assertNotIn(lone, parties)

	def test_party_figures_validates_the_party_type_and_the_party(self):
		party = self._supplier("PF")
		api.recompute_supplier(party)
		frappe.set_user(self._user(["Card User"]))
		with self.assertRaisesRegex(frappe.ValidationError, "Party type must be Supplier or Customer"):
			api.party_figures("Employee", party)
		with self.assertRaises(frappe.PermissionError):
			api.party_figures("Supplier", "TEST-RACC-NO-SUCH-PARTY-" + self.token)
		# a registered party without cards has no figures
		self.assertEqual(api.party_figures("Supplier", party), [])

	# ---------- H4: link queries and registry conditions for a company the user may not see ----------

	def test_party_link_queries_return_nothing_for_a_company_the_user_may_not_see(self):
		customer = self._customer("QN")
		self._card(self._equipment("QN1"), [10])
		self._card(self._equipment("QN2", customer=customer), [10])
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		for query, doctype, party in (
			(api.card_suppliers_query, "Supplier", self.supplier),
			(api.card_customers_query, "Customer", customer),
		):
			for filters in ({"company": self.other}, '{"company": "%s"}' % self.other):
				self.assertEqual(query(doctype, "", "name", 0, 500, filters), [], (doctype, filters))
			own = [row[0] for row in query(doctype, "", "name", 0, 500, {"company": self.company})]
			self.assertIn(party, own, doctype)

	def test_registry_conditions_name_only_the_permitted_company(self):
		from card.party_registry import customer_query_conditions, supplier_query_conditions

		unrestricted = self._user(["Card User"])
		restricted = self._user(["Card User"], restrict_to=self.company)
		# a user of one company gets a condition naming only that company,
		# an unrestricted user and the Administrator get none
		for condition in (supplier_query_conditions(restricted), customer_query_conditions(restricted)):
			self.assertIn(frappe.db.escape(self.company), condition)
			self.assertNotIn(frappe.db.escape(self.other), condition)
		for user in (unrestricted, "Administrator"):
			self.assertEqual(supplier_query_conditions(user), "")
			self.assertEqual(customer_query_conditions(user), "")

	# ---------- H5: which company a report runs for ----------

	def test_resolve_company_asks_for_a_company_when_several_are_visible(self):
		self.assertIn(self.other, permitted_companies())  # premise: more than one company
		with (
			patch("frappe.defaults.get_user_default", return_value=None),
			patch("frappe.defaults.get_global_default", return_value=None),
		):
			for filters in ({}, None, {"company": ""}):
				with self.assertRaisesRegex(frappe.ValidationError, "Select a company"):
					resolve_company(filters)
			self.assertEqual(resolve_company({"company": self.other}), self.other)

	def test_resolve_company_takes_a_default_only_when_permitted(self):
		restricted = self._user(["Card User"], restrict_to=self.company)
		with (
			patch("frappe.defaults.get_user_default", return_value=self.other),
			patch("frappe.defaults.get_global_default", return_value=None),
		):
			self.assertEqual(resolve_company({}), self.other)  # the user default is visible
			frappe.set_user(restricted)
			# the default is another company's: the only visible company is used instead
			self.assertEqual(resolve_company({}), self.company)
			frappe.set_user("Administrator")
		with (
			patch("frappe.defaults.get_user_default", return_value=None),
			patch("frappe.defaults.get_global_default", return_value=self.other),
		):
			self.assertEqual(resolve_company({}), self.other)  # then the global default
