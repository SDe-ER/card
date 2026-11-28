# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""Issue #358: the CARD Mobile management view. Review roles see every machine, project and card of
their permitted companies whoever operates it; operators, Card User and Guest are refused; money goes
to Card Manager and System Manager only (Owner decision 2026-11-28). Counts are exact."""

import frappe
from frappe.tests import IntegrationTestCase

from card import mobile_management as mm
from card.tests.test_controllers import _days, _ensure_masters

ENDED = "منتهية"


class TestMobileManagement(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	def setUp(self):
		frappe.set_user("Administrator")
		self.token = frappe.generate_hash(length=6)
		self.company = self._m["company"]

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _user(self, prefix, roles, scope_company=True):
		email = f"mgmt-{prefix}-{self.token}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		if scope_company:
			frappe.get_doc(
				{
					"doctype": "User Permission",
					"user": email,
					"allow": "Company",
					"for_value": self.company,
					"apply_to_all_doctypes": 1,
				}
			).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _supplier(self):
		sup = frappe.new_doc("Supplier")
		sup.supplier_name = f"MGMT-SUP-{self.token}-{frappe.generate_hash(length=4)}"
		sup.supplier_group = self._m["supplier_group"]
		sup.insert(ignore_permissions=True)
		return sup.name

	def _equipment(self, **values):
		d = frappe.new_doc("Card Equipment")
		d.company = self.company
		d.equipment_type = self._m["etype"]
		d.ownership = "إيجار"
		d.equipment_name = f"MGMT-EQ-{self.token}-{frappe.generate_hash(length=4)}"
		d.rate_type = "باليوم"
		d.rate = 750
		d.daily_hours = 10
		d.supplier = self._supplier()
		d.update(values)
		return d.insert(ignore_permissions=True)

	def _card(self, equipment, month="09"):
		doc = frappe.new_doc("Card Monthly Card")
		doc.equipment = equipment.name
		doc.project = self._m["project"]
		doc.shift = "نهاري"
		doc.month = month
		doc.year = 2026
		for row in _days([10] * 5):
			doc.append("days", row)
		doc.insert(ignore_permissions=True)
		return doc

	# ---------- role gate ----------
	def test_operator_card_user_and_guest_are_refused(self):
		for index, roles in enumerate((["Card Operator"], ["Card User"], [])):
			user = self._user(f"deny{index}", roles)
			for fn in (
				mm.get_management_context,
				mm.list_all_equipment,
				mm.list_monthly_cards,
				mm.list_projects,
			):
				with self.subTest(roles=roles, fn=fn.__name__), self.assertRaises(frappe.PermissionError):
					self._as(user, fn)
		for fn in (mm.get_management_context, mm.list_all_equipment, mm.list_monthly_cards, mm.list_projects):
			with self.subTest(guest=fn.__name__), self.assertRaises(frappe.PermissionError):
				self._as("Guest", fn)

	def test_endpoint_methods(self):
		for fn in (mm.get_management_context, mm.list_all_equipment, mm.list_monthly_cards, mm.list_projects):
			self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[fn], ["GET"])

	# ---------- fleet ----------
	def test_supervisor_sees_every_machine_whoever_operates_it(self):
		before = frappe.db.count("Card Equipment", {"company": self.company, "status": ["!=", ENDED]})
		self._equipment()
		self._equipment(status=ENDED)  # ended machines are never listed
		user = self._user("sup", ["Card Supervisor"])
		rows = self._as(user, mm.list_all_equipment)
		self.assertEqual(len(rows), before + 1)
		self.assertTrue(all(set(r) >= {"name", "equipment_name", "ownership", "status"} for r in rows))
		self.assertFalse(any("rate" in r or "net_amount" in r for r in rows))

	def test_fleet_filters(self):
		own = self._equipment(ownership="تشغيل داخلي", supplier=None)
		user = self._user("filter", ["Card Supervisor"])
		names = [r.name for r in self._as(user, mm.list_all_equipment, ownership="تشغيل داخلي")]
		self.assertIn(own.name, names)
		rented = [r.name for r in self._as(user, mm.list_all_equipment, ownership="إيجار")]
		self.assertNotIn(own.name, rented)
		with self.assertRaises(frappe.PermissionError):
			self._as(user, mm.list_all_equipment, ownership="x' or '1'='1")

	def test_company_restricted_reviewer_sees_no_other_company(self):
		self._equipment()
		other = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"Other {self.token}",
				"abbr": f"O{self.token[:3]}".upper(),
				"default_currency": "SAR",
				"country": "Saudi Arabia",
			}
		).insert(ignore_permissions=True)
		user = self._user("other", ["Card Supervisor"], scope_company=False)
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user,
				"allow": "Company",
				"for_value": other.name,
				"apply_to_all_doctypes": 1,
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=user)
		self.assertEqual(self._as(user, mm.list_all_equipment), [])
		self.assertEqual(self._as(user, mm.list_monthly_cards, 2026, 9), [])

	# ---------- cards ----------
	def test_supervisor_cards_have_no_money_and_manager_cards_have_it(self):
		card = self._card(self._equipment())
		expected = frappe.db.count(
			"Card Monthly Card", {"company": self.company, "docstatus": ["<", 2], "year": 2026, "month": "09"}
		)
		sup = self._user("csup", ["Card Supervisor"])
		# a Card Supervisor cannot read Card Monthly Card at all: an empty list, never an error
		self.assertEqual(self._as(sup, mm.list_monthly_cards, 2026, 9), [])
		manager = self._user("cmgr", ["Card Manager"])
		rows = self._as(manager, mm.list_monthly_cards, 2026, 9)
		self.assertEqual(len(rows), expected)
		row = next(r for r in rows if r.name == card.name)
		self.assertIn("net_amount", row)

	def test_period_is_validated(self):
		manager = self._user("period", ["Card Manager"])
		for year, month in ((2026, 13), (2026, -1), (1999, 5)):
			with self.subTest(year=year, month=month), self.assertRaises(frappe.PermissionError):
				self._as(manager, mm.list_monthly_cards, year, month)

	# ---------- projects ----------
	def test_projects_money_only_for_a_manager(self):
		card = self._card(self._equipment())
		card.submit()
		manager = self._user("pmgr", ["Card Manager"])
		rows = self._as(manager, mm.list_projects, 2026, 9)
		row = next(r for r in rows if r["project"] == self._m["project"])
		self.assertIn("revenue", row)
		self.assertEqual(row["result"], row["revenue"] - row["cost"])
		self.assertEqual(row["cost"], frappe.db.get_value("Card Monthly Card", card.name, "net_amount"))
		sup = self._user("psup", ["Card Supervisor"])
		for r in self._as(sup, mm.list_projects, 2026, 9):
			self.assertFalse({"revenue", "cost", "result"} & set(r))
		self.assertTrue(self._as(manager, mm.get_management_context)["money"])
		self.assertFalse(self._as(sup, mm.get_management_context)["money"])
