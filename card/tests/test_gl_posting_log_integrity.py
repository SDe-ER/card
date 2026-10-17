# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""#57: the GL Posting Log is the audit record that guards Card postings
(card.gl.events._block_amended_copy, #55). No user may delete, edit or create
one: its lifecycle moves only through the builder's insert and the db_set calls
in card.gl.events. Desk, the REST resource handlers (frappe.api.v1) and
frappe.client are exercised for System Manager and Administrator; Delete Company
Transactions and app uninstall keep working. All data is per-test and rolled
back."""

import json
from unittest.mock import patch

import frappe
from frappe.api.v1 import create_doc, update_doc
from frappe.api.v1 import delete_doc as rest_delete
from frappe.client import delete as client_delete
from frappe.client import insert as client_insert
from frappe.client import save as client_save
from frappe.client import set_value as client_set_value

from card.gl.posting import build_monthly_posting, post_month, rebuild_monthly_posting
from card.tests.test_amended_copy_name_reuse import REFUSED
from card.tests.test_posting_lines import _ReconciliationBase

# the #57 guards' own messages
DELETE, EDIT, CREATE, SOURCES = (
	"cannot be deleted",
	"cannot be edited",
	"created only by CARD",
	"sources of a posting log",
)
IDENTITY = (
	"company",
	"party_type",
	"party",
	"month",
	"year",
	"posting_type",
	"posting_doctype",
	"posting_doc",
	"sequence",
	"creation",
)


class TestGLPostingLogIntegrity(_ReconciliationBase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.form_dict = frappe._dict()
		super().tearDown()

	# ---- helpers ----
	def _login(self, roles):
		email = f"gl57-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "GL57",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(email)
		return email

	def _try(self, fn, *args, **kwargs):
		try:
			fn(*args, **kwargs)
			return True
		except (frappe.PermissionError, frappe.ValidationError):
			return False

	def _rest(self, fn, *args, data=None):
		frappe.local.form_dict = frappe._dict(data=json.dumps(data or {}, default=str))
		try:
			return self._try(fn, *args)
		finally:
			frappe.local.form_dict = frappe._dict()

	def _refused_by(self, guard, fn, *args, data=None, **kwargs):
		"""Refused by the #57 guard itself, not by a permission or another check
		(the paths that bypass permissions: Administrator, ignore_permissions)."""
		if data is not None:
			frappe.local.form_dict = frappe._dict(data=json.dumps(data, default=str))
		try:
			with self.assertRaisesRegex((frappe.ValidationError, frappe.PermissionError), guard):
				fn(*args, **kwargs)
		finally:
			frappe.local.form_dict = frappe._dict()

	def _other_company(self):
		name = "TEST-GL57-CO-" + self.token
		if not frappe.db.exists("Company", name):
			co = frappe.new_doc("Company")
			co.update(
				{
					"company_name": name,
					"abbr": "G57" + self.token[:4].upper(),
					"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"country": frappe.db.get_value("Company", self.company, "country"),
				}
			)
			co.name = name
			co.db_insert()
		return name

	def _amend(self, invoice):
		amended = frappe.copy_doc(invoice)
		amended.amended_from = invoice.name
		amended.docstatus = 0
		amended.bill_no = (invoice.bill_no or "TEST") + "-A"
		return amended

	def _submitted_posting(self):
		self._vat_supplier()
		self._example_card()
		pi = frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		pi.bill_no = "TEST-GL57-" + frappe.generate_hash(length=6)
		pi.bill_date = pi.posting_date
		pi.submit()
		return pi, frappe.db.get_value("GL Posting Log", {"posting_doc": pi.name, "status": "Submitted"})

	def _cancelled_posting(self):
		pi, log = self._submitted_posting()
		pi.cancel()
		return pi, log

	def _log_payload(self, invoice, **changes):
		return dict(
			{
				"doctype": "GL Posting Log",
				"company": self.company,
				"party_type": "Supplier",
				"party": self.supplier,
				"month": "09",
				"year": 2026,
				"posting_type": "Purchase Invoice",
				"status": "Draft",
				"posting_doctype": "Purchase Invoice",
				"posting_doc": invoice,
				"sequence": 5,
			},
			**changes,
		)

	def _snapshot(self, log):
		doc = frappe.get_doc("GL Posting Log", log)
		values = {f: str(doc.get(f)) for f in (*IDENTITY, "status", "remarks", "amount")}
		values["sources"] = [(r.source_doctype, r.source_name, r.amount) for r in doc.sources]
		return values

	# ---- L-1: a log is never deleted ----
	def test_cancelled_log_cannot_be_deleted_on_any_path_and_amendment_stays_refused(self):
		pi, log = self._cancelled_posting()
		self._login(["System Manager"])
		self.assertFalse(self._try(frappe.delete_doc, "GL Posting Log", log), "delete_doc")
		self.assertFalse(self._rest(rest_delete, "GL Posting Log", log), "REST DELETE")
		self.assertFalse(self._try(client_delete, "GL Posting Log", log), "frappe.client.delete")
		from frappe.desk.reportview import delete_bulk

		# list-view bulk delete commits / rolls back per row: keep the test transaction
		with patch.object(frappe.db, "commit"), patch.object(frappe.db, "rollback"):
			self.assertEqual(delete_bulk("GL Posting Log", [log]), [log], "list bulk delete")
		frappe.set_user("Administrator")
		self._refused_by(DELETE, frappe.delete_doc, "GL Posting Log", log, ignore_permissions=True)
		self._refused_by(DELETE, rest_delete, "GL Posting Log", log)
		self.assertTrue(frappe.db.exists("GL Posting Log", log))
		with self.assertRaisesRegex(frappe.ValidationError, REFUSED):
			self._amend(pi).insert(ignore_permissions=True)

	def test_stale_log_of_a_deleted_draft_is_kept_and_name_reuse_still_works(self):
		self._vat_supplier()
		self._example_card()
		draft = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.delete_doc("Purchase Invoice", draft, ignore_permissions=True)  # legitimate draft deletion
		stale = frappe.db.get_value(
			"GL Posting Log", {"posting_doc": draft}, ["name", "status"], as_dict=True
		)
		self.assertEqual(stale.status, "Cancelled")
		self._refused_by(DELETE, frappe.delete_doc, "GL Posting Log", stale.name, ignore_permissions=True)
		manual = self._manual_invoice("Purchase Invoice", "2026-09-20", 777)
		self.assertEqual(manual.name, draft)  # #55: the number is reused, the manual invoice stays amendable
		manual.cancel()
		self.assertTrue(self._amend(manual).insert(ignore_permissions=True).name)

	# ---- L-2: a log is never edited ----
	def test_log_cannot_be_edited_on_any_path(self):
		pi, log = self._submitted_posting()
		other = self._manual_invoice("Purchase Invoice", "2026-09-21", 10)
		before = self._snapshot(log)
		changes = (
			{"posting_doc": other.name},
			{"status": "Cancelled"},
			{"creation": "2020-01-01 00:00:00"},
			{"remarks": "edited"},
			{"amount": 1},
		)
		self._login(["System Manager"])
		for values in changes:
			self.assertFalse(self._rest(update_doc, "GL Posting Log", log, data=values), values)
			self.assertFalse(self._try(client_set_value, "GL Posting Log", log, values), values)
		frappe.set_user("Administrator")
		from frappe.desk.form.save import savedocs

		for values in changes:
			self._refused_by(EDIT, update_doc, "GL Posting Log", log, data=values)
			doc = frappe.get_doc("GL Posting Log", log)
			doc.update(values)
			self._refused_by(EDIT, doc.save, ignore_permissions=True)
			form = frappe.get_doc("GL Posting Log", log).as_dict()
			form.update(values)
			self._refused_by(EDIT, savedocs, json.dumps(form, default=str), "Save")  # Desk form save
		self.assertEqual(self._snapshot(log), before)
		pi.cancel()  # the lifecycle still moves the status (db_set)
		self.assertEqual(frappe.db.get_value("GL Posting Log", log, "status"), "Cancelled")

	# ---- L-3: only the builder creates a log ----
	def test_log_cannot_be_created_outside_the_builder(self):
		draft = self._manual_invoice("Purchase Invoice", "2026-09-20", 300, submit=False).name
		payload = self._log_payload(draft)  # a draft of the right company and party, no log yet
		self._login(["System Manager"])
		self.assertFalse(self._rest(create_doc, "GL Posting Log", data=payload), "SM REST POST")
		self.assertFalse(self._try(client_insert, payload), "SM frappe.client.insert")
		frappe.set_user("Administrator")
		# flags sent in a request are dropped ("flags" is a reserved key): the marker is missing
		self._refused_by(CREATE, create_doc, "GL Posting Log", data=dict(payload, flags={"card_gl_build": 1}))
		self._refused_by(CREATE, client_insert, dict(payload, flags={"card_gl_build": 1}))
		self._refused_by(CREATE, frappe.get_doc(payload).insert, ignore_permissions=True)
		deleted = frappe.get_doc(
			{
				"doctype": "Deleted Document",
				"deleted_doctype": "GL Posting Log",
				"deleted_name": "TEST-GL57-RESTORED",
				"data": json.dumps(dict(payload, name="TEST-GL57-RESTORED"), default=str),
			}
		).insert(ignore_permissions=True)
		from frappe.core.doctype.deleted_document.deleted_document import restore

		self._refused_by(CREATE, restore, deleted.name)
		self.assertFalse(frappe.db.exists("GL Posting Log", {"posting_doc": draft}))

	def test_builder_marker_alone_is_not_enough(self):
		draft = self._manual_invoice("Purchase Invoice", "2026-09-20", 300, submit=False).name
		submitted = self._manual_invoice("Purchase Invoice", "2026-09-21", 300).name
		other_supplier = frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": "TEST-GL57-SUP-" + self.token,
				"supplier_group": frappe.db.get_value("Supplier", self.supplier, "supplier_group"),
			}
		).insert(ignore_permissions=True)
		_pi, logged = self._submitted_posting()
		logged_doc = frappe.db.get_value("GL Posting Log", logged, "posting_doc")
		cases = {
			"posting type": self._log_payload(draft, posting_type="Sales Invoice"),
			"no document": self._log_payload(None),
			"company": self._log_payload(draft, company=self._other_company()),
			"party": self._log_payload(draft, party=other_supplier.name),
			"party type": self._log_payload(draft, party_type="Customer", party=self.customer),
			"submitted": self._log_payload(submitted),
			"second log": self._log_payload(logged_doc),
		}
		for label, payload in cases.items():
			forged = frappe.get_doc(payload)
			forged.flags.card_gl_build = True
			with self.subTest(label):
				self._refused_by(CREATE, forged.insert, ignore_permissions=True)
		# control: the marker with matching data is exactly what the builder writes
		ok = frappe.get_doc(self._log_payload(draft))
		ok.flags.card_gl_build = True
		self.assertTrue(ok.insert(ignore_permissions=True).name)

	# ---- source rows (GL Posting Source) are never changed on their own ----
	def test_source_rows_cannot_be_changed_added_or_deleted_directly(self):
		_pi, log = self._submitted_posting()
		before = self._snapshot(log)
		row = frappe.get_doc("GL Posting Log", log).sources[0]
		self.assertEqual(row.source_doctype, "Card Monthly Card")
		# a real card of the same type, so link validation passes and only the guard can refuse
		foreign = self._card(self._equipment(), [4], submit=True).name
		self._login(["System Manager"])
		self.assertFalse(self._rest(update_doc, "GL Posting Source", row.name, data={"source_name": foreign}))
		frappe.set_user("Administrator")
		self._refused_by(SOURCES, update_doc, "GL Posting Source", row.name, data={"source_name": foreign})
		self._refused_by(SOURCES, client_save, dict(row.as_dict(), source_name=foreign))
		self._refused_by(SOURCES, rest_delete, "GL Posting Source", row.name)  # frappe.delete_doc on the row
		# frappe.client deletes / sets a row through its log, so the log refuses
		self._refused_by(EDIT, client_delete, "GL Posting Source", row.name)
		self._refused_by(EDIT, client_set_value, "GL Posting Source", row.name, "amount", 1)
		self._refused_by(
			EDIT,
			client_insert,
			{
				"doctype": "GL Posting Source",
				"parenttype": "GL Posting Log",
				"parentfield": "sources",
				"parent": log,
				"source_doctype": "Card Monthly Card",
				"source_name": foreign,
			},
		)
		self.assertEqual(self._snapshot(log), before)

	# ---- permissions: read-only for every role, also through DocShare / Custom DocPerm ----
	def test_no_role_may_create_write_delete_or_share(self):
		for perm in frappe.get_all(
			"DocPerm",
			filters={"parent": "GL Posting Log"},
			fields=["role", "create", "write", "delete", "share"],
		):
			self.assertFalse(perm.create or perm.write or perm.delete or perm.share, perm.role)
		self.assertFalse(frappe.db.exists("Custom DocPerm", {"parent": "GL Posting Log"}))

	def test_docshare_and_custom_docperm_do_not_grant_write_or_delete(self):
		_pi, log = self._cancelled_posting()
		before = self._snapshot(log)
		manager = self._login(["Card Manager"])
		frappe.set_user("Administrator")
		frappe.share.add_docshare(
			"GL Posting Log", log, manager, write=1, share=1, flags={"ignore_share_permission": True}
		)
		custom = frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": "GL Posting Log",
				"role": "System Manager",
				"permlevel": 0,
				"read": 1,
				"write": 1,
				"create": 1,
				"delete": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(doctype="GL Posting Log")
		try:
			for roles in (None, ["System Manager"]):
				if roles:
					self._login(roles)
				else:
					frappe.set_user(manager)
				# both may write now (share / custom DocPerm): the guard refuses
				self._refused_by(EDIT, update_doc, "GL Posting Log", log, data={"remarks": "x"})
				if roles:  # the custom DocPerm also grants create and delete
					self._refused_by(DELETE, rest_delete, "GL Posting Log", log)
					self._refused_by(CREATE, create_doc, "GL Posting Log", data=self._log_payload(_pi.name))
				else:  # a share never grants delete
					self.assertFalse(self._rest(rest_delete, "GL Posting Log", log))
				frappe.set_user("Administrator")
		finally:
			frappe.set_user("Administrator")
			frappe.delete_doc("Custom DocPerm", custom.name, ignore_permissions=True)
			frappe.clear_cache(doctype="GL Posting Log")
		self.assertEqual(self._snapshot(log), before)

	# ---- the lifecycle is unchanged ----
	def test_lifecycle_keeps_every_logs_identity(self):
		self._vat_supplier()
		self._example_card()
		first = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		old = frappe.db.get_value("GL Posting Log", {"posting_doc": first, "status": "Draft"})
		old_identity = {k: v for k, v in self._snapshot(old).items() if k in (*IDENTITY, "sources")}
		self._card(self._equipment(), [4], submit=True)  # a late source: rebuild deletes the draft
		pi = frappe.get_doc(
			"Purchase Invoice", rebuild_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		)
		new = frappe.db.get_value("GL Posting Log", {"posting_doc": pi.name, "status": "Draft"})
		new_identity = {k: v for k, v in self._snapshot(new).items() if k in (*IDENTITY, "sources")}
		pi.bill_no = "TEST-GL57-LC"
		pi.bill_date = pi.posting_date
		pi.submit()
		pi.cancel()
		self.assertEqual(frappe.db.get_value("GL Posting Log", old, "status"), "Cancelled")
		self.assertEqual(frappe.db.get_value("GL Posting Log", new, "status"), "Cancelled")
		for log, identity in ((old, old_identity), (new, new_identity)):
			self.assertEqual({k: v for k, v in self._snapshot(log).items() if k in identity}, identity)
		# sources are free again and a new month build takes them once
		again = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(
			frappe.db.count(
				"GL Posting Log", {"party": self.supplier, "status": ["in", ["Draft", "Submitted"]]}
			),
			1,
		)
		self.assertTrue(again)

	def test_card_manager_and_system_manager_still_post(self):
		self._vat_supplier()
		self._example_card()
		# the endpoint (party and Item read checks) with Purchase User, as in production
		build = lambda: post_month(self.company, "Supplier", self.supplier, "9", "2026")  # noqa: E731
		for roles in (["Card Manager", "Purchase User"], ["System Manager", "Purchase User"]):
			self._login(roles)
			name = build()
			frappe.set_user("Administrator")
			self.assertEqual(
				frappe.db.get_value("GL Posting Log", {"posting_doc": name, "status": "Draft"}, "status"),
				"Draft",
			)
			frappe.delete_doc("Purchase Invoice", name, ignore_permissions=True)

	# ---- administrative operations keep working ----
	def test_transaction_deletion_removes_only_that_companys_logs_and_sources(self):
		"""The steps Delete Company Transactions runs for each DocType (ERPNext
		Transaction Deletion Record), called directly inside the test transaction.
		The background job itself is not run (no worker on the QA bench)."""
		from erpnext.setup.doctype.transaction_deletion_record.transaction_deletion_record import (
			_get_protected_doctypes_internal,
		)

		_pi, kept = self._cancelled_posting()
		kept_before = self._snapshot(kept)
		other = self._other_company()
		for i in range(2):  # pre-existing logs of the other company, written directly
			log = frappe.get_doc(
				{
					"doctype": "GL Posting Log",
					"company": other,
					"party_type": "Supplier",
					"party": self.supplier,
					"month": "09",
					"year": 2026,
					"posting_type": "Purchase Invoice",
					"status": "Cancelled",
					"sequence": i + 1,
				}
			)
			log.append(
				"sources", {"source_doctype": "Card Monthly Card", "source_name": f"X-{i}", "amount": 1}
			)
			log.set_new_name()
			log.set_parent_in_children()
			log.db_insert()
			for row in log.sources:
				row.db_insert()
		tdr = frappe.new_doc("Transaction Deletion Record")
		tdr.company = other
		self.assertNotIn("GL Posting Log", _get_protected_doctypes_internal())
		self.assertIn("GL Posting Log", {d.parent for d in tdr.get_doctypes_with_company_field(["Company"])})
		self.assertEqual(tdr._get_child_tables("GL Posting Log"), ["GL Posting Source"])
		names = frappe.get_all("GL Posting Log", filters={"company": other}, pluck="name")
		self.assertEqual(len(names), 2)
		tdr.delete_child_tables("GL Posting Log", names)
		tdr.delete_docs_linked_with_specified_company("GL Posting Log", names)
		self.assertFalse(frappe.db.exists("GL Posting Log", {"company": other}))
		self.assertFalse(frappe.db.exists("GL Posting Source", {"parent": ["in", names]}))
		self.assertEqual(self._snapshot(kept), kept_before)

	def test_app_uninstall_deletion_path_is_not_blocked(self):
		_pi, log = self._cancelled_posting()
		# frappe.installer.remove_app deletes every record of the app's DocTypes this way
		frappe.delete_doc("GL Posting Log", log, ignore_on_trash=True, force=True)
		self.assertFalse(frappe.db.exists("GL Posting Log", log))
		self.assertFalse(frappe.db.exists("GL Posting Source", {"parent": log}))
