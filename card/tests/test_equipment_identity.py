# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""D1 tests: a chassis or plate number belongs to one Card Equipment per company.
Rolled back with the test transaction, except the concurrency case, which commits its own
synthetic records (a race needs two real transactions) and removes them in tearDown."""

import contextvars
import threading

import frappe
from frappe.tests import IntegrationTestCase

from card.card.doctype.card_equipment.card_equipment import identity_key
from card.patches.v4_1_0 import backfill_equipment_identity_keys
from card.tests.test_controllers import _ensure_masters

WAIT = 30  # seconds; a stuck step fails the test instead of hanging the run


class TestEquipmentIdentity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _token(self):
		return frappe.generate_hash(length=8).upper()

	def _equipment(self, company=None, **kw):
		d = frappe.new_doc("Card Equipment")
		d.company = company or self._m["company"]
		d.equipment_type = self._m["etype"]
		d.ownership = kw.pop("ownership", "ملك")
		d.equipment_name = "TEST-ID-" + frappe.generate_hash(length=8)
		d.daily_hours = 8
		for key, value in kw.items():
			d.set(key, value)
		return d

	def _make(self, **kw):
		return self._equipment(**kw).insert(ignore_permissions=True)

	def _other_company(self):
		token = frappe.generate_hash(length=8)
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": "TEST-ID-CO-" + token,
				"abbr": "I" + token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self._m["company"], "default_currency"),
				"country": frappe.db.get_value("Company", self._m["company"], "country"),
			}
		)
		co.name = co.company_name
		co.db_insert()
		return co.name

	def _user(self, roles):
		email = f"identity-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Identity",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		return email

	# ---------- the key ----------

	def test_identity_key_normalises_case_spaces_separators_and_digits(self):
		self.assertEqual(identity_key(" ab-12 / 3.4_5 "), "AB12345")
		self.assertEqual(identity_key("١٢٣ أ ب ج"), "123أبج")
		self.assertEqual(identity_key("۴۵۶"), "456")
		self.assertIsNone(identity_key(None))
		self.assertIsNone(identity_key(" - / "))
		# invisible marks pasted with Arabic text and full-width digits compare equal
		self.assertEqual(identity_key("١٢٣\u200f أبج"), identity_key("123 أبج"))
		self.assertEqual(identity_key("\u200dAB\u200c-\uff11\uff12"), "AB12")

	def test_keys_are_stored_on_save(self):
		eq = self._make(serial_no=" kmt-001 ", plate_no="١٢٣ أبج")
		self.assertEqual((eq.serial_no_key, eq.plate_no_key), ("KMT001", "123أبج"))

	# ---------- refused ----------

	def test_same_chassis_number_in_one_company_is_refused(self):
		token = self._token()
		first = self._make(serial_no="CH-" + token)
		with self.assertRaisesRegex(frappe.ValidationError, first.name):
			self._make(serial_no="ch " + token)  # same number, other spelling

	def test_same_plate_number_in_one_company_is_refused(self):
		token = self._token()
		self._make(plate_no="PL " + token)
		with self.assertRaises(frappe.ValidationError):
			self._make(plate_no="pl-" + token)

	def test_changing_a_number_to_one_in_use_is_refused(self):
		token = self._token()
		self._make(serial_no="A" + token)
		other = self._make(serial_no="B" + token)
		other.serial_no = "a" + token
		with self.assertRaises(frappe.ValidationError):
			other.save(ignore_permissions=True)

	def test_moving_to_a_company_that_uses_the_number_is_refused(self):
		token = self._token()
		company = self._other_company()
		self._make(company=company, serial_no="MV" + token)
		eq = self._make(serial_no="MV" + token)  # allowed: other company
		eq.company = company
		with self.assertRaises(frappe.ValidationError):
			eq.save(ignore_permissions=True)

	def test_message_names_the_other_equipment_only_to_a_reader(self):
		token = self._token()
		first = self._make(serial_no="MSG" + token)
		reader = self._user(["Card Manager"])
		frappe.set_user(reader)
		try:
			with self.assertRaises(frappe.ValidationError) as refused:
				self._equipment(serial_no="MSG" + token).insert()
			self.assertIn(first.name, str(refused.exception))  # Card Manager reads equipment
		finally:
			frappe.set_user("Administrator")
		# a user who may read only another machine is told the number is taken, not where
		visible = self._make()
		restricted = self._user(["Card Manager"])
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": restricted,
				"allow": "Card Equipment",
				"for_value": visible.name,
				"apply_to_all_doctypes": 0,
				"applicable_for": "Card Equipment",
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=restricted)
		eq = self._equipment(serial_no="MSG" + token)
		eq.set_identity_keys()
		frappe.set_user(restricted)
		try:
			self.assertFalse(frappe.has_permission("Card Equipment", "read", first.name))
			with self.assertRaises(frappe.ValidationError) as hidden:
				eq.validate_unique_identity()
		finally:
			frappe.set_user("Administrator")
		self.assertNotIn(first.name, str(hidden.exception))

	# ---------- allowed ----------

	def test_empty_numbers_are_never_compared(self):
		a = self._make(serial_no="", plate_no=None)
		b = self._make(serial_no="  ", plate_no="-")
		self.assertIsNone(a.serial_no_key)
		self.assertIsNone(b.serial_no_key)
		self.assertIsNone(b.plate_no_key)

	def test_same_number_in_another_company_is_allowed(self):
		token = self._token()
		self._make(serial_no="CO" + token)
		other = self._make(company=self._other_company(), serial_no="CO" + token)
		self.assertEqual(other.serial_no_key, "CO" + token)

	def test_chassis_and_plate_are_separate_numbers(self):
		token = self._token()
		self._make(serial_no="X" + token)
		self.assertTrue(self._make(plate_no="X" + token).name)

	def test_resaving_or_editing_the_same_equipment_is_allowed(self):
		eq = self._make(serial_no="SELF" + self._token())
		eq.serial_no = eq.serial_no.lower()  # same key
		eq.brand = "edited"
		eq.save(ignore_permissions=True)

	def test_legacy_duplicate_is_kept_and_unrelated_edit_allowed(self):
		token = self._token()
		first = self._make(serial_no="OLD" + token)
		legacy = self._make(serial_no="TMP" + token)
		# a duplicate made before D1 (direct write, no key yet)
		frappe.db.set_value(
			"Card Equipment",
			legacy.name,
			{"serial_no": "OLD" + token, "serial_no_key": None},
			update_modified=False,
		)
		logs = frappe.db.count("Error Log", {"method": "CARD equipment numbers shared before D1"})
		backfill_equipment_identity_keys.execute()
		self.assertGreater(
			frappe.db.count("Error Log", {"method": "CARD equipment numbers shared before D1"}), logs
		)  # the shared number is listed for the office
		self.assertEqual(frappe.db.get_value("Card Equipment", legacy.name, "serial_no_key"), "OLD" + token)
		self.assertEqual(frappe.db.get_value("Card Equipment", legacy.name, "serial_no"), "OLD" + token)
		doc = frappe.get_doc("Card Equipment", legacy.name)
		doc.brand = "unrelated edit"
		doc.save(ignore_permissions=True)  # not blocked: the number did not change
		doc.serial_no = "NEW" + token  # and it can be corrected
		doc.save(ignore_permissions=True)
		self.assertTrue(first.name)

	def test_backfill_is_idempotent_and_writes_only_the_keys(self):
		eq = self._make(serial_no="BF-" + self._token())
		frappe.db.set_value("Card Equipment", eq.name, "serial_no_key", None, update_modified=False)
		modified = frappe.db.get_value("Card Equipment", eq.name, "modified")
		versions = frappe.db.count("Version", {"ref_doctype": "Card Equipment", "docname": eq.name})
		backfill_equipment_identity_keys.execute()
		backfill_equipment_identity_keys.execute()
		self.assertEqual(
			frappe.db.get_value("Card Equipment", eq.name, "serial_no_key"), identity_key(eq.serial_no)
		)
		self.assertEqual(frappe.db.get_value("Card Equipment", eq.name, "modified"), modified)
		self.assertEqual(
			frappe.db.count("Version", {"ref_doctype": "Card Equipment", "docname": eq.name}), versions
		)


class TestEquipmentIdentityConcurrency(IntegrationTestCase):
	"""Two requests save equipment with the same chassis number at the same time: the second
	waits for the first one's company identity lock, then its locking read sees the first's row."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls._m = _ensure_masters()
		frappe.db.commit()  # nosemgrep: test masters seen by the other connections

	def setUp(self):
		self.number = "RACE-" + frappe.generate_hash(length=8).upper()
		self.made = []

	def tearDown(self):
		def remove():
			for name in frappe.get_all("Card Equipment", filters={"serial_no": self.number}, pluck="name"):
				frappe.delete_doc(
					"Card Equipment", name, ignore_permissions=True, force=True, delete_permanently=True
				)

		self._committed(remove)

	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True
		if frappe.db.sql("show variables like 'innodb_snapshot_isolation'"):
			# MariaDB 10.6 (Production) behaviour, this session only
			frappe.db.sql("set session innodb_snapshot_isolation = 0")
		frappe.db.sql("set session innodb_lock_wait_timeout = 10")

	def _committed(self, fn):
		out = {}

		def run():
			try:
				self._connect()
				out["value"] = fn()
				frappe.db.commit()  # nosemgrep: cleanup seen by the other connections
			except Exception as e:
				out["error"] = e
			finally:
				frappe.destroy()

		thread = threading.Thread(target=run, daemon=True, context=contextvars.Context())
		thread.start()
		thread.join(WAIT * 2)
		if "error" in out:
			raise out["error"]
		return out.get("value")

	def _insert(self):
		d = frappe.new_doc("Card Equipment")
		d.update(
			{
				"company": self._m["company"],
				"equipment_type": self._m["etype"],
				"ownership": "ملك",
				"equipment_name": "TEST-RACE-" + frappe.generate_hash(length=6),
				"daily_hours": 8,
				"serial_no": self.number,
			}
		)
		return d.insert(ignore_permissions=True).name

	def test_two_saves_at_once_keep_one_equipment_per_number(self):
		state = {"one": {}, "two": {}}
		one_written, release_one, two_started = threading.Event(), threading.Event(), threading.Event()

		def one():
			try:
				self._connect()
				frappe.db.sql("select count(*) from `tabCard Equipment`")  # snapshot before the other writes
				state["one"]["name"] = self._insert()
				one_written.set()
				release_one.wait(WAIT)
				frappe.db.commit()  # nosemgrep: a race needs two committed transactions
			except Exception as e:
				state["one"]["error"] = e
				one_written.set()
			finally:
				frappe.destroy()

		def two():
			try:
				self._connect()
				frappe.db.sql("select count(*) from `tabCard Equipment`")  # snapshot before one commits
				two_started.set()
				state["two"]["name"] = self._insert()
				frappe.db.commit()  # nosemgrep: a race needs two committed transactions
			except Exception as e:
				state["two"]["error"] = e
				frappe.db.rollback()
			finally:
				frappe.destroy()

		t1 = threading.Thread(target=one, daemon=True, context=contextvars.Context())
		t2 = threading.Thread(target=two, daemon=True, context=contextvars.Context())
		try:
			t1.start()
			self.assertTrue(one_written.wait(WAIT))
			self.assertNotIn("error", state["one"], state["one"].get("error"))
			t2.start()
			self.assertTrue(two_started.wait(WAIT))
			t2.join(1)  # the second request waits for the first one's lock
			self.assertTrue(t2.is_alive(), "the second save did not wait for the first")
		finally:
			release_one.set()  # never leave the first request holding its locks
			t1.join(WAIT)
			t2.join(WAIT)
		self.assertIsInstance(state["two"].get("error"), frappe.ValidationError, state["two"])
		saved = self._committed(
			lambda: frappe.get_all(
				"Card Equipment", filters={"serial_no_key": identity_key(self.number)}, pluck="name"
			)
		)
		self.assertEqual(saved, [state["one"]["name"]])
