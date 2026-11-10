# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Third-party equipment owners: what each owner is due from the monthly cards (Owner 2026-11-10).

Read-only and informational. Nothing here writes a document or a ledger row; CARD posting stays as
it is (the cards of these machines bill the customer only).

Rules
-----
- The monthly card is the only source of the owner's entitlement. Only months whose cards are all
  submitted are final; a month with a draft card is shown apart and never in the totals of dues.
  The first card month counted is the equipment's ``owner_entitlement_from`` (cut-over); without one,
  the owner's first submitted third-party card.
- Owner revenue (before VAT) = the card's customer amount (rental days; customer-caused stops are
  billed days) + customer-side rows of an adjustment type flagged "Crusher owner revenue" (signed:
  breakdown deductions reduce, extra hours add) + the APPROVED amount of conditional rows (a Card
  Owner Revenue Approval names the row). Pending approvals are potential only; rejected or not
  approved parts are excluded; any other customer row stays the company's. VAT is never the owner's.
- Deductions of a month:
  - managed partner: the expenses on the equipment's cost center (Expense accounts, diesel and
    payroll accounts excluded), the wages of company employees who operated it, and the recorded
    shared-expense lines (Card Owner Deduction);
  - self-operating owner: the wages of company employees who operated it and the documented lines
    paid on the owner's behalf (Card Owner Deduction) only.
  Wages: the Salary Slip gross pay, shared over the employee's card working days in the slip period
  (all equipment); an employee whose cards in that period are all on one machine is charged in full
  to it. Payroll accounts are excluded from the cost-center expenses, so a wage is deducted once.
- The owner's party ledger is read across every payable account and each line is classified:
  payment (bank/cash), recharge / paid on behalf, reclass (same party, another account), inter-owner
  transfer, manual accrual (a credit by invoice or journal), other adjustment. A manual accrual on or
  after the owner's cut-over is a possible duplicate of the cards: shown, never counted.
- A family (owners whose CARD registry row names the same "Family settlement group") shares one
  settlement: a payment to any member is a family payment. Member balances are before family
  payments; the family balance deducts them. Documented allocations between members are the
  inter-owner transfer lines.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate

from card.adjustments import ADDITION
from card.card.doctype.card_owner_revenue_approval.card_owner_revenue_approval import (
	APPROVED,
	PARTIAL,
	PENDING,
	REJECTED,
)
from card.constants import DIR_RENTED_OUT, OWNER_MODEL_MANAGED, THIRD_PARTY
from card.settings import company_setting

PAYMENT = "payment"
RECHARGE = "recharge"
RECLASS = "reclass"
TRANSFER = "transfer"
ACCRUAL = "accrual"
ADJUSTMENT = "adjustment"

DEDUCTION_TYPES = {
	"Shared expense": "shared_expenses",
	"Paid on behalf": "paid_on_behalf",
	"Wages": "recorded_wages",
	"Other": "other_deductions",
}


# ---------------------------------------------------------------- owners and equipment


def family_members(company, family):
	"""Suppliers whose CARD registry row names ``family`` as their family settlement group."""
	if not family:
		return []
	return sorted(
		frappe.get_all("Card Equipment Supplier", filters={"settlement_family": family}, pluck="supplier")
	)


def family_of(supplier):
	return frappe.db.get_value("Card Equipment Supplier", supplier, "settlement_family")


def owner_equipment(company, owners):
	"""The owners' machines: third-party equipment they own now, and any equipment with a submitted
	third-party card of theirs (a machine that changed owner keeps its earlier cards with the owner
	they were submitted with)."""
	fields = [
		"name",
		"equipment_name",
		"supplier",
		"ownership",
		"rental_direction",
		"owner_model",
		"owner_entitlement_from",
		"cost_center",
	]
	current = frappe.get_all(
		"Card Equipment",
		filters=[
			["company", "=", company],
			["ownership", "=", THIRD_PARTY],
			["supplier", "in", list(owners)],
		],
		fields=fields,
		limit_page_length=0,
	)
	past = set(
		frappe.get_all(
			"Card Monthly Card",
			filters=[
				["company", "=", company],
				["supplier", "in", list(owners)],
				["ownership", "=", THIRD_PARTY],
				["card_direction", "=", DIR_RENTED_OUT],
				["docstatus", "=", 1],
			],
			pluck="equipment",
			distinct=True,
		)
	) - {m.name for m in current}
	if past:
		current += frappe.get_all(
			"Card Equipment",
			filters=[["company", "=", company], ["name", "in", list(past)]],
			fields=fields,
			limit_page_length=0,
		)
	return sorted(current, key=lambda m: (m.supplier or "", m.name))


# ---------------------------------------------------------------- cards and revenue


def equipment_cards(company, equipment_names, until):
	"""Draft and submitted customer-billing cards (rented out) of the machines: a rented-in or
	sub-rented third-party machine bills a supplier, so its cards are not the owner's revenue here."""
	if not equipment_names:
		return []
	return frappe.get_all(
		"Card Monthly Card",
		filters=[
			["company", "=", company],
			["equipment", "in", list(equipment_names)],
			["card_direction", "=", DIR_RENTED_OUT],
			["docstatus", "in", [0, 1]],
			["from_date", "<=", until],
		],
		fields=[
			"name",
			"equipment",
			"supplier",
			"ownership",
			"docstatus",
			"from_date",
			"to_date",
			"working_days",
			"operator",
			"owner_model",
			"owner_entitlement_from",
			"amended_from",
			"customer_amount",
			"customer_net_amount",
			"sales_invoice",
		],
		order_by="from_date asc, name asc",
		limit_page_length=0,
	)


def owner_revenue_types(company):
	"""Names of the company's adjustment types flagged as crusher owner revenue."""
	return {
		row.type_name
		for row in (frappe.get_doc("Card Settings").get("adjustment_types") or [])
		if row.company == company and cint(row.get("owner_revenue"))
	}


def card_revenue(card, rows, approvals, owner_types):
	"""Owner revenue of one card, split so that the card's customer net is explained once:
	customer_net = customer_amount + owner rows + conditional rows + company rows."""
	out = frappe._dict(
		customer_net=flt(card.customer_net_amount, 2),
		customer_amount=flt(card.customer_amount, 2),
		owner_rows=0.0,
		conditional_gross=0.0,
		approved=0.0,
		pending=0.0,
		excluded=0.0,
		company_rows=0.0,
		unclassified=0.0,
		approval_status=set(),
		approval_records=[],
		approval_mismatch=False,
	)
	for row in rows:
		if (row.side or "Supplier") != "Customer":
			continue
		signed = flt(row.amount, 2) if row.adjustment_type == ADDITION else -flt(row.amount, 2)
		approval = approvals.get(row.name)
		if approval and row.adjustment_type == ADDITION:
			gross = flt(row.amount, 2)
			out.conditional_gross += gross
			out.approval_status.add(approval.approval_status)
			out.approval_records.append(approval.name)
			if flt(approval.gross_amount, 2) != gross:
				out.approval_mismatch = True  # the card row changed after the approval was recorded
			if approval.approval_status in (APPROVED, PARTIAL):
				approved = min(flt(approval.approved_amount, 2), gross)
				out.approved += approved
				out.excluded += gross - approved
			elif approval.approval_status == PENDING:
				out.pending += gross
			else:
				out.excluded += gross
		elif row.adjustment_type_ref and row.adjustment_type_ref in owner_types:
			out.owner_rows += signed
		else:
			out.company_rows += signed
			if not row.adjustment_type_ref:
				out.unclassified += signed
	out.confirmed = flt(out.customer_amount + out.owner_rows + out.approved, 2)
	out.check = flt(
		out.customer_net - out.customer_amount - out.owner_rows - out.conditional_gross - out.company_rows,
		2,
	)
	return out


def card_rows(card_names):
	rows = defaultdict(list)
	if not card_names:
		return rows
	for row in frappe.get_all(
		"Card Monthly Card Adjustment",
		filters=[["parent", "in", list(card_names)], ["parenttype", "=", "Card Monthly Card"]],
		fields=[
			"name",
			"idx",
			"parent",
			"side",
			"adjustment_type",
			"amount",
			"adjustment_type_ref",
			"description",
		],
		order_by="idx asc",
		limit_page_length=0,
	):
		rows[row.parent].append(row)
	return rows


APPROVAL_FIELDS = [
	"name",
	"monthly_card",
	"adjustment_row",
	"approval_status",
	"approved_amount",
	"gross_amount",
	"evidence",
]


def card_approvals(card_names, rows_by_card=None, amended_from=None):
	"""{card: {adjustment row: approval}}.

	A customer's approval survives a cancel and amend of the card: an approval recorded on an earlier
	version of the card (``amended_from`` chain) applies to the same row of the amendment (same
	position, side, type and amount). An approval recorded on the amendment itself wins."""
	out = defaultdict(dict)
	if not card_names:
		return out
	for approval in frappe.get_all(
		"Card Owner Revenue Approval",
		filters=[["monthly_card", "in", list(card_names)]],
		fields=APPROVAL_FIELDS,
		limit_page_length=0,
	):
		out[approval.monthly_card][approval.adjustment_row] = approval
	if rows_by_card is None:
		return out
	chains = amendment_chains(amended_from or {})
	for card in card_names:
		ancestors = chains.get(card) or []
		if not ancestors:
			continue
		inherited = frappe.get_all(
			"Card Owner Revenue Approval",
			filters=[["monthly_card", "in", ancestors]],
			fields=APPROVAL_FIELDS,
			limit_page_length=0,
		)
		if not inherited:
			continue
		old_rows = {r.name: r for rows in card_rows(ancestors).values() for r in rows}
		# nearest earlier version first
		order = {name: i for i, name in enumerate(ancestors)}
		inherited.sort(key=lambda a: order.get(a.monthly_card, len(order)))
		for row in rows_by_card.get(card, []):
			if row.name in out[card]:
				continue
			for approval in inherited:
				old = old_rows.get(approval.adjustment_row)
				if old and _same_row(old, row):
					out[card][row.name] = approval
					break
	return out


def amendment_chains(amended_from):
	"""{card: [earlier versions, nearest first]} for ``amended_from`` = {card: its amended_from}.
	Resolved level by level with one query per level (the cancelled versions are not in the card list)."""
	parent = {c: a for c, a in amended_from.items() if a}
	pending = {a for a in parent.values() if a not in parent}
	seen = set(parent)
	for _level in range(50):
		pending -= seen
		if not pending:
			break
		seen |= pending
		rows = frappe.get_all(
			"Card Monthly Card",
			filters=[["name", "in", list(pending)]],
			fields=["name", "amended_from"],
			limit_page_length=0,
		)
		pending = set()
		for row in rows:
			if row.amended_from:
				parent[row.name] = row.amended_from
				pending.add(row.amended_from)
	chains = {}
	for card in amended_from:
		chain, current = [], parent.get(card)
		while current and current not in chain and len(chain) < 50:
			chain.append(current)
			current = parent.get(current)
		chains[card] = chain
	return chains


def _same_row(old, new):
	return (
		old.idx == new.idx
		and (old.side or "") == (new.side or "")
		and old.adjustment_type == new.adjustment_type
		and flt(old.amount, 2) == flt(new.amount, 2)
	)


# ---------------------------------------------------------------- deductions


def excluded_expense_accounts(company):
	"""Diesel (the company bears it for every managed partner) and payroll accounts (wages are
	counted from the Salary Slips): never part of the cost-center expenses."""
	accounts = set()
	diesel = company_setting(company, "diesel_expense_account")
	if diesel:
		accounts.update(_with_descendants("Account", diesel))
	if frappe.db.table_exists("Salary Component Account"):
		accounts.update(
			frappe.get_all(
				"Salary Component Account",
				filters={"company": company, "account": ["is", "set"]},
				pluck="account",
			)
		)
	return accounts


def _with_descendants(doctype, name):
	bounds = frappe.db.get_value(doctype, name, ["lft", "rgt"], as_dict=True)
	if not bounds:
		return {name}
	return set(
		frappe.get_all(doctype, filters={"lft": [">=", bounds.lft], "rgt": ["<=", bounds.rgt]}, pluck="name")
	)


def rent_expense_accounts(company):
	"""The company's equipment-rental expense account and its children: a voucher that credits an
	owner and debits one of them is a manual accrual of the owner's dues. Any other voucher that
	credits the owner (for example his invoice for spare parts) is a genuine amount due to him.
	None when the account is not set: then every voucher that credits the owner is treated as an
	accrual of dues (the behaviour before the setting is used)."""
	account = company_setting(company, "equipment_rental_expense_account")
	return _with_descendants("Account", account) if account else None


def deductible_expense_accounts(company):
	"""The company's Expense ledger accounts, without diesel and payroll accounts."""
	excluded = excluded_expense_accounts(company)
	return [
		account
		for account in frappe.get_all(
			"Account", filters={"company": company, "root_type": "Expense", "is_group": 0}, pluck="name"
		)
		if account not in excluded
	]


def cost_center_expenses(company, cost_center, start, end, accounts, owners=(), rent_accounts=None):
	"""Net amount of ``accounts`` on the cost center itself in the period (debit - credit); a recharge
	that credits the expense on the same cost center nets here once. The expense side of a voucher
	that CREDITS an owner (a manual accrual of the owner's dues booked as an expense of the machine) is
	the owner's revenue, not a machine expense: it is left out (the accrual is shown in the ledger)."""
	if not cost_center:
		return None
	if not accounts:
		return 0.0
	rows = frappe.get_all(
		"GL Entry",
		filters=[
			["company", "=", company],
			["cost_center", "=", cost_center],
			["account", "in", accounts],
			["is_cancelled", "=", 0],
			["posting_date", ">=", start],
			["posting_date", "<=", end],
		],
		fields=["voucher_type", "voucher_no", "account", "debit", "credit"],
		limit_page_length=0,
	)
	accruals = set()
	if owners and rows:
		accruals = {
			(r.voucher_type, r.voucher_no)
			for r in frappe.get_all(
				"GL Entry",
				filters=[
					["company", "=", company],
					["voucher_no", "in", list({r.voucher_no for r in rows})],
					["party_type", "=", "Supplier"],
					["party", "in", list(owners)],
					["credit", ">", 0],
					["is_cancelled", "=", 0],
				],
				fields=["voucher_type", "voucher_no"],
				limit_page_length=0,
			)
		}

	def accrual_side(r):
		# the rent side of an owner accrual is the owner's revenue; a genuine owner invoice (parts)
		# stays a machine expense
		return (r.voucher_type, r.voucher_no) in accruals and (
			rent_accounts is None or r.account in rent_accounts
		)

	return flt(sum(flt(r.debit) - flt(r.credit) for r in rows if not accrual_side(r)), 2)


def cost_center_days(company, cost_center, month):
	"""{card: working days} of every card of the company's machines on the cost center in the month
	(any ownership): a cost center shared by several machines, or by two owners of one machine in the
	same month, is split between the cards by working days, so each share is counted once."""
	machines = frappe.get_all(
		"Card Equipment", filters={"company": company, "cost_center": cost_center}, pluck="name"
	)
	days = {}
	if not machines:
		return days
	for card in frappe.get_all(
		"Card Monthly Card",
		filters=[
			["company", "=", company],
			["equipment", "in", machines],
			["docstatus", "in", [0, 1]],
			["from_date", "=", month],
		],
		fields=["name", "working_days"],
		limit_page_length=0,
	):
		days[card.name] = cint(card.working_days)
	return days


def cost_center_share(days, card_names):
	"""Share of the cost-center month that belongs to ``card_names``: their working days over all
	the cards' days; with no working days at all, by number of cards."""
	if not days:
		return 1.0
	mine = [c for c in card_names if c in days]
	total = sum(days.values())
	if total:
		return sum(days[c] for c in mine) / total
	return len(mine) / len(days)


def wages_by_card(company, months_by_employee):
	"""{(employee, card): wage} for the employees who operated the owners' machines.
	``months_by_employee`` = {employee: set(month starts)}. Gross pay of each submitted Salary Slip is
	shared over the employee's card working days in the slip period, every equipment included; one
	machine only = the slip's full gross pay to it. Keyed by card, so two owners of one machine in the
	same month each get only their own cards' share."""
	out = defaultdict(float)
	for employee, months in (months_by_employee or {}).items():
		first = min(months)
		last = get_last_day(max(months))
		slips = salary_slips(company, employee, first, last)
		if not slips:
			continue
		# one card query per employee over every slip period, matched to each slip below
		all_cards = frappe.get_all(
			"Card Monthly Card",
			filters=[
				["company", "=", company],
				["operator", "=", employee],
				["docstatus", "in", [0, 1]],
				["from_date", "<=", max(getdate(s.end_date) for s in slips)],
				["to_date", ">=", min(getdate(s.start_date) for s in slips)],
			],
			fields=["name", "equipment", "from_date", "to_date", "working_days"],
			limit_page_length=0,
		)
		for slip in slips:
			cards = [
				c
				for c in all_cards
				if getdate(c.from_date) <= getdate(slip.end_date)
				and getdate(c.to_date) >= getdate(slip.start_date)
			]
			if not cards:
				continue
			gross = flt(slip.gross_pay, 2)
			machines = {c.equipment for c in cards}
			total_days = sum(cint(c.working_days) for c in cards)
			for c in cards:
				# by working days; one machine only: its cards together carry the full gross pay
				if total_days:
					share = gross * cint(c.working_days) / total_days
				else:
					share = gross / len(cards) if len(machines) == 1 else 0
				out[(employee, c.name)] += share
	return out


def salary_slips(company, employee, first, last):
	"""Submitted Salary Slips of the employee overlapping [first, last] (none without HRMS)."""
	if not frappe.db.table_exists("Salary Slip"):
		return []
	return frappe.get_all(
		"Salary Slip",
		filters=[
			["company", "=", company],
			["employee", "=", employee],
			["docstatus", "=", 1],
			["start_date", "<=", last],
			["end_date", ">=", first],
		],
		fields=["name", "start_date", "end_date", "gross_pay"],
		limit_page_length=0,
	)


def recorded_deductions(company, equipment_names, start, end):
	"""Submitted Card Owner Deduction lines of the machines in [start, end].

	Returns ({(owner, equipment, month start): {bucket: amount}}, [lines whose source is cancelled]).
	A line belongs to the owner it names (``owner_supplier``, the owner on its posting date), not to
	the machine's current owner. A line whose source document is no longer submitted stops applying
	and is listed instead."""
	out = defaultdict(lambda: defaultdict(float))
	void = []
	if not equipment_names:
		return out, void
	lines = frappe.get_all(
		"Card Owner Deduction",
		filters=[
			["company", "=", company],
			["equipment", "in", list(equipment_names)],
			["docstatus", "=", 1],
			["posting_date", ">=", start],
			["posting_date", "<=", end],
		],
		fields=[
			"name",
			"equipment",
			"owner_supplier",
			"posting_date",
			"deduction_type",
			"amount",
			"source_doctype",
			"source_name",
		],
		limit_page_length=0,
	)
	submitted = {}
	for doctype in {line.source_doctype for line in lines if line.source_doctype}:
		names = list({line.source_name for line in lines if line.source_doctype == doctype})
		if not frappe.db.exists("DocType", doctype):
			continue
		submitted[doctype] = set(
			frappe.get_all(doctype, filters={"name": ["in", names], "docstatus": 1}, pluck="name")
		)
	for line in lines:
		if line.source_name not in submitted.get(line.source_doctype, set()):
			void.append(line)
			continue
		bucket = DEDUCTION_TYPES.get(line.deduction_type, "other_deductions")
		key = (line.owner_supplier, line.equipment, getdate(get_first_day(line.posting_date)))
		out[key][bucket] += flt(line.amount, 2)
	return out, void


# ---------------------------------------------------------------- party ledger


def owner_ledger(company, owners, until, rent_accounts=None):
	"""Classified party-ledger lines of the owners, every payable account, up to ``until``."""
	if not owners:
		return []
	lines = frappe.get_all(
		"GL Entry",
		filters=[
			["company", "=", company],
			["party_type", "=", "Supplier"],
			["party", "in", list(owners)],
			["is_cancelled", "=", 0],
			["posting_date", "<=", until],
		],
		fields=[
			"name",
			"posting_date",
			"party",
			"account",
			"debit",
			"credit",
			"voucher_type",
			"voucher_no",
			"against_voucher_type",
			"against_voucher",
		],
		order_by="posting_date asc, creation asc",
		limit_page_length=0,
	)
	vouchers = {(line.voucher_type, line.voucher_no) for line in lines}
	others = defaultdict(list)
	if vouchers:
		for row in frappe.get_all(
			"GL Entry",
			filters=[["voucher_no", "in", [v[1] for v in vouchers]], ["is_cancelled", "=", 0]],
			fields=[
				"name",
				"voucher_type",
				"voucher_no",
				"account",
				"party_type",
				"party",
				"debit",
				"credit",
				"cost_center",
			],
			limit_page_length=0,
		):
			others[(row.voucher_type, row.voucher_no)].append(row)
	account_types = {}
	accounts = {row.account for rows in others.values() for row in rows}
	if accounts:
		account_types = {
			a.name: a
			for a in frappe.get_all(
				"Account",
				filters={"name": ["in", list(accounts)]},
				fields=["name", "account_type", "root_type"],
			)
		}
	for line in lines:
		line.kind, line.counterparty = classify(
			line, others[(line.voucher_type, line.voucher_no)], account_types
		)
		line.effect = flt(flt(line.credit) - flt(line.debit), 2)  # + = due to the owner
		line.allocated = bool(line.against_voucher and line.against_voucher != line.voucher_no)
		rest = [
			r
			for r in others[(line.voucher_type, line.voucher_no)]
			if r.name != line.name and not (r.party_type == "Supplier" and r.party == line.party)
		]
		line.cost_centers = {r.cost_center for r in rest if r.cost_center}
		line.rent_accrual = rent_accounts is None or any(r.account in rent_accounts for r in rest)
	_set_reversals(lines)
	return lines


def _set_reversals(lines):
	"""``line.reverses`` = the voucher a debit line reverses: a Purchase Invoice return (its
	``return_against``), a reversing Journal Entry (``reversal_of``), or a debit made against that
	voucher. Payments are never reversals."""
	pis = list({l.voucher_no for l in lines if l.voucher_type == "Purchase Invoice"})
	jes = list({l.voucher_no for l in lines if l.voucher_type == "Journal Entry"})
	returns = {}
	if pis:
		returns = {
			r.name: r.return_against
			for r in frappe.get_all(
				"Purchase Invoice",
				filters={"name": ["in", pis], "is_return": 1},
				fields=["name", "return_against"],
				limit_page_length=0,
			)
		}
	reversals = {}
	if jes and frappe.get_meta("Journal Entry").has_field("reversal_of"):
		reversals = {
			r.name: r.reversal_of
			for r in frappe.get_all(
				"Journal Entry",
				filters={"name": ["in", jes], "reversal_of": ["is", "set"]},
				fields=["name", "reversal_of"],
				limit_page_length=0,
			)
		}
	for line in lines:
		line.reverses = None
		if line.kind == PAYMENT or flt(line.debit) <= flt(line.credit):
			continue
		line.reverses = (
			returns.get(line.voucher_no)
			or reversals.get(line.voucher_no)
			or (line.against_voucher if line.against_voucher != line.voucher_no else None)
		)


def classify(line, voucher_rows, account_types):
	"""(kind, counterparty) of one owner party line. Not every debit is a payment: a debit against an
	expense or income account is a recharge; against a bank, cash or other balance-sheet account (for
	example an owner's current account that paid the owner) it settles the owner's dues."""
	if line.voucher_type == "Payment Entry":
		return PAYMENT, None
	if line.voucher_type == "Purchase Invoice":
		return (ACCRUAL if flt(line.credit) > flt(line.debit) else ADJUSTMENT), None
	rest = [
		r
		for r in voucher_rows
		if r.name != line.name and not (r.party_type == "Supplier" and r.party == line.party)
	]
	info = {r.account: account_types.get(r.account) or frappe._dict() for r in rest}
	if any(info[r.account].account_type in ("Bank", "Cash") for r in rest):
		return PAYMENT, None
	if not rest:
		return RECLASS, None
	party_rows = [r for r in rest if r.party_type == "Supplier" and r.party]
	if party_rows:
		return TRANSFER, party_rows[0].party
	if flt(line.debit) <= flt(line.credit):
		return ACCRUAL, None
	if any(info[r.account].root_type in ("Expense", "Income") for r in rest):
		return RECHARGE, None
	return PAYMENT, rest[0].account  # settled through another balance-sheet account


# ---------------------------------------------------------------- statement


def build_statement(
	company,
	owners,
	start,
	end,
	equipment=None,
	owner_model=None,
	family=None,
	show_ledger=True,
	show_wages=True,
):
	"""The statement of ``owners`` for [start, end] (whole months). Returns a dict with the owners'
	machine-month rows, the owner totals and the family total (when ``family``).

	The owner totals and balances always cover all the owner's machines (the party ledger is the
	owner's, not a machine's): ``equipment`` and ``owner_model`` only choose the rows shown."""
	start, end = getdate(start), getdate(end)
	owners = list(owners)
	machines = owner_equipment(company, owners)
	by_name = {m.name: m for m in machines}
	cards = equipment_cards(company, list(by_name), end)
	rows_by_card = card_rows([c.name for c in cards])
	approvals = card_approvals([c.name for c in cards], rows_by_card, {c.name: c.amended_from for c in cards})
	owner_types = owner_revenue_types(company)

	# the owner of each card: a submitted card keeps the owner it was submitted with (third-party
	# cards only; earlier cards were not the owner's); a draft follows the equipment
	months = defaultdict(list)
	for card in cards:
		machine = by_name[card.equipment]
		if card.docstatus == 1:
			if card.ownership != THIRD_PARTY:
				continue
			owner = card.supplier
		else:
			if machine.ownership != THIRD_PARTY or machine.rental_direction != DIR_RENTED_OUT:
				continue
			owner = machine.supplier
		if owner not in owners:
			continue
		months[(owner, card.equipment, getdate(get_first_day(card.from_date)))].append(card)

	cutover = {}
	for owner, eq, _month in list(months):
		if (owner, eq) in cutover:
			continue
		machine = by_name[eq]
		# the start date each owner's submitted cards carry (a new owner gets his own); a machine's
		# current date only for its current owner
		snapshots = [
			getdate(get_first_day(c.owner_entitlement_from))
			for (o, e, _m), cs in months.items()
			if (o, e) == (owner, eq)
			for c in cs
			if c.docstatus == 1 and c.get("owner_entitlement_from")
		]
		first = min(snapshots) if snapshots else None
		if not first and owner == machine.supplier and machine.owner_entitlement_from:
			first = getdate(get_first_day(machine.owner_entitlement_from))
		if not first:
			# no cut-over set: the first submitted card month of this owner, else the first card month
			own = [m for (o, e, m) in months if (o, e) == (owner, eq)]
			submitted = [
				m
				for (o, e, m), cs in months.items()
				if (o, e) == (owner, eq) and any(c.docstatus == 1 for c in cs)
			]
			first = min(submitted or own)
		cutover[(owner, eq)] = first
	months = {k: v for k, v in months.items() if k[2] >= cutover[(k[0], k[1])]}

	first_month = min([k[2] for k in months] + [get_first_day(start)])
	accounts = deductible_expense_accounts(company) if show_ledger else []
	recorded, void_deductions = recorded_deductions(company, list(by_name), first_month, end)
	by_employee = defaultdict(set)
	for (_owner, _eq, month), cs in months.items():
		for c in cs:
			if c.operator:
				by_employee[c.operator].add(month)
	wages = wages_by_card(company, by_employee) if show_wages else {}
	cc_cache = {}

	month_rows = []
	for (owner, eq, month), cs in sorted(months.items(), key=lambda kv: kv[0]):
		machine = by_name[eq]
		model = month_owner_model(cs, machine)
		managed = model == OWNER_MODEL_MANAGED
		row = frappe._dict(
			owner=owner,
			equipment=eq,
			equipment_name=machine.equipment_name,
			owner_model=model,
			month=month,
			cards=[c.name for c in cs],
			final=all(c.docstatus == 1 for c in cs),
			in_period=start <= month <= end,
			shown=(not equipment or eq == equipment) and (not owner_model or model == owner_model),
			no_card=False,
		)
		revenue = [
			card_revenue(c, rows_by_card.get(c.name, []), approvals.get(c.name, {}), owner_types) for c in cs
		]
		for key in REVENUE_KEYS:
			row[key] = flt(sum(r[key] for r in revenue), 2)
		row.approval_status = sorted({s for r in revenue for s in r.approval_status})
		row.approval_records = [n for r in revenue for n in r.approval_records]
		row.approval_mismatch = any(r.approval_mismatch for r in revenue)
		row.expenses = 0.0
		row.no_owner_model = not model
		row.no_cost_center = managed and show_ledger and not machine.cost_center
		if managed and show_ledger and machine.cost_center:
			key = (machine.cost_center, month)
			if key not in cc_cache:
				cc_cache[key] = (
					cost_center_expenses(
						company,
						machine.cost_center,
						month,
						get_last_day(month),
						accounts,
						owners,
						rent_expense_accounts(company),
					),
					cost_center_days(company, machine.cost_center, month),
				)
			total, days = cc_cache[key]
			share = cost_center_share(days, row.cards)
			if share < 1:
				total = flt(flt(total) * share, 2)
				row.shared_cost_center = True
			row.expenses = total
		row.wages = (
			flt(sum(v for (_emp, card), v in wages.items() if card in row.cards), 2) if show_wages else None
		)
		apply_recorded(row, recorded.pop((owner, eq, month), {}), show_wages)
		row.entitlement = flt(row.confirmed - row.deductions, 2)
		row.complete = bool(show_ledger and show_wages and not row.no_cost_center and not row.no_owner_model)
		month_rows.append(row)

	# a submitted deduction in a month with no card of its owner on that machine is never dropped:
	# it becomes its own final month row (no revenue) and a warning
	warnings = []
	for (owner, eq, month), lines in sorted(
		recorded.items(), key=lambda kv: (kv[0][0] or "", kv[0][1], kv[0][2])
	):
		if owner not in owners or eq not in by_name:
			continue
		machine = by_name[eq]
		cut = cutover.get((owner, eq))
		if not cut and owner == machine.supplier and machine.owner_entitlement_from:
			cut = getdate(get_first_day(machine.owner_entitlement_from))
		if cut and month < cut:
			total = flt(sum(lines.values()), 2)
			warnings.append(
				_(
					"{0}: deductions of {1} on {2} in {3} are before the cut-over {4}; they are not counted."
				).format(owner, total, eq, month_label(month), month_label(cut))
			)
			continue
		row = frappe._dict(
			owner=owner,
			equipment=eq,
			equipment_name=machine.equipment_name,
			owner_model=machine.owner_model,
			month=month,
			cards=[],
			final=True,
			in_period=start <= month <= end,
			shown=(not equipment or eq == equipment)
			and (not owner_model or machine.owner_model == owner_model),
			no_card=True,
			approval_status=[],
			approval_records=[],
			approval_mismatch=False,
			no_cost_center=False,
			expenses=0.0,
			wages=0.0 if show_wages else None,
		)
		for key in REVENUE_KEYS:
			row[key] = 0.0
		apply_recorded(row, lines, show_wages)
		row.entitlement = flt(-row.deductions, 2)
		row.complete = bool(show_ledger and show_wages)
		month_rows.append(row)
		warnings.append(
			_(
				"{0}: deductions of {1} on {2} in {3} have no card that month; they are shown as their own row."
			).format(owner, row.deductions, eq, month_label(month))
		)
	for line in void_deductions:
		warnings.append(
			_("Card Owner Deduction {0} no longer applies: its source {1} {2} is not submitted.").format(
				line.name, line.source_doctype, line.source_name
			)
		)
	month_rows.sort(key=lambda r: (r.owner or "", r.equipment, r.month))

	def cut_for(owner, eq):
		if (owner, eq) in cutover:
			return cutover[(owner, eq)]
		machine = by_name.get(eq)
		if machine and owner == machine.supplier and machine.owner_entitlement_from:
			return getdate(get_first_day(machine.owner_entitlement_from))
		return None

	# Purchase Invoices CARD posted for an owner's cards (a rented-in machine) are not manual accruals
	card_invoices = set(
		frappe.get_all(
			"Card Monthly Card",
			filters=[
				["company", "=", company],
				["supplier", "in", owners],
				["docstatus", "=", 1],
				["purchase_invoice", "is", "set"],
			],
			pluck="purchase_invoice",
		)
	)

	owner_rows = {}
	rent_accounts = rent_expense_accounts(company) if show_ledger else None
	ledger = owner_ledger(company, owners, end, rent_accounts) if show_ledger else []
	duplicate_vouchers = set()
	for line in ledger:
		line.duplicate = False
		if line.kind != ACCRUAL or not line.rent_accrual:
			continue
		if line.voucher_type == "Purchase Invoice" and line.voucher_no in card_invoices:
			continue
		# the machine(s) the accrual is booked on (cost center); one machine only: that one
		mine = [eq for eq, m in by_name.items() if m.cost_center and m.cost_center in line.cost_centers]
		if not mine:
			owned = [eq for eq in by_name if cut_for(line.party, eq)]
			mine = owned if len(owned) == 1 else []
		cuts = [cut_for(line.party, eq) for eq in mine]
		if not mine or not all(cuts):
			if not mine and any(cut_for(line.party, eq) for eq in by_name):
				warnings.append(
					_(
						"Manual accrual {0} {1} names no machine of the owner; check it against the cards."
					).format(line.voucher_type, line.voucher_no)
				)
			continue
		if getdate(line.posting_date) >= max(cuts):
			line.duplicate = True
			duplicate_vouchers.add(line.voucher_no)
	for line in ledger:
		if line.reverses and line.reverses in duplicate_vouchers:
			line.duplicate = True  # a reversal of a duplicate accrual nets to zero for the owner
	for owner in owners:
		o = frappe._dict(
			owner=owner,
			opening=0.0,
			entitlement=0.0,
			confirmed=0.0,
			pending=0.0,
			deductions=0.0,
			complete=True,
		)
		for key in (PAYMENT, RECHARGE, RECLASS, TRANSFER, ADJUSTMENT):
			o[key] = 0.0
		o.payments_allocated = 0.0
		o.payments_unallocated = 0.0
		o.duplicate_accruals = 0.0
		o.accruals = 0.0
		o.ledger_lines = []
		for row in month_rows:
			if row.owner != owner or not row.final:
				continue
			if row.month > end:
				continue
			o.complete = o.complete and row.complete
			if row.month < get_first_day(start):
				o.opening += row.entitlement
			elif row.in_period:
				o.entitlement += row.entitlement
				o.confirmed += row.confirmed
				o.pending += row.pending
				o.deductions += row.deductions
		for line in ledger:
			if line.party != owner:
				continue
			duplicate = line.duplicate
			before = getdate(line.posting_date) < start
			if before:
				if not duplicate and not (family and line.kind == PAYMENT):
					o.opening += line.effect
				continue
			o.ledger_lines.append(line)
			if duplicate:
				o.duplicate_accruals += flt(line.credit) - flt(line.debit)
				continue
			if line.kind == PAYMENT:
				paid = -line.effect
				o[PAYMENT] += paid
				if line.allocated:
					o.payments_allocated += paid
				else:
					o.payments_unallocated += paid
			elif line.kind == ACCRUAL:
				o.accruals += line.effect
			else:
				o[line.kind] += line.effect
		o.closing = flt(
			o.opening
			+ o.entitlement
			+ o.accruals
			+ o[RECHARGE]
			+ o[RECLASS]
			+ o[TRANSFER]
			+ o[ADJUSTMENT]
			- (0 if family else o[PAYMENT]),
			2,
		)
		for key in list(o):
			if isinstance(o[key], float):
				o[key] = flt(o[key], 2)
		owner_rows[owner] = o

	family_row = None
	if family:
		payments_before = sum(
			-line.effect for line in ledger if line.kind == PAYMENT and getdate(line.posting_date) < start
		)
		family_row = frappe._dict(
			family=family,
			complete=all(o.complete for o in owner_rows.values()),
			opening=flt(sum(o.opening for o in owner_rows.values()) - payments_before, 2),
			entitlement=flt(sum(o.entitlement for o in owner_rows.values()), 2),
			payments=flt(sum(o[PAYMENT] for o in owner_rows.values()), 2),
		)
		family_row.closing = flt(
			sum(o.closing for o in owner_rows.values()) - payments_before - family_row.payments, 2
		)
	return frappe._dict(
		machines=machines, months=month_rows, owners=owner_rows, family=family_row, warnings=warnings
	)


REVENUE_KEYS = (
	"customer_net",
	"customer_amount",
	"owner_rows",
	"conditional_gross",
	"approved",
	"pending",
	"excluded",
	"company_rows",
	"unclassified",
	"confirmed",
	"check",
)


def month_owner_model(cards, machine):
	"""The owner model of a machine-month: the snapshot on its submitted cards (history is never
	recomputed from today's equipment settings); a month with drafts only follows the equipment.
	A submitted card saved before the snapshot existed (empty) falls back to the equipment."""
	for card in cards:
		if card.docstatus == 1 and card.get("owner_model"):
			return card.owner_model
	return machine.owner_model


def apply_recorded(row, lines, show_wages):
	"""Put the recorded deduction lines of a machine-month on ``row`` and total its deductions."""
	for bucket in DEDUCTION_TYPES.values():
		row[bucket] = flt((lines or {}).get(bucket), 2)
	if not show_wages:
		row.recorded_wages = 0.0  # wages stay hidden from a user who may not read Salary Slips
	row.deductions = flt(
		flt(row.expenses)
		+ flt(row.wages)
		+ row.shared_expenses
		+ row.paid_on_behalf
		+ row.recorded_wages
		+ row.other_deductions,
		2,
	)


def period(from_month, from_year, to_month=None, to_year=None):
	fm, fy = cint(from_month), cint(from_year)
	tm, ty = cint(to_month) or fm, cint(to_year) or fy
	if not fm or not fy:
		frappe.throw(_("Select the start month and year"))
	start = getdate(f"{fy}-{fm:02d}-01")
	end = get_last_day(getdate(f"{ty}-{tm:02d}-01"))
	if end < start:
		frappe.throw(_("Invalid period: end is before start"))
	return start, end


def month_label(month):
	return f"{getdate(month).year}-{getdate(month).month:02d}"
