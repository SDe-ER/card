# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#43/#48/#121 (WP-14, FR-120): a move the equipment supplier, the customer or another named party pays
keeps the amount agreed with them as information only (`informational_amount`). It is never company
cost: not in the transport cost reports' totals, not in the partial margin, not in any posting. The new
"Other party bears the cost" responsibility names that party (party_type + party). Existing scenarios and
transports behave as before. Everything is rolled back."""

import frappe
from frappe.utils import flt

from card import analytics
from card.card.doctype.equipment_transport.equipment_transport import RESPONSIBILITIES
from card.card.report.equipment_partial_margin.equipment_partial_margin import execute as partial_margin
from card.card.report.operating_cost_by_project.operating_cost_by_project import execute as operating_cost
from card.card.report.transport_accounting_review.transport_accounting_review import execute as review
from card.card.report.transport_cost_by_project.transport_cost_by_project import execute as cost_report
from card.gl.posting import _supplier_sources
from card.tests.test_p0_posting_integrity import _P0Base
from card.tests.transport_parties import as_recorded_before_p12, company_paid
from card.transport_costs import (
	company_cost_project,
	not_company_cost_by_project,
	transport_cost_by_project,
)

OTHER = "Other party bears the cost"
PERIOD = {"from_date": "2026-09-01", "to_date": "2026-09-30"}
NOT_PAID = {
	"Equipment supplier bears the cost": ("Equipment Supplier", "Equipment Supplier"),
	"Customer pays the transporter directly": ("Customer", "Customer"),
	OTHER: ("Other Party", "Other Party"),
}


class TestTransportOtherParty(_P0Base):
	def _new(self, responsibility=OTHER, informational=900, party_type="Supplier", party="self", amount=0):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"date": "2026-09-10",
				"company": self.company,
				"transport_supplier": self.supplier,
				"destination_type": "Project",
				"project": self.project,
				"responsibility": responsibility,
				"amount": amount,
				"informational_amount": informational,
			}
		)
		if responsibility == OTHER:
			t.party_type = party_type
			t.party = (
				(self.supplier if party_type == "Supplier" else self.customer) if party == "self" else party
			)
		t.append("items", {"card_equipment": self._equipment().name})
		return t

	def _submitted(self, t):
		t.insert(ignore_permissions=True)
		t.submit()
		return t

	def _employee(self, company=None):
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		emp = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "WP14 Party " + self.token,
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		if company:
			frappe.db.set_value("Employee", emp.name, "company", company)
		return emp.name

	def _other_company(self):
		name = "TEST-WP14-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "W" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	# ---- each payer type
	def test_each_payer_type_keeps_the_agreed_amount_as_information_only(self):
		for scenario, pair in NOT_PAID.items():
			t = self._new(scenario, amount=500).insert(ignore_permissions=True)
			self.assertEqual(
				(
					(t.payer, t.cost_bearer),
					flt(t.informational_amount),
					flt(t.amount),
					sum(flt(r.amount) for r in t.items),
					t.cost_center,
					t.cost_project,
					t.customer_billable,
					t.supplier_recoverable,
					t.financial_status,
				),
				(pair, 900, 0, 0, None, None, 0, 0, "No decision needed"),
				scenario,
			)

	def test_other_party_scenario_maps_both_ways(self):
		self.assertEqual(RESPONSIBILITIES[OTHER], ("Other Party", "Other Party"))
		t = self._new(responsibility=None)
		t.responsibility = None
		t.payer, t.cost_bearer = "Other Party", "Other Party"
		t.party_type, t.party = "Customer", self.customer
		t.insert(ignore_permissions=True)
		self.assertEqual(t.responsibility, OTHER)

	def test_other_party_supplier_customer_and_employee(self):
		for party_type, party in (
			("Supplier", self.supplier),
			("Customer", self.customer),
			("Employee", self._employee()),
		):
			t = self._new(party_type=party_type, party=party).insert(ignore_permissions=True)
			self.assertEqual((t.party_type, t.party), (party_type, party))

	def test_other_party_must_be_named(self):
		t = self._new(party_type=None, party=None)
		with self.assertRaisesRegex(frappe.ValidationError, "type of the other party"):
			t.insert(ignore_permissions=True)
		t = self._new(party=None)
		t.party = None
		with self.assertRaisesRegex(frappe.ValidationError, "Select the other party"):
			t.insert(ignore_permissions=True)
		t = self._new(party_type="Company", party=self.company)
		with self.assertRaisesRegex(frappe.ValidationError, "type of the other party"):
			t.insert(ignore_permissions=True)

	def test_disabled_or_missing_other_party_is_refused(self):
		t = self._new(party="NO-SUCH-SUPPLIER-" + self.token)
		with self.assertRaises(frappe.ValidationError):
			t.insert(ignore_permissions=True)
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-WP14-PARTY-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		frappe.db.set_value("Supplier", sup.name, "disabled", 1)
		t = self._new(party=sup.name)
		with self.assertRaisesRegex(frappe.ValidationError, "is disabled"):
			t.insert(ignore_permissions=True)

	def test_negative_agreed_amount_is_refused(self):
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be negative"):
			self._new(informational=-5).insert(ignore_permissions=True)

	def test_agreed_amount_is_optional(self):
		t = self._new(informational=0).insert(ignore_permissions=True)
		self.assertEqual(flt(t.informational_amount), 0)

	# ---- company isolation
	def test_employee_of_another_company_is_refused(self):
		other = self._other_company()
		t = self._new(party_type="Employee", party=self._employee(company=other))
		with self.assertRaisesRegex(
			frappe.ValidationError, f"is not an employee of company {self.company}"
		) as caught:
			t.insert(ignore_permissions=True)
		self.assertNotIn(other, str(caught.exception))  # the other company is never named

	def test_employee_who_is_not_active_is_refused(self):
		for status in ("Left", "Inactive"):
			employee = self._employee()
			frappe.db.set_value("Employee", employee, "status", status)
			t = self._new(party_type="Employee", party=employee)
			with self.assertRaisesRegex(frappe.ValidationError, "is not active", msg=status):
				t.insert(ignore_permissions=True)

	def test_informational_amounts_stay_in_their_company(self):
		t = self._submitted(self._new())
		self.assertIn(self.project, not_company_cost_by_project(self.company, **PERIOD))
		other = self._other_company()
		self.assertNotIn(self.project, not_company_cost_by_project(other, **PERIOD))
		user = f"wp14-{frappe.generate_hash(length=8)}@example.com"
		doc = frappe.get_doc(
			{"doctype": "User", "email": user, "first_name": "WP14", "send_welcome_email": 0}
		)
		doc.append("roles", {"role": "Card Manager"})
		doc.insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Company", "for_value": other}
		).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(user)
		for report in (cost_report, operating_cost):
			with self.assertRaises(frappe.PermissionError):
				report({"company": self.company, **PERIOD})
		frappe.set_user("Administrator")
		self.assertTrue(t.name)

	# ---- never company cost, never posted, never in the margin
	def test_excluded_from_company_cost_and_shown_apart(self):
		paid = self._submitted(
			company_paid(
				self._new("Company bears the cost", 0, amount=400), basis="Project", cost_project=self.project
			)
		)
		other = self._submitted(self._new())
		self.assertIsNone(company_cost_project(frappe._dict(other.as_dict())))
		totals = transport_cost_by_project(self.company, **PERIOD)
		self.assertEqual((totals[self.project]["transports"], flt(totals[self.project]["amount"])), (1, 400))
		_c, data = cost_report({"company": self.company, **PERIOD})
		row = {r["project"]: r for r in data}[self.project]
		self.assertEqual(
			(row["transports"], row["amount"], row["not_company_transports"], row["not_company_cost"]),
			(1, 400, 1, 900),
		)
		_c, data = operating_cost({"company": self.company, **PERIOD})
		row = {r["project"]: r for r in data}[self.project]
		self.assertEqual(
			(row["transport"], row["total"] - row["diesel"], row["transport_not_company_cost"]),
			(400, 400, 900),
		)
		self.assertTrue(paid.name)

	def test_never_posted(self):
		t = self._submitted(self._new())
		_c, _f, transports = _supplier_sources(
			self.company, self.supplier, "2026-09-01", "2026-09-30", 9, 2026
		)
		self.assertNotIn(t.name, {x.name for x in transports})

	def test_excluded_from_the_analytics_margin(self):
		t = self._submitted(self._new())
		self.assertEqual(
			[r for r in analytics.transport_costs(self.company, "2026-09-01", "2026-09-30") if r[2] == 900],
			[],
		)
		_columns, data, _message, _chart, _summary = partial_margin(
			{"company": self.company, **PERIOD, "project": self.project}
		)
		self.assertEqual(sum(flt(r.get("transport")) for r in data), 0)
		self.assertNotIn(900, [flt(r.get("total_cost")) for r in data])
		self.assertTrue(t.name)

	def test_review_report_shows_it_as_record_only(self):
		t = self._submitted(self._new())
		_c, rows, *_ = review({"company": self.company, **PERIOD, "show": "All"})
		row = {r["transport"]: r for r in rows}[t.name]
		self.assertEqual((row["attention"], row["amount"], row["informational_amount"]), (0, 0, 900))
		self.assertIn(self.supplier, row["other_party"])

	def test_cancel_cannot_rewrite_the_agreed_amount(self):
		t = self._submitted(self._new())
		t.informational_amount = 50
		with self.assertRaisesRegex(frappe.ValidationError, "cancelled as approved"):
			t.cancel()

	def test_cancel_cannot_rewrite_the_other_party(self):
		for change in ("party_type and party", "party only"):
			t = self._submitted(self._new())
			if change == "party_type and party":
				t.party_type, t.party = "Customer", self.customer
			else:
				sup = frappe.new_doc("Supplier")
				sup.supplier_name = "TEST-WP14-CANCEL-" + frappe.generate_hash(length=6)
				sup.supplier_group = self._m["supplier_group"]
				sup.insert(ignore_permissions=True)
				t.party = sup.name
			with self.assertRaisesRegex(frappe.ValidationError, "cancelled as approved", msg=change):
				t.cancel()
			self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "docstatus"), 1)

	# ---- existing behaviour unchanged
	def test_company_paid_moves_keep_no_agreed_amount_or_party(self):
		for scenario in (
			"Company bears the cost",
			"Company pays, bills the customer",
			"Company pays, recovers from equipment supplier",
		):
			t = company_paid(self._new(scenario, amount=400), basis="Project", cost_project=self.project)
			t.party_type, t.party = "Supplier", self.supplier
			t.insert(ignore_permissions=True)
			self.assertEqual(
				(flt(t.amount), flt(t.informational_amount), t.party_type, t.party),
				(400, 0, None, None),
				scenario,
			)

	def test_no_charge_and_needs_review_keep_no_agreed_amount(self):
		for scenario in ("No transport charge", "Responsibility needs review"):
			t = self._new(scenario).insert(ignore_permissions=True)
			self.assertEqual((flt(t.informational_amount), t.party), (0, None), scenario)

	def test_transport_recorded_before_p12_is_unchanged(self):
		t = self._submitted(
			company_paid(
				self._new("Company bears the cost", 0, amount=400), basis="Project", cost_project=self.project
			)
		)
		as_recorded_before_p12(t.name)
		self.assertEqual(flt(transport_cost_by_project(self.company, **PERIOD)[self.project]["amount"]), 400)
		self.assertNotIn(self.project, not_company_cost_by_project(self.company, **PERIOD))

	def test_agreed_amount_sent_on_a_company_paid_transport_is_cleared(self):
		t = company_paid(
			self._new("Company bears the cost", informational=750, amount=400),
			basis="Project",
			cost_project=self.project,
		).insert(ignore_permissions=True)
		self.assertEqual((flt(t.amount), flt(t.informational_amount)), (400, 0))
		t.informational_amount = 750  # sent again on a later save
		t.save(ignore_permissions=True)
		self.assertEqual(flt(frappe.db.get_value("Equipment Transport", t.name, "informational_amount")), 0)

	def test_agreed_amount_sent_on_a_transport_recorded_before_p12_is_cleared(self):
		t = company_paid(
			self._new("Company bears the cost", informational=0, amount=400),
			basis="Project",
			cost_project=self.project,
		).insert(ignore_permissions=True)
		as_recorded_before_p12(t.name)
		t = frappe.get_doc("Equipment Transport", t.name)
		self.assertFalse(t.responsibility)
		t.informational_amount = 750
		t.run_method("validate")  # the controller rule of a transport with no responsibility
		self.assertEqual(flt(t.informational_amount), 0)
