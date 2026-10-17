# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""card.gl.events._block_amended_copy after a reused invoice number
(2026-10-17). Frappe reverts the naming series when the last draft is deleted,
so a manual invoice can take the number of a deleted Card draft whose log stays
behind as Cancelled. Such a manual invoice must stay amendable, while an
amendment of a real Card posting — directly or further up the amendment chain —
stays refused, and missing or equal timestamps refuse (fail-closed)."""

import frappe

from card.gl import events
from card.gl.posting import build_monthly_posting
from card.tests.test_posting_lines import _ReconciliationBase

REFUSED = "amends CARD posting"


class TestAmendedCopyAfterNameReuse(_ReconciliationBase):
	def _amend(self, invoice):
		amended = frappe.copy_doc(invoice)
		amended.amended_from = invoice.name
		amended.docstatus = 0
		if amended.doctype == "Purchase Invoice":
			amended.bill_no = (invoice.bill_no or "TEST") + "-A"
		return amended

	def _assert_refused(self, invoice):
		with self.assertRaisesRegex(frappe.ValidationError, REFUSED):
			self._amend(invoice).insert(ignore_permissions=True)
		self.assertFalse(frappe.db.exists(invoice.doctype, {"amended_from": invoice.name}))

	def _deleted_supplier_draft(self):
		draft = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.delete_doc("Purchase Invoice", draft, ignore_permissions=True)
		return draft

	def _submitted_supplier_posting(self):
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-AMEND-" + frappe.generate_hash(length=6)
		pi.bill_date = pi.posting_date
		pi.submit()
		return pi

	def _customer_card(self):
		eq = self._rented_out(customer_rate=1000)
		self._card(eq, [8, 8], submit=True)

	# ---- legitimate manual amendments stay possible ----

	def test_manual_invoice_reusing_a_deleted_card_draft_name_can_be_amended(self):  # P1
		self._vat_supplier()
		self._example_card()
		draft = self._deleted_supplier_draft()
		self.assertEqual(frappe.db.get_value("GL Posting Log", {"posting_doc": draft}, "status"), "Cancelled")
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		self.assertEqual(manual.name, draft)  # the number is reused
		manual.cancel()
		amended = self._amend(manual)
		amended.insert(ignore_permissions=True)
		self.assertEqual(amended.amended_from, manual.name)

	def test_sales_invoice_reusing_a_deleted_card_draft_name_can_be_amended(self):  # P2
		self._customer_card()
		draft = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		frappe.delete_doc("Sales Invoice", draft, ignore_permissions=True)
		manual = self._manual_invoice("Sales Invoice", "2026-09-20", 500)
		self.assertEqual(manual.name, draft)
		manual.cancel()
		amended = self._amend(manual)
		amended.insert(ignore_permissions=True)
		self.assertEqual(amended.amended_from, manual.name)

	def test_number_reused_by_two_deleted_card_drafts_then_a_manual_invoice(self):  # P3
		self._vat_supplier()
		self._example_card()
		first = self._deleted_supplier_draft()
		self.assertEqual(self._deleted_supplier_draft(), first)
		self.assertEqual(frappe.db.count("GL Posting Log", {"posting_doc": first}), 2)
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		self.assertEqual(manual.name, first)
		manual.cancel()
		self._amend(manual).insert(ignore_permissions=True)

	def test_manual_invoice_without_card_history_can_be_amended(self):  # P4
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 300)
		self.assertFalse(frappe.db.exists("GL Posting Log", {"posting_doc": manual.name}))
		manual.cancel()
		self._amend(manual).insert(ignore_permissions=True)

	def test_amendment_of_a_manual_amendment_can_be_amended_again(self):  # P5
		self._vat_supplier()
		self._example_card()
		self._deleted_supplier_draft()
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		manual.cancel()
		first = self._amend(manual)
		first.insert(ignore_permissions=True)
		first.submit()
		first.cancel()
		second = self._amend(first)
		second.insert(ignore_permissions=True)
		self.assertEqual(second.amended_from, first.name)

	# ---- Card postings stay protected ----

	def test_amending_a_cancelled_card_posting_is_still_refused(self):  # N1
		self._vat_supplier()
		self._example_card()
		pi = self._submitted_supplier_posting()
		pi.cancel()
		self._assert_refused(pi)

	def test_amending_a_cancelled_card_sales_posting_is_refused(self):  # N2
		self._customer_card()
		si = frappe.get_doc(
			"Sales Invoice", build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		)
		si.submit()
		si.cancel()
		self._assert_refused(si)

	def test_card_posting_that_reused_a_deleted_card_draft_name_stays_protected(self):  # N3
		self._vat_supplier()
		self._example_card()
		draft = self._deleted_supplier_draft()
		pi = self._submitted_supplier_posting()
		self.assertEqual(pi.name, draft)  # the older, Cancelled log must not hide the live one
		self.assertEqual(frappe.db.count("GL Posting Log", {"posting_doc": pi.name}), 2)
		pi.cancel()
		self._assert_refused(pi)

	def test_equal_timestamps_refuse(self):  # N4
		self._vat_supplier()
		self._example_card()
		draft = self._deleted_supplier_draft()
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		self.assertEqual(manual.name, draft)
		log = frappe.db.get_value("GL Posting Log", {"posting_doc": draft}, "name")
		frappe.db.set_value("GL Posting Log", log, "creation", manual.creation, update_modified=False)
		manual.cancel()
		self._assert_refused(manual)

	def test_missing_amended_invoice_with_a_card_log_refuses(self):  # N5
		self._vat_supplier()
		self._example_card()
		draft = self._deleted_supplier_draft()  # the log stays, the invoice is gone
		self.assertFalse(frappe.db.exists("Purchase Invoice", draft))
		doc = frappe.new_doc("Purchase Invoice")
		doc.amended_from = draft
		with self.assertRaisesRegex(frappe.ValidationError, REFUSED):
			events._block_amended_copy(doc)

	def test_amendment_chain_rooted_in_a_card_posting_stays_protected(self):  # N6
		self._vat_supplier()
		self._example_card()
		pi = self._submitted_supplier_posting()
		pi.cancel()
		# an amendment that predates the guard (legacy data) — only the chain
		# links it to the Card posting
		legacy = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		frappe.db.set_value("Purchase Invoice", legacy.name, "amended_from", pi.name, update_modified=False)
		legacy.reload()
		legacy.cancel()
		with self.assertRaisesRegex(frappe.ValidationError, REFUSED + " " + pi.name):
			self._amend(legacy).insert(ignore_permissions=True)
