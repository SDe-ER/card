# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""F2 B7 + D, gate G1: a needs review saved before the F2 fix keeps the stock on hand in its
Version history (Equipment Needs Review Item.stock_qty). F2 stopped storing the figure; these
tests read the old history as users without stock rights and expect no figure:

- T1 getdoc, T2 get_docinfo / API v2 / the deprecated `cmd` route, T3 the savedocs, cancel and
  discard responses: real WSGI requests (the `after_request` scrub runs only there);
- T9 the activity timeline, T10 the Document Follow digest.

Gate G1 runs these on the current code first: each one must fail on the stock assertion
(STOCK_SHOWN), proving that the path returns the figure. One path per test, so a failing path
never hides the next one. Every test also checks that the other changes of the history are still
there. A request that does not answer with docinfo raises RuntimeError (an error, not a finding).

Requests run in another thread with their own database connection, so the synthetic records are
committed and removed by name in a cleanup that runs also when setUp fails."""

import json

import frappe
from frappe.tests.test_api import FrappeAPITestCase

from card import materials
from card.tests import test_v4_materials as v4
from card.tests.test_controllers import _ensure_masters

REVIEW = "Equipment Needs Review"
CHILD = "Equipment Needs Review Item"
REQUEST = "Equipment Needs Request"
SETTINGS = ("default_store_warehouse", "tool_custody_warehouse", "repeat_request_days")
# the history of a review saved before F2: a row edit that changes the stock first (Document
# Follow shows the first change of a row) and a row edit without stock
STOCK_EDIT = [["stock_qty", 5.0, 6.0], ["approved_qty", 2.0, 1.0]]
OTHER_EDIT = [["approved_qty", 1.0, 2.0]]
# the message of every stock assertion: G1 counts only failures with this text
STOCK_SHOWN = "a stock figure is returned to a user without stock rights"


def _stock_figures(versions):
	"""(stock figures, other changes) in docinfo.versions."""
	stock = other = 0
	for version in versions:
		data = json.loads(version.get("data") or "{}")
		for _table, _idx, _row, changes in data.get("row_changed") or []:
			for change in changes:
				stock += change[0] == "stock_qty"
				other += change[0] != "stock_qty"
		for key in ("added", "removed"):
			for _table, row in data.get(key) or []:
				stock += isinstance(row, dict) and "stock_qty" in row
		other += len(data.get("changed") or [])
	return stock, other


class TestF2VersionStock(FrappeAPITestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	# the v4 materials builders (functions, not the test class, so its tests do not run twice)
	_user = v4.TestV4Materials._user
	_operator = v4.TestV4Materials._operator
	_equipment = v4.TestV4Materials._equipment
	_item = v4.TestV4Materials._item
	_ask = v4.TestV4Materials._ask
	_review = v4.TestV4Materials._review

	def setUp(self):
		self.settings = {f: frappe.db.get_single_value("Card Settings", f) for f in SETTINGS}
		self.requests, self.reviews = [], []
		# unlike tearDown, a cleanup runs also when setUp fails half way
		self.addCleanup(self._remove_records)
		v4.TestV4Materials.setUp(self)
		frappe.get_doc(
			{"doctype": "Bin", "item_code": self.filter, "warehouse": self.store, "actual_qty": 5}
		).insert(ignore_permissions=True)
		self.card_user = self._user("cu", ["Card User"])
		self.supervisor = self._user("sup", ["Card Supervisor"])
		self.stock_user = self._user("su", ["Card User", "Stock User"])
		self.submitted = self._old_review(submit=True)
		self.draft = self._old_review(submit=False)
		self.discarded = self._old_review(submit=False)
		frappe.db.commit()  # nosemgrep: the requests read these records in their own connection

	def _remove_records(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()  # drops what a failed setUp or test did not commit
		users = [
			u
			for u in (getattr(self, a, None) for a in ("op_user", "card_user", "supervisor", "stock_user"))
			if u
		]
		items = [i for i in (getattr(self, "filter", None), getattr(self, "tool", None)) if i]
		eq, operator = getattr(self, "eq", None), getattr(self, "operator", None)
		for child, doctype, docs in (
			(CHILD, REVIEW, self.reviews),
			(REQUEST + " Item", REQUEST, self.requests),
		):
			if docs:
				frappe.db.delete(child, {"parent": ["in", docs]})
				frappe.db.delete(doctype, {"name": ["in", docs]})
		if items:
			frappe.db.delete("Bin", {"item_code": ["in", items]})
		if users:
			frappe.db.delete("Document Follow", {"user": ["in", users]})
			frappe.db.delete("Sessions", {"user": ["in", users]})
			frappe.db.delete("Activity Log", {"user": ["in", users]})
		assignments = (
			frappe.get_all("Card Equipment Assignment", {"equipment": eq}, pluck="name") if eq else []
		)
		for doctype, name in (
			*(("Card Equipment Assignment", a) for a in assignments),
			("Card Equipment", eq),
			("Employee", operator),
			*(("Item", i) for i in items),
			*(("User", u) for u in users),
		):
			if name and frappe.db.exists(doctype, name):
				frappe.delete_doc(doctype, name, ignore_permissions=True, force=True, delete_permanently=True)
		# after delete_doc, which can add its own comments
		names = [*self.reviews, *self.requests, *assignments, eq, operator, *items, *users]
		names = [n for n in names if n]
		if names:
			frappe.db.delete("Version", {"docname": ["in", names]})
			frappe.db.delete("Comment", {"reference_name": ["in", names]})
		for field, value in self.settings.items():
			frappe.db.set_single_value("Card Settings", field, value)
		frappe.db.commit()  # nosemgrep: remove the committed test records
		for name in self.reviews:
			self.assertFalse(frappe.db.exists(REVIEW, name), "synthetic records left behind")
		for field, value in self.settings.items():
			self.assertEqual(frappe.db.get_single_value("Card Settings", field), value, field)

	# ---------- builders ----------
	def _old_review(self, submit):
		"""A review whose history carries a stock figure, as one saved before F2."""
		self.requests.append(self._ask([{"kind": "Part", "item_code": self.filter, "qty": 2}]))
		review = self._review()
		self.reviews.append(review.name)
		row = review.items[0].name
		for changes in (STOCK_EDIT, OTHER_EDIT):
			data = {"changed": [], "added": [], "removed": [], "row_changed": [["items", 0, row, changes]]}
			frappe.get_doc(
				{
					"doctype": "Version",
					"ref_doctype": REVIEW,
					"docname": review.name,
					"data": frappe.as_json(data),
				}
			).insert(ignore_permissions=True)
		if submit:
			review.reload()
			review.submit()
		return review.name

	def _sid(self, user):
		from frappe.auth import CookieManager, LoginManager
		from frappe.utils import set_request

		set_request(path="/")
		frappe.local.cookie_manager = CookieManager()
		frappe.local.login_manager = LoginManager()
		frappe.local.login_manager.login_as(user)
		sid = frappe.session.sid
		frappe.set_user("Administrator")
		frappe.db.commit()  # nosemgrep: the session is read by the request's connection
		return sid

	def _versions(self, response):
		# not an assertion: a request that fails is an error of the test, not a finding
		if response.status_code != 200:
			raise RuntimeError(f"HTTP {response.status_code}: {response.get_data(as_text=True)[:500]}")
		body = response.json
		if "docinfo" not in body and isinstance(body.get("data"), dict):
			body = body["data"]  # API v2 wraps the result
		if not isinstance(body.get("docinfo"), dict) or "versions" not in body["docinfo"]:
			raise RuntimeError(f"no docinfo.versions in the response: {sorted(body)}")
		return body["docinfo"]["versions"]

	def assertNoStockFigure(self, versions):
		stock, other = _stock_figures(versions)
		self.assertGreater(other, 0, "the other changes of the review history must stay")
		self.assertEqual(stock, 0, STOCK_SHOWN)

	def _read_params(self):
		return {"doctype": REVIEW, "name": self.submitted, "sid": self._sid(self.card_user)}

	# ---------- T1-T3: real requests, one path each ----------
	def test_t1_getdoc_has_no_stock_figure(self):
		response = self.get(self.method("frappe.desk.form.load.getdoc"), self._read_params())
		self.assertNoStockFigure(self._versions(response))

	def test_t2a_get_docinfo_has_no_stock_figure(self):
		response = self.get(self.method("frappe.desk.form.load.get_docinfo"), self._read_params())
		self.assertNoStockFigure(self._versions(response))

	def test_t2b_api_v2_getdoc_has_no_stock_figure(self):
		v2 = self.get_path("v2", "method", "frappe.desk.form.load.getdoc")
		self.assertNoStockFigure(self._versions(self.get(v2, self._read_params())))

	def test_t2c_cmd_route_getdoc_has_no_stock_figure(self):
		params = {"cmd": "frappe.desk.form.load.getdoc", **self._read_params()}
		self.assertNoStockFigure(self._versions(self.post("/", params)))

	def test_t3a_savedocs_response_has_no_stock_figure(self):
		sid = self._sid(self.supervisor)
		doc = frappe.get_doc(REVIEW, self.draft).as_dict(convert_dates_to_str=True)
		doc["notes"] = "G1 save"
		saved = self.post(
			self.method("frappe.desk.form.save.savedocs"),
			{"doc": frappe.as_json(doc), "action": "Save", "sid": sid},
		)
		self.assertNoStockFigure(self._versions(saved))

	def test_t3b_cancel_response_has_no_stock_figure(self):
		cancelled = self.post(
			self.method("frappe.desk.form.save.cancel"),
			{"doctype": REVIEW, "name": self.submitted, "sid": self._sid(self.supervisor)},
		)
		self.assertNoStockFigure(self._versions(cancelled))

	def test_t3c_discard_response_has_no_stock_figure(self):
		discarded = self.post(
			self.method("frappe.desk.form.save.discard"),
			{"doctype": REVIEW, "name": self.discarded, "sid": self._sid(self.supervisor)},
		)
		self.assertNoStockFigure(self._versions(discarded))

	# ---------- T9 timeline, T10 Document Follow ----------
	def test_t9_timeline_has_no_stock_change(self):
		from frappe.desk.form.activity import get_activity_timeline

		frappe.set_user(self.card_user)
		activities = get_activity_timeline(REVIEW, self.submitted)["activities"]
		changes = [a["data"] for a in activities if a["type"] == "version"]
		self.assertTrue(any(c.get("fieldname") == "items" for c in changes), "row changes must stay")
		self.assertFalse([c for c in changes if "stock_qty" in json.dumps(c)], STOCK_SHOWN)

	def _digest_fields(self, user):
		from frappe.desk.form.document_follow import get_message_for_user

		frappe.db.set_value(
			"User", user, {"document_follow_notify": 1, "document_follow_frequency": "Hourly"}
		)
		frappe.get_doc(
			{"doctype": "Document Follow", "ref_doctype": REVIEW, "ref_docname": self.submitted, "user": user}
		).insert(ignore_permissions=True)
		message, _follows = get_message_for_user("Hourly", user)
		return [m["data"].get("field") for m in message if m.get("type") == "row changed"]

	def test_t10a_document_follow_digest_card_user_has_no_stock_line(self):
		fields = self._digest_fields(self.card_user)
		self.assertIn("approved_qty", fields, "the other changes of the review history must stay")
		self.assertNotIn("stock_qty", fields, STOCK_SHOWN)

	def test_t10b_document_follow_digest_stock_user_has_no_stock_line(self):
		# design R4: permlevel 1 without a level-1 DocPerm closes the digest line for every user
		fields = self._digest_fields(self.stock_user)
		self.assertIn("approved_qty", fields, "the other changes of the review history must stay")
		self.assertNotIn("stock_qty", fields, STOCK_SHOWN)

	def test_g1_review_stock_still_reads_live_stock(self):
		# control: the live hint of F2 is not part of the history and stays for a stock reader
		frappe.set_user(self.stock_user)
		self.assertEqual(set(materials.review_stock(self.submitted).values()), {5})
