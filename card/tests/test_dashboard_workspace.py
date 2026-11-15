# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""v4.10.0 CARD workspace dashboard: the money number cards and the monthly values chart refuse a user without
money read (FR-162), the supplier card equals the chart's supplier series for the same month, a company-restricted
user sees only that company, the workspace fixture imports idempotently, and every link of the workspace is in the
Card sidebar. Structure checks read the fixtures; the money checks run the real methods."""

import json
import os
from datetime import date
from unittest.mock import patch

import frappe
from frappe.modules.import_file import import_file_by_path
from frappe.tests import IntegrationTestCase

from card import card_value as cv
from card.tests.test_card_money_privacy import _user

SEPT = ("2026-09-01", "2026-09-30")
MONEY_METHODS = (
	"customer_value_last_month",
	"supplier_cost_last_month",
	"internal_value_last_month",
)


def _fixture(name):
	return os.path.join(frappe.get_app_path("card"), "fixtures", name)


def _load(name):
	with open(_fixture(name), encoding="utf-8") as fh:
		return json.load(fh)


class TestMoneyGate(IntegrationTestCase):
	"""FR-162 on the dashboard: the money methods refuse a user whose roles have no money read."""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _refused(self, user, call):
		frappe.set_user(user)
		try:
			with self.assertRaises(frappe.PermissionError):
				call()
		finally:
			frappe.set_user("Administrator")

	def test_card_operator_is_refused_by_every_money_method(self):
		operator = _user(["Card Operator"])
		self.addCleanup(frappe.delete_doc, "User", operator, ignore_permissions=True, force=True)
		for name in MONEY_METHODS:
			with self.subTest(method=name):
				self._refused(operator, lambda n=name: getattr(cv, n)())

	def test_card_operator_is_refused_by_the_monthly_values_chart(self):
		operator = _user(["Card Operator"])
		self.addCleanup(frappe.delete_doc, "User", operator, ignore_permissions=True, force=True)
		self._refused(
			operator,
			lambda: cv.chart_data(frappe._dict(timespan="Select Date Range"), {}, *SEPT),
		)

	def test_card_supervisor_is_refused_by_the_money_methods(self):
		supervisor = _user(["Card Supervisor"])
		self.addCleanup(frappe.delete_doc, "User", supervisor, ignore_permissions=True, force=True)
		for name in MONEY_METHODS:
			with self.subTest(method=name):
				self._refused(supervisor, lambda n=name: getattr(cv, n)())

	def test_money_reader_gets_the_value(self):
		reader = _user(["Card Manager"])
		self.addCleanup(frappe.delete_doc, "User", reader, ignore_permissions=True, force=True)
		frappe.set_user(reader)
		try:
			for name in MONEY_METHODS:
				with self.subTest(method=name):
					self.assertIn("value", getattr(cv, name)())
		finally:
			frappe.set_user("Administrator")


class TestSupplierCardMatchesChart(IntegrationTestCase):
	"""The supplier Number Card and the chart's supplier series read the same totals for the same month."""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_supplier_card_equals_chart_supplier_series_for_the_same_month(self):
		september = (date(2026, 9, 1), date(2026, 9, 30))
		with patch("card.card_value._last_month", return_value=september):
			card_value = cv.supplier_cost_last_month()["value"]
		chart = cv.chart_data(frappe._dict(timespan="Select Date Range"), {}, *SEPT)
		supplier = next(ds for ds in chart["datasets"] if ds["name"] == cv.series_labels()["supplier"])
		self.assertEqual(round(float(card_value), 2), round(float(supplier["values"][-1]), 2))


class TestDashboardCompanyScope(IntegrationTestCase):
	"""A company-restricted user sees the supplier card only for that company (the list is user-permission scoped)."""

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_restricted_user_sees_no_more_than_the_unrestricted_total(self):
		company = frappe.db.get_single_value("Global Defaults", "default_company")
		if not company:
			self.skipTest("no default company on this site")
		unrestricted = _user(["Card Manager"])
		restricted = _user(["Card Manager"], restrict=company)
		self.addCleanup(frappe.delete_doc, "User", unrestricted, ignore_permissions=True, force=True)
		self.addCleanup(frappe.delete_doc, "User", restricted, ignore_permissions=True, force=True)
		frappe.set_user(unrestricted)
		try:
			everything = float(cv.supplier_cost_last_month()["value"])
		finally:
			frappe.set_user("Administrator")
		frappe.set_user(restricted)
		try:
			mine = float(cv.supplier_cost_last_month()["value"])
		finally:
			frappe.set_user("Administrator")
		self.assertLessEqual(mine, everything)


class TestWorkspaceFixture(IntegrationTestCase):
	"""The workspace fixture is structure-checked from the files and imports idempotently."""

	def _workspace(self):
		return next(w for w in _load("workspace.json") if w.get("name") == "Card")

	def test_every_block_reference_exists_in_its_fixture(self):
		ws = self._workspace()
		numbers = {n["name"] for n in _load("number_card.json")}
		charts = {c["name"] for c in _load("dashboard_chart.json")}
		for row in ws.get("number_cards", []):
			self.assertIn(row["number_card_name"], numbers)
		for row in ws.get("charts", []):
			self.assertIn(row["chart_name"], charts)

	def test_every_link_of_the_workspace_is_in_the_card_sidebar(self):
		ws = self._workspace()
		sidebar = next(s for s in _load("workspace_sidebar.json") if s.get("name") == "Card")
		listed = {i.get("link_to") for i in sidebar.get("items", []) if i.get("link_to")}
		urls = {i.get("url") for i in sidebar.get("items", []) if i.get("url")}
		for row in ws.get("links", []):
			if row.get("type") == "Card Break":
				continue
			if row.get("link_type") == "URL":
				self.assertIn(row["url"], urls, row.get("label"))
				continue
			self.assertIn(row["link_to"], listed, row.get("label"))
		for row in ws.get("shortcuts", []):
			if row.get("link_to"):
				self.assertIn(row["link_to"], listed, row.get("label"))

	def test_fixture_import_is_idempotent(self):
		path = _fixture("workspace.json")
		import_file_by_path(path, force=True)
		first = frappe.db.get_value("Workspace", "Card", "modified")
		import_file_by_path(path, force=True)
		second = frappe.db.get_value("Workspace", "Card", "modified")
		self.assertEqual(str(first), str(second))
