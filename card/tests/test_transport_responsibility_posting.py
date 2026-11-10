# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-139 (#49, #126, #43; conflict C-09, owner decision O-14): per-company transport responsibility
posting. Hold (the default, and an empty value) keeps the P1-2 rule of 2026-10-31 exactly: a transport
recorded with a responsibility is never posted. Post adds it to the monthly DRAFT invoices through
standard documents: the transporter's Purchase Invoice line, the customer's Sales Invoice line from the
approved billing amount (never negative, ZATCA), and the equipment supplier's recovery as a deduction."""

import frappe
from frappe.utils import flt

from card.card.doctype.equipment_transport.equipment_transport import record_financial_decision
from card.gl import preflight
from card.gl.posting import (
	_supplier_sources,
	build_monthly_posting,
	month_parties,
	preview_monthly_posting,
)
from card.tests.cancel_reason import with_reason
from card.tests.test_p0_posting_integrity import _P0Base
from card.tests.test_s3_posting import _leaf_under
from card.tests.transport_parties import as_recorded_before_p12, company_paid

HOLD = preflight.TRANSPORT_POSTING_HOLD
POST = preflight.TRANSPORT_POSTING_POST

# the P1-2 query of card.gl.posting._supplier_sources as it stands on main before FR-139 (v4.7.0)
P12_FILTER_FIELDS = [
	"name",
	"transport_supplier",
	"cost_borne_by",
	"project",
	"amount",
	"date",
	"from_location",
	"to_location",
	"source_type",
	"source_project",
	"source_location",
	"destination_type",
	"destination_location",
	"cost_center",
]


def _p12_transports(company, party, first_day, last_day):
	return frappe.get_all(
		"Equipment Transport",
		filters={
			"docstatus": 1,
			"company": company,
			"transport_supplier": party,
			"date": ["between", [first_day, last_day]],
			"purchase_invoice": ["in", ["", None]],
			"cost_borne_by": ["in", ["Company", "", None]],
			"responsibility": ["in", ["", None]],
			"payer": ["in", ["", None]],
		},
		fields=P12_FILTER_FIELDS,
	)


class TestTransportResponsibilityPosting(_P0Base):
	def setUp(self):
		super().setUp()
		self.inc_transport = _leaf_under(self.company, "Income", "Test Transport Recharge Income")
		self._mode(None, account=self.inc_transport)
		# the billing project names the customer (P1-2 decision rule)
		frappe.db.set_value("Project", self.project, "customer", self.customer)

	# ---- fixtures
	def _mode(self, value, company=None, account=None):
		settings = frappe.get_doc("Card Settings")
		company = company or self.company
		row = next((r for r in settings.company_settings if r.company == company), None)
		if row is None:
			row = settings.append("company_settings", {"company": company})
		row.transport_responsibility_posting = value
		if account is not None:
			row.transport_recharge_income_account = account
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")

	def _new(self, amount=400, supplier=None, machines=1):
		t = frappe.new_doc("Equipment Transport")
		t.update(
			{
				"date": "2026-09-10",
				"company": self.company,
				"transport_supplier": supplier or self.supplier,
				"destination_type": "Project",
				"project": self.project,
				"amount": amount,
			}
		)
		for _i in range(machines):
			t.append("items", {"card_equipment": self._equipment().name})
		return t

	def _submitted(self, t):
		t.insert(ignore_permissions=True)
		t.submit()
		return t

	def _company_cost(self, **kw):
		return self._submitted(company_paid(self._new(**kw), basis="Project", cost_project=self.project))

	def _accountant(self):
		email = f"frt-{frappe.generate_hash(length=8)}@example.com"
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "FR139", "send_welcome_email": 0}
		)
		user.append("roles", {"role": "Accounts Manager"})
		user.insert(ignore_permissions=True)
		frappe.set_user(email)

	def _decided(self, bearer, decision, supplier=None, machines=1, **values):
		t = company_paid(self._new(supplier=supplier, machines=machines))
		t.cost_bearer = bearer
		self._submitted(t)
		self._accountant()
		try:
			record_financial_decision(t.name, decision, **values)
		finally:
			frappe.set_user("Administrator")
		t.reload()
		return t

	def _billed(self, mode="Monthly invoice", amount=650, machines=1):
		return self._decided(
			"Customer",
			"Bill customer",
			machines=machines,
			customer=self.customer,
			billing_project=self.project,
			billing_amount=amount,
			billing_mode=mode,
			billing_reference="CONTRACT-FR139",
			confirmed=1,
		)

	def _recovered(self, mode="Deduct from monthly dues", supplier=None, amount=150, machines=1):
		return self._decided(
			"Equipment Supplier",
			"Recover from equipment supplier",
			supplier=supplier,
			machines=machines,
			recovery_mode=mode,
			recovery_amount=amount,
		)

	def _sources(self):
		_c, _f, transports = _supplier_sources(
			self.company, self.supplier, "2026-09-01", "2026-09-30", 9, 2026
		)
		return transports

	def _pi(self):
		return frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)

	def _si(self):
		return frappe.get_doc(
			"Sales Invoice", build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		)

	def _transport_lines(self, inv, name):
		return [i for i in inv.items if name in (i.description or "")]

	# ---- the setting
	def test_hold_is_the_default_and_empty_means_hold(self):
		field = frappe.get_meta("Card Company Settings").get_field("transport_responsibility_posting")
		self.assertEqual(field.default, HOLD)
		self.assertEqual(field.options.split("\n"), [HOLD, POST])
		self.assertEqual(field.permlevel, 1)
		for value in (None, HOLD):
			self._mode(value)
			self.assertFalse(preflight.posts_transport_responsibility(self.company))
		self._mode(POST)
		self.assertTrue(preflight.posts_transport_responsibility(self.company))
		self.assertFalse(preflight.posts_transport_responsibility(None))

	# ---- Hold: byte-identical to the P1-2 rule
	def test_hold_returns_exactly_the_p12_query(self):
		paid = self._company_cost()
		legacy = self._company_cost()
		as_recorded_before_p12(legacy.name)
		billed = self._billed()
		recovered = self._recovered()
		for value in (None, HOLD):
			self._mode(value)
			got = self._sources()
			want = _p12_transports(self.company, self.supplier, "2026-09-01", "2026-09-30")
			self.assertEqual(frappe.as_json(got), frappe.as_json(want))
			names = {t.name for t in got}
			self.assertIn(legacy.name, names)
			self.assertFalse(names & {paid.name, billed.name, recovered.name})

	def test_hold_builds_no_transport_line_on_either_side(self):
		self._rental_card()
		billed = self._billed()
		paid = self._company_cost()
		pi = self._pi()
		self.assertFalse(self._transport_lines(pi, billed.name) or self._transport_lines(pi, paid.name))
		self.assertNotIn("Equipment Transport", {s.source_doctype for s in self._log(pi.name).sources})
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			self._si()
		parties = {(p["party_type"], p["party"]) for p in month_parties(self.company, 9, 2026)}
		self.assertNotIn(("Customer", self.customer), parties)

	# ---- Post: each responsibility scenario
	def test_post_company_cost_on_its_cost_project(self):
		self._mode(POST)
		t = self._company_cost()
		pi = self._pi()
		(line,) = self._transport_lines(pi, t.name)
		self.assertEqual(
			(flt(line.rate), line.project, line.cost_center, line.expense_account),
			(
				400,
				self.project,
				frappe.db.get_value("Project", self.project, "cost_center"),
				self.exp_transport,
			),
		)
		self.assertIn((t.name, 400), [(s.source_name, flt(s.amount)) for s in self._log(pi.name).sources])

	def test_post_company_cost_on_an_overhead_cost_center(self):
		self._mode(POST)
		t = self._submitted(company_paid(self._new()))
		(line,) = self._transport_lines(self._pi(), t.name)
		self.assertEqual((line.project or None, line.cost_center), (None, t.overhead_cost_center))

	def test_post_billed_customer_on_both_sides(self):
		self._mode(POST)
		t = self._billed()
		pi = self._pi()
		(cost,) = self._transport_lines(pi, t.name)
		project_cc = frappe.db.get_value("Project", self.project, "cost_center")
		self.assertEqual((flt(cost.rate), cost.project, cost.cost_center), (400, self.project, project_cc))
		si = self._si()
		(revenue,) = self._transport_lines(si, t.name)
		self.assertEqual(
			(flt(revenue.rate), revenue.income_account, revenue.project, revenue.cost_center),
			(650, self.inc_transport, self.project, project_cc),
		)
		self.assertTrue(all(flt(i.rate) >= 0 for i in si.items))  # ZATCA: no negative Sales Invoice line
		self.assertEqual(
			revenue.item_tax_template, preflight.company_settings_row(self.company).vat_item_tax_template
		)
		self.assertEqual(flt(si.total_taxes_and_charges), 97.5)  # the FR-127 company rate, not inferred
		self.assertEqual(
			[(s.source_doctype, s.source_name, flt(s.amount)) for s in self._log(si.name).sources],
			[("Equipment Transport", t.name, 650)],
		)

	def test_post_customer_line_needs_the_recharge_income_account(self):
		self._mode(POST, account="")
		self._billed()
		with self.assertRaisesRegex(frappe.ValidationError, "Transport recharge income account"):
			self._si()

	def test_post_separate_invoice_stays_off_the_monthly_sales_invoice(self):
		self._mode(POST)
		t = self._submitted(company_paid(self._new()))
		t.db_set("cost_bearer", "Customer")  # the decision below needs the customer as bearer
		frappe.db.set_value(
			"Equipment Transport",
			t.name,
			{
				"financial_status": "Approved",
				"financial_decision": "Bill customer",
				"customer": self.customer,
				"billing_project": self.project,
				"billing_amount": 650,
				"billing_mode": "Separate invoice",
				"cost_basis": None,
				"cost_project": None,
				"cost_center": None,
				"overhead_cost_center": None,
			},
		)
		self.assertTrue(self._transport_lines(self._pi(), t.name))  # the transporter is still paid
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			self._si()

	def test_post_recovery_from_the_transporter_is_a_deduction(self):
		self._mode(POST)
		t = self._recovered()
		self.assertEqual(t.equipment_supplier, self.supplier)
		pi = self._pi()
		lines = self._transport_lines(pi, t.name)
		self.assertEqual(sorted(flt(i.rate) for i in lines), [-150, 400])
		self.assertEqual({i.expense_account for i in lines}, {self.exp_transport})
		self.assertEqual({i.project or None for i in lines}, {None})
		self.assertEqual(
			{i.cost_center for i in lines}, {preflight.company_settings_row(self.company).cost_center}
		)
		self.assertIn((t.name, 250), [(s.source_name, flt(s.amount)) for s in self._log(pi.name).sources])

	def test_post_recovery_by_adjustment_document_pays_the_transporter_only(self):
		self._mode(POST)
		t = self._recovered(mode="Adjustment document")
		self.assertEqual([flt(i.rate) for i in self._transport_lines(self._pi(), t.name)], [400])

	def test_post_recovery_from_another_supplier_is_held_with_a_reason(self):
		self._mode(POST)
		transporter = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "TEST-FR139-TRN-" + self.token,
				"supplier_group": self._m["supplier_group"],
			}
		).insert(ignore_permissions=True)
		t = self._recovered(supplier=transporter.name)
		_c, _f, rows = _supplier_sources(self.company, transporter.name, "2026-09-01", "2026-09-30", 9, 2026)
		self.assertNotIn(t.name, {r.name for r in rows})
		self._company_cost(supplier=transporter.name)
		out = preview_monthly_posting(self.company, "Supplier", transporter.name, 9, 2026)
		self.assertFalse(out.blocked)
		self.assertTrue(any(t.name in w and "another supplier" in w for w in out.warnings))

	def test_post_holds_what_is_not_decided_or_not_paid(self):
		self._mode(POST)
		pending = company_paid(self._new())
		pending.cost_bearer = "Customer"
		pending = self._submitted(pending)
		absorbed = self._decided("Customer", "Company absorbs", absorption_reason="goodwill")
		rejected = self._decided("Customer", "Return for correction", note="wrong bearer")
		review = self._new()
		review.responsibility = "Responsibility needs review"
		review = self._submitted(review)
		direct = self._new()
		direct.responsibility = "Customer pays the transporter directly"
		direct = self._submitted(direct)
		names = {t.name for t in self._sources()}
		self.assertFalse(names & {pending.name, absorbed.name, rejected.name, review.name, direct.name})
		self._company_cost()
		warnings = preview_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026).warnings
		for t in (pending, absorbed, rejected):
			self.assertTrue(any(t.name in w for w in warnings), t.name)

	def test_post_legacy_transport_keeps_its_old_rule(self):
		self._mode(POST)
		legacy = self._company_cost()
		as_recorded_before_p12(legacy.name)
		# the P0-0 rule: a move without its cost project recorded is an exception for review
		with self.assertRaisesRegex(frappe.ValidationError, "which project bears this move"):
			self._pi()

	# ---- two companies
	def _other_company(self):
		name = "TEST-FR139-CO-" + self.token
		if not frappe.db.exists("Company", name):
			co = frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": name,
					"abbr": "F" + self.token[:6].upper(),
					"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"country": frappe.db.get_value("Company", self.company, "country"),
				}
			)
			co.name = name
			co.db_insert()
		return name

	def test_the_setting_is_per_company(self):
		other = self._other_company()
		t = self._company_cost()
		self._mode(HOLD)
		self._mode(POST, company=other)
		self.assertTrue(preflight.posts_transport_responsibility(other))
		self.assertFalse(preflight.posts_transport_responsibility(self.company))
		self.assertNotIn(t.name, {r.name for r in self._sources()})
		_c, _f, rows = _supplier_sources(other, self.supplier, "2026-09-01", "2026-09-30", 9, 2026)
		self.assertNotIn(t.name, {r.name for r in rows})  # never another company's transport
		self._mode(POST)
		self._mode(HOLD, company=other)
		self.assertIn(t.name, {r.name for r in self._sources()})

	def test_a_billing_project_of_another_company_is_refused(self):
		self._mode(POST)
		t = self._billed()
		other_project = frappe.get_doc(
			{
				"doctype": "Project",
				"project_name": "TEST-FR139-XP-" + self.token,
				"company": self._other_company(),
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Equipment Transport", t.name, "billing_project", other_project.name)
		with self.assertRaisesRegex(frappe.ValidationError, "does not belong to company"):
			self._si()

	# ---- duplicate guard
	def test_a_posted_transport_is_never_posted_twice(self):
		self._mode(POST)
		t = self._billed()
		pi = self._pi()
		with self.assertRaisesRegex(frappe.ValidationError, "A draft posting already exists"):
			self._pi()
		with self.assertRaisesRegex(frappe.ValidationError, "reserved by draft posting"):
			with_reason(frappe.get_doc("Equipment Transport", t.name)).cancel()
		pi.reload()
		pi.submit()
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "purchase_invoice"), pi.name)
		self.assertNotIn(t.name, {r.name for r in self._sources()})
		si = self._si()
		with self.assertRaisesRegex(frappe.ValidationError, "A draft posting already exists"):
			self._si()
		si.reload()
		si.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			self._si()
		customer = next(p for p in month_parties(self.company, 9, 2026) if p["party"] == self.customer)
		self.assertEqual((customer["status"], customer["pending_sources"]), ("Posted", 0))

	# ---- integrity snapshot and signature
	def test_built_drafts_carry_their_signature_and_refuse_an_edit(self):
		self._mode(POST)
		self._vat_supplier()
		t = self._recovered()
		pi = self._pi()
		log = self._log(pi.name)
		self.assertTrue(log.built_signature and log.lines_signature and log.built_snapshot)
		self.assertEqual(flt(pi.net_total), 250)
		self.assertEqual(flt(pi.total_taxes_and_charges), 37.5)  # 15% of the net, the FR-127 rate
		(deduction,) = [i for i in self._transport_lines(pi, t.name) if flt(i.rate) < 0]
		deduction.rate = -100
		pi.bill_no, pi.bill_date = "FR139-" + self.token, "2026-09-30"
		pi.save()
		with self.assertRaisesRegex(
			frappe.ValidationError, "differs from what CARD built|no longer matches|accept_correction"
		):
			pi.submit()

	def test_unchanged_drafts_submit_on_both_sides(self):
		self._mode(POST)
		t = self._billed()
		pi = self._pi()
		pi.submit()
		si = self._si()
		self.assertTrue(self._log(si.name).built_signature)
		si.submit()
		self.assertEqual((pi.docstatus, si.docstatus), (1, 1))
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "posted"), 1)

	# ---- review findings (F-1 .. F-7)
	def test_cancelling_the_purchase_invoice_keeps_a_customer_posted_transport_posted(self):
		"""F-1: Equipment Transport has no sales_invoice field; its customer side is read from the
		submitted Customer log."""
		self._mode(POST)
		t = self._billed()
		pi = self._pi()
		pi.submit()
		si = self._si()
		si.submit()
		pi.reload()
		pi.cancel()
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "posted"), 1)
		self.assertFalse(frappe.db.get_value("Equipment Transport", t.name, "purchase_invoice"))
		si.reload()
		si.cancel()
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "posted"), 0)

	def test_a_cancelled_posting_frees_the_transport_for_a_new_build(self):
		self._mode(POST)
		t = self._billed()
		pi = self._pi()
		pi.submit()
		pi.reload()
		pi.cancel()
		self.assertIn(t.name, {r.name for r in self._sources()})
		again = self._pi()
		self.assertNotEqual(again.name, pi.name)
		self.assertEqual([flt(i.rate) for i in self._transport_lines(again, t.name)], [400])
		again.submit()
		self.assertEqual(
			frappe.db.get_value("Equipment Transport", t.name, ["purchase_invoice", "posted"]),
			(again.name, 1),
		)
		si = self._si()
		si.submit()
		si.reload()
		si.cancel()
		self.assertEqual(frappe.db.get_value("Equipment Transport", t.name, "posted"), 1)  # PI still on
		si2 = self._si()
		self.assertEqual([flt(i.rate) for i in self._transport_lines(si2, t.name)], [650])

	def test_a_recovery_above_the_transport_cost_is_refused(self):
		"""F-2"""
		self._mode(POST)
		self._recovered(amount=500)
		with self.assertRaisesRegex(frappe.ValidationError, "more than the transport cost"):
			self._pi()

	def test_multi_machine_recovery_and_billing_follow_the_shares(self):
		"""F-3: the recovery and customer lines are split per machine like the cost lines; the parts add
		up to the amount exactly (remainder on the last machine)."""
		self._mode(POST)
		recovered = self._recovered(amount=100, machines=3)
		shares = [(r.card_equipment, flt(r.amount)) for r in recovered.items]
		self.assertEqual(round(sum(a for _e, a in shares), 2), 400)
		lines = self._transport_lines(self._pi(), recovered.name)
		costs = {i.card_equipment: flt(i.rate) for i in lines if flt(i.rate) > 0}
		deductions = {i.card_equipment: flt(i.rate) for i in lines if flt(i.rate) < 0}
		self.assertEqual(costs, dict(shares))
		self.assertEqual(set(deductions), {e for e, _a in shares})
		self.assertEqual(round(sum(deductions.values()), 2), -100)
		for equipment, share in shares[:-1]:
			self.assertEqual(deductions[equipment], -flt(100 * share / 400, 2))
		billed = self._billed(amount=650, machines=3)
		parts = {i.card_equipment: flt(i.rate) for i in self._transport_lines(self._si(), billed.name)}
		self.assertEqual(set(parts), {r.card_equipment for r in billed.items})
		self.assertEqual(round(sum(parts.values()), 2), 650)
		self.assertTrue(all(v > 0 for v in parts.values()))

	def test_the_recharge_account_must_be_an_income_account(self):
		"""F-5"""
		self._mode(POST, account=self.exp_transport)
		self._billed()
		with self.assertRaisesRegex(frappe.ValidationError, "must be an income account"):
			self._si()

	def test_a_cancelled_billing_project_is_refused(self):
		"""F-7"""
		self._mode(POST)
		self._billed()
		frappe.db.set_value("Project", self.project, "status", "Cancelled")
		with self.assertRaisesRegex(frappe.ValidationError, "is cancelled"):
			self._si()
