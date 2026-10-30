# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Customer side under the F.7 equipment-level model: the EQUIPMENT carries the
rental direction and both billing sides (supplier: supplier/rate_type/rate;
customer: default_customer/customer_rate_type/customer_rate). Cards only MIRROR
the equipment — live on every save of a draft, frozen into *_used snapshots on
submit. CARD stores no customer balances — the official Sales Invoice is
created in S3; here only the classification, the mirror and the accrued
customer amount are proven. All data is per-test and rolled back."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.constants import (
	DIR_INTERNAL,
	DIR_RENTED_IN,
	DIR_RENTED_OUT,
	DIR_SUBRENTAL,
	OWNED,
)
from card.tests.test_controllers import _days, _ensure_masters, _registry_figures

RENTED = "إيجار"


def _leaf(doctype, name_field, root):
	"""A non-group row of a tree master (Customer needs leaf group/territory)."""
	leaf = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if leaf:
		return leaf
	leaf = "Test " + doctype
	if not frappe.db.exists(doctype, leaf):
		frappe.get_doc(
			{"doctype": doctype, name_field: leaf, "parent_" + frappe.scrub(doctype): root, "is_group": 0}
		).insert(ignore_permissions=True)
	return leaf


class _CustomerCardsBase(IntegrationTestCase):
	"""Shared masters + builders for the equipment-level direction tests.
	Not collected by the runner (no test_* methods of its own)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-CUST-PRJ-" + self.token
		proj.company = self.company
		# P1-0 (Owner decision 2026-10-30): CARD postings need the project's cost center
		proj.cost_center = frappe.db.get_value(
			"Cost Center", {"company": self.company, "is_group": 0}, "name"
		)
		proj.insert(ignore_permissions=True)
		self.project = proj.name
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "TEST-CUST-SUP-" + self.token
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		self.customer = self._customer("-A")

	def tearDown(self):
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---- builders ----
	def _customer(self, suffix):
		cust = frappe.new_doc("Customer")
		cust.customer_name = "TEST-CUST-" + self.token + suffix
		cust.customer_group = _leaf("Customer Group", "customer_group_name", "All Customer Groups")
		cust.territory = _leaf("Territory", "territory_name", "All Territories")
		cust.insert(ignore_permissions=True)
		return cust.name

	def _equipment(
		self,
		ownership=RENTED,
		direction=None,
		customer=None,
		customer_rate=None,
		customer_rate_type=None,
		**kw,
	):
		"""F.7: billing is configured ON the equipment. Supplier side 750/day
		over 10h (= 75/h) for rented ownerships; customer side only when asked."""
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = ownership
		d.equipment_name = "TEST-CUST-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		if ownership != OWNED:
			d.supplier = self.supplier
		if direction:
			d.rental_direction = direction
		if customer:
			d.default_customer = customer
		if customer_rate is not None:
			d.customer_rate = customer_rate
			d.customer_rate_type = customer_rate_type or "باليوم"
		for k, v in kw.items():
			setattr(d, k, v)
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _rented_out(self, customer=None, customer_rate=1000, **kw):
		# owned equipment billed to a customer: 1000/day over 10h = 100/h
		return self._equipment(
			OWNED,
			direction=DIR_RENTED_OUT,
			customer=customer or self.customer,
			customer_rate=customer_rate,
			**kw,
		)

	def _sub_rental(self, customer=None, customer_rate=1200, **kw):
		# rented at 750/day (75/h), rented out at 1200/day (120/h)
		return self._equipment(
			RENTED,
			direction=DIR_SUBRENTAL,
			customer=customer or self.customer,
			customer_rate=customer_rate,
			**kw,
		)

	def _card(self, eq, hours_list, submit=False, **presets):
		"""presets are values typed on the card BEFORE insert — the F.7 mirror
		must overwrite every one of them from the equipment."""
		c = frappe.new_doc("Card Monthly Card")
		c.equipment = eq.name
		c.project = self.project
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for k, v in presets.items():
			setattr(c, k, v)
		for row in _days(hours_list):
			c.append("days", row)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c


class TestCardDirection(_CustomerCardsBase):
	# ---- 1. the four directions derive and bill from the EQUIPMENT ----
	def test_internal_default_for_owned_without_customer(self):
		eq = self._equipment(OWNED)
		self.assertEqual(eq.rental_direction, DIR_INTERNAL)  # derived on the equipment itself
		card = self._card(eq, [10, 10], submit=True)
		self.assertEqual(card.card_direction, DIR_INTERNAL)
		self.assertEqual(flt(card.amount), 0)  # no supplier billing (existing rule)
		self.assertEqual(flt(card.customer_amount), 0)  # no customer billing
		self.assertFalse(card.customer)

	def test_rented_in_default_for_rented_without_customer(self):
		eq = self._equipment()
		self.assertEqual(eq.rental_direction, DIR_RENTED_IN)
		card = self._card(eq, [10, 10], submit=True)
		self.assertEqual(card.card_direction, DIR_RENTED_IN)
		self.assertEqual(flt(card.net_amount), flt(20 * 75.0, 2))  # supplier side unchanged
		self.assertEqual(flt(card.customer_amount), 0)
		self.assertFalse(card.customer)

	def test_rented_out_bills_customer(self):
		card = self._card(self._rented_out(), [10, 10], submit=True)
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertEqual(card.customer, self.customer)  # mirrored from the equipment
		self.assertEqual(flt(card.amount), 0)  # still no supplier billing
		self.assertEqual(flt(card.customer_amount), 2000.0)  # 20h x 100/h
		self.assertEqual(flt(card.customer_rate_used), 100.0)  # snapshot on submit

	def test_sub_rental_bills_both_sides(self):
		card = self._card(self._sub_rental(), [10], submit=True)
		self.assertEqual(card.card_direction, DIR_SUBRENTAL)
		self.assertEqual(flt(card.net_amount), 750.0)  # supplier side (our cost)
		self.assertEqual(flt(card.customer_amount), 1200.0)  # customer side (our price)
		self.assertEqual(flt(card.hourly_rate_used), 75.0)
		self.assertEqual(flt(card.customer_rate_used), 120.0)
		# F.7 snapshots: direction / customer / rate basis used at submit
		self.assertEqual(card.direction_used, DIR_SUBRENTAL)
		self.assertEqual(card.direction_used, card.card_direction)
		self.assertEqual(card.customer_used, card.customer)
		self.assertEqual(card.customer_used, self.customer)
		self.assertEqual(card.rate_basis_used, card.rate_type)
		self.assertEqual(card.rate_basis_used, "باليوم")

	# ---- 2. the card MIRRORS the equipment ----
	def test_card_mirrors_equipment_on_insert(self):
		eq = self._rented_out()
		other = self._customer("-OTHER")
		card = self._card(
			eq,
			[10],
			customer=other,
			customer_rate=555,
			customer_rate_type="بالساعة",
			card_direction=DIR_INTERNAL,
		)
		# whatever was typed on the card is overwritten from the equipment
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertEqual(card.customer, self.customer)
		self.assertEqual(flt(card.customer_rate), 1000.0)
		self.assertEqual(card.customer_rate_type, "باليوم")
		self.assertEqual(flt(card.customer_amount), 1000.0)
		# non-billing direction: a typed customer is cleared, nothing billed
		internal = self._card(
			self._equipment(OWNED),
			[10],
			customer=other,
			customer_rate=555,
			customer_rate_type="بالساعة",
		)
		self.assertFalse(internal.customer)
		self.assertFalse(internal.customer_rate_type)
		self.assertEqual(flt(internal.customer_rate), 0)
		self.assertEqual(flt(internal.customer_amount), 0)

	def test_draft_follows_equipment_submitted_frozen(self):
		eq = self._rented_out()
		draft = self._card(eq, [10])
		self.assertEqual(flt(draft.customer_amount), 1000.0)
		frappe.db.set_value("Card Equipment", eq.name, "customer_rate", 2000)
		draft.save(ignore_permissions=True)
		draft.reload()
		self.assertEqual(flt(draft.customer_rate), 2000.0)  # re-mirrored LIVE on save
		self.assertEqual(flt(draft.customer_amount), 2000.0)

		eq2 = self._rented_out()
		submitted = self._card(eq2, [10], submit=True)
		self.assertEqual(flt(submitted.customer_amount), 1000.0)
		frappe.db.set_value("Card Equipment", eq2.name, "customer_rate", 2000)
		submitted.reload()
		self.assertEqual(flt(submitted.customer_rate), 1000.0)  # stored values never change
		self.assertEqual(flt(submitted.customer_amount), 1000.0)
		self.assertEqual(flt(submitted.customer_rate_used), 100.0)

	# ---- 3. guards ----
	def test_billing_direction_requires_customer_on_submit(self):
		eq = self._rented_out()
		# legacy data: the customer vanished from the equipment without validate
		frappe.db.set_value("Card Equipment", eq.name, "default_customer", None)
		card = self._card(eq, [10])  # draft mirrors the empty customer and saves fine
		self.assertEqual(card.docstatus, 0)
		self.assertEqual(card.card_direction, DIR_RENTED_OUT)
		self.assertFalse(card.customer)
		with self.assertRaises(frappe.ValidationError):
			card.submit()

	def test_card_rejects_direction_inconsistent_with_ownership(self):
		eq = self._equipment(OWNED)  # internal
		# flip the equipment to a direction its ownership forbids (no validate)
		frappe.db.set_value("Card Equipment", eq.name, "rental_direction", DIR_RENTED_IN)
		with self.assertRaises(frappe.ValidationError):
			self._card(eq, [10])

	def test_customer_mismatch_warns_not_blocks(self):
		project_customer = self._customer("-PRJ")
		frappe.db.set_value("Project", self.project, "customer", project_customer)
		eq = self._rented_out()  # equipment customer differs from the project's
		frappe.local.message_log = []
		card = self._card(eq, [10])  # the insert SUCCEEDS (review flag, never a block)
		self.assertTrue(card.name)
		self.assertEqual(card.customer, self.customer)
		messages = " | ".join(str(m.get("message", "")) for m in frappe.get_message_log())
		self.assertIn(project_customer, messages)
		self.assertIn(self.customer, messages)


class TestEquipmentDirectionMatrix(_CustomerCardsBase):
	# ---- rental_direction validate matrix on Card Equipment ----
	def test_owned_cannot_be_rented_in(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(OWNED, direction=DIR_RENTED_IN)

	def test_rented_cannot_be_internal(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(direction=DIR_INTERNAL)

	def test_rented_out_requires_customer(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(OWNED, direction=DIR_RENTED_OUT, customer_rate=1000)

	def test_sub_rental_requires_customer_rate(self):
		with self.assertRaises(frappe.ValidationError):
			self._equipment(direction=DIR_SUBRENTAL, customer=self.customer)

	def test_blank_direction_derives_from_ownership(self):
		self.assertEqual(self._equipment(OWNED).rental_direction, DIR_INTERNAL)
		self.assertEqual(self._equipment().rental_direction, DIR_RENTED_IN)


class TestCustomerRegistry(_CustomerCardsBase):
	# ---- customer registry (Card Equipment Customer) ----
	def test_registry_sync_on_submit_and_cancel(self):
		# recompute_customer counts submitted cards by card_direction + customer
		card = self._card(self._rented_out(), [10, 10], submit=True)
		self.assertTrue(frappe.db.exists("Card Equipment Customer", self.customer))
		fig = _registry_figures("Customer", self.customer)
		self.assertEqual(fig.card_count, 1)
		self.assertEqual(fig.equipment_count, 1)
		self.assertEqual(fig.total_hours, 20.0)
		self.assertEqual(fig.total, 2000.0)  # operational accrual, not a balance
		self.assertTrue(fig.first_month)
		card.cancel()
		fig = _registry_figures("Customer", self.customer)
		self.assertEqual(fig.card_count, 0)
		self.assertEqual(fig.total, 0)

	def test_customers_query_lists_only_customers_with_cards(self):
		from card.api import card_customers_query

		other = self._customer("-NONE")
		self._card(self._rented_out(), [10], submit=True)

		names = [r[0] for r in card_customers_query("Customer", "TEST-CUST", "name", 0, 50, {})]
		self.assertIn(self.customer, names)
		self.assertNotIn(other, names)


class TestDirectionPatches(_CustomerCardsBase):
	# ---- v1.2 F.7 migration patches ----
	def test_backfill_rental_direction(self):
		from card.patches.v1_2.backfill_rental_direction import execute

		# (i) owned with nothing configured -> internal
		eq_owned = self._equipment(OWNED)
		# (ii) rented with a supplier only -> rented-in
		eq_rented = self._equipment()
		# (iii) owned carrying its own customer config -> rented-out
		eq_out = self._equipment(OWNED, customer=self.customer, customer_rate=1000)
		# (iv) E-era: a SUBMITTED card billed a customer but the equipment lost its config
		eq_sub = self._sub_rental()
		card = self._card(eq_sub, [10], submit=True)
		frappe.db.set_value(
			"Card Monthly Card",
			card.name,
			{
				"card_direction": DIR_SUBRENTAL,
				"customer": self.customer,
				"customer_rate_type": "باليوم",
				"customer_rate": 1200,
			},
			update_modified=False,
		)
		frappe.db.set_value(
			"Card Equipment",
			eq_sub.name,
			{"default_customer": None, "customer_rate_type": None, "customer_rate": 0},
			update_modified=False,
		)

		for name in (eq_owned.name, eq_rented.name, eq_out.name, eq_sub.name):
			frappe.db.set_value("Card Equipment", name, "rental_direction", None, update_modified=False)

		execute()

		def direction(name):
			return frappe.db.get_value("Card Equipment", name, "rental_direction")

		self.assertEqual(direction(eq_owned.name), DIR_INTERNAL)
		self.assertEqual(direction(eq_rented.name), DIR_RENTED_IN)
		self.assertEqual(direction(eq_out.name), DIR_RENTED_OUT)
		lifted = frappe.db.get_value(
			"Card Equipment",
			eq_sub.name,
			["rental_direction", "default_customer", "customer_rate_type", "customer_rate"],
			as_dict=True,
		)
		self.assertEqual(lifted.rental_direction, DIR_SUBRENTAL)
		self.assertEqual(lifted.default_customer, self.customer)  # lifted from the card
		self.assertEqual(lifted.customer_rate_type, "باليوم")
		self.assertEqual(flt(lifted.customer_rate), 1200.0)

	def test_rederive_draft_cards(self):
		from card.patches.v1_2.rederive_draft_cards import execute

		eq = self._rented_out()
		draft = self._card(eq, [10])
		submitted = self._card(self._rented_out(), [10], submit=True)
		stale = {
			"card_direction": DIR_INTERNAL,
			"customer": None,
			"customer_rate_type": None,
			"customer_rate": 0,
		}
		frappe.db.set_value("Card Monthly Card", draft.name, stale, update_modified=False)
		frappe.db.set_value("Card Monthly Card", submitted.name, stale, update_modified=False)

		execute()

		fields = ["card_direction", "customer", "customer_rate_type", "customer_rate"]
		d = frappe.db.get_value("Card Monthly Card", draft.name, fields, as_dict=True)
		self.assertEqual(d.card_direction, DIR_RENTED_OUT)  # re-mirrored from its equipment
		self.assertEqual(d.customer, self.customer)
		self.assertEqual(d.customer_rate_type, "باليوم")
		self.assertEqual(flt(d.customer_rate), 1000.0)
		s = frappe.db.get_value("Card Monthly Card", submitted.name, fields, as_dict=True)
		self.assertEqual(s.card_direction, DIR_INTERNAL)  # submitted rows stay untouched
		self.assertFalse(s.customer)
		self.assertFalse(s.customer_rate_type)
		self.assertEqual(flt(s.customer_rate), 0.0)
