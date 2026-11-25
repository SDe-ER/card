# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-191: month-end approval rule, open-month reopen on the ORIGINAL card, open-month editing and final approval.

The Riyadh business date is frozen per test with ``card.approval_period.riyadh_today`` (the rule's only clock);
the cards are September 2026 cards, so 2026-09-20 means "September is open" and 2026-10-01 means "September has
ended". All data is per-test and rolled back."""

from datetime import UTC, date, datetime, timezone
from unittest.mock import patch

import frappe
import frappe.client
from frappe.utils import flt

from card import approval_period, open_month
from card.approval_period import ApprovalBeforeMonthEndError
from card.open_month import STATE_OPEN_MONTH, OpenMonthEditError, OpenMonthStateError, ReopenRefusedError
from card.tests.test_controllers import _days
from card.tests.test_customer import _CustomerCardsBase

CARD = "Card Monthly Card"
OPEN = date(2026, 9, 20)  # September 2026 not ended (Riyadh)
ENDED = date(2026, 10, 1)  # first permitted approval day of September 2026
REASON = "Owner-authorized open-month recovery (test)"


def _today(d):
	return patch("card.approval_period.riyadh_today", return_value=d)


class TestApprovalPeriodRule(_CustomerCardsBase):
	# ---------- the date rule ----------
	def test_earliest_approval_date(self):
		self.assertEqual(approval_period.earliest_approval_date(2026, "11"), date(2026, 12, 1))
		self.assertEqual(approval_period.earliest_approval_date(2026, "12"), date(2027, 1, 1))  # Dec -> Jan
		self.assertEqual(approval_period.earliest_approval_date(2027, "02"), date(2027, 3, 1))
		self.assertEqual(approval_period.earliest_approval_date(2028, "02"), date(2028, 3, 1))  # leap year

	def test_riyadh_midnight_boundary(self):
		before = datetime(2026, 11, 30, 20, 59, 59, tzinfo=UTC)  # 23:59:59 +03:00
		at = datetime(2026, 11, 30, 21, 0, 0, tzinfo=UTC)  # 00:00:00 +03:00 on 1 December
		self.assertEqual(approval_period.riyadh_today(before), date(2026, 11, 30))
		self.assertEqual(approval_period.riyadh_today(at), date(2026, 12, 1))
		self.assertFalse(approval_period.month_ended(2026, "11", approval_period.riyadh_today(before)))
		self.assertTrue(approval_period.month_ended(2026, "11", approval_period.riyadh_today(at)))

	def test_leap_february_boundaries(self):
		self.assertFalse(approval_period.month_ended(2028, "02", date(2028, 2, 29)))
		self.assertTrue(approval_period.month_ended(2028, "02", date(2028, 3, 1)))
		self.assertFalse(approval_period.month_ended(2027, "02", date(2027, 2, 28)))
		self.assertTrue(approval_period.month_ended(2027, "02", date(2027, 3, 1)))
		self.assertTrue(approval_period.month_ended(2026, "12", date(2027, 1, 1)))
		self.assertFalse(approval_period.month_ended(2026, "12", date(2026, 12, 31)))

	# ---------- the submit routes ----------
	def _draft(self, hours=(8, 8)):
		return self._card(self._equipment(), list(hours))

	def test_save_current_month_then_reject_submit(self):
		with _today(OPEN):
			card = self._draft()
			card.append("days", _days([0, 0, 9])[2])
			card.save()
			self.assertEqual(flt(card.total_working_hours), 25)
			with self.assertRaises(ApprovalBeforeMonthEndError):
				card.submit()
		self.assertEqual(frappe.db.get_value(CARD, card.name, "docstatus"), 0)

	def test_reject_future_month(self):
		with _today(date(2026, 8, 15)):
			card = self._draft(hours=(0, 0))
			with self.assertRaises(ApprovalBeforeMonthEndError):
				card.submit()

	def test_allow_previous_month(self):
		with _today(ENDED):
			card = self._draft()
			card.submit()
		self.assertEqual(frappe.db.get_value(CARD, card.name, "docstatus"), 1)

	def test_rest_submit_rejected(self):
		with _today(OPEN):
			card = self._draft()
			with self.assertRaises(ApprovalBeforeMonthEndError):
				frappe.client.submit(card.as_dict())
		self.assertEqual(frappe.db.get_value(CARD, card.name, "docstatus"), 0)

	def test_bulk_submit_rejected(self):
		from frappe.desk.doctype.bulk_update.bulk_update import submit_cancel_or_update_docs

		with _today(OPEN):
			card = self._draft()
			# the bulk helper commits per document; the test keeps its rollback
			with patch.object(frappe.db, "commit"):
				failed = submit_cancel_or_update_docs(CARD, [card.name], action="submit")
		self.assertIn(card.name, failed or [])
		self.assertEqual(frappe.db.get_value(CARD, card.name, "docstatus"), 0)

	def test_administrator_not_exempt(self):
		self.assertEqual(frappe.session.user, "Administrator")
		with _today(OPEN):
			card = self._draft()
			with self.assertRaises(ApprovalBeforeMonthEndError):
				card.submit()

	def test_eligibility_method(self):
		with _today(OPEN):
			card = self._draft()
			info = approval_period.get_approval_eligibility(card.name)
		self.assertFalse(info["eligible"])
		self.assertEqual(info["earliest_approval_date"], "2026-10-01")
		self.assertTrue(info["message"])


class TestOpenMonthCard(_CustomerCardsBase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		open_month.ensure_open_month_state()

	def _approved(self, hours=(8, 8), adjustments=None):
		"""A card approved the old way (submitted), then the clock is set back into its open month."""
		with _today(ENDED):
			card = frappe.new_doc(CARD)
			card.update(
				{
					"equipment": self._equipment().name,
					"project": self.project,
					"shift": "نهاري",
					"month": "09",
					"year": 2026,
				}
			)
			for row in _days(list(hours)):
				card.append("days", row)
			for adj in adjustments or []:
				card.append("adjustments", {"adjustment_date": "2026-09-01", **adj})
			card.insert()
			card.submit()
		card.reload()
		return card

	def _snapshot(self, name):
		doc = frappe.get_doc(CARD, name)
		rows = lambda table: [  # noqa: E731
			{
				k: v
				for k, v in r.as_dict().items()
				if k not in ("modified", "modified_by", "creation", "owner")
			}
			for r in doc.get(table)
		]
		return {
			"days": rows("days"),
			"adjustments": rows("adjustments"),
			"totals": {f: flt(doc.get(f)) for f in open_month.COMPUTED_FIELDS},
		}

	def _reopen(self, name):
		with _today(OPEN):
			return open_month.reopen_card(name, REASON)

	# ---------- reopen on the same ID ----------
	def test_reopen_keeps_name_rows_and_creates_nothing(self):
		card = self._approved(
			adjustments=[{"adjustment_type": "خصم", "description": "Diesel", "amount": 100}]
		)
		card.add_comment("Comment", "kept")
		before = self._snapshot(card.name)
		cards_before = frappe.db.count(CARD)
		docs_before = {
			dt: frappe.db.count(dt)
			for dt in (
				"Journal Entry",
				"Payment Entry",
				"Purchase Invoice",
				"Sales Invoice",
				"GL Posting Log",
			)
		}
		out = self._reopen(card.name)
		self.assertEqual(out["name"], card.name)
		stored = frappe.db.get_value(
			CARD, card.name, ["docstatus", "workflow_state", "approved_by"], as_dict=True
		)
		self.assertEqual(
			(stored.docstatus, stored.workflow_state, stored.approved_by), (1, STATE_OPEN_MONTH, None)
		)
		self.assertEqual(self._snapshot(card.name), before)
		self.assertEqual(frappe.db.count(CARD), cards_before)
		self.assertFalse(frappe.db.exists(CARD, {"amended_from": card.name}))
		self.assertEqual({dt: frappe.db.count(dt) for dt in docs_before}, docs_before)
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": card.name, "content": "kept"}))
		self.assertTrue(
			frappe.db.exists(
				"Comment", {"reference_name": card.name, "content": ["like", "%" + REASON + "%"]}
			)
		)

	def test_reopen_refused_when_month_ended_posted_or_not_system_manager(self):
		card = self._approved()
		with _today(ENDED), self.assertRaises(ReopenRefusedError):
			open_month.reopen_card(card.name, REASON)
		frappe.db.set_value(CARD, card.name, "posted", 1)
		with _today(OPEN), self.assertRaises(ReopenRefusedError):
			open_month.reopen_card(card.name, REASON)
		frappe.db.set_value(CARD, card.name, "posted", 0)
		user = "open-month-mgr-" + frappe.generate_hash(length=6) + "@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": "OM",
				"send_welcome_email": 0,
				"roles": [{"role": "Card Manager"}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(user)
		try:
			with _today(OPEN), self.assertRaises(frappe.PermissionError):
				open_month.reopen_card(card.name, REASON)
		finally:
			frappe.set_user("Administrator")

	# ---------- editing an open card ----------
	def test_add_day_row_and_adjustment_on_open_card(self):
		card = self._approved()
		self._reopen(card.name)
		with _today(OPEN):
			doc = frappe.get_doc(CARD, card.name)
			doc.append("days", {"operation_date": "2026-09-03", "day_status": "عمل", "working_hours": 10})
			doc.append(
				"adjustments",
				{
					"adjustment_date": "2026-09-03",
					"adjustment_type": "خصم",
					"description": "Diesel",
					"amount": 50,
				},
			)
			doc.save(ignore_version=False)
		doc = frappe.get_doc(CARD, card.name)
		self.assertEqual(doc.name, card.name)
		self.assertEqual(len(doc.days), 3)
		self.assertEqual(flt(doc.total_working_hours), 26)
		self.assertEqual(doc.working_days, 3)
		self.assertEqual(flt(doc.amount), flt(26 * 75.0, 2))
		self.assertEqual(flt(doc.total_deductions), 50)
		self.assertEqual(flt(doc.net_amount), flt(26 * 75.0 - 50, 2))
		self.assertTrue(frappe.db.exists("Version", {"ref_doctype": CARD, "docname": card.name}))
		self.assertIn("Administrator", doc.edited_by or "")
		# the posting builders never see an open card
		from card.gl.posting import _supplier_sources

		cards, _fills, _transports = _supplier_sources(
			doc.company, doc.supplier, date(2026, 9, 1), date(2026, 9, 30), 9, 2026
		)
		self.assertNotIn(card.name, [c.name for c in cards])
		self.assertTrue(open_month.provisional_suffix(doc))

	def test_frozen_field_refused_on_open_card(self):
		card = self._approved()
		self._reopen(card.name)
		with _today(OPEN), self.assertRaises(frappe.UpdateAfterSubmitError):
			doc = frappe.get_doc(CARD, card.name)
			doc.shift = "ليلي"
			doc.save()

	def test_approved_card_stays_frozen(self):
		card = self._approved()
		with _today(OPEN), self.assertRaises(OpenMonthEditError):
			doc = frappe.get_doc(CARD, card.name)
			doc.append("days", {"operation_date": "2026-09-03", "day_status": "عمل", "working_hours": 4})
			doc.save()
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			frappe.client.set_value(CARD, card.name, "net_amount", 1)
		with self.assertRaises(OpenMonthStateError):
			frappe.client.set_value(CARD, card.name, "workflow_state", STATE_OPEN_MONTH)
		self.assertEqual(len(frappe.get_doc(CARD, card.name).days), 2)

	# ---------- final approval ----------
	def test_final_approval_only_after_month_end(self):
		card = self._approved()
		self._reopen(card.name)
		with _today(OPEN), self.assertRaises(ApprovalBeforeMonthEndError):
			open_month.approve_open_month_card(card.name)
		with _today(ENDED):
			out = open_month.approve_open_month_card(card.name)
		self.assertEqual(out["workflow_state"], open_month.STATE_APPROVED)
		stored = frappe.db.get_value(
			CARD, card.name, ["docstatus", "approved_by", "approved_on"], as_dict=True
		)
		self.assertEqual((stored.docstatus, stored.approved_by), (1, "Administrator"))
		self.assertTrue(stored.approved_on)
		with _today(ENDED), self.assertRaises(OpenMonthEditError):
			doc = frappe.get_doc(CARD, card.name)
			doc.append("days", {"operation_date": "2026-09-03", "day_status": "عمل", "working_hours": 4})
			doc.save()

	def test_concurrent_edit_and_approval(self):
		card = self._approved()
		self._reopen(card.name)
		stale = frappe.get_doc(CARD, card.name)
		with _today(ENDED):
			open_month.approve_open_month_card(card.name)
			stale.append("days", {"operation_date": "2026-09-03", "day_status": "عمل", "working_hours": 4})
			with self.assertRaises((frappe.TimestampMismatchError, frappe.UpdateAfterSubmitError)):
				stale.save()

	# ---------- recovery method ----------
	def test_recovery_dry_run_idempotent_and_refusals(self):
		a = self._approved()
		b = self._approved()
		frappe.db.set_value(CARD, b.name, "posted", 1)
		mine = {a.name, b.name}
		with _today(OPEN):
			dry = open_month.reopen_open_month_cards(2026, "09", dry_run=1)
			plan = {c["name"]: c["action"] for c in dry["cards"] if c["name"] in mine}
			self.assertEqual(plan, {a.name: "would reopen", b.name: "refused"})
			self.assertEqual(
				frappe.db.get_value(CARD, a.name, "workflow_state"), "Approved – before governance"
			)
			run = open_month.reopen_open_month_cards(2026, "09", dry_run=0, reason=REASON)
			self.assertEqual(
				{c["name"]: c["action"] for c in run["cards"] if c["name"] in mine},
				{a.name: "reopened", b.name: "refused"},
			)
			again = open_month.reopen_open_month_cards(2026, "09", dry_run=0, reason=REASON)
			self.assertEqual(
				{c["name"]: c["action"] for c in again["cards"] if c["name"] in mine},
				{a.name: "already open", b.name: "refused"},
			)
		self.assertEqual(run["new_cards"], 0)

	def test_recovery_rolls_back_a_failing_card(self):
		a = self._approved()
		real = open_month._reopen

		def failing(doc, reason):
			real(doc, reason)
			raise RuntimeError("boom")

		with _today(OPEN), patch("card.open_month._reopen", side_effect=failing):
			run = open_month.reopen_open_month_cards(2026, "09", dry_run=0, reason=REASON)
		entry = next(c for c in run["cards"] if c["name"] == a.name)
		self.assertEqual(entry["action"], "error")
		self.assertEqual(frappe.db.get_value(CARD, a.name, "workflow_state"), "Approved – before governance")

	# ---------- review follow-ups ----------
	def test_held_open_card_is_not_edited(self):
		card = self._approved()
		self._reopen(card.name)
		frappe.db.set_value(CARD, card.name, "posted", 1)
		with _today(OPEN), self.assertRaises(OpenMonthEditError):
			doc = frappe.get_doc(CARD, card.name)
			doc.append("days", {"operation_date": "2026-09-03", "day_status": "عمل", "working_hours": 4})
			doc.save()

	def test_snapshot_follows_open_card_recalculation(self):
		card = self._approved()
		self._reopen(card.name)
		frappe.db.set_value("Card Equipment", card.equipment, "daily_hours", 8)
		with _today(OPEN):
			doc = frappe.get_doc(CARD, card.name)
			doc.append("days", {"operation_date": "2026-09-03", "day_status": "عمل", "working_hours": 4})
			doc.save()
		stored = frappe.db.get_value(
			CARD, card.name, ["daily_hours_used", "hourly_rate_used", "amount"], as_dict=True
		)
		self.assertEqual(flt(stored.daily_hours_used), 8)
		self.assertEqual(flt(stored.hourly_rate_used), flt(750 / 8, 6))
		self.assertEqual(flt(stored.amount), flt(20 * 750 / 8, 2))

	def test_unchanged_update_of_approved_card_is_accepted(self):
		card = self._approved()
		doc = frappe.get_doc(CARD, card.name)
		for row in doc.days:
			row.working_hours = int(row.working_hours)  # 8.0 -> 8, as a Desk round trip sends it
		doc.save()
		self.assertEqual(
			frappe.db.get_value(CARD, card.name, "workflow_state"), "Approved – before governance"
		)

	def test_no_native_transition_is_added(self):
		from card.governance_workflows import WORKFLOWS

		wf = frappe.get_doc("Workflow", WORKFLOWS[CARD])
		self.assertIn(STATE_OPEN_MONTH, [s.state for s in wf.states])
		self.assertNotIn(
			STATE_OPEN_MONTH, [t.state for t in wf.transitions] + [t.next_state for t in wf.transitions]
		)
		self.assertFalse(wf.is_active)
