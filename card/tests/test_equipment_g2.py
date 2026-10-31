# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#56 (G2): Card Equipment fields that drive company, accounting and the
assignment control are Card Manager-only and validated server-side; the
location fields follow the assignment in force today; a unit's card days are
checked on the unit's own assignments too. Desk saves, frappe.client and the
REST resource handler (frappe.api.v1.update_doc, the code behind
PUT /api/resource) are exercised for Card User and Card Manager. All data is
per-test and rolled back."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.api.v1 import update_doc
from frappe.client import set_value
from frappe.utils import add_days, getdate, nowdate

from card import transfer
from card.dimension import ASSET_LINK_FIELD
from card.tests.test_customer import _CustomerCardsBase
from card.tests.transport_parties import company_paid

OWNED = "ملك"
# permlevel-1 scalar fields and a value Card User might try to write
PROTECTED_SCALARS = {
	"is_unit": 1,
	"is_unit_component": 1,
	"daily_diesel_consumption": 123,
	"expected_consumption": 9,
}


class _G2Base(_CustomerCardsBase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()
		super().tearDown()

	# ---- users and write paths ----
	def _login(self, roles, companies=()):
		email = f"g2-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "G2",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		for company in companies:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": company,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.set_user(email)
		return email

	def _try(self, fn, *args):
		try:
			fn(*args)
			return True
		except (frappe.PermissionError, frappe.ValidationError):
			return False

	def _via_save(self, name, values):
		doc = frappe.get_doc("Card Equipment", name)
		doc.update(values)
		return self._try(doc.save)

	def _via_client(self, name, values):
		return self._try(set_value, "Card Equipment", name, values)

	def _via_rest(self, name, values):
		frappe.local.form_dict = frappe._dict(data=json.dumps(values))
		try:
			return self._try(update_doc, "Card Equipment", name)
		finally:
			frappe.local.form_dict = frappe._dict()

	PATHS = ("_via_save", "_via_client", "_via_rest")

	# ---- masters ----
	def _other_company(self):
		name = "TEST-G2-CO-" + self.token
		if not frappe.db.exists("Company", name):
			co = frappe.new_doc("Company")
			co.update(
				{
					"company_name": name,
					"abbr": "G" + self.token[:6].upper(),
					"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"country": frappe.db.get_value("Company", self.company, "country"),
				}
			)
			co.name = name
			co.db_insert()
		return name

	def _owned(self, components=None, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = OWNED
		d.equipment_name = "TEST-G2-EQ-" + frappe.generate_hash(length=6)
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.update(kw)
		for row in components or []:
			d.append("components", row)
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _assign(self, equipment, project, start, end=None):
		a = frappe.new_doc("Card Equipment Assignment")
		a.equipment = equipment
		a.project = project
		a.from_date = start
		a.to_date = end
		a.insert(ignore_permissions=True)
		return a

	def _asset(self, company=None, docstatus=1):
		item = frappe.db.get_value("Item", {"is_fixed_asset": 1, "disabled": 0}, "name")
		category = frappe.db.get_value("Asset Category", {}, "name")
		location = frappe.db.get_value("Location", {}, "name")
		if not (item and category and location):
			self.skipTest("Site has no fixed-asset Item / Asset Category / Location to build an Asset")
		try:
			asset = frappe.get_doc(
				{
					"doctype": "Asset",
					"asset_name": "TEST-G2-ASSET-" + frappe.generate_hash(length=8),
					"item_code": item,
					"asset_category": category,
					"location": location,
					"company": self.company,
					"is_existing_asset": 1,
					"gross_purchase_amount": 1000,
					"net_purchase_amount": 1000,
					"purchase_date": nowdate(),
					"available_for_use_date": nowdate(),
				}
			).insert(ignore_permissions=True)
		except Exception as e:
			if isinstance(e, unittest.SkipTest):
				raise
			self.skipTest("Cannot create an Asset in this test environment: %s" % e)
		values = {"docstatus": docstatus}
		if company:
			values["company"] = company
		frappe.db.set_value("Asset", asset.name, values)
		return asset.name

	def _legacy_location(self, eq, project, date=None):
		"""A pre-#56 row: location typed by hand (written directly, as no save can)."""
		frappe.db.set_value("Card Equipment", eq.name, {"current_project": project, "assignment_date": date})

	def _loc(self, eq):
		return frappe.db.get_value(
			"Card Equipment", eq.name, ["current_project", "assignment_date"], as_dict=True
		)

	def _comments(self, eq):
		return frappe.get_all(
			"Comment",
			filters={
				"reference_doctype": "Card Equipment",
				"reference_name": eq.name,
				"comment_type": "Info",
			},
			pluck="content",
		)

	def _enable_daily(self, on):
		frappe.db.set_single_value("Card Settings", "sync_equipment_location_daily", 1 if on else 0)

	def _project(self, label):
		p = frappe.new_doc("Project")
		p.project_name = "TEST-G2-%s-%s" % (label, self.token)
		p.company = self.company
		p.insert(ignore_permissions=True)
		return p.name

	def _days_from(self, today_offset):
		return str(add_days(getdate(nowdate()), today_offset))


class TestG2FieldProtection(_G2Base):
	def _snapshot(self, eq, fields):
		return frappe.db.get_value("Card Equipment", eq.name, fields, as_dict=True)

	def test_card_user_cannot_change_protected_fields_on_any_path(self):
		eq = self._owned()
		changes = dict(PROTECTED_SCALARS, company=self._other_company())
		before = self._snapshot(eq, list(changes))
		self._login(["Card User"])
		for path in self.PATHS:
			for field, value in changes.items():
				getattr(self, path)(eq.name, {field: value})
		frappe.set_user("Administrator")
		self.assertEqual(self._snapshot(eq, list(changes)), before)

	def test_card_user_cannot_link_a_valid_asset(self):
		asset = self._asset()
		eq = self._owned()
		self._login(["Card User", "Accounts User"])  # may read the Asset, still may not link it
		for path in self.PATHS:
			getattr(self, path)(eq.name, {ASSET_LINK_FIELD: asset})
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value("Card Equipment", eq.name, ASSET_LINK_FIELD))

	def test_card_user_cannot_change_a_valid_units_components(self):
		a, b = self._owned(), self._owned()
		unit = self._owned(is_unit=1, components=[{"component": a.name}])
		row = frappe.get_all("Card Equipment Component", filters={"parent": unit.name}, pluck="name")[0]
		self._login(["Card User"])
		for path in self.PATHS:
			getattr(self, path)(unit.name, {"components": [{"component": b.name}]})
		# child-table REST: the row is saved through its parent
		self._try(set_value, "Card Equipment Component", row, "component", b.name)
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.get_all("Card Equipment Component", filters={"parent": unit.name}, pluck="component"),
			[a.name],
		)

	def test_card_user_still_edits_operational_fields_on_every_path(self):
		eq = self._owned()
		user = self._login(["Card User"])
		for i, path in enumerate(self.PATHS):
			self.assertTrue(getattr(self, path)(eq.name, {"plate_no": f"G2-{i}", "brand": f"B{i}"}), path)
			frappe.set_user("Administrator")
			self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "plate_no"), f"G2-{i}")
			frappe.set_user(user)

	def test_card_manager_writes_protected_fields_on_every_path(self):
		eq = self._owned()
		user = self._login(["Card Manager"])
		for i, path in enumerate(self.PATHS):
			values = {"daily_diesel_consumption": 70 + i, "expected_consumption": i + 1}
			self.assertTrue(getattr(self, path)(eq.name, values), path)
			frappe.set_user("Administrator")
			self.assertEqual(
				frappe.db.get_value("Card Equipment", eq.name, "daily_diesel_consumption"), 70 + i
			)
			frappe.set_user(user)

	def test_location_fields_ignore_writes_from_every_role_and_path(self):
		eq = self._owned()
		self._assign(eq.name, self.project, self._days_from(-10))
		fields = ["current_project", "assignment_date"]
		stored = self._snapshot(eq, fields)
		other = frappe.new_doc("Project")
		other.project_name = "TEST-G2-OTHER-" + self.token
		other.company = self.company
		other.insert(ignore_permissions=True)
		for roles in (["Card User"], ["Card Manager"], ["System Manager"]):
			self._login(roles)
			for path in self.PATHS:
				getattr(self, path)(eq.name, {"current_project": other.name, "assignment_date": "2020-01-01"})
			frappe.set_user("Administrator")
		self.assertEqual(self._snapshot(eq, fields), stored)

	def test_location_fields_cannot_be_set_on_insert(self):
		eq = self._owned(current_project=self.project, assignment_date="2020-01-01")
		self.assertEqual(
			self._snapshot(eq, ["current_project", "assignment_date"]),
			frappe._dict(current_project=None, assignment_date=None),
		)


class TestG2CompanyAndAsset(_G2Base):
	def test_company_cannot_change_once_the_equipment_is_used(self):
		eq = self._owned()
		self._card(eq, [8], submit=False)
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.company = self._other_company()
		with self.assertRaisesRegex(frappe.ValidationError, "company cannot change"):
			doc.save(ignore_permissions=True)

	def test_company_change_allowed_on_an_unused_equipment(self):
		eq = self._owned()
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.company = self._other_company()
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "company"), doc.company)

	def test_company_change_rechecks_components_and_asset(self):
		a = self._owned()
		unit = self._owned(is_unit=1, components=[{"component": a.name}])
		doc = frappe.get_doc("Card Equipment", unit.name)
		doc.company = self._other_company()
		with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
			doc.save(ignore_permissions=True)
		asset = self._asset()
		eq = self._owned(**{ASSET_LINK_FIELD: asset})
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.company = self._other_company()
		with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
			doc.save(ignore_permissions=True)

	def test_restricted_card_manager_cannot_move_equipment_to_another_company(self):
		eq = self._owned()
		other = self._other_company()
		self._login(["Card Manager"], companies=[self.company])
		for path in self.PATHS:
			getattr(self, path)(eq.name, {"company": other})
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "company"), self.company)

	def test_asset_of_another_company_is_refused(self):
		asset = self._asset(company=self._other_company())
		with self.assertRaisesRegex(frappe.ValidationError, "belongs to company"):
			self._owned(**{ASSET_LINK_FIELD: asset})

	def test_cancelled_asset_is_refused(self):
		asset = self._asset(docstatus=2)
		with self.assertRaisesRegex(frappe.ValidationError, "cancelled"):
			self._owned(**{ASSET_LINK_FIELD: asset})

	def test_card_manager_without_asset_read_cannot_link(self):
		asset = self._asset()
		eq = self._owned()
		self._login(["Card Manager"])
		self.assertFalse(frappe.has_permission("Asset", "read", asset))
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.set(ASSET_LINK_FIELD, asset)
		with self.assertRaises(frappe.PermissionError):
			doc.save()

	def test_card_manager_with_asset_read_links_and_syncs(self):
		asset = self._asset()
		eq = self._owned()
		self._login(["Card Manager", "Accounts User"])
		self.assertTrue(frappe.has_permission("Asset", "read", asset))
		self.assertTrue(self._via_rest(eq.name, {ASSET_LINK_FIELD: asset}))
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, ASSET_LINK_FIELD), asset)
		from card.dimension import DIMENSION_FIELD

		if frappe.get_meta("Asset").has_field(DIMENSION_FIELD):
			self.assertEqual(frappe.db.get_value("Asset", asset, DIMENSION_FIELD), eq.name)

	def test_legacy_cross_company_asset_link_does_not_block_other_edits(self):
		asset = self._asset()
		eq = self._owned(**{ASSET_LINK_FIELD: asset})
		frappe.db.set_value("Asset", asset, "company", self._other_company())  # legacy inconsistency
		doc = frappe.get_doc("Card Equipment", eq.name)
		doc.plate_no = "LEGACY-OK"
		doc.save(ignore_permissions=True)


class TestG2Components(_G2Base):
	def _unit(self, components, **kw):
		return self._owned(is_unit=1, components=[{"component": c} for c in components], **kw)

	def test_component_rules(self):
		a, b = self._owned(), self._owned()
		unit = self._unit([a.name])
		other_co = self._owned(company=self._other_company())
		cases = {
			"own component": [unit.name],
			"itself a unit": [unit.name],
			"twice": [b.name, b.name],
			"company": [other_co.name],
			"already belongs": [a.name],
		}
		for label, rows in cases.items():
			target = unit if label in ("own component",) else None
			with self.assertRaises(frappe.ValidationError, msg=label):
				if target:
					doc = frappe.get_doc("Card Equipment", unit.name)
					doc.set("components", [{"component": c} for c in rows])
					doc.save(ignore_permissions=True)
				else:
					self._unit(rows)

	def test_a_component_cannot_become_a_unit(self):
		a = self._owned()
		self._unit([a.name])
		doc = frappe.get_doc("Card Equipment", a.name)
		doc.is_unit = 1
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be a unit"):
			doc.save(ignore_permissions=True)

	def test_components_need_a_unit(self):
		a = self._owned()
		with self.assertRaisesRegex(frappe.ValidationError, "Only a unit"):
			self._owned(is_unit=0, components=[{"component": a.name}])

	def test_valid_unit_saves_and_legacy_row_saves_unrelated_edits(self):
		a, b = self._owned(), self._owned()
		unit = self._unit([a.name, b.name])
		# legacy: the same piece also listed on a second unit (written directly)
		legacy = self._owned(is_unit=1)
		frappe.get_doc(
			{
				"doctype": "Card Equipment Component",
				"parent": legacy.name,
				"parenttype": "Card Equipment",
				"parentfield": "components",
				"component": a.name,
				"idx": 1,
			}
		).db_insert()
		doc = frappe.get_doc("Card Equipment", legacy.name)
		doc.plate_no = "LEGACY-UNIT"
		doc.save(ignore_permissions=True)
		self.assertTrue(unit.name)


class TestG2ComponentRows(_G2Base):
	"""A component row saved on its own (PUT /api/resource/Card Equipment
	Component/<row>, frappe.client.save): a component change is refused outright
	(#59 — the unit's re-save that update_doc does next would leave no Version
	entry); a standalone row insert still follows the unit's rules (#56)."""

	def _unit(self, components):
		return self._owned(is_unit=1, components=[{"component": c} for c in components])

	def _row(self, unit, component):
		return frappe.get_all(
			"Card Equipment Component", filters={"parent": unit.name, "component": component}, pluck="name"
		)[0]

	def _stored(self, unit):
		return frappe.get_all(
			"Card Equipment Component", filters={"parent": unit.name}, pluck="component", order_by="idx"
		)

	def _put_row(self, row, values):
		frappe.local.form_dict = frappe._dict(data=json.dumps(values))
		try:
			return self._try(update_doc, "Card Equipment Component", row)
		finally:
			frappe.local.form_dict = frappe._dict()

	def test_direct_row_put_cannot_break_the_unit_rules(self):
		a, b, c = self._owned(), self._owned(), self._owned()
		unit = self._unit([a.name, c.name])
		self._unit([b.name])  # b belongs to another unit
		another_unit = self._owned(is_unit=1)
		foreign = self._owned(company=self._other_company())
		cases = {
			"other company": foreign.name,
			"a unit": another_unit.name,
			"the unit itself": unit.name,
			"in another unit": b.name,
			"listed twice": c.name,
		}
		for roles, companies in ((["Card Manager"], ()), (["Card Manager"], (self.company,))):
			self._login(roles, companies)
			for label, component in cases.items():
				self.assertFalse(
					self._put_row(self._row(unit, a.name), {"component": component}), f"{label} {companies}"
				)
			frappe.set_user("Administrator")
			self.assertEqual(self._stored(unit), [a.name, c.name])

	def test_direct_row_save_through_frappe_client_follows_the_same_rules(self):
		from frappe.client import save

		a = self._owned()
		unit = self._unit([a.name])
		foreign = self._owned(company=self._other_company())
		row = frappe.get_doc("Card Equipment Component", self._row(unit, a.name)).as_dict()
		row["component"] = foreign.name
		self._login(["Card Manager"])
		self.assertFalse(self._try(save, row))
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(unit), [a.name])

	def test_a_row_cannot_be_moved_to_another_unit(self):
		a, b, free = self._owned(), self._owned(), self._owned()
		unit, other = self._unit([a.name]), self._unit([b.name])
		for companies in ((), (self.company,)):
			self._login(["Card Manager"], companies)
			# with a free component the moved row would pass the unit rules: only the move check stops it
			for values in ({"parent": other.name}, {"parent": other.name, "component": free.name}):
				self.assertFalse(self._put_row(self._row(unit, a.name), values), (values, companies))
			frappe.set_user("Administrator")
			self.assertEqual((self._stored(unit), self._stored(other)), ([a.name], [b.name]))

	def test_role_edit_on_a_legacy_unit_row_is_not_blocked(self):
		a = self._owned()
		unit = self._unit([a.name])
		# legacy: a foreign component written directly, before #56
		foreign = self._owned(company=self._other_company())
		frappe.get_doc(
			{
				"doctype": "Card Equipment Component",
				"parent": unit.name,
				"parenttype": "Card Equipment",
				"parentfield": "components",
				"component": foreign.name,
				"idx": 2,
			}
		).db_insert()
		self._login(["Card Manager"])
		self.assertTrue(self._put_row(self._row(unit, a.name), {"role": "Prime mover"}))
		self.assertFalse(self._put_row(self._row(unit, a.name), {"component": self._owned().name}))
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Card Equipment Component", self._row(unit, a.name), "role"), "Prime mover"
		)

	def test_card_manager_role_edit_saves_but_component_change_needs_the_unit(self):
		"""#59: a role-only row edit still saves; a component change through the raw
		row endpoint is refused even when the new value would pass the unit rules,
		because only the unit's own save is serialized and versioned."""
		a, free = self._owned(), self._owned()
		unit = self._unit([a.name])
		self._login(["Card Manager"])
		self.assertTrue(self._put_row(self._row(unit, a.name), {"role": "Prime mover"}))
		self.assertFalse(self._put_row(self._row(unit, a.name), {"component": free.name}))
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(unit), [a.name])
		self.assertEqual(
			frappe.db.get_value("Card Equipment Component", self._row(unit, a.name), "role"), "Prime mover"
		)
		# the same change through the unit saves — and lands in the unit's Version
		# history (the test runner sets ignore_version by default: frappe v16
		# document._save, `ignore_version = frappe.in_test if ignore_version is
		# None ...` — so versioning is asked for explicitly here)
		self._login(["Card Manager"])
		doc = frappe.get_doc("Card Equipment", unit.name)
		doc.set("components", [{"component": free.name}])
		doc.save(ignore_version=False)
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(unit), [free.name])
		version = frappe.get_all(
			"Version",
			filters={"ref_doctype": "Card Equipment", "docname": unit.name},
			order_by="creation desc",
			limit=1,
			pluck="data",
		)
		self.assertTrue(version and free.name in version[0], "unit Version must record the component change")

	def test_card_user_cannot_put_a_row_valid_or_not(self):
		a, free = self._owned(), self._owned()
		unit = self._unit([a.name])
		foreign = self._owned(company=self._other_company())
		self._login(["Card User"])
		for values in ({"component": foreign.name}, {"component": free.name}, {"role": "x"}):
			self.assertFalse(self._put_row(self._row(unit, a.name), values), values)
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(unit), [a.name])

	def test_unit_save_still_checks_and_accepts_its_rows(self):
		a, free = self._owned(), self._owned()
		unit = self._unit([a.name])
		foreign = self._owned(company=self._other_company())
		self._login(["Card Manager"])
		for path in self.PATHS:
			self.assertFalse(
				getattr(self, path)(unit.name, {"components": [{"component": foreign.name}]}), path
			)
		self.assertTrue(self._via_rest(unit.name, {"components": [{"component": free.name}]}))
		frappe.set_user("Administrator")
		self.assertEqual(self._stored(unit), [free.name])


class TestG2UnitDays(_G2Base):
	def test_unit_days_outside_its_own_assignment_are_refused(self):
		"""G2-2 reproduction: a component without history used to switch the
		check off, so days before the unit's assignment were accepted."""
		comp = self._owned()
		unit = self._owned(is_unit=1, components=[{"component": comp.name}])
		self._assign(unit.name, self.project, "2026-09-15")
		with self.assertRaisesRegex(frappe.ValidationError, "not assigned to this project"):
			self._card(unit, [8, 8, 8])  # 1-3 Sept, before the unit arrived
		card = frappe.new_doc("Card Monthly Card")
		card.update(
			{"equipment": unit.name, "project": self.project, "shift": "نهاري", "month": "09", "year": 2026}
		)
		card.append("days", {"operation_date": "2026-09-16", "day_status": "عمل", "working_hours": 8})
		card.insert(ignore_permissions=True)  # inside the assignment: fine

	def test_component_rule_is_as_strict_as_before(self):
		with_history, without = self._owned(), self._owned()
		unit = self._owned(
			is_unit=1, components=[{"component": with_history.name}, {"component": without.name}]
		)
		self._assign(with_history.name, self.project, "2026-09-01")
		# any component with history -> every component must be assigned (unchanged)
		with self.assertRaisesRegex(frappe.ValidationError, "not assigned to this project"):
			self._card(unit, [8])

	def test_unit_without_any_history_is_free_as_before(self):
		comp = self._owned()
		unit = self._owned(is_unit=1, components=[{"component": comp.name}])
		self.assertTrue(self._card(unit, [8, 8]).name)


class TestG2Location(_G2Base):
	def test_assignment_in_force_sets_project_and_its_start(self):
		eq = self._owned()
		start = self._days_from(-10)
		self._assign(eq.name, self.project, start, self._days_from(5))
		loc = self._loc(eq)
		self.assertEqual((loc.current_project, str(loc.assignment_date)), (self.project, start))

	def test_future_assignment_does_not_move_the_location(self):
		eq = self._owned()
		start = self._days_from(-10)
		self._assign(eq.name, self.project, start, self._days_from(5))
		future = frappe.new_doc("Project")
		future.project_name = "TEST-G2-FUT-" + self.token
		future.company = self.company
		future.insert(ignore_permissions=True)
		self._assign(eq.name, future.name, self._days_from(10))
		self.assertEqual(self._loc(eq).current_project, self.project)
		only_future = self._owned()
		self._assign(only_future.name, future.name, self._days_from(10))
		self.assertEqual(self._loc(only_future), frappe._dict(current_project=None, assignment_date=None))

	def test_no_assignment_in_force_empties_but_keeps_site_location_and_history(self):
		eq = self._owned(site_location="Yard 1")
		a = self._assign(eq.name, self.project, self._days_from(-30), self._days_from(5))
		doc = frappe.get_doc("Card Equipment Assignment", a.name)
		doc.to_date = self._days_from(-1)  # ended yesterday: back in the yard
		doc.save(ignore_permissions=True)
		self.assertEqual(self._loc(eq), frappe._dict(current_project=None, assignment_date=None))
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "site_location"), "Yard 1")
		self.assertTrue(frappe.db.exists("Card Equipment Assignment", a.name))  # history kept
		self.assertTrue(any(self.project in c for c in self._comments(eq)))  # the old value is recorded

	def test_overwriting_a_legacy_value_leaves_a_comment_and_deleting_recomputes(self):
		legacy = frappe.new_doc("Project")
		legacy.project_name = "TEST-G2-LEG-" + self.token
		legacy.company = self.company
		legacy.insert(ignore_permissions=True)
		eq = self._owned()
		self._legacy_location(eq, legacy.name)
		a = self._assign(eq.name, self.project, self._days_from(-3))
		self.assertEqual(self._loc(eq).current_project, self.project)
		self.assertTrue(any(legacy.name in c and self.project in c for c in self._comments(eq)))
		frappe.delete_doc("Card Equipment Assignment", a.name, ignore_permissions=True)
		self.assertEqual(self._loc(eq), frappe._dict(current_project=None, assignment_date=None))

	def test_back_dated_edit_moves_the_assignment_date(self):
		eq = self._owned()
		a = self._assign(eq.name, self.project, self._days_from(-5))
		doc = frappe.get_doc("Card Equipment Assignment", a.name)
		doc.from_date = self._days_from(-20)
		doc.save(ignore_permissions=True)
		self.assertEqual(str(self._loc(eq).assignment_date), self._days_from(-20))

	def test_sync_writes_only_the_two_fields(self):
		eq = self._owned(site_location="Site X")
		modified = frappe.db.get_value("Card Equipment", eq.name, "modified")
		self._assign(eq.name, self.project, self._days_from(-2))
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "modified"), modified)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "site_location"), "Site X")
		self.assertFalse(
			frappe.get_all("Version", filters={"ref_doctype": "Card Equipment", "docname": eq.name}, limit=1)
		)

	def test_daily_job_is_off_by_default_and_aligns_when_enabled(self):
		eq = self._owned()
		self._assign(eq.name, self.project, self._days_from(-2))
		frappe.db.set_value("Card Equipment", eq.name, "current_project", None)  # drift
		self._enable_daily(False)
		transfer.sync_equipment_locations_daily()
		self.assertIsNone(self._loc(eq).current_project)
		self._enable_daily(True)
		transfer.sync_equipment_locations_daily()
		self.assertEqual(self._loc(eq).current_project, self.project)
		count = len(self._comments(eq))
		transfer.sync_equipment_locations_daily()  # idempotent: nothing new
		self.assertEqual(len(self._comments(eq)), count)

	def test_daily_job_never_touches_equipment_without_history(self):
		legacy = frappe.new_doc("Project")
		legacy.project_name = "TEST-G2-NOH-" + self.token
		legacy.company = self.company
		legacy.insert(ignore_permissions=True)
		eq = self._owned()
		self._legacy_location(eq, legacy.name)
		self._enable_daily(True)
		transfer.sync_equipment_locations_daily()
		self.assertEqual(self._loc(eq).current_project, legacy.name)
		self.assertFalse(self._comments(eq))

	def test_draft_card_keeps_its_project_when_the_location_is_emptied(self):
		eq = self._owned()
		self._legacy_location(eq, self.project)
		card = self._card(eq, [8])
		self.assertEqual(card.project, self.project)
		frappe.db.set_value("Card Equipment", eq.name, "current_project", None)
		card.reload()
		card.save(ignore_permissions=True)
		self.assertEqual(card.project, self.project)

	def _transport(self, eq, project, date):
		tr = frappe.new_doc("Equipment Transport")
		tr.update(
			{
				"equipment": eq.name,
				"project": project,
				"date": date,
				"transport_supplier": self.supplier,
				"company": self.company,
				"amount": 100,
			}
		)
		company_paid(tr).insert(ignore_permissions=True)
		tr.submit()
		return tr

	def test_transfer_moves_the_location_from_the_day_after_its_date(self):
		b, c = self._project("B"), self._project("C")
		eq = self._owned()
		self._assign(eq.name, self.project, self._days_from(-30))
		self._transport(eq, b, self._days_from(-1))  # new assignment starts today
		self.assertEqual(self._loc(eq).current_project, b)
		self._transport(eq, c, self._days_from(0))  # starts tomorrow: today is still B
		self.assertEqual(self._loc(eq).current_project, b)

	def test_cancelling_a_transfer_restores_the_location(self):
		b = self._project("B")
		eq = self._owned()
		self._assign(eq.name, self.project, self._days_from(-30))
		tr = self._transport(eq, b, self._days_from(-1))
		self.assertEqual(self._loc(eq).current_project, b)
		tr.cancel()
		self.assertEqual(self._loc(eq).current_project, self.project)
		self.assertFalse(frappe.flags.get("card_defer_location_sync"))

	def test_defer_flag_is_restored_after_an_error(self):
		eq = self._owned()
		frappe.flags.card_defer_location_sync = None
		# v3.0.0: a transport moves the rows of its equipment table
		row = frappe._dict(card_equipment=eq.name, idx=1)
		row.db_set = lambda *a, **k: None
		tr = frappe._dict(project="TEST-G2-NO-SUCH-PROJECT", date=self._days_from(-1), items=[row])
		tr.db_set = lambda *a, **k: None
		with self.assertRaises(Exception):
			transfer.apply_transfer(tr)
		self.assertFalse(frappe.flags.get("card_defer_location_sync"))


class TestG2Overlap(_G2Base):
	"""Overlapping assignments in force are recorded, never guessed."""

	def _legacy_assignment(self, eq, project, start):
		doc = frappe.get_doc(
			{
				"doctype": "Card Equipment Assignment",
				"equipment": eq.name,
				"project": project,
				"from_date": start,
			}
		)
		doc.db_insert()  # a pre-#56 overlap, written directly (validation would refuse it)
		return doc.name

	def _overlapping(self, eq, count=2):
		return sorted(
			self._legacy_assignment(eq, self._project("OV%s" % i), self._days_from(-10 - i))
			for i in range(count)
		)

	def _overlap_comments(self, eq):
		return [c for c in self._comments(eq) if transfer.OVERLAP_MARK in c]

	def _overlap_errors(self, eq):
		# by reference, not by the (translated) title: language-independent
		return frappe.db.count(
			"Error Log", {"reference_doctype": "Card Equipment", "reference_name": eq.name}
		)

	def test_overlap_is_recorded_with_its_assignments_and_date_even_with_empty_fields(self):
		eq = self._owned()
		names = self._overlapping(eq)
		self.assertEqual(self._loc(eq), frappe._dict(current_project=None, assignment_date=None))
		frappe.local.message_log = []
		transfer.sync_equipment_location(eq.name)
		self.assertEqual(self._loc(eq), frappe._dict(current_project=None, assignment_date=None))
		comments = self._overlap_comments(eq)
		self.assertEqual(len(comments), 1)
		for name in names:
			self.assertIn(name, comments[0])
		self.assertIn(nowdate(), comments[0])
		self.assertTrue(any(names[0] in str(m) for m in frappe.local.message_log))  # shown to the user

	def test_the_same_overlap_is_recorded_once(self):
		eq = self._owned()
		self._overlapping(eq)
		transfer.sync_equipment_location(eq.name)
		transfer.sync_equipment_location(eq.name)
		self.assertEqual(len(self._overlap_comments(eq)), 1)

	def test_a_changed_overlap_set_is_recorded_again(self):
		eq = self._owned()
		self._overlapping(eq)
		transfer.sync_equipment_location(eq.name)
		self._legacy_assignment(eq, self._project("OV9"), self._days_from(-3))
		transfer.sync_equipment_location(eq.name)
		self.assertEqual(len(self._overlap_comments(eq)), 2)

	def test_no_overlap_records_nothing(self):
		eq = self._owned()
		self._assign(eq.name, self.project, self._days_from(-5))
		self._enable_daily(True)
		before = self._overlap_errors(eq)
		transfer.sync_equipment_locations_daily()
		self.assertFalse(self._overlap_comments(eq))
		self.assertEqual(self._overlap_errors(eq), before)

	def test_daily_job_logs_a_new_overlap_once_not_every_day(self):
		eq = self._owned()
		self._overlapping(eq)
		self._enable_daily(True)
		before = self._overlap_errors(eq)
		transfer.sync_equipment_locations_daily()
		transfer.sync_equipment_locations_daily()
		self.assertEqual(self._overlap_errors(eq), before + 1)
		logged = frappe.get_all(
			"Error Log",
			filters={"reference_doctype": "Card Equipment", "reference_name": eq.name},
			pluck="error",
			order_by="creation desc",
			limit=1,
		)
		self.assertIn(eq.name, logged[0])  # the entry names the equipment
		self.assertEqual(len(self._overlap_comments(eq)), 1)

	def test_a_failure_to_record_does_not_stop_the_other_equipment(self):
		overlapped, drifted = self._owned(), self._owned()
		self._overlapping(overlapped)
		self._assign(drifted.name, self.project, self._days_from(-2))
		frappe.db.set_value("Card Equipment", drifted.name, "current_project", None)
		real_get_doc = frappe.get_doc

		def failing_comment(*args, **kwargs):
			if args and isinstance(args[0], dict) and transfer.OVERLAP_MARK in (args[0].get("content") or ""):
				raise frappe.ValidationError("simulated failure while recording the overlap")
			return real_get_doc(*args, **kwargs)

		self._enable_daily(True)
		with patch("frappe.get_doc", side_effect=failing_comment):
			transfer.sync_equipment_locations_daily()  # no exception escapes
		self.assertEqual(self._loc(drifted).current_project, self.project)
		self.assertEqual(self._loc(overlapped), frappe._dict(current_project=None, assignment_date=None))

	def test_one_failing_equipment_does_not_undo_the_others(self):
		first, second = self._owned(), self._owned()
		for eq in (first, second):
			self._assign(eq.name, self.project, self._days_from(-2))
			frappe.db.set_value("Card Equipment", eq.name, "current_project", None)
		real_sync = transfer.sync_equipment_location

		def failing_for_first(equipment, **kwargs):
			if equipment == first.name:
				raise frappe.ValidationError("simulated sync failure")
			return real_sync(equipment, **kwargs)

		self._enable_daily(True)
		failed_log = {"error": ["like", "%" + first.name + "%"]}  # language-independent
		before = frappe.db.count("Error Log", failed_log)
		with patch.object(transfer, "sync_equipment_location", side_effect=failing_for_first):
			transfer.sync_equipment_locations_daily()
		self.assertIsNone(self._loc(first).current_project)
		self.assertEqual(self._loc(second).current_project, self.project)
		self.assertEqual(frappe.db.count("Error Log", failed_log), before + 1)
