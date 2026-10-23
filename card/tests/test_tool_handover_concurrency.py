# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""#113 PR-T2: two requests that hand over the same tool at the same moment never give it
twice.

Each request runs in its own thread with its own database connection, as two web requests
do. The first does its work and holds its transaction open; the second starts and waits on
the first one's row lock; then the first commits. The synthetic records are committed (a race
needs two real transactions) and removed in tearDown, with the Card Settings value restored."""

import contextvars
import threading

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import nowdate

from card import materials

# a valid 1x1 PNG: the scanned receipt in tests (random bytes keep every file unique)
RECEIPT_PNG = bytes.fromhex(
	"89504e470d0a1a0a0000000d4948445200000001000000010806000000"
	"1f15c4890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
)

WAIT = 30  # seconds; a stuck step fails the test instead of hanging the run
LOCK_WAIT = 10  # innodb_lock_wait_timeout of the two requests (session only)
SAFE_ERRORS = (
	frappe.ValidationError,
	frappe.exceptions.QueryDeadlockError,
	frappe.exceptions.QueryTimeoutError,
)
CUSTODY = "Employee Tool Custody"


class _Request(threading.Thread):
	"""One web request: it runs `action`, then waits to commit."""

	def __init__(self, test, action):
		super().__init__(daemon=True, context=contextvars.Context())
		self.test, self.action = test, action
		self.go, self.written, self.release, self.finished = (threading.Event() for _ in range(4))
		self.error = None
		self.committed = False

	def run(self):
		try:
			self.test._connect()
			frappe.db.sql("set session innodb_lock_wait_timeout = %s", LOCK_WAIT)
			frappe.db.sql("select 1")  # the snapshot of a real request starts before it waits
			if not self.go.wait(WAIT):
				raise TimeoutError("request was never started")
			self.action()
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


class TestToolHandoverConcurrency(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.created = []  # (doctype, name), removed in reverse order
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

	def _race(self, action):
		"""The same action twice: the first holds its transaction while the second starts."""
		one, two = _Request(self, action), _Request(self, action)
		two.release.set()
		try:
			one.start()
			two.start()
			one.go.set()
			self.assertTrue(one.written.wait(WAIT), "first request did not write: %r" % one.error)
			two.go.set()
			two.finished.wait(1)  # the second reaches the first one's row lock
			one.release.set()
		finally:
			for request in (one, two):
				request.go.set()
				request.release.set()
			one.join(WAIT * 2)
			two.join(WAIT * 2)
		self.assertTrue(one.committed, "first request: %r" % one.error)
		self.assertFalse(two.committed, "the second request handed the tool over again")
		self.assertIsInstance(two.error, SAFE_ERRORS)

	# ---- records ----
	def _new(self, values):
		doc = frappe.get_doc(values).insert(ignore_permissions=True)
		self.created.append((doc.doctype, doc.name))
		return doc

	def _raw(self, values):
		"""A fixture row written directly (a submitted record without its whole history)."""
		doc = frappe.get_doc(values)
		doc.name = doc.name or frappe.generate_hash(length=10)
		doc.db_insert()
		for row in doc.get_all_children():
			row.parent = doc.name
			row.db_insert()
		self.created.append((doc.doctype, doc.name))
		return doc

	def _make_records(self):
		company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		leaves = company and frappe.get_all(
			"Warehouse", filters={"company": company, "is_group": 0}, pluck="name", order_by="name"
		)
		if not leaves or len(leaves) < 2 or not frappe.db.exists("UOM", "Nos"):
			self.skipTest("test masters missing (card.install.before_tests)")
		self.store, custody = leaves[0], leaves[1]
		self.old_custody_store = frappe.db.get_single_value("Card Settings", "tool_custody_warehouse")
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", custody)
		if not frappe.db.exists("Gender", "Male"):
			self._new({"doctype": "Gender", "gender": "Male"})
		self.item = self._new(
			{
				"doctype": "Item",
				"item_code": f"THC-TOOL-{self.token}",
				"item_name": f"THC tool {self.token}",
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 1,
			}
		).name
		employee = {
			"doctype": "Employee",
			"gender": "Male",
			"date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01",
			"company": company,
			"status": "Active",
		}
		self.worker = self._new(dict(employee, first_name=f"THC worker {self.token}")).name
		self.colleague = self._new(dict(employee, first_name=f"THC mate {self.token}")).name
		project = self._new(
			{"doctype": "Project", "project_name": f"THC project {self.token}", "company": company}
		).name
		# an approved review line of one tool (fixture rows: the approval itself is tested elsewhere)
		self.review = self._raw(
			{
				"doctype": "Equipment Needs Review",
				"name": f"THC-REV-{self.token}",
				"project": project,
				"company": company,
				"docstatus": 1,
				"approval_status": "Approved",
				"approved_by": "Administrator",
				"items": [
					{
						"name": f"THC-LINE-{self.token}",
						"kind": "Tool",
						"operator": self.worker,
						"item_code": self.item,
						"warehouse": self.store,
						"approved_qty": 1,
						"handed_qty": 0,
						"request_item": f"THC-REQ-{self.token}",
					}
				],
			}
		)
		self.line = f"THC-LINE-{self.token}"
		# the worker already holds one tool (a confirmed handover fixture, no stock history)
		self._raw(
			{
				"doctype": CUSTODY,
				"name": f"THC-HELD-{self.token}",
				"company": company,
				"employee": self.worker,
				"movement": "Handover",
				"date": nowdate(),
				"item_code": self.item,
				"qty": 1,
				"docstatus": 1,
			}
		)
		receipt = self._new(
			{
				"doctype": "File",
				"file_name": f"thc-receipt-{self.token}.png",
				"is_private": 1,
				"content": RECEIPT_PNG + frappe.generate_hash(length=12).encode(),
			}
		)
		transfer = frappe.get_doc(
			{
				"doctype": CUSTODY,
				"employee": self.worker,
				"movement": "Transfer",
				"to_employee": self.colleague,
				"date": nowdate(),
				"item_code": self.item,
				"qty": 1,
				"handover_receipt": receipt.file_url,
			}
		).insert(ignore_permissions=True)
		self.created.append((CUSTODY, transfer.name))
		self.transfer = transfer.name

	def _remove_records(self):
		for name in frappe.get_all(CUSTODY, filters={"item_code": self.item}, pluck="name"):
			if (CUSTODY, name) not in self.created:
				self.created.append((CUSTODY, name))
		for doctype, name in reversed(self.created):
			# custody rows of a reviewed line and submitted fixtures are never deleted by users
			if doctype in (CUSTODY, "Equipment Needs Review"):
				frappe.db.delete("Equipment Needs Review Item", {"parent": name})
				frappe.db.delete(doctype, {"name": name})
				frappe.db.delete("Version", {"ref_doctype": doctype, "docname": name})
			elif frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)
		frappe.db.set_single_value("Card Settings", "tool_custody_warehouse", self.old_custody_store)

	def _count(self, filters):
		return self._committed(lambda: frappe.db.count(CUSTODY, filters))

	# ---- cases ----
	def test_two_requests_make_the_same_replacement_handover(self):
		self._race(lambda: materials.make_tool_handover(self.line))
		self.assertEqual(self._count({"review_item": self.line, "docstatus": 0}), 1)

	def test_two_requests_confirm_the_same_transfer(self):
		def confirm():
			frappe.get_doc(CUSTODY, self.transfer).submit()

		self._race(confirm)
		self.assertEqual(self._count({"name": self.transfer, "docstatus": 1}), 1)
		self.assertEqual(
			self._committed(lambda: materials.custody_balance(self.colleague, self.item)),
			1,
			"the colleague got the tool once",
		)
