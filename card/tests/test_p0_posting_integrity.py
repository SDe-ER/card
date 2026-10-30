# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P0 posting integrity (2026-10-30 integration audit, QA failures T3b, T3c, T9h2, T9h3, T9i):
manual supplier invoices as evidence, the diesel VAT basis, the built-signature
check of edited drafts, and the copy guard."""

import frappe
from frappe.utils import flt

from card.gl.integrity import accept_correction, link_supplier_invoice
from card.gl.posting import build_monthly_posting, rebuild_monthly_posting
from card.tests.diesel_price import approve_fill, use_fill_price
from card.tests.test_s3_posting import _PostingBase


class _P0Base(_PostingBase):
	def _row(self):
		settings = frappe.get_doc("Card Settings")
		return settings, next(r for r in settings.company_settings if r.company == self.company)

	def _set_basis(self, basis):
		settings, row = self._row()
		row.diesel_price_vat_basis = basis
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")

	def _rental_card(self, hours=(8,)):
		return self._card(self._equipment(), list(hours), submit=True)

	def _fill(self, litres=100, price=2, day="2026-09-10"):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": day,
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": litres,
				"unit_price": price,
			}
		)
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		return fill

	def _manual_pi(
		self, rate, posting_date="2026-09-20", item=None, account=None, description=None, submit=True
	):
		from card.gl.masters import ensure_posting_masters

		row = ensure_posting_masters(self.company)
		inv = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": self.supplier,
				"set_posting_time": 1,
				"posting_date": posting_date,
				"due_date": posting_date,
				"bill_no": f"P0-MANUAL-{self.token}-{frappe.generate_hash(length=6)}",
				"bill_date": posting_date,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"items": [
					{
						"item_code": item or row.rental_item,
						"qty": 1,
						"rate": rate,
						"expense_account": account or self.exp_rental,
						**({"description": description} if description else {}),
					}
				],
			}
		).insert(ignore_permissions=True)
		if submit:
			inv.submit()
		return inv

	def _build(self, **kw):
		return frappe.get_doc(
			"Purchase Invoice", build_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026, **kw)
		)

	def _log(self, invoice):
		return frappe.get_doc(
			"GL Posting Log", {"posting_doc": invoice, "status": ["in", ["Draft", "Submitted"]]}
		)


class TestDraftIntegrity(_P0Base):
	"""T9h2/T9h3: every financially significant field of a CARD draft is re-checked at submit."""

	def test_unchanged_draft_submits_and_records_signatures(self):
		self._rental_card()
		pi = self._build()
		log = self._log(pi.name)
		self.assertEqual(log.origin, "Built")
		self.assertTrue(log.built_signature and log.lines_signature and log.built_snapshot)
		pi.reload()
		pi.submit()
		self.assertEqual(pi.docstatus, 1)

	def test_changed_supplier_is_refused(self):
		self._rental_card()
		pi = self._build()
		other = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "TEST-P0-OTHER-" + self.token}
		).insert(ignore_permissions=True)
		pi.supplier = other.name
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "differs from what CARD built"):
			pi.submit()

	def test_changed_expense_account_is_refused_until_accepted(self):
		self._rental_card()
		pi = self._build()
		pi.items[0].expense_account = self.exp_transport
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "accept_correction"):
			pi.submit()
		accept_correction("Purchase Invoice", pi.name, "wrong expense head on the card type")
		pi.reload()
		pi.submit()
		self.assertEqual(pi.docstatus, 1)
		self.assertEqual(self._log(pi.name).accepted_by, "Administrator")

	def test_edit_after_acceptance_needs_a_new_acceptance(self):
		self._rental_card()
		pi = self._build()
		pi.items[0].expense_account = self.exp_transport
		pi.save()
		accept_correction("Purchase Invoice", pi.name, "correct the head")
		pi.reload()
		pi.items[0].expense_account = self.exp_diesel
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "differs from what CARD built"):
			pi.submit()

	def test_acceptance_refuses_non_correctable_changes(self):
		self._rental_card()
		pi = self._build()
		pi.items[0].card_equipment = None
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "Only cost center and account changes"):
			accept_correction("Purchase Invoice", pi.name, "try")

	def test_acceptance_refuses_an_account_of_another_root_type(self):
		self._rental_card()
		pi = self._build()
		pi.items[0].expense_account = self.vat_in  # an Asset account
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "enabled leaf"):
			accept_correction("Purchase Invoice", pi.name, "try")

	def test_removed_tax_rows_are_refused(self):
		self._vat_supplier()
		self._rental_card()
		pi = self._build()
		pi.taxes_and_charges = ""
		pi.set("taxes", [])
		pi.bill_no = "P0-VAT-" + self.token
		pi.bill_date = pi.posting_date
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "differs from what CARD built"):
			pi.submit()

	def test_draft_without_signature_must_be_rebuilt(self):
		self._rental_card()
		pi = self._build()
		self._log(pi.name).db_set("built_signature", None)
		with self.assertRaisesRegex(frappe.ValidationError, "rebuild the posting"):
			pi.reload()
			pi.submit()


class TestCopyGuard(_P0Base):
	"""T9i: a copied CARD posting or an invoice naming a held source cannot be submitted."""

	def test_desk_duplicate_of_a_submitted_posting_is_refused(self):
		self._rental_card()
		pi = self._build()
		pi.submit()
		dup = frappe.copy_doc(pi)
		dup.docstatus = 0  # Desk "Duplicate" gives a new draft
		dup.bill_no = "P0-DUP-" + self.token
		dup.insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "repeats the lines of CARD posting"):
			dup.submit()

	def test_manual_invoice_naming_a_held_source_is_refused(self):
		card = self._rental_card()
		self._build()
		inv = self._manual_pi(500, submit=False, description=f"rent as per {card.name}")
		with self.assertRaisesRegex(frappe.ValidationError, "already booked by"):
			inv.submit()

	def test_unrelated_manual_invoice_still_submits(self):
		self._rental_card()
		self._build()
		inv = self._manual_pi(500, posting_date="2026-11-03", submit=False)
		inv.submit()
		self.assertEqual(inv.docstatus, 1)


class TestManualInvoiceEvidence(_P0Base):
	"""T3b: hand-booked supplier invoices of the month are reviewed or linked, never booked twice."""

	def test_build_refused_while_a_manual_invoice_is_unreviewed(self):
		self._rental_card()
		manual = self._manual_pi(600)
		with self.assertRaisesRegex(frappe.ValidationError, manual.name):
			self._build()
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))

	def test_draft_manual_invoice_is_evidence_too(self):
		self._rental_card()
		manual = self._manual_pi(600, submit=False)
		with self.assertRaisesRegex(frappe.ValidationError, manual.name):
			self._build()

	def test_reviewed_unrelated_invoice_allows_a_second_legitimate_invoice(self):
		self._rental_card()
		manual = self._manual_pi(600)
		pi = self._build(reviewed_invoices=[manual.name])
		log = self._log(pi.name)
		self.assertIn(manual.name, log.reviewed_invoices)
		self.assertIn("Reviewed as unrelated", log.remarks)

	def test_unknown_reviewed_invoice_is_refused(self):
		self._rental_card()
		with self.assertRaisesRegex(frappe.ValidationError, "Not a candidate invoice"):
			self._build(reviewed_invoices=["ACC-PINV-NOT-THERE"])

	def test_invoice_far_outside_the_window_or_on_a_non_expense_account_is_not_evidence(self):
		self._rental_card()
		self._manual_pi(600, posting_date="2026-12-20")  # beyond month end + 62 days
		other_item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": "P0-OTHER-" + self.token,
				"item_group": "All Item Groups",
				"stock_uom": "Nos",
				"is_stock_item": 0,
			}
		).insert(ignore_permissions=True)
		# a non-CARD item on an Asset account: not an expense
		self._manual_pi(80, item=other_item.name, account=self.vat_in)
		self.assertEqual(self._build().docstatus, 0)

	def test_linked_manual_invoice_holds_the_sources_and_nothing_is_reposted(self):
		card = self._rental_card()
		fill = self._fill()
		manual = self._manual_pi(800)
		gl_before = frappe.db.count("GL Entry", {"voucher_no": manual.name})
		log_name = link_supplier_invoice(
			manual.name,
			[
				{"doctype": "Card Monthly Card", "name": card.name},
				{"doctype": "Project Diesel Fill", "name": fill.name},
			],
			"supplier invoice covers the month",
		)
		log = frappe.get_doc("GL Posting Log", log_name)
		self.assertEqual((log.origin, log.status), ("Linked", "Submitted"))
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"), manual.name)
		self.assertEqual(
			frappe.db.get_value("Project Diesel Fill", fill.name, "purchase_invoice"), manual.name
		)
		self.assertEqual(frappe.db.count("GL Entry", {"voucher_no": manual.name}), gl_before)
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			self._build()
		# a second link of the same source is refused
		other = self._manual_pi(50)
		with self.assertRaisesRegex(frappe.ValidationError, "already invoiced"):
			link_supplier_invoice(other.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		# cancelling the hand-booked invoice frees the sources; its amendment is normal ERPNext
		manual.reload()
		manual.cancel()
		self.assertFalse(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"))
		amended = frappe.copy_doc(manual)
		amended.amended_from = manual.name
		amended.docstatus = 0
		amended.insert(ignore_permissions=True)
		self.assertTrue(amended.name)

	def test_link_to_a_draft_invoice_then_submit(self):
		card = self._rental_card()
		manual = self._manual_pi(600, submit=False)
		link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		self.assertEqual(self._log(manual.name).status, "Draft")
		manual.reload()
		manual.submit()
		self.assertEqual(self._log(manual.name).status, "Submitted")
		self.assertEqual(frappe.db.get_value("Card Monthly Card", card.name, "purchase_invoice"), manual.name)

	def test_link_refuses_another_supplier_and_a_built_posting(self):
		card = self._rental_card()
		pi = self._build()
		with self.assertRaisesRegex(frappe.ValidationError, "already a CARD posting"):
			link_supplier_invoice(pi.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		frappe.delete_doc("Purchase Invoice", pi.name, ignore_permissions=True)
		other = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "TEST-P0-OTHER2-" + self.token}
		).insert(ignore_permissions=True)
		manual = self._manual_pi(800)
		manual_other = frappe.copy_doc(manual)
		manual_other.supplier = other.name
		manual_other.bill_no = "P0-OTH-" + self.token
		manual_other.insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "another company or supplier"):
			link_supplier_invoice(manual_other.name, [{"doctype": "Card Monthly Card", "name": card.name}])

	def test_rebuild_never_deletes_a_linked_draft_invoice(self):
		card = self._rental_card()
		manual = self._manual_pi(600, submit=False)
		link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		self._rental_card(hours=(4,))
		pi = frappe.get_doc(
			"Purchase Invoice",
			rebuild_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026),
		)
		self.assertTrue(frappe.db.exists("Purchase Invoice", manual.name))
		self.assertNotIn(card.name, " ".join(i.description for i in pi.items))

	def test_bill_no_already_booked_is_refused_on_the_card_posting(self):
		self._vat_supplier()
		self._rental_card()
		manual = self._manual_pi(600, posting_date="2026-11-02")
		pi = self._build(reviewed_invoices=[manual.name])
		pi.bill_no = manual.bill_no
		pi.bill_date = pi.posting_date
		pi.save()
		with self.assertRaisesRegex(frappe.ValidationError, "already booked on"):
			pi.submit()


class TestDieselVatBasis(_P0Base):
	"""T3c: the diesel price is VAT-inclusive or exclusive by setting; unknown = review."""

	def test_unverified_basis_refuses_a_vat_supplier(self):
		self._vat_supplier()
		self._set_basis("")
		self._fill()
		with self.assertRaisesRegex(frappe.ValidationError, "need review"):
			self._build()
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"party": self.supplier}))
		# retry after the setting is verified: one clean build
		self._set_basis("Exclusive")
		self.assertEqual(flt(self._build().grand_total, 2), 230.0)

	def test_exclusive_adds_vat(self):
		self._vat_supplier()
		self._set_basis("Exclusive")
		self._fill()
		pi = self._build()
		self.assertEqual((flt(pi.net_total, 2), flt(pi.grand_total, 2)), (200.0, 230.0))

	def test_inclusive_keeps_the_fill_amount_and_adds_no_second_vat(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		fill = self._fill(litres=1300, price=1.79)  # 2,327.00 incl. VAT
		pi = self._build()
		self.assertEqual(flt(pi.net_total, 2), 2023.48)
		self.assertEqual(flt(pi.grand_total, 2), 2327.0)
		log = self._log(pi.name)
		self.assertIn("includes VAT", log.remarks)
		self.assertEqual(flt(log.sources[0].amount, 2), 2023.48)
		pi.bill_no = "P0-INCL-" + self.token
		pi.bill_date = pi.posting_date
		pi.save()
		pi.submit()
		self.assertEqual(frappe.db.get_value("Project Diesel Fill", fill.name, "purchase_invoice"), pi.name)

	def test_non_vat_supplier_books_the_full_amount_either_way(self):
		self._set_basis("Inclusive")
		self._fill()
		pi = self._build()
		self.assertEqual((flt(pi.net_total, 2), flt(pi.grand_total, 2)), (200.0, 200.0))


class TestSalesInvoiceSignature(_P0Base):
	"""The built-signature check covers CARD Sales Invoices too: a save leaves it intact, an edit is refused."""

	def _si(self):
		eq = self._rented_out(customer_rate=1000)
		self._card(eq, [8, 8], submit=True)
		return frappe.get_doc(
			"Sales Invoice", build_monthly_posting(self.company, "Customer", self.customer, 9, 2026)
		)

	def test_saved_unchanged_si_submits(self):
		si = self._si()
		si.remarks = "P0 save before submit"
		si.save()
		si.submit()
		self.assertEqual(si.docstatus, 1)

	def test_changed_income_account_is_refused(self):
		si = self._si()
		si.items[0].income_account = self.acc_mob
		si.save()
		with self.assertRaisesRegex(frappe.ValidationError, "differs from what CARD built"):
			si.submit()


class TestLinkEvidence(_P0Base):
	"""A link never shows unmatched amounts as matched, and imported sessions keep their invoice identity."""

	def test_amount_difference_needs_an_accepted_reason(self):
		card = self._rental_card()  # 600
		manual = self._manual_pi(650)
		with self.assertRaisesRegex(frappe.ValidationError, "accept the difference"):
			link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		with self.assertRaisesRegex(frappe.ValidationError, "accept the difference"):
			link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}], "", 1)
		log = frappe.get_doc(
			"GL Posting Log",
			link_supplier_invoice(
				manual.name,
				[{"doctype": "Card Monthly Card", "name": card.name}],
				"mobilization on the invoice",
				1,
			),
		)
		self.assertEqual(flt(log.link_difference, 2), 50.0)
		self.assertIn("open difference", log.remarks)

	def test_matched_against_the_vat_inclusive_total(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		fill = self._fill(litres=300, price=2.3)  # 690.00 incl. VAT
		manual = self._manual_pi(600, item=None, account=self.exp_diesel, submit=False)
		manual.taxes_and_charges = frappe.db.get_value(
			"Purchase Taxes and Charges Template",
			{"title": "Test CARD Purchase VAT", "company": self.company},
			"name",
		)
		manual.set("taxes", [])
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		for row in get_taxes_and_charges("Purchase Taxes and Charges Template", manual.taxes_and_charges):
			manual.append("taxes", row)
		manual.save()
		self.assertEqual(flt(manual.grand_total, 2), 690.0)
		log = frappe.get_doc(
			"GL Posting Log",
			link_supplier_invoice(manual.name, [{"doctype": "Project Diesel Fill", "name": fill.name}]),
		)
		self.assertEqual(flt(log.link_difference, 2), 0.0)
		self.assertIn("matched", log.remarks)

	def test_imported_session_must_name_this_invoice_and_stays_held(self):
		fill = frappe.get_doc(
			{
				"doctype": "Project Diesel Fill",
				"date": "2026-09-10",
				"project": self.project,
				"supplier": self.supplier,
				"company": self.company,
				"litres": 100,
				"unit_price": 2,
			}
		)
		fill.flags.diesel_import = True
		fill.source_key = "WA-TEST-P0-" + frappe.generate_hash(length=8)
		fill.source_messages = "WA-TEST-P0"
		fill.supplier_invoice_no = "INV-777"
		use_fill_price(fill).insert(ignore_permissions=True)
		approve_fill(fill)
		fill.submit()
		wrong = self._manual_pi(200)
		with self.assertRaisesRegex(frappe.ValidationError, "INV-777"):
			link_supplier_invoice(wrong.name, [{"doctype": "Project Diesel Fill", "name": fill.name}])
		right = self._manual_pi(200, submit=False)
		right.bill_no = "INV-777"
		right.save()
		right.submit()
		link_supplier_invoice(right.name, [{"doctype": "Project Diesel Fill", "name": fill.name}])
		self.assertEqual(
			frappe.db.get_value("Project Diesel Fill", fill.name, "purchase_invoice"), right.name
		)
		# a linked session cannot be cancelled (so not amended or re-imported into a second expense)
		fill.reload()
		with self.assertRaisesRegex(frappe.ValidationError, "cancel that invoice first"):
			fill.cancel()
		# and CARD posting never takes it
		with self.assertRaisesRegex(frappe.ValidationError, "Nothing to post"):
			self._build()

	def test_credit_note_against_a_linked_invoice_is_allowed(self):
		card = self._rental_card()
		manual = self._manual_pi(600)
		link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		from erpnext.controllers.sales_and_purchase_return import make_return_doc

		ret = make_return_doc("Purchase Invoice", manual.name)
		ret.bill_no = "P0-RET-" + self.token
		ret.insert(ignore_permissions=True)
		ret.submit()
		self.assertEqual(ret.docstatus, 1)


def _user(roles, restrict_to=None):
	email = f"p0-{frappe.generate_hash(length=8)}@example.com"
	frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": "P0",
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


class _AuthBase(_P0Base):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def _other_company(self):
		name = "TEST-P0-CO-" + self.token
		if not frappe.db.exists("Company", name):
			co = frappe.new_doc("Company")
			co.update(
				{
					"company_name": name,
					"abbr": "Q" + self.token[:6].upper(),
					"default_currency": frappe.db.get_value("Company", self.company, "default_currency"),
					"country": frappe.db.get_value("Company", self.company, "country"),
				}
			)
			co.name = name
			co.db_insert()
		return name

	def _as(self, user, fn, *args):
		frappe.set_user(user)
		try:
			return fn(*args)
		finally:
			frappe.set_user("Administrator")


class TestLinkAuthorization(_AuthBase):
	"""Independent review 1: rights needed to create a reconciliation link or accept a correction."""

	def _link_args(self):
		card = self._rental_card()
		manual = self._manual_pi(600)
		return manual.name, [{"doctype": "Card Monthly Card", "name": card.name}]

	def test_card_manager_without_an_accounting_role_cannot_link(self):
		invoice, sources = self._link_args()
		user = _user(["Card Manager", "Purchase User"])
		with self.assertRaises(frappe.PermissionError):
			self._as(user, link_supplier_invoice, invoice, sources)

	def test_accountant_of_another_company_cannot_link(self):
		invoice, sources = self._link_args()
		user = _user(["Accounts Manager", "Card Manager"], restrict_to=self._other_company())
		with self.assertRaises(frappe.PermissionError):
			self._as(user, link_supplier_invoice, invoice, sources)
		self.assertFalse(frappe.db.exists("GL Posting Log", {"posting_doc": invoice}))

	def test_accountant_without_access_to_the_sources_cannot_link(self):
		invoice, sources = self._link_args()
		user = _user(["Accounts User"])  # no CARD role: cannot read the card
		with self.assertRaises(frappe.PermissionError):
			self._as(user, link_supplier_invoice, invoice, sources)

	def test_accountant_with_card_and_invoice_rights_can_link(self):
		invoice, sources = self._link_args()
		user = _user(["Accounts Manager", "Card Manager"])
		log = self._as(user, link_supplier_invoice, invoice, sources)
		self.assertEqual(frappe.db.get_value("GL Posting Log", log, "origin"), "Linked")

	def test_card_manager_cannot_declare_invoices_unrelated(self):
		self._rental_card()
		manual = self._manual_pi(600)
		user = _user(["Card Manager", "Purchase User"])
		from card.gl.posting import post_month

		with self.assertRaises(frappe.PermissionError):
			self._as(user, post_month, self.company, "Supplier", self.supplier, "9", "2026", [manual.name])

	def test_only_an_accounts_manager_of_the_company_accepts_a_correction(self):
		self._rental_card()
		pi = self._build()
		pi.items[0].expense_account = self.exp_transport
		pi.save()
		for user in (
			_user(["Accounts User", "Card Manager"]),
			_user(["Accounts Manager", "Card Manager"], restrict_to=self._other_company()),
		):
			with self.assertRaises(frappe.PermissionError):
				self._as(user, accept_correction, "Purchase Invoice", pi.name, "try")
		self.assertFalse(self._log(pi.name).accepted_signature)


class TestLinkAccuracy(_P0Base):
	"""Independent review 2: one comparison basis (VAT-exclusive) per source type; no net-or-gross false match."""

	def _vat_invoice(self, net, account=None):
		inv = self._manual_pi(net, account=account, submit=False)
		inv.taxes_and_charges = frappe.db.get_value(
			"Purchase Taxes and Charges Template",
			{"title": "Test CARD Purchase VAT", "company": self.company},
			"name",
		)
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		inv.set("taxes", [])
		for row in get_taxes_and_charges("Purchase Taxes and Charges Template", inv.taxes_and_charges):
			inv.append("taxes", row)
		inv.save()
		return inv

	def test_net_card_equal_to_the_invoice_gross_is_not_a_match(self):
		self._vat_supplier()
		eq = self._equipment(rate_type="بالساعة", rate=86.25)
		card = self._card(eq, [8], submit=True)  # 690.00 net
		inv = self._vat_invoice(600)  # 600 + 90 = 690 gross
		self.assertEqual(flt(inv.grand_total, 2), flt(card.net_amount, 2))
		with self.assertRaisesRegex(frappe.ValidationError, "accept the difference"):
			link_supplier_invoice(inv.name, [{"doctype": "Card Monthly Card", "name": card.name}])

	def test_mixed_rental_and_vat_inclusive_diesel_match_on_net(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		card = self._rental_card()  # 600 net
		fill = self._fill(litres=100, price=2.3)  # 230 incl. VAT = 200 net
		inv = self._vat_invoice(800)
		log = frappe.get_doc(
			"GL Posting Log",
			link_supplier_invoice(
				inv.name,
				[
					{"doctype": "Card Monthly Card", "name": card.name},
					{"doctype": "Project Diesel Fill", "name": fill.name},
				],
			),
		)
		self.assertEqual(flt(log.link_difference, 2), 0.0)
		self.assertEqual(sorted(flt(r.amount, 2) for r in log.sources), [200.0, 600.0])

	def test_vat_exclusive_diesel_matches_the_invoice_net(self):
		self._vat_supplier()
		self._set_basis("Exclusive")
		fill = self._fill()  # 200 net
		inv = self._vat_invoice(200, account=self.exp_diesel)
		log = link_supplier_invoice(inv.name, [{"doctype": "Project Diesel Fill", "name": fill.name}])
		self.assertEqual(flt(frappe.db.get_value("GL Posting Log", log, "link_difference"), 2), 0.0)

	def test_unverified_basis_with_vat_needs_an_accepted_reason(self):
		self._vat_supplier()
		self._set_basis("")
		fill = self._fill()
		inv = self._vat_invoice(200, account=self.exp_diesel)
		with self.assertRaisesRegex(frappe.ValidationError, "not verified"):
			link_supplier_invoice(inv.name, [{"doctype": "Project Diesel Fill", "name": fill.name}])
		log = link_supplier_invoice(
			inv.name,
			[{"doctype": "Project Diesel Fill", "name": fill.name}],
			"basis checked on the paper invoice",
			1,
		)
		self.assertIn("open difference", frappe.db.get_value("GL Posting Log", log, "remarks"))

	def test_sources_of_two_months_link_to_one_invoice(self):
		fill_sep = self._fill(day="2026-09-28")
		fill_oct = self._fill(day="2026-10-03")
		inv = self._manual_pi(400, posting_date="2026-10-06", account=self.exp_diesel)
		log = link_supplier_invoice(
			inv.name,
			[
				{"doctype": "Project Diesel Fill", "name": fill_sep.name},
				{"doctype": "Project Diesel Fill", "name": fill_oct.name},
			],
		)
		self.assertEqual(frappe.db.get_value("GL Posting Log", log, ["month", "year"]), ("10", 2026))


class TestEvidenceCoverage(_P0Base):
	"""Independent review 3: hand-booked invoices found by account, without CARD items, and dated around the month."""

	def test_line_without_item_on_an_expense_account_is_evidence(self):
		self._rental_card()
		inv = self._manual_pi(500, submit=False)
		inv.items[0].item_code = None
		inv.items[0].item_name = "diesel per supplier invoice"
		inv.items[0].description = "diesel per supplier invoice"
		inv.items[0].uom = "Nos"
		inv.items[0].conversion_factor = 1
		inv.save()
		with self.assertRaisesRegex(frappe.ValidationError, inv.name):
			self._build()

	def test_alternative_expense_account_is_evidence(self):
		self._rental_card()
		other = frappe.db.get_value(
			"Account",
			{
				"company": self.company,
				"root_type": "Expense",
				"is_group": 0,
				"name": ["not in", [self.exp_rental, self.exp_diesel, self.exp_transport]],
			},
			"name",
		)
		inv = self._manual_pi(500, account=other)
		with self.assertRaisesRegex(frappe.ValidationError, inv.name):
			self._build()

	def test_invoice_dated_after_the_month_is_evidence(self):
		self._rental_card()
		inv = self._manual_pi(600, posting_date="2026-10-06")
		with self.assertRaisesRegex(frappe.ValidationError, inv.name):
			self._build()

	def test_invoice_dated_before_the_month_is_evidence(self):
		self._rental_card()
		inv = self._manual_pi(600, posting_date="2026-08-25")
		with self.assertRaisesRegex(frappe.ValidationError, inv.name):
			self._build()

	def test_manual_invoice_after_a_card_posting_gets_a_duplicate_warning(self):
		self._rental_card()
		pi = self._build()
		pi.submit()
		frappe.local.message_log = []
		inv = self._manual_pi(600, posting_date="2026-10-05", submit=False)
		inv.submit()
		self.assertTrue(any("CARD already booked" in str(m) for m in frappe.local.message_log))


class TestFinalReviewFixes(_P0Base):
	"""Independent review of the full PR: linked drafts re-checked at submit, duplicate sources,
	bill no. of a CARD posting, reconciliation of linked invoices."""

	def test_linked_draft_changed_supplier_is_refused(self):
		card = self._rental_card()
		manual = self._manual_pi(600, submit=False)
		link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		other = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "TEST-P0-OTHER3-" + self.token}
		).insert(ignore_permissions=True)
		manual.reload()
		manual.supplier = other.name
		manual.save()
		with self.assertRaisesRegex(frappe.ValidationError, "changed company or supplier"):
			manual.submit()

	def test_linked_draft_changed_amount_is_refused(self):
		card = self._rental_card()
		manual = self._manual_pi(600, submit=False)
		link_supplier_invoice(manual.name, [{"doctype": "Card Monthly Card", "name": card.name}])
		manual.reload()
		manual.items[0].rate = 1600
		manual.save()
		with self.assertRaisesRegex(frappe.ValidationError, "was linked to CARD sources for net"):
			manual.submit()

	def test_linked_draft_with_an_accepted_difference_submits(self):
		card = self._rental_card()
		manual = self._manual_pi(650, submit=False)
		link_supplier_invoice(
			manual.name,
			[{"doctype": "Card Monthly Card", "name": card.name}],
			"mobilization on the invoice",
			1,
		)
		manual.reload()
		manual.submit()
		self.assertEqual(manual.docstatus, 1)

	def test_a_source_listed_twice_is_refused(self):
		card = self._rental_card()
		manual = self._manual_pi(1200)
		with self.assertRaisesRegex(frappe.ValidationError, "listed twice"):
			link_supplier_invoice(
				manual.name,
				[
					{"doctype": "Card Monthly Card", "name": card.name},
					{"doctype": "Card Monthly Card", "name": card.name},
				],
			)

	def test_hand_booked_invoice_cannot_reuse_the_bill_no_of_a_card_posting(self):
		self._vat_supplier()
		self._rental_card()
		pi = self._build()
		pi.bill_no = "P0-BILL-" + self.token
		pi.bill_date = pi.posting_date
		pi.save()
		pi.submit()
		manual = self._manual_pi(100, posting_date="2026-12-20", submit=False)
		manual.bill_no = pi.bill_no
		manual.save()
		with self.assertRaisesRegex(frappe.ValidationError, "already booked by CARD posting"):
			manual.submit()

	def test_reconciliation_counts_a_linked_card_in_its_own_month_and_the_rest_outside(self):
		from card.reconciliation import cards_invoiced, invoices_outside_card

		card = self._rental_card()  # September, 600 net
		fill = self._fill(day="2026-10-02")  # 200
		manual = self._manual_pi(800, posting_date="2026-10-06")
		link_supplier_invoice(
			manual.name,
			[
				{"doctype": "Card Monthly Card", "name": card.name},
				{"doctype": "Project Diesel Fill", "name": fill.name},
			],
		)
		sep = cards_invoiced("Supplier", [self.supplier], self.company, "2026-09-01", "2026-09-30")
		self.assertEqual(flt(sep.get(self.supplier), 2), 600.0)
		octo = cards_invoiced("Supplier", [self.supplier], self.company, "2026-10-01", "2026-10-31")
		self.assertFalse(octo.get(self.supplier))
		outside = invoices_outside_card("Supplier", [self.supplier], self.company, "2026-10-01", "2026-10-31")
		self.assertEqual(flt(outside.get(self.supplier), 2), 200.0)  # the diesel part, not a card
