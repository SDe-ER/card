# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""REPRODUCTION ONLY (not a fix) of the review finding on
card.gl.events._block_amended_copy (2026-10-17): it refuses an amendment
whenever ANY GL Posting Log carries the amended invoice's name. Frappe reverts
the naming series when the last draft is deleted, so a manual invoice can take
the number of a deleted Card draft whose log stays behind as Cancelled — and
that manual invoice can then never be amended.

The first test is EXPECTED TO FAIL until the Owner approves a fix. The second
pins the behaviour that must survive any fix: amending a real (submitted, then
cancelled) Card posting stays refused."""

import frappe

from card.gl.posting import build_monthly_posting
from card.tests.test_posting_lines import _ReconciliationBase


class TestAmendedCopyAfterNameReuse(_ReconciliationBase):
	def _amend(self, invoice):
		amended = frappe.copy_doc(invoice)
		amended.amended_from = invoice.name
		amended.docstatus = 0
		if amended.doctype == "Purchase Invoice":
			amended.bill_no = (invoice.bill_no or "TEST") + "-A"
		return amended

	def test_manual_invoice_reusing_a_deleted_card_draft_name_can_be_amended(self):
		self._vat_supplier()
		self._example_card()
		draft = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.delete_doc("Purchase Invoice", draft, ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("GL Posting Log", {"posting_doc": draft}, "status"), "Cancelled")
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		self.assertEqual(manual.name, draft)  # the number is reused
		manual.cancel()
		amended = self._amend(manual)
		amended.insert(ignore_permissions=True)  # refused today: "amends CARD posting"
		self.assertEqual(amended.amended_from, manual.name)

	def test_amending_a_cancelled_card_posting_is_still_refused(self):
		self._vat_supplier()
		self._example_card()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-AMEND-" + frappe.generate_hash(length=6)
		pi.bill_date = pi.posting_date
		pi.submit()
		pi.cancel()
		with self.assertRaisesRegex(frappe.ValidationError, "amends CARD posting"):
			self._amend(pi).insert(ignore_permissions=True)
