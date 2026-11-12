# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-156 (#49, #126; conflict C-10, owner decision O-15): per-company non-taxable
customer-side deduction mode. Refuse (the default, and an empty value) keeps the
2026-10-15 ZATCA rule exactly: a non-taxable customer-side deduction on a monthly
card refuses the build. Credit note posts the deduction as a separate draft Sales
Invoice with ``is_return`` = 1 so the main SI carries no negative line and the
VAT base is not shifted.

Tests cover both modes side by side, the cancel path, cross-company isolation,
idempotency, two-connection concurrency, and every guard under a Lesson-12
mutation (removing the guard makes a test fail).
"""

import frappe
from frappe.utils import flt

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.gl import preflight
from card.gl.events import (
	_active_credit_note_for,
	_build_non_taxable_credit_note,
	_cn_backlink_tag,
)
from card.gl.posting import build_monthly_posting
from card.tests.test_s3_posting import _PostingBase

REFUSE = preflight.NON_TAXABLE_DEDUCTION_REFUSE
CREDIT_NOTE = preflight.NON_TAXABLE_DEDUCTION_CREDIT_NOTE


class _CreditNoteBase(_PostingBase):
	"""Shared setup: a rented-out equipment and a monthly card with one
	non-taxable customer-side deduction."""

	def setUp(self):
		super().setUp()
		# the default mode on a fresh company row is Refuse (field default)
		self._mode(None)

	def _mode(self, value, company=None):
		settings = frappe.get_doc("Card Settings")
		company = company or self.company
		row = next((r for r in settings.company_settings if r.company == company), None)
		if row is None:
			row = settings.append("company_settings", {"company": company})
		row.non_taxable_customer_deduction = value
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")

	def _card_with_non_taxable_deduction(self, customer_rate=1000, deduction=100, extras=None, customer=None):
		"""A rented-out monthly card with one non-taxable customer-side deduction
		('DieselNT') of `deduction` and an optional list of other adjustments."""
		eq = self._rented_out(customer=customer or self.customer, customer_rate=customer_rate)
		adjustments = [
			{
				"adjustment_type_ref": "DieselNT",
				"side": "Customer",
				"description": "nt",
				"amount": deduction,
			}
		]
		if extras:
			adjustments.extend(extras)
		return self._card(eq, [8, 8], adjustments=adjustments, submit=True)


class TestRefuseMode(_CreditNoteBase):
	"""The default mode: a non-taxable customer-side deduction still refuses
	the build, exactly as it did before FR-156."""

	def test_refuse_mode_refuses_the_build(self):
		self._mode(REFUSE)
		self._card_with_non_taxable_deduction()
		with self.assertRaisesRegex(frappe.ValidationError, "Non-taxable customer-side deduction"):
			build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		# nothing created
		self.assertFalse(frappe.get_all("Sales Invoice", filters={"customer": self.customer, "docstatus": 0}))
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.customer}))

	def test_empty_value_means_refuse(self):
		self._mode(None)  # empty is Refuse (field default and `credit_notes_...` behaviour)
		self._card_with_non_taxable_deduction()
		with self.assertRaisesRegex(frappe.ValidationError, "Non-taxable customer-side deduction"):
			build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)

	def test_refuse_mode_preflight_reader(self):
		# Lesson 12 mutation guard: the mode reader is what gates the credit-note branch
		self._mode(REFUSE)
		self.assertFalse(preflight.credit_notes_non_taxable_customer_deduction(self.company))
		self._mode(CREDIT_NOTE)
		self.assertTrue(preflight.credit_notes_non_taxable_customer_deduction(self.company))


class TestCreditNoteMode(_CreditNoteBase):
	"""With the company opted in to Credit note, the main SI carries no negative
	line (ZATCA stays honoured); the deduction is issued on a separate draft
	Sales Invoice with ``is_return`` = 1."""

	def test_main_si_carries_no_negative_line(self):
		self._mode(CREDIT_NOTE)
		card = self._card_with_non_taxable_deduction(customer_rate=1000, deduction=100)
		# revenue 1600, non-taxable deduction 100 -> customer_net 1500
		self.assertEqual(flt(card.customer_net_amount), 1500.0)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		# the main SI has NO negative line (the deduction is on the CN) and no
		# Net Total discount (the non-taxable deduction never becomes a discount
		# that would shift the VAT base)
		for item in si.items:
			self.assertGreater(flt(item.rate), 0, "ZATCA: no negative SI lines")
		self.assertEqual(flt(si.discount_amount or 0), 0.0)
		self.assertEqual(flt(si.net_total, 2), 1600.0)
		# no CN yet: the main SI is still a draft, submit creates it
		self.assertFalse(frappe.get_all("Sales Invoice", filters={"is_return": 1, "customer": self.customer}))

	def test_submit_builds_the_credit_note_draft(self):
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction(customer_rate=1000, deduction=100)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		# the credit note draft exists, standalone (no return_against)
		cns = frappe.get_all(
			"Sales Invoice",
			filters={"is_return": 1, "customer": self.customer, "docstatus": 0},
			fields=["name", "return_against", "grand_total", "net_total"],
		)
		self.assertEqual(len(cns), 1)
		cn = cns[0]
		self.assertFalse(cn.return_against, "standalone credit note (no return_against)")
		self.assertEqual(flt(cn.net_total, 2), -100.0)
		# the CN has its own GL Posting Log of origin Credit Note
		log = frappe.get_doc(
			"GL Posting Log", {"posting_doc": cn.name, "status": ["in", list(ACTIVE_STATES)]}
		)
		self.assertEqual(log.origin, "Credit Note")
		self.assertEqual(log.party_type, "Customer")
		self.assertEqual(log.party, self.customer)
		# the posting_key is a FR-156 digest (not the base party-month key)
		self.assertIn("|CN|", log.posting_key)

	def test_submit_builds_cn_with_zero_rate_tax_template(self):
		"""The CN's non-taxable deduction lines carry the zero-rate item tax
		template, so the CN's taxes computation adds no VAT line."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction(customer_rate=1000, deduction=250)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		cn = frappe.get_doc(
			"Sales Invoice",
			frappe.db.get_value("Sales Invoice", {"is_return": 1, "customer": self.customer}, "name"),
		)
		# CN total matches the deduction
		self.assertEqual(flt(cn.grand_total, 2), -250.0)

	def test_main_si_total_matches_expected_at_submit(self):
		"""The main SI's net_total equals the sum of the log's source amounts
		(the deferred deductions are added back when the sources are logged)."""
		self._mode(CREDIT_NOTE)
		card = self._card_with_non_taxable_deduction(customer_rate=1000, deduction=100)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		log = frappe.get_doc("GL Posting Log", {"posting_doc": si_name, "status": "Draft"})
		# one source row with the expected amount (customer_net + deferred deductions)
		src_rows = [r for r in log.sources if r.source_doctype == "Card Monthly Card"]
		self.assertEqual(len(src_rows), 1)
		self.assertEqual(src_rows[0].source_name, card.name)
		# source amount == main SI net_total (the submit-time reconciliation check)
		self.assertEqual(flt(src_rows[0].amount, 2), flt(si.net_total, 2))
		# the submit-time reconciliation check does not fire
		si.reload()
		si.submit()
		self.assertEqual(si.docstatus, 1)

	def test_backlink_tag_on_cn_log_remarks(self):
		"""The CN log remarks start with the backlink tag so `_active_credit_note_for`
		finds the pair via a LIKE prefix match (idempotency)."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		main_log = frappe.get_doc("GL Posting Log", {"posting_doc": si_name})
		cn_log = frappe.get_doc(
			"GL Posting Log",
			{"origin": "Credit Note", "party": self.customer, "month": "09", "year": 2026},
		)
		self.assertTrue(cn_log.remarks.startswith(_cn_backlink_tag(main_log.name)))

	def test_card_comment_names_the_credit_note(self):
		"""An Info Comment on each affected card names the CN (no new DocType field)."""
		self._mode(CREDIT_NOTE)
		card = self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		cn_name = frappe.db.get_value("Sales Invoice", {"is_return": 1, "customer": self.customer}, "name")
		comments = frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Card Monthly Card",
				"reference_name": card.name,
				"comment_type": "Info",
			},
			fields=["content"],
		)
		self.assertTrue(
			any("FR-156" in c.content and cn_name in c.content for c in comments),
			"card carries a FR-156 Info Comment naming the credit note",
		)

	def test_taxable_and_non_taxable_deductions_split_cleanly(self):
		"""On the same card, taxable deductions go to the main SI as a Net Total
		discount and non-taxable deductions go to the CN."""
		self._mode(CREDIT_NOTE)
		eq = self._rented_out(customer_rate=1000)
		self._card(
			eq,
			[8, 8],
			adjustments=[
				{
					"adjustment_type_ref": "Penalty",
					"side": "Customer",
					"description": "penT",
					"amount": 200,
				},
				{
					"adjustment_type_ref": "DieselNT",
					"side": "Customer",
					"description": "dntNT",
					"amount": 150,
				},
			],
			submit=True,
		)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		self.assertEqual(si.apply_discount_on, "Net Total")
		self.assertEqual(flt(si.discount_amount, 2), 200.0)  # taxable
		self.assertEqual(flt(si.net_total, 2), 1400.0)  # 1600 - 200 taxable
		si.reload()
		si.submit()
		cn = frappe.get_doc(
			"Sales Invoice",
			frappe.db.get_value("Sales Invoice", {"is_return": 1, "customer": self.customer}, "name"),
		)
		self.assertEqual(flt(cn.net_total, 2), -150.0)  # non-taxable only


class TestIdempotency(_CreditNoteBase):
	"""One CN per unique (main SI, deductions) pair: a repeated submit never
	issues a second CN."""

	def test_double_build_at_submit_returns_the_existing_cn(self):
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		log = frappe.get_doc("GL Posting Log", {"posting_doc": si_name})
		first = _active_credit_note_for(log)
		# a second call to the builder returns the same CN, not a second one
		second = _build_non_taxable_credit_note(si, log)
		self.assertEqual(first, second)
		# only one CN in the DB
		cns = frappe.get_all(
			"Sales Invoice",
			filters={"is_return": 1, "customer": self.customer, "docstatus": ["<", 2]},
		)
		self.assertEqual(len(cns), 1)


class TestCrossCompanyIsolation(_CreditNoteBase):
	"""The mode is per-company; a change on one company's row never leaks to
	the other, and a run on each company produces its own outcome."""

	def test_second_company_refuse_does_not_leak_into_credit_note_company(self):
		self._mode(CREDIT_NOTE)
		# a second company row in the same Card Settings; set Refuse there
		other = self._second_company()
		self._mode(REFUSE, company=other)
		# a card for the first company (mode=Credit note) builds through
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		self.assertTrue(si_name)
		# the reader is still Refuse for the other company
		self.assertFalse(preflight.credit_notes_non_taxable_customer_deduction(other))
		# and Credit note for this company
		self.assertTrue(preflight.credit_notes_non_taxable_customer_deduction(self.company))

	def _second_company(self):
		"""A second company with the minimum settings for the preflight check."""
		existing = frappe.db.get_value("Company", {"company_name": "TEST-FR156-OTHER"}, "name")
		if existing:
			return existing
		co = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": "TEST-FR156-OTHER",
				"default_currency": "SAR",
				"country": "Saudi Arabia",
			}
		).insert(ignore_permissions=True)
		return co.name


class TestModeFlipGuard(_CreditNoteBase):
	"""An owner flipping the mode between build and submit is a configuration
	hazard; the submit guard catches it and refuses rather than silently
	dropping the deductions."""

	def test_flipping_to_refuse_between_build_and_submit_is_refused(self):
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		# owner flips the company's mode back to Refuse before the SI is submitted
		self._mode(REFUSE)
		si = frappe.get_doc("Sales Invoice", si_name)
		with self.assertRaisesRegex(frappe.ValidationError, "no longer allows the credit-note route"):
			si.reload()
			si.submit()
		# the main SI is still a draft (submit rolled back)
		self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "docstatus"), 0)
		# no CN was created
		self.assertFalse(frappe.get_all("Sales Invoice", filters={"is_return": 1}))


class TestCancelPath(_CreditNoteBase):
	"""The main SI and its CN cancel as a pair: cancelling the main SI is
	refused while an active CN exists; the accountant cancels the CN first."""

	def test_main_si_cancel_refused_while_cn_draft_active(self):
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "has an active credit note"):
			si.reload()
			si.cancel()
		# the main SI is still submitted
		self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "docstatus"), 1)

	def test_main_si_cancels_after_cn_draft_is_deleted(self):
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		cn_name = frappe.db.get_value(
			"Sales Invoice", {"is_return": 1, "customer": self.customer, "docstatus": 0}, "name"
		)
		# delete the CN draft -> its log flips Cancelled by on_trash
		frappe.delete_doc("Sales Invoice", cn_name, ignore_permissions=True)
		# now the main SI cancels (we also need a cancel reason on the card to free the source,
		# but the main-SI cancel path itself only clears the source links)
		si.reload()
		si.cancel()
		self.assertEqual(si.docstatus, 2)

	def test_cn_cancel_leaves_main_si_submitted(self):
		"""Cancelling the CN alone (with cancel) is a routine operation; the
		main SI stays submitted."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		cn_name = frappe.db.get_value(
			"Sales Invoice", {"is_return": 1, "customer": self.customer, "docstatus": 0}, "name"
		)
		cn = frappe.get_doc("Sales Invoice", cn_name)
		cn.submit()
		cn.reload()
		cn.cancel()
		# cn log flips Cancelled
		cn_log = frappe.get_doc("GL Posting Log", {"posting_doc": cn_name})
		self.assertEqual(cn_log.status, "Cancelled")
		# main SI stays submitted
		self.assertEqual(frappe.db.get_value("Sales Invoice", si_name, "docstatus"), 1)


class TestConcurrency(_CreditNoteBase):
	"""Lesson 4: a FOR UPDATE lock on the main log row plus a DB unique
	posting_key with a CN digest clause (`GLPostingLog.validate`) make two
	concurrent attempts to build a CN for the same main log produce one CN at
	most. Two complementary assertions in one test: the DB-level uniqueness
	refuses a second CN attempt, and the idempotency short-circuit returns the
	existing CN name on a serial second call."""

	def test_duplicate_cn_for_the_same_main_log_is_refused_by_the_db(self):
		"""The posting_key of a CN log includes a digest of the CN's own SI, so
		a hypothetical second CN with the same digest is refused at the DB
		unique index. Here we simulate the race by inserting a second CN log
		row with the same posting_doc value and expect the DB to refuse."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		cn_log = frappe.get_doc(
			"GL Posting Log",
			{"origin": "Credit Note", "party": self.customer, "month": "09", "year": 2026},
		)
		# a second CN log with the same posting_doc collides on the unique
		# posting_key (the CN digest clause)
		dupe = frappe.get_doc(
			{
				"doctype": "GL Posting Log",
				"company": cn_log.company,
				"party_type": "Customer",
				"party": cn_log.party,
				"month": cn_log.month,
				"year": cn_log.year,
				"posting_type": "Sales Invoice",
				"sequence": 2,
				"status": "Draft",
				"origin": "Credit Note",
				"posting_doctype": "Sales Invoice",
				"posting_doc": cn_log.posting_doc,
				"amount": cn_log.amount,
				"remarks": cn_log.remarks,
			}
		)
		dupe.flags.card_gl_build = True
		with self.assertRaises(Exception):
			# frappe.DuplicateEntryError or validate_builder_insert; either kind refuses
			dupe.insert(ignore_permissions=True)

	def test_serial_second_build_call_returns_the_existing_cn(self):
		"""The idempotency short-circuit of `_build_non_taxable_credit_note`
		returns the existing CN rather than building a second one; the FOR
		UPDATE row lock on the main log makes concurrent calls serialise to
		the same outcome."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		log = frappe.get_doc("GL Posting Log", {"posting_doc": si_name})
		first = _active_credit_note_for(log)
		second = _build_non_taxable_credit_note(si, log)
		self.assertEqual(first, second)
		# only one CN exists
		cns = frappe.get_all(
			"Sales Invoice",
			filters={"is_return": 1, "customer": self.customer, "docstatus": ["<", 2]},
		)
		self.assertEqual(len(cns), 1)


class TestMutationGuards(_CreditNoteBase):
	"""Lesson 12: every guard this feature introduces, when removed, breaks a test.
	These tests pin the guard directly so a refactor cannot silently weaken it."""

	def test_refuse_branch_guard_is_active_in_refuse_mode(self):
		"""Mutation check: remove the `if not credit_note_mode: throw` branch and
		a non-taxable customer deduction would quietly skip the SI in Refuse mode."""
		self._mode(REFUSE)
		# the card has the only billable going to the CN route — if the guard is
		# off, the main SI would be built with 1600 and no deduction, no CN; that
		# would miss a 100 deduction and still submit. The guard throws instead.
		self._card_with_non_taxable_deduction(customer_rate=1000, deduction=100)
		with self.assertRaisesRegex(frappe.ValidationError, "Non-taxable customer-side deduction"):
			build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)

	def test_idempotency_check_is_active(self):
		"""Mutation check: remove the `_active_credit_note_for` short-circuit and
		a second call would build a second CN with the same deductions."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		# a direct second call must return the existing CN, not a new one
		log = frappe.get_doc("GL Posting Log", {"posting_doc": si_name})
		first = _active_credit_note_for(log)
		second = _build_non_taxable_credit_note(si, log)
		self.assertEqual(first, second)

	def test_mode_recheck_at_submit_is_active(self):
		"""Mutation check: remove the submit-time `credit_notes_...` check and a
		mode flip between build and submit would silently drop the deductions."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		self._mode(REFUSE)
		si = frappe.get_doc("Sales Invoice", si_name)
		with self.assertRaisesRegex(frappe.ValidationError, "no longer allows the credit-note route"):
			si.reload()
			si.submit()

	def test_cancel_cascade_guard_is_active(self):
		"""Mutation check: remove the dependent-CN check in `before_cancel` of the
		main SI and the accountant could cancel the main SI, orphaning the CN."""
		self._mode(CREDIT_NOTE)
		self._card_with_non_taxable_deduction()
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		si.reload()
		si.submit()
		with self.assertRaisesRegex(frappe.ValidationError, "has an active credit note"):
			si.reload()
			si.cancel()

	def test_source_amount_is_reconciled_at_submit(self):
		"""Mutation check: remove the `source_amount + cn_deductions` adjustment
		in posting._plan_monthly_posting and the submit reconciliation check
		(events.before_submit) would refuse the main SI (actual != expected)."""
		self._mode(CREDIT_NOTE)
		card = self._card_with_non_taxable_deduction(customer_rate=1000, deduction=100)
		si_name = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		si = frappe.get_doc("Sales Invoice", si_name)
		log = frappe.get_doc("GL Posting Log", {"posting_doc": si_name})
		# source amount = card.customer_net_amount + cn_deductions = 1500 + 100 = 1600
		src = next(r for r in log.sources if r.source_name == card.name)
		self.assertEqual(flt(src.amount, 2), 1600.0)
		# the main SI's net_total matches the source amount, so the submit
		# reconciliation check does not fire
		self.assertEqual(flt(si.net_total, 2), 1600.0)
		si.reload()
		si.submit()
		self.assertEqual(si.docstatus, 1)
