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
# document functions whose doctype argument (first positional or ``doctype=``) must never be a ledger: they create,
# change or delete a row, or load one as a Document that can then be saved, submitted or cancelled
DOC_FUNCS = frozenset(
	{
		"new_doc",
		"get_doc",
		"get_cached_doc",
		"get_last_doc",
		"set_value",
		"delete",
		"delete_doc",
		"bulk_insert",
		"insert",
		"db_insert",
		"rename_doc",
	}
)
SQL_WRITES = ("insert into", "insert ignore", "update ", "delete from", "replace into", "truncate")


def _name(func):
	return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _module_ledger_names(tree):
	"""Module-level names bound to a ledger doctype string (``LEDGER = "GL Entry"``)."""
	names = set()
	for node in tree.body:
		if isinstance(node, ast.Assign | ast.AnnAssign):
			value = node.value
			targets = node.targets if isinstance(node, ast.Assign) else [node.target]
			if isinstance(value, ast.Constant) and value.value in LEDGERS:
				names.update(t.id for t in targets if isinstance(t, ast.Name))
	return names


def _ledger_writes(tree):
	"""(line, what) of every direct ledger write found in a parsed module."""
	found = []
	constants = _module_ledger_names(tree)

	def is_ledger(expr):
		if isinstance(expr, ast.Constant):
			return expr.value in LEDGERS
		return isinstance(expr, ast.Name) and expr.id in constants

	def qb_ledger_call(expr):
		# inline frappe.qb.DocType("<ledger>") / DocType(LEDGER)
		return (
			isinstance(expr, ast.Call)
			and _name(expr.func) == "DocType"
			and bool(expr.args)
			and is_ledger(expr.args[0])
		)

	qb_ledgers = set()  # names bound to frappe.qb.DocType("<ledger>")
	for node in ast.walk(tree):
		if isinstance(node, ast.Assign) and qb_ledger_call(node.value):
			qb_ledgers.update(t.id for t in node.targets if isinstance(t, ast.Name))

	def is_qb_ledger(expr):
		return qb_ledger_call(expr) or (isinstance(expr, ast.Name) and expr.id in qb_ledgers)

	for node in ast.walk(tree):
		if isinstance(node, ast.Call):
			name = _name(node.func)
			first = node.args[0] if node.args else None
			keyword = next((kw.value for kw in node.keywords if kw.arg in ("doctype", "dt")), None)
			if name in LEDGER_WRITERS:
				found.append((node.lineno, name))
			elif name in DOC_FUNCS and (is_ledger(first) or is_ledger(keyword)):
				found.append((node.lineno, f"{name}(<ledger>)"))
			elif name == "dict" and is_ledger(keyword):
				found.append((node.lineno, "dict(doctype=<ledger>)"))
			elif name in ("update", "into") and is_qb_ledger(first):
				found.append((node.lineno, f"qb.{name}(<ledger>)"))
			elif name == "delete" and isinstance(node.func, ast.Attribute):
				chain = node.func.value
				if any(
					isinstance(sub, ast.Call)
					and _name(sub.func) == "from_"
					and sub.args
					and is_qb_ledger(sub.args[0])
					for sub in ast.walk(chain)
				):
					found.append((node.lineno, "qb.from_(<ledger>).delete()"))
		elif isinstance(node, ast.Dict):
			for key, value in zip(node.keys, node.values, strict=False):
				if isinstance(key, ast.Constant) and key.value == "doctype" and is_ledger(value):
					found.append((node.lineno, "document dict <ledger>"))
		elif isinstance(node, ast.Constant) and isinstance(node.value, str):
			text = " ".join(node.value.lower().split())
			if any(table.lower() in text for table in LEDGER_TABLES) and any(w in text for w in SQL_WRITES):
				found.append((node.lineno, "raw SQL write"))
	return found


def _production_modules():
	root = REPO / "card"
	return [path for path in sorted(root.rglob("*.py")) if "tests" not in path.relative_to(root).parts]


# negative controls: (source, number of findings); each write form once, and the reads next to it never
CONTROLS = (
	("make_gl_entries(gl_map)", 1),
	("frappe.get_doc({'doctype': 'GL Entry', 'account': 'A'}).insert()", 1),
	("frappe.get_doc(dict(doctype='GL Entry', account='A')).insert()", 1),
	("frappe.get_doc('GL Entry', name).cancel()", 1),
	("frappe.get_doc(doctype='GL Entry', name=name).cancel()", 1),
	("frappe.get_cached_doc('Payment Ledger Entry', name)", 1),
	("frappe.get_cached_doc(doctype='Payment Ledger Entry', name=name)", 1),
	("frappe.get_last_doc('Stock Ledger Entry')", 1),
	("frappe.get_last_doc(doctype='Stock Ledger Entry')", 1),
	("frappe.new_doc(doctype='GL Entry')", 1),
	("frappe.db.set_value('Payment Ledger Entry', 'x', 'amount', 0)", 1),
	("frappe.db.delete('GL Entry', {'voucher_no': 'x'})", 1),
	("frappe.get_doc(LEDGER, name).cancel()", 1),
	("frappe.db.set_value(LEDGER, 'x', 'debit', 0)", 1),
	("frappe.db.sql('UPDATE `tabGL Entry` SET debit = 0')", 1),
	("gle = frappe.qb.DocType('GL Entry')\nfrappe.qb.update(gle).set(gle.debit, 0).run()", 1),
	("frappe.qb.update(frappe.qb.DocType('GL Entry')).set('debit', 0).run()", 1),
	("frappe.qb.into(frappe.qb.DocType(LEDGER)).insert(1).run()", 1),
	("frappe.qb.from_(frappe.qb.DocType('GL Entry')).delete().run()", 1),
	# reads: never a finding
	("frappe.get_all('GL Entry', fields=['debit'])", 0),
	("frappe.get_all(LEDGER, fields=['debit'])", 0),
	("frappe.db.get_value(LEDGER, {'voucher_no': 'x'}, 'debit')", 0),
	("frappe.db.sql('select debit from `tabGL Entry`')", 0),
	("frappe.qb.from_(frappe.qb.DocType('GL Entry')).select('debit').run()", 0),
	("frappe.get_doc('Purchase Invoice', name).submit()", 0),
	("frappe.get_meta('GL Entry').has_field('project')", 0),
	("x = dict(doctype='Purchase Invoice')", 0),
)


class TestGlNeutralityStatic(IntegrationTestCase):
	def test_no_module_writes_a_ledger_row(self):
		modules = _production_modules()
		scanned = {str(path.relative_to(REPO)) for path in modules}
		self.assertGreater(len(modules), 0, "the scan found no module")
		self.assertIn("card/gl/posting.py", scanned)
		offences = []
		for path in modules:
			for line, what in _ledger_writes(ast.parse(path.read_text())):
				offences.append(f"{path.relative_to(REPO)}:{line} {what}")
		self.assertEqual(offences, [], "CARD must create ERPNext documents, never ledger rows")

	def test_scan_detects_every_ledger_write_form(self):
		"""Negative controls: every write form the scan knows is detected once; the reads next to it are not."""
		for source, expected in CONTROLS:
			with self.subTest(source=source):
				module = "import frappe\nLEDGER = 'GL Entry'\ndef f(name, gl_map):\n" + "".join(
					"    " + line + "\n" for line in source.split("\n")
				)
				self.assertEqual(
					len(_ledger_writes(ast.parse(module))), expected, _ledger_writes(ast.parse(module))
				)

	def test_module_constant_alone_is_not_a_finding(self):
		self.assertEqual(_ledger_writes(ast.parse("LEDGER = 'GL Entry'\nDOCTYPES = ('GL Entry',)\n")), [])


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
