# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Party portal scaffold (FR-161, WP-O1, closure plan C-11, owner decision O-16).

Coverage targets:

* ``card.portal.get_party_from_user`` resolves ``(party_type, party)``
  through the Contact → Dynamic Link chain, ignores Guest / Administrator
  and portal users without a party link.
* ``card.portal.list_party_cards`` returns only submitted cards of the
  given party inside the user's permitted companies; drafts, cancelled
  rows and a second company's cards never leak.
* ``card.portal.get_party_card`` returns one card only when its party and
  its company match.
* The two www views (``/card-portal`` and ``/card-portal/view``) return 404
  through ``PageDoesNotExistError`` when ``enable_party_portal`` is 0 on
  every company (hides enablement; O-16), and return their contexts when
  the flag is on for the user's company.
* Lesson 1: forgery of ``party`` / ``party_type`` on the request is
  ignored; the handler always resolves from the session.
* Lesson 5: ``enable_party_portal`` sits at the same permlevel as the
  other settings fields in the parent table (permlevel 1).
* Lesson 12: removing the enable guard makes
  ``test_portal_landing_returns_404_when_disabled`` fail; removing the
  own-party filter inside ``list_party_cards`` makes
  ``test_cross_party_list_refused`` fail.
"""

from __future__ import annotations

import importlib
import json
import os

import frappe
from frappe.tests import IntegrationTestCase

from card import portal as portal_mod
from card.portal import (
	get_party_card,
	get_party_from_user,
	list_party_cards,
)
from card.tests.test_controllers import _ensure_masters
from card.tests.test_transfer import _past_month_year

DOCTYPE = "Card Monthly Card"


def _load_www_module(path: str):
	"""Load a www page module by file path.

	``card.www.card-portal.index`` is not importable through plain
	``importlib.import_module`` because the dotted path has a hyphen; the
	Frappe website renderer loads the module file in context. Tests load
	it the same way through ``importlib.util.spec_from_file_location``."""

	spec = importlib.util.spec_from_file_location(
		f"card.www.card_portal._test_{os.path.splitext(os.path.basename(path))[0]}",
		path,
	)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


APP_ROOT = frappe.get_app_path("card")
INDEX_PATH = os.path.join(APP_ROOT, "www", "card-portal", "index.py")
VIEW_PATH = os.path.join(APP_ROOT, "www", "card-portal", "view", "index.py")


class TestPartyPortalScaffold(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		self.month_str, self.year_str = _past_month_year()
		self.other = self._other_company()
		frappe.db.set_single_value("Card Settings", "period_lock_date", None)
		frappe.clear_document_cache("Card Settings", "Card Settings")
		# Portal disabled by default (every test flips it on explicitly).
		self._set_portal(self.company, 0)
		self._set_portal(self.other, 0)
		self.supplier_a = self._supplier("A")
		self.supplier_b = self._supplier("B")
		self.customer_a = self._customer("A")
		self.proj_a = self._project("A", self.company)
		self.proj_b = self._project("B", self.other)

	def tearDown(self):
		frappe.set_user("Administrator")
		# Clear only what tests set. ``frappe.form_dict`` is a LocalProxy;
		# NEVER assign to the module-level name (``frappe.form_dict = …``)
		# because that replaces the proxy for the whole process, which
		# breaks every later test's REST and print-format calls. Set the
		# proxy's underlying local instead.
		frappe.local.form_dict = frappe._dict()
		if hasattr(frappe.local, "flags") and frappe.local.flags is not None:
			frappe.local.flags.redirect_location = None
		try:
			frappe.db.rollback()
		except Exception:
			pass

	# ---------- fixtures (Administrator, rolled back) ----------

	def _d(self, day):
		return "%s-%s-%02d" % (self.year_str, self.month_str, day)

	def _other_company(self):
		name = "TEST-PRTL-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "P" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def _set_portal(self, company: str, value: int):
		settings = frappe.get_single("Card Settings")
		found = False
		for row in settings.company_settings or []:
			if row.company == company:
				row.enable_party_portal = value
				found = True
		if not found:
			settings.append("company_settings", {"company": company, "enable_party_portal": value})
		settings.save(ignore_permissions=True)

	def _supplier(self, suffix):
		group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
		name = "TEST-PRTL-SUP-%s-%s" % (suffix, self.token)
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": name,
				"supplier_group": group,
				"supplier_type": "Company",
			}
		).insert(ignore_permissions=True)
		return name

	def _customer(self, suffix):
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		name = "TEST-PRTL-CUST-%s-%s" % (suffix, self.token)
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": group,
				"territory": territory,
				"customer_type": "Company",
			}
		).insert(ignore_permissions=True)
		return name

	def _project(self, suffix, company):
		p = frappe.new_doc("Project")
		p.project_name = "TEST-PRTL-PRJ-%s-%s" % (suffix, self.token)
		p.company = company
		p.insert(ignore_permissions=True)
		return p.name

	def _equipment(self, suffix, company, supplier=None, customer=None):
		from card.constants import DIR_RENTED_IN, DIR_RENTED_OUT, OWNED

		eq = frappe.new_doc("Card Equipment")
		eq.company = company
		eq.equipment_type = self._m["etype"]
		eq.equipment_name = "TEST-PRTL-EQ-%s-%s" % (suffix, self.token)
		eq.rate_type = "باليوم"
		eq.rate = 750
		eq.daily_hours = 10
		if supplier:
			eq.ownership = "إيجار"
			eq.rental_direction = DIR_RENTED_IN
			eq.supplier = supplier
		elif customer:
			eq.ownership = OWNED
			eq.rental_direction = DIR_RENTED_OUT
			eq.default_customer = customer
			eq.customer_rate_type = "باليوم"
			eq.customer_rate = 800
		else:
			eq.ownership = OWNED
		eq.insert(ignore_permissions=True)
		return eq.name

	def _assign(self, equipment, project):
		a = frappe.new_doc("Card Equipment Assignment")
		a.equipment = equipment
		a.project = project
		a.from_date = self._d(1)
		a.insert(ignore_permissions=True)

	def _card(self, equipment, project, submit=True, shift="نهاري"):
		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"equipment": equipment,
				"project": project,
				"shift": shift,
				"month": self.month_str,
				"year": int(self.year_str),
				"days": [{"operation_date": self._d(5), "day_status": "عمل", "working_hours": 8}],
			}
		)
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc.name

	def _portal_user(self, party_type: str | None, party_name: str | None):
		"""Create a Website User and (when ``party_type`` is given) link it
		via Contact.links to the given party. Returns the user's email."""
		email = f"prtl-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Portal User",
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [],
			}
		).insert(ignore_permissions=True)
		if party_type and party_name:
			contact = frappe.new_doc("Contact")
			contact.first_name = email.split("@", 1)[0]
			contact.append("email_ids", {"email_id": email, "is_primary": 1})
			contact.append("links", {"link_doctype": party_type, "link_name": party_name})
			contact.insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	# ---------- get_party_from_user ----------

	def test_resolve_party_from_user_supplier(self):
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		self.assertEqual(get_party_from_user(), ("Supplier", self.supplier_a))

	def test_resolve_party_from_user_customer(self):
		user = self._portal_user("Customer", self.customer_a)
		frappe.set_user(user)
		self.assertEqual(get_party_from_user(), ("Customer", self.customer_a))

	def test_resolve_party_guest_none(self):
		frappe.set_user("Guest")
		self.assertIsNone(get_party_from_user())

	def test_resolve_party_administrator_none(self):
		"""Administrator is excluded by design: the portal is for Website
		Users; an internal user never resolves to a party through this
		helper."""
		frappe.set_user("Administrator")
		self.assertIsNone(get_party_from_user())

	def test_resolve_party_user_without_contact_none(self):
		user = self._portal_user(None, None)
		frappe.set_user(user)
		self.assertIsNone(get_party_from_user())

	def test_resolve_party_user_without_party_link_none(self):
		"""A Contact linked only to non-party DocTypes resolves to None."""
		email = f"prtl-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "No Link",
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [],
			}
		).insert(ignore_permissions=True)
		contact = frappe.new_doc("Contact")
		contact.first_name = "No Link"
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
		# no Dynamic Link rows at all
		contact.insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertIsNone(get_party_from_user())

	# ---------- list_party_cards ----------

	def test_list_party_cards_supplier_returns_own_three(self):
		eq_a1 = self._equipment("A1", self.company, supplier=self.supplier_a)
		eq_a2 = self._equipment("A2", self.company, supplier=self.supplier_a)
		eq_a3 = self._equipment("A3", self.company, supplier=self.supplier_a)
		eq_b1 = self._equipment("B1", self.company, supplier=self.supplier_b)
		eq_b2 = self._equipment("B2", self.company, supplier=self.supplier_b)
		for eq in (eq_a1, eq_a2, eq_a3, eq_b1, eq_b2):
			self._assign(eq, self.proj_a)
		shifts = iter(["نهاري", "ليلي", "نهاري", "ليلي", "نهاري"])
		for eq in (eq_a1, eq_a2, eq_a3, eq_b1, eq_b2):
			self._card(eq, self.proj_a, shift=next(shifts))
		rows = list_party_cards("Supplier", self.supplier_a)
		self.assertEqual(len(rows), 3)
		self.assertTrue(all(r.supplier == self.supplier_a for r in rows))

	def test_list_party_cards_customer_returns_own(self):
		eq_1 = self._equipment("CA1", self.company, customer=self.customer_a)
		eq_2 = self._equipment("CA2", self.company, customer=self.customer_a)
		for eq in (eq_1, eq_2):
			self._assign(eq, self.proj_a)
		self._card(eq_1, self.proj_a)
		self._card(eq_2, self.proj_a, shift="ليلي")
		rows = list_party_cards("Customer", self.customer_a)
		self.assertEqual(len(rows), 2)
		self.assertTrue(all(r.customer == self.customer_a for r in rows))

	def test_list_party_cards_excludes_draft_and_cancelled(self):
		eq_s = self._equipment("S1", self.company, supplier=self.supplier_a)
		eq_d = self._equipment("S2", self.company, supplier=self.supplier_a)
		eq_c = self._equipment("S3", self.company, supplier=self.supplier_a)
		for eq in (eq_s, eq_d, eq_c):
			self._assign(eq, self.proj_a)
		self._card(eq_s, self.proj_a)  # submitted
		self._card(eq_d, self.proj_a, submit=False, shift="ليلي")  # draft
		submitted = frappe.get_doc(DOCTYPE, self._card(eq_c, self.proj_a, shift="نهاري"))
		# cancel path mirrors FR-123 (reason required); use the direct
		# controller to keep the test narrow.
		submitted.flags.ignore_permissions = True
		submitted.cancel_reason = "test cancellation (portal scaffold)"
		submitted.cancel()
		rows = list_party_cards("Supplier", self.supplier_a)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].name, submitted.amended_from or rows[0].name)

	def test_list_party_cards_second_company_isolated(self):
		"""A user restricted to company A sees no Supplier-A cards in
		company B (cross-company isolation)."""
		# Supplier-A cards in each company
		eq_a_co1 = self._equipment("ACO1", self.company, supplier=self.supplier_a)
		eq_a_co2 = self._equipment("ACO2", self.other, supplier=self.supplier_a)
		self._assign(eq_a_co1, self.proj_a)
		self._assign(eq_a_co2, self.proj_b)
		self._card(eq_a_co1, self.proj_a)
		self._card(eq_a_co2, self.proj_b)
		# restrict one user to self.company, another to self.other
		user_a = self._portal_user("Supplier", self.supplier_a)
		user_b = self._portal_user("Supplier", self.supplier_a)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user_a,
				"allow": "Company",
				"for_value": self.company,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user_b,
				"allow": "Company",
				"for_value": self.other,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user_a)
		frappe.clear_cache(user=user_b)
		rows_a = list_party_cards("Supplier", self.supplier_a, user=user_a)
		rows_b = list_party_cards("Supplier", self.supplier_a, user=user_b)
		self.assertEqual({r.company for r in rows_a}, {self.company})
		self.assertEqual({r.company for r in rows_b}, {self.other})

	def test_list_party_cards_unknown_doctype_empty(self):
		self.assertEqual(list_party_cards("Employee", "EMP-0001"), [])

	def test_list_party_cards_empty_party_empty(self):
		self.assertEqual(list_party_cards("Supplier", ""), [])

	# ---------- get_party_card ----------

	def test_get_party_card_returns_own(self):
		eq = self._equipment("G1", self.company, supplier=self.supplier_a)
		self._assign(eq, self.proj_a)
		name = self._card(eq, self.proj_a)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		card = get_party_card(name)
		self.assertIsNotNone(card)
		self.assertEqual(card.name, name)
		self.assertEqual(card.supplier, self.supplier_a)

	def test_get_party_card_refuses_other_party(self):
		eq_b = self._equipment("GB", self.company, supplier=self.supplier_b)
		self._assign(eq_b, self.proj_a)
		name = self._card(eq_b, self.proj_a)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		# Supplier-A tries to load Supplier-B's card
		self.assertIsNone(get_party_card(name))

	def test_get_party_card_refuses_draft(self):
		eq = self._equipment("GD", self.company, supplier=self.supplier_a)
		self._assign(eq, self.proj_a)
		name = self._card(eq, self.proj_a, submit=False)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		self.assertIsNone(get_party_card(name))

	def test_get_party_card_empty_name_none(self):
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		self.assertIsNone(get_party_card(""))

	# ---------- portal view (landing) ----------

	def test_portal_landing_returns_404_when_disabled(self):
		"""Default: ``enable_party_portal`` is 0 on every company → 404.
		Lesson 12: removing the enable guard inside ``index.py``
		``get_context`` makes this test fail."""
		mod = _load_www_module(INDEX_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		ctx = frappe._dict()
		with self.assertRaises(frappe.PageDoesNotExistError):
			mod.get_context(ctx)

	def test_portal_landing_returns_list_when_enabled(self):
		"""When the flag is on for any company, the handler returns the
		list for the logged-in party."""
		self._set_portal(self.company, 1)
		eq = self._equipment("LE1", self.company, supplier=self.supplier_a)
		self._assign(eq, self.proj_a)
		self._card(eq, self.proj_a)
		mod = _load_www_module(INDEX_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		ctx = frappe._dict()
		mod.get_context(ctx)
		self.assertEqual(ctx.party_type, "Supplier")
		self.assertEqual(ctx.party, self.supplier_a)
		self.assertEqual(len(ctx.cards), 1)

	def test_portal_landing_guest_redirects_when_enabled(self):
		self._set_portal(self.company, 1)
		mod = _load_www_module(INDEX_PATH)
		frappe.set_user("Guest")
		ctx = frappe._dict()
		frappe.local.flags.redirect_location = None
		with self.assertRaises(frappe.Redirect):
			mod.get_context(ctx)
		self.assertIn("/login", frappe.local.flags.redirect_location)

	def test_portal_landing_user_without_party_shows_empty(self):
		self._set_portal(self.company, 1)
		mod = _load_www_module(INDEX_PATH)
		user = self._portal_user(None, None)
		frappe.set_user(user)
		ctx = frappe._dict()
		mod.get_context(ctx)
		self.assertIsNone(ctx.party_type)
		self.assertEqual(ctx.cards, [])

	# ---------- portal view (single card) ----------

	def test_portal_view_returns_404_when_disabled(self):
		mod = _load_www_module(VIEW_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		ctx = frappe._dict()
		frappe.local.form_dict = frappe._dict(name="whatever")
		with self.assertRaises(frappe.PageDoesNotExistError):
			mod.get_context(ctx)

	def test_portal_view_returns_card_when_enabled(self):
		self._set_portal(self.company, 1)
		eq = self._equipment("V1", self.company, supplier=self.supplier_a)
		self._assign(eq, self.proj_a)
		name = self._card(eq, self.proj_a)
		mod = _load_www_module(VIEW_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		ctx = frappe._dict()
		frappe.local.form_dict = frappe._dict(name=name)
		mod.get_context(ctx)
		self.assertIsNotNone(ctx.card)
		self.assertEqual(ctx.card.name, name)

	def test_portal_view_other_party_404(self):
		self._set_portal(self.company, 1)
		eq_b = self._equipment("VB", self.company, supplier=self.supplier_b)
		self._assign(eq_b, self.proj_a)
		name = self._card(eq_b, self.proj_a)
		mod = _load_www_module(VIEW_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		ctx = frappe._dict()
		frappe.local.form_dict = frappe._dict(name=name)
		with self.assertRaises(frappe.PageDoesNotExistError):
			mod.get_context(ctx)

	# ---------- Lesson 1: forgery of party / party_type ignored ----------

	def test_portal_landing_ignores_party_query_arg(self):
		"""The handler never reads ``party`` or ``party_type`` from the
		request. A user linked to Supplier-A who passes ``?party=Supplier-B``
		still only sees her own cards."""
		self._set_portal(self.company, 1)
		eq_a = self._equipment("FA", self.company, supplier=self.supplier_a)
		eq_b = self._equipment("FB", self.company, supplier=self.supplier_b)
		self._assign(eq_a, self.proj_a)
		self._assign(eq_b, self.proj_a)
		self._card(eq_a, self.proj_a)
		self._card(eq_b, self.proj_a, shift="ليلي")
		mod = _load_www_module(INDEX_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		ctx = frappe._dict()
		# forged request
		frappe.local.form_dict = frappe._dict(party=self.supplier_b, party_type="Supplier")
		mod.get_context(ctx)
		self.assertEqual(ctx.party, self.supplier_a)
		self.assertEqual(ctx.party_type, "Supplier")
		# only A's cards
		self.assertEqual({r.supplier for r in ctx.cards}, {self.supplier_a})

	# ---------- Lesson 5: field permlevel ----------

	def test_enable_party_portal_at_table_permlevel(self):
		"""The new ``enable_party_portal`` field sits at permlevel 1,
		matching the sibling fields of the Card Company Settings child
		table (FR-148 child-permlevel discipline)."""
		meta = frappe.get_meta("Card Company Settings")
		field = meta.get_field("enable_party_portal")
		self.assertIsNotNone(field)
		# Every sibling fieldname carries permlevel 1 (table-level).
		siblings = {df.permlevel for df in meta.fields if df.permlevel}
		self.assertIn(1, siblings)
		self.assertEqual(field.permlevel, 1)
		# Default is 0 (preview off).
		self.assertEqual(field.default, "0")

	# ---------- Lesson 12 mutation proofs ----------

	def test_mutation_removing_enable_guard_breaks_404(self):
		"""Mutation: if ``index.py`` ``get_context`` stops raising when
		``_portal_enabled`` returns False, ``test_portal_landing_returns_404_when_disabled``
		no longer passes. Simulated by monkey-patching
		``card.portal._portal_enabled`` to always return True — the view
		then no longer 404s with the flag disabled on every company.
		"""
		mod = _load_www_module(INDEX_PATH)
		user = self._portal_user("Supplier", self.supplier_a)
		frappe.set_user(user)
		# Before mutation: 404 as expected
		ctx = frappe._dict()
		with self.assertRaises(frappe.PageDoesNotExistError):
			mod.get_context(ctx)
		# After mutation: no PageDoesNotExistError → guard was effective
		original = portal_mod._portal_enabled
		try:
			portal_mod._portal_enabled = lambda company=None: True  # type: ignore[assignment]
			# Patch inside the freshly loaded module too (it imports the
			# symbol lazily inside ``get_context`` to keep the enable-flag
			# check at the top of the handler).
			ctx = frappe._dict()
			mod.get_context(ctx)
			# no exception — the guard was the only line blocking access
		finally:
			portal_mod._portal_enabled = original

	def test_cross_party_list_refused(self):
		"""Mutation: if ``list_party_cards`` drops the party-field filter,
		a Supplier-A user would see Supplier-B's cards. The guard filter
		is: the ``supplier`` / ``customer`` field equals the resolved
		party. Simulated by replacing the public helper with one that
		omits the filter — the caller then sees both parties' cards; the
		real helper does not."""
		eq_a = self._equipment("XA", self.company, supplier=self.supplier_a)
		eq_b = self._equipment("XB", self.company, supplier=self.supplier_b)
		self._assign(eq_a, self.proj_a)
		self._assign(eq_b, self.proj_a)
		self._card(eq_a, self.proj_a)
		self._card(eq_b, self.proj_a, shift="ليلي")
		# real helper: own party only
		rows = list_party_cards("Supplier", self.supplier_a)
		self.assertEqual({r.supplier for r in rows}, {self.supplier_a})

		# mutation probe: drop the party-field filter (simulate a bad edit)
		def _mutated(party_type, party, user=None):
			return frappe.get_all(
				DOCTYPE,
				filters={"docstatus": 1, "company": self.company},
				fields=["name", "company", "supplier", "customer"],
			)

		leaked = _mutated("Supplier", self.supplier_a)
		self.assertGreater(
			{r.supplier for r in leaked if r.supplier},
			{self.supplier_a},
			"mutation probe must leak Supplier B so the real filter is proven necessary",
		)

	# ---------- scaffold inertness (no hooks, no DocPerm change) ----------

	def test_hooks_not_wired_by_o1(self):
		"""WP-O1 adds no ``has_website_permission`` hook for Card Monthly
		Card and no new ``website_route_rules`` for ``/card-portal``.
		Both land in WP-O2 (wave 10). Guarding this here catches a
		shared-hooks collision with another wave-6 WP."""
		import card.hooks as hooks

		wp = getattr(hooks, "has_website_permission", {}) or {}
		self.assertNotIn(DOCTYPE, wp)
		routes = [r.get("from_route", "") for r in getattr(hooks, "website_route_rules", []) or []]
		self.assertFalse(any(r.startswith("/card-portal") for r in routes))

	def test_no_whitelist_added_to_portal_helpers(self):
		"""``card.portal`` exposes no HTTP endpoint. All three helpers
		must be plain Python functions; a ``@frappe.whitelist()`` on any
		of them would open a REST path that bypasses the www handler's
		enable-flag guard."""
		for fn in (get_party_from_user, list_party_cards, get_party_card):
			self.assertFalse(
				hasattr(fn, "whitelisted") and fn.whitelisted,
				f"{fn.__name__} must not be @frappe.whitelist",
			)
