# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-194: link a submitted Sales Invoice that was booked by hand in ERPNext to the customer monthly cards it
bills (``card.gl.integrity.link_customer_invoice``), and the read-only audit list
``card.gl.integrity.unlinked_customer_invoice_candidates``.

The link is the customer mirror of ``link_supplier_invoice``: one Linked GL Posting Log, one source row per card,
and the customer invoice link on each card. It posts nothing and changes neither the invoice nor a card amount.
All data is synthetic and rolled back."""

import inspect

import frappe
from frappe.utils import flt

from card.gl.events import active_log_holding
from card.gl.integrity import link_customer_invoice, unlinked_customer_invoice_candidates
from card.gl.posting import build_monthly_posting
from card.open_month import STATE_OPEN_MONTH, financial_holders
from card.tests.cancel_reason import with_reason
from card.tests.test_p0_posting_integrity import _AuthBase, _user

CARD = "Card Monthly Card"
LOG = "GL Posting Log"
SI = "Sales Invoice"
REASON = "The invoice was booked in ERPNext before the cards"
SEPTEMBER = dict(from_month=9, from_year=2026, to_month=9, to_year=2026)


class _LinkBase(_AuthBase):
	def _out_card(self, hours=(8, 8), customer_rate=1000, submit=True, customer=None, **presets):
		"""A rented-out card of 09/2026: 16 h at 100 per hour = 1,600 customer net."""
		eq = self._rented_out(customer=customer, customer_rate=customer_rate)
		return self._card(eq, list(hours), submit=submit, **presets)

	def _second_project(self):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-LINK-PRJ-B-" + self.token
		proj.company = self.company
		proj.cost_center = frappe.db.get_value(
			"Cost Center", {"company": self.company, "is_group": 0}, "name"
		)
		proj.insert(ignore_permissions=True)
		return proj.name

	def _si(
		self,
		rate,
		posting_date="2026-09-30",
		customer=None,
		line_project="default",
		header_project=None,
		vat=False,
		submit=True,
	):
		"""A Sales Invoice booked by hand (not built by CARD), one line, net = ``rate``."""
		from card.gl.masters import ensure_posting_masters, ensure_selling_price_list

		row = ensure_posting_masters(self.company)
		item = {"item_code": row.rental_item, "qty": 1, "rate": rate, "income_account": self.inc_rental}
		project = self.project if line_project == "default" else line_project
		if project:
			item["project"] = project
		doc = frappe.get_doc(
			{
				"doctype": SI,
				"company": self.company,
				"customer": customer or self.customer,
				"set_posting_time": 1,
				"posting_date": posting_date,
				"due_date": posting_date,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"selling_price_list": ensure_selling_price_list(self.company),
				"items": [item],
			}
		)
		if header_project:
			doc.project = header_project
		if vat:
			from erpnext.controllers.accounts_controller import get_taxes_and_charges

			template = frappe.db.get_value(
				"Sales Taxes and Charges Template",
				{"title": "Test CARD Sales VAT", "company": self.company},
				"name",
			)
			doc.taxes_and_charges = template
			for tax_row in get_taxes_and_charges("Sales Taxes and Charges Template", template):
				doc.append("taxes", tax_row)
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		doc.reload()
		return doc

	def _link(self, invoice, *cards, reason=REASON):
		return link_customer_invoice(invoice.name, [c.name for c in cards], reason)

	def _refused(self, pattern, invoice, *cards, reason=REASON, error=frappe.ValidationError):
		with self.assertRaisesRegex(error, pattern):
			self._link(invoice, *cards, reason=reason)
		self.assertFalse(
			frappe.db.exists(LOG, {"posting_doc": invoice.name, "status": ["in", ["Draft", "Submitted"]]}),
			"a refused link left a posting log",
		)


class TestLinkCustomerInvoice(_LinkBase):
	def test_link_writes_one_log_its_sources_and_the_card_links(self):
		card_a = self._out_card()  # 1,600
		card_b = self._out_card(hours=(8,), customer_rate=500)  # 8 h x 50 = 400
		si = self._si(2000, vat=True)
		self.assertEqual((flt(si.net_total, 2), flt(si.grand_total, 2)), (2000.0, 2300.0))

		log = frappe.get_doc(LOG, self._link(si, card_a, card_b))

		self.assertEqual(
			(log.origin, log.status, log.party_type, log.party, log.company),
			("Linked", "Submitted", "Customer", self.customer, self.company),
		)
		self.assertEqual((log.posting_type, log.posting_doctype, log.posting_doc), (SI, SI, si.name))
		self.assertEqual((log.month, int(log.year)), ("09", 2026))
		self.assertEqual(flt(log.amount, 2), 2300.0)
		self.assertEqual(flt(log.link_difference, 2), 0)
		self.assertIn(REASON, log.remarks)
		self.assertIn("Administrator", log.remarks)
		self.assertEqual(
			sorted((r.source_doctype, r.source_name, flt(r.amount, 2)) for r in log.sources),
			sorted([(CARD, card_a.name, 1600.0), (CARD, card_b.name, 400.0)]),
		)
		for card in (card_a, card_b):
			stored = frappe.db.get_value(
				CARD, card.name, ["sales_invoice", "posted", "gl_posting"], as_dict=True
			)
			self.assertEqual((stored.sales_invoice, stored.posted, stored.gl_posting), (si.name, 1, log.name))
			self.assertEqual(active_log_holding(CARD, card.name, "Customer").name, log.name)

	def test_link_adds_an_info_comment_on_the_invoice_and_on_each_card(self):
		card = self._out_card()
		si = self._si(1600)
		self._link(si, card, reason="<b>late</b> entry & review")
		for doctype, name in ((SI, si.name), (CARD, card.name)):
			comments = frappe.get_all(
				"Comment",
				filters={
					"reference_doctype": doctype,
					"reference_name": name,
					"comment_type": "Info",
					"content": ["like", "%Linked%"],
				},
				pluck="content",
			)
			self.assertEqual(len(comments), 1, (doctype, comments))
			self.assertIn("Administrator", comments[0])
			self.assertIn("late", comments[0])
			self.assertNotIn("<b>", comments[0])
		card_comment = frappe.get_all(
			"Comment",
			filters={"reference_doctype": CARD, "reference_name": card.name, "comment_type": "Info"},
			pluck="content",
		)
		self.assertTrue(any(si.name in c for c in card_comment))

	def test_link_changes_no_ledger_invoice_or_card_amount(self):
		card = self._out_card()
		si = self._si(1600, vat=True)

		def ledger():
			return (
				frappe.db.count("GL Entry"),
				frappe.db.sql(
					"select count(*), sum(debit), sum(credit) from `tabGL Entry` where voucher_no=%s", si.name
				)[0],
				frappe.db.count("Payment Ledger Entry"),
				frappe.db.sql(
					"select count(*), sum(amount) from `tabPayment Ledger Entry` where voucher_no=%s", si.name
				)[0],
			)

		def children(doctype, parent):
			return frappe.db.sql(
				f"select count(*), max(modified) from `tab{doctype}` where parent=%s", parent
			)[0]

		def invoice_rows():
			return (
				frappe.db.get_value(SI, si.name, "*", as_dict=True),
				children("Sales Invoice Item", si.name),
				children("Sales Taxes and Charges", si.name),
			)

		def card_rows():
			return (
				frappe.db.get_value(CARD, card.name, "*", as_dict=True),
				children("Card Monthly Card Day", card.name),
				children("Card Monthly Card Adjustment", card.name),
			)

		ledger_before, invoice_before, card_before = ledger(), invoice_rows(), card_rows()
		invoices_before = frappe.db.count(SI)
		self._link(si, card)

		self.assertEqual(ledger(), ledger_before, "the link wrote to the ledger")
		self.assertEqual(frappe.db.count(SI), invoices_before)
		self.assertEqual(invoice_rows(), invoice_before, "the link changed the Sales Invoice")
		card_after = card_rows()
		self.assertEqual(card_after[1:], card_before[1:], "the link changed a day or adjustment row")
		changed = {k for k, v in card_after[0].items() if v != card_before[0].get(k)}
		# the only card columns a link writes: the customer invoice link, the posted flag, the display link
		self.assertEqual(changed, {"sales_invoice", "posted", "gl_posting"})
		for field in ("modified", "docstatus", "workflow_state", "customer_amount", "customer_net_amount"):
			self.assertEqual(card_after[0][field], card_before[0][field], field)

	def test_second_call_for_the_same_invoice_is_refused(self):
		card = self._out_card()
		other = self._out_card(hours=(8,), customer_rate=500)
		si = self._si(1600)
		self._link(si, card)
		with self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting or linked"):
			self._link(si, card)
		with self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting or linked"):
			self._link(si, other)
		self.assertEqual(frappe.db.count(LOG, {"posting_doc": si.name}), 1)

	def test_reason_is_required(self):
		card = self._out_card()
		si = self._si(1600)
		for reason in (None, "", "   ", "<p> </p>"):
			self._refused("Give the reason", si, card, reason=reason)

	def test_there_is_no_accept_the_difference_option(self):
		self.assertEqual(
			list(inspect.signature(link_customer_invoice).parameters), ["invoice", "cards", "reason"]
		)

	def test_amount_difference_is_always_refused(self):
		card = self._out_card()
		self._refused("Linked amounts differ|net", self._si(1500), card)
		self._refused("net", self._si(1600.02), card)
		# VAT is not part of the comparison: gross 1,600 is net 1,391.30
		self._refused("net", self._si(1391.30, vat=True), card)

	def test_difference_within_the_reconciliation_tolerance_links(self):
		card = self._out_card()
		si = self._si(1600.01)
		log = frappe.get_doc(LOG, self._link(si, card))
		self.assertEqual(flt(log.sources[0].amount, 2), 1600.0)

	def test_cards_as_a_json_string(self):
		card = self._out_card()
		si = self._si(1600)
		log = link_customer_invoice(si.name, frappe.as_json([card.name]), REASON)
		self.assertEqual(frappe.db.get_value(CARD, card.name, "sales_invoice"), si.name)
		self.assertEqual(frappe.db.get_value(LOG, log, "origin"), "Linked")

	def test_header_project_of_the_invoice_is_enough(self):
		card = self._out_card()
		si = self._si(1600, line_project=None, header_project=self.project)
		self._link(si, card)
		self.assertEqual(frappe.db.get_value(CARD, card.name, "sales_invoice"), si.name)

	def test_sub_rental_card_keeps_its_supplier_side_free(self):
		eq = self._sub_rental()  # customer side 16 h x 120 = 1,920
		card = self._card(eq, [8, 8], submit=True)
		si = self._si(flt(card.customer_net_amount, 2))
		self._link(si, card)
		stored = frappe.db.get_value(CARD, card.name, ["sales_invoice", "purchase_invoice"], as_dict=True)
		self.assertEqual((stored.sales_invoice, stored.purchase_invoice or ""), (si.name, ""))
		self.assertIsNone(active_log_holding(CARD, card.name, "Supplier"))
		# the supplier side is still built by CARD
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(frappe.db.get_value("Purchase Invoice", pi, "docstatus"), 0)

	def test_linked_card_is_held_and_never_built_again(self):
		card = self._out_card()
		si = self._si(1600)
		self._link(si, card)
		self.assertTrue(financial_holders(frappe.get_doc(CARD, card.name)))
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		with self.assertRaises(frappe.ValidationError):
			with_reason(frappe.get_doc(CARD, card.name)).cancel()

	def test_cancelling_the_invoice_frees_the_cards(self):
		"""The only undo CARD has (as on the supplier side). A company under ZATCA cannot cancel a submitted
		Sales Invoice; that block belongs to ksa_compliance, which is not installed here."""
		card = self._out_card()
		si = self._si(1600)
		log = self._link(si, card)
		si.reload()
		si.cancel()
		stored = frappe.db.get_value(CARD, card.name, ["sales_invoice", "posted", "gl_posting"], as_dict=True)
		self.assertEqual((stored.sales_invoice or "", stored.posted, stored.gl_posting or ""), ("", 0, ""))
		self.assertEqual(frappe.db.get_value(LOG, log, "status"), "Cancelled")
		self.assertIsNone(active_log_holding(CARD, card.name, "Customer"))


class TestLinkRefusals(_LinkBase):
	def test_invoice_must_be_submitted(self):
		card = self._out_card()
		self._refused("not submitted", self._si(1600, submit=False), card)
		cancelled = self._si(1600)
		cancelled.cancel()
		self._refused("not submitted", cancelled, card)

	def test_return_debit_note_and_opening_invoices_are_refused(self):
		card = self._out_card()
		for field, value, pattern in (
			("is_return", 1, "return"),
			("is_debit_note", 1, "debit note"),
			("is_opening", "Yes", "opening"),
		):
			si = self._si(1600)
			frappe.db.set_value(SI, si.name, field, value, update_modified=False)
			self._refused(pattern, si, card)

	def test_card_built_invoice_is_refused(self):
		card = self._out_card()
		built = frappe.get_doc(SI, build_monthly_posting(self.company, "Customer", self.customer, 9, 2026))
		built.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting or linked"):
			self._link(built, card)

	def test_no_card_and_a_card_listed_twice(self):
		card = self._out_card()
		si = self._si(3200)
		self._refused("Choose the monthly cards", si)
		self._refused("listed twice", si, card, card)

	def test_card_must_be_submitted_and_approved(self):
		si = self._si(1600)
		self._refused("not submitted", si, self._out_card(submit=False))
		cancelled = self._out_card()
		with_reason(cancelled).cancel()
		self._refused("not submitted", si, cancelled)
		opened = self._out_card()
		frappe.db.set_value(CARD, opened.name, "workflow_state", STATE_OPEN_MONTH, update_modified=False)
		self._refused("month has not ended|not approved", si, opened)

	def test_card_must_bill_a_customer(self):
		rented_in = self._card(self._equipment(), [8, 8], submit=True)
		self._refused("not billed to a customer", self._si(1600), rented_in)

	def test_card_of_another_company_customer_or_project_is_refused(self):
		si = self._si(1600)
		other_customer = self._out_card(customer=self._customer("-B"))
		self._refused("another customer", si, other_customer)
		other_project = self._out_card(project=self._second_project())
		self._refused("project", si, other_project)
		other_company = self._out_card()
		frappe.db.set_value(CARD, other_company.name, "company", self._other_company(), update_modified=False)
		self._refused("another company", si, other_company)

	def test_invoice_without_a_project_is_refused(self):
		card = self._out_card()
		self._refused("project", self._si(1600, line_project=None), card)

	def test_card_already_invoiced_or_held_is_refused(self):
		linked = self._out_card()
		self._link(self._si(1600), linked)
		self._refused("already invoiced", self._si(1600), linked)
		# a card in a CARD draft posting is held before it carries an invoice link
		customer_b = self._customer("-B")
		held = self._out_card(customer=customer_b)
		draft = build_monthly_posting(self.company, "Customer", customer_b, 9, 2026)
		self.assertFalse(frappe.db.get_value(CARD, held.name, "sales_invoice"))
		self._refused("already held by " + draft, self._si(1600, customer=customer_b), held)

	def test_rented_out_card_marked_posted_is_refused(self):
		card = self._out_card()
		frappe.db.set_value(CARD, card.name, "posted", 1, update_modified=False)
		self._refused("marked posted", self._si(1600), card)


class TestLinkCustomerAuthorization(_LinkBase):
	def _args(self):
		card = self._out_card()
		return self._si(1600).name, [card.name], REASON

	def test_roles_other_than_the_two_are_refused(self):
		invoice, cards, reason = self._args()
		for roles in (
			["Card Manager"],
			["Card Manager", "Sales User"],
			["Accounts User", "Card Manager"],
			["Card User"],
		):
			with self.subTest(roles=roles), self.assertRaises(frappe.PermissionError):
				self._as(_user(roles), link_customer_invoice, invoice, cards, reason)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": invoice}))
		self.assertFalse(frappe.db.get_value(CARD, cards[0], "sales_invoice"))

	def test_accounts_manager_can_link(self):
		invoice, cards, reason = self._args()
		user = _user(["Accounts Manager"])
		log = self._as(user, link_customer_invoice, invoice, cards, reason)
		self.assertEqual(frappe.db.get_value(LOG, log, ["origin", "owner"]), ("Linked", user))
		self.assertIn(user, frappe.db.get_value(LOG, log, "remarks"))

	def test_system_manager_passes_the_role_gate(self):
		invoice, cards, reason = self._args()
		# Accounts User gives the submit right on Sales Invoice; it is refused without System Manager (test above)
		log = self._as(
			_user(["System Manager", "Accounts User"]), link_customer_invoice, invoice, cards, reason
		)
		self.assertEqual(frappe.db.get_value(LOG, log, "origin"), "Linked")

	def test_accounts_manager_of_another_company_is_refused(self):
		invoice, cards, reason = self._args()
		user = _user(["Accounts Manager", "Card Manager"], restrict_to=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			self._as(user, link_customer_invoice, invoice, cards, reason)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": invoice}))

	def test_candidates_roles_and_company_scope(self):
		self._args()
		for roles in (["Card Manager"], ["Accounts User", "Card Manager"]):
			with self.subTest(roles=roles), self.assertRaises(frappe.PermissionError):
				self._as(_user(roles), unlinked_customer_invoice_candidates, self.company)
		other = _user(["Accounts Manager"], restrict_to=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			self._as(other, unlinked_customer_invoice_candidates, self.company)
		result = self._as(_user(["Accounts Manager"]), unlinked_customer_invoice_candidates, self.company)
		self.assertTrue(result["invoices"])


class TestLinkedInvoiceInReports(_LinkBase):
	def _statement(self):
		from card.card.report.equipment_customer_statement.equipment_customer_statement import execute

		summary = execute(frappe._dict(company=self.company, customer=self.customer, **SEPTEMBER))[4]
		return {s["key"]: flt(s["value"], 2) for s in summary if s.get("key")}

	def _summary_row(self):
		from card.card.report.equipment_customers_summary.equipment_customers_summary import execute

		rows = execute(frappe._dict(company=self.company, **SEPTEMBER))[1]
		return next(r for r in rows if r.get("customer") == self.customer)

	def test_customer_statement_before_and_after_the_link(self):
		card = self._out_card()
		si = self._si(1600, vat=True)  # net 1,600, gross 1,840
		before = self._statement()
		self.assertEqual(
			(before["net_cards"], before["invoiced"], before["not_invoiced"], before["outside"]),
			(1600.0, 0.0, 1600.0, 1600.0),
		)
		self.assertEqual(before["closing"], 1840.0)

		self._link(si, card)

		after = self._statement()
		self.assertEqual(
			(after["net_cards"], after["invoiced"], after["not_invoiced"], after["outside"]),
			(1600.0, 1600.0, 0.0, 0.0),
		)
		for key in ("closing", "opening", "received", "invoiced_entries"):
			self.assertEqual(after[key], before[key], key)

	def test_another_hand_booked_invoice_stays_outside_card(self):
		card = self._out_card()
		si = self._si(1600)
		self._si(500)
		self._link(si, card)
		after = self._statement()
		self.assertEqual((after["invoiced"], after["not_invoiced"], after["outside"]), (1600.0, 0.0, 500.0))

	def test_customers_summary_before_and_after_the_link(self):
		card = self._out_card()
		si = self._si(1600)
		before = self._summary_row()
		self.assertEqual((before["invoiced_net"], before["diff"], before["external_net"]), (0, 1600, 1600))
		self._link(si, card)
		after = self._summary_row()
		self.assertEqual((after["invoiced_net"], after["diff"], after["external_net"]), (1600, 0, 0))
		self.assertEqual(after["closing"], before["closing"])

	def test_linked_card_is_not_unbilled_and_not_an_integrity_fault(self):
		from card.card.report.posting_source_integrity.posting_source_integrity import execute as integrity
		from card.card.report.unbilled_card_work.unbilled_card_work import execute as unbilled

		period = {"company": self.company, "from_date": "2026-09-01", "to_date": "2026-09-30"}

		def unbilled_cards():
			data = unbilled({**period, "project": self.project, "side": "Customer"})[1]
			return {r["card"] for r in data}

		card = self._out_card()
		si = self._si(1600)
		self.assertIn(card.name, unbilled_cards())
		self._link(si, card)
		self.assertNotIn(card.name, unbilled_cards())
		rows = [r for r in integrity({**period, "show": "All"})[1] if r["source"] == card.name]
		self.assertEqual(len(rows), 1, rows)
		self.assertFalse(rows[0]["problem"], rows[0]["check"])
		self.assertEqual(rows[0]["sales_invoice"], si.name)


class TestUnlinkedCustomerInvoiceCandidates(_LinkBase):
	def _rows(self, **kw):
		result = unlinked_customer_invoice_candidates(self.company, **kw)
		return {r["invoice"]: r for r in result["invoices"]}, result

	def test_exact_match_on_the_cards_of_the_invoice_month(self):
		card = self._out_card()
		si = self._si(1600, vat=True)
		rows, _result = self._rows()
		row = rows[si.name]
		self.assertEqual(row["match"], "exact")
		self.assertEqual((row["customer"], row["projects"]), (self.customer, [self.project]))
		self.assertEqual(flt(row["net_total"], 2), 1600.0)
		self.assertEqual(str(row["posting_date"]), "2026-09-30")
		self.assertEqual(
			[(c["name"], c["month"], int(c["year"]), flt(c["customer_net_amount"], 2)) for c in row["cards"]],
			[(card.name, "09", 2026, 1600.0)],
		)
		self.assertTrue(row["note"])

	def test_exact_match_on_all_unlinked_cards_of_the_project(self):
		card = self._out_card()
		si = self._si(1600, posting_date="2026-12-31")  # the card month is outside December and November
		row = self._rows()[0][si.name]
		self.assertEqual(row["match"], "exact")
		self.assertEqual([c["name"] for c in row["cards"]], [card.name])

	def test_no_match_lists_the_unlinked_cards_of_the_project(self):
		card = self._out_card()
		self._out_card(project=self._second_project())
		si = self._si(999)
		row = self._rows()[0][si.name]
		self.assertEqual(row["match"], "none")
		self.assertEqual([c["name"] for c in row["cards"]], [card.name])
		self.assertTrue(row["note"])

	def test_invoice_without_a_project_never_matches(self):
		self._out_card()
		si = self._si(1600, line_project=None)
		row = self._rows()[0][si.name]
		self.assertEqual((row["match"], row["projects"], row["cards"]), ("none", [], []))
		self.assertTrue(row["note"])

	def test_only_hand_booked_submitted_normal_invoices_are_listed(self):
		card = self._out_card()
		draft = self._si(1600, submit=False)
		returned = self._si(1600)
		frappe.db.set_value(SI, returned.name, "is_return", 1, update_modified=False)
		opening = self._si(1600)
		frappe.db.set_value(SI, opening.name, "is_opening", "Yes", update_modified=False)
		linked = self._si(1600)
		self._link(linked, card)
		open_one = self._si(700)
		rows, _result = self._rows()
		for inv in (draft, returned, opening, linked):
			self.assertNotIn(inv.name, rows)
		# the linked card is no longer a candidate of another invoice
		self.assertEqual(rows[open_one.name]["cards"], [])

	def test_customer_without_customer_billing_cards_is_not_listed(self):
		self._out_card()
		stranger = self._si(1600, customer=self._customer("-B"))
		self.assertNotIn(stranger.name, self._rows()[0])

	def test_paging(self):
		self._out_card()
		first, second = self._si(100, posting_date="2026-09-29"), self._si(200, posting_date="2026-09-30")
		mine = {first.name, second.name}
		seen, start = [], 0
		while True:
			_rows, result = self._rows(limit_start=start, limit_page_length=1)
			self.assertLessEqual(len(result["invoices"]), 1)
			seen += [r["invoice"] for r in result["invoices"]]
			if not result["has_more"]:
				break
			start += 1
			self.assertLess(start, 500, "paging does not end")
		self.assertTrue(mine <= set(seen))
		self.assertEqual(len(seen), len(set(seen)))
		# newest first
		self.assertLess(seen.index(second.name), seen.index(first.name))

	def test_the_list_writes_nothing(self):
		card = self._out_card()
		self._si(1600)
		writes = frappe.db.transaction_writes
		counts = (frappe.db.count(LOG), frappe.db.count("Comment"), frappe.db.count("Version"))
		modified = frappe.db.get_value(CARD, card.name, "modified")
		self._rows()
		self.assertEqual(frappe.db.transaction_writes, writes)
		self.assertEqual(
			(frappe.db.count(LOG), frappe.db.count("Comment"), frappe.db.count("Version")), counts
		)
		self.assertEqual(frappe.db.get_value(CARD, card.name, "modified"), modified)
