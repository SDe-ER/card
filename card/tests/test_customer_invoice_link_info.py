# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-194 / FR-195: ``card.gl.integrity.customer_invoice_link_info``, the read-only data of the Desk buttons
"Link to monthly cards" and "Remove link to monthly cards" on a submitted Sales Invoice. It has the gates of the
candidates list and writes nothing. All data is synthetic and rolled back."""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from card.gl.integrity import customer_invoice_link_info
from card.open_month import STATE_OPEN_MONTH
from card.tests.test_link_customer_invoice import CARD, LOG, SI, _LinkBase
from card.tests.test_p0_posting_integrity import _user


class TestCustomerInvoiceLinkInfo(_LinkBase):
	def test_it_is_a_get_only_method(self):
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[customer_invoice_link_info], ["GET"]
		)

	def test_unlinked_invoice_returns_its_candidate_cards(self):
		card = self._out_card()  # 1,600
		other_project = self._out_card(project=self._second_project())  # not a project of the invoice
		si = self._si(1600, vat=True)

		info = customer_invoice_link_info(si.name, 1)

		self.assertEqual((info["eligible"], info["linked"], info["log"]), (True, False, None))
		self.assertEqual(flt(info["net_total"], 2), 1600.0)
		self.assertEqual(info["linked_cards"], [])
		self.assertEqual(
			[
				(c["name"], c["month"], int(c["year"]), c["project"], flt(c["customer_net_amount"], 2))
				for c in info["cards"]
			],
			[(card.name, "09", 2026, self.project, 1600.0)],
		)
		self.assertNotIn(other_project.name, [c["name"] for c in info["cards"]])

	def test_the_card_list_is_read_only_when_asked_for(self):
		self._out_card()
		self._out_card(hours=(8,), customer_rate=500)
		si = self._si(2000)
		cheap = customer_invoice_link_info(si.name)
		self.assertEqual((cheap["eligible"], cheap["card_count"], cheap["cards"]), (True, 2, []))
		for flag in (1, "1"):
			self.assertEqual(len(customer_invoice_link_info(si.name, flag)["cards"]), 2)
		self.assertEqual(customer_invoice_link_info(si.name, 0)["cards"], [])

	def test_the_list_is_newest_first_and_capped_with_the_total(self):
		old = self._out_card()
		new = self._out_card(hours=(8,), customer_rate=500)
		frappe.db.set_value(CARD, new.name, "month", "10", update_modified=False)
		si = self._si(2000)
		with patch("card.gl.integrity.CANDIDATE_CARDS_MAX", 1):
			info = customer_invoice_link_info(si.name, 1)
		self.assertEqual([c["name"] for c in info["cards"]], [new.name])
		self.assertEqual((info["card_count"], info["more_cards"]), (2, True))
		info = customer_invoice_link_info(si.name, 1)
		self.assertEqual([c["name"] for c in info["cards"]], [new.name, old.name])
		self.assertFalse(info["more_cards"])

	def test_cards_already_held_or_open_are_not_offered(self):
		held = self._out_card()
		self._link(self._si(1600), held)
		open_card = self._out_card()
		frappe.db.set_value(CARD, open_card.name, "workflow_state", STATE_OPEN_MONTH, update_modified=False)
		si = self._si(500)
		info = customer_invoice_link_info(si.name, 1)
		self.assertEqual((info["cards"], info["card_count"]), ([], 0))

	def test_linked_invoice_returns_the_log_and_its_cards(self):
		card = self._out_card()
		si = self._si(1600)
		log = self._link(si, card)

		info = customer_invoice_link_info(si.name)

		self.assertEqual((info["linked"], info["log"], info["origin"]), (True, log, "Linked"))
		self.assertEqual(info["cards"], [])
		self.assertEqual(
			[(c["name"], flt(c["customer_net_amount"], 2)) for c in info["linked_cards"]],
			[(card.name, 1600.0)],
		)

	def test_a_built_posting_is_reported_with_its_origin(self):
		from card.gl.posting import build_monthly_posting

		self._out_card()
		built = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		info = customer_invoice_link_info(built)
		self.assertEqual((info["linked"], info["origin"]), (True, "Built"))

	def test_invoices_that_cannot_be_linked_are_not_eligible(self):
		self._out_card()
		draft = self._si(1600, submit=False)
		returned = self._si(1600)
		frappe.db.set_value(SI, returned.name, "is_return", 1, update_modified=False)
		for si in (draft, returned):
			with self.subTest(invoice=si.name):
				info = customer_invoice_link_info(si.name)
				self.assertEqual((info["eligible"], info["linked"], info["cards"]), (False, False, []))

	def test_roles_other_than_the_two_are_refused(self):
		si = self._si(1600)
		for roles in (["Card Manager"], ["Accounts User", "Card Manager"], ["Card User"]):
			with self.subTest(roles=roles), self.assertRaises(frappe.PermissionError):
				self._as(_user(roles), customer_invoice_link_info, si.name)
		for roles in (["Accounts Manager"], ["System Manager", "Accounts User"]):
			with self.subTest(roles=roles):
				self.assertTrue(self._as(_user(roles), customer_invoice_link_info, si.name)["eligible"])

	def test_company_scope_is_enforced(self):
		self._out_card()
		si = self._si(1600)
		user = _user(["Accounts Manager"], restrict_to=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			self._as(user, customer_invoice_link_info, si.name)

	def test_read_on_the_invoice_and_on_monthly_cards_is_required(self):
		si = self._si(1600)
		real = frappe.permissions.has_permission

		def deny(doctype, *args, **kwargs):
			if doctype == doctype_to_deny[0]:
				if kwargs.get("throw"):
					frappe.throw("denied", frappe.PermissionError)
				return False
			return real(doctype, *args, **kwargs)

		for doctype_to_deny in ([CARD], [SI]):
			with self.subTest(denied=doctype_to_deny[0]):
				with patch("frappe.has_permission", deny), patch("frappe.permissions.has_permission", deny):
					with self.assertRaises(frappe.PermissionError):
						customer_invoice_link_info(si.name)

	def test_it_writes_nothing(self):
		card = self._out_card()
		si = self._si(1600)
		linked = self._si(900)
		self._link(si, card)
		writes = frappe.db.transaction_writes
		counts = (frappe.db.count(LOG), frappe.db.count("Comment"), frappe.db.count("Version"))
		modified = frappe.db.get_value(CARD, card.name, "modified")
		customer_invoice_link_info(si.name, 1)
		customer_invoice_link_info(linked.name, 1)
		self.assertEqual(frappe.db.transaction_writes, writes)
		self.assertEqual(
			(frappe.db.count(LOG), frappe.db.count("Comment"), frappe.db.count("Version")), counts
		)
		self.assertEqual(frappe.db.get_value(CARD, card.name, "modified"), modified)
