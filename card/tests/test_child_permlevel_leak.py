# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-148 (SEC-1): a child-table row is read at the child DocType's own field levels.

Frappe 16 checks the fields of a child row against the child DocType's own ``permlevel`` on the child list routes
(``frappe.client.get_list`` / ``get_value`` with ``parent=``, ``frappe.desk.reportview`` with a child column or a
child filter). It does not apply the level of the parent's Table field there. A Table field above level 0 whose child
DocType has fields at a lower level therefore reached every level-0 reader of the parent through those routes.

The guard test fails for any such table in CARD (now or later); the probes check, for every CARD role and Accounts
Manager, that a level-0-only reader of the parent receives no value of the fixed tables through those routes and the
change history, and that a reader of the table's level still reads it in the form."""

import glob
import json
import os

import frappe
import frappe.client
from frappe.desk import reportview
from frappe.tests import IntegrationTestCase

from card.install import CARD_ROLES
from card.tests.test_controllers import _ensure_masters

TABLE_FIELDTYPES = ("Table", "Table MultiSelect")
LAYOUT_FIELDTYPES = ("Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold")
PROBE_ROLES = (*CARD_ROLES, "Accounts Manager", "Accounts User")
OTHER = "TEST-FR148-OTHER-COMPANY"  # a company name that appears only in crafted Version data
# a test-only role (rolled back with each test) that reads or writes a parent at level 0 only, as a Custom DocPerm
# could give on a site; no role of the code reads Card Settings at level 0 without level 2
LEVEL_0_ROLE = "TEST FR148 Level 0"
# the tables FR-148 fixed: (parent, table field)
FIXED = (
	("Card Equipment", "components"),
	("Card Settings", "diesel_price_schedule"),
	("Card Settings", "project_transport_prices"),
	("Card Settings", "location_cost_centers"),
)


def _card_doctypes():
	"""Every CARD DocType JSON, by name."""
	root = frappe.get_app_path("card")
	docs = {}
	for path in glob.glob(os.path.join(root, "**", "doctype", "*", "*.json"), recursive=True):
		with open(path, encoding="utf-8") as f:
			data = json.load(f)
		if data.get("doctype") == "DocType":
			docs[data["name"]] = data
	return docs


def _level(df):
	return int(df.get("permlevel") or 0)


def enumerate_child_permlevel_gaps(docs=None):
	"""[(parent, table field, table level, child, [child fields below that level])] for every CARD Table or
	Table MultiSelect field above level 0 whose child DocType has a data field at a lower level."""
	docs = docs or _card_doctypes()
	gaps = []
	for name, data in sorted(docs.items()):
		for df in data.get("fields", []):
			if df.get("fieldtype") not in TABLE_FIELDTYPES or not _level(df):
				continue
			child = docs.get(df.get("options"))
			if not child:
				continue
			lower = [
				c["fieldname"]
				for c in child.get("fields", [])
				if c.get("fieldtype") not in LAYOUT_FIELDTYPES and _level(c) < _level(df)
			]
			if lower:
				gaps.append((name, df["fieldname"], _level(df), child["name"], lower))
	return gaps


def high_level_tables(docs=None):
	"""[(parent, table field, level, child)] for every CARD table field above level 0."""
	docs = docs or _card_doctypes()
	return [
		(name, df["fieldname"], _level(df), df["options"])
		for name, data in sorted(docs.items())
		for df in data.get("fields", [])
		if df.get("fieldtype") in TABLE_FIELDTYPES and _level(df) and df.get("options") in docs
	]


class TestChildPermlevelGuard(IntegrationTestCase):
	"""Static guard, driven by the enumeration of every CARD DocType."""

	def test_no_table_above_level_0_has_a_child_field_below_its_level(self):
		self.assertEqual(enumerate_child_permlevel_gaps(), [])

	def test_the_installed_meta_matches(self):
		"""The same rule on the site's meta (it includes Custom Fields and Property Setters)."""
		for parent, fieldname, _lvl, child in high_level_tables():
			table = frappe.get_meta(parent).get_field(fieldname)
			for df in frappe.get_meta(child).fields:
				if df.fieldtype in LAYOUT_FIELDTYPES:
					continue
				with self.subTest(parent=parent, table=fieldname, field=df.fieldname):
					self.assertGreaterEqual(int(df.permlevel or 0), int(table.permlevel or 0))

	def test_a_child_doctype_is_not_shared_by_tables_at_different_levels(self):
		"""Raising a child's levels fits one parent level only; a child shared at two levels needs a split."""
		levels = {}
		for _name, data in _card_doctypes().items():
			for df in data.get("fields", []):
				if df.get("fieldtype") in TABLE_FIELDTYPES:
					levels.setdefault(df.get("options"), set()).add(_level(df))
		self.assertEqual({child: lv for child, lv in levels.items() if len(lv) > 1}, {})

	def test_the_guard_detects_a_gap(self):
		"""The enumeration is not vacuous: a level-1 table with a level-0 child field is reported."""
		docs = {
			"P": {
				"name": "P",
				"fields": [{"fieldname": "rows", "fieldtype": "Table", "options": "C", "permlevel": 1}],
			},
			"C": {"name": "C", "fields": [{"fieldname": "amount", "fieldtype": "Currency"}]},
		}
		self.assertEqual(enumerate_child_permlevel_gaps(docs), [("P", "rows", 1, "C", ["amount"])])

	def test_every_fixed_table_is_still_above_level_0(self):
		tables = {(p, f) for p, f, _lvl, _child in high_level_tables()}
		for parent_field in FIXED:
			self.assertIn(parent_field, tables)


class ChildPermlevelFixtures(IntegrationTestCase):
	"""Data, users and routes shared by the FR-148 probes (no tests of its own)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.users = {}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for doctype in ("Card Settings", "Card Equipment"):
			frappe.clear_cache(doctype=doctype)

	def _grant_level_0(self, *doctypes, write=0):
		"""Give LEVEL_0_ROLE level-0 read (and write) on ``doctypes`` through Custom DocPerms; rolled back."""
		from frappe.permissions import setup_custom_perms

		if not frappe.db.exists("Role", LEVEL_0_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": LEVEL_0_ROLE, "desk_access": 1}).insert(
				ignore_permissions=True
			)
		for doctype in doctypes:
			setup_custom_perms(doctype)
			frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": doctype,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": LEVEL_0_ROLE,
					"permlevel": 0,
					"read": 1,
					"write": write,
				}
			).insert(ignore_permissions=True)
			frappe.clear_cache(doctype=doctype)
		return self._user(LEVEL_0_ROLE)

	# ---- data ----
	def _user(self, role):
		if role not in self.users:
			email = f"fr148-{frappe.generate_hash(length=8)}@example.com"
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": "FR148",
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}
			).insert(ignore_permissions=True)
			frappe.clear_cache(user=email)
			self.users[role] = email
		return self.users[role]

	def _equipment(self, **kw):
		d = frappe.new_doc("Card Equipment")
		d.update(
			{
				"company": self.company,
				"equipment_type": self._m["etype"],
				"ownership": "ملك",
				"equipment_name": "TEST-FR148-" + frappe.generate_hash(length=6),
				"rate_type": "باليوم",
				"rate": 750,
				"daily_hours": 10,
			}
		)
		components = kw.pop("components", None)
		d.update(kw)
		for row in components or []:
			d.append("components", row)
		d.insert(ignore_permissions=True)
		return d

	def _child(self, doctype, parent, parenttype, parentfield, **values):
		row = frappe.get_doc(
			{
				"doctype": doctype,
				"parent": parent,
				"parenttype": parenttype,
				"parentfield": parentfield,
				"idx": 900,
				**values,
			}
		)
		row.db_insert()
		return row

	def _fixtures(self):
		"""Per fixed table: (parent doctype, parent name, child, table field, fields, markers, filter)."""
		piece = self._equipment().name
		marker = "FR148-" + self.token
		unit = self._equipment(
			is_unit=1,
			components=[{"component": piece, "role": marker + "-R", "change_reason": marker + "-C"}],
		).name
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-FR148-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		location = frappe.get_doc(
			{"doctype": "Location", "location_name": "TEST-FR148-L-" + self.token}
		).insert(ignore_permissions=True)
		cost_center = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		settings = ("Card Settings", "Card Settings")
		self._child(
			"Card Diesel Price",
			*settings,
			"diesel_price_schedule",
			company=self.company,
			valid_from="2031-07-13",
			unit_price=4321.987,
		)
		self._child(
			"Card Project Transport Price",
			*settings,
			"project_transport_prices",
			project=project.name,
			amount=98765.43,
		)
		self._child(
			"Card Location Cost Center",
			*settings,
			"location_cost_centers",
			company=self.company,
			location=location.name,
			cost_center=cost_center,
		)
		return {
			("Card Equipment", "components"): (
				unit,
				"Card Equipment Component",
				["component", "role", "change_reason"],
				[piece, marker + "-R", marker + "-C"],
				["change_reason", "=", marker + "-C"],
			),
			("Card Settings", "diesel_price_schedule"): (
				"Card Settings",
				"Card Diesel Price",
				["company", "valid_from", "unit_price"],
				["2031-07-13", "4321.987"],
				["unit_price", "=", 4321.987],
			),
			("Card Settings", "project_transport_prices"): (
				"Card Settings",
				"Card Project Transport Price",
				["project", "amount"],
				[project.name, "98765.43"],
				["amount", "=", 98765.43],
			),
			("Card Settings", "location_cost_centers"): (
				"Card Settings",
				"Card Location Cost Center",
				["company", "location", "cost_center"],
				[location.name],
				["location", "=", location.name],
			),
		}

	# ---- routes ----
	@staticmethod
	def _call(fn):
		"""The reply of a route, or None when it refuses (a refusal leaks nothing)."""
		frappe.db.savepoint("fr148_route")
		try:
			return fn()
		except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
			frappe.db.rollback(save_point="fr148_route")
			frappe.clear_messages()
			return None

	def _child_routes(self, parent, name, child, fieldname, fields, oracle):
		filters = {"parent": name, "parentfield": fieldname}
		replies = {
			"client.get_list": self._call(
				lambda: frappe.client.get_list(child, parent=parent, fields=list(fields), filters=filters)
			),
			"client.get_value": self._call(
				lambda: frappe.client.get_value(child, list(fields), filters=filters, parent=parent)
			),
		}
		if frappe.get_meta(parent).issingle:
			# report view lists no Single (it has no table of its own)
			return replies, None
		replies["reportview child column"] = self._call(
			lambda: reportview.execute(
				parent, fields=[f"`tab{child}`.`{f}`" for f in fields], filters={"name": name}
			)
		)
		hit = self._call(lambda: reportview.execute(parent, fields=["name"], filters=[[child, *oracle]]))
		return replies, hit

	@staticmethod
	def _form(parent, name, fieldname):
		import frappe.client as client

		try:
			doc = client.get(parent, name)
		except frappe.PermissionError:
			frappe.clear_messages()
			return None
		return doc.get(fieldname) or []

	def _levels(self, parent, role):
		return {
			int(p.permlevel or 0) for p in frappe.get_meta(parent).permissions if p.role == role and p.read
		}


class TestChildPermlevelProbes(ChildPermlevelFixtures):
	"""Role probes on the fixed tables: frappe.client.get_list / get_value with ``parent=``, the reportview child
	column and child filter, and the form read as the control."""

	def test_level_0_readers_receive_no_value_of_a_higher_level_table(self):
		"""Driven by the enumeration and the parents' DocPerms: every probe role is checked against every fixed
		table; at least one level-0-only reader per non-empty case (Card Supervisor on components, Card
		Manager on the diesel price schedule) proves the probe is not vacuous."""
		data = self._fixtures()
		self._grant_level_0("Card Settings", "Card Equipment")
		probed = set()
		for parent, fieldname, level, child in high_level_tables():
			if (parent, fieldname) not in data:
				continue
			name, child, fields, markers, oracle = data[(parent, fieldname)]
			for role in (*PROBE_ROLES, LEVEL_0_ROLE):
				levels = self._levels(parent, role)
				frappe.set_user(self._user(role))
				replies, hit = self._child_routes(parent, name, child, fieldname, fields, oracle)
				form = self._form(parent, name, fieldname)
				frappe.set_user("Administrator")
				blob = json.dumps(replies, default=str)
				with self.subTest(table=f"{parent}.{fieldname}", role=role, levels=sorted(levels)):
					if level in levels:
						# the control: a reader of the table's level reads it in the form
						self.assertIn(markers[-1], json.dumps(form, default=str))
						continue
					for marker in markers:
						self.assertNotIn(marker, blob)
					self.assertFalse(form)
					self.assertFalse(hit, "the reportview child filter must not answer")
					if 0 in levels:
						probed.add((parent, fieldname, role))
		self.assertIn(("Card Equipment", "components", "Card Supervisor"), probed)
		self.assertIn(("Card Settings", "diesel_price_schedule", "Card Manager"), probed)
		self.assertIn(("Card Settings", "project_transport_prices", LEVEL_0_ROLE), probed)
		self.assertIn(("Card Settings", "location_cost_centers", LEVEL_0_ROLE), probed)

	def test_permitted_readers_keep_the_child_column_in_reports(self):
		"""A reader of the components' level keeps the child column and the child filter in report view."""
		name, child, _fields, markers, oracle = self._fixtures()[("Card Equipment", "components")]
		for role in ("Card User", "Card Manager", "Accounts Manager"):
			with self.subTest(role=role):
				frappe.set_user(self._user(role))
				rows = reportview.execute(
					"Card Equipment", fields=[f"`tab{child}`.`change_reason`"], filters={"name": name}
				)
				hit = reportview.execute("Card Equipment", fields=["name"], filters=[[child, *oracle]])
				frappe.set_user("Administrator")
				self.assertIn(markers[-1], json.dumps(rows, default=str))
				self.assertEqual(len(hit), 1)

	def test_server_reads_are_not_affected(self):
		"""Server code reads the rows with frappe.get_all (no permission check): the posting, transport, diesel
		price and component lookups keep working for every user."""
		data = self._fixtures()
		frappe.set_user(self._user("Card Supervisor"))
		unit = data[("Card Equipment", "components")][0]
		self.assertTrue(
			frappe.get_all("Card Equipment Component", filters={"parent": unit}, fields=["component", "role"])
		)
		self.assertTrue(
			frappe.get_all(
				"Card Diesel Price",
				filters={"parent": "Card Settings", "unit_price": 4321.987},
				pluck="unit_price",
			)
		)

	def test_component_history_is_masked_for_a_level_0_reader(self):
		"""The change history (Version) of Card Equipment reaches level-0 readers; a component row added after
		FR-148 is kept there without its values (card/field_privacy.py masks every field above level 0)."""
		from frappe.desk.form.load import getdoc

		piece = self._equipment().name
		unit = frappe.get_doc("Card Equipment", self._equipment(is_unit=1).name)
		marker = "FR148-V-" + self.token
		unit.append("components", {"component": piece, "role": marker, "change_reason": marker})
		unit.save(ignore_permissions=True, ignore_version=False)
		frappe.set_user(self._user("Card Supervisor"))
		frappe.local.response = frappe._dict(docs=[])
		getdoc("Card Equipment", unit.name)
		versions = (frappe.response.get("docinfo") or {}).get("versions") or []
		frappe.set_user("Administrator")
		self.assertTrue(versions)
		self.assertNotIn(marker, json.dumps(versions, default=str))


class TestSettingsTimelineByLevel(ChildPermlevelFixtures):
	"""FR-148: the Card Settings timeline (Version rows in getdoc / get_docinfo) masks, per reader, every field
	and child row value at a level he cannot read; a reader of the level sees the real values."""

	def _settings_version(self):
		"""A real Version of Card Settings (Frappe's own diff of the stored and the changed document) that adds a
		row to each fixed table, changes one row and one level-2 field; inserted without the settings rules."""
		cost_center = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": "TEST-FR148-T-" + self.token, "company": self.company}
		).insert(ignore_permissions=True)
		location = frappe.get_doc(
			{"doctype": "Location", "location_name": "TEST-FR148-TL-" + self.token}
		).insert(ignore_permissions=True)
		self._child(
			"Card Diesel Price",
			"Card Settings",
			"Card Settings",
			"diesel_price_schedule",
			company=self.company,
			valid_from="2032-01-01",
			unit_price=1111.5,
		)
		self._child(
			"Card Diesel Price",
			"Card Settings",
			"Card Settings",
			"diesel_price_schedule",
			company=self.company,
			valid_from="2032-03-03",
			unit_price=2222.75,
		)
		old = frappe.get_doc("Card Settings")
		new = frappe.get_doc("Card Settings")
		new.append(
			"diesel_price_schedule",
			{"company": self.company, "valid_from": "2032-02-02", "unit_price": 7777.123},
		)
		# a removed level-1 row
		new.diesel_price_schedule = [r for r in new.diesel_price_schedule if r.unit_price != 2222.75]
		row = next(r for r in new.diesel_price_schedule if r.unit_price == 1111.5)
		row.unit_price = 6666.25
		new.append("project_transport_prices", {"project": project.name, "amount": 5555.75})
		new.append(
			"location_cost_centers",
			{"company": self.company, "location": location.name, "cost_center": cost_center},
		)
		new.reconciliation_tolerance = 4444.5
		version = frappe.new_doc("Version")
		self.assertTrue(version.update_version_info(old, new))
		version.insert(ignore_permissions=True)
		# row and field changes are stored formatted (e.g. "6,666.25"), added and removed rows raw
		return {
			"level 1": ["7777.123", "6,666.25", "2222.75"],
			"level 2": ["5555.75", location.name, "4,444.50"],
		}

	def _timelines(self, user):
		from card.card.doctype.card_settings import card_settings as scope

		frappe.set_user(user)
		replies = {}
		for label, call in (
			("getdoc", lambda: scope.getdoc("Card Settings", "Card Settings")),
			("get_docinfo", lambda: scope.get_docinfo(doctype="Card Settings", name="Card Settings")),
		):
			frappe.local.response = frappe._dict(docs=[])
			call()
			versions = frappe.response.docinfo.get("versions") or []
			replies[label] = json.dumps(
				[json.loads(v.get("data") or "{}") for v in versions], ensure_ascii=False, default=str
			)
		frappe.set_user("Administrator")
		return replies

	def test_card_manager_sees_the_diesel_rows_masked_and_the_level_2_values(self):
		from card.field_privacy import MASKED

		values = self._settings_version()
		for label, blob in self._timelines(self._user("Card Manager")).items():
			with self.subTest(route=label):
				for value in values["level 1"]:
					self.assertNotIn(value, blob)
				self.assertIn(MASKED, blob)
				for value in values["level 2"]:
					self.assertIn(value, blob)  # Card Manager reads level 2

	def test_accounts_manager_sees_the_real_values(self):
		values = self._settings_version()
		for label, blob in self._timelines(self._user("Accounts Manager")).items():
			with self.subTest(route=label):
				for value in values["level 1"] + values["level 2"]:
					self.assertIn(value, blob)

	def test_a_level_0_reader_sees_every_higher_level_value_masked(self):
		values = self._settings_version()
		user = self._grant_level_0("Card Settings")
		for label, blob in self._timelines(user).items():
			with self.subTest(route=label):
				for value in values["level 1"] + values["level 2"]:
					self.assertNotIn(value, blob)

	def test_the_masking_is_per_reader_and_the_stored_version_keeps_the_values(self):
		self._settings_version()
		stored = frappe.get_all(
			"Version",
			filters={"ref_doctype": "Card Settings"},
			order_by="creation desc",
			limit=1,
			pluck="data",
		)
		self.assertIn("7777.123", stored[0])

	def test_the_version_records_the_removed_row(self):
		"""The fixture's Version has a removed level-1 row (so the mask of ``removed`` is exercised)."""
		self._settings_version()
		stored = frappe.get_all(
			"Version",
			filters={"ref_doctype": "Card Settings"},
			order_by="creation desc",
			limit=1,
			pluck="data",
		)
		removed = json.loads(stored[0]).get("removed") or []
		self.assertTrue(
			any(t == "diesel_price_schedule" and r.get("unit_price") == 2222.75 for t, r in removed)
		)
		for label, blob in self._timelines(self._user("Card Manager")).items():
			with self.subTest(route=label):
				self.assertNotIn("2222.75", blob)

	def test_the_form_save_reply_is_masked(self):
		"""The timeline returned by the form save (savedocs) is masked as well. Card Manager cannot save Card
		Settings (read-only DocPerms at levels 0 and 2), so the writer is a test-only role that reads and writes
		level 0 only."""
		from frappe.desk.form.save import savedocs

		from card.card.doctype.card_settings import card_settings as scope

		values = self._settings_version()
		user = self._grant_level_0("Card Settings", write=1)
		frappe.set_user(user)
		frappe.local.response = frappe._dict(docs=[])
		scope.getdoc("Card Settings", "Card Settings")
		doc = frappe.response.docs[0].as_dict()
		frappe.local.response = frappe._dict(docs=[])
		savedocs(json.dumps(doc, default=str), "Save")
		versions = (frappe.response.get("docinfo") or {}).get("versions") or []
		frappe.set_user("Administrator")
		self.assertTrue(versions)
		blob = json.dumps(
			[json.loads(v.get("data") or "{}") for v in versions], ensure_ascii=False, default=str
		)
		for value in values["level 1"] + values["level 2"]:
			self.assertNotIn(value, blob)

	def test_malformed_versions_do_not_break_the_timeline(self):
		"""A Version whose data is not a JSON object, or has entries with a list or dict as field or table name,
		is shown as empty or without those entries; getdoc and get_docinfo still answer, and nothing leaks; for
		an unrestricted and a company-restricted Card Manager (the FR-133 company filter runs first)."""
		values = self._settings_version()
		for data in (
			"[]",
			"5",
			"null",
			'"s"',
			"not json",
			json.dumps(
				{
					"changed": [[["unit_price"], 7777.123, 7777.123], "bad"],
					"added": [[{"t": 1}, {"unit_price": 7777.123}], [["diesel_price_schedule"], {}], "bad"],
					"removed": "bad",
					"row_changed": [[["diesel_price_schedule"], 1, "x", [["unit_price", 7777.123, 1]]], [1]],
				}
			),
			# crafted entries: a valid shape with extra elements, unknown keys, non-string names and values
			json.dumps(
				{
					"added": [
						[
							"diesel_price_schedule",
							{"company": self.company, "unit_price": 1.0},
							{"company": OTHER, "unit_price": "SECRET-EXTRA-ROW"},
						],
						["adjustment_types", {"company": OTHER, "type_name": "SECRET-OTHER-COMPANY"}],
						["adjustment_types", {"company": [self.company], "type_name": "SECRET-LIST-COMPANY"}],
					],
					"debug": {"note": "SECRET-UNKNOWN-KEY"},
					"row_changed": [
						[
							"adjustment_types",
							1,
							"x",
							[["type_name", "a", "b"]],
							{"leak": "SECRET-ROW-CHANGED"},
						],
						["adjustment_types", 1, ["x"], [["type_name", "a", "SECRET-LIST-NAME"]]],
						[
							"adjustment_types",
							1,
							"x",
							[
								["company", [self.company], OTHER],
								["type_name", {"x": "SECRET-DICT-VALUE"}, "b"],
							],
						],
					],
					"changed": [["reconciliation_tolerance", 1, 2, "SECRET-CHANGED-EXTRA"]],
				}
			),
		):
			frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": "Card Settings",
					"docname": "Card Settings",
					"data": data,
				}
			).db_insert()
		manager = self._user("Card Manager")
		restricted = f"fr148-r-{frappe.generate_hash(length=8)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": restricted,
				"first_name": "FR148",
				"send_welcome_email": 0,
				"roles": [{"role": "Card Manager"}],
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": restricted,
				"allow": "Company",
				"for_value": self.company,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=restricted)
		# dropped for every reader: extra elements, unknown keys, non-string names, non-plain values
		always = (
			"SECRET-EXTRA-ROW",
			"SECRET-UNKNOWN-KEY",
			"SECRET-ROW-CHANGED",
			"SECRET-LIST-NAME",
			"SECRET-DICT-VALUE",
			"SECRET-CHANGED-EXTRA",
		)
		# dropped for the company-restricted reader: another company's row, a company that is not a string
		restricted_only = ("SECRET-OTHER-COMPANY", "SECRET-LIST-COMPANY", OTHER)
		for user in (manager, restricted):
			for label, blob in self._timelines(user).items():
				with self.subTest(user=user, route=label):
					for value in [*values["level 1"], *always]:
						self.assertNotIn(value, blob)
					if user == restricted:
						for value in restricted_only:
							self.assertNotIn(value, blob)


class TestChildPermlevelPrintAndWrite(ChildPermlevelFixtures):
	"""FR-148: prints carry no hidden row; a role without the table's level cannot overwrite or empty the rows."""

	def test_print_carries_no_hidden_component_row(self):
		name, _child, _fields, markers, _oracle = self._fixtures()[("Card Equipment", "components")]
		frappe.set_user(self._user("Card Supervisor"))
		try:
			html = frappe.get_print("Card Equipment", name)
		except frappe.PermissionError:
			frappe.clear_messages()
			html = ""
		frappe.set_user("Administrator")
		for marker in markers[1:]:
			self.assertNotIn(marker, html)
		frappe.set_user(self._user("Card Manager"))
		html = frappe.get_print("Card Equipment", name)
		frappe.set_user("Administrator")
		self.assertIn(markers[-1], html)  # the control: a reader of level 1 prints the rows

	def test_print_of_settings_carries_no_hidden_diesel_row(self):
		self._fixtures()
		frappe.set_user(self._user("Card Manager"))
		try:
			html = frappe.get_print("Card Settings", "Card Settings")
		except frappe.PermissionError:
			frappe.clear_messages()
			html = ""
		frappe.set_user("Administrator")
		self.assertNotIn("4321.987", html)

	def _stored(self, parent, name, fieldname):
		return sorted(
			frappe.get_all(
				frappe.get_meta(parent).get_field(fieldname).options,
				filters={"parent": name, "parenttype": parent, "parentfield": fieldname},
				pluck="name",
			)
		)

	def test_a_writer_without_the_level_cannot_empty_or_overwrite_the_rows(self):
		from frappe.desk.form.save import savedocs

		data = self._fixtures()
		unit = data[("Card Equipment", "components")][0]
		before = self._stored("Card Equipment", unit, "components")
		self.assertTrue(before)
		user = self._grant_level_0("Card Equipment", write=1)
		for route in ("savedocs", "client.save"):
			with self.subTest(route=route):
				frappe.set_user(user)
				doc = frappe.client.get("Card Equipment", unit)
				self.assertFalse(doc.get("components"))  # hidden from him
				doc["components"] = [{"component": unit, "role": "forged", "change_reason": "forged"}]
				if route == "savedocs":
					frappe.local.response = frappe._dict(docs=[])
					savedocs(json.dumps(doc, default=str), "Save")
				else:
					frappe.client.save(doc)
				frappe.set_user("Administrator")
				self.assertEqual(self._stored("Card Equipment", unit, "components"), before)
				self.assertFalse(
					frappe.db.exists("Card Equipment Component", {"parent": unit, "role": "forged"})
				)
		frappe.set_user(user)
		doc = frappe.client.get("Card Equipment", unit)
		doc["components"] = []
		frappe.client.save(doc)
		frappe.set_user("Administrator")
		self.assertEqual(self._stored("Card Equipment", unit, "components"), before)

	def test_a_settings_writer_without_the_level_cannot_empty_the_hidden_tables(self):
		"""Card Settings: a writer of level 0 only (a test-only role; Card Manager's DocPerms there are
		read-only) saves without the diesel schedule (level 1) and the transport prices (level 2); the stored
		rows are kept on both routes, and a forged row is not written."""
		from frappe.desk.form.save import savedocs

		self._fixtures()
		tables = ("diesel_price_schedule", "project_transport_prices")
		before = {t: self._stored("Card Settings", "Card Settings", t) for t in tables}
		self.assertTrue(all(before.values()))
		user = self._grant_level_0("Card Settings", write=1)
		for route in ("savedocs", "client.save"):
			with self.subTest(route=route):
				frappe.set_user(user)
				doc = frappe.client.get("Card Settings")
				for table in tables:
					self.assertFalse(doc.get(table))  # hidden from him
				doc["diesel_price_schedule"] = [
					{"company": self.company, "valid_from": "2033-01-01", "unit_price": 1.5}
				]
				doc["project_transport_prices"] = []
				if route == "savedocs":
					frappe.local.response = frappe._dict(docs=[])
					savedocs(json.dumps(doc, default=str), "Save")
				else:
					frappe.client.save(doc)
				frappe.set_user("Administrator")
				for table in tables:
					self.assertEqual(self._stored("Card Settings", "Card Settings", table), before[table])
				self.assertFalse(
					frappe.db.exists(
						"Card Diesel Price", {"parent": "Card Settings", "valid_from": "2033-01-01"}
					)
				)
