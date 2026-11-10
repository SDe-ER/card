# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-136 (risk R-25, #54): the read-only "Posting Source Integrity" report finds sources whose invoice link,
posted flag and GL Posting Log disagree, and changes nothing."""

import frappe

from card.card.report.posting_source_integrity.posting_source_integrity import execute
from card.gl.posting import build_monthly_posting
from card.tests.test_s3_posting import _PostingBase

PERIOD = {"from_date": "2026-09-01", "to_date": "2026-09-30"}


class TestPostingSourceIntegrity(_PostingBase):
	def _run(self, show="Problems", **extra):
		return execute({"company": self.company, "show": show, **PERIOD, **extra})

	def _posted_card(self):
		self._vat_supplier()
		card = self._card(self._equipment(), [8, 8], submit=True)
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-PSI-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		return card, pi

	def _row(self, rows, name):
		mine = [r for r in rows if r["source"] == name]
		self.assertEqual(len(mine), 1, rows)
		return mine[0]

	def _snapshot(self, card):
		return (
			frappe.db.get_value(
				"Card Monthly Card",
				card.name,
				["purchase_invoice", "posted", "gl_posting", "modified"],
				as_dict=True,
			),
			frappe.db.count("GL Posting Log"),
			frappe.db.count("Version"),
		)

	def test_consistent_posting_is_not_a_problem(self):
		card, pi = self._posted_card()
		before = self._snapshot(card)
		_columns, rows, message, _chart, summary = self._run()
		self.assertFalse([r for r in rows if r["source"] == card.name])
		row = self._row(self._run("All")[1], card.name)
		self.assertFalse(row["problem"])
		self.assertEqual(row["purchase_invoice"], pi.name)
		self.assertEqual(row["log_status"], frappe._("Submitted"))
		self.assertTrue(message)
		self.assertEqual(summary[1]["value"], len(rows))
		self.assertEqual(self._snapshot(card), before, "the report wrote something")

	def test_cleared_invoice_link_is_listed(self):
		card, pi = self._posted_card()
		frappe.db.set_value("Card Monthly Card", card.name, "purchase_invoice", "", update_modified=False)
		row = self._row(self._run()[1], card.name)
		self.assertTrue(row["problem"])
		self.assertIn(pi.name, row["check"])
		self.assertIn(frappe._("Purchase Invoice"), row["check"])

	def test_link_to_another_invoice_is_listed(self):
		card, pi = self._posted_card()
		frappe.db.set_value(
			"Card Monthly Card", card.name, "purchase_invoice", "ACC-PINV-NOPE", update_modified=False
		)
		row = self._row(self._run()[1], card.name)
		self.assertTrue(row["problem"])
		self.assertIn("ACC-PINV-NOPE", row["check"])
		self.assertIn(pi.name, row["check"])  # the invoice the log posted it on

	def test_posted_flag_out_of_step_is_listed(self):
		card, _pi = self._posted_card()
		frappe.db.set_value("Card Monthly Card", card.name, "posted", 0, update_modified=False)
		self.assertTrue(self._row(self._run()[1], card.name)["problem"])
		lonely = self._card(self._equipment(), [3], submit=True)
		frappe.db.set_value("Card Monthly Card", lonely.name, "posted", 1, update_modified=False)
		row = self._row(self._run()[1], lonely.name)
		self.assertTrue(row["problem"])
		self.assertFalse(row["posting_log"])

	def test_link_without_any_log_is_listed(self):
		card = self._card(self._equipment(), [3], submit=True)
		frappe.db.set_value(
			"Card Monthly Card",
			card.name,
			{"purchase_invoice": "ACC-PINV-HAND", "posted": 1},
			update_modified=False,
		)
		row = self._row(self._run()[1], card.name)
		self.assertTrue(row["problem"])
		self.assertIn("ACC-PINV-HAND", row["check"])

	def test_unposted_source_is_not_listed(self):
		card = self._card(self._equipment(), [3], submit=True)
		self.assertFalse([r for r in self._run("All")[1] if r["source"] == card.name])

	def test_report_is_read_only_for_its_roles(self):
		report = frappe.get_doc("Report", "Posting Source Integrity")
		self.assertEqual(report.report_type, "Script Report")
		self.assertEqual(sorted(r.role for r in report.roles), ["Accounts Manager", "System Manager"])
		user = "test-psi-" + self.token + "@example.com"
		frappe.get_doc(
			{"doctype": "User", "email": user, "first_name": "PSI", "roles": [{"role": "Card User"}]}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				self._run()
		finally:
			frappe.set_user("Administrator")

	def test_period_is_required(self):
		with self.assertRaises(frappe.ValidationError):
			execute({"company": self.company})
		with self.assertRaises(frappe.ValidationError):
			execute({"company": self.company, "from_date": "2026-09-30", "to_date": "2026-09-01"})
