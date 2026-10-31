# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P1-2 (Owner decisions 2026-10-31, controlled QA scope): a transport records who pays the transporter,
who finally bears the cost and where the company's cost is charged — explicitly, never from the origin or
the destination; an Accounts Manager (not the creator or submitter) records the financial decision of a
customer- or supplier-borne move; customer billing, supplier recovery and the Purchase Invoice of these
transports stay disabled pending the accountant's and the tax adviser's decisions."""

import frappe
from frappe.utils import flt

from card.card.doctype.equipment_transport.equipment_transport import record_financial_decision
from card.card.report.transport_accounting_review.transport_accounting_review import execute as review
from card.gl.posting import _supplier_sources
from card.tests.test_p0_posting_integrity import _P0Base
from card.tests.transport_parties import as_recorded_before_p12, company_paid, paid_by


class TestTransportCostBearing(_P0Base):
	def _new(self, destination="Project", project="self", amount=400, place=None, items=True):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"date": "2026-09-10",
				"company": self.company,
				"transport_supplier": self.supplier,
				"destination_type": destination,
				"destination_location": place,
				"project": (self.project if project == "self" else project)
				if destination == "Project"
				else None,
				"amount": amount,
			}
		)
		if items:
			t.append("items", {"card_equipment": self._equipment().name})
		return t

	def _user(self, roles, company=None):
		email = f"p12-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "P12", "send_welcome_email": 0}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		if company:
			frappe.get_doc(
				{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": company}
			).insert(ignore_permissions=True)
		self.addCleanup(frappe.set_user, "Administrator")
		return email

	def _submitted(self, t):
		t.insert(ignore_permissions=True)
		t.submit()
		return t

	def _accountant(self):
		frappe.set_user(self._user(["Accounts Manager"]))

	# ---- responsibility is explicit
	def test_responsibility_is_required(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Transport responsibility|: responsibility"):
			self._new().insert(ignore_permissions=True)

	def test_one_choice_records_payer_bearer_and_eligibility(self):
		from card.card.doctype.equipment_transport.equipment_transport import RESPONSIBILITIES

		expected = {
			"Company pays, bills the customer": (1, 0, "Pending"),
			"Company pays, recovers from equipment supplier": (0, 1, "Pending"),
			"Equipment supplier bears the cost": (0, 0, "No decision needed"),
			"Customer pays the transporter directly": (0, 0, "No decision needed"),
			"No transport charge": (0, 0, "No decision needed"),
		}
		for scenario, (billable, recoverable, status) in expected.items():
			t = self._new()
			t.responsibility = scenario
			t.insert(ignore_permissions=True)
			self.assertEqual(
				(t.payer, t.cost_bearer or None, t.customer_billable, t.supplier_recoverable, t.financial_status),
				(*RESPONSIBILITIES[scenario], billable, recoverable, status),
				scenario,
			)

	def test_needs_review_is_recorded_without_cost_decision_or_posting(self):
		t = self._new()
		t.responsibility = "Responsibility needs review"
		self._submitted(t)
		self.assertEqual(
			(t.payer, t.cost_bearer, t.cost_project, t.cost_center, t.financial_status or None, flt(t.amount)),
			(None, None, None, None, None, 0),
		)
		_c, _f, transports = _supplier_sources(
			self.company, self.supplier, "2026-09-01", "2026-09-30", 9, 2026
		)
		self.assertNotIn(t.name, {x.name for x in transports})
		_c, rows, *_ = review({"company": self.company, "from_date": "2026-09-01", "to_date": "2026-09-30"})
		self.assertIn("needs review", {r["transport"]: r for r in rows}[t.name]["review"])

	def test_recharged_move_carries_no_cost_project(self):
		t = self._new()
		t.responsibility = "Company pays, bills the customer"
		t.cost_project = self.project  # ignored: the company does not finally bear this cost
		t.insert(ignore_permissions=True)
		self.assertEqual((t.cost_basis, t.cost_project, t.cost_center), (None, None, None))

	def test_company_borne_move_needs_its_cost_project(self):
		t = self._new()
		t.responsibility = "Company bears the cost"
		with self.assertRaisesRegex(
			frappe.ValidationError, "never taken from where the machine comes from or goes to"
		):
			t.insert(ignore_permissions=True)

	def test_cost_project_is_never_taken_from_the_destination(self):
		t = company_paid(self._new(), basis="Project", cost_project=None)
		with self.assertRaisesRegex(
			frappe.ValidationError, "never taken from where the machine comes from or goes to|Cost project"
		):
			t.insert(ignore_permissions=True)

	def test_chosen_cost_project_gives_its_cost_center(self):
		t = company_paid(self._new(), basis="Project", cost_project=self.project).insert(
			ignore_permissions=True
		)
		self.assertEqual(t.cost_center, frappe.db.get_value("Project", self.project, "cost_center"))

	def test_cost_project_of_another_company_is_refused(self):
		other = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "TEST-P12-X-" + self.token,
				"company": self._other_company(),
			}
		).insert(ignore_permissions=True)
		t = company_paid(self._new(), basis="Project", cost_project=other.name)
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to company"):
			t.insert(ignore_permissions=True)

	def _other_company(self):
		return frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name") or self.skipTest(
			"one company"
		)

	def test_overhead_cost_center_of_the_company(self):
		t = company_paid(self._new()).insert(ignore_permissions=True)
		self.assertEqual(t.cost_center, t.overhead_cost_center)

	def test_place_basis_is_never_used_for_a_move_to_a_project(self):
		# the place basis follows a move to a workshop or storage only; a project move needs its cost project
		t = company_paid(self._new(), basis="Workshop or storage")
		with self.assertRaisesRegex(frappe.ValidationError, "never taken from where the machine comes from"):
			t.insert(ignore_permissions=True)

	def test_company_paid_needs_a_transporter_and_a_cost(self):
		t = company_paid(self._new(amount=0))
		with self.assertRaisesRegex(frappe.ValidationError, "transporter cost"):
			t.insert(ignore_permissions=True)

	def test_unsupported_combinations_are_refused(self):
		for payer, bearer in (
			("Customer", "Company"),
			("Equipment Supplier", "Company"),
			("Equipment Supplier", "Customer"),
		):
			t = paid_by(self._new(), payer, bearer)
			with self.assertRaisesRegex(frappe.ValidationError, "is not supported", msg=(payer, bearer)):
				t.insert(ignore_permissions=True)

	def test_moves_the_company_does_not_pay_carry_no_cost(self):
		for payer in ("Customer", "Equipment Supplier", "No charge"):
			t = paid_by(self._new(), payer, payer if payer != "No charge" else None).insert(
				ignore_permissions=True
			)
			self.assertEqual(
				(flt(t.amount), t.cost_center, t.financial_status), (0, None, "No decision needed"), payer
			)

	def test_customer_or_supplier_borne_company_paid_move_needs_a_financial_decision(self):
		for bearer in ("Customer", "Equipment Supplier"):
			t = company_paid(self._new())
			t.cost_bearer = bearer
			t.insert(ignore_permissions=True)
			self.assertEqual(t.financial_status, "Pending", bearer)
		self.assertEqual(
			company_paid(self._new()).insert(ignore_permissions=True).financial_status, "No decision needed"
		)

	# ---- financial decision: Accounts Manager, separation of duties, audit
	def _pending(self, bearer="Customer"):
		t = company_paid(self._new())
		t.cost_bearer = bearer
		return self._submitted(t)

	def test_accounts_manager_records_customer_billing(self):
		t = self._pending()
		self._accountant()
		record_financial_decision(
			t.name,
			"Bill customer",
			customer=self.customer,
			billing_project=self.project,
			confirmed=1,
			billing_amount=650,
			billing_mode="Monthly invoice",
			billing_reference="CONTRACT-12/CL-7",
		)
		t.reload()
		self.assertEqual(
			(t.financial_status, t.financial_decision, t.customer, flt(t.billing_amount), flt(t.amount)),
			("Approved", "Bill customer", self.customer, 650, 400),  # the transporter cost is kept apart
		)
		comment = frappe.db.get_value(
			"Comment", {"reference_name": t.name, "comment_type": "Info"}, "content"
		)
		self.assertNotIn("650", comment)  # permlevel-1 money facts never in a comment every reader sees
		self.assertEqual(t.financial_approver, frappe.session.user)

	def test_billing_needs_the_accountants_confirmation(self):
		t = self._pending()
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "Confirm the customer and the billing project"):
			record_financial_decision(
				t.name,
				"Bill customer",
				customer=self.customer,
				billing_project=self.project,
				billing_amount=650,
				billing_reference="R",
			)

	def test_customer_comes_from_the_billing_project_and_monthly_is_the_default(self):
		frappe.db.set_value("Project", self.project, "customer", self.customer)
		t = self._pending()
		self._accountant()
		record_financial_decision(
			t.name,
			"Bill customer",
			billing_project=self.project,
			billing_amount=650,
			billing_reference="R",
			confirmed=1,
		)
		self.assertEqual(
			frappe.db.get_value("Equipment Transport", t.name, ["customer", "billing_mode"]),
			(self.customer, "Monthly invoice"),
		)

	def test_billing_suggestion_only_from_a_project_with_a_customer(self):
		from card.card.doctype.equipment_transport.equipment_transport import billing_customer

		t = self._pending()
		self._accountant()
		self.assertEqual(billing_customer(t.name), {})  # the destination project names no customer
		frappe.set_user("Administrator")
		frappe.db.set_value("Project", self.project, "customer", self.customer)
		self._accountant()
		self.assertEqual(billing_customer(t.name), {"project": self.project, "customer": self.customer})
		frappe.set_user(self._user(["Card Manager"]))
		with self.assertRaises(frappe.PermissionError):
			billing_customer(t.name)

	def test_separate_invoice_needs_the_authorization_document(self):
		t = self._pending()
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "authorization document of a separate invoice"):
			record_financial_decision(
				t.name,
				"Bill customer",
				customer=self.customer,
				billing_project=self.project,
				billing_amount=650,
				billing_reference="R",
				billing_mode="Separate invoice",
				confirmed=1,
			)

	def test_decision_leaves_a_version_without_permlevel_values(self):
		t = self._pending()
		self._accountant()
		record_financial_decision(
			t.name,
			"Bill customer",
			customer=self.customer,
			billing_project=self.project,
			billing_amount=650,
			billing_reference="CONTRACT-77",
			confirmed=1,
		)
		data = frappe.get_all(
			"Version", filters={"ref_doctype": "Equipment Transport", "docname": t.name}, pluck="data"
		)
		trail = [d for d in data if "financial_status" in d]
		self.assertEqual(len(trail), 1)
		self.assertIn("Approved", trail[0])
		self.assertNotIn("CONTRACT-77", trail[0])
		self.assertNotIn("650", trail[0])

	def test_billing_mode_is_required(self):
		t = self._pending()
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "monthly invoice or separately"):
			record_financial_decision(
				t.name,
				"Bill customer",
				customer=self.customer,
				billing_project=self.project,
				confirmed=1,
				billing_amount=650,
				billing_reference="R",
				billing_mode="Whenever",
			)

	def test_billing_needs_reference_amount_and_matching_project_customer(self):
		t = self._pending()
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "authorization reference"):
			record_financial_decision(
				t.name,
				"Bill customer",
				customer=self.customer,
				billing_project=self.project,
				confirmed=1,
				billing_amount=650,
			)
		with self.assertRaisesRegex(frappe.ValidationError, "agreed billing amount"):
			record_financial_decision(
				t.name,
				"Bill customer",
				customer=self.customer,
				billing_project=self.project,
				confirmed=1,
				billing_reference="R",
			)

	def test_absorption_needs_a_reason(self):
		t = self._pending()
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "why the company absorbs"):
			record_financial_decision(t.name, "Company absorbs")
		record_financial_decision(
			t.name, "Company absorbs", absorption_reason="Goodwill, approved by the owner"
		)
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "financial_status"), "Approved")

	def test_supplier_recovery_records_method_and_amount(self):
		t = self._pending("Equipment Supplier")
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "Bill customer|does not fit"):
			record_financial_decision(t.name, "Bill customer")
		record_financial_decision(
			t.name,
			"Recover from equipment supplier",
			recovery_mode="Deduct from monthly dues",
			recovery_amount=400,
		)
		self.assertEqual(
			frappe.db.get_value("Equipment Transport", t.name, "recovery_mode"), "Deduct from monthly dues"
		)

	def test_creator_or_submitter_cannot_decide(self):
		acm = self._user(["Accounts Manager", "Card Manager"])
		frappe.set_user(acm)
		t = company_paid(self._new())
		t.cost_bearer = "Customer"
		t.insert(ignore_permissions=True)
		t.submit()
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")

	def test_creator_alone_cannot_decide(self):
		acm = self._user(["Accounts Manager", "Card Manager"])
		frappe.set_user(acm)
		t = company_paid(self._new())
		t.cost_bearer = "Customer"
		t.insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		t.reload()
		t.submit()
		frappe.set_user(acm)
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")

	def test_submitter_alone_cannot_decide(self):
		t = company_paid(self._new())
		t.cost_bearer = "Customer"
		t.insert(ignore_permissions=True)
		acm = self._user(["Accounts Manager", "Card Manager"])
		frappe.set_user(acm)
		t.reload()
		t.submit()
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "submitted_by"), acm)
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")

	def test_creator_of_the_amended_transport_cannot_decide(self):
		acm = self._user(["Accounts Manager", "Card Manager"])
		frappe.set_user(acm)
		first = company_paid(self._new())
		first.cost_bearer = "Customer"
		first.insert(ignore_permissions=True)
		frappe.set_user("Administrator")
		first.reload()
		first.submit()
		first.cancel()
		amended = frappe.copy_doc(first, ignore_no_copy=False)
		amended.docstatus = 0
		amended.previous_assignment = amended.created_assignment = None  # header mirrors
		amended.amended_from = first.name
		amended.insert(ignore_permissions=True)
		amended.submit()
		frappe.set_user(acm)
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(amended.name, "Company absorbs", absorption_reason="x")

	def test_editor_of_the_draft_cannot_decide(self):
		t = company_paid(self._new())
		t.cost_bearer = "Customer"
		t.insert(ignore_permissions=True)
		acm = self._user(["Accounts Manager", "Card Manager"])
		frappe.set_user(acm)
		t.reload()
		t.remarks = "edited by the accountant"
		t.save()
		frappe.set_user("Administrator")
		t.reload()
		t.submit()
		frappe.set_user(acm)
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")

	def test_editors_come_from_the_stored_record_not_the_client(self):
		t = company_paid(self._new())
		t.cost_bearer = "Customer"
		t.insert(ignore_permissions=True)
		t.edited_by = "someone-else@example.com"
		t.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "edited_by"), "Administrator")

	def test_decision_fields_refused_through_set_value(self):
		from frappe.client import set_value as rest_set_value

		t = self._pending()
		frappe.set_user(self._user(["Card Manager"]))
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			rest_set_value("Equipment Transport", t.name, "financial_status", "Approved")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "financial_status"), "Pending")

	def test_p12_transport_cannot_be_linked_to_a_supplier_invoice(self):
		from card.gl.integrity import link_supplier_invoice

		paid = self._submitted(company_paid(self._new()))
		manual = self._manual_pi(400, submit=False)
		with self.assertRaisesRegex(frappe.ValidationError, "not enabled yet"):
			link_supplier_invoice(manual.name, [{"doctype": "Equipment Transport", "name": paid.name}])
		self.assertFalse(frappe.db.get_value("Equipment Transport", paid.name, "purchase_invoice"))

	def test_only_an_accounts_manager_decides(self):
		t = self._pending()
		frappe.set_user(self._user(["Card Manager"]))
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")

	def test_accounts_manager_of_another_company_is_refused(self):
		t = self._pending()
		frappe.set_user(self._user(["Accounts Manager"], company=self._other_company()))
		with self.assertRaises(frappe.PermissionError):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")

	def test_decision_cannot_be_changed_by_a_save(self):
		t = self._pending()
		t.reload()
		t.financial_status = "Approved"
		with self.assertRaisesRegex(frappe.ValidationError, "recorded by an Accounts Manager only"):
			t.save(ignore_permissions=True)

	def test_decision_only_once_and_only_when_pending(self):
		t = self._pending()
		self._accountant()
		record_financial_decision(t.name, "Return for correction", note="Wrong bearer")
		with self.assertRaisesRegex(frappe.ValidationError, "no pending financial decision"):
			record_financial_decision(t.name, "Company absorbs", absorption_reason="x")
		frappe.set_user("Administrator")
		done = company_paid(self._new())
		self._submitted(done)
		self._accountant()
		with self.assertRaisesRegex(frappe.ValidationError, "no pending financial decision"):
			record_financial_decision(done.name, "Return for correction", note="n/a")

	def test_cancel_and_amend_reset_the_decision(self):
		t = self._pending()
		self._accountant()
		record_financial_decision(t.name, "Company absorbs", absorption_reason="Owner approval")
		frappe.set_user("Administrator")
		t.reload()
		t.cancel()
		amended = frappe.copy_doc(t, ignore_no_copy=False)
		amended.docstatus = 0
		amended.previous_assignment = amended.created_assignment = None  # header mirrors
		amended.amended_from = t.name
		amended.insert(ignore_permissions=True)
		self.assertEqual(
			(
				amended.financial_status,
				amended.financial_decision or None,
				amended.absorption_reason,
				amended.submitted_by,
			),
			("Pending", None, None, None),
		)

	# ---- financial postings stay disabled
	def test_p12_transports_are_not_posted(self):
		paid = self._submitted(company_paid(self._new()))
		legacy = self._submitted(company_paid(self._new()))
		as_recorded_before_p12(legacy.name)
		_c, _f, transports = _supplier_sources(
			self.company, self.supplier, "2026-09-01", "2026-09-30", 9, 2026
		)
		names = {t.name for t in transports}
		self.assertNotIn(paid.name, names)
		self.assertIn(legacy.name, names)

	# ---- read-only review report
	def test_review_lists_legacy_pending_and_disabled_postings_without_writing(self):
		pending = self._pending()
		paid = self._submitted(company_paid(self._new()))
		legacy = self._submitted(company_paid(self._new()))
		as_recorded_before_p12(legacy.name)
		record_only = self._submitted(paid_by(self._new(), "Customer", "Customer"))
		before = frappe.db.get_value("Equipment Transport", pending.name, "modified")
		_c, rows, _m, _ch, summary = review(
			{"company": self.company, "from_date": "2026-09-01", "to_date": "2026-09-30"}
		)
		by = {r["transport"]: r for r in rows}
		self.assertIn("pending", by[pending.name]["review"])
		self.assertIn("Purchase Invoice posting waits", by[paid.name]["review"])
		self.assertIn("Recorded before P1-2", by[legacy.name]["review"])
		self.assertNotIn(record_only.name, by)  # needs no attention
		_c, rows, *_ = review(
			{"company": self.company, "from_date": "2026-09-01", "to_date": "2026-09-30", "show": "All"}
		)
		self.assertIn(record_only.name, {r["transport"] for r in rows})
		self.assertEqual(frappe.db.get_value("Equipment Transport", pending.name, "modified"), before)

	def test_review_needs_purchase_invoice_read(self):
		frappe.set_user(self._user(["Card Manager"]))
		with self.assertRaises(frappe.PermissionError):
			review({"company": self.company, "from_date": "2026-09-01", "to_date": "2026-09-30"})

	def test_cost_reports_use_the_chosen_cost_project_not_the_destination(self):
		from card.transport_costs import transport_cost_by_project

		other = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-P12-COST-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Project", other.name, "cost_center", frappe.db.get_value("Project", self.project, "cost_center")
		)
		self._submitted(company_paid(self._new(), basis="Project", cost_project=other.name))
		totals = transport_cost_by_project(self.company, "2026-09-01", "2026-09-30")
		self.assertEqual(flt(totals[other.name]["amount"]), 400)
		self.assertNotIn(self.project, totals)  # the destination is not the cost project
