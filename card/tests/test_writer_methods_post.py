# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-136 (#54, risk R-16): every whitelisted CARD function that writes accepts POST only.

AGENTS.md: "Every @frappe.whitelist declares methods=: ["GET"] only for reads without side effects, ["POST"] for
anything that writes." With ``methods=None`` Frappe allows GET, POST, PUT and DELETE and checks CSRF for the last
three only, so a writer reachable by GET can be triggered by a link or an image tag.

The tests prove, for every whitelisted function of the app (tests excluded):

1. the decorator names ``methods=`` explicitly;
2. a function the FR-129 matrix marks as writing (``Case.writes``) allows exactly POST;
3. a function that allows GET is marked read-only in the matrix and has no direct write call in its body;
4. Frappe itself refuses a GET request to every writer (``frappe.handler.is_valid_http_method``) and accepts POST.

``card/tests/test_bola_matrix.py`` proves at run time that the read endpoints write nothing; this module is the
POST side of the same rule."""

import ast
import types

import frappe
from frappe.handler import is_valid_http_method
from frappe.tests import IntegrationTestCase

from card.tests.test_bola_matrix import CASES, REPO, whitelisted_functions

# a direct call of one of these in a function body is a write (inserts, saves, workflow actions, raw writes)
WRITE_CALLS = frozenset(
	{
		"insert",
		"save",
		"submit",
		"cancel",
		"delete",
		"db_set",
		"db_insert",
		"db_update",
		"set_value",
		"set_single_value",
		"delete_doc",
		"rename_doc",
		"add_comment",
		"enqueue",
	}
)


def _function_nodes():
	"""``module.function`` -> (ast node, file) for every whitelisted function (tests excluded)."""
	nodes = {}
	root = REPO / "card"
	for path in sorted(root.rglob("*.py")):
		if "tests" in path.relative_to(root).parts:
			continue
		module = ".".join(path.relative_to(REPO).with_suffix("").parts)
		for node in ast.walk(ast.parse(path.read_text())):
			if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and any(
				"whitelist" in ast.unparse(d) for d in node.decorator_list
			):
				nodes[f"{module}.{node.name}"] = (node, path.relative_to(REPO))
	return nodes


def _whitelist_decorator(node):
	for decorator in node.decorator_list:
		if "whitelist" in ast.unparse(decorator):
			return decorator
	return None


def _direct_writes(node):
	"""Names of write calls made directly in the function body."""
	found = set()
	for sub in ast.walk(node):
		if isinstance(sub, ast.Call):
			func = sub.func
			name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
			if name in WRITE_CALLS:
				found.add(name)
			if name == "sql" and sub.args and isinstance(sub.args[0], ast.Constant):
				text = str(sub.args[0].value).lstrip().lower()
				if text.startswith(("insert", "update", "delete", "replace")):
					found.add("sql write")
	return found


class TestWriterMethodsPost(IntegrationTestCase):
	def setUp(self):
		self.nodes = _function_nodes()
		self.assertEqual(set(self.nodes), set(whitelisted_functions()))
		self.assertTrue(self.nodes, "no whitelisted function found: the scan is broken")

	def test_every_whitelist_names_its_methods(self):
		for path, (node, file) in sorted(self.nodes.items()):
			with self.subTest(path=path):
				decorator = _whitelist_decorator(node)
				keywords = {kw.arg for kw in getattr(decorator, "keywords", [])}
				self.assertIn("methods", keywords, f"{file}:{node.lineno} @frappe.whitelist without methods=")

	def test_every_writer_is_post_only(self):
		writers = [path for path, case in CASES.items() if case.writes]
		self.assertTrue(writers, "the matrix marks no writer: the table is broken")
		for path in sorted(writers):
			with self.subTest(path=path):
				fn = frappe.get_attr(path)
				self.assertEqual(sorted(frappe.allowed_http_methods_for_whitelisted_func[fn]), ["POST"])

	def test_get_endpoints_are_read_only(self):
		for path in sorted(self.nodes):
			fn = frappe.get_attr(path)
			if "GET" not in frappe.allowed_http_methods_for_whitelisted_func[fn]:
				continue
			with self.subTest(path=path):
				self.assertIn(path, CASES, "a GET endpoint must be in the FR-129 matrix")
				self.assertFalse(CASES[path].writes, "the matrix marks this GET endpoint as writing")
				node, file = self.nodes[path]
				self.assertFalse(
					_direct_writes(node), f"{file}:{node.lineno} a GET endpoint calls a write directly"
				)

	def test_frappe_refuses_get_on_every_writer(self):
		saved = getattr(frappe.local, "request", None)
		try:
			for path, case in sorted(CASES.items()):
				if not case.writes:
					continue
				fn = frappe.get_attr(path)
				with self.subTest(path=path):
					frappe.local.request = types.SimpleNamespace(method="GET")
					with self.assertRaises(frappe.PermissionError):
						is_valid_http_method(fn)
					frappe.local.request = types.SimpleNamespace(method="POST")
					is_valid_http_method(fn)
		finally:
			if saved is None:
				try:
					del frappe.local.request
				except AttributeError:
					pass
			else:
				frappe.local.request = saved

	def test_write_scan_detects_a_writer(self):
		"""Control: the body scan flags a direct save and a raw UPDATE."""
		tree = ast.parse(
			"def f(name):\n"
			"    doc = frappe.get_doc('X', name)\n"
			"    doc.save()\n"
			"    frappe.db.sql('update `tabX` set a = 1')\n"
		)
		self.assertEqual(_direct_writes(tree.body[0]), {"save", "sql write"})
