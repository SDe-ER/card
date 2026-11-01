# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-099 / FR-100 / FR-101: equipment_manager consolidated into CARD.

Meter history (append-only, plausibility, current meter), per-machine fuelling on the
diesel fill, maintenance plans / status / orders / breakdowns and the ERPNext documents
they create, and the legacy archive + import (skipped when equipment_manager is absent)."""

from unittest import skipUnless
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, flt, now_datetime, today

from card.maintenance import DUE, NO_RECORD, SOON, WITHIN, compute_status, interval_for, refresh_status
from card.meter import REJECTED, SUSPECT, VALID, add_reading
from card.tests import test_asset_link as _link
from card.tests.test_controllers import _ensure_masters

LINK = "الأصل_في_erpnext"
METER = "Card Meter Reading"


def _em_installed():
	return bool(frappe.db.exists("DocType", "Fueling Log"))


class TestEMConsolidation(IntegrationTestCase):
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

	def _manual(self, eq, reading, when=None, **kw):
		return frappe.get_doc(
			{
				"doctype": METER,
				"equipment": eq,
				"reading": reading,
				"reading_time": when or now_datetime(),
				"source_type": "Manual",
				**kw,
			}
		).insert(ignore_permissions=True)

	# ---------- FR-099 meter history ----------

	def test_manual_readings_set_the_current_meter_to_the_highest_valid(self):
		eq = self._make_equipment()
		self._manual(eq.name, 100, add_to_date(now_datetime(), days=-3))
		self._manual(eq.name, 112, add_to_date(now_datetime(), days=-2))
		self._manual(eq.name, 105, add_to_date(now_datetime(), days=-1))  # suspect (backward)
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", eq.name, "current_meter")), 112)

	def test_backward_and_jump_readings_are_suspect_not_refused(self):
		eq = self._make_equipment()
		self._manual(eq.name, 1000, add_to_date(now_datetime(), days=-2))
		back = self._manual(eq.name, 900, add_to_date(now_datetime(), days=-1))
		self.assertEqual(back.status, SUSPECT)
		self.assertEqual(flt(back.reading), 900)  # never altered
		jump = self._manual(eq.name, 5000, now_datetime())  # 4000 h in one day
		self.assertEqual(jump.status, SUSPECT)
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", eq.name, "current_meter")), 1000)

	def test_consumption_from_litres_and_hours_since_previous(self):
		eq = self._make_equipment()
		self._manual(eq.name, 100, add_to_date(now_datetime(), days=-1))
		r = add_reading(eq.name, 110, now_datetime(), "Diesel Fill", litres=150)
		self.assertEqual(flt(r.hours_since_previous), 10)
		self.assertEqual(flt(r.consumption_rate), 15)

	def test_readings_are_append_only(self):
		eq = self._make_equipment()
		r = self._manual(eq.name, 50)
		r.reading = 55
		with self.assertRaisesRegex(frappe.ValidationError, "cannot be changed"):
			r.save(ignore_permissions=True)
		r.reload()
		with self.assertRaises(frappe.ValidationError):
			r.delete(ignore_permissions=True)
		r.reload()
		r.status = REJECTED
		with self.assertRaisesRegex(frappe.ValidationError, "reason"):
			r.save(ignore_permissions=True)
		r.reload()
		r.status, r.status_reason = REJECTED, "typo"
		r.save(ignore_permissions=True)
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", eq.name, "current_meter")), 0)

	def test_card_user_cannot_change_a_reading_status(self):
		eq = self._make_equipment()
		r = self._manual(eq.name, 70)
		self._as(["Card User"])
		r = frappe.get_doc(METER, r.name)
		r.status, r.status_reason = REJECTED, "no"
		with self.assertRaises(frappe.PermissionError):
			r.save(ignore_permissions=True)

	def test_system_sources_cannot_be_typed_by_a_user(self):
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "recorded by CARD"):
			self._manual(eq.name, 10, source_type="Diesel Fill")

	def test_reading_takes_the_equipment_company_and_asset(self):
		asset = self._make_asset()
		eq = self._make_equipment(**{LINK: asset})
		r = self._manual(eq.name, 5)
		self.assertEqual(r.company, eq.company)
		self.assertEqual(r.asset, asset)

	# ---------- FR-099 per-machine fuelling on the diesel fill ----------

	def _fill(self, **kw):
		from card.card.doctype.project_diesel_fill.project_diesel_fill import ProjectDieselFill

		doc = frappe.new_doc("Project Diesel Fill")
		doc.name = "PDF-TEST-" + frappe.generate_hash(length=6)
		doc.date = today()
		doc.litres = kw.pop("litres", 300)
		for k, v in kw.items():
			doc.set(k, v)
		doc.db_insert()  # the meter rows point at a real fill
		return ProjectDieselFill, doc

	def test_machine_litres_cannot_exceed_the_fill(self):
		a, b = self._make_equipment(), self._make_equipment()
		cls, doc = self._fill(litres=100)
		doc.append("equipment_filled", {"card_equipment": a.name, "litres": 60})
		doc.append("equipment_filled", {"card_equipment": b.name, "litres": 50})
		with self.assertRaisesRegex(frappe.ValidationError, "more than the litres"):
			cls._check_machine_rows(doc)
		doc.equipment_filled[1].litres = 40
		cls._check_machine_rows(doc)  # 100 of 100: fine
		doc.append("equipment_filled", {"litres": 1})
		with self.assertRaisesRegex(frappe.ValidationError, "need the equipment"):
			cls._check_machine_rows(doc)

	def test_fill_submit_and_cancel_write_and_reject_meter_history(self):
		a, b = self._make_equipment(), self._make_equipment()
		cls, doc = self._fill(litres=200)
		doc.append("equipment_filled", {"card_equipment": a.name, "litres": 120, "hour_meter_reading": 500})
		doc.append("equipment_filled", {"card_equipment": b.name, "litres": 80})  # no meter: no reading
		cls.on_submit(doc)
		rows = frappe.get_all(METER, {"source_name": doc.name}, ["equipment", "reading", "litres", "status"])
		self.assertEqual([(r.equipment, flt(r.reading), flt(r.litres)) for r in rows], [(a.name, 500, 120)])
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", a.name, "current_meter")), 500)
		cls.on_cancel(doc)
		self.assertEqual(frappe.db.get_value(METER, {"source_name": doc.name}, "status"), REJECTED)
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", a.name, "current_meter")), 0)

	def test_cost_allocation_ignores_machine_litres(self):
		# FR-033 is unchanged: project-tank fills still split by operating hours
		import inspect

		from card import diesel

		self.assertNotIn("equipment_filled", inspect.getsource(diesel.allocate_project_diesel))

	# ---------- FR-100 maintenance ----------

	def _plan(self, **kw):
		return frappe.get_doc(
			{"doctype": "Card Maintenance Plan", "plan_name": "P-" + frappe.generate_hash(length=5), **kw}
		).insert(ignore_permissions=True)

	def test_status_follows_the_hours_since_the_last_service(self):
		eq = self._make_equipment(service_interval_hours=250)
		self.assertEqual(compute_status(eq.name)[0], NO_RECORD)
		frappe.db.set_value("Card Equipment", eq.name, "last_service_meter", 1000)
		self._manual(eq.name, 1100, add_to_date(now_datetime(), days=-20))
		self.assertEqual(compute_status(eq.name), (WITHIN, 1250))
		self._manual(eq.name, 1210, add_to_date(now_datetime(), days=-10))
		self.assertEqual(compute_status(eq.name)[0], SOON)  # 40 h left, warning 50 h
		self._manual(eq.name, 1260)
		self.assertEqual(compute_status(eq.name)[0], DUE)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "maintenance_status"), DUE)

	def test_machine_plan_wins_over_model_plan_and_equipment_interval(self):
		make = frappe.get_doc(
			{"doctype": "Card Equipment Make", "make_name": "MK-" + frappe.generate_hash(length=5)}
		).insert(ignore_permissions=True)
		model = frappe.get_doc(
			{
				"doctype": "Card Equipment Model",
				"model_name": "M-" + frappe.generate_hash(length=5),
				"equipment_make": make.name,
				"equipment_type": self._m["etype"],
			}
		)
		model.insert(ignore_permissions=True)
		eq = self._make_equipment(service_interval_hours=300, equipment_model=model.name)
		self.assertEqual(interval_for(eq.name)[0], 300)
		self._plan(applies_to="Equipment Model", equipment_model=model.name, interval_hours=400)
		self.assertEqual(interval_for(eq.name)[0], 400)
		self._plan(applies_to="Equipment", card_equipment=eq.name, interval_hours=200, warn_before_hours=20)
		self.assertEqual(interval_for(eq.name)[:2], (200, 20))

	def test_plan_validation(self):
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "interval"):
			self._plan(applies_to="Equipment", card_equipment=eq.name)
		with self.assertRaisesRegex(frappe.ValidationError, "warning"):
			self._plan(
				applies_to="Equipment", card_equipment=eq.name, interval_hours=100, warn_before_hours=100
			)
		self._plan(applies_to="Equipment", card_equipment=eq.name, interval_hours=100)
		with self.assertRaises(frappe.UniqueValidationError):
			self._plan(applies_to="Equipment", card_equipment=eq.name, interval_hours=120)

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

	def test_service_order_moves_the_last_service_and_cancel_restores_it(self):
		eq = self._make_equipment(service_interval_hours=250)
		frappe.db.set_value(
			"Card Equipment",
			eq.name,
			{"last_service_meter": 700, "last_service_date": add_days(today(), -30)},
		)
		order = self._order(eq.name, 950)
		row = frappe.db.get_value(
			"Card Equipment", eq.name, ["last_service_meter", "maintenance_status"], as_dict=True
		)
		self.assertEqual(flt(row.last_service_meter), 950)
		self.assertEqual(row.maintenance_status, WITHIN)
		self.assertEqual(
			frappe.db.get_value(METER, order.meter_reading_record, "source_type"), "Maintenance Order"
		)
		order.cancel()
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", eq.name, "last_service_meter")), 700)
		self.assertEqual(frappe.db.get_value(METER, order.meter_reading_record, "status"), REJECTED)

	def test_breakdown_takes_the_machine_out_of_service_until_it_is_back(self):
		eq = self._make_equipment()
		start = add_to_date(now_datetime(), hours=-30)
		order = self._order(eq.name, 10, service_type="Breakdown", out_of_service_from=start)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "status"), "في الصيانة")
		order.back_in_service_on = add_to_date(start, hours=24)
		order.save(ignore_permissions=True)
		self.assertEqual(flt(order.downtime_hours), 24)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "status"), "نشطة")
		# a repair or breakdown does not move the scheduled-service baseline
		self.assertFalse(flt(frappe.db.get_value("Card Equipment", eq.name, "last_service_meter")))

	def test_order_refuses_future_dates_and_another_companys_plan(self):
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "future"):
			self._order(eq.name, 1, submit=False, service_date=add_days(today(), 2))
		other = self._make_equipment()
		plan = self._plan(applies_to="Equipment", card_equipment=other.name, interval_hours=100)
		with self.assertRaisesRegex(frappe.ValidationError, "not the active plan"):
			self._order(eq.name, 1, submit=False, maintenance_plan=plan.name)

	def test_material_request_from_an_order_once_and_with_the_users_rights(self):
		from card.maintenance import make_material_request

		item = frappe.db.get_value("Item", {"is_stock_item": 1, "disabled": 0}, "name") or _stock_item()
		eq = self._make_equipment()
		order = self._order(eq.name, 5, items=[{"item_code": item, "qty": 2}])
		name = make_material_request(order.name)
		mr = frappe.get_doc("Material Request", name)
		self.assertEqual(
			(mr.docstatus, mr.material_request_type, flt(mr.items[0].qty)), (0, "Material Issue", 2)
		)
		with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
			make_material_request(order.name)
		self._as(["Card Supervisor"])  # reads orders, may not write them
		with self.assertRaises(frappe.PermissionError):
			make_material_request(order.name)

	def test_due_alert_reaches_card_managers_once(self):
		manager = self._user(["Card Manager"])
		eq = self._make_equipment(service_interval_hours=100)
		frappe.db.set_value("Card Equipment", eq.name, "last_service_meter", 100)
		before = frappe.db.count("Notification Log", {"for_user": manager, "document_name": eq.name})
		self._manual(eq.name, 250)
		refresh_status(eq.name)  # already due: no second alert
		self.assertEqual(
			frappe.db.count("Notification Log", {"for_user": manager, "document_name": eq.name}) - before, 1
		)

	def test_daily_scan_never_stops_on_one_bad_equipment(self):
		from card.maintenance import daily_maintenance_scan

		self._make_equipment()
		logs = frappe.db.count("Error Log")
		with patch("card.maintenance.refresh_status", side_effect=RuntimeError("x")):
			daily_maintenance_scan()
		self.assertGreater(frappe.db.count("Error Log"), logs)

	# ---------- FR-101 legacy equipment_manager ----------

	def _legacy_log(self, asset, reading, litres, docstatus=1, when=None):
		doc = frappe.get_doc(
			{
				"doctype": "Fueling Log",
				"asset": asset,
				"date": when or now_datetime(),
				"hour_meter_reading": reading,
				"fuel_qty": litres,
			}
		)
		doc.set_new_name()
		doc.docstatus = docstatus
		doc.db_insert()  # legacy data as stored, without the old app's logic
		return doc.name

	@skipUnless(_em_installed(), "equipment_manager not installed")
	def test_import_dry_run_writes_nothing_then_imports_everything_once(self):
		from card.legacy_equipment_manager import import_fueling_logs, verify

		asset = self._make_asset()
		eq = self._make_equipment(**{LINK: asset})
		unmapped = self._make_asset()
		t0 = add_to_date(now_datetime(), days=-10)
		names = [
			self._legacy_log(asset, 100, 50, when=t0),
			self._legacy_log(asset, 110, 40, when=add_to_date(t0, days=1)),
			self._legacy_log(asset, 0, 30, when=add_to_date(t0, days=2)),  # no meter
			self._legacy_log(asset, 120, 20, docstatus=2, when=add_to_date(t0, days=3)),  # cancelled
			self._legacy_log(unmapped, 7, 5, when=t0),
		]
		source_modified = {n: frappe.db.get_value("Fueling Log", n, "modified") for n in names}
		before = frappe.db.count(METER)
		dry = import_fueling_logs(dry_run=1)
		self.assertEqual(frappe.db.count(METER), before)
		self.assertIn(unmapped, dry["unmapped_assets"])
		run = import_fueling_logs(dry_run=0)
		copies = {
			r.legacy_record: r
			for r in frappe.get_all(
				METER, {"legacy_record": ["in", names]}, ["legacy_record", "status", "equipment", "litres"]
			)
		}
		self.assertEqual(set(copies), set(names))
		self.assertEqual(copies[names[0]].status, VALID)
		self.assertEqual(copies[names[2]].status, SUSPECT)
		self.assertEqual(copies[names[3]].status, REJECTED)
		self.assertEqual(copies[names[0]].equipment, eq.name)
		self.assertFalse(copies[names[4]].equipment)  # Asset without equipment: kept on the Asset
		self.assertGreaterEqual(run["created"], 5)
		again = import_fueling_logs(dry_run=0)
		self.assertEqual(again["created"], 0)  # idempotent
		self.assertTrue(verify()["ok"])
		for n in names:  # source untouched
			self.assertEqual(frappe.db.get_value("Fueling Log", n, "modified"), source_modified[n])
		# the Asset's readings join the equipment linked to it later
		later = self._make_equipment(**{LINK: unmapped})
		self.assertEqual(frappe.db.get_value(METER, {"legacy_record": names[4]}, "equipment"), later.name)

	@skipUnless(_em_installed(), "equipment_manager not installed")
	def test_legacy_litres_are_never_a_cost(self):
		from card.legacy_equipment_manager import import_fueling_logs

		asset = self._make_asset()
		self._make_equipment(**{LINK: asset})
		self._legacy_log(asset, 10, 999)
		pinv = frappe.db.count("Purchase Invoice")
		import_fueling_logs(dry_run=0)
		self.assertEqual(frappe.db.count("Purchase Invoice"), pinv)
		self.assertFalse(frappe.db.exists("Project Diesel Fill", {"litres": 999}))

	@skipUnless(_em_installed(), "equipment_manager not installed")
	def test_archive_is_private_with_a_checksum(self):
		import hashlib

		from card.legacy_equipment_manager import archive

		asset = self._make_asset()
		self._legacy_log(asset, 1, 1)
		out = archive()
		file = frappe.get_doc("File", {"file_url": out["file"]})
		self.assertTrue(file.is_private)
		self.assertEqual(hashlib.sha256(_bytes(file.get_content())).hexdigest(), out["sha256"])
		self.assertGreaterEqual(out["counts"]["Fueling Log"], 1)
		data = frappe.parse_json(_bytes(file.get_content()).decode())
		for key in (
			"comments",
			"custom_fields",
			"property_setters",
			"reports",
			"server_scripts",
			"web_forms",
		):
			self.assertIn(key, data)

	@skipUnless(_em_installed(), "equipment_manager not installed")
	def test_retirement_tools_are_system_manager_only(self):
		from card.legacy_equipment_manager import archive, import_fueling_logs, verify

		self._as(["Card Manager"])
		for fn in (archive, verify, lambda: import_fueling_logs(dry_run=1)):
			with self.assertRaises(frappe.PermissionError):
				fn()

	@skipUnless(_em_installed(), "equipment_manager not installed")
	def test_meter_reconciliation_reads_card_history_without_double_counting(self):
		from card.legacy_equipment_manager import import_fueling_logs
		from card.meter_reconciliation import legacy_readings

		asset = self._make_asset()
		eq = self._make_equipment(**{LINK: asset})
		self._legacy_log(asset, 300, 10)
		import_fueling_logs(dry_run=0)
		self._manual(eq.name, 320)
		found, available = legacy_readings({asset})
		sources = sorted(r["source"] for r in found[asset])
		self.assertEqual(sources, ["Card Meter Reading", "Fueling Log"])  # the legacy copy is skipped
		self.assertTrue(available)

	# ---------- review fixes (2026-11-01) ----------

	def test_company_restricted_user_cannot_use_another_companys_equipment(self):
		other = self._other_company()
		mine = self._make_equipment()
		theirs = self._make_equipment(company=other)
		reading = self._manual(theirs.name, 10, add_to_date(now_datetime(), days=-1))
		order = self._order(theirs.name, 10)
		self._as(["Card User"], restrict=self._m["company"])
		for doctype, fields in ((METER, {"reading": 20}), ("Card Maintenance Order", {"meter_reading": 20})):
			doc = frappe.get_doc(
				{"doctype": doctype, "equipment": theirs.name, "service_date": today(), **fields}
			)
			with self.assertRaises(frappe.PermissionError):
				doc.insert()
		self.assertFalse(frappe.has_permission(METER, "read", reading.name))
		self.assertFalse(frappe.has_permission("Card Maintenance Order", "read", order.name))
		self.assertNotIn(reading.name, frappe.get_list(METER, pluck="name"))
		self.assertNotIn(order.name, frappe.get_list("Card Maintenance Order", pluck="name"))
		# the user's own company still works
		frappe.get_doc({"doctype": METER, "equipment": mine.name, "reading": 5}).insert()

	def test_restricted_manager_cannot_write_model_plans(self):
		self._other_company()  # the user must be limited to fewer companies than exist
		eq = self._make_equipment()
		self._as(["Card Manager"], restrict=self._m["company"])
		model_plan = frappe.get_doc(
			{
				"doctype": "Card Maintenance Plan",
				"plan_name": "MP-" + frappe.generate_hash(length=5),
				"applies_to": "Equipment Model",
				"equipment_model": "x",
				"interval_hours": 100,
			}
		)
		with self.assertRaises(frappe.PermissionError):
			model_plan.insert()
		frappe.get_doc(
			{
				"doctype": "Card Maintenance Plan",
				"plan_name": "EP-" + frappe.generate_hash(length=5),
				"applies_to": "Equipment",
				"card_equipment": eq.name,
				"interval_hours": 100,
			}
		).insert()

	def test_manual_reading_cannot_carry_system_fields(self):
		asset = self._make_asset()
		eq = self._make_equipment(**{LINK: asset})
		r = self._manual(
			eq.name,
			40,
			litres=999,
			legacy_record="FLG-FAKE",
			legacy_values="{}",
			asset=self._make_asset(),
		)
		self.assertEqual((flt(r.litres), r.legacy_record, r.legacy_values), (0, None, None))
		self.assertEqual(r.asset, asset)

	def test_future_and_back_dated_readings(self):
		eq = self._make_equipment()
		with self.assertRaisesRegex(frappe.ValidationError, "future"):
			self._manual(eq.name, 10, add_to_date(now_datetime(), days=30))
		self._manual(eq.name, 100, add_to_date(now_datetime(), days=-5))
		self._manual(eq.name, 120, add_to_date(now_datetime(), days=-1))
		back = self._manual(eq.name, 500, add_to_date(now_datetime(), days=-3))  # above a later reading
		self.assertEqual(back.status, SUSPECT)
		self.assertEqual(flt(frappe.db.get_value("Card Equipment", eq.name, "current_meter")), 120)

	def test_status_change_with_form_values_and_revalidation(self):
		eq = self._make_equipment()
		r = self._manual(eq.name, 30, add_to_date(now_datetime(), days=-1))
		doc = frappe.get_doc(METER, r.name)
		# values as a form or REST sends them (strings)
		doc.reading_time = str(doc.reading_time)
		doc.reading = str(doc.reading)
		doc.status, doc.status_reason = REJECTED, "duplicate"
		doc.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value(METER, r.name, "status"), REJECTED)
		self._manual(eq.name, 40, add_to_date(now_datetime(), hours=-12))
		jump = self._manual(eq.name, 9000)
		self.assertEqual(jump.status, SUSPECT)
		jump.reload()
		jump.status = VALID
		with self.assertRaisesRegex(frappe.ValidationError, "implausible"):
			jump.save(ignore_permissions=True)

	def test_cancelled_source_reading_stays_rejected(self):
		eq = self._make_equipment()
		order = self._order(eq.name, 15)
		order.cancel()
		r = frappe.get_doc(METER, order.meter_reading_record)
		r.status, r.status_reason = VALID, ""
		with self.assertRaisesRegex(frappe.ValidationError, "cancelled"):
			r.save(ignore_permissions=True)

	def test_last_service_follows_the_latest_valid_order(self):
		eq = self._make_equipment(service_interval_hours=250)
		frappe.db.set_value(
			"Card Equipment",
			eq.name,
			{"last_service_meter": 100, "last_service_date": add_days(today(), -40)},
		)
		a = self._order(eq.name, 300, service_date=add_days(today(), -20))
		b = self._order(eq.name, 500, service_date=add_days(today(), -5))
		old = self._order(eq.name, 200, service_date=add_days(today(), -30))  # back-dated
		last = lambda: flt(frappe.db.get_value("Card Equipment", eq.name, "last_service_meter"))  # noqa: E731
		self.assertEqual(last(), 500)
		a.cancel()
		self.assertEqual(last(), 500)
		b.cancel()
		self.assertEqual(last(), 200)  # never the cancelled order a
		old.cancel()
		self.assertEqual(last(), 100)  # the value before the first CARD order

	def test_first_service_at_meter_zero_is_a_record(self):
		eq = self._make_equipment(service_interval_hours=100)
		frappe.db.set_value("Card Equipment", eq.name, "last_service_date", add_days(today(), -1))
		self.assertEqual(compute_status(eq.name)[0], WITHIN)

	def test_litres_only_plan(self):
		eq = self._make_equipment()
		frappe.db.set_value(
			"Card Equipment", eq.name, {"last_service_meter": 10, "last_service_date": add_days(today(), -5)}
		)
		self._plan(applies_to="Equipment", card_equipment=eq.name, interval_litres=1000)
		self.assertEqual(interval_for(eq.name)[0], 0)  # no hours default
		self.assertEqual(compute_status(eq.name)[0], WITHIN)
		add_reading(eq.name, 20, add_to_date(now_datetime(), days=-1), "Diesel Fill", litres=950)
		self.assertEqual(compute_status(eq.name)[0], SOON)
		add_reading(eq.name, 30, now_datetime(), "Diesel Fill", litres=100)
		self.assertEqual(compute_status(eq.name)[0], DUE)

	def test_due_alert_skips_managers_of_other_companies(self):
		outsider = self._user(["Card Manager"], restrict=self._other_company())
		eq = self._make_equipment(service_interval_hours=100)
		frappe.db.set_value("Card Equipment", eq.name, "last_service_meter", 100)
		self._manual(eq.name, 250)
		self.assertFalse(
			frappe.db.exists("Notification Log", {"for_user": outsider, "document_name": eq.name})
		)

	def test_breakdown_cancel_keeps_the_machine_out_while_another_is_open(self):
		eq = self._make_equipment()
		start = add_to_date(now_datetime(), hours=-10)
		first = self._order(eq.name, 5, service_type="Breakdown", out_of_service_from=start)
		self._order(eq.name, 5, service_type="Repair", out_of_service_from=start)
		first.cancel()
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "status"), "في الصيانة")

	def test_settings_refuse_a_warning_above_the_interval(self):
		settings = frappe.get_single("Card Settings")
		settings.default_service_interval_hours = 100
		settings.maintenance_warn_before_hours = 150
		with self.assertRaisesRegex(frappe.ValidationError, "warning"):
			settings.save(ignore_permissions=True)

	@skipUnless(_em_installed(), "equipment_manager not installed")
	def test_archive_file_is_not_attached_to_a_shared_record(self):
		from card.legacy_equipment_manager import archive

		asset = self._make_asset()
		self._legacy_log(asset, 1, 1)
		file = frappe.get_doc("File", {"file_url": archive()["file"]})
		self.assertFalse(file.attached_to_doctype)
		self._as(["Card Manager"])
		self.assertFalse(frappe.has_permission("File", "read", file.name))


def _stock_item():
	code = "TEST-PART-" + frappe.generate_hash(length=5)
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": code,
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _bytes(content):
	return content if isinstance(content, bytes) else content.encode()
