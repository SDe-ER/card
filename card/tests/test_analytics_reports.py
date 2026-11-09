# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Analytics reports (#53, #127 P8; WP-16, WP-17): Equipment Partial Margin, Unbilled Card
Work and Equipment Maintenance Cost. All three are read-only: the math, the "not invoiced
yet" column kept out of revenue, project-tank diesel kept on a project line (never split by
equipment), company isolation, role access and the missing-dimension path. Everything is
rolled back."""

from unittest.mock import patch

import frappe
from frappe.utils import flt

from card import analytics
from card.card.report.equipment_maintenance_cost.equipment_maintenance_cost import (
	execute as maintenance_cost,
)
from card.card.report.equipment_partial_margin.equipment_partial_margin import execute as partial_margin
from card.card.report.unbilled_card_work.unbilled_card_work import execute as unbilled_work
from card.gl.journal_link import link_accrual_journal
from card.gl.posting import build_monthly_posting
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_p0_posting_integrity import _P0Base

PERIOD = {"from_date": "2026-09-01", "to_date": "2026-12-31"}


class _AnalyticsBase(_P0Base):
	def _period(self, **kw):
		return {"company": self.company, **PERIOD, **kw}

	def _margin(self, **kw):
		columns, data, message, _chart, summary = partial_margin(self._period(project=self.project, **kw))
		rows = {(r["equipment"], r["project"]): r for r in data}
		return rows, message, {s["label"]: s["value"] for s in summary}, columns

	def _unbilled(self, **kw):
		_columns, data, _message, _chart, summary = unbilled_work(self._period(project=self.project, **kw))
		return {(r["card"], r["party_type"]): r for r in data}, {s["label"]: s["value"] for s in summary}

	def _direct_fill(self, equipment, litres=50, price=2, day="2026-09-12"):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": day,
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"card_equipment": equipment,
				"litres": litres,
				"unit_price": price,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		return fill

	def _maintenance_pi(self, equipment, rate, posting_date="2026-10-05"):
		inv = self._manual_pi(rate, posting_date=posting_date, account=self.exp_transport, submit=False)
		inv.items[0].card_equipment = equipment
		inv.items[0].project = self.project
		inv.save()
		inv.submit()
		return inv

	def _user(self, roles, restrict_to=None):
		email = f"analytics-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Analytics",
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
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

	def _other_company(self):
		name = "TEST-ANLY-CO-" + self.token
		co = frappe.new_doc("Company")
		co.update(
			{
				"company_name": name,
				"abbr": "Y" + self.token[:6].upper(),
				"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"country": frappe.db.get_value("Company", self.company, "country"),
			}
		)
		co.name = name
		co.db_insert()
		return name

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()


class TestEquipmentPartialMargin(_AnalyticsBase):
	def test_margin_math_and_unbilled_kept_out_of_revenue(self):
		eq = self._sub_rental()  # supplier 75/h, customer 120/h
		card = self._card(eq, [8, 8], submit=True)  # supplier 1,200 / customer 1,920
		tank = self._fill(litres=100, price=2)  # project tank: 200, no equipment
		# before any invoice: nothing recognised, both sides are "not invoiced yet"
		rows, message, summary, _cols = self._margin()
		row = rows[(eq.name, self.project)]
		self.assertEqual(row["revenue"], 0)
		self.assertEqual(row["unbilled_revenue"], flt(card.customer_net_amount, 2))
		self.assertEqual(row["rental"], 0)
		self.assertEqual(row["unbilled_rental"], flt(card.net_amount, 2))
		self.assertIn("excludes depreciation, labour, insurance and overhead", message)

		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		si = build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		frappe.get_doc("Purchase Invoice", pi).submit()
		frappe.get_doc("Sales Invoice", si).submit()
		direct = self._direct_fill(eq.name, litres=50, price=2)  # 100, not posted: fill amount
		self._maintenance_pi(eq.name, 333.33)

		rows, _message, summary, _cols = self._margin()
		row = rows[(eq.name, self.project)]
		self.assertEqual(row["revenue"], 1920.0)
		self.assertEqual(row["unbilled_revenue"], 0)
		self.assertEqual(row["rental"], 1200.0)
		self.assertEqual(row["unbilled_rental"], 0)
		self.assertEqual(row["diesel"], flt(direct.amount, 2))
		self.assertEqual(row["maintenance"], 333.33)
		# the posted tank fill is split by hours on the invoice lines, but never here
		self.assertEqual(row["tank_diesel"], 0)
		project_row = rows[(None, self.project)]
		self.assertEqual(project_row["tank_diesel"], flt(tank.amount, 2))
		self.assertEqual(project_row["diesel"], 0)
		expected_cost = flt(1200.0 + flt(direct.amount) + 333.33, 2)
		self.assertEqual(row["total_cost"], expected_cost)
		self.assertEqual(row["margin"], flt(1920.0 - expected_cost, 2))
		self.assertEqual(project_row["margin"], -flt(tank.amount, 2))
		self.assertEqual(summary["Partial margin"], flt(row["margin"] + project_row["margin"], 2))
		self.assertEqual(summary["Unallocated tank diesel"], flt(tank.amount, 2))

	def test_customer_card_not_invoiced_is_never_revenue(self):
		eq = self._rented_out(customer_rate=1000)
		card = self._card(eq, [8, 8], submit=True)
		build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)  # draft only
		rows, _m, summary, _c = self._margin()
		row = rows[(eq.name, self.project)]
		self.assertEqual(row["revenue"], 0)
		self.assertEqual(row["unbilled_revenue"], flt(card.customer_net_amount, 2))
		self.assertEqual(row["margin"], 0)
		self.assertEqual(summary["Customer cards not invoiced yet"], flt(card.customer_net_amount, 2))

	def test_transport_shares_and_unshared_moves(self):
		project = self.project
		transports = [
			frappe._dict(
				name="T1",
				amount=300,
				responsibility="x",
				payer="Company",
				cost_bearer="Company",
				cost_basis="Project",
				cost_project=project,
			),
			frappe._dict(
				name="T2",
				amount=80,
				responsibility="x",
				payer="Company",
				cost_bearer="Company",
				cost_basis="Project",
				cost_project=project,
			),
			# the supplier bears it: never company cost
			frappe._dict(
				name="T3",
				amount=999,
				responsibility="x",
				payer="Company",
				cost_bearer="Equipment Supplier",
				cost_basis="Project",
				cost_project=project,
			),
		]
		items = [
			frappe._dict(parent="T1", card_equipment="EQ-A", amount=200),
			frappe._dict(parent="T1", card_equipment="EQ-B", amount=100),
		]
		with (
			patch.object(analytics.frappe, "get_list", return_value=transports),
			patch.object(analytics, "_children", return_value=items),
		):
			result = analytics.transport_costs(self.company, "2026-09-01", "2026-09-30")
		self.assertEqual(
			sorted(result, key=str),
			sorted([("EQ-A", project, 200.0), ("EQ-B", project, 100.0), (None, project, 80.0)], key=str),
		)

	def test_missing_dimension_is_explained_not_failed(self):
		eq = self._rented_out(customer_rate=1000)
		card = self._card(eq, [8], submit=True)
		with patch.object(analytics, "dimension_ready", return_value=False):
			rows, message, _s, _c = self._margin()
			_cols, data, mmessage, _chart, _summary = maintenance_cost(self._period())
		self.assertIn("Card Equipment accounting dimension is not set up", message)
		self.assertEqual(rows[(eq.name, self.project)]["unbilled_revenue"], flt(card.customer_net_amount, 2))
		self.assertEqual(rows[(eq.name, self.project)]["revenue"], 0)
		self.assertEqual(data, [])
		self.assertIn("Card Equipment accounting dimension is not set up", mmessage)

	def test_company_isolation(self):
		eq = self._rented_out(customer_rate=1000)
		card = self._card(eq, [8], submit=True)
		other = self._other_company()
		frappe.db.set_value("Card Monthly Card", card.name, "company", other, update_modified=False)
		rows, _m, _s, _c = self._margin()
		self.assertNotIn((eq.name, self.project), rows)
		# a user restricted to this company may not ask for the other one
		frappe.set_user(self._user(["Accounts Manager"], restrict_to=self.company))
		with self.assertRaises(frappe.PermissionError):
			partial_margin({"company": other, **PERIOD})
		with self.assertRaises(frappe.PermissionError):
			maintenance_cost({"company": other, **PERIOD})
		with self.assertRaises(frappe.PermissionError):
			unbilled_work({"company": other, **PERIOD})

	def test_ledger_readers_only(self):
		for roles in (["Card User"], ["Card Manager"]):
			frappe.set_user(self._user(roles))
			with self.assertRaises(frappe.PermissionError, msg=roles):
				partial_margin(self._period())
			with self.assertRaises(frappe.PermissionError, msg=roles):
				maintenance_cost(self._period())
			frappe.set_user("Administrator")
		frappe.set_user(self._user(["Accounts Manager"]))
		partial_margin(self._period())
		maintenance_cost(self._period())

	def test_nothing_is_written(self):
		eq = self._sub_rental()
		self._card(eq, [8], submit=True)
		self._fill(litres=10, price=2)
		with (
			patch.object(frappe.db, "set_value", side_effect=AssertionError("write")),
			patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql,
		):
			self._margin()
			self._unbilled()
			maintenance_cost(self._period())
		for call in sql.call_args_list:
			statement = str(call.args[0]).lstrip().lower() if call.args else ""
			self.assertFalse(statement.startswith(("insert", "update", "delete")), statement)


class TestUnbilledCardWork(_AnalyticsBase):
	def test_lists_each_side_until_recognised(self):
		eq = self._sub_rental()
		card = self._card(eq, [8, 8], submit=True)
		rows, summary = self._unbilled()
		self.assertEqual(rows[(card.name, "Supplier")]["amount"], flt(card.net_amount, 2))
		self.assertEqual(rows[(card.name, "Customer")]["amount"], flt(card.customer_net_amount, 2))
		self.assertEqual(summary["Supplier cards not invoiced"], flt(card.net_amount, 2))

		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		rows, _s = self._unbilled()
		self.assertNotIn((card.name, "Supplier"), rows)  # a live (draft) posting holds it
		self.assertIn((card.name, "Customer"), rows)  # the other side stays open
		rows, _s = self._unbilled(include_drafts=1)
		self.assertEqual(rows[(card.name, "Supplier")]["document"], pi)
		self.assertEqual(rows[(card.name, "Supplier")]["status"], "Held by a draft posting")

		frappe.get_doc("Purchase Invoice", pi).submit()
		rows, _s = self._unbilled(include_drafts=1)
		self.assertNotIn((card.name, "Supplier"), rows)
		rows, _s = self._unbilled(side="Supplier")
		self.assertFalse(rows)

	def test_linked_accrual_journal_entry_counts_as_recognised(self):
		card = self._rental_card()
		self.assertIn((card.name, "Supplier"), self._unbilled()[0])
		row = next(r for r in frappe.get_doc("Card Settings").company_settings if r.company == self.company)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": self.company,
				"posting_date": "2026-09-30",
				"voucher_type": "Journal Entry",
				"accounts": [
					{
						"account": self.exp_rental,
						"cost_center": row.cost_center,
						"debit_in_account_currency": flt(card.net_amount, 2),
					},
					{
						"account": row.payable_account,
						"party_type": "Supplier",
						"party": self.supplier,
						"cost_center": row.cost_center,
						"credit_in_account_currency": flt(card.net_amount, 2),
					},
				],
			}
		).insert(ignore_permissions=True)
		je.submit()
		link_accrual_journal(je.name, [card.name])
		self.assertNotIn((card.name, "Supplier"), self._unbilled()[0])
		rows, _m, _s, _c = self._margin()
		self.assertEqual(rows[(card.equipment, self.project)]["rental"], flt(card.net_amount, 2))

	def test_role_access(self):
		self._rental_card()
		frappe.set_user(self._user(["Card User"]))
		with self.assertRaises(frappe.PermissionError):
			self._unbilled()
		frappe.set_user("Administrator")
		frappe.set_user(self._user(["Card Manager"]))
		rows, _s = self._unbilled()
		self.assertTrue(rows)


class TestEquipmentMaintenanceCost(_AnalyticsBase):
	def test_tagged_lines_only_and_card_invoices_excluded(self):
		eq = self._rental_card().equipment
		pi = build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		frappe.get_doc("Purchase Invoice", pi).submit()  # CARD rental invoice: never maintenance
		repair = self._maintenance_pi(eq, 250)
		untagged = self._manual_pi(70, posting_date="2026-10-06", account=self.exp_transport)
		_cols, data, _message, _chart, summary = maintenance_cost(self._period(equipment=eq))
		vouchers = {r["voucher_no"]: r for r in data}
		self.assertEqual(set(vouchers), {repair.name})
		self.assertNotIn(untagged.name, vouchers)
		self.assertEqual(vouchers[repair.name]["amount"], 250.0)
		self.assertEqual(vouchers[repair.name]["equipment"], eq)
		self.assertEqual(summary[0]["value"], 250.0)

	def test_other_company_lines_are_not_read(self):
		eq = self._rental_card().equipment
		repair = self._maintenance_pi(eq, 120)
		other = self._other_company()
		frappe.db.set_value("Purchase Invoice", repair.name, "company", other, update_modified=False)
		_cols, data, _m, _c, _s = maintenance_cost(self._period())
		self.assertNotIn(repair.name, {r["voucher_no"] for r in data})

	def test_unreadable_sources_are_named_not_hidden(self):
		real = analytics.can_read
		with patch.object(analytics, "can_read", side_effect=lambda dt: dt != "Stock Entry" and real(dt)):
			_cols, _data, message, _c, _s = maintenance_cost(self._period())
		self.assertIn("you cannot read them: Stock Entry", message)

	def test_stock_item_purchase_is_not_counted_twice(self):
		eq = self._rental_card().equipment
		service = self._maintenance_pi(eq, 40)
		item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "TEST-ANLY-SPARE-" + self.token,
				"item_name": "Spare part",
				"item_group": frappe.db.get_value("Item", service.items[0].item_code, "item_group"),
				"stock_uom": frappe.db.get_value("Item", service.items[0].item_code, "stock_uom"),
				"is_stock_item": 1,
			}
		).insert(ignore_permissions=True)
		inv = self._manual_pi(90, posting_date="2026-10-07", item=item.name, submit=False)
		inv.items[0].card_equipment = eq
		inv.save()
		inv.submit()
		_cols, data, _m, _c, _s = maintenance_cost(self._period(equipment=eq))
		vouchers = {r["voucher_no"] for r in data}
		self.assertIn(service.name, vouchers)
		self.assertNotIn(inv.name, vouchers)


class TestDieselValuation(_AnalyticsBase):
	def _direct_diesel(self):
		eq = self._rental_card().equipment
		fill = self._direct_fill(eq, litres=50, price=2.3)  # 115.00 as recorded
		rows, message, _s, _c = self._margin(equipment=eq)
		return fill, rows[(eq, self.project)]["diesel"], message

	def test_unposted_fill_is_net_under_an_inclusive_basis(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		fill, diesel, _message = self._direct_diesel()
		self.assertEqual(flt(fill.amount, 2), 115.0)
		self.assertEqual(diesel, 100.0)  # 115 incl. 15% VAT, by the posting's own rule

	def test_exclusive_basis_keeps_the_fill_amount(self):
		self._vat_supplier()
		self._set_basis("Exclusive")
		fill, diesel, _message = self._direct_diesel()
		self.assertEqual(diesel, flt(fill.amount, 2))

	def test_unregistered_supplier_keeps_the_fill_amount_under_an_inclusive_basis(self):
		self._set_basis("Inclusive")
		fill, diesel, _message = self._direct_diesel()
		self.assertEqual(diesel, flt(fill.amount, 2))

	def test_vat_supplier_without_purchase_tax_template_is_reported(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		settings, row = self._row()
		row.purchase_tax_template = ""
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")
		fill, diesel, message = self._direct_diesel()
		self.assertEqual(diesel, flt(fill.amount, 2))  # the posting refuses this case: never guessed
		self.assertIn("VAT basis is not verified", message)
		self.assertIn(self.supplier, message)

	def test_posted_fill_uses_the_net_stored_in_the_posting(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		eq = self._rental_card().equipment
		fill = self._direct_fill(eq, litres=50, price=2.3)  # 115.00 incl. VAT
		pi = self._build()
		pi.bill_no = "TEST-ANLY-VAT-" + self.token
		pi.bill_date = pi.posting_date
		pi.save()
		pi.submit()
		stored = frappe.get_all(
			"GL Posting Source",
			filters={
				"parenttype": "GL Posting Log",
				"source_doctype": "Project Diesel Fill",
				"source_name": fill.name,
			},
			pluck="amount",
		)
		self.assertEqual([flt(a, 2) for a in stored], [100.0])
		rows, _message, _s, _c = self._margin(equipment=eq)
		self.assertEqual(rows[(eq, self.project)]["diesel"], 100.0)

	def test_unverified_basis_is_reported_not_guessed(self):
		self._vat_supplier()
		self._set_basis("")
		frappe.local.message_log = []
		fill, diesel, message = self._direct_diesel()
		self.assertEqual(diesel, flt(fill.amount, 2))
		self.assertIn("VAT basis is not verified", message)
		self.assertIn(self.supplier, message)
		self.assertFalse(
			[m for m in frappe.local.message_log if "VAT basis" in str(m)],
			"the posting's refusal must not reach the user as a pop-up",
		)
