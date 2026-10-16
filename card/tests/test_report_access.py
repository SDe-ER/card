# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Report access regression tests (issue #13): every CARD report runs for one
validated company, ledger figures reach only users whose own roles read
GL Entry, and the link-filter queries are role-checked and company-scoped.
No test grants an ERPNext permission — the point is that none is needed.
Cross-company rows are written raw into a second company label so the tests
need no second Company record; everything is rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card import api
from card.report_access import permitted_companies
from card.tests.test_controllers import _days, _ensure_masters

RENTED = "إيجار"
OTHER = "Other Isolated Co"
LEDGER_KEYS = {
	"equipment_suppliers_summary": {"accrued", "diff", "opening", "paid", "closing"},
	"equipment_customers_summary": {"invoiced", "diff", "opening", "received", "closing"},
}


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
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-RACC-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- helpers ----------

	def _user(self, roles, restrict_to=None, website=False):
		email = f"racc-{frappe.generate_hash(length=6)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Report Access",
				"send_welcome_email": 0,
				"user_type": "Website User" if website else "System User",
				"roles": [{"role": r} for r in roles],
			}
		)
		user.insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _rented_card(self, hours, submit=True):
		eq = frappe.new_doc("Card Equipment")
		eq.company = self.company
		eq.equipment_type = self._m["etype"]
		eq.ownership = RENTED
		eq.equipment_name = "TEST-RACC-EQ-" + self.token + frappe.generate_hash(length=4)
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		eq.supplier = self.supplier
		eq.insert(ignore_permissions=True)
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

	def _statement_filters(self, **kw):
		f = {
			"statement_type": "مورد",
			"supplier": self.supplier,
			"from_month": 9,
			"from_year": 2026,
			"project": self.project,
		}
		f.update(kw)
		return f

	# ---------- ledger gating ----------

	def test_card_user_statement_shows_card_figures_but_no_ledger(self):
		card = self._rented_card([10, 10])
		self._raw_gl(self.company, credit=999)
		frappe.set_user(self._user(["Card User"]))
		_cols, _rows, message, summary = _run("equipment_supplier_statement", self._statement_filters())
		self.assertEqual(flt(_value(summary, "Net cards")), flt(card.net_amount))
		self.assertNotIn(frappe._("Accrual entries (Credit)"), _labels(summary))
		self.assertNotIn(frappe._("Supplier closing balance"), _labels(summary))
		self.assertIn(
			frappe._("Ledger balances are shown only to users with General Ledger access."), message
		)

	def test_ledger_user_sees_only_own_company_entries(self):
		self._rented_card([10])
		self._raw_gl(self.company, credit=400)
		self._raw_gl(OTHER, credit=7000)
		_cols, _rows, _msg, summary = _run("equipment_supplier_statement", self._statement_filters())
		self.assertEqual(flt(_value(summary, "Accrual entries (Credit)")), 400.0)

	def test_summaries_drop_ledger_columns_and_values_for_card_user(self):
		self._rented_card([10])
		self._raw_gl(self.company, credit=999)
		frappe.set_user(self._user(["Card User"]))
		for module, keys in LEDGER_KEYS.items():
			cols, rows, _msg, summary = _run(module, {"from_month": 9, "from_year": 2026})
			self.assertFalse(keys & _fieldnames(cols), module)
			for row in rows:
				self.assertFalse(keys & set(row), module)
			self.assertNotIn(frappe._("Reconciliation difference"), _labels(summary), module)

	def test_customer_statement_hides_ledger_for_card_user(self):
		frappe.set_user(self._user(["Card User"]))
		_cols, _rows, message, summary = _run(
			"equipment_customer_statement", {"from_month": 9, "from_year": 2026, "customer": "x"}
		)
		self.assertNotIn(frappe._("Invoiced entries (Debit)"), _labels(summary))
		self.assertIn(
			frappe._("Ledger balances are shown only to users with General Ledger access."), message
		)

	def test_expenses_without_equipment_refuses_users_without_ledger(self):
		frappe.set_user(self._user(["Card User"]))
		with self.assertRaises(frappe.PermissionError):
			_run("equipment_expenses_without_equipment", {"company": self.company})

	# ---------- company scoping ----------

	def test_cards_of_another_company_are_not_listed(self):
		card = self._rented_card([10])
		frappe.db.set_value("Card Monthly Card", card.name, "company", OTHER, update_modified=False)
		_cols, rows, _msg, _summary = _run("equipment_supplier_statement", self._statement_filters())
		self.assertNotIn(card.name, [r.get("card") for r in rows])

	def test_restricted_user_is_refused_another_company(self):
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		self.assertEqual(permitted_companies(), [self.company])
		reports = {
			"equipment_supplier_statement": self._statement_filters(company=OTHER),
			"equipment_suppliers_summary": {"from_month": 9, "from_year": 2026, "company": OTHER},
			"equipment_customer_statement": {"from_month": 9, "from_year": 2026, "company": OTHER},
			"equipment_customers_summary": {"from_month": 9, "from_year": 2026, "company": OTHER},
			"equipment_diesel_analysis": {"from_month": 9, "from_year": 2026, "company": OTHER},
			"equipment_diesel_consumption": {"company": OTHER},
			"operating_cost_by_project": {"company": OTHER},
			"transport_cost_by_project": {"company": OTHER},
		}
		for module, filters in reports.items():
			with self.assertRaises(frappe.PermissionError, msg=module):
				_run(module, filters)

	def test_restricted_user_runs_permitted_company(self):
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		_cols, _rows, _msg, summary = _run(
			"equipment_suppliers_summary", {"from_month": 9, "from_year": 2026, "company": self.company}
		)
		self.assertIsNotNone(summary)

	# ---------- link-filter queries ----------

	def test_party_queries_refuse_users_without_card_role(self):
		frappe.set_user(self._user([], website=True))
		# real doctypes: the search decorator returns [] early for an unknown one
		for query, doctype in (
			(api.card_suppliers_query, "Supplier"),
			(api.card_customers_query, "Customer"),
			(api.card_projects_query, "Project"),
			(api.card_companies_query, "Company"),
		):
			with self.assertRaises(frappe.PermissionError, msg=doctype):
				query(doctype, "", "name", 0, 20, {})

	def test_queries_are_company_scoped(self):
		self._rented_card([10])
		frappe.set_user(self._user(["Card User"], restrict_to=self.company))
		suppliers = [r[0] for r in api.card_suppliers_query("Supplier", "", "name", 0, 50, {})]
		self.assertIn(self.supplier, suppliers)
		projects = [r[0] for r in api.card_projects_query("Project", "", "name", 0, 50, {})]
		self.assertIn(self.project, projects)
		companies = [r[0] for r in api.card_companies_query("Company", "", "name", 0, 50, {})]
		self.assertEqual(companies, [self.company])
		for query, doctype in (
			(api.card_suppliers_query, "Supplier"),
			(api.card_projects_query, "Project"),
			(api.card_customers_query, "Customer"),
		):
			self.assertEqual(list(query(doctype, "", "name", 0, 50, {"company": OTHER})), [], doctype)

	def test_card_roles_gain_no_erpnext_grants(self):
		frappe.set_user(self._user(["Card User"]))
		for doctype in ("GL Entry", "Project", "Supplier", "Customer"):
			self.assertFalse(frappe.has_permission(doctype, "read"), doctype)
