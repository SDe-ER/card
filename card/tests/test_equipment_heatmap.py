# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Heatmap timeline tests for Card Equipment (form-dashboard hook).

These tests are written in TDD red state: the function
`get_timeline_data(doctype: str, name: str)` is NOT yet implemented in
`card.card.doctype.card_equipment.card_equipment`. Each test imports it
inside the test body (via importlib) so module collection does not crash
if the symbol is missing. The orchestrator will run them against a Frappe v16
site after implementation.
"""

import importlib

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import get_datetime, getdate, nowdate

from card.tests.test_controllers import _days, _ensure_masters


def _past_month_year():
    """Return (month_str, year_str) for a past month (e.g. two months back)
    so validate rules pass (no future-dated hours, dates inside card month).
    """
    today = getdate(nowdate())
    year = today.year
    month = today.month - 2
    if month < 1:
        month += 12
        year -= 1
    return f"{month:02d}", str(year)


def _mid_date_str(month_str: str, year_str: str, day: int = 15):
    return f"{year_str}-{month_str}-{day:02d}"


def _midnight_unix(date_str: str):
    dt = get_datetime(date_str)
    dt_midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(dt_midnight.timestamp())


class TestEquipmentHeatmap(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._m = _ensure_masters()

    def setUp(self):
        self.token = frappe.generate_hash(length=8)
        self.company = self._m["company"]
        self.etype = self._m["etype"]
        self.project = self._m["project"]
        self.month_str, self.year_str = _past_month_year()
        self.mid_date = _mid_date_str(self.month_str, self.year_str, day=15)

        sg = self._m["supplier_group"]
        sup = frappe.new_doc("Supplier")
        sup.supplier_name = "TEST-SUP-HEAT-" + self.token
        sup.supplier_group = sg
        sup.insert(ignore_permissions=True)
        self.supplier = sup.name

    def tearDown(self):
        try:
            frappe.db.rollback()
        except Exception:
            pass

    def _make_equipment(self, ownership="إيجار", rate=750, daily_hours=10, **kw):
        d = frappe.new_doc("Card Equipment")
        d.company = self.company
        d.equipment_type = self.etype
        d.ownership = ownership
        d.equipment_name = kw.pop("equipment_name", "TEST-EQ-HEAT-" + self.token)
        d.rate_type = "باليوم"
        d.rate = rate
        d.daily_hours = daily_hours
        if ownership != "ملك":
            d.supplier = self.supplier
        for key, value in kw.items():
            setattr(d, key, value)
        d.insert(ignore_permissions=True)
        d.reload()
        return d

    def _make_card(self, eq, hours_list, shift="نهاري", submit=False, month_str=None, year_str=None, days_override=None):
        month_str = month_str or self.month_str
        year_str = year_str or self.year_str
        c = frappe.new_doc("Card Monthly Card")
        c.equipment = eq.name
        c.project = self.project
        c.shift = shift
        c.month = month_str
        c.year = int(year_str) if year_str.isdigit() else year_str
        if days_override is not None:
            for row in days_override:
                c.append("days", row)
        else:
            for row in _days(hours_list, year=int(c.year), month=int(c.month)):
                c.append("days", row)
        c.insert(ignore_permissions=True)
        if submit:
            c.submit()
        c.reload()
        return c

    def _get_timeline_data(self, doctype: str, name: str):
        mod = importlib.import_module("card.card.doctype.card_equipment.card_equipment")
        return mod.get_timeline_data(doctype, name)

    def test_two_shifts_same_date_sum(self):
        eq = self._make_equipment()
        days = [
            {"operation_date": self.mid_date, "day_status": "عمل", "working_hours": 10.0}
        ]
        self._make_card(eq, hours_list=[], shift="نهاري", submit=True, days_override=days)
        self._make_card(eq, hours_list=[], shift="ليلي", submit=True, days_override=days)
        result = self._get_timeline_data("Card Equipment", eq.name)
        key = _midnight_unix(self.mid_date)
        self.assertIn(key, result)
        self.assertAlmostEqual(result[key], 20.0)

    def test_draft_and_cancelled_excluded(self):
        eq = self._make_equipment()
        date1 = self.mid_date
        date2 = _mid_date_str(self.month_str, self.year_str, day=16)
        days1 = [{"operation_date": date1, "day_status": "عمل", "working_hours": 8.0}]
        days2 = [{"operation_date": date2, "day_status": "عمل", "working_hours": 7.0}]
        c_draft = self._make_card(eq, hours_list=[], submit=False, days_override=days1)
        self.assertEqual(c_draft.docstatus, 0)
        # ليلي shift: the duplicate guard blocks a second card with the same
        # equipment+month+year+shift while the draft (نهاري) one exists.
        c_cancel = self._make_card(eq, hours_list=[], shift="ليلي", submit=True, days_override=days2)
        c_cancel.cancel()
        c_cancel.reload()
        self.assertEqual(c_cancel.docstatus, 2)
        result = self._get_timeline_data("Card Equipment", eq.name)
        key1 = _midnight_unix(date1)
        key2 = _midnight_unix(date2)
        self.assertNotIn(key1, result)
        self.assertNotIn(key2, result)

    def test_stoppage_day_absent(self):
        eq = self._make_equipment()
        date_worked = self.mid_date
        date_stop = _mid_date_str(self.month_str, self.year_str, day=17)
        days = [
            {"operation_date": date_stop, "day_status": "توقف من العميل", "working_hours": 0.0},
            {"operation_date": date_worked, "day_status": "عمل", "working_hours": 8.0},
        ]
        self._make_card(eq, hours_list=[], submit=True, days_override=days)
        result = self._get_timeline_data("Card Equipment", eq.name)
        key_stop = _midnight_unix(date_stop)
        key_worked = _midnight_unix(date_worked)
        self.assertNotIn(key_stop, result)
        self.assertIn(key_worked, result)

    def test_empty_equipment_returns_empty_dict(self):
        eq = self._make_equipment()
        result = self._get_timeline_data("Card Equipment", eq.name)
        self.assertIsInstance(result, dict)
        self.assertEqual(result, {})

    def test_permission_denied_other_user(self):
        eq = self._make_equipment()
        test_user = f"test-heat-{self.token}@example.com"
        if not frappe.db.exists("User", test_user):
            user = frappe.new_doc("User")
            user.email = test_user
            user.first_name = "Test"
            user.send_welcome_email = 0
            user.insert(ignore_permissions=True)
        old_user = frappe.session.user
        try:
            frappe.set_user(test_user)
            with self.assertRaises(frappe.PermissionError):
                self._get_timeline_data("Card Equipment", eq.name)
        finally:
            frappe.set_user(old_user)

    def test_key_and_value_types(self):
        eq = self._make_equipment()
        date_w = self.mid_date
        days = [{"operation_date": date_w, "day_status": "عمل", "working_hours": 6.5}]
        self._make_card(eq, hours_list=[], submit=True, days_override=days)
        result = self._get_timeline_data("Card Equipment", eq.name)
        self.assertIsInstance(result, dict)
        key_exp = _midnight_unix(date_w)
        self.assertIn(key_exp, result)
        for k, v in result.items():
            self.assertIsInstance(k, int)
            self.assertIsInstance(v, float)
