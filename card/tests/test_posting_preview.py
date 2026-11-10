# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-119 (#49, #126): the posting screen. The preview is the builder's own plan run as a
dry run: its lines equal the lines the post (or rebuild) creates, it writes nothing, and it
is reachable only by the roles and for the companies that may already post."""

from unittest.mock import patch

import frappe
from frappe.model.document import Document
from frappe.utils import flt

from card.gl.masters import ensure_posting_masters
from card.gl.posting import (
	build_monthly_posting,
	posting_month_parties,
	preview_month,
	preview_monthly_posting,
	rebuild_monthly_posting,
)
from card.tests.test_p0_posting_integrity import _P0Base

WRITE_VERBS = {"insert", "update", "delete", "replace", "truncate", "alter", "drop", "create"}

COMPARED = (
	"item_code",
	"rate",
	"account",
	"project",
	"cost_center",
	"card_equipment",
	"item_tax_template",
	"description",
)


def _invoice_lines(doctype, name):
	account = "expense_account" if doctype == "Purchase Invoice" else "income_account"
	return [
		{
			"item_code": i.item_code,
			"rate": flt(i.rate, 2),
			"account": i.get(account),
			"project": i.project,
			"cost_center": i.cost_center,
			"card_equipment": i.card_equipment or None,
			"item_tax_template": i.item_tax_template or None,
			"description": i.description,
		}
		for i in frappe.get_doc(doctype, name).items
	]


def _preview_lines(preview):
	return [
		{k: (item.get(k) or None) if k != "rate" else item[k] for k in COMPARED} for item in preview.lines
	]


class _PreviewBase(_P0Base):
	def setUp(self):
		super().setUp()
		# the first post provisions the masters; the equality tests start provisioned
		ensure_posting_masters(self.company)
		frappe.clear_cache(doctype="Card Settings")

	def _counts(self):
		return {
			doctype: frappe.db.count(doctype)
			for doctype in (
				"Purchase Invoice",
				"Sales Invoice",
				"GL Posting Log",
				"GL Posting Source",
				"Item",
				"Item Tax Template",
				"Price List",
			)
		}

	def _no_write_guard(self):
		"""Every write path a preview could take raises inside the block."""

		def refuse(*args, **kwargs):
			raise AssertionError("the posting preview must not write")

		from frappe.database.database import Database

		real_sql = Database.sql

		def read_only_sql(db, query, *args, **kwargs):
			# any statement that writes is refused; reads (and locking reads) pass through
			verb = str(query).lstrip(" \t\n(").split(None, 1)[0].lower() if str(query).strip() else ""
			if verb in WRITE_VERBS:
				raise AssertionError(f"the posting preview must not write: {query}")
			return real_sql(db, query, *args, **kwargs)

		return [
			patch.object(Document, "insert", refuse),
			patch.object(Document, "save", refuse),
			patch.object(Document, "db_set", refuse),
			patch.object(Document, "db_insert", refuse),
			patch.object(Document, "db_update", refuse),
			patch.object(Database, "sql", read_only_sql),
			patch.object(Document, "delete", refuse, create=True),
			patch("frappe.database.database.Database.set_value", refuse),
			patch.object(frappe, "delete_doc", refuse),
			patch("card.gl.integrity.lock_sources", refuse),
			patch("card.gl.posting.ensure_posting_masters", refuse),
			patch("card.gl.posting._point_display", refuse),
		]

	def _preview_without_writes(self, party_type, party):
		before = self._counts()
		guards = self._no_write_guard()
		for g in guards:
			g.start()
		try:
			preview = preview_monthly_posting(self.company, party_type, party, 9, 2026)
		finally:
			for g in reversed(guards):
				g.stop()
		self.assertEqual(self._counts(), before)
		return preview


class TestPreviewEqualsPosting(_PreviewBase):
	def test_supplier_preview_equals_the_built_invoice(self):
		self._vat_supplier()
		_eq, card = self._example_card()
		self._fill()
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertFalse(preview.blocked, preview.blocked)
		self.assertEqual(preview.mode, "post")
		self.assertEqual(preview.posting_doctype, "Purchase Invoice")
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(_preview_lines(preview), _invoice_lines("Purchase Invoice", pi))
		doc = frappe.get_doc("Purchase Invoice", pi)
		self.assertEqual(preview.net_total, flt(doc.net_total, 2))
		self.assertEqual(preview.tax_template, doc.taxes_and_charges)
		self.assertEqual(preview.vat_estimate, flt(doc.total_taxes_and_charges, 2))
		self.assertEqual(
			sorted((s["doctype"], s["name"], s["amount"]) for s in preview.sources),
			sorted(
				(s.source_doctype, s.source_name, flt(s.amount, 2))
				for s in frappe.get_doc("GL Posting Log", {"posting_doc": pi}).sources
			),
		)
		self.assertEqual(card.name in {s["name"] for s in preview.sources}, True)

	def test_inclusive_diesel_basis_is_previewed_as_booked(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		self._fill(litres=100, price=2.3)
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertTrue(preview.diesel_note)
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(_preview_lines(preview), _invoice_lines("Purchase Invoice", pi))

	def test_customer_preview_equals_the_built_invoice(self):
		eq = self._rented_out(customer_rate=1000)
		self._card(
			eq,
			[8, 8],
			adjustments=[
				{"adjustment_type_ref": "Mobilization", "side": "Customer", "description": "m", "amount": 400}
			],
			submit=True,
		)
		preview = self._preview_without_writes("Customer", self.customer)
		self.assertFalse(preview.blocked, preview.blocked)
		si = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		self.assertEqual(_preview_lines(preview), _invoice_lines("Sales Invoice", si))
		self.assertEqual(preview.net_total, flt(frappe.db.get_value("Sales Invoice", si, "net_total"), 2))

	def test_rebuild_preview_equals_the_rebuilt_invoice(self):
		self._rental_card()
		first = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		late = self._rental_card(hours=(5,))
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertEqual(preview.mode, "rebuild")
		self.assertEqual(preview.replaces, [first])
		self.assertIn(late.name, {s["name"] for s in preview.sources})
		# the draft still exists and still holds its sources after the preview
		self.assertTrue(frappe.db.exists("Purchase Invoice", first))
		second = rebuild_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(_preview_lines(preview), _invoice_lines("Purchase Invoice", second))

	def test_unprovisioned_masters_are_reported_not_created(self):
		settings, row = self._row()
		template = row.vat_item_tax_template
		row.vat_item_tax_template = ""
		settings.save(ignore_permissions=True)
		# a site that never posted: the 15% CARD item tax template does not exist yet
		# (test transaction only, rolled back in tearDown)
		frappe.db.delete("Item Tax Template Detail", {"parent": template})
		frappe.db.delete("Item Tax Template", {"name": template})
		frappe.clear_cache(doctype="Card Settings")
		self._vat_supplier()
		self._rental_card()
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertFalse(preview.blocked, preview.blocked)
		self.assertTrue(preview.warnings)
		self.assertFalse(frappe.db.exists("Item Tax Template", template))
		self.assertFalse(self._row()[1].vat_item_tax_template)

	def test_unprovisioned_preview_still_refuses_what_the_post_refuses(self):
		settings, row = self._row()
		row.vat_item_tax_template = ""
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")
		self._vat_supplier()
		self._rental_card()
		frappe.db.set_single_value("Accounts Settings", "add_taxes_from_item_tax_template", 1)
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertIn("must be off", preview.blocked or "")
		with self.assertRaisesRegex(frappe.ValidationError, "must be off"):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)

	def test_supplier_without_tax_id_has_no_vat(self):
		self.assertFalse(frappe.db.get_value("Supplier", self.supplier, "tax_id"))
		self._rental_card()
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertFalse(preview.blocked, preview.blocked)
		self.assertIsNone(preview.tax_template)
		self.assertFalse(preview.vat_registered)
		self.assertEqual((preview.vat_rate, preview.vat_estimate), (0.0, 0.0))
		self.assertTrue(all("item_tax_template" not in line for line in preview.lines))
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		doc = frappe.get_doc("Purchase Invoice", pi)
		self.assertFalse(doc.taxes)
		self.assertEqual(flt(doc.total_taxes_and_charges, 2), 0.0)
		self.assertEqual(_preview_lines(preview), _invoice_lines("Purchase Invoice", pi))


class TestPreviewGates(_PreviewBase):
	def test_a_refused_build_is_returned_as_blocked_without_writes(self):
		self._rental_card()
		frappe.db.set_single_value("Card Settings", "enable_accounting", 0)
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertIn("disabled", preview.blocked)
		self.assertFalse(preview.lines)

	def test_unreviewed_manual_invoice_is_listed_and_the_post_still_refuses(self):
		self._rental_card()
		manual = self._manual_pi(600)
		preview = self._preview_without_writes("Supplier", self.supplier)
		self.assertFalse(preview.blocked, preview.blocked)
		self.assertEqual([i["name"] for i in preview.review_invoices], [manual.name])
		self.assertTrue(preview.can_review)  # Administrator
		with self.assertRaisesRegex(frappe.ValidationError, manual.name):
			build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		pi = build_monthly_posting(
			self.company, "Supplier", self.supplier, 9, 2026, reviewed_invoices=[manual.name]
		)
		self.assertEqual(_preview_lines(preview), _invoice_lines("Purchase Invoice", pi))


class TestMonthParties(_PreviewBase):
	def _status(self):
		rows = posting_month_parties(self.company, "9", "2026")
		return next(r for r in rows if r["party_type"] == "Supplier" and r["party"] == self.supplier)

	def test_status_moves_from_not_posted_to_draft_to_posted(self):
		self._rental_card()
		row = self._status()
		self.assertEqual((row["status"], row["pending_sources"]), ("Not posted", 1))
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		row = self._status()
		self.assertEqual((row["status"], row["pending_sources"]), ("Draft", 0))
		self.assertEqual([p["posting_doc"] for p in row["postings"]], [pi])
		doc = frappe.get_doc("Purchase Invoice", pi)
		doc.bill_no = "TEST-PREVIEW-" + self.token
		doc.bill_date = doc.posting_date
		doc.submit()
		self.assertEqual(self._status()["status"], "Posted")

	def test_listing_writes_nothing(self):
		self._rental_card()
		before = self._counts()
		self._status()
		self.assertEqual(self._counts(), before)


class TestPreviewAccess(_PreviewBase):
	def setUp(self):
		super().setUp()
		self.other = "TEST-PPRV-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": self.other,
				"abbr": "V" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = self.other
		co.db_insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _user(self, roles, restrict_to=None):
		email = f"pprv-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Posting Preview",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)
		if restrict_to:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": restrict_to,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def test_endpoints_are_get_only(self):
		for fn in (preview_month, posting_month_parties):
			self.assertEqual(sorted(frappe.allowed_http_methods_for_whitelisted_func[fn]), ["GET"])

	def test_other_company_is_refused(self):
		self._rental_card()
		frappe.set_user(
			self._user(("Card Manager", "Accounts Manager", "Purchase User"), restrict_to=self.other)
		)
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to build postings"):
			preview_month(self.company, "Supplier", self.supplier, "9", "2026")
		with self.assertRaisesRegex(frappe.PermissionError, "not permitted to build postings"):
			posting_month_parties(self.company, "9", "2026")

	def test_permitted_manager_previews_its_company(self):
		self._rental_card()
		frappe.set_user(
			self._user(
				("Card Manager", "Accounts Manager", "Purchase User", "Sales User"), restrict_to=self.company
			)
		)
		preview = preview_month(self.company, "Supplier", self.supplier, "9", "2026")
		self.assertFalse(preview.blocked, preview.blocked)
		self.assertTrue(preview.lines)
		self.assertTrue(preview.can_review)

	def test_roles_that_cannot_post_are_refused(self):
		self._rental_card()
		frappe.set_user(self._user(("Accounts User", "Purchase User")))
		with self.assertRaisesRegex(frappe.PermissionError, "Only Card Manager or System Manager"):
			preview_month(self.company, "Supplier", self.supplier, "9", "2026")
		with self.assertRaisesRegex(frappe.PermissionError, "Only Card Manager or System Manager"):
			posting_month_parties(self.company, "9", "2026")

	def test_page_is_open_only_to_posting_roles(self):
		from frappe.desk.desk_views import DeskViews
		from frappe.desk.utils import is_item_allowed

		self.assertTrue(frappe.db.exists("Page", "card-monthly-posting"))
		expected = {
			self._user(("Card Manager",)): True,
			self._user(("System Manager",)): True,
			self._user(("Accounts User",)): False,
			self._user(("Accounts Manager",)): False,
			self._user(("Card User",)): False,
		}
		for user, allowed in expected.items():
			frappe.set_user(user)
			try:
				self.assertEqual(is_item_allowed("card-monthly-posting", "Page", DeskViews()), allowed, user)
			finally:
				frappe.set_user("Administrator")
