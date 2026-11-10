# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-149 (#49, WP-S2): an approved, current Card Period Run before the monthly posting, opt-in per company.

Proven here: off by default and then the posting is unchanged (the same invoice with and without the gate; the run
is never read); on, every route refuses without an approved, current run (whitelisted post_month and rebuild_month,
a background job, the builder called directly, both sides, the preview as ``blocked``), with the reason (no run,
draft, waiting, returned, an approval of another version, self-approval under the company's Refuse rule, stale);
a rebuild is refused before it deletes the old draft; an approved, current run lets both sides post, in FR-139
Hold and Post; the document-by-document comparison (side, party, fingerprint as the posting read the document,
fill supplier VAT registration, diesel VAT basis) without comparing amounts with invoice totals (a VAT-inclusive
diesel price posts its net part against the run's gross amount); the stricter of the run's and the company's
self-approval rule; the posting screen's read; and, with two connections, a change committed while a posting
runs (a source changed, a source added, the run cancelled) is seen by the locked re-check."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from card.card.doctype.equipment_transport.equipment_transport import record_financial_decision
from card.constants import DIR_RENTED_IN
from card.gl import period_gate, period_run, posting, preflight
from card.gl.posting import build_monthly_posting, preview_monthly_posting, rebuild_monthly_posting
from card.tests.test_posting_preview import _invoice_lines, _PreviewBase
from card.tests.test_s3_posting import _leaf_under
from card.tests.transport_parties import company_paid

RUN = "Card Period Run"
CARD = "Card Monthly Card"
FILL = "Project Diesel Fill"
TRANSPORT = "Equipment Transport"
Refused = period_gate.PeriodRunRequiredError


class TestPeriodRunPostingGate(_PreviewBase):
	def setUp(self):
		super().setUp()
		frappe.db.set_value("Project", self.project, "customer", self.customer)
		self.accountant = self._user("acc", ("Accounts Manager",))
		self.accountant2 = self._user("acc2", ("Accounts Manager",))

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	# ---------- builders ----------
	def _user(self, prefix, roles):
		email = f"prp-{prefix}-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Gate " + prefix,
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
		frappe.clear_cache(user=email)
		return email

	def _settings(self, **values):
		settings = frappe.get_doc("Card Settings")
		row = next(r for r in settings.company_settings if r.company == self.company)
		row.update(values)
		settings.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Card Settings")

	def _require(self, on=1):
		self._settings(require_period_approval=on)

	def _mode(self, value):
		self._settings(
			transport_responsibility_posting=value,
			transport_recharge_income_account=_leaf_under(
				self.company, "Income", "Test Transport Recharge Income"
			),
		)

	def _as(self, user, fn, *args, **kwargs):
		frappe.set_user(user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _run(self, submit=True, user="Administrator"):
		def go():
			run = frappe.new_doc(RUN)
			run.update({"company": self.company, "month": "09", "year": 2026})
			run.insert()
			if submit:
				run.submit()
			return run.name

		return frappe.get_doc(RUN, self._as(user, go))

	def _status(self, run, status, user=None, reason=None):
		def go():
			doc = frappe.get_doc(RUN, run.name)
			doc.approval_status = status
			if reason:
				doc.return_reason = reason
			doc.save()

		self._as(user or self.accountant, go)
		return frappe.get_doc(RUN, run.name)

	def _approved(self, user=None):
		return self._status(self._run(), period_run.APPROVED, user)

	def _post(self, party_type="Supplier", party=None):
		party = party or (self.supplier if party_type == "Supplier" else self.customer)
		return build_monthly_posting(self.company, party_type, party, 9, 2026)

	def _refused(self, fn, *args, contains=None, **kwargs):
		with self.assertRaises(Refused) as ctx:
			fn(*args, **kwargs)
		frappe.local.message_log = []
		if contains:
			self.assertIn(contains, str(ctx.exception))
		return str(ctx.exception)

	def _transport(self, amount=400):
		t = frappe.new_doc(TRANSPORT)
		t.update(
			{
				"date": "2026-09-10",
				"company": self.company,
				"transport_supplier": self.supplier,
				"destination_type": "Project",
				"project": self.project,
				"amount": amount,
			}
		)
		t.append("items", {"card_equipment": self._equipment().name})
		return t

	def _submitted(self, t):
		t.insert(ignore_permissions=True)
		t.submit()
		return t

	def _billed_transport(self):
		t = company_paid(self._transport())
		t.cost_bearer = "Customer"
		self._submitted(t)
		self._as(
			self.accountant,
			record_financial_decision,
			t.name,
			"Bill customer",
			customer=self.customer,
			billing_project=self.project,
			billing_amount=650,
			billing_mode="Monthly invoice",
			billing_reference="CONTRACT-PRP",
			confirmed=1,
		)
		return frappe.get_doc(TRANSPORT, t.name)

	def _month(self):
		"""A rented card (supplier), a sub-rental card (both sides) and a diesel fill (supplier)."""
		return frappe._dict(
			rented=self._card(self._equipment(), [8], submit=True).name,
			sub=self._card(self._sub_rental(), [10], submit=True).name,
			fill=self._fill().name,
		)

	def _no_artifacts(self):
		self.assertFalse(frappe.get_all("GL Posting Log", filters={"company": self.company}))
		self.assertFalse(frappe.get_all("Purchase Invoice", filters={"supplier": self.supplier}))
		self.assertFalse(frappe.get_all("Sales Invoice", filters={"customer": self.customer}))

	# ---------- off (the default) ----------
	def test_off_by_default_and_the_run_is_never_read(self):
		meta = frappe.get_meta("Card Company Settings")
		self.assertEqual(meta.get_field("require_period_approval").default, "0")
		self.assertFalse(period_gate.required(self.company))
		self._month()

		def boom(*args, **kwargs):
			raise AssertionError("the period run is read with the setting off")

		with (
			patch.object(period_run, "active_run", boom),
			patch.object(period_run, "check_current", boom),
			patch.object(period_gate, "_load", boom),
		):
			self.assertTrue(self._post("Supplier"))
			self.assertTrue(self._post("Customer"))
		self.assertIsNone(period_gate.check_posting(self.company, "Supplier", self.supplier, 9, 2026, {}))

	def test_the_same_invoice_with_and_without_the_gate(self):
		self._vat_supplier()
		self._month()
		off = {}
		for party_type in ("Supplier", "Customer"):
			name = self._post(party_type)
			doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
			doc = frappe.get_doc(doctype, name)
			off[party_type] = (_invoice_lines(doctype, name), flt(doc.grand_total, 2), len(doc.taxes))
			frappe.delete_doc(doctype, name, ignore_permissions=True)  # frees its sources (events.on_trash)
		self._require()
		self._approved()
		for party_type in ("Supplier", "Customer"):
			name = self._post(party_type)
			doctype = "Purchase Invoice" if party_type == "Supplier" else "Sales Invoice"
			doc = frappe.get_doc(doctype, name)
			self.assertEqual(
				(_invoice_lines(doctype, name), flt(doc.grand_total, 2), len(doc.taxes)), off[party_type]
			)

	# ---------- on: refused on every route ----------
	def test_no_run_is_refused_on_every_route(self):
		self._require()
		self._month()
		message = "requires an approved period run"
		args = (self.company, "Supplier", self.supplier, "9", "2026")
		self._refused(posting.post_month, *args, contains=message)  # whitelisted
		self._refused(posting.rebuild_month, *args, contains=message)  # whitelisted
		self._refused(build_monthly_posting, self.company, "Supplier", self.supplier, 9, 2026)  # direct
		self._refused(rebuild_monthly_posting, self.company, "Supplier", self.supplier, 9, 2026)
		self._refused(  # a background job (enqueue runs the same function; now=True runs it here)
			frappe.enqueue,
			"card.gl.posting.build_monthly_posting",
			now=True,
			company=self.company,
			party_type="Supplier",
			party=self.supplier,
			month=9,
			year=2026,
		)
		self._refused(build_monthly_posting, self.company, "Customer", self.customer, 9, 2026)
		for party_type, party in (("Supplier", self.supplier), ("Customer", self.customer)):
			preview = preview_monthly_posting(self.company, party_type, party, 9, 2026)
			self.assertIn(message, preview.blocked)
		self._no_artifacts()

	def test_a_rebuild_is_refused_before_it_deletes_the_draft(self):
		self._month()
		draft = self._post("Supplier")
		self._require()
		calls = []
		real = frappe.delete_doc
		with patch.object(frappe, "delete_doc", lambda *a, **k: calls.append(a) or real(*a, **k)):
			self._refused(rebuild_monthly_posting, self.company, "Supplier", self.supplier, 9, 2026)
		self.assertEqual(calls, [])
		self.assertTrue(frappe.db.exists("Purchase Invoice", draft))

	def test_a_run_not_approved_is_refused_with_its_reason(self):
		self._require()
		self._month()
		run = self._run(submit=False)
		self._refused(self._post, contains="is still a draft")
		frappe.get_doc(RUN, run.name).submit()
		self._refused(self._post, contains="is waiting for an accountant's approval")
		self._status(run, period_run.RETURNED, reason="wrong hours")
		self._refused(self._post, contains="was returned for correction (wrong hours)")
		self._no_artifacts()

	def test_an_approval_of_another_version_is_refused(self):
		self._require()
		self._month()
		run = self._approved()
		frappe.db.set_value(RUN, run.name, "approved_version", 7, update_modified=False)
		self._refused(self._post, contains="is not for its current version")
		frappe.db.set_value(RUN, run.name, {"approved_version": run.version, "approved_hash": "x" * 64})
		self._refused(self._post, contains="is not for its current version")

	# ---------- on: an approved, current run posts ----------
	def test_an_approved_current_run_posts_both_sides(self):
		self._require()
		docs = self._month()
		run = self._approved()
		preview = preview_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
		self.assertFalse(preview.blocked, preview.blocked)
		pi = self._post("Supplier")
		self.assertEqual(
			{s.source_name for s in frappe.get_doc("GL Posting Log", {"posting_doc": pi}).sources},
			{docs.rented, docs.sub, docs.fill},
		)
		# posting one side never makes the run stale (FR-147): the other side posts against the same run
		self.assertTrue(period_run.check_current(frappe.get_doc(RUN, run.name)).current)
		self.assertTrue(self._post("Customer"))

	def test_fr139_post_mode_transports_post_with_an_approved_run(self):
		self._mode(preflight.TRANSPORT_POSTING_POST)
		self._require()
		self._month()
		cost = self._submitted(company_paid(self._transport(250), basis="Project", cost_project=self.project))
		billed = self._billed_transport()
		self._approved()
		pi = self._post("Supplier")
		si = self._post("Customer")
		held = {
			name: {s.source_name for s in frappe.get_doc("GL Posting Log", {"posting_doc": name}).sources}
			for name in (pi, si)
		}
		self.assertTrue({cost.name, billed.name} <= held[pi])
		self.assertIn(billed.name, held[si])

	def test_fr139_hold_keeps_the_responsibility_transports_out(self):
		self._mode(preflight.TRANSPORT_POSTING_HOLD)
		self._require()
		self._month()
		held = self._submitted(company_paid(self._transport(250), basis="Project", cost_project=self.project))
		run = self._approved()
		self.assertNotIn(held.name, {r.source_name for r in run.sources})
		pi = self._post("Supplier")
		self.assertNotIn(
			held.name, {s.source_name for s in frappe.get_doc("GL Posting Log", {"posting_doc": pi}).sources}
		)

	# ---------- stale and document by document ----------
	def test_a_run_that_became_stale_is_refused(self):
		self._require()
		docs = self._month()
		self._approved()
		new = self._fill(day="2026-09-15")
		# the supplier posting would bill the new fill: the document-by-document step names it
		self._refused(self._post, "Supplier", contains=f"{new.name} (not in the run on this side)")
		# the customer posting does not bill it, but the run is no longer current
		text = self._refused(self._post, "Customer", contains="changed after period run")
		self.assertIn(f"added: {new.name}", text)
		frappe.db.set_value(FILL, new.name, "docstatus", 2)
		self.assertTrue(self._post("Customer"))
		frappe.db.set_value(CARD, docs.rented, "rate", 99)  # a fingerprinted field of a billed card
		self._refused(self._post, "Supplier", contains=f"{docs.rented} (changed since the run was built)")

	def test_vat_inclusive_diesel_posts_its_net_part_against_the_gross_run(self):
		"""Like with like: the run holds the fill's gross amount, the invoice books its net part; nothing compares
		the two. The basis and the supplier's VAT registration are compared, never inferred."""
		self._vat_supplier()
		self._set_basis("Inclusive")
		self._require()
		fill = self._fill()  # 100 L x 2 = 200 gross
		run = self._approved()
		row = next(r for r in run.sources if r.source_name == fill.name)
		self.assertEqual((flt(row.supplier_amount, 2), row.supplier_vat_registered), (200.0, 1))
		self.assertEqual(run.diesel_vat_basis, "Inclusive")
		pi = frappe.get_doc("Purchase Invoice", self._post("Supplier"))
		line = next(i for i in pi.items if fill.name in (i.description or ""))
		self.assertLess(flt(line.rate, 2), 200.0)  # the net part
		self.assertNotEqual(flt(pi.net_total, 2), flt(run.supplier_total, 2))

	def test_the_vat_basis_and_registration_of_the_run_are_compared(self):
		self._vat_supplier()
		self._set_basis("Inclusive")
		self._require()
		fill = self._fill()
		self._card(self._sub_rental(), [10], submit=True)  # a customer side without fills
		self._approved()
		self._set_basis("Exclusive")
		# the fill's own posting: the document-by-document step compares the basis
		self._refused(self._post, "Supplier", contains="diesel price VAT basis Exclusive")
		# a posting without fills: the run is stale (its snapshot holds the basis)
		self._refused(self._post, "Customer", contains="changed after period run")
		self._set_basis("Inclusive")
		sources = {CARD: [], FILL: [(fill.name, 0)], TRANSPORT: []}
		check = period_gate.check_posting
		text = self._refused(
			check,
			self.company,
			"Supplier",
			self.supplier,
			9,
			2026,
			sources,
			frappe._dict(diesel_price_vat_basis="Exclusive"),
			True,
		)
		self.assertIn("diesel price VAT basis Exclusive (the run was built with Inclusive)", text)
		text = self._refused(
			check,
			self.company,
			"Supplier",
			self.supplier,
			9,
			2026,
			sources,
			frappe._dict(diesel_price_vat_basis="Inclusive"),
			False,
		)
		self.assertIn(f"{fill.name} (supplier VAT registration changed)", text)

	def test_each_billed_document_must_be_in_the_run_on_its_side_for_its_party(self):
		self._require()
		docs = self._month()
		run = self._approved()
		check = period_gate.check_posting
		self.assertEqual(
			check(self.company, "Supplier", self.supplier, 9, 2026, {CARD: [(docs.rented, 0)]}, None, False),
			run.name,
		)
		text = self._refused(
			check, self.company, "Customer", self.customer, 9, 2026, {CARD: [(docs.rented, 0)]}
		)
		self.assertIn(f"{docs.rented} (not in the run on this side)", text)
		text = self._refused(
			check, self.company, "Supplier", "OTHER-SUP", 9, 2026, {CARD: [(docs.rented, 0)]}
		)
		self.assertIn(f"{docs.rented} (another party in the run)", text)
		text = self._refused(
			check, self.company, "Supplier", self.supplier, 9, 2026, {FILL: [("NOT-A-FILL", 0)]}
		)
		self.assertIn("NOT-A-FILL (not in the run on this side)", text)
		self.assertIn(run.name, text)

	def test_a_run_of_another_month_does_not_count(self):
		self._require()
		self._month()
		self._approved()
		self._refused(
			period_gate.check_posting,
			self.company,
			"Supplier",
			self.supplier,
			10,
			2026,
			{},
			contains="requires an approved period run before posting 10/2026",
		)

	# ---------- self-approval: the stricter of the run's and the company's rule ----------
	def test_company_refuse_rule_applies_to_runs_and_postings(self):
		self._require()
		self._month()
		both = self._user("both", ("Card Manager", "Accounts Manager"))
		run = self._status(self._run(user=both), period_run.APPROVED, user=both)  # Warn: approved, marked
		self.assertEqual((run.self_approved, run.self_approval_rule), (1, period_run.RULE_WARN))
		frappe.local.message_log = []
		self.assertTrue(self._post("Supplier"))
		self._settings(period_run_self_approval_rule=period_run.RULE_REFUSE)
		self._refused(self._post, "Customer", contains="the self-approval rule of company")

	def test_company_refuse_rule_stops_a_self_approval(self):
		self._require()
		self._month()
		both = self._user("both", ("Card Manager", "Accounts Manager"))
		run = self._run(user=both)  # built while the company rule is Warn: the run's own rule is Warn
		self.assertEqual(run.self_approval_rule, period_run.RULE_WARN)
		self._settings(period_run_self_approval_rule=period_run.RULE_REFUSE)
		with self.assertRaises(frappe.PermissionError):
			self._status(run, period_run.APPROVED, user=both)
		frappe.local.message_log = []
		self._status(run, period_run.APPROVED, user=self.accountant2)
		self.assertTrue(self._post("Supplier"))

	def test_a_run_built_under_the_company_refuse_rule_takes_refuse(self):
		self._settings(period_run_self_approval_rule=period_run.RULE_REFUSE)
		self._month()
		self.assertEqual(self._run(submit=False).self_approval_rule, period_run.RULE_REFUSE)
		self.assertEqual(period_run.company_self_approval_rule(self.company), period_run.RULE_REFUSE)
		self._settings(period_run_self_approval_rule="")
		self.assertEqual(period_run.company_self_approval_rule(self.company), period_run.RULE_WARN)

	# ---------- the posting screen ----------
	def test_the_screen_read_explains_the_refusal_and_writes_nothing(self):
		self._month()
		state = posting.posting_period_run(self.company, "9", "2026")
		self.assertEqual((state.required, state.refusal, state.run), (False, None, None))
		self.assertIn("requires an approved period run", state.would_refuse)
		self._require()
		state = posting.posting_period_run(self.company, "9", "2026")
		self.assertIn("requires an approved period run", state.refusal)
		run = self._run()
		state = posting.posting_period_run(self.company, "9", "2026")
		self.assertEqual((state.run, state.version, state.current), (run.name, run.version, True))
		self.assertIn("is waiting for an accountant's approval", state.refusal)
		self._status(run, period_run.APPROVED)
		guards = self._no_write_guard()
		for g in guards:
			g.start()
		try:
			state = posting.posting_period_run(self.company, "9", "2026")
		finally:
			for g in reversed(guards):
				g.stop()
		self.assertEqual((state.refusal, state.approval_status), (None, period_run.APPROVED))
		self._fill(day="2026-09-20")
		state = posting.posting_period_run(self.company, "9", "2026")
		self.assertFalse(state.current)
		self.assertIn("changed after period run", state.refusal)
		self.assertNotIn("supplier_total", state)
		self.assertEqual(
			frappe.allowed_http_methods_for_whitelisted_func[posting.posting_period_run], ["GET"]
		)

	def test_a_real_build_rechecks_with_locks_and_the_preview_without(self):
		self._require()
		self._month()
		self._approved()
		calls = []
		real = period_gate.check_posting

		def spy(*args, **kwargs):
			calls.append(kwargs.get("lock"))
			return real(*args, **kwargs)

		with patch.object(period_gate, "check_posting", spy):
			preview_monthly_posting(self.company, "Supplier", self.supplier, 9, 2026)
			self._post("Supplier")
		self.assertEqual(calls, [False, True])

	def test_the_screen_read_hides_a_run_the_user_cannot_open(self):
		self._require()
		self._month()
		run = self._approved()
		real = frappe.has_permission

		def no_run_read(doctype, *args, **kwargs):
			return False if doctype == RUN else real(doctype, *args, **kwargs)

		with patch.object(frappe, "has_permission", no_run_read):
			state = period_gate.run_state(self.company, 9, 2026)
		self.assertIsNone(state.run)
		self.assertNotIn(run.name, state.refusal)
		self.assertIn("you cannot open it", state.refusal)

	def test_the_screen_read_needs_the_posting_role(self):
		user = self._user("cu", ("Card User",))
		with self.assertRaises(frappe.PermissionError):
			self._as(user, posting.posting_period_run, self.company, "9", "2026")


class TestPeriodRunPostingConcurrency(IntegrationTestCase):
	"""Lesson 4 (two connections): a change committed by another request while a posting runs its gate is seen by
	the locked re-check (the run rows, the month's sources and their rows, the fill supplier, the company's settings
	row are read with locking reads, not the request's REPEATABLE READ snapshot). The first request writes and keeps
	its transaction open; the posting gate runs in the second, waits for the first one's lock, then must refuse.
	Records are committed and removed (or restored) in tearDown."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.site, cls.sites_path = frappe.local.site, frappe.local.sites_path
		cls.has_snapshot_isolation = bool(frappe.db.sql("show variables like 'innodb_snapshot_isolation'"))

	def setUp(self):
		from card.tests import test_assignment_overlap_concurrency as model

		self.model = model
		self.token = frappe.generate_hash(length=8)
		self.month, self.year = (
			"%02d" % (int(self.token[:4], 16) % 12 + 1),
			2100 + int(self.token[4:6], 16) % 50,
		)
		self.card = "TEST-PRP-RACE-" + self.token
		self.card2 = self.card + "-2"
		self.fill = "TEST-PRP-FILL-" + self.token
		self.transport = "TEST-PRP-TRN-" + self.token
		self.supplier = "TEST-PRP-SUP-" + self.token
		self.started = self._committed(frappe.utils.now)
		self.run = self._committed(self._make_records)

	def tearDown(self):
		self._committed(self._remove_records)
		self.assertEqual(self._committed(self._leftovers), 0, "synthetic records left behind")

	def _connect(self):
		frappe.init(self.site, sites_path=self.sites_path)
		frappe.connect()
		frappe.set_user("Administrator")
		frappe.flags.in_test = True

	def _first_day(self):
		return f"{self.year:04d}-{self.month}-05"

	def _insert(self, doctype, name, values):
		doc = frappe.new_doc(doctype)
		doc.update({"company": self.company, "docstatus": 1, **values})
		doc.name = name
		doc.db_insert()

	def _insert_card(self, name, amount=100):
		self._insert(
			CARD,
			name,
			{"month": self.month, "year": self.year, "card_direction": DIR_RENTED_IN, "net_amount": amount},
		)

	def _settings_row(self):
		"""The company's Card Company Settings row (created for the test when the company has none); its two
		values this class changes are restored in tearDown."""
		filters = {
			"parent": "Card Settings",
			"parenttype": "Card Settings",
			"parentfield": "company_settings",
		}
		name = frappe.db.get_value("Card Company Settings", {**filters, "company": self.company}, "name")
		if name:
			self.created_row = None
		else:
			row = frappe.new_doc("Card Company Settings")
			row.update({**filters, "company": self.company, "idx": 999})
			row.name = "TEST-PRP-ROW-" + self.token
			row.db_insert()
			name = self.created_row = row.name
		self.kept = frappe.db.get_value(
			"Card Company Settings",
			name,
			["diesel_price_vat_basis", "transport_responsibility_posting"],
			as_dict=True,
		)
		frappe.db.set_value(
			"Card Company Settings",
			name,
			{
				"diesel_price_vat_basis": "Exclusive",
				"transport_responsibility_posting": preflight.TRANSPORT_POSTING_HOLD,
			},
			update_modified=False,
		)
		return name

	def _make_records(self):
		self.company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
		group = frappe.db.get_value("Supplier Group", {"is_group": 0}, "name")
		if not (self.company and group):
			self.skipTest("test masters missing (card.install.before_tests)")
		self.row = self._settings_row()
		supplier = frappe.new_doc("Supplier")
		supplier.update({"supplier_name": self.supplier, "supplier_group": group})
		supplier.name = self.supplier
		supplier.db_insert()
		self._insert_card(self.card)
		self._insert(
			FILL,
			self.fill,
			{"date": self._first_day(), "supplier": self.supplier, "litres": 10, "amount": 50},
		)
		# a transport with a responsibility the company pays and bears: billed only in FR-139 Post
		self._insert(
			TRANSPORT,
			self.transport,
			{
				"date": self._first_day(),
				"amount": 10,
				"responsibility": "Company bears the cost",
				"payer": "Company",
				"cost_bearer": "Company",
			},
		)
		frappe.clear_cache(doctype="Card Settings")
		run = frappe.get_doc(
			{"doctype": RUN, "company": self.company, "month": self.month, "year": self.year}
		)
		run.insert(ignore_permissions=True)
		frappe.db.set_value(
			RUN,
			run.name,
			{
				"docstatus": 1,
				"approval_status": period_run.APPROVED,
				"approved_version": run.version,
				"approved_hash": run.snapshot_hash,
			},
			update_modified=False,
		)
		return run.name

	def _filters(self):
		return {"company": self.company, "month": self.month, "year": self.year}

	def _mine(self):
		return {
			CARD: [self.card, self.card2],
			FILL: [self.fill],
			TRANSPORT: [self.transport],
			"Supplier": [self.supplier],
		}

	def _remove_records(self):
		names = frappe.get_all(RUN, filters=self._filters(), pluck="name")
		for name in names:
			frappe.db.set_value(RUN, name, "docstatus", 0, update_modified=False)
			self.model._delete(RUN, name)
		for doctype, docs in self._mine().items():
			frappe.db.delete(doctype, {"name": ["in", docs]})
		if self.created_row:
			frappe.db.delete("Card Company Settings", {"name": self.created_row})
		else:
			frappe.db.set_value("Card Company Settings", self.row, self.kept, update_modified=False)
		frappe.clear_cache(doctype="Card Settings")
		mine = [*names, *(n for docs in self._mine().values() for n in docs)]
		since = {"creation": [">=", self.started]}
		frappe.db.delete("Version", {"docname": ["in", mine], **since})
		frappe.db.delete("Comment", {"reference_name": ["in", mine], **since})
		frappe.db.delete("Deleted Document", {"deleted_name": ["in", mine], **since})

	def _leftovers(self):
		count = frappe.db.count(RUN, self._filters())
		for doctype, docs in self._mine().items():
			count += frappe.db.count(doctype, {"name": ["in", docs]})
		if self.created_row:
			count += frappe.db.count("Card Company Settings", {"name": self.created_row})
		return count

	def _gate(self, lock=True):
		return period_gate.check_posting(
			self.company,
			"Supplier",
			self.supplier,
			self.month,
			self.year,
			{CARD: [], FILL: [(self.fill, 50)], TRANSPORT: []},
			frappe._dict(diesel_price_vat_basis="Exclusive"),
			False,
			lock=lock,
		)

	def _race_gate(self, first):
		with patch.object(period_gate, "required", lambda company: True):
			_one, two = self._race(first, self._gate)
		self.assertFalse(two.committed, "the gate passed on a stale snapshot")
		self.assertIsInstance(two.error, Refused, repr(two.error))
		return str(two.error)

	def test_the_gate_passes_without_a_concurrent_change(self):
		with patch.object(period_gate, "required", lambda company: True):
			self.assertEqual(self._committed(self._gate), self.run)
		run = self._committed(lambda: frappe.get_doc(RUN, self.run))
		self.assertEqual({r.source_name for r in run.sources}, {self.card, self.fill})  # Hold: no transport
		self.assertEqual(run.diesel_vat_basis, "Exclusive")

	def test_a_source_changed_meanwhile_is_seen(self):
		# rate is fingerprinted and not part of the selection's own fields: only the locked document read sees it
		text = self._race_gate(lambda: frappe.db.set_value(CARD, self.card, "rate", 120))
		self.assertIn(f"changed: {self.card}", text)

	def test_a_source_added_meanwhile_is_seen(self):
		text = self._race_gate(lambda: self._insert_card(self.card2))
		self.assertIn(f"added: {self.card2}", text)

	def test_a_fill_supplier_registered_meanwhile_is_seen(self):
		text = self._race_gate(
			lambda: frappe.db.set_value("Supplier", self.supplier, "tax_id", "300000000000003")
		)
		self.assertIn(f"changed: {self.fill}", text)

	def test_a_company_vat_basis_changed_meanwhile_is_seen(self):
		text = self._race_gate(
			lambda: frappe.db.set_value(
				"Card Company Settings",
				self.row,
				"diesel_price_vat_basis",
				"Inclusive",
				update_modified=False,
			)
		)
		self.assertIn("changed after period run", text)

	def test_a_switch_to_fr139_post_meanwhile_is_seen(self):
		text = self._race_gate(
			lambda: frappe.db.set_value(
				"Card Company Settings",
				self.row,
				"transport_responsibility_posting",
				preflight.TRANSPORT_POSTING_POST,
				update_modified=False,
			)
		)
		self.assertIn(f"added: {self.transport}", text)

	def test_a_run_cancelled_meanwhile_is_seen(self):
		text = self._race_gate(
			lambda: frappe.db.set_value(RUN, self.run, "docstatus", 2, update_modified=False)
		)
		self.assertIn("requires an approved period run", text)


def _bind_model_helpers():
	from card.tests import test_assignment_overlap_concurrency as model

	base = model.TestAssignmentOverlapConcurrency
	TestPeriodRunPostingConcurrency._committed = base._committed
	TestPeriodRunPostingConcurrency._race = base._race


_bind_model_helpers()
