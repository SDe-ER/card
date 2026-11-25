# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Partner split in the Equipment Suppliers Summary (FR-190, issue 300).

Card Company Settings ``partner_equipment_split`` (default off) adds, per supplier, the count of
partner machines and the net of their cards. A partner machine is a machine whose submitted card
stores ``ownership`` = طرف ثالث (fetched from Card Equipment.ownership). Proven here, with fixtures
that the test transaction rolls back (no real company data):

- off (no value, or 0) = the report of today: same columns, row keys and summary tiles;
- on = the two figures per supplier and on the total row, and one summary tile;
- on without the Monthly Card money level = no partner net in columns, rows or summary;
- the setting of another company does not apply."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.report.equipment_suppliers_summary.equipment_suppliers_summary import execute
from card.constants import THIRD_PARTY
from card.tests import test_settings_wiring as wiring
from card.tests.test_controllers import _ensure_masters

SETTING = "partner_equipment_split"
MONEY_GATE = "card.card.report.equipment_suppliers_summary.equipment_suppliers_summary.role_reads_money"
TODAY_COLUMNS = [
	"supplier_name",
	"supplier",
	"equipment_count",
	"card_count",
	"working_days",
	"hours",
	"net",
	"accrued",
	"invoiced_net",
	"diff",
	"external_net",
	"opening",
	"paid",
	"closing",
]
TODAY_TILES = [
	"Number of suppliers",
	"Net cards",
	"Not invoiced through Card",
	"ERPNext invoices outside Card — to reconcile (net before VAT)",
	"Total supplier balances",
]
PARTNER_KEYS = ("partner_equipment_count", "partner_net")
PARTNER_TILE = "Net cards (partner-owned)"


def _set_split(company, value):
	"""Write only the company's row of Card Settings > Company settings (rolled back with the test)."""
	name = frappe.db.get_value(
		"Card Company Settings",
		{"parent": "Card Settings", "parenttype": "Card Settings", "company": company},
		"name",
	)
	if name:
		frappe.db.set_value("Card Company Settings", name, SETTING, value)
		return
	frappe.get_doc(
		{
			"doctype": "Card Company Settings",
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": "company_settings",
			"company": company,
			SETTING: value,
		}
	).db_insert()


class TestPartnerEquipmentSplit(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls._m = _ensure_masters()

	# the fixtures of the report wiring tests: own project and supplier, equipment and card builders
	setUp = wiring.TestCardSettingsWiring.setUp
	_equipment = wiring.TestCardSettingsWiring._equipment
	_card = wiring.TestCardSettingsWiring._card

	def tearDown(self):
		frappe.db.rollback()

	def _cards(self):
		"""One supplier with a rented machine and a partner machine, each with a submitted card."""
		rented = self._card(self._equipment("-R"), [10, 10], submit=True)
		partner = self._card(self._equipment("-P", ownership=THIRD_PARTY), [10, 10, 10], submit=True)
		self.assertEqual(partner.ownership, THIRD_PARTY)
		self.assertTrue(flt(rented.net_amount) and flt(partner.net_amount))
		return rented, partner

	def _run(self):
		filters = {"company": self.company, "from_month": 9, "from_year": 2026, "project": self.project}
		columns, rows, _message, _chart, summary, _flag = execute(filters)
		return frappe._dict(
			columns=[c["fieldname"] for c in columns],
			rows=rows,
			row=next(r for r in rows if r.get("supplier") == self.supplier),
			total=next(r for r in rows if r.get("is_total")),
			tiles=[t["label"] for t in summary],
			summary=summary,
		)

	def _other_company(self):
		"""Second company (the pattern of test_approval_tier._company_b)."""
		name = "TEST-PSPLIT-CO-" + self.token
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

	def _assert_report_of_today(self, r):
		self.assertEqual(r.columns, TODAY_COLUMNS)
		self.assertEqual(r.tiles, [frappe._(label) for label in TODAY_TILES])
		for key in PARTNER_KEYS:
			self.assertFalse([x for x in r.rows if key in x], key)

	# ---------- the setting ----------

	def test_setting_is_a_check_off_by_default_at_the_money_level(self):
		df = frappe.get_meta("Card Company Settings").get_field(SETTING)
		self.assertIsNotNone(df)
		self.assertEqual(df.fieldtype, "Check")
		self.assertEqual(str(df.default), "0")
		self.assertEqual(df.permlevel, 1)
		self.assertFalse(df.description)

	# ---------- off = the report of today ----------

	def test_off_is_the_report_of_today(self):
		self._cards()
		untouched = self._run()
		self._assert_report_of_today(untouched)
		_set_split(self.company, 0)
		off = self._run()
		self._assert_report_of_today(off)
		self.assertEqual(off.rows, untouched.rows)
		self.assertEqual(off.summary, untouched.summary)

	# ---------- on = the partner figures ----------

	def test_on_adds_the_partner_count_and_net(self):
		rented, partner = self._cards()
		before = self._run()
		_set_split(self.company, 1)
		r = self._run()

		expected = list(TODAY_COLUMNS)
		expected.insert(expected.index("equipment_count") + 1, "partner_equipment_count")
		expected.insert(expected.index("net") + 1, "partner_net")
		self.assertEqual(r.columns, expected)

		self.assertEqual(r.row["equipment_count"], 2)
		self.assertEqual(r.row["partner_equipment_count"], 1)
		self.assertEqual(r.row["partner_net"], flt(partner.net_amount, 2))
		self.assertEqual(r.row["net"], flt(flt(rented.net_amount) + flt(partner.net_amount), 2))
		self.assertEqual(r.total["partner_equipment_count"], 1)
		self.assertEqual(r.total["partner_net"], flt(partner.net_amount, 2))

		tile = next(t for t in r.summary if t["label"] == frappe._(PARTNER_TILE))
		self.assertEqual(tile["value"], flt(partner.net_amount, 2))
		self.assertEqual(tile["datatype"], "Currency")
		self.assertEqual([t for t in r.tiles if t != frappe._(PARTNER_TILE)], before.tiles)

		# every figure of today is unchanged
		for row, old in zip(r.rows, before.rows, strict=True):
			self.assertEqual({k: v for k, v in row.items() if k not in PARTNER_KEYS}, old)

	def test_on_a_supplier_without_partner_machines_shows_zero(self):
		self._card(self._equipment("-R"), [10, 10], submit=True)
		_set_split(self.company, 1)
		r = self._run()
		self.assertEqual(r.row["partner_equipment_count"], 0)
		self.assertEqual(r.row["partner_net"], 0)
		self.assertEqual(r.total["partner_net"], 0)

	# ---------- on, without the Monthly Card money level ----------

	def test_on_without_the_money_level_has_no_partner_net(self):
		self._cards()
		_set_split(self.company, 1)
		with patch(MONEY_GATE, return_value=False):
			r = self._run()
		for key in ("net", "diff", "partner_net"):
			self.assertNotIn(key, r.columns)
			self.assertFalse([x for x in r.rows if key in x], key)
		for label in ("Net cards", "Not invoiced through Card", PARTNER_TILE):
			self.assertNotIn(frappe._(label), r.tiles)
		# the count is no card amount: it stays, like the equipment count
		self.assertIn("partner_equipment_count", r.columns)
		self.assertEqual(r.row["partner_equipment_count"], 1)

	# ---------- company scope of the setting ----------

	def test_the_setting_of_another_company_does_not_apply(self):
		self._cards()
		_set_split(self._other_company(), 1)
		self._assert_report_of_today(self._run())
