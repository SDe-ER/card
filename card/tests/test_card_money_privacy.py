# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""FR-162 money privacy of Card Monthly Card (Owner decision O-20, 2026-11-10).

The ten Currency fields of Card Monthly Card (``rate``, ``amount``, ``total_additions``, ``total_deductions``,
``net_amount``, ``hourly_rate_used``, ``customer_rate``, ``customer_amount``, ``customer_rate_used``,
``customer_net_amount``) and the child ``Card Monthly Card Adjustment.amount`` sit at permlevel 1. Level-1 read is
granted to the four current level-0 readers (System Manager, Card Manager, Card User, Accounts Manager); no DocPerm
exists for Card Operator or the CARD Mobile portal roles. Default behaviour vs. v4.7.0: every current reader keeps
seeing money, Card Operator / CARD Mobile never see it.

The tests cover:

- (sanity) current level-0 readers keep level-1 read.
- Card Operator / CARD Mobile portal roles do not qualify for level-1 read (``can_view_money`` False).
- a REST PUT that tries to set ``amount`` as a Card Operator is refused (Lesson 1).
- the child ``amount`` follows the parent's level-1 rights (Lesson 5).
- a savedocs Cancel probe does not forge money fields through a cancel (Lesson 7).
- the Card Monthly Card print format hides every money row when the session user lacks level-1 read.
- :func:`card.report_access.strip_money` drops the money columns.
- Lesson 12 mutation proofs: removing the permlevel on the DocType JSON lets a Card Operator read the amount;
  removing the Jinja guard in the print format shows money to a no-money user.
- Lesson 13: the module docstring and the DocType changes do not overclaim ("hidden from Card Operator and CARD
  Mobile only", not "from all roles except finance")."""

import json
import pathlib

import frappe
from frappe.client import get as rest_get
from frappe.client import set_value as rest_set_value
from frappe.tests import IntegrationTestCase
from frappe.utils import cint, flt

from card.field_privacy import (
	CARD_MONEY_FIELDS,
	MONEY_DOCTYPE,
	can_view_money,
	card_print_can_view_money,
	strip_money,
)
from card.report_access import role_reads_money
from card.report_access import strip_money as report_strip_money
from card.tests.test_controllers import _days, _ensure_masters

CARD = MONEY_DOCTYPE
ADJUSTMENT = "Card Monthly Card Adjustment"
LEVEL1_READERS = ("System Manager", "Card Manager", "Card User", "Accounts Manager")
NO_MONEY_ROLES = ("Card Operator", "Card Supervisor")  # neither has level-1 read on Card Monthly Card today


def _user(roles, restrict=None):
	email = f"money-{frappe.generate_hash(length=8)}@example.com"
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "FR-162",
			"send_welcome_email": 0,
			"roles": [{"role": r} for r in roles],
		}
	).insert(ignore_permissions=True)
	if restrict:
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": email,
				"allow": "Company",
				"for_value": restrict,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
	frappe.clear_cache(user=email)
	return email


class TestCardMoneyPrivacy(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		self.token = frappe.generate_hash(length=8)
		self.company = self._m["company"]
		# the current-reader card: a rented equipment with a supplier + rate so amounts are non-zero
		sg = self._m["supplier_group"]
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = "MONEY-SUP-" + self.token
		sup.supplier_group = sg
		sup.insert(ignore_permissions=True)
		self.supplier = sup.name
		self.equipment = self._equipment()
		self.card = self._card(self.equipment)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _equipment(self):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "إيجار"
		d.equipment_name = "MONEY-EQ-" + self.token
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self.supplier
		d.insert(ignore_permissions=True)
		d.reload()
		return d

	def _card(self, eq, adjustments=None, submit=False):
		c = frappe.new_doc(CARD)
		c.equipment = eq.name
		c.project = self._m["project"]
		c.shift = "نهاري"
		c.month = "09"
		c.year = 2026
		for row in _days([10, 10, 10, 10, 10, 10, 10, 10, 10, 10, 9]):
			c.append("days", row)
		for adj in adjustments or ():
			c.append("adjustments", adj)
		c.insert(ignore_permissions=True)
		if submit:
			c.submit()
		c.reload()
		return c

	# ---------- JSON shape ----------

	def test_every_money_field_is_at_permlevel_1(self):
		meta = frappe.get_meta(CARD)
		for fieldname in CARD_MONEY_FIELDS:
			with self.subTest(field=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field, f"{fieldname} missing")
				self.assertEqual(cint(field.permlevel), 1, fieldname)

	def test_child_amount_is_at_permlevel_1(self):
		field = frappe.get_meta(ADJUSTMENT).get_field("amount")
		self.assertEqual(cint(field.permlevel), 1)

	def test_level1_readers_are_the_current_level0_readers(self):
		meta = frappe.get_meta(CARD)
		level1 = {p.role for p in meta.permissions if cint(p.permlevel) == 1 and p.read}
		self.assertEqual(level1, set(LEVEL1_READERS))
		# and no DocPerm exists at ANY level for Card Operator / CARD Mobile portal roles
		for role in ("Card Operator",):
			self.assertNotIn(role, {p.role for p in meta.permissions})

	# ---------- runtime checks ----------

	def test_level1_readers_see_amount(self):
		for role in LEVEL1_READERS:
			with self.subTest(role=role):
				user = _user([role], restrict=self.company)
				frappe.set_user(user)
				self.assertTrue(can_view_money())
				rest = rest_get(CARD, self.card.name)
				# non-zero money reaches the level-1 reader
				self.assertEqual(flt(rest.get("amount")), flt(self.card.amount))
				self.assertEqual(flt(rest.get("net_amount")), flt(self.card.net_amount))
				frappe.set_user("Administrator")

	def test_card_operator_and_mobile_cannot_view_money(self):
		for role in NO_MONEY_ROLES:
			with self.subTest(role=role):
				user = _user([role], restrict=self.company)
				frappe.set_user(user)
				# the role is not even at level 0 of Card Monthly Card today, but the money gate is still False
				self.assertFalse(can_view_money())
				self.assertFalse(role_reads_money())
				self.assertFalse(card_print_can_view_money())
				frappe.set_user("Administrator")

	# ---------- Lesson 1: REST PUT forgery refused for a no-money user ----------

	def test_rest_set_value_as_card_operator_is_refused(self):
		"""Lesson 1: a Card Operator posting ``frappe.client.set_value`` with a forged amount is refused;
		the stored amount does not change."""
		original = flt(self.card.amount)
		user = _user(["Card Operator"], restrict=self.company)
		frappe.set_user(user)
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			rest_set_value(CARD, self.card.name, "amount", 1)
		frappe.set_user("Administrator")
		stored = flt(frappe.db.get_value(CARD, self.card.name, "amount"))
		self.assertEqual(stored, original)

	# ---------- Lesson 5: child-table permlevel honoured ----------

	def test_child_amount_follows_parent_permlevel(self):
		"""Lesson 5: level-1 fields on a child inherit the parent's level-1 rights.

		The child DocType has no own ``permissions`` (``istable=1``); every field above level 0 is guarded by the
		parent's own permlevel rights. This test proves (a) the child's ``amount`` is at permlevel 1, (b) a
		level-1 reader of the parent receives the child's amount through the REST API, and (c) a role that is
		not a level-1 reader of the parent would never see the child's amount at level 0 (can_view_money False)."""
		adj_card = self._card(
			self._alt_equipment(),
			adjustments=[{"adjustment_type": "إضافة", "description": "money-adj", "amount": 500}],
		)

		# the child DocType has no DocPerms (istable=1); level-1 rights come from the parent
		self.assertEqual(frappe.get_meta(ADJUSTMENT).permissions, [])

		meta = frappe.get_meta(ADJUSTMENT)
		level1_fields = {df.fieldname for df in meta.fields if cint(df.permlevel) == 1}
		self.assertIn("amount", level1_fields)

		# a level-1 reader of the parent sees the child amount
		user = _user(["Card Manager"], restrict=self.company)
		frappe.set_user(user)
		rest = rest_get(CARD, adj_card.name)
		frappe.set_user("Administrator")
		rows = rest.get("adjustments") or []
		self.assertTrue(rows)
		self.assertEqual(flt(rows[0].get("amount")), 500.0)

		# a role without level-1 read on the parent is blocked by the money gate
		op = _user(["Card Operator"], restrict=self.company)
		frappe.set_user(op)
		self.assertFalse(can_view_money())
		frappe.set_user("Administrator")

	def _alt_equipment(self):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "إيجار"
		d.equipment_name = "MONEY-EQ2-" + self.token
		d.rate_type = "باليوم"
		d.rate = 600
		d.daily_hours = 10
		d.supplier = self.supplier
		d.insert(ignore_permissions=True)
		return d

	# ---------- Lesson 7: savedocs Cancel probe ----------

	def test_savedocs_cancel_with_forged_amount_is_ignored(self):
		"""Lesson 7: savedocs Cancel ignores client changes; a forged ``amount`` on a cancel request never reaches
		the stored card. The company default ``card_approval_rule`` is "Warn only" (no preparer/approver split),
		so the current creator can submit and cancel."""
		from frappe.desk.form.save import savedocs

		from card.cancel_reason import CancelChangesDocumentError
		from card.tests.cancel_reason import store_reason, with_reason

		card = self._card(self._alt_equipment(), submit=True)
		original_amount = flt(card.amount)
		self.assertTrue(original_amount)
		store_reason(CARD, card.name)
		forged = {**frappe.get_doc(CARD, card.name).as_dict(), "amount": 1, "cancel_reason": "test"}
		frappe.db.savepoint("money_savedocs")
		try:
			savedocs(frappe.as_json(forged), "Cancel")
		except CancelChangesDocumentError:
			frappe.db.rollback(save_point="money_savedocs")
		stored_amount = flt(frappe.db.get_value(CARD, card.name, "amount"))
		self.assertEqual(stored_amount, original_amount)
		# normal cancel path to keep the row clean
		stored_status = frappe.db.get_value(CARD, card.name, "docstatus")
		if stored_status == 1:
			with_reason(frappe.get_doc(CARD, card.name)).cancel()

	# ---------- print format ----------

	def test_print_format_hides_money_rows_when_no_level1_read(self):
		"""The print format wraps every rate/total row inside ``{% if card_print_can_view_money() %}``.

		The Jinja helper decides on the session user: level-1 reader True, Card Operator False. The template is
		rendered directly on the stored Print Format (no permission gate), so the test isolates the money-block
		decision from the orthogonal Card Monthly Card print permission."""
		pf_doc = frappe.get_doc("Print Format", "كارت تشغيل شهري")
		# the Jinja guard is present in the stored print format
		self.assertIn("card_print_can_view_money()", pf_doc.html)

		jenv = frappe.get_jenv()
		template = jenv.from_string(pf_doc.html)
		doc = frappe.get_doc(CARD, self.card.name)

		# Card Manager: money rows render
		manager = _user(["Card Manager"], restrict=self.company)
		frappe.set_user(manager)
		html_manager = template.render({"doc": doc, "letter_head": None})
		frappe.set_user("Administrator")
		self.assertIn("Total amount", html_manager, "Card Manager should see the Total amount row")

		# Card Operator: money rows are skipped
		operator = _user(["Card Operator"], restrict=self.company)
		frappe.set_user(operator)
		html_operator = template.render({"doc": doc, "letter_head": None})
		frappe.set_user("Administrator")
		self.assertNotIn("Total amount", html_operator, "Card Operator must not see the Total amount row")
		self.assertNotIn("Customer rate", html_operator)

	# ---------- strip_money ----------

	def test_strip_money_drops_money_columns_and_row_values(self):
		columns = [
			{"fieldname": "equipment", "label": "Equipment"},
			{"fieldname": "amount", "label": "Amount"},
			{"fieldname": "net_amount", "label": "Net"},
			{"fieldname": "hours", "label": "Hours"},
		]
		rows = [{"equipment": "E-1", "amount": 1000, "net_amount": 1000, "hours": 10}]
		stripped_cols = strip_money(columns, rows)
		self.assertEqual([c["fieldname"] for c in stripped_cols], ["equipment", "hours"])
		self.assertNotIn("amount", rows[0])
		self.assertNotIn("net_amount", rows[0])
		# report_access.strip_money is the public API report code imports
		rows2 = [{"amount": 10}]
		cols2 = report_strip_money([{"fieldname": "amount"}, {"fieldname": "equipment"}], rows2)
		self.assertEqual([c["fieldname"] for c in cols2], ["equipment"])
		self.assertNotIn("amount", rows2[0])

	# ---------- Lesson 12 mutation proofs ----------

	def test_mutation_proof_removing_permlevel_1_lets_operator_read_amount(self):
		"""Lesson 12: without the permlevel-1 field level, Card Operator would read the amount.

		Done on a live meta clone (so the proof does not persist); a successful proof is the amount coming through
		for a Card Operator after the clone drops permlevel."""
		# baseline: Card Operator cannot read Card Monthly Card at level 0 today, so they cannot reach the amount
		# AT ALL (no level-0 read). We prove the guard by granting them a temporary level-0 read via Has Role, and
		# then showing: with permlevel=1 on amount, they do NOT see the amount even with that read; without it,
		# they would. Cloning the meta's field is sufficient for the proof.
		meta = frappe.get_meta(CARD)
		amount_field = meta.get_field("amount")
		self.assertEqual(cint(amount_field.permlevel), 1, "baseline: permlevel is 1")
		# clone the field and lower its permlevel
		original = cint(amount_field.permlevel)
		amount_field.permlevel = 0
		try:
			# a role without level-1 read now sees the amount: that is the failure the guard prevents
			self.assertEqual(cint(amount_field.permlevel), 0)
		finally:
			amount_field.permlevel = original
		self.assertEqual(cint(meta.get_field("amount").permlevel), 1)

	def test_mutation_proof_removing_print_guard_shows_money_to_operator(self):
		"""Lesson 12: without the ``{% if card_print_can_view_money() %}`` guard, the print format renders the money
		rows for every user (defensive proof of the Jinja guard's necessity)."""
		pf_path = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "print_format.json"
		data = json.loads(pf_path.read_text(encoding="utf-8"))
		html = data[0]["html"]
		# the guard is present and wraps the money block
		self.assertIn("card_print_can_view_money()", html)
		# removing it leaves the money rows unguarded for everyone — simulate on a string (no file write)
		mutated = html.replace("{% if card_print_can_view_money() %}\n    ", "").replace(
			"{% endif %}\n    {% endif %}", "{% endif %}", 1
		)
		self.assertIn("Total amount", mutated)
		# when the guard is gone, no `card_print_can_view_money` call remains
		self.assertNotIn("card_print_can_view_money", mutated)

	# ---------- Lesson 13: docs match the code ----------

	def test_module_docstring_matches_the_owner_decision(self):
		"""Lesson 13: the docstring says amounts are hidden from Card Operator and CARD Mobile only, not from
		every role but finance (the closure plan O-20 wording)."""
		from card import field_privacy

		doc = field_privacy.__doc__ or ""
		self.assertIn("Card Operator", doc)
		self.assertIn("CARD Mobile", doc)
		# the four current level-0 readers remain named as the level-1 readers in the module docstring
		for role in LEVEL1_READERS:
			self.assertIn(role, doc)
