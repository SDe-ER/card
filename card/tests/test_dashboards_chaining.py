"""CARD dashboard overrides must APPEND to the chained dashboard data, never replace it.

Frappe feeds the already-built dashboard (standard + earlier apps like HRMS) into
each ``override_doctype_dashboards`` function. These tests use a synthetic
pre-existing ``data`` to prove other apps' connections survive.
"""

from frappe import _
from frappe.tests import IntegrationTestCase

from card import dashboards


def _existing():
	return {
		"fieldname": "supplier",
		"transactions": [{"label": "Existing HRMS", "items": ["Some Existing Doctype"]}],
		"non_standard_fieldnames": {"Some Existing Doctype": "xfield"},
	}


def _labels(data):
	return [g.get("label") for g in data["transactions"]]


class TestDashboardsChaining(IntegrationTestCase):
	def _assert_appends(self, fn, expected_items, expected_fieldnames):
		data = _existing()
		result = fn(data)

		# Existing group still present, untouched, and still first.
		self.assertEqual(
			result["transactions"][0], {"label": "Existing HRMS", "items": ["Some Existing Doctype"]}
		)
		self.assertIn("Existing HRMS", _labels(result))
		# Other top-level keys preserved.
		self.assertEqual(result["fieldname"], "supplier")
		# Pre-existing non_standard_fieldnames key survived.
		self.assertEqual(result["non_standard_fieldnames"]["Some Existing Doctype"], "xfield")
		# Exactly one Card group was appended (list grew by one, appended last).
		self.assertEqual(len(result["transactions"]), 2)
		card_group = result["transactions"][-1]
		self.assertEqual(card_group["items"], expected_items)
		self.assertEqual(_labels(result).count(card_group["label"]), 1)
		# Link fieldnames registered.
		for doctype, fieldname in expected_fieldnames.items():
			self.assertEqual(result["non_standard_fieldnames"][doctype], fieldname)

	def test_supplier_appends_not_replaces(self):
		self._assert_appends(
			dashboards.supplier_dashboard,
			["Card Equipment", "Card Monthly Card", "Project Diesel Fill", "Equipment Transport"],
			{
				"Card Equipment": "supplier",
				"Card Monthly Card": "supplier",
				"Project Diesel Fill": "supplier",
				"Equipment Transport": "transport_supplier",
			},
		)

	def test_asset_appends_not_replaces(self):
		self._assert_appends(
			dashboards.asset_dashboard,
			["Card Equipment"],
			{"Card Equipment": "الأصل_في_erpnext"},
		)

	def test_project_appends_not_replaces(self):
		self._assert_appends(
			dashboards.project_dashboard,
			[
				"Card Monthly Card",
				"Card Equipment Assignment",
				"Project Diesel Fill",
				"Equipment Transport",
				"Card Equipment",
			],
			{
				"Card Monthly Card": "project",
				"Card Equipment Assignment": "project",
				"Project Diesel Fill": "project",
				"Equipment Transport": "project",
				"Card Equipment": "current_project",
			},
		)

	def test_same_list_object_is_appended_in_place(self):
		data = _existing()
		transactions = data["transactions"]
		result = dashboards.supplier_dashboard(data)
		self.assertIs(result, data)
		self.assertIs(result["transactions"], transactions)

	def test_pre_existing_fieldname_for_shared_doctype_is_not_lost_for_others(self):
		# Another app registered its own doctype mapping; CARD only sets its own keys.
		data = _existing()
		data["non_standard_fieldnames"]["Other App Doctype"] = "yfield"
		result = dashboards.project_dashboard(data)
		self.assertEqual(result["non_standard_fieldnames"]["Other App Doctype"], "yfield")
		self.assertEqual(result["non_standard_fieldnames"]["Some Existing Doctype"], "xfield")

	def test_customer_appends_not_replaces(self):
		# phase E: the Customer dashboard gains a Card group; native groups survive
		data = _existing()
		result = dashboards.customer_dashboard(data)
		self.assertIn("Existing HRMS", _labels(result))
		# the group label is the application name, CARD in every language (WS-013)
		self.assertIn(_("Card"), _labels(result))
		card_group = next(g for g in result["transactions"] if g["label"] == _("Card"))
		self.assertIn("Card Equipment Customer", card_group["items"])
		self.assertIn("Card Monthly Card", card_group["items"])
		self.assertEqual(result["non_standard_fieldnames"]["Card Equipment Customer"], "customer")
		self.assertEqual(result["non_standard_fieldnames"]["Card Monthly Card"], "customer")

	def test_dashboards_handle_empty_data(self):
		for fn in (
			dashboards.supplier_dashboard,
			dashboards.asset_dashboard,
			dashboards.project_dashboard,
			dashboards.customer_dashboard,
		):
			result = fn({})
			self.assertIsInstance(result["transactions"], list)
			self.assertEqual(len(result["transactions"]), 1)
			self.assertIsInstance(result["non_standard_fieldnames"], dict)
