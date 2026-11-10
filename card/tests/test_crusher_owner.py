# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Third-party equipment owners (Owner 2026-11-10): ownership x direction, owner terms, the customer
approval of conditional additions, owner deductions and the Crusher Owner Statement. Synthetic data
only; the amounts follow the October cards of the brief (9 days x 2,500 + a 17,000 addition)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card import owner_statement as os_
from card.constants import (
	DIR_INTERNAL,
	DIR_RENTED_IN,
	DIR_RENTED_OUT,
	DIR_SUBRENTAL,
	OWNED,
	OWNER_MODEL_MANAGED,
	OWNER_MODEL_SELF,
	THIRD_PARTY,
	allowed_directions,
)
from card.tests import sample_files
from card.tests.test_controllers import _days, _ensure_masters

RENTED = "إيجار"
ADD = "إضافة"
DED = "خصم"
GENERATOR = "Generator rental 17-09 to 20-10 (34 days x 500)"


class TestAllowedDirections(IntegrationTestCase):
	def test_every_ownership_direction_pair(self):
		expected = {
			OWNED: {DIR_RENTED_OUT, DIR_INTERNAL},
			RENTED: {DIR_RENTED_IN, DIR_SUBRENTAL},
			THIRD_PARTY: {DIR_RENTED_OUT, DIR_RENTED_IN, DIR_SUBRENTAL},
		}
		for ownership, allowed in expected.items():
			for direction in (DIR_RENTED_IN, DIR_RENTED_OUT, DIR_SUBRENTAL, DIR_INTERNAL):
				with self.subTest(ownership=ownership, direction=direction):
					self.assertEqual(direction in allowed_directions(ownership), direction in allowed)


class OwnerFixtures(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TEST-COS-PRJ-" + self.token,
					"status": "Open",
					"company": self.company,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self.customer = self._customer()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# ---- builders ----
	def _customer(self):
		cust = frappe.new_doc("Customer")
		cust.customer_name = "TEST-COS-CUST-" + self.token
		cust.customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		cust.territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		cust.insert(ignore_permissions=True)
		return cust.name

	def _supplier(self, suffix):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-COS-SUP-" + self.token + suffix
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _cost_center(self, suffix):
		root = frappe.db.get_value(
			"Cost Center",
			{"company": self.company, "is_group": 1, "parent_cost_center": ["is", "not set"]},
			"name",
		)
		cc = frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": "TEST-COS-CC-" + self.token + suffix,
				"parent_cost_center": root,
				"company": self.company,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
		return cc.name

	def _equipment(self, owner, model=OWNER_MODEL_MANAGED, cost_center=None, rate=2500, since="2026-09-01"):
		eq = frappe.new_doc("Card Equipment")
		eq.company = self.company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-COS-EQ-" + frappe.generate_hash(length=6)
		eq.ownership = THIRD_PARTY
		eq.supplier = owner
		eq.owner_model = model
		eq.owner_entitlement_from = since
		eq.rental_direction = DIR_RENTED_OUT
		eq.default_customer = self.customer
		eq.customer_rate_type = "باليوم"
		eq.customer_rate = rate
		eq.daily_hours = 10
		eq.cost_center = cost_center
		eq.insert(ignore_permissions=True)
		return eq

	def _card(self, eq, rows=(), submit=True, month="09", days=9, operator=None):
		card = frappe.new_doc("Card Monthly Card")
		card.equipment = eq.name
		card.project = self.project
		card.month = month
		card.year = 2026
		if operator:
			card.operator = operator
		for row in _days([10] * days, month=int(month)):
			card.append("days", row)
		for row in rows:
			card.append("adjustments", row)
		card.insert(ignore_permissions=True)
		if submit:
			card.submit()
		return card

	def _generator_row(self, amount=17000):
		return {"side": "Customer", "adjustment_type": ADD, "description": GENERATOR, "amount": amount}

	def _evidence(self):
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "approval-" + self.token + ".pdf",
				"is_private": 1,
				"content": sample_files.pdf(self.token),
			}
		).insert(ignore_permissions=True)
		return f.file_url

	def _approval(self, card, status="Pending", approved=None, evidence=True):
		doc = frappe.get_doc(
			{
				"doctype": "Card Owner Revenue Approval",
				"monthly_card": card.name,
				"adjustment_row": card.adjustments[0].name,
				"approval_status": status,
				"approved_amount": approved,
				"approval_date": "2026-10-25" if status != "Pending" else None,
				"evidence": self._evidence() if evidence and status != "Pending" else None,
			}
		)
		return doc.insert(ignore_permissions=True)

	def _account(self, **filters):
		rows = frappe.get_all(
			"Account",
			filters={"company": self.company, "is_group": 0, "freeze_account": ["!=", "Yes"], **filters},
			fields=["name", "account_type"],
			order_by="lft asc",
		)
		return rows

	def _expense_account(self):
		diesel = os_.excluded_expense_accounts(self.company)
		for row in self._account(root_type="Expense"):
			if (row.account_type or "") in ("", "Expense Account", "Chargeable") and row.name not in diesel:
				return row.name
		self.skipTest("the test company has no plain expense account")

	def _payable(self):
		rows = self._account(account_type="Payable")
		if not rows:
			self.skipTest("the test company has no payable account")
		return rows[0].name

	def _bank(self):
		rows = self._account(account_type=["in", ["Bank", "Cash"]])
		if not rows:
			self.skipTest("the test company has no bank or cash account")
		return rows[0].name

	def _je(self, lines, date="2026-09-20"):
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": date,
				"voucher_type": "Journal Entry",
				"accounts": lines,
			}
		)
		je.insert(ignore_permissions=True)
		je.submit()
		return je

	def _owner_line(self, owner, debit=0, credit=0, account=None):
		return {
			"account": account or self._payable(),
			"party_type": "Supplier",
			"party": owner,
			"debit_in_account_currency": debit,
			"credit_in_account_currency": credit,
		}

	def _statement(self, owners, **kw):
		return os_.build_statement(self.company, owners, "2026-09-01", "2026-09-30", **kw)


class TestOwnerTerms(OwnerFixtures):
	def test_third_party_needs_its_owner_and_model(self):
		owner = self._supplier("-A")
		eq = frappe.new_doc("Card Equipment")
		eq.update(
			{
				"company": self.company,
				"equipment_type": self._m["etype"],
				"equipment_name": "TEST-COS-EQ-" + self.token,
				"ownership": THIRD_PARTY,
				"rental_direction": DIR_RENTED_OUT,
				"default_customer": self.customer,
				"customer_rate_type": "باليوم",
				"customer_rate": 2500,
				"daily_hours": 10,
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "owner"):
			eq.insert(ignore_permissions=True)
		eq.supplier = owner
		with self.assertRaisesRegex(frappe.ValidationError, "owner model"):
			eq.insert(ignore_permissions=True)
		eq.owner_model = OWNER_MODEL_SELF
		eq.insert(ignore_permissions=True)
		self.assertEqual(eq.rental_direction, DIR_RENTED_OUT)

	def test_owner_terms_are_cleared_for_another_ownership(self):
		eq = frappe.new_doc("Card Equipment")
		eq.update(
			{
				"company": self.company,
				"equipment_type": self._m["etype"],
				"equipment_name": "TEST-COS-EQ-" + self.token,
				"ownership": OWNED,
				"owner_model": OWNER_MODEL_MANAGED,
				"owner_entitlement_from": "2026-10-01",
				"daily_hours": 10,
			}
		)
		eq.insert(ignore_permissions=True)
		self.assertFalse(eq.owner_model)
		self.assertFalse(eq.owner_entitlement_from)

	def test_rented_out_third_party_card_bills_the_customer_only(self):
		owner = self._supplier("-A")
		eq = self._equipment(owner)
		card = self._card(eq, [self._generator_row()])
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertEqual(flt(card.customer_amount), 22500)
		self.assertEqual(flt(card.customer_net_amount), 39500)
		self.assertEqual(flt(card.amount), 0)  # no supplier billing, no Purchase Invoice
		self.assertEqual(card.supplier, owner)
		self.assertEqual(card.owner_model, OWNER_MODEL_MANAGED)

	def test_rented_out_cards_are_not_in_the_supplier_statement(self):
		from card.card.report.equipment_supplier_statement.equipment_supplier_statement import execute

		owner = self._supplier("-A")
		self._card(self._equipment(owner), [self._generator_row()])
		result = execute(
			{
				"company": self.company,
				"statement_type": "مورد",
				"supplier": owner,
				"from_month": "09",
				"from_year": 2026,
			}
		)
		self.assertFalse([r for r in result[1] if r.get("card")])

	def test_a_card_without_customer_rate_is_not_submitted(self):
		owner = self._supplier("-A")
		eq = self._equipment(owner, rate=0)  # the equipment may wait for its rate
		card = self._card(eq, submit=False)
		with self.assertRaisesRegex(frappe.ValidationError, "customer rate"):
			card.submit()


class TestRevenueApproval(OwnerFixtures):
	def setUp(self):
		super().setUp()
		self.owner = self._supplier("-A")
		self.card = self._card(self._equipment(self.owner), [self._generator_row()], submit=False)

	def test_states_and_amounts(self):
		pending = self._approval(self.card)
		self.assertEqual(flt(pending.gross_amount), 17000)
		self.assertEqual(flt(pending.approved_amount), 0)
		self.assertEqual(pending.owner_supplier, self.owner)
		evidence = self._evidence()

		def save(**values):
			doc = frappe.get_doc("Card Owner Revenue Approval", pending.name)
			doc.update(values)
			doc.save(ignore_permissions=True)
			return doc

		with self.assertRaisesRegex(frappe.ValidationError, "date"):
			save(approval_status="Approved")
		with self.assertRaisesRegex(frappe.ValidationError, "evidence"):
			save(approval_status="Approved", approval_date="2026-10-25")
		doc = save(approval_status="Approved", approval_date="2026-10-25", evidence=evidence)
		self.assertEqual(flt(doc.approved_amount), 17000)
		with self.assertRaisesRegex(frappe.ValidationError, "partial"):
			save(approval_status="Partially approved", approved_amount=17000)
		doc = save(approval_status="Partially approved", approved_amount=12000)
		self.assertEqual(flt(doc.approved_amount), 12000)
		self.assertEqual(flt(save(approval_status="Rejected").approved_amount), 0)

	def test_one_record_per_card_row(self):
		self._approval(self.card)
		with self.assertRaisesRegex(frappe.ValidationError, "already has approval"):
			self._approval(self.card)

	def test_only_a_customer_addition_row(self):
		self.card.append(
			"adjustments", {"side": "Customer", "adjustment_type": DED, "description": "x", "amount": 10}
		)
		self.card.save(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Card Owner Revenue Approval",
				"monthly_card": self.card.name,
				"adjustment_row": self.card.adjustments[1].name,
			}
		)
		with self.assertRaisesRegex(frappe.ValidationError, "customer-side addition"):
			doc.insert(ignore_permissions=True)

	def test_card_user_reads_but_does_not_write(self):
		perms = {p.role: p for p in frappe.get_meta("Card Owner Revenue Approval").permissions}
		self.assertTrue(perms["Card User"].read)
		self.assertFalse(perms["Card User"].write)
		self.assertFalse(perms["Card User"].create)
		self.assertTrue(perms["Card Manager"].write)

	def test_a_user_who_cannot_read_the_card_cannot_record_it(self):
		email = f"cos-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "COS",
				"send_welcome_email": 0,
				"roles": [{"role": "Card Manager"}],
			}
		).insert(ignore_permissions=True)
		other = frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name")
		if not other:
			self.skipTest("one company only")
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Company", "for_value": other}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		doc = frappe.get_doc(
			{
				"doctype": "Card Owner Revenue Approval",
				"monthly_card": self.card.name,
				"adjustment_row": self.card.adjustments[0].name,
			}
		)
		with self.assertRaises(frappe.PermissionError):
			doc.insert()


class TestCardRevenue(IntegrationTestCase):
	"""The split of one card's customer net (pure rules, no database rows)."""

	def _card(self):
		return frappe._dict(customer_amount=22500, customer_net_amount=39500)

	def _row(self, name="r1", amount=17000, kind=ADD, ref=None):
		return frappe._dict(
			name=name, side="Customer", adjustment_type=kind, amount=amount, adjustment_type_ref=ref
		)

	def _approval(self, status, approved=0, gross=17000):
		return frappe._dict(
			name="COA-1", approval_status=status, approved_amount=approved, gross_amount=gross
		)

	def test_generator_states_never_double_count(self):
		cases = {
			"Pending": (22500, 17000, 0),
			"Approved": (39500, 0, 0),
			"Partially approved": (34500, 0, 5000),
			"Rejected": (22500, 0, 17000),
		}
		for status, (confirmed, pending, excluded) in cases.items():
			with self.subTest(status=status):
				approved = {"Approved": 17000, "Partially approved": 12000}.get(status, 0)
				out = os_.card_revenue(
					self._card(), [self._row()], {"r1": self._approval(status, approved)}, set()
				)
				self.assertEqual(out.confirmed, confirmed)
				self.assertEqual(out.pending, pending)
				self.assertEqual(out.excluded, excluded)
				self.assertEqual(out.check, 0)  # the customer net is explained exactly once

	def test_without_approval_record_the_row_is_the_companys(self):
		out = os_.card_revenue(self._card(), [self._row()], {}, set())
		self.assertEqual(out.confirmed, 22500)
		self.assertEqual(out.unclassified, 17000)
		self.assertEqual(out.check, 0)

	def test_flagged_types_change_owner_revenue_both_ways(self):
		card = frappe._dict(customer_amount=22500, customer_net_amount=22500 - 500 + 750)
		rows = [self._row("b", 500, DED, "Breakdown"), self._row("x", 750, ADD, "Extra hours")]
		out = os_.card_revenue(card, rows, {}, {"Breakdown", "Extra hours"})
		self.assertEqual(out.confirmed, 22750)
		self.assertEqual(out.check, 0)

	def test_row_changed_after_approval_uses_the_smaller_amount(self):
		out = os_.card_revenue(
			frappe._dict(customer_amount=22500, customer_net_amount=37500),
			[self._row(amount=15000)],
			{"r1": self._approval("Approved", 17000, 17000)},
			set(),
		)
		self.assertTrue(out.approval_mismatch)
		self.assertEqual(out.approved, 15000)


class TestClassify(IntegrationTestCase):
	def _line(self, **kw):
		return frappe._dict(
			{"name": "L1", "party": "OWNER", "debit": 0, "credit": 0, "voucher_type": "Journal Entry", **kw}
		)

	def _row(self, account, party=None, name="R"):
		return frappe._dict(name=name, account=account, party_type="Supplier" if party else None, party=party)

	def test_not_every_debit_is_a_payment(self):
		def acc(account_type, root_type):
			return frappe._dict(account_type=account_type, root_type=root_type)

		types = {
			"Bank": acc("Bank", "Asset"),
			"Expense": acc(None, "Expense"),
			"Payable2": acc("Payable", "Liability"),
			"OwnerCurrent": acc(None, "Equity"),
		}
		line = self._line(debit=100)
		self.assertEqual(os_.classify(line, [line, self._row("Bank")], types)[0], os_.PAYMENT)
		self.assertEqual(os_.classify(line, [line, self._row("Expense")], types)[0], os_.RECHARGE)
		self.assertEqual(os_.classify(line, [line, self._row("Payable2", "OWNER")], types)[0], os_.RECLASS)
		kind, other = os_.classify(line, [line, self._row("Payable2", "BROTHER")], types)
		self.assertEqual((kind, other), (os_.TRANSFER, "BROTHER"))
		# paid through the owner's current account: a settlement, never a recharge
		self.assertEqual(
			os_.classify(line, [line, self._row("OwnerCurrent")], types), (os_.PAYMENT, "OwnerCurrent")
		)
		credit = self._line(credit=100)
		self.assertEqual(os_.classify(credit, [credit, self._row("Expense")], types)[0], os_.ACCRUAL)
		pi = self._line(voucher_type="Purchase Invoice", credit=5)
		self.assertEqual(os_.classify(pi, [], types)[0], os_.ACCRUAL)
		pe = self._line(voucher_type="Payment Entry", debit=5)
		self.assertEqual(os_.classify(pe, [], types)[0], os_.PAYMENT)


class TestOwnerStatement(OwnerFixtures):
	def test_owner_filter_returns_all_the_owners_crushers(self):
		owner = self._supplier("-NB")
		other = self._supplier("-X")
		a, b = self._equipment(owner), self._equipment(owner)
		self._equipment(other)
		for eq in (a, b):
			self._card(eq)
		s = self._statement([owner], show_ledger=False, show_wages=False)
		self.assertEqual({m.name for m in s.machines}, {a.name, b.name})
		self.assertEqual(s.owners[owner].entitlement, 45000)

	def test_drafts_and_pending_are_never_in_the_dues(self):
		owner = self._supplier("-A")
		eq = self._equipment(owner)
		card = self._card(eq, [self._generator_row()], submit=False)
		self._approval(card)
		s = self._statement([owner], show_ledger=False, show_wages=False)
		self.assertEqual(s.owners[owner].entitlement, 0)
		self.assertFalse(s.months[0].final)
		card.reload()
		card.submit()
		s = self._statement([owner], show_ledger=False, show_wages=False)
		self.assertEqual(s.owners[owner].entitlement, 22500)
		self.assertEqual(s.owners[owner].pending, 17000)

	def test_managed_partner_expenses_exclude_diesel_and_net_a_recharge_once(self):
		owner = self._supplier("-N")
		cc = self._cost_center("-8")
		eq = self._equipment(owner, cost_center=cc)
		self._card(eq)
		expense = self._expense_account()
		bank = self._bank()
		self._je(
			[
				{"account": expense, "debit_in_account_currency": 1000, "cost_center": cc},
				{"account": bank, "credit_in_account_currency": 1000},
			]
		)
		# the owner is recharged 300 of it: the expense credit on the crusher's cost center nets it
		self._je(
			[
				self._owner_line(owner, debit=300),
				{"account": expense, "credit_in_account_currency": 300, "cost_center": cc},
			]
		)
		s = self._statement([owner], show_wages=False)
		month = s.months[0]
		self.assertEqual(month.expenses, 700)
		o = s.owners[owner]
		self.assertEqual(o[os_.RECHARGE], -300)
		self.assertEqual(o.entitlement, 22500 - 700)
		self.assertEqual(o.closing, 22500 - 700 - 300)  # 1000 deducted once in all

	def test_self_operating_owner_bears_only_documented_amounts(self):
		owner = self._supplier("-M")
		cc = self._cost_center("-B")
		eq = self._equipment(owner, model=OWNER_MODEL_SELF, cost_center=cc)
		self._card(eq)
		expense, bank = self._expense_account(), self._bank()
		source = self._je(
			[
				{"account": expense, "debit_in_account_currency": 4000, "cost_center": cc},
				{"account": bank, "credit_in_account_currency": 4000},
			]
		)
		line = frappe.get_doc(
			{
				"doctype": "Card Owner Deduction",
				"equipment": eq.name,
				"posting_date": "2026-09-20",
				"deduction_type": "Paid on behalf",
				"amount": 2500,
				"source_doctype": "Journal Entry",
				"source_name": source.name,
			}
		).insert(ignore_permissions=True)
		line.submit()
		s = self._statement([owner], show_wages=False)
		self.assertEqual(s.months[0].expenses, 0)  # the cost center is not the owner's
		self.assertEqual(s.owners[owner].entitlement, 22500 - 2500)
		over = frappe.copy_doc(line)
		over.docstatus = 0
		over.amount = 1600  # 2,500 + 1,600 > 4,000
		over.insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "more than the document amount"):
			over.submit()

	def test_a_shared_expense_is_only_for_a_managed_partner(self):
		eq = self._equipment(self._supplier("-M"), model=OWNER_MODEL_SELF)
		source = self._je(
			[
				{
					"account": self._expense_account(),
					"debit_in_account_currency": 10,
					"cost_center": frappe.get_cached_value("Company", self.company, "cost_center"),
				},
				{"account": self._bank(), "credit_in_account_currency": 10},
			]
		)
		with self.assertRaisesRegex(frappe.ValidationError, "managed partner"):
			frappe.get_doc(
				{
					"doctype": "Card Owner Deduction",
					"equipment": eq.name,
					"posting_date": "2026-09-20",
					"deduction_type": "Shared expense",
					"amount": 10,
					"source_doctype": "Journal Entry",
					"source_name": source.name,
				}
			).insert(ignore_permissions=True)

	def test_manual_accrual_after_cut_over_is_counted_once(self):
		owner = self._supplier("-NJ")
		self._card(self._equipment(owner, cost_center=self._cost_center("-NJ")))
		expense = self._expense_account()
		default_cc = frappe.get_cached_value("Company", self.company, "cost_center")
		self._je(
			[
				{"account": expense, "debit_in_account_currency": 22500, "cost_center": default_cc},
				self._owner_line(owner, credit=22500),
			]
		)
		# booked as an expense of the machine itself (as the manual owner accruals are): still not a
		# machine expense
		cc = frappe.db.get_value("Card Equipment", {"supplier": owner}, "cost_center")
		self._je(
			[
				{"account": expense, "debit_in_account_currency": 5000, "cost_center": cc},
				self._owner_line(owner, credit=5000),
			]
		)
		s = self._statement([owner], show_wages=False)
		o = s.owners[owner]
		self.assertEqual(s.months[0].expenses, 0)
		self.assertEqual(o.duplicate_accruals, 27500)
		self.assertEqual(o.closing, 22500)  # the card only

	def test_family_payment_is_not_one_members_payment(self):
		family = self._m["supplier_group"]
		nasser, mohammed = self._supplier("-NS"), self._supplier("-MD")
		for owner in (nasser, mohammed):
			self._card(self._equipment(owner, model=OWNER_MODEL_SELF))
			frappe.db.set_value("Card Equipment Supplier", owner, "settlement_family", family)
		self._je(
			[
				self._owner_line(nasser, debit=30000),
				{"account": self._bank(), "credit_in_account_currency": 30000},
			]
		)
		s = self._statement([nasser, mohammed], family=family, show_wages=False)
		self.assertEqual(s.owners[nasser].closing, 22500)  # before family payments
		self.assertEqual(s.owners[mohammed].closing, 22500)
		self.assertEqual(s.family.payments, 30000)
		self.assertEqual(s.family.closing, 45000 - 30000)

	def test_wages_by_working_days_and_in_full_for_one_crusher(self):
		owner = self._supplier("-W")
		a, b = self._equipment(owner), self._equipment(owner)
		one, shared = self._employee("one"), self._employee("shared")
		self._card(a, operator=one, days=9)
		self._card(b, operator=shared, days=6)
		owned = frappe.new_doc("Card Equipment")
		owned.update(
			{
				"company": self.company,
				"equipment_type": self._m["etype"],
				"equipment_name": "TEST-COS-OWN-" + self.token,
				"ownership": OWNED,
				"daily_hours": 10,
			}
		)
		owned.insert(ignore_permissions=True)
		self._card(owned, operator=shared, days=3)
		slips = {
			one: [frappe._dict(name="S1", start_date="2026-09-01", end_date="2026-09-30", gross_pay=3000)],
			shared: [frappe._dict(name="S2", start_date="2026-09-01", end_date="2026-09-30", gross_pay=4500)],
		}
		with patch.object(
			os_, "salary_slips", lambda company, employee, first, last: slips.get(employee, [])
		):
			s = self._statement([owner], show_ledger=False)
		by_eq = {m.equipment: m.wages for m in s.months}
		self.assertEqual(by_eq[a.name], 3000)  # one crusher only: in full
		self.assertEqual(by_eq[b.name], 3000)  # 6 of 9 working days

	def _employee(self, suffix):
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": "COS-" + suffix + "-" + self.token,
					"gender": frappe.db.get_value("Gender", {}, "name") or "Male",
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2020-01-01",
					"company": self.company,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)


class TestReviewFixes(OwnerFixtures):
	"""Regressions for the code and security review of 2026-11-10."""

	def _bank_je(self, owner, amount, date="2026-09-25"):
		return self._je(
			[
				self._owner_line(owner, debit=amount),
				{"account": self._bank(), "credit_in_account_currency": amount},
			],
			date,
		)

	def test_equipment_filter_does_not_change_the_owners_balance(self):
		owner = self._supplier("-F")
		a, b = self._equipment(owner), self._equipment(owner)
		self._card(a)
		self._card(b)
		self._bank_je(owner, 10000)
		whole = self._statement([owner], show_wages=False)
		one = self._statement([owner], equipment=a.name, show_wages=False)
		self.assertEqual(one.owners[owner].closing, whole.owners[owner].closing)
		self.assertEqual(whole.owners[owner].closing, 45000 - 10000)
		self.assertEqual({m.equipment for m in one.months if m.shown}, {a.name})

	def test_a_machine_that_changed_owner_keeps_its_earlier_cards(self):
		first, second = self._supplier("-P"), self._supplier("-Q")
		eq = self._equipment(first)
		self._card(eq)
		eq.reload()
		eq.supplier = second
		eq.commercial_change_reason = "owner change " + self.token
		eq.save(ignore_permissions=True)
		s = self._statement([first], show_ledger=False, show_wages=False)
		self.assertEqual(s.owners[first].entitlement, 22500)
		s = self._statement([second], show_ledger=False, show_wages=False)
		self.assertEqual(s.owners[second].entitlement, 0)

	def test_hidden_wages_make_the_dues_incomplete(self):
		owner = self._supplier("-I")
		self._card(self._equipment(owner, model=OWNER_MODEL_SELF))
		s = self._statement([owner], show_ledger=False, show_wages=False)
		self.assertFalse(s.owners[owner].complete)
		with patch.object(os_, "salary_slips", lambda *a: []):
			s = self._statement([owner], show_wages=True)
		self.assertTrue(s.owners[owner].complete)

	def test_a_shared_cost_center_is_split_by_working_days(self):
		owner = self._supplier("-S")
		cc = self._cost_center("-S")
		a, b = self._equipment(owner, cost_center=cc), self._equipment(owner, cost_center=cc)
		self._card(a, days=6)
		self._card(b, days=3)
		self._je(
			[
				{"account": self._expense_account(), "debit_in_account_currency": 9000, "cost_center": cc},
				{"account": self._bank(), "credit_in_account_currency": 9000},
			]
		)
		with patch.object(os_, "salary_slips", lambda *a: []):
			s = self._statement([owner])
		by_eq = {m.equipment: m.expenses for m in s.months}
		self.assertEqual(by_eq, {a.name: 6000, b.name: 3000})

	def test_a_card_without_customer_rate_basis_is_not_submitted(self):
		eq = self._equipment(self._supplier("-B"))
		eq.reload()
		eq.customer_rate_type = None
		eq.commercial_change_reason = "no basis " + self.token
		eq.save(ignore_permissions=True)
		card = self._card(eq, submit=False)
		with self.assertRaisesRegex(frappe.ValidationError, "customer rate"):
			card.submit()

	def test_unrelated_save_of_a_third_party_machine_is_not_blocked(self):
		eq = self._equipment(self._supplier("-U"))
		frappe.db.set_value("Card Equipment", eq.name, "owner_model", None)  # a legacy row
		eq = frappe.get_doc("Card Equipment", eq.name)
		eq.site_location = "yard " + self.token
		eq.save(ignore_permissions=True)

	def test_a_cost_center_expense_is_not_recorded_again(self):
		cc = self._cost_center("-D")
		eq = self._equipment(self._supplier("-D"), cost_center=cc)
		source = self._je(
			[
				{"account": self._expense_account(), "debit_in_account_currency": 500, "cost_center": cc},
				{"account": self._bank(), "credit_in_account_currency": 500},
			]
		)
		line = frappe.get_doc(
			{
				"doctype": "Card Owner Deduction",
				"equipment": eq.name,
				"posting_date": "2026-09-20",
				"deduction_type": "Shared expense",
				"amount": 100,
				"source_doctype": "Journal Entry",
				"source_name": source.name,
			}
		).insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "already deducts"):
			line.submit()

	def test_wages_need_a_bulk_payroll_read(self):
		from card.card.report.crusher_owner_statement.crusher_owner_statement import can_view_wages

		if not frappe.db.table_exists("Salary Slip"):
			self.assertTrue(can_view_wages(self.company))  # no payroll: nothing to hide
			return
		email = f"cos-w-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "COS W",
				"send_welcome_email": 0,
				"roles": [{"role": "Card Manager"}, {"role": "Employee"}],
			}
		).insert(ignore_permissions=True)
		employee = TestOwnerStatement._employee(self, "w")
		frappe.get_doc(
			{"doctype": "User Permission", "user": email, "allow": "Employee", "for_value": employee}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertFalse(can_view_wages(self.company))  # reads only his own slip


class TestReportAndPrint(OwnerFixtures):
	def test_report_runs_and_prints(self):
		from card.card.report.crusher_owner_statement import owner_statement_pdf
		from card.card.report.crusher_owner_statement.crusher_owner_statement import execute

		# a managed partner without a cost center: the dues are incomplete, no entitlement tile
		managed = self._supplier("-RM")
		self._card(self._equipment(managed), [self._generator_row()])
		result = execute({"company": self.company, "owner": managed, "from_month": "09", "from_year": 2026})
		self.assertFalse([s for s in result[4] if s["key"] in ("entitlement", "closing")])

		owner = self._supplier("-R")
		card = self._card(self._equipment(owner, model=OWNER_MODEL_SELF), [self._generator_row()])
		self._approval(card, "Approved")
		filters = {"company": self.company, "owner": owner, "from_month": "09", "from_year": 2026}
		with patch.object(os_, "salary_slips", lambda *a: []):
			columns, rows, _message, _chart, summary, _skip = execute(filters)
		entitlement = next(s for s in summary if s["key"] == "entitlement")
		self.assertEqual(entitlement["value"], 39500)
		html = owner_statement_pdf.build_html(frappe._dict(filters), columns, rows, summary)
		self.assertEqual(html.count('<span class="ess-line">'), 3)  # accountant, reviewer, owner
		self.assertIn("ess-totals", html)
		label = {c["fieldname"]: c["label"] for c in columns}
		head = html.split('class="ess-rows"', 1)[1].split("</thead>", 1)[0]  # the rows table header
		self.assertIn(label["confirmed_revenue"], head)
		self.assertNotIn(label["pending_potential"], head)  # nothing pending: the column is not printed
		self.assertNotIn("ERPNext", html)
		self.assertNotIn(">CARD<", html)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[owner_statement_pdf.download_pdf], ["POST"]
		)

	def test_no_owner_no_rows(self):
		from card.card.report.crusher_owner_statement.crusher_owner_statement import execute

		result = execute({"company": self.company, "from_month": "09", "from_year": 2026})
		self.assertEqual(result[1], [])

	def test_pdf_endpoint_never_takes_html(self):
		from card.card.report.crusher_owner_statement import owner_statement_pdf

		with self.assertRaisesRegex(frappe.ValidationError, "Invalid filters"):
			owner_statement_pdf.download_pdf(json.dumps({"company": self.company, "owner": ["<x>"]}))
