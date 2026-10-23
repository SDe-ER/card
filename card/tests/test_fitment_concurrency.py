# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-077: two requests that save the same equipment make, model or fitment row at the
same moment never leave two rows.

Each request runs in its own thread with its own database connection, as two web requests
do. Both take their snapshot and pass the controller's duplicate lookup before either
commits; the unique key then refuses the second insert. The synthetic records are committed
(a race needs two real transactions) and removed in tearDown with their Version rows."""

import contextvars
import threading

import frappe
from frappe.tests import IntegrationTestCase

WAIT = 30  # seconds; a stuck step fails the test instead of hanging the run
LOCK_WAIT = 10  # innodb_lock_wait_timeout of the two requests (session only)
SAFE_ERRORS = (
	frappe.ValidationError,
	frappe.exceptions.QueryDeadlockError,
	frappe.exceptions.QueryTimeoutError,
)
CLEANED = ("Card Equipment Part", "Card Equipment Model", "Card Equipment Make", "Item", "Item Group")


class _Request(threading.Thread):
	"""One web request: it reads (snapshot), waits, inserts, then waits to commit."""

	def __init__(self, test, values):
		super().__init__(daemon=True, context=contextvars.Context())
		self.test, self.values = test, values
		self.read, self.go, self.written, self.release, self.finished = (threading.Event() for _ in range(5))
		self.error = None
		self.committed = False

	def run(self):
		try:
			self.test._connect()
			frappe.db.sql("set session innodb_lock_wait_timeout = %s", LOCK_WAIT)
			# the duplicate lookup of the controller runs here for both requests
			self.lookup = frappe.db.exists(self.values["doctype"], self.test.key_filter)
			self.read.set()
			if not self.go.wait(WAIT):
				raise TimeoutError("request was never started")
			frappe.get_doc(dict(self.values)).insert(ignore_permissions=True)
			self.written.set()
			if not self.release.wait(WAIT):
				raise TimeoutError("request was never released")
			frappe.db.commit()  # nosemgrep: a race needs two committed transactions
			self.committed = True
		except Exception as e:
			self.error = e
			if getattr(frappe.local, "db", None):
				frappe.db.rollback()
		finally:
			self.finished.set()
			frappe.destroy()


class TestFitmentConcurrency(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.key_filter = {}
		self.created = {doctype: [] for doctype in CLEANED}
		self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)

	# ---- connections ----
	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	def _committed(self, fn):
		out = {}

		def run():
			try:
				self._connect()
				out["value"] = fn()
				frappe.db.commit()  # nosemgrep: test data seen by the other connections
			except Exception as e:
				out["error"] = e
				if getattr(frappe.local, "db", None):
					frappe.db.rollback()
			finally:
				frappe.destroy()

		thread = threading.Thread(target=run, daemon=True, context=contextvars.Context())
		thread.start()
		thread.join(WAIT * 4)
		if thread.is_alive():
			raise TimeoutError("helper connection did not finish")
		if "error" in out:
			raise out["error"]
		return out.get("value")

	def _race(self, values_one, values_two):
		"""Both requests read before either writes; the first inserts and holds its
		transaction while the second inserts, then the first commits."""
		one, two = _Request(self, values_one), _Request(self, values_two)
		two.release.set()
		try:
			one.start()
			two.start()
			self.assertTrue(one.read.wait(WAIT) and two.read.wait(WAIT), "requests did not start")
			self.assertFalse(one.lookup or two.lookup, "a row existed before the race")
			one.go.set()
			self.assertTrue(one.written.wait(WAIT), "first request did not write: %r" % one.error)
			two.go.set()
			two.finished.wait(1)  # the second reaches the first one's key lock
			one.release.set()
		finally:
			for request in (one, two):
				request.go.set()
				request.release.set()
			one.join(WAIT * 2)
			two.join(WAIT * 2)
		self.assertTrue(one.committed, "first request: %r" % one.error)
		self.assertFalse(two.committed, "the second request saved a duplicate")
		self.assertIsInstance(two.error, SAFE_ERRORS)
		return one, two

	# ---- records ----
	def _new(self, doctype, values):
		doc = frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
		self.created[doctype].append(doc.name)
		return doc.name

	def _make_records(self):
		etype = frappe.db.get_value("Card Equipment Type", {}, "name", order_by="creation asc")
		if not etype or not frappe.db.exists("UOM", "Nos"):
			self.skipTest("test masters missing (card.install.before_tests)")
		self.etype = etype
		group = self._new(
			"Item Group",
			{"item_group_name": f"FITC-GRP-{self.token}", "parent_item_group": "All Item Groups"},
		)
		self.item = self._new(
			"Item",
			{
				"item_code": f"FITC-ITEM-{self.token}",
				"item_name": f"FITC item {self.token}",
				"item_group": group,
				"stock_uom": "Nos",
			},
		)
		self.make = self._new("Card Equipment Make", {"make_name": f"FITC make {self.token}"})
		self.model = self._new(
			"Card Equipment Model",
			{"model_name": "PC200-8", "equipment_make": self.make, "equipment_type": etype},
		)

	def _remove_records(self):
		for doctype in ("Card Equipment Part", "Card Equipment Model", "Card Equipment Make"):
			names = frappe.get_all(doctype, filters={"creation": [">=", self._started()]}, pluck="name")
			names = [n for n in names if self._ours(doctype, n)]
			if names:
				# fitment rows are never deleted by users (on_trash refuses); test data only
				frappe.db.delete(doctype, {"name": ["in", names]})
				frappe.db.delete("Version", {"ref_doctype": doctype, "docname": ["in", names]})
		for doctype in ("Item", "Item Group"):
			for name in self.created[doctype]:
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)

	def _started(self):
		return frappe.utils.add_to_date(frappe.utils.now_datetime(), hours=-1)

	def _ours(self, doctype, name):
		if doctype == "Card Equipment Make":
			return self.token in (frappe.db.get_value(doctype, name, "make_name") or "")
		if doctype == "Card Equipment Model":
			return frappe.db.get_value(doctype, name, "equipment_make") == self.make
		return frappe.db.get_value(doctype, name, "item_code") == self.item

	def _count(self, doctype, filters):
		return self._committed(lambda: frappe.db.count(doctype, filters))

	# ---- cases ----
	def test_two_requests_save_the_same_make(self):
		self.key_filter = {"make_key": f"FITCNEW{self.token.upper()}"}
		values = {"doctype": "Card Equipment Make", "make_name": f"FITC new {self.token}"}
		other = dict(values, make_name=f"fitc-NEW {self.token}")
		self._race(values, other)
		self.assertEqual(self._count("Card Equipment Make", self.key_filter), 1)

	def test_two_requests_save_the_same_model(self):
		self.key_filter = {"model_key": f"{self.make}|D61PX"}
		base = {"doctype": "Card Equipment Model", "equipment_make": self.make, "equipment_type": self.etype}
		self._race(dict(base, model_name="D61PX"), dict(base, model_name="d61 px"))
		self.assertEqual(self._count("Card Equipment Model", self.key_filter), 1)

	def test_two_requests_save_the_same_fitment_row(self):
		self.key_filter = {"compat_key": f"M|{self.model}|{self.item}"}
		values = {
			"doctype": "Card Equipment Part",
			"item_code": self.item,
			"applies_to": "Equipment Model",
			"equipment_model": self.model,
		}
		self._race(values, dict(values))
		self.assertEqual(self._count("Card Equipment Part", self.key_filter), 1)
