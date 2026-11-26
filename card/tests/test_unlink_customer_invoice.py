# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-195: remove a wrong customer invoice link (``card.gl.integrity.unlink_customer_invoice``).

The undo of FR-194 for a company that cannot cancel a submitted Sales Invoice: the Linked GL Posting Log goes to
Cancelled (it stays as the audit record), each card loses exactly what the link wrote, and the invoice and the
cards can be linked again. Nothing is posted, cancelled or amended; the invoice and the ledger are not changed.
All data is synthetic and rolled back."""

import inspect
import types

import frappe
from frappe.handler import is_valid_http_method
from frappe.utils import flt

from card.gl.events import active_log_holding
from card.gl.integrity import (
	link_customer_invoice,
	unlink_customer_invoice,
	unlinked_customer_invoice_candidates,
)
from card.gl.journal_link import link_accrual_journal
from card.gl.posting import build_monthly_posting
from card.tests.test_link_customer_invoice import CARD, LOG, REASON, SI, _LinkBase
from card.tests.test_p0_posting_integrity import _user

UNLINK_REASON = "The invoice was linked to the cards of another month"
LINK_FIELDS = ["sales_invoice", "posted", "gl_posting"]


class _UnlinkBase(_LinkBase):
	def _linked(self, rate=1600, **card_kw):
		"""(invoice, card, log name) of one linked pair."""
		card = self._out_card(**card_kw)
		si = self._si(rate)
		return si, card, self._link(si, card)

	def _state(self, *cards):
		return [
			(*(v or "" for v in frappe.db.get_value(CARD, card.name, LINK_FIELDS)), card.name)
			for card in cards
		]

	def _accrued_sub_rental_card(self):
		"""A sub-rental card whose supplier side is recognised by a linked accrual Journal Entry: the card is
		posted on that side without a purchase invoice link."""
		card = self._card(self._sub_rental(), [8, 8], submit=True)
		row = next(r for r in frappe.get_doc("Card Settings").company_settings if r.company == self.company)
		amount = flt(card.net_amount, 2)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": "2026-09-30",
				"voucher_type": "Journal Entry",
				"accounts": [
					{
						"account": self.exp_rental,
						"cost_center": row.cost_center,
						"debit_in_account_currency": amount,
					},
					{
						"account": row.payable_account,
						"party_type": "Supplier",
						"party": self.supplier,
						"cost_center": row.cost_center,
						"credit_in_account_currency": amount,
					},
				],
			}
		).insert(ignore_permissions=True)
		je.submit()
		accrual_log = link_accrual_journal(je.name, [card.name])
		self.assertEqual(self._state(card), [("", 1, accrual_log, card.name)])
		return card, accrual_log

	def _restricted(self, roles, allow, value):
		"""A user whose Card Monthly Card access is limited to one ``allow`` record (User Permission)."""
		user = _user(roles)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": allow,
				"for_value": value,
				"apply_to_all_doctypes": 0,
				"applicable_for": CARD,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)
		return user

	def _comments(self, doctype, name):
		return frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": doctype,
				"reference_name": name,
				"comment_type": "Info",
				"content": ["like", "%Unlinked%"],
			},
			pluck="content",
		)

	def _refused(self, pattern, invoice, log, *cards, reason=UNLINK_REASON, error=frappe.ValidationError):
		"""The unlink is refused and nothing of the link changed."""
		before = (
			self._state(*cards),
			frappe.db.get_value(LOG, log, ["status", "remarks", "posting_key", "modified"]) if log else None,
			frappe.db.count("Comment"),
		)
		with self.assertRaisesRegex(error, pattern):
			unlink_customer_invoice(invoice.name, reason)
		after = (
			self._state(*cards),
			frappe.db.get_value(LOG, log, ["status", "remarks", "posting_key", "modified"]) if log else None,
			frappe.db.count("Comment"),
		)
		self.assertEqual(after, before, "a refused unlink changed the link")


class TestUnlinkCustomerInvoice(_UnlinkBase):
	def test_signature_and_post_only(self):
		self.assertEqual(list(inspect.signature(unlink_customer_invoice).parameters), ["invoice", "reason"])
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[unlink_customer_invoice], ["POST"])
		saved = getattr(frappe.local, "request", None)
		try:
			frappe.local.request = types.SimpleNamespace(method="GET")
			with self.assertRaises(frappe.PermissionError):
				is_valid_http_method(unlink_customer_invoice)
			frappe.local.request = types.SimpleNamespace(method="POST")
			is_valid_http_method(unlink_customer_invoice)
		finally:
			if saved is None:
				del frappe.local.request
			else:
				frappe.local.request = saved

	def test_unlink_clears_the_cards_and_closes_the_log(self):
		card_a = self._out_card()  # 1,600
		card_b = self._out_card(hours=(8,), customer_rate=500)  # 400
		si = self._si(2000, vat=True)
		log = self._link(si, card_a, card_b)
		link_remarks = frappe.db.get_value(LOG, log, "remarks")

		self.assertEqual(unlink_customer_invoice(si.name, UNLINK_REASON), log)

		for card in (card_a, card_b):
			self.assertEqual(self._state(card), [("", 0, "", card.name)])
			self.assertIsNone(active_log_holding(CARD, card.name, "Customer"))
		stored = frappe.get_doc(LOG, log)
		# the log stays: it is the audit record of the link and of its removal
		self.assertEqual((stored.status, stored.origin, stored.posting_doc), ("Cancelled", "Linked", si.name))
		self.assertFalse(stored.posting_key)
		self.assertEqual(
			sorted((r.source_name, flt(r.amount, 2)) for r in stored.sources),
			sorted([(card_a.name, 1600.0), (card_b.name, 400.0)]),
		)
		# the audit text: the link text is kept, then who, when, why and the previous links
		self.assertTrue(stored.remarks.startswith(link_remarks))
		audit = stored.remarks[len(link_remarks) :]
		for expected in (
			"Unlinked",
			"Administrator",
			UNLINK_REASON,
			si.name,
			log,
			card_a.name,
			card_b.name,
			"1600.0",
			"400.0",
			frappe.utils.nowdate(),
		):
			self.assertIn(expected, audit)
		self.assertFalse(
			frappe.db.exists(LOG, {"posting_doc": si.name, "status": ["in", ["Draft", "Submitted"]]})
		)

	def test_unlink_adds_an_info_comment_on_the_invoice_and_on_each_card(self):
		si, card, log = self._linked()
		unlink_customer_invoice(si.name, "<b>wrong</b> month & customer")
		invoice_comments = self._comments(SI, si.name)
		card_comments = self._comments(CARD, card.name)
		self.assertEqual((len(invoice_comments), len(card_comments)), (1, 1))
		for content in (*invoice_comments, *card_comments):
			self.assertIn("Administrator", content)
			self.assertIn("wrong", content)
			self.assertNotIn("<b>", content)
			self.assertIn(log, content)
		self.assertIn(card.name, invoice_comments[0])
		self.assertIn(si.name, card_comments[0])
		self.assertNotIn("<b>", frappe.db.get_value(LOG, log, "remarks"))

	def test_unlink_changes_no_ledger_no_invoice_and_gives_the_card_back_as_it_was(self):
		card = self._out_card()
		si = self._si(1600, vat=True)

		def ledger():
			return (
				frappe.db.sql("select count(*), sum(debit), sum(credit), max(modified) from `tabGL Entry`")[
					0
				],
				frappe.db.sql("select count(*), sum(amount), max(modified) from `tabPayment Ledger Entry`")[
					0
				],
			)

		def children(doctype, parent):
			return frappe.get_all(
				doctype, filters={"parent": parent}, fields=["name", "modified"], order_by="idx asc"
			)

		def invoice_rows():
			return (
				frappe.db.get_value(SI, si.name, "*", as_dict=True),
				children("Sales Invoice Item", si.name),
				children("Sales Taxes and Charges", si.name),
			)

		def card_rows():
			row = frappe.db.get_value(CARD, card.name, "*", as_dict=True)
			for field in LINK_FIELDS:
				row[field] = row[field] or ""
			return (
				row,
				children("Card Monthly Card Day", card.name),
				children("Card Monthly Card Adjustment", card.name),
			)

		card_before_link = card_rows()
		self._link(si, card)
		ledger_before, invoice_before = ledger(), invoice_rows()
		counts_before = (frappe.db.count(SI), frappe.db.count(LOG), frappe.db.count("Version"))
		linked = card_rows()[0]

		unlink_customer_invoice(si.name, UNLINK_REASON)

		self.assertEqual(ledger(), ledger_before, "the unlink wrote to the ledger")
		self.assertEqual(invoice_rows(), invoice_before, "the unlink changed the Sales Invoice")
		self.assertEqual(
			(frappe.db.count(SI), frappe.db.count(LOG), frappe.db.count("Version")),
			counts_before,
			"the unlink created or deleted a document",
		)
		self.assertEqual(frappe.db.get_value(SI, si.name, "docstatus"), 1)
		after = card_rows()
		changed = {k for k, v in after[0].items() if v != linked.get(k)}
		# the only card columns an unlink writes are the three the link wrote
		self.assertEqual(changed, set(LINK_FIELDS))
		# and the card is again exactly the card it was before the link (modified and amounts included)
		self.assertEqual(after, card_before_link)

	def test_invoice_and_cards_can_be_linked_again(self):
		si, card, first = self._linked()
		other = self._out_card()
		unlink_customer_invoice(si.name, UNLINK_REASON)

		rows = {r["invoice"]: r for r in unlinked_customer_invoice_candidates(self.company)["invoices"]}
		self.assertIn(si.name, rows, "the unlinked invoice is not a candidate again")
		self.assertIn(card.name, [c["name"] for c in rows[si.name]["cards"]])

		# the same invoice, another card this time
		second = self._link(si, other)
		self.assertNotEqual(second, first)
		self.assertEqual(
			(frappe.db.get_value(LOG, first, "status"), frappe.db.get_value(LOG, second, "status")),
			("Cancelled", "Submitted"),
		)
		self.assertEqual(self._state(other), [(si.name, 1, second, other.name)])
		self.assertEqual(self._state(card), [("", 0, "", card.name)])
		# and the freed card links to another invoice
		third = self._link(self._si(1600), card)
		self.assertEqual(frappe.db.get_value(CARD, card.name, "gl_posting"), third)
		# a second removal acts on the new link only
		self.assertEqual(unlink_customer_invoice(si.name, UNLINK_REASON), second)
		self.assertEqual(frappe.db.get_value(LOG, first, "status"), "Cancelled")
		self.assertEqual(self._state(other), [("", 0, "", other.name)])
		self.assertEqual(frappe.db.count(LOG, {"posting_doc": si.name}), 2)

	def test_unlinked_card_is_built_by_card_again(self):
		si, card, _log = self._linked()
		unlink_customer_invoice(si.name, UNLINK_REASON)
		built = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		self.assertEqual(frappe.db.get_value(SI, built, "docstatus"), 0)
		self.assertEqual(active_log_holding(CARD, card.name, "Customer").posting_doc, built)

	def test_sub_rental_card_keeps_its_supplier_side(self):
		eq = self._sub_rental()
		card = self._card(eq, [8, 8], submit=True)
		# the supplier side is a CARD draft: the display link of the card is on that log
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		supplier_log = active_log_holding(CARD, card.name, "Supplier").name
		si = self._si(flt(card.customer_net_amount, 2))
		log = self._link(si, card)
		self.assertEqual(self._state(card), [(si.name, 1, supplier_log, card.name)])

		unlink_customer_invoice(si.name, UNLINK_REASON)

		self.assertEqual(self._state(card), [("", 0, supplier_log, card.name)])
		self.assertEqual(frappe.db.get_value(LOG, log, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value(LOG, supplier_log, ["status", "posting_doc"]), ("Draft", pi))
		self.assertFalse(frappe.db.get_value(CARD, card.name, "purchase_invoice"))

	def test_sub_rental_card_posted_on_the_supplier_side_stays_posted(self):
		eq = self._sub_rental()
		card = self._card(eq, [8, 8], submit=True)
		si = self._si(flt(card.customer_net_amount, 2))
		self._link(si, card)
		# the supplier side was invoiced after the link
		frappe.db.set_value(CARD, card.name, "purchase_invoice", "PINV-ELSEWHERE", update_modified=False)
		unlink_customer_invoice(si.name, UNLINK_REASON)
		stored = frappe.db.get_value(CARD, card.name, ["sales_invoice", "posted", "purchase_invoice"])
		self.assertEqual((stored[0] or "", stored[1], stored[2]), ("", 1, "PINV-ELSEWHERE"))


class TestUnlinkKeepsTheSupplierSide(_UnlinkBase):
	"""Review of the pull request: a linked accrual Journal Entry posts the supplier side of a card without a
	purchase invoice link (``card.gl.journal_link.link_accrual_journal``)."""

	def test_card_accrued_by_a_journal_entry_stays_posted_after_the_unlink(self):
		card, accrual_log = self._accrued_sub_rental_card()
		si = self._si(flt(card.customer_net_amount, 2))
		self._link(si, card)
		self.assertEqual(self._state(card), [(si.name, 1, accrual_log, card.name)])

		unlink_customer_invoice(si.name, UNLINK_REASON)

		self.assertEqual(self._state(card), [("", 1, accrual_log, card.name)])
		self.assertEqual(frappe.db.get_value(LOG, accrual_log, "status"), "Submitted")

	def test_card_accrued_by_a_journal_entry_stays_posted_after_the_invoice_is_cancelled(self):
		# the same rule on the cancel path of a linked invoice (card.gl.events.before_cancel)
		card, accrual_log = self._accrued_sub_rental_card()
		si = self._si(flt(card.customer_net_amount, 2))
		self._link(si, card)
		si.reload()
		si.cancel()
		self.assertEqual(self._state(card), [("", 1, accrual_log, card.name)])


class TestUnlinkRefusals(_UnlinkBase):
	def test_reason_is_required(self):
		si, card, log = self._linked()
		for reason in (None, "", "   ", "<p> </p>"):
			self._refused("Give the reason", si, log, card, reason=reason)

	def test_invoice_without_a_link_is_refused(self):
		card = self._out_card()
		si = self._si(1600)
		self._refused("is not linked to CARD cards", si, None, card)
		# a removed link is not removed twice
		log = self._link(si, card)
		unlink_customer_invoice(si.name, UNLINK_REASON)
		self._refused("is not linked to CARD cards", si, log, card)

	def test_card_built_posting_is_refused(self):
		card = self._out_card()
		built = frappe.get_doc(SI, build_monthly_posting(self.company, "Customer", self.customer, 9, 2026))
		draft_log = active_log_holding(CARD, card.name, "Customer").name
		self._refused("not submitted", built, draft_log, card)
		built.submit()
		self._refused("is a CARD posting", built, draft_log, card)
		self.assertEqual(frappe.db.get_value(LOG, draft_log, "status"), "Submitted")
		self.assertEqual(frappe.db.get_value(CARD, card.name, "sales_invoice"), built.name)
		# a posting log without an origin is a built one
		frappe.db.set_value(LOG, draft_log, "origin", "", update_modified=False)
		self._refused("is a CARD posting", built, draft_log, card)

	def test_cancelled_invoice_is_refused(self):
		si, card, log = self._linked()
		frappe.db.set_value(SI, si.name, "docstatus", 2, update_modified=False)
		self._refused("not submitted", si, log, card)

	def test_card_invoiced_elsewhere_since_the_link_is_refused_and_named(self):
		card_a = self._out_card()
		card_b = self._out_card(hours=(8,), customer_rate=500)
		si = self._si(2000)
		log = self._link(si, card_a, card_b)
		frappe.db.set_value(CARD, card_b.name, "sales_invoice", "SINV-ELSEWHERE", update_modified=False)
		# nothing is partly undone: the first card keeps its link
		self._refused(card_b.name + ".*SINV-ELSEWHERE", si, log, card_a, card_b)
		self.assertEqual(frappe.db.get_value(CARD, card_a.name, "sales_invoice"), si.name)

	def test_card_without_its_invoice_link_is_refused(self):
		si, card, log = self._linked()
		frappe.db.set_value(CARD, card.name, "sales_invoice", "", update_modified=False)
		self._refused(card.name, si, log, card)

	def test_card_pointing_at_another_log_is_refused(self):
		si, card, log = self._linked()
		for other in ("GLP-ELSEWHERE", ""):
			frappe.db.set_value(CARD, card.name, "gl_posting", other, update_modified=False)
			self._refused(card.name, si, log, card)

	def test_card_not_marked_posted_or_not_submitted_is_refused(self):
		si, card, log = self._linked()
		frappe.db.set_value(CARD, card.name, "posted", 0, update_modified=False)
		self._refused(card.name + ".*not marked as posted", si, log, card)
		frappe.db.set_value(CARD, card.name, {"posted": 1, "docstatus": 2}, update_modified=False)
		self._refused(card.name + ".*no longer submitted", si, log, card)

	def test_invoice_amended_by_another_is_refused(self):
		si, card, log = self._linked()
		amendment = self._si(1600, submit=False)
		frappe.db.set_value(SI, amendment.name, "amended_from", si.name, update_modified=False)
		self._refused("cancelled-and-amended chain mismatch.*" + amendment.name, si, log, card)

	def test_amendment_whose_earlier_invoice_still_holds_a_link_is_refused(self):
		earlier, earlier_card, earlier_log = self._linked()
		si, card, log = self._linked()
		frappe.db.set_value(SI, si.name, "amended_from", earlier.name, update_modified=False)
		self._refused("cancelled-and-amended chain mismatch.*" + earlier.name, si, log, card, earlier_card)
		self.assertEqual(frappe.db.get_value(LOG, earlier_log, "status"), "Submitted")

	def test_amendment_with_its_own_exact_link_is_unlinked(self):
		# the earlier invoice was cancelled: its link was freed by the cancel, the amendment was linked afresh
		earlier, earlier_card, earlier_log = self._linked()
		earlier.reload()
		earlier.cancel()
		self.assertEqual(frappe.db.get_value(LOG, earlier_log, "status"), "Cancelled")
		si = self._si(1600)
		frappe.db.set_value(SI, si.name, "amended_from", earlier.name, update_modified=False)
		log = self._link(si, earlier_card)
		self.assertEqual(unlink_customer_invoice(si.name, UNLINK_REASON), log)
		self.assertEqual(self._state(earlier_card), [("", 0, "", earlier_card.name)])
		self.assertEqual(frappe.db.get_value(LOG, earlier_log, "remarks").count("Unlinked"), 0)

	def test_log_with_a_source_that_is_not_a_card_is_refused(self):
		si, card, log = self._linked()
		row = frappe.db.get_value("GL Posting Source", {"parent": log}, "name")
		frappe.db.set_value(
			"GL Posting Source", row, "source_doctype", "Equipment Transport", update_modified=False
		)
		self._refused("not a monthly card", si, log, card)


class TestUnlinkCustomerAuthorization(_UnlinkBase):
	def test_only_a_system_manager_may_unlink(self):
		si, card, log = self._linked()
		for roles in (
			["Accounts Manager"],
			["Accounts Manager", "Card Manager"],
			["Accounts User", "Card Manager"],
			["Card Manager"],
			["Card User"],
		):
			with self.subTest(roles=roles), self.assertRaises(frappe.PermissionError):
				self._as(_user(roles), unlink_customer_invoice, si.name, UNLINK_REASON)
		self.assertEqual(frappe.db.get_value(LOG, log, "status"), "Submitted")
		self.assertEqual(frappe.db.get_value(CARD, card.name, "sales_invoice"), si.name)

	def test_system_manager_can_unlink(self):
		si, card, log = self._linked()
		# Accounts User gives the read right on Sales Invoice; alone it is refused (test above)
		user = _user(["System Manager", "Accounts User"])
		self.assertEqual(self._as(user, unlink_customer_invoice, si.name, UNLINK_REASON), log)
		self.assertEqual(frappe.db.get_value(LOG, log, "status"), "Cancelled")
		self.assertIn(user, frappe.db.get_value(LOG, log, "remarks"))
		self.assertIn(user, self._comments(CARD, card.name)[0])

	def test_system_manager_of_another_company_is_refused(self):
		si, card, log = self._linked()
		user = _user(["System Manager", "Accounts Manager"], restrict_to=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			self._as(user, unlink_customer_invoice, si.name, UNLINK_REASON)
		self.assertEqual(frappe.db.get_value(LOG, log, "status"), "Submitted")
		self.assertEqual(frappe.db.get_value(CARD, card.name, "sales_invoice"), si.name)

	def test_company_outside_the_card_scope_of_the_caller_is_refused(self):
		# the invoice is readable (no Company restriction on Sales Invoice); the CARD scope is another company
		si, card, log = self._linked()
		user = self._restricted(["System Manager", "Accounts User"], "Company", self._other_company())
		frappe.set_user(user)
		self.assertTrue(frappe.get_doc(SI, si.name).has_permission("read"))
		frappe.set_user("Administrator")
		before = (self._state(card), frappe.db.get_value(LOG, log, ["status", "remarks"]))
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to unlink invoices for company"):
			self._as(user, unlink_customer_invoice, si.name, UNLINK_REASON)
		self.assertEqual((self._state(card), frappe.db.get_value(LOG, log, ["status", "remarks"])), before)
		self.assertFalse(self._comments(SI, si.name))

	def test_card_the_caller_cannot_read_is_refused(self):
		card_a = self._out_card()
		card_b = self._out_card(hours=(8,), customer_rate=500, project=self._second_project())
		si = self._si(0, lines=[(1600, self.project), (400, card_b.project)])
		log = self._link(si, card_a, card_b)
		# the caller reads the cards of the first project only
		user = self._restricted(["System Manager", "Accounts User"], "Project", self.project)
		before = (self._state(card_a, card_b), frappe.db.get_value(LOG, log, ["status", "remarks"]))
		with self.assertRaises(frappe.PermissionError):
			self._as(user, unlink_customer_invoice, si.name, UNLINK_REASON)
		self.assertEqual(
			(self._state(card_a, card_b), frappe.db.get_value(LOG, log, ["status", "remarks"])), before
		)
		self.assertFalse(self._comments(SI, si.name))
		self.assertFalse(self._comments(CARD, card_a.name))

	def test_relink_after_an_unlink_by_an_accounts_manager(self):
		si, card, _log = self._linked()
		unlink_customer_invoice(si.name, UNLINK_REASON)
		second = self._as(_user(["Accounts Manager"]), link_customer_invoice, si.name, [card.name], REASON)
		self.assertEqual(frappe.db.get_value(LOG, second, ["origin", "status"]), ("Linked", "Submitted"))
