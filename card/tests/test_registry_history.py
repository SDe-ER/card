# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#23 / Owner decision 2026-10-17: the CARD party registries' change history
(Versions holding pre-1.2.2 party-wide figures) is kept unchanged as audit
history and is not exposed. A Property Setter cannot turn track_changes on for
a registry — on insert or on any later save, whatever the path (Customize Form,
REST, frappe.client); the Version records stay readable by System Manager only.
All data is per-test and rolled back."""

import json

import frappe
from frappe.api.v1 import create_doc, document_list, read_doc, update_doc
from frappe.client import get as client_get
from frappe.client import get_list as client_get_list
from frappe.client import get_value as client_get_value
from frappe.client import insert as client_insert
from frappe.client import set_value as client_set_value
from frappe.desk.form import load
from frappe.desk.reportview import get as reportview_get
from frappe.tests import IntegrationTestCase

REGISTRY_DOCTYPES = ("Card Equipment Supplier", "Card Equipment Customer")
REFUSED = "Change tracking cannot be turned on"
FIGURE = "123456.78"  # a legacy party-wide total in the seeded Version


class TestRegistryHistory(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.supplier = (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": "TEST-RH-SUP-" + frappe.generate_hash(length=6),
					"supplier_group": frappe.get_all(
						"Supplier Group", filters={"is_group": 0}, pluck="name", limit=1
					)[0],
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		if not frappe.db.exists("Card Equipment Supplier", self.supplier):
			frappe.get_doc({"doctype": "Card Equipment Supplier", "supplier": self.supplier}).insert(
				ignore_permissions=True
			)
		self.version = frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Card Equipment Supplier",
				"docname": self.supplier,
				"data": json.dumps({"changed": [["total_net", 0, float(FIGURE)], ["card_count", 0, 9]]}),
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()
		for doctype in (*REGISTRY_DOCTYPES, "Card Equipment Type"):
			frappe.clear_cache(doctype=doctype)

	# ---- helpers ----
	def _login(self, roles):
		email = f"rh-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "RH",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		return email

	def _rest(self, fn, *args, data=None, form=None):
		frappe.local.form_dict = frappe._dict(form or {})
		if data is not None:
			frappe.local.form_dict.data = json.dumps(data)
		try:
			return fn(*args)
		finally:
			frappe.local.form_dict = frappe._dict()

	def _setter(self, doctype, value, prop="track_changes"):
		return {
			"doctype": "Property Setter",
			"doctype_or_field": "DocType",
			"doc_type": doctype,
			"property": prop,
			"property_type": "Check",
			"value": str(value),
		}

	def _track_changes(self, doctype):
		frappe.clear_cache(doctype=doctype)
		return frappe.get_meta(doctype).track_changes

	# ---- the guard: creation ----
	def test_turning_tracking_on_is_refused_on_every_creation_path(self):
		for registry in REGISTRY_DOCTYPES:
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				frappe.get_doc(self._setter(registry, 1)).insert(ignore_permissions=True)
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				# the Customize Form path
				frappe.make_property_setter(
					{
						"doctype": registry,
						"doctype_or_field": "DocType",
						"property": "track_changes",
						"value": 1,
						"property_type": "Check",
					}
				)
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				# a server-side caller skipping validation (before_validate still runs)
				frappe.make_property_setter(
					{
						"doctype": registry,
						"doctype_or_field": "DocType",
						"property": "track_changes",
						"value": 1,
						"property_type": "Check",
					},
					ignore_validate=True,
				)
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				self._rest(create_doc, "Property Setter", data=self._setter(registry, 1))
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				client_insert(self._setter(registry, 1))
			self.assertFalse(self._track_changes(registry), registry)

	# ---- the guard: modification of an existing setter ----
	def test_turning_tracking_on_is_refused_on_every_update_path(self):
		for registry in REGISTRY_DOCTYPES:
			setter = frappe.get_doc(self._setter(registry, 0)).insert(ignore_permissions=True)
			doc = frappe.get_doc("Property Setter", setter.name)
			doc.value = "1"
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				doc.save(ignore_permissions=True)
			doc = frappe.get_doc("Property Setter", setter.name)
			doc.value = "1"
			doc.flags.ignore_validate = True
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				doc.save(ignore_permissions=True)
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				self._rest(update_doc, "Property Setter", setter.name, data={"value": "1"})
			with self.assertRaisesRegex(frappe.ValidationError, REFUSED, msg=registry):
				client_set_value("Property Setter", setter.name, "value", "1")
			self.assertEqual(frappe.db.get_value("Property Setter", setter.name, "value"), "0")
			self.assertFalse(self._track_changes(registry), registry)

	def test_other_properties_and_doctypes_are_not_affected(self):
		# tracking off on a registry, another property on a registry, tracking on elsewhere
		frappe.get_doc(self._setter("Card Equipment Supplier", 0)).insert(ignore_permissions=True)
		frappe.get_doc(
			dict(self._setter("Card Equipment Supplier", 1, prop="allow_copy"), property_type="Check")
		).insert(ignore_permissions=True)
		frappe.get_doc(self._setter("Card Equipment Type", 1)).insert(ignore_permissions=True)
		self.assertTrue(self._track_changes("Card Equipment Type"))

	def test_registries_do_not_track_changes(self):
		for registry in REGISTRY_DOCTYPES:
			self.assertFalse(self._track_changes(registry), registry)

	# ---- exposure: history kept, readable for audit only ----
	def test_only_system_manager_and_administrator_may_read_versions(self):
		readers = {
			p.role
			for doctype in ("DocPerm", "Custom DocPerm")
			for p in frappe.get_all(doctype, filters={"parent": "Version", "read": 1}, fields=["role"])
		}
		self.assertLessEqual(readers, {"System Manager", "Administrator"})
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "Version"}))

	def test_card_roles_cannot_read_the_legacy_figures_on_any_path(self):
		name = self.version.name
		paths = {
			"REST GET /api/resource/Version/<name>": lambda: read_doc("Version", name),
			"REST GET /api/resource/Version": lambda: self._rest(
				document_list, "Version", form={"fields": '["name","data"]'}
			),
			"frappe.client.get": lambda: client_get("Version", name),
			"frappe.client.get_list": lambda: client_get_list("Version", fields=["name", "data"]),
			"frappe.client.get_value": lambda: client_get_value("Version", "data", {"name": name}),
			"list view (reportview)": lambda: self._rest(
				reportview_get, form={"doctype": "Version", "fields": '["name","data"]'}
			),
		}
		for role in ("Card User", "Card Manager", "Accounts Manager"):
			self._login([role])
			for label, fn in paths.items():
				with self.assertRaises(frappe.PermissionError, msg=f"{role} {label}"):
					fn()
			# Desk form load of the registry: no Versions in docinfo
			frappe.response.pop("docinfo", None)
			load.getdoc("Card Equipment Supplier", self.supplier)
			self.assertNotIn(FIGURE, json.dumps(frappe.response.get("docinfo"), default=str), role)
			frappe.set_user("Administrator")

	def test_system_manager_keeps_audit_access(self):
		self._login(["System Manager"])
		self.assertIn(FIGURE, client_get("Version", self.version.name)["data"])
		self.assertIn(FIGURE, read_doc("Version", self.version.name).data)  # REST handler
		self.assertTrue(
			client_get_list(
				"Version", filters={"ref_doctype": "Card Equipment Supplier", "docname": self.supplier}
			)
		)
