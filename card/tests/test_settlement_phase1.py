# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Settlement phase 1 (owner decisions 2026-11-09): an accountant links an existing
supplier accrual Journal Entry to the monthly cards it recognised (D1/D2); the
reconciliation counts them as recognised (D7) and CARD never invoices them again;
the Card Settlement Status report reads paid and remaining from the Payment Ledger
Entry, allocating payments oldest first (D6, Q3). Nothing posts from CARD."""

import json

import frappe
from frappe.utils import flt

from card.card.report.card_settlement_status.card_settlement_status import execute as settlement_status
from card.gl.journal_link import link_accrual_journal
from card.gl.posting import build_monthly_posting
from card.reconciliation import cards_invoiced
from card.tests.test_p0_posting_integrity import _P0Base


class TestAccrualJournalLink(_P0Base):
	def setUp(self):
		super().setUp()
		row = next(r for r in frappe.get_doc("Card Settings").company_settings if r.company == self.company)
		self.payable = row.payable_account
		self.cost_center = row.cost_center
		self.bank = frappe.db.get_value(
			"Account",
			{"company": self.company, "account_type": ["in", ["Bank", "Cash"]], "is_group": 0},
			"name",
		)

	# ---------- fixtures ----------

	def _accrual(self, amount, submit=True, party=None, debit_party=False, vat=0, reference=None):
		"""Expense debit / supplier credit (debit_party: the reverse, a payment-like entry)."""
		party_row = {
			"account": self.payable,
			"party_type": "Supplier",
			"party": party or self.supplier,
			"cost_center": self.cost_center,
			"debit_in_account_currency": amount if debit_party else 0,
			"credit_in_account_currency": 0 if debit_party else amount,
		}
		if reference:
			party_row.update({"reference_type": reference.doctype, "reference_name": reference.name})
		other = {
			"account": self.bank if debit_party else self.exp_rental,
			"cost_center": self.cost_center,
			"debit_in_account_currency": 0 if debit_party else amount - vat,
			"credit_in_account_currency": amount if debit_party else 0,
		}
		rows = [other, party_row]
		if vat:
			rows.insert(
				1, {"account": self.vat_in, "cost_center": self.cost_center, "debit_in_account_currency": vat}
			)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": "2026-09-30",
				"voucher_type": "Journal Entry",
				"accounts": rows,
			}
		).insert(ignore_permissions=True)
		if submit:
			je.submit()
		return je

	def _payment(self, amount, against=None):
		"""Bank payment journal: supplier debit (against the accrual when given) / bank credit."""
		party_row = {
			"account": self.payable,
			"party_type": "Supplier",
			"party": self.supplier,
			"cost_center": self.cost_center,
			"debit_in_account_currency": amount,
		}
		if against:
			party_row.update({"reference_type": "Journal Entry", "reference_name": against})
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": "2026-10-17",
				"voucher_type": "Bank Entry",
				"cheque_no": "TEST-" + self.token,
				"cheque_date": "2026-10-17",
				"accounts": [
					party_row,
					{
						"account": self.bank,
						"cost_center": self.cost_center,
						"credit_in_account_currency": amount,
					},
				],
			}
		).insert(ignore_permissions=True)
		je.submit()
		return je

	def _status(self):
		_columns, data, _message, _chart, summary = settlement_status(
			{
				"company": self.company,
				"party_type": "Supplier",
				"party": self.supplier,
				"from_date": "2026-09-01",
				"to_date": "2026-12-31",
			}
		)
		return {r["card"]: r for r in data}, {s["label"]: s["value"] for s in summary}

	def _recognised(self, card):
		return cards_invoiced(
			"Supplier", [self.supplier], self.company, "2026-09-01", "2026-09-30", cards=[card]
		)

	# ---------- D2: link ----------

	def test_link_reserves_the_card_and_counts_it_as_recognised(self):
		card = self._rental_card()
		net = flt(card.net_amount, 2)
		self.assertEqual(self._recognised(card.name), {})
		je = self._accrual(net)
		log = frappe.get_doc("GL Posting Log", link_accrual_journal(je.name, json.dumps([card.name])))
		self.assertEqual(
			(log.origin, log.posting_type, log.posting_doctype, log.posting_doc, log.status),
			("Linked", "Journal Entry", "Journal Entry", je.name, "Submitted"),
		)
		self.assertEqual(flt(log.amount, 2), net)
		self.assertEqual(flt(log.link_difference, 2), 0)
		self.assertEqual(
			[(s.source_doctype, s.source_name) for s in log.sources], [("Card Monthly Card", card.name)]
		)
		self.assertEqual(
			frappe.db.get_value("Card Monthly Card", card.name, ["posted", "gl_posting"]), (1, log.name)
		)
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"))
		# D7: the statement counts the card as recognised
		self.assertEqual(self._recognised(card.name), {self.supplier: net})
		# never invoiced again: the monthly posting finds nothing to post
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)

	def test_journal_entry_is_linked_once_and_card_held_once(self):
		card = self._rental_card()
		je = self._accrual(flt(card.net_amount, 2))
		link_accrual_journal(je.name, [card.name])
		with self.assertRaises(frappe.ValidationError):
			link_accrual_journal(je.name, [card.name])
		other = self._accrual(flt(card.net_amount, 2))
		with self.assertRaises(frappe.ValidationError):
			link_accrual_journal(other.name, [card.name])

	def test_refusals(self):
		card = self._rental_card()
		net = flt(card.net_amount, 2)
		with self.assertRaises(frappe.ValidationError):  # draft journal entry
			link_accrual_journal(self._accrual(net, submit=False).name, [card.name])
		with self.assertRaises(frappe.ValidationError):  # a payment, not an accrual
			link_accrual_journal(self._accrual(net, debit_party=True).name, [card.name])
		with self.assertRaises(frappe.ValidationError):  # amount differs, not accepted
			link_accrual_journal(self._accrual(net + 100).name, [card.name])
		with self.assertRaises(frappe.ValidationError):  # card listed twice
			link_accrual_journal(self._accrual(net).name, [card.name, card.name])
		self.assertEqual(self._recognised(card.name), {})

	def test_vat_on_the_accrual_is_not_a_difference(self):
		card = self._rental_card()
		net = flt(card.net_amount, 2)
		je = self._accrual(flt(net * 1.15, 2), vat=flt(net * 0.15, 2))
		log = frappe.get_doc("GL Posting Log", link_accrual_journal(je.name, [card.name]))
		self.assertEqual(flt(log.link_difference, 2), 0)
		self.assertEqual(flt(log.amount, 2), flt(net * 1.15, 2))

	def test_entry_against_another_document_is_refused(self):
		card = self._rental_card()
		net = flt(card.net_amount, 2)
		pi = self._manual_pi(net)
		with self.assertRaisesRegex(frappe.ValidationError, "booked against"):
			link_accrual_journal(self._accrual(net, debit_party=True, reference=pi).name, [card.name])

	def test_accepted_difference_is_stored_with_the_reason(self):
		card = self._rental_card()
		je = self._accrual(flt(card.net_amount, 2) + 100)
		log = frappe.get_doc(
			"GL Posting Log",
			link_accrual_journal(
				je.name, [card.name], reason="transport booked on the same entry", accept_difference=1
			),
		)
		self.assertEqual(flt(log.link_difference, 2), 100)
		self.assertIn("transport booked on the same entry", log.remarks)

	def test_only_an_accountant_may_link(self):
		card = self._rental_card()
		je = self._accrual(flt(card.net_amount, 2))
		email = f"settle-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Card",
				"send_welcome_email": 0,
				"roles": [{"role": "Card Manager"}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				link_accrual_journal(je.name, [card.name])
		finally:
			frappe.set_user("Administrator")

	def test_cancelling_the_journal_entry_frees_the_card(self):
		card = self._rental_card()
		je = self._accrual(flt(card.net_amount, 2))
		log_name = link_accrual_journal(je.name, [card.name])
		je.reload()
		je.cancel()
		self.assertEqual(
			frappe.db.get_value("GL Posting Log", log_name, ["status", "posting_key"]), ("Cancelled", None)
		)
		self.assertEqual(
			frappe.db.get_value("Card Monthly Card", card.name, ["posted", "gl_posting"]), (0, "")
		)
		self.assertEqual(self._recognised(card.name), {})

	# ---------- D6: settlement status ----------

	def test_status_reads_paid_and_remaining_from_the_ledger(self):
		card = self._rental_card()
		net = flt(card.net_amount, 2)
		rows, summary = self._status()
		self.assertEqual(rows[card.name]["status"], "Not recognised yet")
		je = self._accrual(net)
		link_accrual_journal(je.name, [card.name])
		rows, _s = self._status()
		self.assertEqual(rows[card.name]["status"], "Recognised, not settled")
		self.assertEqual((rows[card.name]["share"], rows[card.name]["remaining"]), (net, net))
		# a bank payment not allocated to the accrual: card still open, payment shown apart
		self._payment(100)
		rows, summary = self._status()
		self.assertEqual(rows[card.name]["remaining"], net)
		self.assertEqual(summary["Payments not allocated to a document up to the end date"], 100)
		# a payment against the accrual: partly, then fully settled
		self._payment(flt(net / 2, 2), against=je.name)
		rows, _s = self._status()
		self.assertEqual(rows[card.name]["status"], "Partly settled")
		self.assertEqual(rows[card.name]["paid"], flt(net / 2, 2))
		self._payment(flt(net - flt(net / 2, 2), 2), against=je.name)
		rows, _s = self._status()
		self.assertEqual((rows[card.name]["status"], rows[card.name]["remaining"]), ("Fully settled", 0))

	def test_payments_are_allocated_oldest_first(self):
		first = self._rental_card()
		second = self._rental_card()
		older, newer = sorted([first, second], key=lambda c: (str(c.from_date), c.name))
		total = flt(first.net_amount + second.net_amount, 2)
		je = self._accrual(total)
		link_accrual_journal(je.name, [first.name, second.name])
		self._payment(flt(older.net_amount, 2), against=je.name)
		rows, _s = self._status()
		self.assertEqual(rows[older.name]["status"], "Fully settled")
		self.assertEqual(rows[newer.name]["status"], "Recognised, not settled")
		self.assertEqual(rows[newer.name]["remaining"], flt(newer.net_amount, 2))

	def test_status_needs_ledger_access(self):
		email = f"settle-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Card",
				"send_welcome_email": 0,
				"roles": [{"role": "Card User"}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		try:
			with self.assertRaises(frappe.PermissionError):
				self._status()
		finally:
			frappe.set_user("Administrator")

	def test_methods_are_post_only(self):
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[link_accrual_journal], ["POST"])
