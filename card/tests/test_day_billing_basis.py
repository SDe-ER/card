# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-138 (#123, #44; C-05, O-06): the day billing basis of a per-day ("باليوم") rate.

Proven here: the default basis "Prorated by hours" prices every card exactly as before
(billed hours x rate / daily hours), also for an equipment saved before FR-138 (empty value);
"Full day" bills each billed day at the per-day rate; the basis is snapshotted on submit and a
submitted card is never repriced; an amended card is priced with the equipment's basis of its own
submit; a sub-rental card applies the basis to each side by that side's own rate basis and billed
days; the Equipment Supplier Statement shows the basis used. All data is per-test and rolled back."""

import frappe
from frappe.utils import flt

from card.card.report.equipment_customer_statement.equipment_customer_statement import (
	execute as customer_statement,
)
from card.card.report.equipment_supplier_statement.equipment_supplier_statement import (
	execute as supplier_statement,
)
from card.card_value import DAY_BASIS_FULL_DAY, DAY_BASIS_PRORATED, DAY_BILLING_BASES, day_billing_basis
from card.patches.v4_8_0 import default_day_billing_basis
from card.tests.cancel_reason import with_reason
from card.tests.test_stop_reasons import CLIENT_STOP, STATEMENT, _StopBase

HOURS = [4, 10, 12]  # 26 hours on 3 working days


class TestDayBillingBasis(_StopBase):
	def _set_basis(self, eq, basis):
		eq.reload()
		eq.day_billing_basis = basis
		eq.commercial_change_reason = "TEST basis " + basis + " " + frappe.generate_hash(length=4)
		eq.save(ignore_permissions=True)
		eq.reload()
		return eq

	# ---- default: identical to the behaviour before FR-138 ----
	def test_default_is_prorated_and_prices_as_before(self):
		eq = self._equipment()  # rented in: 750/day over 10 h = 75/h
		self.assertEqual(eq.day_billing_basis, DAY_BASIS_PRORATED)
		card = self._card(eq, HOURS, submit=True)
		self.assertEqual(card.day_billing_basis, DAY_BASIS_PRORATED)
		self.assertEqual(flt(card.amount), 26 * 75.0)  # billed hours x rate / daily hours
		self.assertEqual(flt(card.net_amount), 26 * 75.0)
		self.assertEqual(flt(card.hourly_rate_used), 75.0)
		self.assertEqual(card.day_billing_basis_used, DAY_BASIS_PRORATED)

	def test_legacy_equipment_without_a_basis_is_prorated(self):
		eq = self._equipment()
		frappe.db.set_value("Card Equipment", eq.name, "day_billing_basis", None, update_modified=False)
		card = self._card(eq, HOURS, submit=True)
		self.assertEqual(flt(card.amount), 26 * 75.0)
		self.assertEqual(card.day_billing_basis_used, DAY_BASIS_PRORATED)
		self.assertEqual(day_billing_basis(None), DAY_BASIS_PRORATED)
		self.assertEqual(day_billing_basis(""), DAY_BASIS_PRORATED)

	def test_patch_fills_the_default_and_is_idempotent(self):
		eq = self._equipment()
		frappe.db.set_value("Card Equipment", eq.name, "day_billing_basis", None, update_modified=False)
		modified = frappe.db.get_value("Card Equipment", eq.name, "modified")
		full = self._set_basis(self._equipment(), DAY_BASIS_FULL_DAY)
		for _run in range(2):
			default_day_billing_basis.execute()
			self.assertEqual(
				frappe.db.get_value("Card Equipment", eq.name, "day_billing_basis"), DAY_BASIS_PRORATED
			)
			self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "modified"), modified)
			# an explicit choice is never overwritten
			self.assertEqual(
				frappe.db.get_value("Card Equipment", full.name, "day_billing_basis"), DAY_BASIS_FULL_DAY
			)

	# ---- Full day ----
	def test_full_day_bills_each_working_day_at_the_day_rate(self):
		eq = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		card = self._card(eq, HOURS, submit=True)
		self.assertEqual(card.working_days, 3)
		self.assertEqual(flt(card.total_working_hours), 26)  # hours are still recorded
		self.assertEqual(flt(card.amount), 3 * 750.0)  # 4 h, 10 h and 12 h days: one day each
		self.assertEqual(flt(card.net_amount), 3 * 750.0)
		self.assertEqual(card.day_billing_basis_used, DAY_BASIS_FULL_DAY)

	def test_full_day_adds_adjustments_like_before(self):
		eq = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		c = frappe.new_doc("Card Monthly Card")
		c.update(
			{"equipment": eq.name, "project": self.project, "shift": "نهاري", "month": "09", "year": 2026}
		)
		for i, h in enumerate(HOURS, start=1):
			c.append("days", {"operation_date": "2026-09-%02d" % i, "day_status": "عمل", "working_hours": h})
		c.append("adjustments", {"adjustment_type": "خصم", "amount": 100, "description": "TEST"})
		c.insert(ignore_permissions=True)
		self.assertEqual(flt(c.amount), 2250.0)
		self.assertEqual(flt(c.net_amount), 2150.0)

	def test_full_day_counts_a_day_billed_only_by_a_billable_stop(self):
		eq = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		reason = self._reason(billable=1)
		card = self._stop_card(
			eq,
			[
				{"working_hours": 6, "stop_reason": reason.name, "stopped_hours": 2},  # one day, not two
				{"day_status": CLIENT_STOP, "stop_reason": reason.name, "stopped_hours": 4},
			],
			submit=True,
		)
		self.assertEqual(card.working_days, 1)
		self.assertEqual(card.billable_stopped_days, 1)
		self.assertEqual(flt(card.amount), 2 * 750.0)
		# a non-billable stopped day bills nothing, as before
		plain = self._reason(billable=0)
		card = self._stop_card(
			self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY),
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": plain.name, "stopped_hours": 4},
			],
		)
		self.assertEqual(flt(card.amount), 750.0)

	def test_full_day_leaves_hourly_and_monthly_rates_unchanged(self):
		hourly = self._equipment(rate_type="بالساعة", rate=80, day_billing_basis=DAY_BASIS_FULL_DAY)
		self.assertEqual(flt(self._card(hourly, HOURS).amount), 26 * 80.0)
		monthly = self._equipment(rate_type="بالشهر", rate=26000, day_billing_basis=DAY_BASIS_FULL_DAY)
		self.assertEqual(flt(self._card(monthly, HOURS).amount), 26 * 100.0)  # 26,000 / 260 h

	def test_unknown_basis_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(day_billing_basis="Half day")

	def test_basis_is_a_commercial_field(self):
		from card.card.doctype.card_equipment.card_equipment import COMMERCIAL_FIELDS

		self.assertIn("day_billing_basis", COMMERCIAL_FIELDS)
		eq = self._equipment()
		eq.reload()
		eq.day_billing_basis = DAY_BASIS_FULL_DAY
		eq.commercial_change_reason = None
		with self.assertRaises(frappe.ValidationError):
			eq.save(ignore_permissions=True)

	# ---- snapshot: a submitted card is never repriced ----
	def test_submitted_card_keeps_its_basis_and_amount(self):
		eq = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		card = self._card(eq, HOURS, submit=True)
		draft = frappe.new_doc("Card Monthly Card")  # same equipment, October
		draft.update({"equipment": eq.name, "project": self.project, "shift": "نهاري"})
		draft.update({"month": "10", "year": 2026})
		for i, h in enumerate(HOURS, start=1):
			draft.append(
				"days", {"operation_date": "2026-10-%02d" % i, "day_status": "عمل", "working_hours": h}
			)
		draft.insert(ignore_permissions=True)
		self.assertEqual(flt(draft.amount), 2250.0)
		self.assertFalse(draft.day_billing_basis_used)  # taken on submit only

		self._set_basis(eq, DAY_BASIS_PRORATED)

		card.reload()  # submitted: never repriced
		self.assertEqual(card.day_billing_basis_used, DAY_BASIS_FULL_DAY)
		self.assertEqual(flt(card.amount), 2250.0)
		self.assertEqual(flt(card.net_amount), 2250.0)
		draft.reload()  # draft: follows the equipment on its next save
		draft.save(ignore_permissions=True)
		draft.reload()
		self.assertEqual(draft.day_billing_basis, DAY_BASIS_PRORATED)
		self.assertEqual(flt(draft.amount), 26 * 75.0)
		draft.submit()
		draft.reload()
		self.assertEqual(draft.day_billing_basis_used, DAY_BASIS_PRORATED)

	def test_amended_card_is_priced_with_the_basis_of_its_own_submit(self):
		eq = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		card = self._card(eq, HOURS, submit=True)
		with_reason(card).cancel()
		self._set_basis(eq, DAY_BASIS_PRORATED)

		amended = frappe.copy_doc(card, ignore_no_copy=False)
		amended.amended_from = card.name
		amended.docstatus = 0  # as the Desk "Amend" action does
		amended.insert(ignore_permissions=True)
		self.assertFalse(amended.day_billing_basis_used)  # the snapshot is not copied
		self.assertEqual(flt(amended.amount), 26 * 75.0)
		amended.submit()
		amended.reload()
		self.assertEqual(amended.day_billing_basis_used, DAY_BASIS_PRORATED)
		self.assertEqual(flt(amended.amount), 26 * 75.0)
		card.reload()  # the cancelled original keeps what it was priced with
		self.assertEqual(card.day_billing_basis_used, DAY_BASIS_FULL_DAY)
		self.assertEqual(flt(card.amount), 2250.0)

	# ---- sub-rental: supplier side and customer side ----
	def test_sub_rental_full_day_bills_both_sides_by_days(self):
		eq = self._sub_rental(day_billing_basis=DAY_BASIS_FULL_DAY)  # 750/day supplier, 1200/day customer
		card = self._card(eq, HOURS, submit=True)
		self.assertEqual(flt(card.amount), 3 * 750.0)
		self.assertEqual(flt(card.customer_amount), 3 * 1200.0)
		self.assertEqual(flt(card.customer_net_amount), 3 * 1200.0)
		# the same machine prorated: both sides as before
		prorated = self._card(self._sub_rental(), HOURS, submit=True)
		self.assertEqual(flt(prorated.amount), 26 * 75.0)
		self.assertEqual(flt(prorated.customer_amount), 26 * 120.0)

	def test_sub_rental_each_side_follows_its_own_rate_basis(self):
		# supplier per day (full day), customer per hour (hours, unchanged)
		eq = self._sub_rental(
			customer_rate=130, customer_rate_type="بالساعة", day_billing_basis=DAY_BASIS_FULL_DAY
		)
		card = self._card(eq, HOURS)
		self.assertEqual(flt(card.amount), 3 * 750.0)
		self.assertEqual(flt(card.customer_amount), 26 * 130.0)

	def test_sub_rental_full_day_counts_stopped_days_per_side(self):
		eq = self._sub_rental(day_billing_basis=DAY_BASIS_FULL_DAY)
		supplier_only = self._reason(billable=1, side="Supplier")
		customer_only = self._reason(billable=1, side="Customer")
		card = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": supplier_only.name, "stopped_hours": 4},
				{"day_status": CLIENT_STOP, "stop_reason": customer_only.name, "stopped_hours": 3},
				{"day_status": CLIENT_STOP, "stop_reason": customer_only.name, "stopped_hours": 5},
			],
		)
		self.assertEqual(flt(card.amount), 2 * 750.0)  # working day + the supplier-billed day
		self.assertEqual(flt(card.customer_amount), 3 * 1200.0)  # working day + two customer-billed days

	# ---- Equipment Supplier Statement shows the basis used ----
	def test_supplier_statement_shows_the_basis_used(self):
		full = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		submitted = self._card(full, HOURS, submit=True)
		prorated = self._card(self._equipment(), HOURS, submit=True)
		hourly = self._card(self._equipment(rate_type="بالساعة", rate=80), HOURS, submit=True)
		self._set_basis(full, DAY_BASIS_PRORATED)  # later change: the statement keeps the used one

		filters = {**STATEMENT, "company": self.company, "supplier": self.supplier, "project": self.project}
		columns, rows, *_ = supplier_statement(filters)
		self.assertIn("day_billing_basis", [c["fieldname"] for c in columns])
		by_card = {r.get("card"): r for r in rows if r.get("card")}
		self.assertEqual(by_card[submitted.name]["day_billing_basis"], frappe._(DAY_BASIS_FULL_DAY))
		self.assertEqual(by_card[submitted.name]["amount"], 2250.0)
		self.assertEqual(by_card[prorated.name]["day_billing_basis"], frappe._(DAY_BASIS_PRORATED))
		self.assertIsNone(by_card[hourly.name]["day_billing_basis"])  # not a per-day rate
		equipment_row = next(r for r in rows if r.get("row_id", "").endswith("|E|" + full.name))
		self.assertEqual(equipment_row["day_billing_basis"], frappe._(DAY_BASIS_FULL_DAY))

	def test_supplier_statement_shows_a_drafts_current_basis(self):
		eq = self._equipment(day_billing_basis=DAY_BASIS_FULL_DAY)
		draft = self._card(eq, HOURS)
		filters = {
			**STATEMENT,
			"company": self.company,
			"supplier": self.supplier,
			"project": self.project,
			"include_draft": 1,
		}
		_c, rows, *_ = supplier_statement(filters)
		row = next(r for r in rows if r.get("card") == draft.name)
		self.assertEqual(row["day_billing_basis"], frappe._(DAY_BASIS_FULL_DAY))
		self.assertEqual(row["amount"], 2250.0)

	# ---- Equipment Customer Statement: basis used and the effective hourly rate ----
	def _customer_rows(self, **kw):
		filters = {
			"company": self.company,
			"customer": self.customer,
			"from_month": 9,
			"from_year": 2026,
			"project": self.project,
			**kw,
		}
		columns, rows, *_ = customer_statement(filters)
		self.assertIn("day_billing_basis", [c["fieldname"] for c in columns])
		return {r.get("card"): r for r in rows if r.get("card")}, rows

	def test_customer_statement_full_day_submitted_card(self):
		eq = self._sub_rental(day_billing_basis=DAY_BASIS_FULL_DAY)  # 1200/day to the customer
		card = self._card(eq, HOURS, submit=True)
		prorated = self._card(self._sub_rental(), HOURS, submit=True)
		self._set_basis(eq, DAY_BASIS_PRORATED)  # later change: the statement keeps the used one
		by_card, rows = self._customer_rows()
		row = by_card[card.name]
		self.assertEqual(row["day_billing_basis"], frappe._(DAY_BASIS_FULL_DAY))
		self.assertEqual(row["customer_amount"], 3600.0)
		# not the nominal snapshot (120/h): the amount over every billed hour, as on the supplier statement
		self.assertEqual(row["hourly_rate"], flt(3600.0 / 26, 2))
		# a prorated card keeps the snapshot rate, as before
		self.assertEqual(by_card[prorated.name]["day_billing_basis"], frappe._(DAY_BASIS_PRORATED))
		self.assertEqual(by_card[prorated.name]["hourly_rate"], 120.0)
		equipment_row = next(r for r in rows if r.get("row_id", "").endswith("|E|" + eq.name))
		self.assertEqual(equipment_row["day_billing_basis"], frappe._(DAY_BASIS_FULL_DAY))

	def test_customer_statement_full_day_stopped_hours_and_draft(self):
		eq = self._sub_rental(day_billing_basis=DAY_BASIS_FULL_DAY)
		customer_only = self._reason(billable=1, side="Customer")
		draft = self._stop_card(
			eq,
			[
				{"working_hours": 8},
				{"day_status": CLIENT_STOP, "stop_reason": customer_only.name, "stopped_hours": 4},
			],
		)
		by_card, _rows = self._customer_rows(include_draft=1)
		row = by_card[draft.name]
		self.assertEqual(row["day_billing_basis"], frappe._(DAY_BASIS_FULL_DAY))  # current basis
		self.assertEqual(row["customer_amount"], 2400.0)
		self.assertEqual(row["hourly_rate"], 200.0)  # 2,400 over 8 + 4 customer-billed hours
		draft.submit()
		by_card, _rows = self._customer_rows()
		self.assertEqual(by_card[draft.name]["hourly_rate"], 200.0)

	def test_card_basis_fields_are_translated_selects(self):
		meta = frappe.get_meta("Card Monthly Card")
		for fieldname in ("day_billing_basis", "day_billing_basis_used"):
			df = meta.get_field(fieldname)
			self.assertEqual(df.fieldtype, "Select")
			self.assertTrue(df.read_only)
			self.assertEqual([o for o in df.options.split("\n") if o], list(DAY_BILLING_BASES))
