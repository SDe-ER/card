# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""CARD 4.4.0: integration API v1 for field apps (DAWM), service lines, work-order
lifecycle, parts issue by Stock Entry and part warranty alerts."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, flt, now_datetime, today

from card import integration_v1 as api
from card.maintenance import DUE, NO_RECORD, SOON, WITHIN, compute_status, line_statuses
from card.meter import REJECTED, VALID
from card.tests import test_asset_link as _link
from card.tests.test_controllers import _ensure_masters

LINK = "الأصل_في_erpnext"
METER = "Card Meter Reading"
SOURCE = "ToDo"  # any DocType a user can write stands in for a field app's document


def _hooks(authorizer="card.tests.test_integration_v1.allow_all", sources=(SOURCE,)):
	"""Register SOURCE as a field source with one authorizer (as a calling app's hooks.py would)."""
	real = frappe.get_hooks

	def fake(hook=None, *args, **kwargs):
		if hook == "card_field_meter_sources":
			return {doctype: [authorizer] if authorizer else [] for doctype in sources}
		return real(hook, *args, **kwargs)

	return patch("card.integration_v1.frappe.get_hooks", side_effect=fake)


def allow_all(source, equipment):
	return True


def deny_all(source, equipment):
	return False


class TestIntegrationV1(IntegrationTestCase):
	_fixed_asset_account = _link.TestAssetLink._fixed_asset_account
	_asset_masters = _link.TestAssetLink._asset_masters
	_make_asset = _link.TestAssetLink._make_asset
	_user = _link.TestAssetLink._user
	_as = _link.TestAssetLink._as
	_make_equipment = _link.TestAssetLink._make_equipment
	_other_company = _link.TestAssetLink._other_company

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		try:
			frappe.db.rollback()
		except Exception:
			pass

	def _source(self):
		return frappe.get_doc({"doctype": SOURCE, "description": "shift"}).insert(ignore_permissions=True)

	def _plan(self, **kw):
		return frappe.get_doc(
			{"doctype": "Card Maintenance Plan", "plan_name": "P-" + frappe.generate_hash(length=5), **kw}
		).insert(ignore_permissions=True)

	def _order(self, eq, meter, submit=True, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Card Maintenance Order",
				"equipment": eq,
				"service_date": kw.pop("service_date", today()),
				"meter_reading": meter,
				**kw,
			}
		).insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	# ---------- C1 lookups ----------

	def test_equipment_for_asset_and_snapshot(self):
		asset = self._make_asset()
		eq = self._make_equipment(**{LINK: asset})
		self.assertEqual(api.equipment_for_asset(asset), eq.name)
		self.assertEqual(api.equipment_for_assets([asset, "NO-SUCH"]), {asset: eq.name})
		src = self._source()
		with _hooks():
			api.record_machine_fuelling(
				eq.name, 120, 55, SOURCE, src.name, add_to_date(now_datetime(), hours=-1)
			)
		snap = api.equipment_snapshot(eq.name)
		self.assertEqual((snap["asset"], flt(snap["current_meter"])), (asset, 55))
		self.assertEqual(flt(snap["last_fuelling"]["litres"]), 120)
		self.assertIsNone(snap["hours_since_last_service"])

	def test_lookup_hides_another_companys_equipment(self):
		other = self._other_company()
		asset = self._make_asset()
		eq = self._make_equipment(company=other)
		frappe.db.set_value("Card Equipment", eq.name, LINK, asset)  # test data only
		self._as(["Card User"], restrict=self._m["company"])
		self.assertIsNone(api.equipment_for_asset(asset))
		self.assertEqual(api.equipment_for_assets([asset]), {})
		with self.assertRaises(frappe.PermissionError):
			api.equipment_snapshot(eq.name)

	# ---------- C2 / C3 field readings ----------

	def test_field_reading_needs_a_registered_source_and_its_write_right(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks(sources=()):
			with self.assertRaises(frappe.PermissionError):
				api.record_meter_reading(eq.name, 10, SOURCE, src.name)
		with _hooks(authorizer=None):  # registered without an authorizer: fail closed
			with self.assertRaises(frappe.PermissionError):
				api.record_meter_reading(eq.name, 10, SOURCE, src.name)
		self._as(["Employee"])  # not the owner of the ToDo: no write right
		with _hooks():
			with self.assertRaises(frappe.PermissionError):
				api.record_meter_reading(eq.name, 10, SOURCE, src.name)

	def test_field_reading_is_idempotent_and_a_new_value_replaces_the_old(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks():
			first = api.record_meter_reading(eq.name, 100, SOURCE, src.name, source_key="end")
			again = api.record_meter_reading(eq.name, 100, SOURCE, src.name, source_key="end")
			self.assertEqual(first["name"], again["name"])
			start = api.record_meter_reading(
				eq.name, 98, SOURCE, src.name, add_to_date(now_datetime(), hours=-8), source_key="start"
			)
			fixed = api.record_meter_reading(eq.name, 104, SOURCE, src.name, source_key="end")
		self.assertNotEqual(fixed["name"], first["name"])
		self.assertEqual(frappe.db.get_value(METER, first["name"], "status"), REJECTED)
		self.assertEqual(frappe.db.get_value(METER, start["name"], "status"), VALID)
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", eq.name, "current_meter")), 104)
		self.assertEqual(fixed["source_type"], "Field Operation")

	def test_strict_refuses_a_backward_reading_and_default_marks_it_suspect(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks():
			api.record_meter_reading(
				eq.name, 500, SOURCE, src.name, add_to_date(now_datetime(), hours=-5), "a"
			)
			with self.assertRaisesRegex(frappe.ValidationError, "lower than the last reading"):
				api.record_meter_reading(eq.name, 450, SOURCE, src.name, source_key="b", strict=1)
			soft = api.record_meter_reading(eq.name, 450, SOURCE, src.name, source_key="b")
		self.assertEqual(soft["status"], "Suspect")

	def test_authorizer_hook_can_refuse_and_company_is_checked(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks(authorizer="card.tests.test_integration_v1.deny_all"):
			with self.assertRaises(frappe.PermissionError):
				api.record_meter_reading(eq.name, 1, SOURCE, src.name)
		theirs = self._make_equipment(company=self._other_company())
		user = self._user(["Card User"], restrict=self._m["company"])
		frappe.set_user(user)
		mine = frappe.get_doc({"doctype": SOURCE, "description": "x"}).insert()
		with _hooks():
			with self.assertRaises(frappe.PermissionError):
				api.record_meter_reading(theirs.name, 1, SOURCE, mine.name)

	def test_fuelling_needs_litres_and_posts_no_cost(self):
		eq = self._make_equipment()
		src = self._source()
		pinv = frappe.db.count("Purchase Invoice")
		fills = frappe.db.count("Project Diesel Fill")
		with _hooks():
			with self.assertRaisesRegex(frappe.ValidationError, "greater than zero"):
				api.record_machine_fuelling(eq.name, 0, 10, SOURCE, src.name)
			row = api.record_machine_fuelling(eq.name, 80, 10, SOURCE, src.name)
		self.assertEqual((row["source_type"], flt(row["litres"])), ("Field Fuelling", 80))
		self.assertEqual(frappe.db.count("Purchase Invoice"), pinv)
		self.assertEqual(frappe.db.count("Project Diesel Fill"), fills)

	def test_field_sources_cannot_be_typed_as_manual_readings(self):
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "recorded by CARD"):
			frappe.get_doc(
				{"doctype": METER, "equipment": eq.name, "reading": 3, "source_type": "Field Operation"}
			).insert(ignore_permissions=True)

	def test_reject_source_readings(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks():
			row = api.record_meter_reading(eq.name, 30, SOURCE, src.name)
			api.reject_source_readings(SOURCE, src.name)
		self.assertEqual(frappe.db.get_value(METER, row["name"], "status"), REJECTED)

	# ---------- C5 service lines ----------

	def test_service_lines_have_their_own_baselines(self):
		eq = self._make_equipment()
		self._plan(
			applies_to="Equipment",
			card_equipment=eq.name,
			service_lines=[
				{"service_name": "Oil", "interval_hours": 250, "warn_before_hours": 20},
				{"service_name": "Filters", "interval_hours": 500, "warn_before_hours": 50},
			],
		)
		self.assertEqual(compute_status(eq.name)[0], NO_RECORD)
		self._order(eq.name, 1000, service_date=add_days(today(), -30))  # both services
		self._order(
			eq.name, 1240, service_date=add_days(today(), -14), services_done=[{"service_name": "Oil"}]
		)
		src = self._source()
		with _hooks():
			api.record_meter_reading(eq.name, 1470, SOURCE, src.name, add_to_date(now_datetime(), days=-2))
		lines = {r.service_name: r for r in line_statuses(eq.name)}
		self.assertEqual((lines["Oil"].status, flt(lines["Oil"].next_at)), (SOON, 1490))
		self.assertEqual((lines["Filters"].status, flt(lines["Filters"].next_at)), (SOON, 1500))
		self.assertEqual(compute_status(eq.name), (SOON, 1490))
		with _hooks():
			api.record_meter_reading(eq.name, 1495, SOURCE, src.name, source_key="2")
		self.assertEqual(compute_status(eq.name)[0], DUE)

	def test_plan_line_validation_and_order_services(self):
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "twice"):
			self._plan(
				applies_to="Equipment",
				card_equipment=eq.name,
				service_lines=[
					{"service_name": "Oil", "interval_hours": 100},
					{"service_name": "Oil", "interval_hours": 200},
				],
			)
		self._plan(
			applies_to="Equipment",
			card_equipment=eq.name,
			service_lines=[{"service_name": "Oil", "interval_hours": 100}],
		)
		with self.assertRaisesRegex(frappe.ValidationError, "not a service line"):
			self._order(eq.name, 5, submit=False, services_done=[{"service_name": "Tyres"}])
		frappe.db.set_value("Card Equipment", eq.name, "last_service_date", add_days(today(), -1))
		self.assertEqual(compute_status(eq.name)[0], WITHIN)

	# ---------- C4 lifecycle ----------

	def test_due_scan_creates_one_draft_order_that_must_be_approved(self):
		from card.maintenance import approve_order, refresh_status, start_order

		settings = frappe.get_single("Card Settings")
		settings.auto_create_due_orders = 1
		settings.save(ignore_permissions=True)
		eq = self._make_equipment(service_interval_hours=100)
		frappe.db.set_value("Card Equipment", eq.name, "last_service_meter", 100)
		src = self._source()
		with _hooks():
			api.record_meter_reading(eq.name, 250, SOURCE, src.name)
		refresh_status(eq.name)
		orders = frappe.get_all(
			"Card Maintenance Order",
			filters={"equipment": eq.name},
			fields=["name", "work_status", "auto_created"],
		)
		self.assertEqual(len(orders), 1)
		self.assertEqual((orders[0].work_status, orders[0].auto_created), ("Due", 1))
		order = frappe.get_doc("Card Maintenance Order", orders[0].name)
		with self.assertRaisesRegex(frappe.ValidationError, "Approve"):
			order.submit()
		self._as(["Card User"])
		with self.assertRaises(frappe.PermissionError):
			approve_order(order.name)
		frappe.set_user("Administrator")
		self.assertEqual(approve_order(order.name), "Approved")
		self.assertEqual(start_order(order.name), "In Progress")
		order.reload()
		order.submit()
		self.assertEqual(
			frappe.db.get_value("Card Maintenance Order", order.name, "work_status"), "Completed"
		)

	def test_work_status_cannot_be_typed(self):
		eq = self._make_equipment()
		order = self._order(eq.name, 5, submit=False, work_status="Completed", approved_by="Administrator")
		self.assertEqual((order.work_status, order.approved_by), ("Approved", None))
		order.work_status = "Due"
		order.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Card Maintenance Order", order.name, "work_status"), "Approved")
		order.reload()
		order.submit()
		order.cancel()
		self.assertEqual(
			frappe.db.get_value("Card Maintenance Order", order.name, "work_status"), "Cancelled"
		)

	# ---------- C6 parts issue ----------

	def test_stock_entry_from_an_order_once(self):
		from card.maintenance import make_stock_entry
		from card.tests.test_em_consolidation import _stock_item

		item = _stock_item()
		if not frappe.db.exists("Stock Entry Type", {"purpose": "Material Issue"}):
			frappe.get_doc(
				{"doctype": "Stock Entry Type", "name": "Material Issue", "purpose": "Material Issue"}
			).insert(ignore_permissions=True)
		warehouse = frappe.db.get_value("Warehouse", {"company": self._m["company"], "is_group": 0}, "name")
		eq = self._make_equipment()
		no_wh = self._order(eq.name, 5, items=[{"item_code": item, "qty": 1}])
		with self.assertRaisesRegex(frappe.ValidationError, "warehouse"):
			make_stock_entry(no_wh.name)
		frappe.db.set_value("Item", item, "valuation_rate", 10)  # ERPNext needs a rate for the issue
		order = self._order(eq.name, 6, items=[{"item_code": item, "qty": 3}], source_warehouse=warehouse)
		name = make_stock_entry(order.name)
		se = frappe.get_doc("Stock Entry", name)
		self.assertEqual((se.docstatus, se.purpose, flt(se.items[0].qty)), (0, "Material Issue", 3))
		self.assertEqual(se.items[0].s_warehouse, warehouse)
		with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
			make_stock_entry(order.name)

	# ---------- C7 warranty ----------

	def test_warranty_alert_once_per_part(self):
		from card.maintenance import daily_warranty_scan
		from card.tests.test_em_consolidation import _stock_item

		manager = self._user(["Card Manager"])
		eq = self._make_equipment()
		part = frappe.get_doc(
			{
				"doctype": "Card Equipment Part",
				"item_code": _stock_item(),
				"applies_to": "Equipment",
				"card_equipment": eq.name,
				"part_number": "PN-1",
				"warranty_until": add_days(today(), 10),
				"warranty_alerted_on": today(),  # typed by a user: ignored
			}
		).insert(ignore_permissions=True)
		self.assertFalse(part.warranty_alerted_on)
		frappe.db.set_value("Card Equipment Part", part.name, "is_active", 1)
		daily_warranty_scan()
		daily_warranty_scan()
		self.assertEqual(
			frappe.db.count("Notification Log", {"for_user": manager, "document_name": part.name}), 1
		)

	# ---------- review fixes ----------

	def test_uncovered_line_keeps_the_pre_card_baseline(self):
		eq = self._make_equipment()
		frappe.db.set_value(
			"Card Equipment",
			eq.name,
			{"last_service_meter": 800, "last_service_date": add_days(today(), -40)},
		)
		self._plan(
			applies_to="Equipment",
			card_equipment=eq.name,
			service_lines=[
				{"service_name": "Oil", "interval_hours": 250, "warn_before_hours": 20},
				{"service_name": "Filters", "interval_hours": 500, "warn_before_hours": 50},
			],
		)
		self._order(
			eq.name, 1000, service_date=add_days(today(), -20), services_done=[{"service_name": "Oil"}]
		)
		lines = {r.service_name: r for r in line_statuses(eq.name)}
		self.assertEqual(flt(lines["Filters"].next_at), 1300)  # from 800, not from the oil change
		self.assertEqual(flt(lines["Oil"].next_at), 1250)

	def test_service_submit_past_due_creates_no_false_due_order(self):
		self._due_flow(1)
		eq = self._make_equipment(service_interval_hours=100)
		frappe.db.set_value(
			"Card Equipment",
			eq.name,
			{"last_service_meter": 100, "last_service_date": add_days(today(), -10)},
		)
		order = self._order(eq.name, 205, submit=False, service_date=add_days(today(), -1))
		self.assertEqual(order.work_status, "Due")  # the due workflow needs an approval
		from card.maintenance import approve_order

		approve_order(order.name)
		frappe.get_doc("Card Maintenance Order", order.name).submit()
		self.assertFalse(
			frappe.db.exists(
				"Card Maintenance Order", {"equipment": eq.name, "docstatus": 0, "auto_created": 1}
			)
		)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "maintenance_status"), WITHIN)

	def test_a_failing_due_order_never_loses_the_reading(self):
		self._due_flow(1)
		eq = self._make_equipment(service_interval_hours=100)
		frappe.db.set_value("Card Equipment", eq.name, "last_service_meter", 100)
		src = self._source()
		with _hooks(), patch("card.maintenance.create_due_order", side_effect=RuntimeError("x")):
			row = api.record_meter_reading(eq.name, 250, SOURCE, src.name)
		self.assertTrue(frappe.db.exists(METER, row["name"]))
		self.assertTrue(frappe.db.exists("Error Log", {"method": ["like", "%due order%"]}))

	def test_approval_needs_the_orders_company(self):
		from card.maintenance import approve_order

		self._due_flow(1)
		theirs = self._make_equipment(company=self._other_company())
		order = self._order(theirs.name, 5, submit=False)
		self._as(["Card Manager"], restrict=self._m["company"])
		with self.assertRaises(frappe.PermissionError):
			approve_order(order.name)

	def test_reject_on_a_live_source_follows_the_authorizer(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks():
			row = api.record_meter_reading(eq.name, 12, SOURCE, src.name)
		with _hooks(authorizer="card.tests.test_integration_v1.deny_all"):
			with self.assertRaises(frappe.PermissionError):
				api.reject_source_readings(SOURCE, src.name)
		self.assertEqual(frappe.db.get_value(METER, row["name"], "status"), VALID)

	def test_a_replaced_reading_cannot_be_made_valid_again(self):
		eq = self._make_equipment()
		src = self._source()
		with _hooks():
			old = api.record_meter_reading(eq.name, 20, SOURCE, src.name)
			api.record_meter_reading(eq.name, 21, SOURCE, src.name)
		doc = frappe.get_doc(METER, old["name"])
		doc.status, doc.status_reason = VALID, ""
		with self.assertRaisesRegex(frappe.ValidationError, "replaced"):
			doc.save(ignore_permissions=True)

	def test_parts_are_issued_one_way_only(self):
		from card.maintenance import make_material_request, make_stock_entry
		from card.tests.test_em_consolidation import _stock_item

		eq = self._make_equipment()
		warehouse = frappe.db.get_value("Warehouse", {"company": self._m["company"], "is_group": 0}, "name")
		order = self._order(
			eq.name, 5, items=[{"item_code": _stock_item(), "qty": 1}], source_warehouse=warehouse
		)
		make_material_request(order.name)
		with self.assertRaisesRegex(frappe.ValidationError, "already requested"):
			make_stock_entry(order.name)

	def test_equipment_for_assets_refuses_a_bad_list(self):
		with self.assertRaises(frappe.ValidationError):
			api.equipment_for_assets("ABC")
		with self.assertRaises(frappe.ValidationError):
			api.equipment_for_assets(["A"] * 201)

	def _due_flow(self, on):
		settings = frappe.get_single("Card Settings")
		settings.auto_create_due_orders = on
		settings.save(ignore_permissions=True)
