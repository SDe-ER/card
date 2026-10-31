# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Financial privacy of Card Equipment (Owner decision 2026-10-31): the Asset purchase value, the internal hourly
rate and the Asset cost center are read only by System Manager, Card Manager and Accounts Manager (permlevel 2);
the supplier's hourly rate stays with the commercial fields (permlevel 1). Card User and Card Supervisor do not
receive them through the form, the REST API, list or report queries, or the change history. Nothing is deleted."""

import frappe
from frappe.client import get as rest_get
from frappe.client import get_list as rest_get_list
from frappe.desk.form.load import getdoc
from frappe.tests import IntegrationTestCase

from card.field_privacy import MASKED
from card.tests import test_asset_link as link_tests
from card.tests.test_asset_link import LINK
from card.tests.test_controllers import _ensure_masters

RESTRICTED = ("asset_purchase_value", "internal_hourly_rate", "asset_cost_center", "cost_center")


class TestEquipmentFinancialPrivacy(IntegrationTestCase):
	# the Asset fixtures of the O2a link tests (module imported, so its tests are not collected twice)
	_fixed_asset_account = link_tests.TestAssetLink._fixed_asset_account
	_asset_masters = link_tests.TestAssetLink._asset_masters
	_make_asset = link_tests.TestAssetLink._make_asset
	_make_equipment = link_tests.TestAssetLink._make_equipment
	_user = link_tests.TestAssetLink._user
	_other_company = link_tests.TestAssetLink._other_company

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _equipment(self):
		asset = self._make_asset()
		cost_center = frappe.db.get_value(
			"Cost Center", {"company": self._m["company"], "is_group": 0, "disabled": 0}, "name"
		)
		eq = self._make_equipment(**{LINK: asset, "internal_hourly_rate": 250, "cost_center": cost_center})
		eq.reload()
		self.assertTrue(eq.asset_purchase_value)  # the copy of the Asset's value is kept on the record
		self.assertTrue(eq.cost_center)
		return eq

	def _as(self, roles, company=None):
		frappe.set_user(self._user(roles, restrict=company or self._m["company"]))

	def _paths(self, name):
		"""What the user receives for the equipment through the form, REST and list queries."""
		getdoc("Card Equipment", name)
		form = frappe.response.docs[0]
		rest = rest_get("Card Equipment", name)
		star = rest_get_list("Card Equipment", fields=["*"], filters={"name": name})[0]
		try:
			explicit = frappe.get_list(
				"Card Equipment", fields=["name", *RESTRICTED, "approved_hourly_rate"], filters={"name": name}
			)[0]
		except frappe.PermissionError:
			explicit = {}
		return {"form": form, "rest": rest, "list *": star, "list fields": explicit}

	def test_operational_roles_never_receive_the_financial_fields(self):
		eq = self._equipment()
		for role in ("Card User", "Card Supervisor"):
			with self.subTest(role=role):
				self._as([role])
				for path, values in self._paths(eq.name).items():
					for field in RESTRICTED:
						self.assertFalse(values.get(field), f"{role} {path} {field}")
				frappe.set_user("Administrator")

	def test_supervisor_does_not_receive_the_supplier_hourly_rate(self):
		eq = self._equipment()
		frappe.db.set_value("Card Equipment", eq.name, "approved_hourly_rate", 75)
		self._as(["Card Supervisor"])
		for path, values in self._paths(eq.name).items():
			self.assertFalse(values.get("approved_hourly_rate"), path)

	def test_managers_and_accountants_still_read_them(self):
		eq = self._equipment()
		for role in ("Card Manager", "Accounts Manager"):
			with self.subTest(role=role):
				self._as([role])
				rest = rest_get("Card Equipment", eq.name)
				self.assertEqual(rest.get("internal_hourly_rate"), 250)
				self.assertEqual(rest.get("asset_purchase_value"), eq.asset_purchase_value)
				self.assertEqual(rest.get("asset_cost_center"), eq.asset_cost_center)
				self.assertEqual(rest.get("cost_center"), eq.cost_center)
				frappe.set_user("Administrator")

	def test_other_company_and_unauthorized_users_are_refused(self):
		eq = self._equipment()
		self._as(["Card Manager"], company=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			rest_get("Card Equipment", eq.name)
		frappe.set_user("Administrator")
		self._as([])  # a user without any CARD role
		with self.assertRaises(frappe.PermissionError):
			rest_get("Card Equipment", eq.name)

	def test_change_history_keeps_who_and_when_but_not_the_values(self):
		eq = self._equipment()
		manager = self._user(["Card Manager"], restrict=self._m["company"])
		frappe.set_user(manager)
		version = frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Card Equipment",
				"docname": eq.name,
				"data": frappe.as_json(
					{
						"changed": [
							["internal_hourly_rate", 250, 400],
							["asset_purchase_value", 1000, 2000],
							["approved_hourly_rate", 50, 75],
							["plate_no", "A-1", "A-2"],
						],
						"added": [],
						"removed": [],
						"row_changed": [],
					}
				),
			}
		).insert(ignore_permissions=True)  # as frappe inserts every Version
		frappe.set_user("Administrator")
		changes = {c[0]: c[1:] for c in frappe.parse_json(version.reload().data)["changed"]}
		self.assertEqual(changes["internal_hourly_rate"], [MASKED, MASKED])
		self.assertEqual(changes["asset_purchase_value"], [MASKED, MASKED])
		self.assertEqual(
			changes["approved_hourly_rate"], [MASKED, MASKED]
		)  # level 1 is above level-0 readers
		self.assertEqual(changes["plate_no"], ["A-1", "A-2"])  # operational changes keep their values
		self.assertEqual(version.owner, manager)
		self.assertNotIn("400", version.data)
		other = frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Card Monthly Card",
				"docname": "X",
				"data": frappe.as_json({"changed": [["internal_hourly_rate", 1, 2]]}),
			}
		).insert(ignore_permissions=True)
		self.assertIn("internal_hourly_rate", other.data)  # other doctypes are untouched
		self.assertNotIn(MASKED, other.data)

	def test_field_levels_and_permissions(self):
		meta = frappe.get_meta("Card Equipment")
		for field in RESTRICTED:
			self.assertEqual(meta.get_field(field).permlevel, 2, field)
		self.assertEqual(meta.get_field("approved_hourly_rate").permlevel, 1)
		readers = {p.role for p in meta.permissions if p.permlevel == 2 and p.read}
		self.assertEqual(readers, {"System Manager", "Card Manager", "Accounts Manager"})
