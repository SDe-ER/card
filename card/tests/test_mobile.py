# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""CARD Mobile (/cdms): who may open it, the session context, the page boot, the service worker
route, the apps screen entries (G4) and the operator item search (G1)."""

import importlib
import os
import tempfile
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from card import materials, mobile
from card.pwa import ServiceWorkerRenderer
from card.tests.test_controllers import _ensure_masters

cdms_page = importlib.import_module("card.www.cdms")


class TestCardMobile(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.lang = "en"
		frappe.db.rollback()

	# ---------- builders ----------
	def _user(self, prefix, roles, language=None):
		email = f"mob-{prefix}-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": prefix,
				"send_welcome_email": 0,
				"language": language,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		return email

	def _employee(self, user, status="Active"):
		if not frappe.db.exists("Gender", "Male"):
			frappe.get_doc({"doctype": "Gender", "gender": "Male"}).insert(ignore_permissions=True)
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": f"Mob {self.token}",
				"gender": "Male",
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": status,
				"user_id": user,
			}
		).insert(ignore_permissions=True)

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	# ---------- access ----------
	def test_guest_and_users_without_a_card_role_cannot_open_the_app(self):
		self.assertFalse(self._as("Guest", mobile.has_app_permission))
		outsider = self._user("out", [])
		self._employee(outsider)
		self.assertFalse(self._as(outsider, mobile.has_app_permission))
		with self.assertRaises(frappe.PermissionError):
			self._as(outsider, mobile.get_session_context)

	def test_operator_with_an_active_employee_opens_the_app(self):
		user = self._user("op", ["Card Operator"])
		emp = self._employee(user)
		self.assertTrue(self._as(user, mobile.has_app_permission))
		ctx = self._as(user, mobile.get_session_context)
		self.assertEqual(ctx["employee"]["name"], emp.name)
		self.assertEqual(ctx["roles"], ["Card Operator"])
		self.assertEqual(ctx["card_version"], importlib.import_module("card").__version__)

	def test_website_user_operator_without_employee_gets_no_employee(self):
		user = self._user("web", ["Card Operator"])
		self.assertEqual(frappe.db.get_value("User", user, "user_type"), "Website User")
		self.assertFalse(self._as(user, mobile.has_app_permission))
		self.assertTrue(self._as(user, mobile.has_app_permission, require_employee=False))
		self.assertIsNone(self._as(user, mobile.get_session_context)["employee"])

	def test_employee_left_closes_the_app(self):
		# ERPNext disables the user of an Employee who left; the app also stops finding him
		user = self._user("left", ["Card Operator"])
		emp = self._employee(user)
		emp.status = "Left"
		emp.relieving_date = "2026-01-31"
		emp.save(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("User", user, "enabled"), 0)
		self.assertIsNone(mobile.active_employee(user))

	# ---------- apps screen (G4) ----------
	def test_apps_screen_desk_entry_hidden_from_operators(self):
		self.assertTrue(mobile.has_desk_app_permission())  # Administrator
		web = self._user("web", ["Card Operator"])
		self.assertFalse(self._as(web, mobile.has_desk_app_permission))
		op = self._user("op", ["Card Operator"])
		self._employee(op)  # ERPNext adds the Employee role: a System User without CARD Desk reads
		self.assertEqual(frappe.db.get_value("User", op, "user_type"), "System User")
		self.assertFalse(self._as(op, mobile.has_desk_app_permission))
		manager = self._user("mgr", ["Card Manager"])
		self.assertTrue(self._as(manager, mobile.has_desk_app_permission))
		# custody users work in CARD Desk through Employee Tool Custody only
		stock = self._user("stock", ["Stock Manager"])
		self.assertTrue(self._as(stock, mobile.has_desk_app_permission))

	def test_apps_screen_entries_and_routes(self):
		entries = frappe.get_hooks("add_to_apps_screen", app_name="card")
		self.assertEqual([e["route"] for e in entries], ["/app/card", "/cdms"])
		self.assertEqual(entries[0]["has_permission"], "card.mobile.has_desk_app_permission")
		self.assertEqual(entries[1]["has_permission"], "card.mobile.has_app_permission")
		rules = frappe.get_hooks("website_route_rules", app_name="card")
		self.assertEqual(
			rules,
			[
				{"from_route": "/cdms/sw.js", "to_route": "cdms-sw"},
				{"from_route": "/cdms/<path:app_path>", "to_route": "cdms"},
			],
		)

	# ---------- page boot ----------
	def test_page_boot_for_a_guest_has_a_csrf_token_and_direction(self):
		frappe.set_user("Guest")
		frappe.local.lang = "en"
		ctx = cdms_page.get_context(frappe._dict())
		self.assertTrue(ctx.boot["csrf_token"])
		self.assertEqual((ctx.boot["lang"], ctx.boot["dir"]), ("en", "ltr"))

	def test_page_boot_is_rtl_for_arabic_and_urdu(self):
		user = self._user("ar", ["Card Operator"])
		self._employee(user)
		frappe.set_user(user)
		for lang in ("ar", "ur"):
			frappe.local.lang = lang
			ctx = cdms_page.get_context(frappe._dict())
			self.assertEqual(ctx.boot["dir"], "rtl")
			self.assertIsInstance(ctx.boot["__messages"], dict)
		frappe.local.lang = "bn"
		self.assertEqual(cdms_page.get_context(frappe._dict()).boot["dir"], "ltr")

	def test_page_boot_carries_card_mobile_context_translations(self):
		# generic words are translated under the context "Card Mobile" only (frappe keys them
		# "msgid:context"), so the plain Frappe translation of "Home" stays untouched
		# Card's .mo is built from this checkout's ar.po into a temporary folder: Frappe's own
		# compile writes the bench-wide sites/assets/locale that every site of the bench reads.
		from pathlib import Path

		from babel.messages.mofile import write_mo
		from babel.messages.pofile import read_po
		from frappe.gettext import translate
		from frappe.translate import clear_cache

		real_mo_path = translate.get_mo_path
		with tempfile.TemporaryDirectory() as tmp:
			card_mo = Path(tmp, "card.mo")
			with open(frappe.get_app_path("card", "locale", "ar.po"), "rb") as po, open(card_mo, "wb") as mo:
				write_mo(mo, read_po(po, locale="ar"))

			def mo_path(app, locale=None):
				return card_mo if app == "card" and locale == "ar" else real_mo_path(app, locale)

			with patch.object(translate, "get_mo_path", side_effect=mo_path):
				clear_cache()
				frappe.local.lang = "ar"
				messages = cdms_page.get_context(frappe._dict()).boot["__messages"]
			clear_cache()
		self.assertEqual(messages.get("Home:Card Mobile"), "الرئيسية")
		self.assertEqual(messages.get("My requests"), "طلباتي")
		self.assertNotEqual(messages.get("Home"), "الرئيسية")

	def test_page_refuses_a_signed_in_user_without_a_card_role(self):
		outsider = self._user("out", [])
		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			cdms_page.get_context(frappe._dict())

	# ---------- service worker ----------
	def test_service_worker_route(self):
		with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
			f.write("self.skipWaiting()")
		try:
			with patch.object(ServiceWorkerRenderer, "file_path", staticmethod(lambda: f.name)):
				self.assertTrue(ServiceWorkerRenderer("cdms-sw").can_render())
				self.assertFalse(ServiceWorkerRenderer("cdms").can_render())
				response = ServiceWorkerRenderer("cdms-sw").render()
			self.assertEqual(response.mimetype, "application/javascript")
			self.assertEqual(response.headers["Cache-Control"], "no-cache")
			self.assertEqual(response.get_data(as_text=True), "self.skipWaiting()")
		finally:
			os.unlink(f.name)

	def test_service_worker_route_without_a_build(self):
		with patch.object(ServiceWorkerRenderer, "file_path", staticmethod(lambda: "/nonexistent/sw.js")):
			self.assertFalse(ServiceWorkerRenderer("cdms-sw").can_render())

	# ---------- item search (G1) ----------
	def _item(self, name, **values):
		code = f"MOB-{name}-{self.token}"
		doc = {
			"doctype": "Item",
			"item_code": code,
			"item_name": code,
			"item_group": "All Item Groups",
			"stock_uom": "Nos",
			"is_stock_item": 1,
		}
		doc.update(values)
		frappe.get_doc(doc).insert(ignore_permissions=True)
		return code

	def test_operator_item_search_lists_only_stock_or_purchase_items(self):
		stock = self._item("STOCK")
		bought = self._item("BOUGHT", is_stock_item=0, is_purchase_item=1)
		service = self._item("SERVICE", is_stock_item=0, is_purchase_item=0)
		disabled = self._item("OFF", disabled=1)
		user = self._user("op", ["Card Operator"])
		found = {r["item_code"] for r in self._as(user, materials.search_items, self.token)}
		self.assertIn(stock, found)
		self.assertIn(bought, found)
		self.assertNotIn(service, found)
		self.assertNotIn(disabled, found)
		row = self._as(user, materials.search_items, stock)[0]
		self.assertEqual(set(row), {"item_code", "item_name", "stock_uom"})
