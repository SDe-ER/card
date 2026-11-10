# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-136 (#54 acceptance "GL neutrality", test matrix row 15): CARD never writes a ledger row itself.

AGENTS.md: "CARD never writes GL entries; it creates standard ERPNext documents."

- Static: no production module of the app inserts, updates or deletes a ledger row (GL Entry, Payment Ledger
  Entry, Stock Ledger Entry, Account Closing Balance) by document, by ``frappe.db`` or by raw SQL / query builder,
  and none calls an ERPNext ledger writer (``make_gl_entries`` and the like).
- Run time: submitting and cancelling CARD documents (monthly card, diesel fill, transport) adds no ledger row; building the monthly posting (a draft invoice) adds none; only the submit of the
  ERPNext Purchase Invoice adds rows, and every one of them belongs to that invoice and balances."""

import ast

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.gl.posting import build_monthly_posting
from card.tests.cancel_reason import with_reason
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_bola_matrix import REPO
from card.tests.test_s3_posting import _PostingBase
from card.tests.transport_parties import company_paid

LEDGERS = ("GL Entry", "Payment Ledger Entry", "Stock Ledger Entry", "Account Closing Balance")
LEDGER_TABLES = tuple("tab" + name for name in LEDGERS)
LEDGER_WRITERS = frozenset(
	{
		"make_gl_entries",
		"make_reverse_gl_entries",
		"make_entry",
		"save_entries",
		"create_payment_ledger_entry",
		"make_sl_entries",
		"make_acc_dimensions_offsetting_entry",
	}
)
DOC_WRITERS = frozenset(
	{"new_doc", "set_value", "delete", "delete_doc", "bulk_insert", "insert", "db_insert", "rename_doc"}
)
SQL_WRITES = ("insert into", "insert ignore", "update ", "delete from", "replace into", "truncate")


def _name(func):
	return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _ledger_writes(tree):
	"""(line, what) of every direct ledger write found in a parsed module."""
	found = []
	qb_ledgers = set()  # names bound to frappe.qb.DocType("<ledger>")
	for node in ast.walk(tree):
		if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
			call = node.value
			if (
				_name(call.func) == "DocType"
				and call.args
				and isinstance(call.args[0], ast.Constant)
				and call.args[0].value in LEDGERS
			):
				qb_ledgers.update(t.id for t in node.targets if isinstance(t, ast.Name))
	for node in ast.walk(tree):
		if isinstance(node, ast.Call):
			name = _name(node.func)
			first = node.args[0] if node.args else None
			if name in LEDGER_WRITERS:
				found.append((node.lineno, name))
			elif name in DOC_WRITERS and isinstance(first, ast.Constant) and first.value in LEDGERS:
				found.append((node.lineno, f"{name}({first.value!r})"))
			elif name in ("update", "into") and isinstance(first, ast.Name) and first.id in qb_ledgers:
				found.append((node.lineno, f"qb.{name}({first.id})"))
			elif (
				name == "delete"
				and isinstance(node.func, ast.Attribute)
				and qb_ledgers
				and any(isinstance(n, ast.Name) and n.id in qb_ledgers for n in ast.walk(node.func.value))
			):
				found.append((node.lineno, "qb delete"))
		elif isinstance(node, ast.Dict):
			for key, value in zip(node.keys, node.values, strict=False):
				if (
					isinstance(key, ast.Constant)
					and key.value == "doctype"
					and isinstance(value, ast.Constant)
					and value.value in LEDGERS
				):
					found.append((node.lineno, f"document dict {value.value!r}"))
		elif isinstance(node, ast.Constant) and isinstance(node.value, str):
			text = " ".join(node.value.lower().split())
			if any(table.lower() in text for table in LEDGER_TABLES) and any(w in text for w in SQL_WRITES):
				found.append((node.lineno, "raw SQL write"))
	return found


class TestGlNeutralityStatic(IntegrationTestCase):
	def test_no_module_writes_a_ledger_row(self):
		root = REPO / "card"
		offences = []
		for path in sorted(root.rglob("*.py")):
			if "tests" in path.relative_to(root).parts:
				continue
			for line, what in _ledger_writes(ast.parse(path.read_text())):
				offences.append(f"{path.relative_to(REPO)}:{line} {what}")
		self.assertEqual(offences, [], "CARD must create ERPNext documents, never ledger rows")

	def test_scan_detects_ledger_writes(self):
		"""Control: every write form the scan knows is detected; reads are not."""
		tree = ast.parse(
			"from erpnext.accounts.general_ledger import make_gl_entries\n"
			"def f(gl_map):\n"
			"    make_gl_entries(gl_map)\n"
			"    frappe.get_doc({'doctype': 'GL Entry', 'account': 'A'}).insert()\n"
			"    frappe.db.set_value('Payment Ledger Entry', 'x', 'amount', 0)\n"
			"    frappe.db.sql('UPDATE `tabGL Entry` SET debit = 0')\n"
			"    gle = frappe.qb.DocType('GL Entry')\n"
			"    frappe.qb.update(gle).set(gle.debit, 0).run()\n"
			"def reads():\n"
			"    frappe.get_all('GL Entry', fields=['debit'])\n"
			"    frappe.db.sql('select debit from `tabGL Entry`')\n"
		)
		lines = sorted(line for line, _what in _ledger_writes(tree))
		self.assertEqual(lines, [3, 4, 5, 6, 8])


class TestGlNeutralityRuntime(_PostingBase):
	def _ledger_counts(self):
		return {doctype: frappe.db.count(doctype) for doctype in LEDGERS}

	def _fill(self, eq, litres):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"card_equipment": eq.name,
				"company": self.company,
				"litres": litres,
				"unit_price": 2,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		return fill

	def _transport(self, eq):
		place = frappe.new_doc("Location")
		place.location_name = "TEST-GLN-SHOP-" + self.token
		place.insert(ignore_permissions=True)
		cost_center = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		settings = frappe.get_single("Card Settings")
		settings.append(
			"location_cost_centers",
			{"company": self.company, "location": place.name, "cost_center": cost_center},
		)
		settings.save(ignore_permissions=True)
		transport = frappe.get_doc(
			{
				"doctype": "Equipment Transport",
				"date": "2026-09-14",
				"destination_type": "Workshop",
				"destination_location": place.name,
				"transport_supplier": self.supplier,
				"company": self.company,
				"amount": 300,
				"items": [{"card_equipment": eq.name}],
			}
		)
		company_paid(transport, basis="Workshop or storage").insert(ignore_permissions=True)
		transport.submit()
		return transport

	def test_card_documents_write_no_ledger_row(self):
		before = self._ledger_counts()
		eq = self._equipment()
		card = self._card(eq, [8, 8], submit=True)
		other = self._card(self._equipment(), [4], submit=True)
		fill = self._fill(eq, 50)
		transport = self._transport(eq)
		self.assertEqual(self._ledger_counts(), before, "submitting CARD documents wrote ledger rows")
		with_reason(frappe.get_doc("Card Monthly Card", other.name)).cancel()
		with_reason(frappe.get_doc("Project Diesel Fill", fill.name)).cancel()
		with_reason(frappe.get_doc("Equipment Transport", transport.name)).cancel()
		self.assertEqual(self._ledger_counts(), before, "cancelling CARD documents wrote ledger rows")
		self.assertTrue(card.name)

	def test_ledger_rows_come_only_from_the_submitted_invoice(self):
		self._vat_supplier()
		eq, card = self._example_card()
		self._fill(eq, 100)
		before = self._ledger_counts()
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(self._ledger_counts(), before, "the draft posting wrote ledger rows")
		pi = frappe.get_doc("Purchase Invoice", pi_name)
		pi.bill_no = "TEST-GLN-" + self.token
		pi.bill_date = pi.posting_date
		pi.submit()
		new_gl = frappe.get_all(
			"GL Entry",
			filters={"creation": [">=", pi.creation], "company": self.company},
			fields=["voucher_type", "voucher_no", "debit", "credit"],
		)
		self.assertTrue(new_gl)
		self.assertEqual({(g.voucher_type, g.voucher_no) for g in new_gl}, {("Purchase Invoice", pi_name)})
		self.assertEqual(
			flt(sum(g.debit for g in new_gl), 2),
			flt(sum(g.credit for g in new_gl), 2),
			"the ledger is unbalanced",
		)
		self.assertEqual(
			frappe.db.count("GL Entry") - before["GL Entry"],
			frappe.db.count("GL Entry", {"voucher_type": "Purchase Invoice", "voucher_no": pi_name}),
		)
		# CARD only writes the invoice link and the posted flag on its sources
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"), pi_name)

	def test_one_active_posting_per_party_month_is_a_database_rule(self):
		"""Test matrix row 14: two builds racing past the Python checks still meet the unique posting key."""
		self._card(self._equipment(), [5], submit=True)
		pi_name = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		log = frappe.get_doc("GL Posting Log", {"posting_doc": pi_name, "status": "Draft"})
		self.assertTrue(log.posting_key)
		twin = frappe.new_doc("GL Posting Log")
		twin.update(
			{
				key: log.get(key)
				for key in ("company", "party_type", "party", "month", "year", "posting_type", "posting_key")
			}
		)
		twin.status = "Draft"
		twin.name = "TEST-GLN-TWIN-" + self.token
		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			twin.db_insert()
