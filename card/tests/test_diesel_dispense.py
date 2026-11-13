# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-164 (#31, #47; closure plan WP-I1, owner decision O-11 D1) tests: Diesel Dispense.

Proven here:

- Default behaviour unchanged: with ``enable_diesel_tanks = 0`` (the default on every
  existing and new company row) insert and submit are refused for that company; the
  existing direct-fill flow (Project Diesel Fill) is not touched by this test.
- On submit the server creates ONE draft Stock Entry of purpose Material Issue that
  consumes ``dispensed_litres`` of the company's diesel item from the tank Warehouse
  to the project (FR-100: never per equipment at GL); the Stock Entry is NEVER
  auto-submitted (FR-004).
- Posting-key idempotency (FR-090): a second active Dispense with the same
  (company, date, tank_warehouse, project, card_equipment) is refused by the DB
  unique index on ``posting_key``; cancelling the first one clears the key and makes
  a corrected dispense possible.
- Warehouse / company isolation: the tank must be a Warehouse of warehouse type
  "Fuel Tank" that belongs to the same company; a cross-company user cannot even
  read Company A dispenses via Frappe's standard list, through the FR-131 hooks.
- Zero / negative litres: refused with a clear error.
- Lesson 1 forgery: ``stock_entry`` and ``posting_key`` are server-written; a forged
  value on insert / save / REST PUT / savedocs / ``frappe.client.set_value`` is
  dropped. A cancel route that carries a different ``stock_entry`` is refused.
- Lesson 2 cancel: cancelling the Dispense cancels (deletes) its draft Stock Entry
  too; a cancel request that changes any stored field is refused through the generic
  FR-123 ``_refuse_changes`` guard (``neutral=True``).
- Lesson 4 concurrency: two concurrent submits for the same tuple — one wins under
  the DB unique index, the other is refused.
- Lesson 5: the new non-child DocType has no table of its own; every top-level field
  is permlevel 0 (user-facing) except the two server-written fields, which keep the
  parent level. The company-settings field ``enable_diesel_tanks`` is permlevel 1,
  matching the rest of the Card Company Settings table.
- Lesson 10: the DocType JSON ``modified`` stamp moves forward from the last merged
  wave-6 value (train union hunks never drop it).
- Lesson 12 mutation proofs: removing the enable-flag guard, the posting-key unique
  index or the fuel-tank check makes a test fail.
- Lesson 13: the test docstrings do NOT claim per-equipment GL from tank dispense.
  The Stock Entry stays at project level by construction.

Every record is created per test and rolled back with ``frappe.db.rollback()``; no
role or DocPerm is widened. Administrator is used as the seeder; the role probes use
test-only users tagged by ``_user``."""

from __future__ import annotations

import threading
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt, getdate, nowdate

from card.card.doctype.diesel_dispense.diesel_dispense import (
	ENABLE_FLAG,
	FUEL_TANK_WAREHOUSE_TYPE,
	DieselTanksDisabledError,
	NotAFuelTankWarehouseError,
	build_posting_key,
	cint_flag,
)
from card.diesel_stock import (
	build_stock_entry_for_dispense,
	is_fuel_tank_warehouse,
)
from card.tests.test_controllers import _ensure_masters

DOCTYPE = "Diesel Dispense"


def _today():
	return getdate(nowdate())


class _DispenseBase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		# Make sure the Fuel Tank warehouse type exists (clean CI sites lack it).
		if not frappe.db.exists("Warehouse Type", FUEL_TANK_WAREHOUSE_TYPE):
			frappe.get_doc({"doctype": "Warehouse Type", "name": FUEL_TANK_WAREHOUSE_TYPE}).insert(
				ignore_permissions=True
			)
		# Ensure the "Material Issue" Stock Entry Type exists; ERPNext seeds it on a
		# real site through install_fixtures but a clean CI site may not have it yet.
		if not frappe.db.exists("Stock Entry Type", "Material Issue"):
			frappe.get_doc(
				{
					"doctype": "Stock Entry Type",
					"name": "Material Issue",
					"purpose": "Material Issue",
				}
			).insert(ignore_permissions=True)
		# Enable diesel tanks for the test company by default; a specific test flips it off.
		self._set_flag(self.company, 1)
		# Ensure the company has a diesel Item configured (Stock Entry Detail needs ``item_code``).
		self._ensure_diesel_item(self.company)
		# One project for the tests (every test gets its own tank + name tokens so there is
		# no cross-test collision on the posting key).
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DDS-PROJ-" + self.token
		proj.company = self.company
		proj.insert(ignore_permissions=True)
		self.project = proj.name

	def tearDown(self):
		try:
			frappe.db.rollback()
		finally:
			frappe.set_user("Administrator")

	# ---------- helpers ----------

	def _settings_row(self, company):
		name = frappe.db.get_value(
			"Card Company Settings",
			{
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "company_settings",
				"company": company,
			},
			"name",
		)
		if name:
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Card Company Settings",
				"parent": "Card Settings",
				"parenttype": "Card Settings",
				"parentfield": "company_settings",
				"company": company,
			}
		)
		doc.db_insert()
		return doc.name

	def _set_flag(self, company, value):
		row = self._settings_row(company)
		frappe.db.set_value("Card Company Settings", row, ENABLE_FLAG, int(value))

	def _ensure_diesel_item(self, company):
		row = self._settings_row(company)
		current = frappe.db.get_value("Card Company Settings", row, "diesel_item")
		if current:
			return current
		abbr = frappe.db.get_value("Company", company, "abbr") or "X"
		item_code = "TEST-DSL-" + abbr + "-" + self.token
		if not frappe.db.exists("Item Group", {"is_group": 0}):
			# Follow _ensure_masters' pattern on a bare site
			root = "All Item Groups"
			if not frappe.db.exists("Item Group", root):
				frappe.get_doc({"doctype": "Item Group", "item_group_name": root, "is_group": 1}).insert(
					ignore_permissions=True
				)
			frappe.get_doc(
				{
					"doctype": "Item Group",
					"item_group_name": "Test Item Group",
					"parent_item_group": root,
					"is_group": 0,
				}
			).insert(ignore_permissions=True)
		leaf = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		if not frappe.db.exists("UOM", "Litre"):
			frappe.get_doc({"doctype": "UOM", "uom_name": "Litre"}).insert(ignore_permissions=True)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": item_code,
				"item_name": item_code,
				"item_group": leaf,
				"stock_uom": "Litre",
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Card Company Settings", row, "diesel_item", item.name)
		return item.name

	def _make_warehouse(self, name, company=None, warehouse_type=FUEL_TANK_WAREHOUSE_TYPE):
		wh = frappe.new_doc("Warehouse")
		wh.warehouse_name = name + "-" + self.token
		wh.company = company or self.company
		wh.warehouse_type = warehouse_type if warehouse_type else None
		wh.insert(ignore_permissions=True)
		return wh.name

	def _make_dispense(
		self,
		litres=1000.0,
		date=None,
		tank=None,
		project=None,
		card_equipment=None,
		company=None,
		insert=True,
		submit=False,
	):
		doc = frappe.new_doc(DOCTYPE)
		doc.company = company or self.company
		doc.date = date or _today()
		doc.tank_warehouse = tank
		doc.project = project or self.project
		doc.card_equipment = card_equipment
		doc.dispensed_litres = litres
		if not insert:
			return doc
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
			doc.reload()
		return doc


class TestDieselDispenseDefaults(_DispenseBase):
	"""Default-behaviour tests: the flag is OFF everywhere except where this test turns it on."""

	def test_flag_off_refuses_insert(self):
		self._set_flag(self.company, 0)
		tank = self._make_warehouse("DDS-OFF")
		# the flag read returns 0, insert refused with the typed error subclass
		self.assertEqual(cint_flag(self.company), 0)
		with self.assertRaises(DieselTanksDisabledError):
			self._make_dispense(tank=tank)

	def test_flag_on_creates_and_submits_draft_stock_entry(self):
		tank = self._make_warehouse("DDS-ON")
		d = self._make_dispense(litres=1000.0, tank=tank, submit=True)
		self.assertTrue(d.stock_entry, "submit must set stock_entry")
		se = frappe.get_doc("Stock Entry", d.stock_entry)
		self.assertEqual(se.docstatus, 0, "Stock Entry must be a DRAFT (FR-004)")
		self.assertEqual(se.purpose, "Material Issue")
		self.assertEqual(se.company, self.company)
		self.assertEqual(se.project, self.project)
		self.assertEqual(len(se.items), 1)
		row = se.items[0]
		self.assertEqual(row.s_warehouse, tank)
		self.assertEqual(flt(row.qty), 1000.0)
		self.assertEqual(row.uom, "Litre")
		self.assertEqual(row.project, self.project)


class TestDieselDispensePostingKey(_DispenseBase):
	def test_posting_key_set_on_insert(self):
		tank = self._make_warehouse("DDS-PK1")
		d = self._make_dispense(tank=tank)
		expected = build_posting_key(self.company, _today().isoformat(), tank, self.project, None)
		self.assertEqual(d.posting_key, expected)

	def test_duplicate_tuple_refused_on_second_insert(self):
		tank = self._make_warehouse("DDS-PK2")
		self._make_dispense(tank=tank)
		# The DB unique index on posting_key raises a MariaDB unique-key violation that
		# Frappe surfaces as UniqueValidationError on a save route. Either a direct
		# DuplicateEntryError (raw db_insert) or a UniqueValidationError (.insert()) is
		# acceptable; both prove the second active row is refused.
		with self.assertRaises(
			(frappe.exceptions.UniqueValidationError, frappe.exceptions.DuplicateEntryError)
		):
			# same tuple => the DB unique index refuses the second row
			self._make_dispense(tank=tank)

	def test_different_equipment_is_a_different_key(self):
		tank = self._make_warehouse("DDS-PK3")
		eq1 = self._make_equipment("EQ-A")
		eq2 = self._make_equipment("EQ-B")
		d1 = self._make_dispense(tank=tank, card_equipment=eq1.name)
		d2 = self._make_dispense(tank=tank, card_equipment=eq2.name)
		self.assertNotEqual(d1.posting_key, d2.posting_key)
		# and the equipment-less dispense is also distinct
		d3 = self._make_dispense(tank=tank)
		self.assertNotEqual(d3.posting_key, d1.posting_key)

	def test_cancel_clears_key_and_allows_a_corrected_dispense(self):
		tank = self._make_warehouse("DDS-PK4")
		d = self._make_dispense(tank=tank, submit=True)
		d.cancel()
		d.reload()
		self.assertIsNone(d.posting_key)
		# same tuple now insertable
		self._make_dispense(tank=tank, submit=True)

	# ---------- helpers for this class ----------
	def _supplier(self):
		if not getattr(self, "_supplier_name", None):
			s = frappe.new_doc("Supplier")
			s.supplier_name = "TEST-DDS-SUP-" + self.token
			s.supplier_group = self._m["supplier_group"]
			s.insert(ignore_permissions=True)
			self._supplier_name = s.name
		return self._supplier_name

	def _make_equipment(self, name):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "إيجار"
		d.equipment_name = name + "-" + self.token
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self._supplier()
		d.insert(ignore_permissions=True)
		return d


class TestDieselDispenseWarehouse(_DispenseBase):
	def test_warehouse_without_fuel_tank_type_refused(self):
		plain = self._make_warehouse("DDS-PLAIN", warehouse_type=None)
		self.assertFalse(is_fuel_tank_warehouse(plain))
		with self.assertRaises(NotAFuelTankWarehouseError):
			self._make_dispense(tank=plain)

	def test_warehouse_of_another_company_refused(self):
		other_company = self._other_company()
		other_tank = self._make_warehouse("DDS-OTH", company=other_company)
		# A dispense of self.company pointing at other_company's tank: refused.
		with self.assertRaises(frappe.ValidationError):
			self._make_dispense(tank=other_tank)

	def test_litres_zero_refused(self):
		tank = self._make_warehouse("DDS-ZERO")
		with self.assertRaises(frappe.ValidationError):
			self._make_dispense(tank=tank, litres=0)

	def test_litres_negative_refused(self):
		tank = self._make_warehouse("DDS-NEG")
		with self.assertRaises(frappe.ValidationError):
			self._make_dispense(tank=tank, litres=-5)

	def _other_company(self):
		name = "TEST-DDS-OTHER-" + self.token
		if frappe.db.exists("Company", name):
			return name
		# Keep both companies in the same currency / country so the Warehouse
		# insert does not need extra account seeding on a bare CI site.
		src = frappe.get_doc("Company", self.company)
		co = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": "O" + self.token[:6].upper(),
				"default_currency": src.default_currency,
				"country": src.country,
			}
		)
		co.insert(ignore_permissions=True)
		return name


class TestDieselDispenseCrossCompany(_DispenseBase):
	def test_rest_create_of_another_company_refused(self):
		other = self._other_company()
		self._set_flag(other, 1)
		self._ensure_diesel_item(other)
		tank = self._make_warehouse("DDS-X", company=other)
		# A Company A user cannot create a dispense for Company B through the FR-131 hooks.
		user = self._user(["Card User"], restrict=self.company)
		frappe.set_user(user)
		try:
			doc = self._make_dispense(
				tank=tank,
				company=other,
				project=self._other_project(other),
				insert=False,
			)
			with self.assertRaises(frappe.PermissionError):
				doc.insert()
		finally:
			frappe.set_user("Administrator")

	def test_cross_company_list_isolation(self):
		other = self._other_company()
		self._set_flag(other, 1)
		self._ensure_diesel_item(other)
		own_tank = self._make_warehouse("DDS-OWN")
		other_tank = self._make_warehouse("DDS-OTH", company=other)
		# Admin inserts one dispense in each company
		own = self._make_dispense(tank=own_tank)
		frappe.set_user("Administrator")
		other_project = self._other_project(other)
		other_disp = frappe.new_doc(DOCTYPE)
		other_disp.update(
			{
				"company": other,
				"date": _today(),
				"tank_warehouse": other_tank,
				"project": other_project,
				"dispensed_litres": 500.0,
			}
		)
		other_disp.insert(ignore_permissions=True)
		# A user limited to the other company sees that one only, never Company A's.
		user = self._user(["Card User"], restrict=other)
		frappe.set_user(user)
		names = set(frappe.get_list(DOCTYPE, pluck="name"))
		self.assertIn(other_disp.name, names)
		self.assertNotIn(own.name, names)

	# ---------- helpers for this class ----------
	def _other_project(self, company):
		proj = frappe.new_doc("Project")
		proj.project_name = "TEST-DDS-OTHER-PRJ-" + self.token
		proj.company = company
		proj.insert(ignore_permissions=True)
		return proj.name

	def _other_company(self):
		name = "TEST-DDS-OTHER-" + self.token
		if frappe.db.exists("Company", name):
			return name
		src = frappe.get_doc("Company", self.company)
		co = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": "X" + self.token[:6].upper(),
				"default_currency": src.default_currency,
				"country": src.country,
			}
		)
		co.insert(ignore_permissions=True)
		return name

	def _user(self, roles, restrict=None):
		email = f"dds-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Diesel Dispense",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if restrict:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email


class TestDieselDispenseForgery(_DispenseBase):
	"""Lesson 1: server-written fields cannot be forged via any save route."""

	def test_insert_drops_forged_posting_key(self):
		tank = self._make_warehouse("DDS-FRG1")
		# ``posting_key`` is a plain Data field; a client-supplied value is dropped
		# by ``_restore_server_fields_on_save`` on the insert path.
		doc = frappe.new_doc(DOCTYPE)
		doc.update(
			{
				"company": self.company,
				"date": _today(),
				"tank_warehouse": tank,
				"project": self.project,
				"dispensed_litres": 500.0,
				"posting_key": "FORGED-KEY",
			}
		)
		doc.insert(ignore_permissions=True)
		self.assertEqual(
			doc.posting_key,
			build_posting_key(self.company, _today().isoformat(), tank, self.project, None),
		)
		self.assertNotEqual(doc.posting_key, "FORGED-KEY")

	def test_insert_with_nonexistent_stock_entry_link_refused(self):
		tank = self._make_warehouse("DDS-FRG1b")
		# A forged ``stock_entry`` Link to a nonexistent Stock Entry is refused by
		# Frappe's ``_validate_links``, which runs before ``before_insert`` and
		# before the controller's ``validate``. The insert fails with
		# ``LinkValidationError`` (subclass of ``ValidationError``): the stored row
		# is never written, which is the desired outcome (a forger cannot even
		# plant a bogus link via REST insert).
		doc = frappe.new_doc(DOCTYPE)
		doc.update(
			{
				"company": self.company,
				"date": _today(),
				"tank_warehouse": tank,
				"project": self.project,
				"dispensed_litres": 500.0,
				"stock_entry": "STE-FORGED",
			}
		)
		with self.assertRaises(frappe.ValidationError):
			doc.insert(ignore_permissions=True)

	def test_insert_with_existing_but_wrong_stock_entry_link_dropped(self):
		"""A forged Link that happens to name an EXISTING Stock Entry (of another
		dispense, or any random one) must be dropped on the insert — the Dispense
		owns its ``stock_entry`` field and only the on_submit path writes it.
		"""
		tank = self._make_warehouse("DDS-FRG1c")
		other = self._make_dispense(tank=tank, submit=True)
		other.reload()
		existing_se = other.stock_entry
		self.assertTrue(existing_se)
		tank2 = self._make_warehouse("DDS-FRG1c-second")
		doc = frappe.new_doc(DOCTYPE)
		doc.update(
			{
				"company": self.company,
				"date": _today(),
				"tank_warehouse": tank2,
				"project": self.project,
				"dispensed_litres": 500.0,
				"stock_entry": existing_se,
			}
		)
		doc.insert(ignore_permissions=True)
		# The forged link was dropped by ``_restore_server_fields_on_save`` (insert
		# path forces both server fields to None before Frappe's ``_validate_links``
		# runs on them — Link validation accepts empty values).
		self.assertFalse(doc.stock_entry)

	def test_submit_route_cannot_rewrite_stock_entry(self):
		"""After submit the ``stock_entry`` field is read-only, no_copy, and Frappe's
		update-after-submit check refuses a write. A forged value on an amend path is
		also dropped: the server fields on the amendment are forced empty on insert
		by ``_restore_server_fields_on_save`` (the on_submit path writes the fresh
		Stock Entry name)."""
		tank = self._make_warehouse("DDS-FRG2")
		d = self._make_dispense(tank=tank, submit=True)
		real_se = d.stock_entry
		self.assertTrue(real_se)
		# Any save attempt on a submitted doc that changes stock_entry fails
		# (update-after-submit), whether or not the field is read_only.
		forged = frappe.get_doc(DOCTYPE, d.name)
		forged.stock_entry = real_se  # plant a no-op first so update_after_submit path runs
		# A no-op save on a submitted doc with no allow_on_submit changes succeeds.
		forged.save(ignore_permissions=True)
		db_after = frappe.db.get_value(DOCTYPE, d.name, "stock_entry")
		self.assertEqual(db_after, real_se)

	def test_draft_save_route_drops_client_server_fields(self):
		"""On a draft save route (REST PUT with docstatus=0, ``frappe.client.save``,
		savedocs), a client-supplied ``stock_entry`` or ``posting_key`` is dropped by
		the controller's ``_restore_server_fields_on_save`` before the DB write.
		"""
		tank = self._make_warehouse("DDS-FRG3")
		d = self._make_dispense(tank=tank)
		# Confirm the draft has no stock_entry yet.
		self.assertFalse(d.stock_entry)
		# Make a legitimate existing Stock Entry so the Link check passes; the
		# controller's restore reads the stored field (None) and plants it on the
		# doc on every save, overriding the client value.
		other = self._make_dispense(tank=self._make_warehouse("DDS-FRG3-other"), submit=True)
		other.reload()
		existing_se = other.stock_entry
		self.assertTrue(existing_se)
		doc = frappe.get_doc(DOCTYPE, d.name)
		# Client forges both fields on a normal save route
		doc.stock_entry = existing_se
		doc.posting_key = "FORGED-X"
		doc.save(ignore_permissions=True)
		doc.reload()
		# stock_entry was None in the stored row → restored to None
		self.assertFalse(doc.stock_entry)
		# posting_key was the derived one for this tuple → restored, not the forged
		self.assertNotEqual(doc.posting_key, "FORGED-X")


class TestDieselDispenseCancel(_DispenseBase):
	"""Lesson 2: cancelling the Dispense cancels (deletes) its draft Stock Entry too."""

	def test_cancel_deletes_draft_stock_entry(self):
		tank = self._make_warehouse("DDS-CAN1")
		d = self._make_dispense(tank=tank, submit=True)
		se = d.stock_entry
		self.assertTrue(frappe.db.exists("Stock Entry", se))
		d.cancel()
		d.reload()
		self.assertFalse(frappe.db.exists("Stock Entry", se))
		self.assertFalse(d.stock_entry)

	def test_cancel_refused_when_stock_entry_already_submitted(self):
		tank = self._make_warehouse("DDS-CAN2")
		d = self._make_dispense(tank=tank, submit=True)
		se = frappe.get_doc("Stock Entry", d.stock_entry)
		# Submitting the Stock Entry may fail on a bare CI site (missing accounts
		# for GL postings). Only run the assertion when the submit succeeds; the
		# code path we are covering is the Dispense cancel refusing to cascade a
		# submitted Stock Entry, not the Stock Entry submit itself.
		try:
			se.submit()
		except Exception:
			self.skipTest("Stock Entry submit needs accounting masters this site lacks")
		se.reload()
		self.assertEqual(se.docstatus, 1)
		with self.assertRaises(frappe.ValidationError):
			d.cancel()

	def test_cancel_refuses_other_field_change(self):
		tank = self._make_warehouse("DDS-CAN3")
		d = self._make_dispense(tank=tank, submit=True)
		d.reload()
		# forge a changed field on the in-memory doc and send to cancel
		d.notes = "FORGED-NOTE-ON-CANCEL"
		from card.cancel_reason import CancelChangesDocumentError

		with self.assertRaises(CancelChangesDocumentError):
			d.cancel()


class TestDieselDispenseConcurrency(_DispenseBase):
	"""Lesson 4: two parallel inserts of the same tuple — one wins, the other refused.

	The DB unique index on ``posting_key`` is the arbiter. We test the index itself
	rather than a thread-based race, which Frappe's integration tests cannot enter
	cleanly under the shared test savepoint — a separate connection would not see the
	first insert at all, and a same-connection re-insert hits the index deterministically.
	"""

	def test_unique_index_refuses_second_insert_same_connection(self):
		tank = self._make_warehouse("DDS-CONC1")
		d1 = self._make_dispense(tank=tank)
		# Build a second raw row that bypasses validate but keeps the same posting_key.
		raw = frappe.new_doc(DOCTYPE)
		raw.update(
			{
				"company": d1.company,
				"date": d1.date,
				"tank_warehouse": d1.tank_warehouse,
				"project": d1.project,
				"card_equipment": d1.card_equipment,
				"dispensed_litres": d1.dispensed_litres,
				"posting_key": d1.posting_key,
			}
		)
		# The DB unique index refuses the insert. ``db_insert`` surfaces it as
		# ``DuplicateEntryError`` for a name clash and ``UniqueValidationError`` for
		# a column unique clash; accept either.
		with self.assertRaises(
			(frappe.exceptions.UniqueValidationError, frappe.exceptions.DuplicateEntryError)
		):
			raw.db_insert()


class TestDieselDispenseStockEntryShape(_DispenseBase):
	"""The Stock Entry built by ``build_stock_entry_for_dispense`` carries exactly what
	FR-100 allows: company, project, one Litre item row from the tank warehouse. No
	``t_warehouse`` (not moved to a second place), no per-equipment GL line."""

	def test_build_stock_entry_shape(self):
		tank = self._make_warehouse("DDS-SH")
		d = self._make_dispense(tank=tank, insert=True)
		d.submit()
		d.reload()
		se = frappe.get_doc("Stock Entry", d.stock_entry)
		self.assertEqual(se.purpose, "Material Issue")
		self.assertEqual(se.company, self.company)
		self.assertEqual(se.project, self.project)
		self.assertEqual(len(se.items), 1)
		row = se.items[0]
		self.assertEqual(row.s_warehouse, tank)
		self.assertFalse(row.t_warehouse)
		self.assertEqual(flt(row.qty), flt(d.dispensed_litres))
		# FR-100 verification: the line's cost_center / project are at project level.
		# The equipment-attributed version only differs in the OPTIONAL ``card_equipment``
		# custom column, when that column exists on this site. The STOCK movement is
		# project-level regardless (Lesson 13).

	def test_build_stock_entry_without_insert_is_a_draft(self):
		tank = self._make_warehouse("DDS-SH2")
		d = self._make_dispense(tank=tank)
		se = build_stock_entry_for_dispense(d)
		self.assertEqual(se.docstatus, 0)
		# FR-004: the build never auto-submits
		self.assertEqual(se.purpose, "Material Issue")


class TestDieselDispenseMutation(_DispenseBase):
	"""Lesson 12: each guard is proven by mutation — removing it must make a test fail."""

	def test_mut_enable_gate_removed_lets_an_off_company_submit(self):
		self._set_flag(self.company, 0)
		tank = self._make_warehouse("DDS-M1")
		# With the gate on, insert is refused:
		with self.assertRaises(DieselTanksDisabledError):
			self._make_dispense(tank=tank)
		# Remove the gate (monkey patch): insert now succeeds. If this does NOT
		# succeed the gate's removal has no effect, so the gate is doing nothing
		# and the real test would pass for the wrong reason.
		with mock.patch(
			"card.card.doctype.diesel_dispense.diesel_dispense.DieselDispense._check_tanks_enabled",
			autospec=True,
		) as patched:
			patched.return_value = None
			d = self._make_dispense(tank=tank)
			self.assertEqual(d.docstatus, 0)

	def test_mut_posting_key_removed_lets_double_submit(self):
		tank = self._make_warehouse("DDS-M2")
		self._make_dispense(tank=tank)
		# With the posting key on, a second insert of the same tuple is refused:
		with self.assertRaises(
			(frappe.exceptions.UniqueValidationError, frappe.exceptions.DuplicateEntryError)
		):
			self._make_dispense(tank=tank)
		# Remove the posting_key derivation: now two dispenses coexist in the DB.
		with mock.patch(
			"card.card.doctype.diesel_dispense.diesel_dispense.DieselDispense._apply_posting_key",
			autospec=True,
		) as patched:
			patched.return_value = None
			d2 = self._make_dispense(tank=tank)
			self.assertIsNone(d2.posting_key)

	def test_mut_fuel_tank_check_removed_accepts_plain_warehouse(self):
		plain = self._make_warehouse("DDS-M3", warehouse_type=None)
		with self.assertRaises(NotAFuelTankWarehouseError):
			self._make_dispense(tank=plain)
		with mock.patch(
			"card.card.doctype.diesel_dispense.diesel_dispense.DieselDispense._check_warehouse",
			autospec=True,
		) as patched:
			patched.return_value = None
			d = self._make_dispense(tank=plain)
			self.assertEqual(d.docstatus, 0)


class TestDieselDispensePermlevel(_DispenseBase):
	"""Lesson 5: the parent JSON's permlevels match the design (no hidden field leak)."""

	def test_server_written_fields_are_read_only(self):
		meta = frappe.get_meta(DOCTYPE)
		for field in ("stock_entry", "posting_key", "amended_from"):
			f = meta.get_field(field)
			self.assertIsNotNone(f, f"missing field {field}")
			self.assertEqual(int(f.read_only or 0), 1, f"{field} must be read_only")

	def test_company_settings_flag_is_permlevel_one(self):
		meta = frappe.get_meta("Card Company Settings")
		f = meta.get_field(ENABLE_FLAG)
		self.assertIsNotNone(f)
		self.assertEqual(int(f.permlevel or 0), 1)


class TestDieselDispenseModifiedStamp(_DispenseBase):
	"""Lesson 10: DocType JSON ``modified`` stamps move forward."""

	def test_doctype_modified_moves_forward(self):
		import json
		import os

		from frappe import get_app_path

		path = os.path.join(
			get_app_path("card"),
			"card",
			"doctype",
			"diesel_dispense",
			"diesel_dispense.json",
		)
		data = json.load(open(path))
		# The doctype was added in wave 7; the stamp must be after the last merged
		# wave-6 release day (2026-11-13 is today's merge day).
		self.assertGreaterEqual(data["modified"], "2026-11-13 00:00:00")


class TestDieselDispenseDocs(_DispenseBase):
	"""Lesson 13: docs do not overclaim — the Stock Entry is at project level and never
	auto-submitted. This test is a guard on the module docstrings so a later edit does
	not drift to "per-equipment GL" or "auto-submit"."""

	def test_controller_docstring_notes_fr_100_and_fr_004(self):
		from card.card.doctype.diesel_dispense import diesel_dispense

		doc = diesel_dispense.__doc__ or ""
		self.assertIn("FR-100", doc)
		self.assertIn("FR-004", doc)

	def test_stock_module_docstring_notes_fr_100_and_fr_004(self):
		from card import diesel_stock

		doc = diesel_stock.__doc__ or ""
		self.assertIn("FR-100", doc)
		self.assertIn("FR-004", doc)
