# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Issue 340: locking follow-ups of the invoice links and of the monthly build.

One test connection cannot run two transactions. A value that another transaction committed after this one
took its snapshot is simulated: the database holds the new value, and the plain read (``frappe.get_doc`` or
``frappe.db.get_value`` without ``for_update``) is patched to answer the old one. A locking read is never
patched: it is the read that sees the committed value. All data is synthetic and rolled back."""

import ast
import inspect
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase
from frappe.utils import flt

from card.gl.integrity import (
	link_supplier_invoice,
	unlink_customer_invoice,
	unlinked_customer_invoice_candidates,
)
from card.gl.posting import build_monthly_posting
from card.tests.test_link_customer_invoice import CARD, LOG, SI, _LinkBase
from card.tests.test_p0_posting_integrity import _P0Base

PI = "Purchase Invoice"
SOURCE = "GL Posting Source"


def _snapshot(doctype, rows=None, **values):
	"""``frappe.get_doc`` that answers a plain read of ``doctype`` with old values (``rows``: old values of
	every row of its ``items``), as the snapshot of a transaction that started earlier would. A read with
	``for_update`` gets the real document."""
	real = frappe.get_doc

	def get_doc(*args, **kwargs):
		doc = real(*args, **kwargs)
		if len(args) > 1 and args[0] == doctype and not kwargs.get("for_update"):
			doc.update(values)
			for row in (doc.get("items") or []) if rows else []:
				row.update(rows)
		return doc

	return patch.object(frappe, "get_doc", side_effect=get_doc)


def _no_plain_log_read():
	"""``frappe.db.get_value`` whose plain read of GL Posting Log finds nothing: the log was committed after
	the snapshot. A locking read is answered by the database."""
	real = frappe.db.get_value

	def get_value(doctype, *args, **kwargs):
		if doctype == LOG and not kwargs.get("for_update"):
			return None
		return real(doctype, *args, **kwargs)

	return patch.object(frappe.db, "get_value", side_effect=get_value)


def _locking_reads():
	"""(patch, calls): records (doctype, filters) of every ``frappe.db.get_value`` with ``for_update``."""
	real, calls = frappe.db.get_value, []

	def get_value(doctype, filters=None, *args, **kwargs):
		if kwargs.get("for_update"):
			calls.append((doctype, filters))
		return real(doctype, filters, *args, **kwargs)

	return patch.object(frappe.db, "get_value", side_effect=get_value), calls


class TestCustomerLinkLockOrder(_LinkBase):
	"""Item 1: the log of the invoice is locked by its name; the order is invoice, cards, logs."""

	def test_link_takes_no_locking_read_filtered_on_posting_doc(self):
		card = self._out_card()
		si = self._si(1600)
		spy, calls = _locking_reads()
		with spy:
			self._link(si, card)
		wide = [f for doctype, f in calls if doctype == LOG and isinstance(f, dict) and "posting_doc" in f]
		self.assertEqual(wide, [], "a locking read on posting_doc (no index) locks rows of other postings")

	def test_log_of_the_invoice_is_locked_by_its_name_and_refuses_a_second_link(self):
		card = self._out_card()
		other = self._out_card(hours=(8,), customer_rate=500)
		si = self._si(1600)
		log = self._link(si, card)
		spy, calls = _locking_reads()
		with spy, self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting or linked"):
			self._link(si, other)
		self.assertIn((LOG, log), calls, "the log found by the plain read is locked by its name")

	def test_link_committed_after_the_snapshot_is_seen_by_its_posting_key(self):
		from card.card.doctype.gl_posting_log.gl_posting_log import linked_posting_key

		card = self._out_card()
		other = self._out_card(hours=(8,), customer_rate=500)
		si = self._si(1600)
		log = frappe.db.get_value(
			LOG,
			self._link(si, card),
			["name", "posting_key", "company", "party_type", "party", "month", "year", "posting_doc"],
			as_dict=True,
		)
		# the key the link reads is the key the log controller writes
		self.assertEqual(
			log.posting_key,
			linked_posting_key(log.company, log.party_type, log.party, log.month, log.year, log.posting_doc),
		)
		with _no_plain_log_read(), self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting"):
			self._link(si, other)
		self.assertEqual(frappe.db.count(LOG, {"posting_doc": si.name}), 1)

	def test_unlink_locks_the_cards_before_the_log(self):
		card = self._out_card()
		si = self._si(1600)
		log = self._link(si, card)
		real_value, real_doc, order = frappe.db.get_value, frappe.get_doc, []

		def get_value(doctype, *args, **kwargs):
			if kwargs.get("for_update"):
				order.append(doctype)
			return real_value(doctype, *args, **kwargs)

		def get_doc(*args, **kwargs):
			if kwargs.get("for_update"):
				order.append(args[0])
			return real_doc(*args, **kwargs)

		with (
			patch.object(frappe.db, "get_value", side_effect=get_value),
			patch.object(frappe, "get_doc", side_effect=get_doc),
		):
			self.assertEqual(unlink_customer_invoice(si.name, "The invoice bills other cards"), log)
		self.assertEqual(order[0], SI)
		self.assertLess(order.index(CARD), order.index(LOG), "order: invoice, cards, log")


class TestCustomerLinkAmountsUnderLock(_LinkBase):
	"""Item 2: the amounts that are compared are read again under the locks."""

	def test_card_amount_changed_meanwhile_is_compared_under_the_lock(self):
		card = self._out_card()
		si = self._si(1600)
		frappe.db.set_value(CARD, card.name, "customer_net_amount", 1000, update_modified=False)
		with _snapshot(CARD, customer_net_amount=1600):
			self._refused("the cards total 1000", si, card)

	def test_card_project_changed_meanwhile_is_compared_under_the_lock(self):
		card = self._out_card()
		si = self._si(1600)
		frappe.db.set_value(CARD, card.name, "project", self._second_project(), update_modified=False)
		with _snapshot(CARD, project=self.project):
			self._refused("which is not a project of " + si.name, si, card)

	def test_invoice_net_changed_meanwhile_is_compared_under_the_lock(self):
		card = self._out_card()
		si = self._si(1600)
		frappe.db.set_value(SI, si.name, "base_net_total", 1500, update_modified=False)
		with _snapshot(SI, base_net_total=1600):
			self._refused("is net 1500", si, card)

	def test_invoice_lines_changed_meanwhile_are_compared_under_the_lock(self):
		card = self._out_card()
		si = self._si(1600)
		frappe.db.set_value(
			"Sales Invoice Item", {"parent": si.name}, "base_net_amount", 1500, update_modified=False
		)
		with _snapshot(SI, rows={"base_net_amount": 1600}):
			self._refused("for project " + self.project, si, card)


class TestBuildHeldCheckUnderLock(_LinkBase):
	"""Item 3: the build checks the holder of each source with a locking read, after it locked the source."""

	def test_build_refuses_a_card_linked_after_its_snapshot(self):
		customer_b = self._customer("-B")
		card = self._out_card(customer=customer_b)
		si = self._si(1600, customer=customer_b)
		log = self._link(si, card)
		# the snapshot of a build that waited on the card row for that link: the card has no invoice link
		# and no source row of the link is visible
		frappe.db.set_value(CARD, card.name, {"sales_invoice": None, "posted": 0}, update_modified=False)
		real = frappe.get_all

		def get_all(doctype, *args, **kwargs):
			return [] if doctype == SOURCE else real(doctype, *args, **kwargs)

		with (
			patch.object(frappe, "get_all", side_effect=get_all),
			self.assertRaisesRegex(frappe.ValidationError, "was just reserved by another posting"),
		):
			build_monthly_posting(self.company, "Customer", customer_b, 9, 2026)
		active = {"party": customer_b, "status": ["in", ["Draft", "Submitted"]]}
		self.assertEqual(
			frappe.get_all(LOG, filters=active, pluck="name"),
			[log],
			"the build left a draft posting with a linked card",
		)


class TestCandidatesQuery(_LinkBase):
	"""Item 4: the candidates leave out another currency, and the query carries no list of names."""

	def _rows(self):
		result = unlinked_customer_invoice_candidates(self.company)
		return {r["invoice"]: r for r in result["invoices"]}

	def test_invoice_in_another_currency_is_not_listed(self):
		self._out_card()
		si = self._si(1600)
		self.assertIn(si.name, self._rows())
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		other = "USD" if company_currency != "USD" else "EUR"
		frappe.db.set_value(SI, si.name, "currency", other, update_modified=False)
		self.assertNotIn(si.name, self._rows(), "the link refuses this invoice; it is not a candidate")

	def test_the_query_carries_no_list_of_logged_invoices(self):
		card = self._out_card()
		linked = self._si(1600)
		self._link(linked, card)
		opening = self._si(1600)
		frappe.db.set_value(SI, opening.name, "is_opening", "Yes", update_modified=False)
		open_one = self._si(700)
		with patch.object(frappe, "get_list", wraps=frappe.get_list) as get_list:
			rows = self._rows()
		self.assertIn(open_one.name, rows)
		self.assertNotIn(linked.name, rows)
		self.assertNotIn(opening.name, rows)
		reads = [call for call in get_list.call_args_list if call.args and call.args[0] == SI]
		self.assertTrue(reads)
		for call in reads:
			for condition in call.kwargs.get("filters") or []:
				self.assertNotEqual(condition[1], "not in", "a list that grows with every logged invoice")

	def test_paging_counts_the_candidates_only(self):
		card = self._out_card()
		linked = self._si(1600, posting_date="2026-09-30")
		self._link(linked, card)
		older = self._si(700, posting_date="2026-09-28")
		newer = self._si(800, posting_date="2026-09-29")
		first = unlinked_customer_invoice_candidates(self.company, limit_start=0, limit_page_length=1)
		second = unlinked_customer_invoice_candidates(self.company, limit_start=1, limit_page_length=1)
		self.assertEqual(([r["invoice"] for r in first["invoices"]], first["has_more"]), ([newer.name], True))
		self.assertEqual([r["invoice"] for r in second["invoices"]], [older.name])


class TestSupplierLinkLocking(_P0Base):
	"""Item 5: the supplier link reads under the locks, as the customer link."""

	def _link(self, invoice, *sources, **kw):
		return link_supplier_invoice(invoice.name, [{"doctype": CARD, "name": s} for s in sources], **kw)

	def test_source_invoiced_meanwhile_is_refused_by_the_locked_read(self):
		card = self._rental_card()  # 600 net
		other = self._manual_pi(50)
		manual = self._manual_pi(600)
		frappe.db.set_value(
			CARD, card.name, {"purchase_invoice": other.name, "posted": 1}, update_modified=False
		)
		with (
			_snapshot(CARD, purchase_invoice=None, posted=0),
			self.assertRaisesRegex(frappe.ValidationError, "already invoiced by " + other.name),
		):
			self._link(manual, card.name)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": manual.name}))

	def test_source_amount_changed_meanwhile_is_compared_under_the_lock(self):
		card = self._rental_card()
		manual = self._manual_pi(600)
		frappe.db.set_value(CARD, card.name, "net_amount", 500, update_modified=False)
		with (
			_snapshot(CARD, net_amount=600),
			self.assertRaisesRegex(frappe.ValidationError, "the CARD sources total 500"),
		):
			self._link(manual, card.name)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": manual.name}))

	def test_invoice_cancelled_or_changed_meanwhile_is_read_under_the_lock(self):
		card = self._rental_card()
		manual = self._manual_pi(600, submit=False)
		frappe.db.set_value(PI, manual.name, "net_total", 700, update_modified=False)
		with (
			_snapshot(PI, net_total=600),
			self.assertRaisesRegex(frappe.ValidationError, manual.name + " is net 700"),
		):
			self._link(manual, card.name)
		frappe.db.set_value(PI, manual.name, {"net_total": 600, "docstatus": 2}, update_modified=False)
		with (
			_snapshot(PI, docstatus=0),
			self.assertRaisesRegex(frappe.ValidationError, "is cancelled or a return"),
		):
			self._link(manual, card.name)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": manual.name}))

	def test_source_held_meanwhile_is_refused_without_the_snapshot_holder_check(self):
		card = self._rental_card()
		draft = self._build()
		manual = self._manual_pi(600, submit=False)
		with (
			patch("card.gl.events.active_log_holding", return_value=None),
			self.assertRaisesRegex(frappe.ValidationError, "already held by " + draft.name),
		):
			self._link(manual, card.name)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": manual.name}))

	def test_invoice_linked_after_the_snapshot_is_seen_by_its_posting_key(self):
		first = self._rental_card()
		second = self._rental_card()
		manual = self._manual_pi(600)
		self._link(manual, first.name)
		with _no_plain_log_read(), self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting"):
			self._link(manual, second.name)
		self.assertEqual(frappe.db.count(LOG, {"posting_doc": manual.name}), 1)
		self.assertFalse(frappe.db.get_value(CARD, second.name, "purchase_invoice"))

	def test_one_source_under_two_spellings_is_listed_twice(self):
		# the database compares names without case and without trailing spaces: one row, two request entries
		card = self._rental_card()
		manual = self._manual_pi(1200)
		for other in (card.name.lower(), card.name + " "):
			with self.assertRaisesRegex(frappe.ValidationError, "listed twice"):
				self._link(manual, card.name, other)
		self.assertFalse(frappe.db.exists(LOG, {"posting_doc": manual.name}))

	def test_log_holds_the_stored_source_name(self):
		card = self._rental_card()
		manual = self._manual_pi(600)
		log = self._link(manual, card.name.lower())
		self.assertEqual(frappe.get_all(SOURCE, filters={"parent": log}, pluck="source_name"), [card.name])

	def test_card_linked_to_a_much_later_invoice_counts_in_its_own_month(self):
		from card.reconciliation import cards_invoiced

		# a card of 12/2024: a new card of a past fiscal year is refused, so an existing one is simulated by
		# moving a card of this year to that month directly in the database
		card = self._rental_card()
		frappe.db.set_value(
			CARD,
			card.name,
			{"month": "12", "year": 2024, "from_date": "2024-12-01", "to_date": "2024-12-31"},
			update_modified=False,
		)
		manual = self._manual_pi(600)  # dated 2026-09-20
		log = frappe.get_doc(LOG, self._link(manual, card.name))
		self.assertEqual((log.origin, log.month, int(log.year)), ("Linked", "09", 2026))

		december = cards_invoiced("Supplier", [self.supplier], self.company, "2024-12-01", "2024-12-31")
		self.assertEqual(flt(december.get(self.supplier), 2), 600.0)
		september = cards_invoiced("Supplier", [self.supplier], self.company, "2026-09-01", "2026-09-30")
		self.assertFalse(september.get(self.supplier))


class TestReportAccessImport(UnitTestCase):
	"""Item 6: ``import frappe`` does not load ``frappe.permissions``; a console run without a request fails
	with AttributeError unless the module imports it. The attribute exists in a test run (other modules
	imported it), so the import statement itself is checked."""

	def test_report_access_imports_frappe_permissions(self):
		import card.report_access

		tree = ast.parse(inspect.getsource(card.report_access))
		imported = {alias.name for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
		self.assertIn("frappe.permissions", imported)
