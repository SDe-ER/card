# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""S3 lifecycle (owner items 4a/4b).

Reservation model:
- The GL Posting Log's `sources` child table is the AUTHORITATIVE list of the
  documents a posting includes (written at build time, card/gl/posting.py).
  The sources' own `gl_posting` link is display-only and may point at either
  side's log for sub-rental cards.
- A DRAFT posting reserves its party+month through the log's unique
  posting_key; sources never link to the invoice at draft, so frappe's
  backlink check still allows deleting the draft.
- On SUBMIT the side's invoice link (`purchase_invoice` / `sales_invoice`)
  is written onto every source in the log's list and `posted` flips to 1.
- `before_cancel` of the invoice clears those links FIRST (frappe runs
  before_cancel at document.py:1420, the backlink check only at :1463), so a
  submitted posting can be cancelled and its sources are freed.
- Handlers act ONLY on invoices that have a GL Posting Log row; every other
  Purchase/Sales Invoice on the site passes through untouched.
"""

import frappe
from frappe import _
from frappe.utils import flt

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES


def _log_for(doc):
	"""The ACTIVE log this document belongs to. H1: status-filtered — invoice
	names are legitimately reused after a rebuild (frappe reverts the naming
	series), so a cancelled namesake log must never be resolved here. The
	anti-resurrection guard (_block_amended_copy) deliberately looks across
	ALL statuses instead, keeping only logs written at or after the invoice."""
	name = frappe.db.get_value(
		"GL Posting Log",
		{
			"posting_doc": doc.name,
			"posting_doctype": doc.doctype,
			"status": ["in", list(ACTIVE_STATES)],
		},
		"name",
	)
	return frappe.get_doc("GL Posting Log", name) if name else None


def _side_field(invoice_doctype):
	return "purchase_invoice" if invoice_doctype == "Purchase Invoice" else "sales_invoice"


def _log_sources(log):
	"""The posting's authoritative source list (build-time child rows)."""
	return [(row.source_doctype, row.source_name) for row in log.get("sources") or []]


def active_log_holding(doctype, name, party_type=None):
	"""The active (Draft/Submitted) GL Posting Log that includes this source,
	if any — exact membership through the GL Posting Source child rows; with
	party_type, only a log of that side counts."""
	for parent in frappe.get_all(
		"GL Posting Source",
		filters={"parenttype": "GL Posting Log", "source_doctype": doctype, "source_name": name},
		pluck="parent",
	):
		log = frappe.db.get_value(
			"GL Posting Log",
			parent,
			["name", "status", "posting_doc", "posting_doctype", "party_type"],
			as_dict=True,
		)
		if log and log.status in ACTIVE_STATES and (not party_type or log.party_type == party_type):
			return log
	return None


def _point_display(doctype, name, log_name):
	"""Keep the source's informational gl_posting link on an ACTIVE log without
	stealing the pointer from the other side's active posting (sub-rental)."""
	current = frappe.db.get_value(doctype, name, "gl_posting")
	if current == log_name:
		return
	if current and frappe.db.get_value("GL Posting Log", current, "status") in ACTIVE_STATES:
		return
	frappe.db.set_value(doctype, name, "gl_posting", log_name, update_modified=False)


def _other_active_holder(doctype, name, log):
	"""Another ACTIVE log of the SAME side that also lists this source — the
	submit-time membership re-check of §5a (type-free, party_type = the side)."""
	for parent in frappe.get_all(
		"GL Posting Source",
		filters={"parenttype": "GL Posting Log", "source_doctype": doctype, "source_name": name},
		pluck="parent",
	):
		if parent == log.name:
			continue
		other = frappe.db.get_value("GL Posting Log", parent, ["name", "status", "party_type"], as_dict=True)
		if other and other.status in ACTIVE_STATES and other.party_type == log.party_type:
			return other.name
	return None


def _other_side_still_posted(doctype, name, cleared_field):
	other = "sales_invoice" if cleared_field == "purchase_invoice" else "purchase_invoice"
	if not frappe.get_meta(doctype).has_field(other):
		# FR-139: a source without a link field for the other side (Equipment Transport has no
		# sales_invoice) is still posted on that side while a SUBMITTED log of that side holds it
		other_side = "Customer" if cleared_field == "purchase_invoice" else "Supplier"
		holder = active_log_holding(doctype, name, other_side)
		return bool(holder and holder.status == "Submitted")
	return bool(frappe.db.get_value(doctype, name, other))


def _is_built(log):
	return (log.get("origin") or "Built") == "Built"


def validate(doc, method=None):
	"""Reject amendments of CARD postings and user edits that would skew the
	generated draft's arithmetic."""
	_block_amended_copy(doc)
	if doc.flags.get("card_gl_build"):
		return
	log = _log_for(doc)
	if not log or not _is_built(log):
		return
	stored = (
		frappe.db.get_value(
			doc.doctype, doc.name, ["discount_amount", "additional_discount_percentage"], as_dict=True
		)
		or frappe._dict()
	)
	changed = flt(doc.get("discount_amount")) != flt(stored.get("discount_amount")) or flt(
		doc.get("additional_discount_percentage")
	) != flt(stored.get("additional_discount_percentage"))
	if changed:
		frappe.throw(
			_(
				"{0} was generated by CARD; apply discounts as addition/deduction rows on the cards, not on the invoice."
			).format(doc.name)
		)


def _block_amended_copy(doc):
	"""An amendment of a cancelled CARD posting would submit the same source
	lines a second time outside the log lifecycle — the only supported paths
	are rebuilding the month or a supplementary posting.

	A log belongs to an invoice only when it was written at or after that
	invoice's creation: the builder inserts the invoice, then its log, in one
	transaction. Frappe reverts the naming series when the last draft is
	deleted, so a later manual invoice can carry the number of a deleted CARD
	draft whose log stays behind; that older log does not make the manual
	invoice a CARD posting. Every invoice up the amendment chain is checked,
	and a missing timestamp or an equal one refuses (fail-closed)."""
	name, seen = doc.get("amended_from"), set()
	while name and name not in seen:
		seen.add(name)
		# only CARD-built postings: a hand-booked supplier invoice that was linked keeps
		# the normal ERPNext cancel-and-amend correction (its link is freed on cancel)
		logged = frappe.get_all(
			"GL Posting Log",
			filters={
				"posting_doc": name,
				"posting_doctype": doc.doctype,
				"origin": ["in", ["Built", "", None]],
			},
			pluck="creation",
		)
		if logged:
			created = frappe.db.get_value(doc.doctype, name, "creation")
			if not created or any(not at or at >= created for at in logged):
				frappe.throw(
					_(
						"{0} amends CARD posting {1}; amendments would post the same source documents twice. Build the month again from CARD instead."
					).format(doc.name or _("This invoice"), name)
				)
		name = frappe.db.get_value(doc.doctype, name, "amended_from")


def before_submit(doc, method=None):
	log = _log_for(doc)
	if not log:
		# P0: an invoice CARD did not build may not repeat a CARD posting or a held source.
		# A return / credit note or a debit note against an invoice corrects it; it never books the source twice.
		if doc.get("is_return") or doc.get("is_debit_note"):
			return
		from card.gl.integrity import check_not_a_copy, warn_card_postings_nearby

		check_not_a_copy(doc, "Supplier" if doc.doctype == "Purchase Invoice" else "Customer")
		if doc.doctype == "Purchase Invoice":
			_check_bill_no_not_on_a_card_posting(doc)
		warn_card_postings_nearby(doc)
		return
	# FR-156 (#49, #126; C-10, O-15): a CARD credit note draft (origin = "Credit
	# Note") is not a posting unit of its own — its sources (the deductions'
	# cards) are kept on the main Sales Invoice's log; its log has no built
	# signature. The accountant submits the CN as any standard credit note
	# draft; the main built-flow checks below do not apply to it.
	if log.origin == "Credit Note":
		return
	# FR-156: the main Sales Invoice carries non-taxable customer-side deductions
	# the build deferred to a credit note; if the company's mode was flipped to
	# Refuse between build and submit, refuse the submit now (before the SI is
	# written) so `_build_non_taxable_credit_note` (which runs in on_submit)
	# never sees an inconsistent state and the owner's current Refuse rule is
	# honoured.
	_check_credit_note_mode_still_on(doc, log)
	# KSA VAT input: the supplier's own invoice number/date must be on the PI.
	if doc.doctype == "Purchase Invoice" and frappe.db.get_value("Supplier", doc.supplier, "tax_id"):
		if not (doc.get("bill_no") and doc.get("bill_date")):
			frappe.throw(
				_(
					"Enter the supplier's invoice number and date (Bill No / Bill Date) on {0} before submitting; VAT input requires them."
				).format(doc.name)
			)
	# H3: value edits after build and the period gates are re-asserted at submit
	# (the build-time checks guard the build; nothing guarded the gap until now).
	from frappe.utils import get_last_day, getdate

	from card.gl import preflight
	from card.settings import setting

	if not _is_built(log):
		# a linked supplier invoice keeps its own lines; it must still be the invoice that was
		# linked (company, supplier, amount), and the reservation of its sources is re-verified
		from card.gl.integrity import check_linked_invoice

		check_linked_invoice(doc, log)
		_verify_sources(doc, log)
		return
	from card.gl.integrity import check_built_signature

	check_built_signature(doc, log)
	_check_bill_no_unique(doc)
	if doc.company != log.company:
		frappe.throw(
			_("{0} was retargeted to another company; rebuild the posting instead of editing it.").format(
				doc.name
			)
		)
	month_start = getdate("{0}-{1:02d}-01".format(int(log.year), int(log.month)))
	if not (month_start <= getdate(doc.posting_date) <= get_last_day(month_start)):
		frappe.throw(
			_(
				"{0} is dated {1}, outside its posting unit's month {2}/{3}; keep the posting date inside the unit's month."
			).format(doc.name, doc.posting_date, log.month, log.year)
		)
	preflight.check_period_open(log.company, doc.posting_date, doc.doctype)
	expected = flt(sum(flt(row.amount) for row in log.get("sources") or []), 2)
	actual = flt(doc.net_total, 2)
	tolerance = flt(setting("reconciliation_tolerance")) or 0.01
	if abs(actual - expected) > tolerance:
		frappe.throw(
			_(
				"{0} no longer matches its source documents (lines total {1}, sources total {2}); rebuild the posting instead of editing it."
			).format(doc.name, actual, expected)
		)
	_verify_sources(doc, log)


def _check_bill_no_unique(doc):
	"""One supplier invoice number is booked once: a CARD posting may not reuse the
	bill no. of another live invoice of the same supplier."""
	if doc.doctype != "Purchase Invoice" or not doc.get("bill_no"):
		return
	other = frappe.db.get_value(
		"Purchase Invoice",
		{"supplier": doc.supplier, "bill_no": doc.bill_no, "docstatus": ["<", 2], "name": ["!=", doc.name]},
		"name",
	)
	if other:
		frappe.throw(
			_(
				"Supplier invoice no. {0} is already booked on {1}; link that invoice instead of booking it again."
			).format(doc.bill_no, other),
			title=_("Possible duplicate expense"),
		)


def _check_bill_no_not_on_a_card_posting(doc):
	"""A hand-booked invoice may not book the supplier invoice no. a CARD posting already booked."""
	if not doc.get("bill_no"):
		return
	for name in frappe.get_all(
		"Purchase Invoice",
		filters={
			"supplier": doc.supplier,
			"bill_no": doc.bill_no,
			"docstatus": ["<", 2],
			"name": ["!=", doc.name],
		},
		pluck="name",
	):
		if frappe.db.exists(
			"GL Posting Log",
			{
				"posting_doctype": "Purchase Invoice",
				"posting_doc": name,
				"status": ["in", list(ACTIVE_STATES)],
				"origin": ["in", ["Built", "", None]],
			},
		):
			frappe.throw(
				_(
					"Supplier invoice no. {0} is already booked by CARD posting {1}; correct or cancel that posting instead of booking it again."
				).format(doc.bill_no, name),
				title=_("Possible duplicate expense"),
			)


def _verify_sources(doc, log):
	"""Re-verify the reservation at submit time (guards the build->submit gap)."""
	field = _side_field(doc.doctype)
	for doctype, name in _log_sources(log):
		if frappe.db.get_value(doctype, name, "docstatus") != 1:
			frappe.throw(
				_("Source {0} {1} is no longer submitted; rebuild the posting before submitting {2}.").format(
					_(doctype), name, doc.name
				)
			)
		if frappe.get_meta(doctype).has_field(field):
			linked = frappe.db.get_value(doctype, name, field)
			if linked and linked != doc.name:
				frappe.throw(
					_(
						"Source {0} {1} is already invoiced by {2}; rebuild the posting before submitting {3}."
					).format(_(doctype), name, linked, doc.name)
				)
		other = _other_active_holder(doctype, name, log)
		if other:
			frappe.throw(
				_(
					"Source {0} {1} is now included in another active posting unit ({2}); rebuild before submitting {3}."
				).format(_(doctype), name, other, doc.name)
			)


def on_submit(doc, method=None):
	log = _log_for(doc)
	if not log:
		return
	link_sources_on_submit(doc, log)
	# FR-156 (#49, #126; C-10, O-15): after the monthly Sales Invoice is submitted,
	# issue the deferred non-taxable customer-side deductions as a separate draft
	# Sales Invoice with `is_return` = 1 (standard ERPNext credit note). Only on
	# the customer-side main SI of a Built log, and only when the company's option
	# is Credit note. Refuse mode (the default) never reaches here (`_card_lines`
	# refuses the deduction at build).
	if doc.doctype == "Sales Invoice" and _is_built(log) and log.origin != "Credit Note":
		_build_non_taxable_credit_note(doc, log)


def link_sources_on_submit(doc, log):
	"""Write the invoice link and `posted` on every source of the log."""
	field = _side_field(doc.doctype)
	for doctype, name in _log_sources(log):
		if frappe.get_meta(doctype).has_field(field):
			frappe.db.set_value(doctype, name, field, doc.name, update_modified=False)
		frappe.db.set_value(doctype, name, "posted", 1, update_modified=False)
		_point_display(doctype, name, log.name)
	log.db_set("status", "Submitted")
	log.db_set("amount", doc.grand_total)


def before_cancel(doc, method=None):
	"""Free the sources BEFORE frappe's backlink check so the cancel can pass."""
	log = _log_for(doc)
	if not log:
		return
	# FR-156: cancelling the main Sales Invoice is refused while its deferred
	# credit note is active (draft or submitted); the accountant cancels the
	# credit note first, so the pair cancels atomically. Pattern of FR-110
	# (card/gl/journal_link.py): a linked audit record cancels first.
	if doc.doctype == "Sales Invoice" and log.origin != "Credit Note":
		dependent = _active_credit_note_for(log)
		if dependent:
			frappe.throw(
				_(
					"{0} has an active credit note {1} for non-taxable customer-side deductions; cancel or delete that credit note before cancelling this invoice."
				).format(doc.name, dependent)
			)
	field = _side_field(doc.doctype)
	for doctype, name in _log_sources(log):
		if (
			frappe.get_meta(doctype).has_field(field)
			and frappe.db.get_value(doctype, name, field) == doc.name
		):
			frappe.db.set_value(doctype, name, field, "", update_modified=False)
		frappe.db.set_value(
			doctype,
			name,
			"posted",
			1 if _other_side_still_posted(doctype, name, field) else 0,
			update_modified=False,
		)
		if frappe.db.get_value(doctype, name, "gl_posting") == log.name:
			frappe.db.set_value(doctype, name, "gl_posting", "", update_modified=False)
	log.db_set("status", "Cancelled")
	log.db_set("posting_key", None)
	_repoint_freed_sources(log)


def on_trash(doc, method=None):
	"""Deleting a DRAFT posting frees its reserved sources."""
	log = _log_for(doc)
	if not log:
		return
	for doctype, name in _log_sources(log):
		if frappe.db.get_value(doctype, name, "gl_posting") == log.name:
			frappe.db.set_value(doctype, name, "gl_posting", "", update_modified=False)
	log.db_set("status", "Cancelled")
	log.db_set("posting_key", None)
	log.db_set("remarks", _("Posting document deleted; sources freed."))
	_repoint_freed_sources(log)


def _repoint_freed_sources(log):
	"""Sub-rental: the other side's posting may still hold a freed source —
	point the display link back at that active log."""
	for doctype, name in _log_sources(log):
		if not frappe.db.get_value(doctype, name, "gl_posting"):
			other = active_log_holding(doctype, name)
			if other:
				frappe.db.set_value(doctype, name, "gl_posting", other.name, update_modified=False)


def block_source_cancel(doc, method=None):
	"""4a: a source included in any active posting cannot be cancelled (and so
	cannot be amended) until that posting is cancelled or its draft deleted."""
	log = active_log_holding(doc.doctype, doc.name)
	if not log:
		return
	if log.status == "Submitted":
		frappe.throw(
			_("{0} is included in submitted posting {1}; cancel that invoice first.").format(
				doc.name, log.posting_doc
			)
		)
	frappe.throw(
		_("{0} is reserved by draft posting {1}; delete or rebuild that invoice first.").format(
			doc.name, log.posting_doc
		)
	)


# ---- FR-156 (#49, #126; C-10, O-15): non-taxable customer-side deductions ----


def _cn_backlink_tag(main_log_name):
	"""A stable marker that names the main Sales Invoice log of a FR-156 credit note on
	its remarks. Used to find the dependent credit note (idempotency and before_cancel)
	without a new link field (the DocType's remarks field is a Small Text)."""
	return "FR-156 credit note for {0}".format(main_log_name)


def _active_credit_note_for(main_log):
	"""The active (Draft/Submitted) FR-156 credit note log that depends on `main_log`,
	or None. Idempotency and cascade-cancel both use it."""
	tag = _cn_backlink_tag(main_log.name)
	cn = frappe.db.get_value(
		"GL Posting Log",
		{
			"origin": "Credit Note",
			"company": main_log.company,
			"party_type": "Customer",
			"party": main_log.party,
			"month": main_log.month,
			"year": main_log.year,
			"status": ["in", list(ACTIVE_STATES)],
			"remarks": ["like", "{0}%".format(tag)],
		},
		["name", "posting_doc"],
		as_dict=True,
	)
	return cn.posting_doc if cn else None


def _check_credit_note_mode_still_on(doc, log):
	"""FR-156 pre-submit guard for the MAIN Sales Invoice: a build that deferred
	non-taxable customer-side deductions to a credit note needs the company's
	mode to still be Credit note at submit time. If the owner flipped the row
	to Refuse between build and submit, refuse the submit before Frappe writes
	docstatus = 1 so the SI stays Draft and the owner can rebuild under Refuse.
	Only applies to a customer-side built posting with pending deductions."""
	if doc.doctype != "Sales Invoice":
		return
	from card.gl import preflight

	cn_lines, _per_card = _non_taxable_customer_deductions_from_sources(log)
	if not cn_lines:
		return
	if preflight.credit_notes_non_taxable_customer_deduction(log.company):
		return
	frappe.throw(
		_(
			"Sales Invoice {0} was built with non-taxable customer-side deductions deferred to a credit note, but company {1} no longer allows the credit-note route. Cancel this invoice and rebuild the posting."
		).format(doc.name, log.company)
	)


def _non_taxable_customer_deductions_from_sources(log):
	"""Re-derive the non-taxable customer-side deductions the main SI deferred, by
	walking the cards the log reserves. The cards are submitted, so their adjustments
	are immutable; a fresh walk gives the same result that `card/gl/posting._card_lines`
	collected at build. Returns a list of line dictionaries ready for the credit note
	and a per-card sum."""
	from card.gl.posting import card_cost_center

	settings = frappe.get_doc("Card Settings")
	types = {
		t.type_name: t
		for t in (settings.get("adjustment_types") or [])
		if t.company == log.company and not t.disabled
	}
	cn_lines = []
	cn_per_card = {}
	for doctype, name in _log_sources(log):
		if doctype != "Card Monthly Card":
			continue
		card = frappe.get_doc(doctype, name)
		cost_center = card_cost_center(card, card.company)
		for adj in card.get("adjustments") or []:
			if (adj.side or "Supplier") != "Customer":
				continue
			signed = flt(adj.amount, 2) if adj.adjustment_type == "إضافة" else -flt(adj.amount, 2)
			if signed >= 0:
				continue
			typ = types.get(adj.adjustment_type_ref) if adj.adjustment_type_ref else None
			if typ is None or typ.taxable:
				# taxable deduction already on the main SI as a Net Total discount
				continue
			cn_lines.append(
				{
					"card": card.name,
					"project": card.project,
					"cost_center": cost_center,
					"card_equipment": card.equipment,
					"item_code": typ.item,
					"account": typ.account,
					"amount": flt(adj.amount, 2),
					"adjustment_type_ref": adj.adjustment_type_ref,
					"description": "{0} — {1} — {2}".format(typ.type_name, card.name, adj.description or ""),
				}
			)
			cn_per_card[card.name] = flt(cn_per_card.get(card.name, 0) + flt(adj.amount, 2), 2)
	return cn_lines, cn_per_card


def _build_non_taxable_credit_note(doc, log):
	"""FR-156: issue the deferred non-taxable customer-side deductions as a draft
	Sales Invoice with `is_return` = 1 (standard ERPNext credit note). The main SI
	has just been submitted; the CN is left as a Draft for the accountant's review
	(FR-004: CARD never auto-submits). Idempotent via the CN log's remarks tag and
	via a FOR UPDATE row lock on the main log (two parallel submits serialize).

	ZATCA: the main SI carries no negative lines; the deductions are on their own
	credit note. Each CN line keeps the main SI's name as a reference.
	"""
	from card.gl import preflight

	# serialize parallel on_submit of the same main SI (two-connection race, Lesson 4)
	frappe.db.get_value("GL Posting Log", log.name, "name", for_update=True)

	cn_lines, cn_per_card = _non_taxable_customer_deductions_from_sources(log)
	if not cn_lines:
		return None
	# the Refuse-now-after-Credit-note-build case is refused earlier in
	# `before_submit` so the main SI stays Draft; by the time `on_submit` runs,
	# the mode is Credit note. The check is duplicated fail-closed in case a
	# future caller skips before_submit (e.g. a direct submit path).
	if not preflight.credit_notes_non_taxable_customer_deduction(log.company):
		frappe.throw(
			_(
				"Sales Invoice {0} was built with non-taxable customer-side deductions deferred to a credit note, but company {1} no longer allows the credit-note route. Cancel this invoice and rebuild the posting."
			).format(doc.name, log.company)
		)

	# idempotency: a FR-156 credit note log already exists for this main log
	existing = _active_credit_note_for(log)
	if existing:
		return existing

	row = preflight.company_settings_row(log.company)
	tax_template = row.sales_tax_template

	# build the credit note Sales Invoice
	cn = frappe.new_doc("Sales Invoice")
	cn.company = doc.company
	cn.customer = doc.customer
	cn.currency = doc.currency
	cn.conversion_rate = doc.conversion_rate or 1
	cn.set_posting_time = 1
	cn.posting_date = doc.posting_date
	cn.due_date = doc.due_date or doc.posting_date
	cn.debit_to = doc.debit_to
	cn.is_return = 1
	# standalone credit note: `return_against` left empty on purpose. ERPNext
	# validates returned items against the referenced invoice, and the deduction
	# items are not on the main SI (they are deliberately excluded from it);
	# setting `return_against` would then noise-print a "does not exist" message.
	# The link is kept on the log (`origin` = "Credit Note" + remarks tag) and
	# on the CN items' description (the main SI name).
	cn.selling_price_list = doc.selling_price_list
	cn.cost_center = doc.cost_center
	cn.update_stock = 0
	cn.ignore_pricing_rule = 1
	cn.disable_rounded_total = 1
	cn.remarks = _(
		"FR-156: credit note of {0} for non-taxable customer-side deductions (ZATCA: no negative Sales Invoice lines)."
	).format(doc.name)

	for line in cn_lines:
		item = {
			"item_code": line["item_code"],
			"qty": -1,
			"uom": "Nos",
			"conversion_factor": 1,
			"rate": flt(line["amount"], 2),
			"income_account": line["account"],
			"description": "{0} — {1} ({2})".format(
				line["description"], _("credit note of {0}").format(doc.name), _("non-taxable")
			),
			"project": line["project"],
			"cost_center": line["cost_center"] or row.cost_center,
		}
		if line.get("card_equipment"):
			item["card_equipment"] = line["card_equipment"]
		if tax_template and row.get("vat_zero_item_tax_template"):
			# non-taxable deductions carry the zero-rate item tax template, so the CN's
			# tax computation adds no VAT line (same rule as the main SI's non-taxable
			# addition lines)
			item["item_tax_template"] = row.vat_zero_item_tax_template
		cn.append("items", item)

	if tax_template:
		cn.taxes_and_charges = tax_template
		from erpnext.controllers.accounts_controller import get_taxes_and_charges

		for tax_row in get_taxes_and_charges("Sales Taxes and Charges Template", tax_template):
			cn.append("taxes", tax_row)

	cn.flags.card_gl_build = True
	cn.insert(ignore_permissions=True)
	cn.reload()

	# log the credit note (origin = "Credit Note", posting_key derives its own
	# unique digest in GLPostingLog.validate so the DB blocks a duplicate CN)
	cn_log = frappe.get_doc(
		{
			"doctype": "GL Posting Log",
			"company": log.company,
			"party_type": "Customer",
			"party": log.party,
			"month": log.month,
			"year": log.year,
			"posting_type": "Sales Invoice",
			"sequence": 1,
			"status": "Draft",
			"origin": "Credit Note",
			"posting_doctype": "Sales Invoice",
			"posting_doc": cn.name,
			"amount": flt(cn.grand_total, 2),
			# the backlink tag is first on the remarks so `_active_credit_note_for`
			# finds it with a LIKE prefix match
			"remarks": "{0}: {1} ({2}: {3}).".format(
				_cn_backlink_tag(log.name),
				_("non-taxable customer-side deductions deferred by the main Sales Invoice"),
				_("affected cards"),
				", ".join(sorted(cn_per_card)),
			),
		}
	)
	cn_log.flags.card_gl_build = True
	cn_log.insert(ignore_permissions=True)

	# card backlink: an Info Comment on each card names the credit note and the
	# amount, so an operator or an accountant following the card's history sees
	# it (no new field on Card Monthly Card). Standard Frappe audit vehicle.
	for card_name, amount in cn_per_card.items():
		try:
			frappe.get_doc("Card Monthly Card", card_name).add_comment(
				"Info",
				_(
					"FR-156: non-taxable customer-side deductions {0} of this card issued as credit note {1} (parent invoice {2})."
				).format(flt(amount, 2), cn.name, doc.name),
			)
		except Exception:
			# a missing or stale card does not fail the submit of the main SI;
			# the log already backlinks the pair
			pass

	return cn.name
