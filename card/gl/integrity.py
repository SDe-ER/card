# Copyright (c) 2026, SDCE and contributors
# For license information, please see LICENSE
"""P0 posting integrity (2026-10-30 integration audit).

- Built signature: the builder stores a hash of every financially significant
  field of the draft it creates; submit compares the invoice with it, so an
  edited party, account, cost center, project, dimension, item, rate, quantity
  or tax row cannot reach the ledger unnoticed. An Accounts Manager may accept
  a corrected cost center or expense/income account (same company, leaf,
  same root type) with a reason; every other change needs a rebuild.
- Copy guard: an invoice that is not the posting document of an active CARD log
  may not carry the lines of a CARD posting (Desk "Duplicate") nor name a CARD
  source that an active posting already holds.
- Manual-invoice evidence: Purchase Invoices of the same supplier and month
  that CARD did not build, and that book to the CARD accounts or items, must be
  reviewed before CARD builds — linked to the CARD sources they already pay
  for (no second expense), or declared unrelated by an accountant.
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES

# the CARD source document names (autoname formats of the three source DocTypes; amendments add -N)
SOURCE_NAME_RE = re.compile(r"\b(EOMC-\d{4}-\d{2}-\d+(?:-\d+)?|DSL-\d+(?:-\d+)?|TRN-\d+(?:-\d+)?)\b")
SOURCE_DOCTYPE_BY_PREFIX = {
	"EOMC-": "Card Monthly Card",
	"DSL-": "Project Diesel Fill",
	"TRN-": "Equipment Transport",
}
# the party field of each source on the supplier side
SUPPLIER_FIELD = {
	"Card Monthly Card": "supplier",
	"Project Diesel Fill": "supplier",
	"Equipment Transport": "transport_supplier",
}
# an Accounts Manager may accept these line corrections; anything else needs a rebuild
CORRECTABLE_LINE_FIELDS = ("cost_center", "account")
ACCEPT_ROLES = {"Accounts Manager", "System Manager"}
REVIEW_ROLES = {"Accounts Manager", "Accounts User", "System Manager"}
# FR-194: the customer link is narrower than the supplier review roles (owner rule)
CUSTOMER_LINK_ROLES = {"Accounts Manager", "System Manager"}
# The posting builder's version, stored as "builder" in the log's built_snapshot JSON (never in the signature hash).
# 1 (absent) = before D1: a project-tank diesel fill was split per equipment by operating hours.
# 2 = D1 (PR #163): a project-tank diesel fill posts as ONE project-level line.
BUILDER_VERSION = 2


def _hash(payload):
	return hashlib.sha256(
		json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
	).hexdigest()


def _line(item, doctype):
	account = item.get("expense_account") if doctype == "Purchase Invoice" else item.get("income_account")
	return {
		"item_code": item.get("item_code") or "",
		"qty": flt(item.get("qty"), 6),
		"rate": flt(item.get("rate"), 2),
		"account": account or "",
		"project": item.get("project") or "",
		"cost_center": item.get("cost_center") or "",
		"card_equipment": item.get("card_equipment") or "",
		"item_tax_template": item.get("item_tax_template") or "",
		"description": (item.get("description") or "").strip(),
	}


def snapshot(doc):
	"""The financially significant fields of a posting document, in a stable shape."""
	party_field = "supplier" if doc.doctype == "Purchase Invoice" else "customer"
	party_account = "credit_to" if doc.doctype == "Purchase Invoice" else "debit_to"
	return {
		"header": {
			"doctype": doc.doctype,
			"company": doc.get("company") or "",
			"party": doc.get(party_field) or "",
			"party_account": doc.get(party_account) or "",
			"currency": doc.get("currency") or "",
			"conversion_rate": flt(doc.get("conversion_rate"), 9),
			"taxes_and_charges": doc.get("taxes_and_charges") or "",
			"apply_discount_on": doc.get("apply_discount_on") or "",
			"discount_amount": flt(doc.get("discount_amount"), 2),
			"additional_discount_percentage": flt(doc.get("additional_discount_percentage"), 6),
			"is_return": int(doc.get("is_return") or 0),
		},
		"lines": [_line(i, doc.doctype) for i in doc.get("items") or []],
		"taxes": [
			{
				"charge_type": t.get("charge_type") or "",
				"account_head": t.get("account_head") or "",
				"rate": flt(t.get("rate"), 6),
				"included_in_print_rate": int(t.get("included_in_print_rate") or 0),
				"add_deduct_tax": t.get("add_deduct_tax") or "",
				"category": t.get("category") or "",
			}
			for t in doc.get("taxes") or []
		],
	}


def lines_signature(snap):
	"""Signature of the item lines alone: a Desk copy of a CARD posting keeps it."""
	return _hash(snap["lines"])


def full_signature(snap):
	return _hash(snap)


def _item_tax_rates(value):
	"""A line's item_tax_rate (the JSON ERPNext recalculates from the item tax template on every validate)."""
	try:
		rates = frappe.parse_json(value) if value else {}
	except Exception:
		return {"invalid": str(value)}
	if not isinstance(rates, dict):
		return {"invalid": str(value)}
	return {str(k): flt(v, 6) for k, v in sorted(rates.items())}


def vat_snapshot(doc):
	"""FR-127: the VAT CARD built — each line's tax rates and the invoice's total taxes. Kept beside the
	snapshot (not in the signature), so drafts built before it are compared exactly as before."""
	return {
		"line_tax_rates": [_item_tax_rates(i.get("item_tax_rate")) for i in doc.get("items") or []],
		"total_taxes_and_charges": flt(doc.get("total_taxes_and_charges"), 2),
	}


def stored_snapshot(snap, vat=None):
	"""The JSON kept in the log's built_snapshot: the snapshot plus the builder version (and, FR-127, the built
	VAT). They stay out of the signature, so a draft is compared on its content only."""
	payload = {**snap, "builder": BUILDER_VERSION}
	if vat is not None:
		payload["vat"] = vat
	return frappe.as_json(payload)


def check_built_vat(doc, built):
	"""FR-127: the VAT of a built draft must still be the VAT CARD built (ERPNext recalculates the line tax
	rates from the item tax template on every save). Only a snapshot that recorded the VAT is compared."""
	if "vat" not in (built or {}):
		return
	current = vat_snapshot(doc)
	if current != built["vat"]:
		frappe.throw(
			_(
				"{0}: its VAT changed since CARD built it (total taxes {1} → {2}). Rebuild the posting from CARD."
			).format(
				doc.name, built["vat"].get("total_taxes_and_charges"), current["total_taxes_and_charges"]
			),
			title=_("CARD posting changed"),
		)


def builder_version(built):
	"""The builder version of a stored snapshot; 1 for a snapshot written before versions were recorded."""
	try:
		return int((built or {}).get("builder") or 1)
	except (AttributeError, TypeError, ValueError):
		return 1


def check_builder_version(doc, log, built):
	"""D1 (Owner decision 2026-11-10, enforce): a draft built before D1 split each project-tank diesel fill per
	equipment by operating hours, an estimate that must not reach the ledger. Such a draft is refused on submit;
	a draft of an old builder without a project-tank fill is unaffected by D1 and passes."""
	if builder_version(built) >= BUILDER_VERSION:
		return
	fills = frappe.get_all(
		"GL Posting Source",
		filters={"parent": log.name, "parenttype": "GL Posting Log", "source_doctype": "Project Diesel Fill"},
		pluck="source_name",
	)
	tank = (
		frappe.get_all(
			"Project Diesel Fill",
			filters={"name": ["in", fills], "card_equipment": ["is", "not set"]},
			pluck="name",
			order_by="name asc",
		)
		if fills
		else []
	)
	if tank:
		frappe.throw(
			_(
				"{0} was built before project-tank diesel fills post as one project-level line: it splits {1} per equipment by operating hours, an estimate. Rebuild the posting from CARD before submitting it."
			).format(doc.name, ", ".join(tank)),
			title=_("CARD posting must be rebuilt"),
		)


def describe_differences(built, current):
	"""Human-readable list of what changed between two snapshots."""
	diffs = []
	for key, value in built["header"].items():
		if current["header"].get(key) != value:
			diffs.append(_("{0}: {1} → {2}").format(key, value, current["header"].get(key)))
	if len(built["lines"]) != len(current["lines"]):
		diffs.append(_("line count: {0} → {1}").format(len(built["lines"]), len(current["lines"])))
	else:
		for idx, (a, b) in enumerate(zip(built["lines"], current["lines"], strict=False), start=1):
			for key, value in a.items():
				if b.get(key) != value:
					diffs.append(_("line {0} {1}: {2} → {3}").format(idx, key, value, b.get(key)))
	if built["taxes"] != current["taxes"]:
		diffs.append(_("tax rows changed"))
	return diffs


def correctable_only(built, current):
	"""True when the snapshots differ only in correctable line fields."""
	if built["header"] != current["header"] or built["taxes"] != current["taxes"]:
		return False
	if len(built["lines"]) != len(current["lines"]):
		return False
	for a, b in zip(built["lines"], current["lines"], strict=False):
		for key, value in a.items():
			if key not in CORRECTABLE_LINE_FIELDS and b.get(key) != value:
				return False
	return True


def validate_correction(doc, built, current):
	"""Accepted corrections must stay valid for the company: leaf, enabled, same
	company, and an account keeps the root type of the account CARD chose."""
	for a, b in zip(built["lines"], current["lines"], strict=False):
		if b["cost_center"] != a["cost_center"]:
			cc = frappe.db.get_value(
				"Cost Center", b["cost_center"], ["company", "is_group", "disabled"], as_dict=True
			)
			if not cc or cc.company != doc.company or cc.is_group or cc.disabled:
				frappe.throw(
					_("Cost center {0} is not an enabled leaf cost center of {1}.").format(
						b["cost_center"], doc.company
					)
				)
		if b["account"] != a["account"]:
			new = frappe.db.get_value(
				"Account", b["account"], ["company", "is_group", "disabled", "root_type"], as_dict=True
			)
			old_root = frappe.db.get_value("Account", a["account"], "root_type")
			if (
				not new
				or new.company != doc.company
				or new.is_group
				or new.disabled
				or new.root_type != old_root
			):
				frappe.throw(
					_("Account {0} must be an enabled leaf {1} account of {2}.").format(
						b["account"], old_root, doc.company
					)
				)


def check_built_signature(doc, log):
	"""Submit gate for a BUILT posting: the invoice must still be what CARD built,
	or a correction an Accounts Manager accepted for exactly this content."""
	if not log.get("built_signature"):
		frappe.throw(
			_(
				"{0} was built before CARD recorded invoice signatures; rebuild the posting from CARD before submitting it."
			).format(doc.name)
		)
	built = json.loads(log.built_snapshot)
	# before the signature match: an accepted correction of an old draft does not bypass it
	check_builder_version(doc, log, built)
	current = snapshot(doc)
	signature = full_signature(current)
	if signature in (log.built_signature, log.get("accepted_signature")):
		# FR-127: the content matches, but ERPNext may have recalculated the line VAT from a changed item tax
		# template; an accepted correction never covers a VAT change either
		check_built_vat(doc, built)
		return
	diffs = describe_differences(built, current)
	hint = (
		_(
			"An Accounts Manager can accept this cost center/account correction from the invoice (card.gl.integrity.accept_correction)."
		)
		if correctable_only(built, current)
		else _("Rebuild the posting from CARD (fix the source documents first).")
	)
	frappe.throw(
		_("{0} differs from what CARD built: {1}. {2}").format(doc.name, "; ".join(diffs[:12]), hint),
		title=_("CARD posting changed"),
	)


@frappe.whitelist(methods=["POST"])
def accept_correction(invoice_doctype: str, invoice: str, reason: str):
	"""An Accounts Manager accepts a corrected cost center / account on a CARD
	draft. Only those fields may differ; the acceptance is tied to the exact
	invoice content (any later edit needs a new acceptance)."""
	if invoice_doctype not in ("Purchase Invoice", "Sales Invoice"):
		frappe.throw(_("Only CARD Purchase or Sales Invoices can be corrected."))
	if not ACCEPT_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only an Accounts Manager may accept a CARD posting correction."), frappe.PermissionError
		)
	if not (reason or "").strip():
		frappe.throw(_("Give the reason for the correction."))
	doc = frappe.get_doc(invoice_doctype, invoice)
	doc.check_permission("write")
	from card.gl.posting import POSTING_SOURCE_DOCTYPES
	from card.report_access import permitted_companies

	if doc.company not in permitted_companies(*POSTING_SOURCE_DOCTYPES, invoice_doctype, "GL Posting Log"):
		frappe.throw(
			_("You are not permitted to correct CARD postings of company {0}.").format(doc.company),
			frappe.PermissionError,
		)
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft can be corrected."))
	from card.gl.events import _log_for

	log = _log_for(doc)
	if not log or log.get("origin") == "Linked" or not log.get("built_snapshot"):
		frappe.throw(_("{0} is not a CARD-built posting.").format(invoice))
	built = json.loads(log.built_snapshot)
	current = snapshot(doc)
	if not correctable_only(built, current):
		frappe.throw(
			_("Only cost center and account changes can be accepted; {0}.").format(
				"; ".join(describe_differences(built, current)[:12])
			)
		)
	validate_correction(doc, built, current)
	log.db_set("accepted_signature", full_signature(current))
	log.db_set("accepted_by", frappe.session.user)
	log.db_set("correction_reason", reason.strip())
	return log.name


# ---------- copy guard ----------


def source_names_in(doc):
	names = set()
	for item in doc.get("items") or []:
		names.update(SOURCE_NAME_RE.findall(item.get("description") or ""))
	return names


def _doctype_of(source_name):
	for prefix, doctype in SOURCE_DOCTYPE_BY_PREFIX.items():
		if source_name.startswith(prefix):
			return doctype
	return None


def check_not_a_copy(doc, side):
	"""A Purchase/Sales Invoice that is not an active CARD posting itself must not
	repeat a CARD posting's lines nor name a source an active posting holds."""
	snap_lines = lines_signature(snapshot(doc))
	twin = frappe.db.get_value(
		"GL Posting Log",
		{
			"lines_signature": snap_lines,
			"status": ["in", list(ACTIVE_STATES)],
			"posting_doc": ["!=", doc.name],
			"posting_doctype": doc.doctype,
		},
		"posting_doc",
	)
	if twin:
		frappe.throw(
			_("{0} repeats the lines of CARD posting {1}; the same sources would be booked twice.").format(
				doc.name or _("This invoice"), twin
			),
			title=_("Duplicate CARD posting"),
		)
	from card.gl.events import active_log_holding

	for name in sorted(source_names_in(doc)):
		doctype = _doctype_of(name)
		if not doctype or not frappe.db.exists(doctype, name):
			continue
		holder = active_log_holding(doctype, name, side)
		if holder and holder.posting_doc != doc.name:
			frappe.throw(
				_(
					"{0} names {1} {2}, already booked by {3}; the same operation would be booked twice."
				).format(doc.name or _("This invoice"), _(doctype), name, holder.posting_doc),
				title=_("Duplicate CARD posting"),
			)


# ---------- manual-invoice evidence ----------

# A supplier invoice can cover operations of the month while it is dated before or after it (a fuel invoice
# covering 24/09–06/10 dated 06/10; a rental invoice for May–June dated 05/07). The evidence window around a
# CARD month therefore reaches back one month and forward two.
EVIDENCE_DAYS_BEFORE = 31
EVIDENCE_DAYS_AFTER = 62


def evidence_window(first_day, last_day):
	from frappe.utils import add_days

	return add_days(first_day, -EVIDENCE_DAYS_BEFORE), add_days(last_day, EVIDENCE_DAYS_AFTER)


def manual_invoice_candidates(company, supplier, first_day, last_day, accounts, items):
	"""Purchase Invoices (draft or submitted, not returns) of the supplier that CARD
	did not build, dated (posting or bill date) in the evidence window of the month,
	with at least one line on an Expense account, a CARD account or a CARD item —
	possible evidence that the operations are already booked. Lines without an
	item code count by their account. Returns, stock and asset purchases are not
	evidence; an invoice already linked to CARD sources is reported as handled."""
	start, end = evidence_window(first_day, last_day)
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={"company": company, "supplier": supplier, "docstatus": ["<", 2], "is_return": 0},
		or_filters={
			"posting_date": ["between", [start, end]],
			"bill_date": ["between", [start, end]],
		},
		fields=["name", "docstatus", "bill_no", "bill_date", "posting_date", "net_total", "grand_total"],
	)
	if not invoices:
		return []
	names = [inv.name for inv in invoices]
	logs = {
		r.posting_doc: r
		for r in frappe.get_all(
			"GL Posting Log",
			filters={
				"posting_doctype": "Purchase Invoice",
				"posting_doc": ["in", names],
				"status": ["in", list(ACTIVE_STATES)],
			},
			fields=["name", "origin", "posting_doc"],
		)
	}
	lines = frappe.get_all(
		"Purchase Invoice Item",
		filters={"parent": ["in", names], "parenttype": "Purchase Invoice"},
		fields=["parent", "expense_account", "item_code"],
	)
	expense_accounts = set(
		frappe.get_all(
			"Account",
			filters={
				"name": ["in", list({ln.expense_account for ln in lines if ln.expense_account})],
				"root_type": "Expense",
			},
			pluck="name",
		)
	)
	hits = {
		ln.parent
		for ln in lines
		if ln.expense_account in accounts
		or ln.expense_account in expense_accounts
		or (ln.item_code and ln.item_code in items)
	}
	out = []
	for inv in invoices:
		log = logs.get(inv.name)
		if log and (log.origin or "Built") == "Built":
			continue  # CARD's own posting
		if inv.name in hits:
			inv["linked_log"] = log.name if log else None
			out.append(inv)
	return out


def require_reviewed(candidates, reviewed):
	"""Refuse to build while a candidate manual invoice is neither linked to CARD
	sources nor declared unrelated by an accountant for this build. Invoice names
	are shown only to a user who may read them."""
	pending = [c for c in candidates if not c.linked_log and c.name not in reviewed]
	if pending:
		readable = [c for c in pending if frappe.has_permission("Purchase Invoice", "read", c.name)]
		listed = ", ".join(
			"{0} ({1}{2})".format(
				c.name, c.bill_no or _("no bill no."), _(", draft") if c.docstatus == 0 else ""
			)
			for c in readable
		)
		hidden = len(pending) - len(readable)
		if hidden:
			parts = [listed] if listed else []
			parts.append(_("{0} invoice(s) you cannot open").format(hidden))
			listed = ", ".join(parts)
		frappe.throw(
			_(
				"Supplier invoices booked around this month may cover the same operations: {0}. Link each one to the CARD sources it pays for (card.gl.integrity.link_supplier_invoice), or have an accountant confirm it is unrelated, then build again."
			).format(listed),
			title=_("Possible duplicate expense"),
		)
	if reviewed:
		if not REVIEW_ROLES & set(frappe.get_roles()):
			frappe.throw(
				_("Only an accountant may declare supplier invoices unrelated."), frappe.PermissionError
			)
		unknown = set(reviewed) - {c.name for c in candidates}
		if unknown:
			frappe.throw(
				_("Not a candidate invoice for this supplier and month: {0}").format(
					", ".join(sorted(unknown))
				)
			)
		for name in reviewed:
			frappe.has_permission("Purchase Invoice", "read", name, throw=True)


def lock_sources(sources):
	"""Row-lock every source in a stable order, so a concurrent build or link of
	the same documents waits and then sees the first one's reservation."""
	for doctype, name in sorted((dt, n) for dt, rows in sources.items() for n, _amount in rows):
		frappe.db.get_value(doctype, name, "name", for_update=True)


def _source_net_amount(doctype, src, row, vat_rate, invoice_has_vat):
	"""The amount of one CARD source on the VAT-exclusive basis of the supplier invoice
	it is linked to, or None when that basis cannot be verified. Cards and transports
	carry net amounts; a diesel fill carries litres × price, whose VAT basis is the
	company's Diesel price VAT basis. Without VAT on the invoice every amount is its own total."""
	if doctype == "Card Monthly Card":
		return flt(src.net_amount, 2)
	amount = flt(src.amount, 2)
	if doctype == "Equipment Transport" or not invoice_has_vat:
		return amount
	basis = row.get("diesel_price_vat_basis") if row else None
	if basis == "Exclusive":
		return amount
	if basis == "Inclusive" and vat_rate:
		return flt(amount * 100 / (100 + vat_rate), 2)
	return None


@frappe.whitelist(methods=["POST"])
def link_supplier_invoice(
	invoice: str, sources: str | list, reason: str | None = None, accept_difference: int | str = 0
):
	"""Record that an existing supplier Purchase Invoice (booked by hand) already
	pays for these CARD sources. Nothing is reposted and the invoice is not
	changed: a Linked GL Posting Log reserves the sources so CARD never builds them
	again, and the sources show the invoice once it is submitted.

	Authorization: an accountant role, the company within the caller's CARD and
	accounting scope, read on the supplier and every source, and submit right on
	the invoice (the right to make it a ledger document).

	Evidence: the sources are compared with the invoice's net total on one basis
	(cards and transports net; fills by the Diesel price VAT basis); a gap, or a
	basis that cannot be verified, is refused unless an accountant accepts it with a
	reason, and it is then stored on the log as an open difference, never shown as
	matched. An imported diesel session that carries its supplier invoice no. links
	only to the invoice with that bill no. Sources may span several months (an
	invoice covering 24/09–06/10)."""
	from card.gl.events import active_log_holding, link_sources_on_submit
	from card.gl.posting import POSTING_SOURCE_DOCTYPES
	from card.report_access import permitted_companies
	from card.settings import setting

	if not REVIEW_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only an accountant may link supplier invoices to CARD sources."), frappe.PermissionError
		)
	if isinstance(sources, str):
		sources = json.loads(sources)
	inv = frappe.get_doc("Purchase Invoice", invoice)
	inv.check_permission("read")
	if inv.company not in permitted_companies(*POSTING_SOURCE_DOCTYPES, "Purchase Invoice", "GL Posting Log"):
		frappe.throw(
			_("You are not permitted to link invoices for company {0}.").format(inv.company),
			frappe.PermissionError,
		)
	frappe.has_permission("Purchase Invoice", "submit", inv, throw=True)
	frappe.has_permission("Supplier", "read", inv.supplier, throw=True)
	if inv.docstatus == 2 or inv.is_return:
		frappe.throw(_("{0} is cancelled or a return; link the valid supplier invoice.").format(invoice))
	built = frappe.db.get_value(
		"GL Posting Log",
		{
			"posting_doctype": "Purchase Invoice",
			"posting_doc": invoice,
			"status": ["in", list(ACTIVE_STATES)],
		},
		["name", "origin"],
		as_dict=True,
	)
	if built:
		frappe.throw(_("{0} is already a CARD posting or linked ({1}).").format(invoice, built.name))
	if not sources:
		frappe.throw(_("Choose the CARD sources this invoice pays for."))
	rows = {"Card Monthly Card": [], "Project Diesel Fill": [], "Equipment Transport": []}
	for src in sources:
		doctype, name = src.get("doctype"), src.get("name")
		if doctype not in rows:
			frappe.throw(_("{0} is not a CARD source type.").format(doctype))
		if any(n == name for n, _a in rows[doctype]):
			frappe.throw(_("{0} {1} is listed twice.").format(_(doctype), name))
		rows[doctype].append((name, 0))
	lock_sources(rows)
	settings_row = next(
		(
			r
			for r in frappe.get_cached_doc("Card Settings").get("company_settings") or []
			if r.company == inv.company
		),
		None,
	)
	invoice_has_vat = flt(inv.total_taxes_and_charges, 2) != 0
	vat_rate = 0
	if invoice_has_vat and settings_row and settings_row.get("purchase_tax_template"):
		from card.gl.posting import _vat_rate

		vat_rate = _vat_rate(settings_row)
	unverified = []
	for doctype, items in rows.items():
		for i, (name, _amount) in enumerate(items):
			src = frappe.get_doc(doctype, name)
			src.check_permission("read")
			if src.docstatus != 1:
				frappe.throw(_("{0} {1} is not submitted.").format(_(doctype), name))
			if src.company != inv.company or src.get(SUPPLIER_FIELD[doctype]) != inv.supplier:
				frappe.throw(
					_("{0} {1} belongs to another company or supplier than {2}.").format(
						_(doctype), name, invoice
					)
				)
			if src.get("purchase_invoice"):
				frappe.throw(
					_("{0} {1} is already invoiced by {2}.").format(_(doctype), name, src.purchase_invoice)
				)
			if doctype == "Equipment Transport" and (src.get("responsibility") or src.get("payer")):
				# P1-2: the supplier invoicing of transports with a recorded payer waits for the
				# accountant's and tax adviser's decisions (built and linked by neither path yet)
				frappe.throw(
					_(
						"Transport {0} records who pays and who bears its cost; linking it to a supplier invoice is not enabled yet."
					).format(name)
				)
			holder = active_log_holding(doctype, name, "Supplier")
			if holder:
				frappe.throw(
					_("{0} {1} is already held by {2}.").format(_(doctype), name, holder.posting_doc)
				)
			invoice_no = src.get("supplier_invoice_no") if doctype == "Project Diesel Fill" else None
			if invoice_no and (invoice_no or "").strip() != (inv.bill_no or "").strip():
				frappe.throw(
					_("{0} {1} was recorded on supplier invoice no. {2}, not on {3} (bill no. {4}).").format(
						_(doctype), name, invoice_no, invoice, inv.bill_no or "-"
					)
				)
			net = _source_net_amount(doctype, src, settings_row, vat_rate, invoice_has_vat)
			if net is None:
				unverified.append(name)
				net = flt(src.amount, 2)
			items[i] = (name, net)
	posting_day = getdate(inv.bill_date or inv.posting_date)
	sources_net = flt(sum(a for items in rows.values() for _n, a in items), 2)
	# per-line rounding of VAT-inclusive fills: up to one halala per fill
	tolerance = (flt(setting("reconciliation_tolerance")) or 0.01) + 0.01 * len(rows["Project Diesel Fill"])
	difference = flt(flt(inv.net_total, 2) - sources_net, 2)
	if abs(difference) <= tolerance and not unverified:
		difference = 0
	accepted = frappe.utils.cint(accept_difference) and (reason or "").strip()
	if (difference or unverified) and not accepted:
		problem = (
			_("the VAT basis of fills {0} is not verified (Card Settings: Diesel price VAT basis)").format(
				", ".join(unverified)
			)
			if unverified
			else _("the CARD sources total {0} net, {1} is net {2}").format(
				sources_net, invoice, flt(inv.net_total, 2)
			)
		)
		frappe.throw(
			_(
				"Cannot confirm the link: {0}. Link only the sources this invoice pays for, or accept the difference {1} with a reason."
			).format(problem, difference),
			title=_("Linked amounts differ"),
		)
	log = frappe.get_doc(
		{
			"doctype": "GL Posting Log",
			"origin": "Linked",
			"company": inv.company,
			"party_type": "Supplier",
			"party": inv.supplier,
			"month": "%02d" % posting_day.month,
			"year": posting_day.year,
			"posting_type": "Purchase Invoice",
			"sequence": 1,
			"status": "Submitted" if inv.docstatus == 1 else "Draft",
			"posting_doctype": "Purchase Invoice",
			"posting_doc": inv.name,
			"amount": flt(inv.grand_total, 2),
			"link_difference": flt(flt(inv.net_total, 2) - sources_net, 2)
			if (difference or unverified)
			else 0,
			"remarks": _(
				"Linked by {0}: supplier invoice {1} (bill no. {2}) net {3} / total {4}, CARD sources net {5}, {6}. {7}"
			).format(
				frappe.session.user,
				inv.name,
				inv.bill_no or "-",
				flt(inv.net_total, 2),
				flt(inv.grand_total, 2),
				sources_net,
				_("open difference {0} accepted").format(flt(flt(inv.net_total, 2) - sources_net, 2))
				if (difference or unverified)
				else _("matched"),
				reason or "",
			),
		}
	)
	for doctype, items in rows.items():
		for name, amount in items:
			log.append("sources", {"source_doctype": doctype, "source_name": name, "amount": amount})
	log.flags.card_gl_build = True
	log.insert(ignore_permissions=True)  # the audit record; the gate above is the authorization
	if inv.docstatus == 1:
		link_sources_on_submit(inv, log)
	return log.name


def check_linked_invoice(doc, log):
	"""Submit gate for a linked hand-booked invoice that was linked as a draft: it must
	still be the invoice of the link — same company and supplier, not a return, and its
	net total equal to the linked sources plus the accepted open difference."""
	from card.settings import setting

	if doc.company != log.company or doc.get("supplier") != log.party or doc.get("is_return"):
		frappe.throw(
			_(
				"{0} changed company or supplier after it was linked to CARD sources; delete the link by deleting or cancelling the invoice and link again."
			).format(doc.name),
			title=_("Linked invoice changed"),
		)
	sources = log.get("sources") or []
	expected = flt(sum(flt(r.amount) for r in sources) + flt(log.get("link_difference")), 2)
	fills = sum(1 for r in sources if r.source_doctype == "Project Diesel Fill")
	tolerance = (flt(setting("reconciliation_tolerance")) or 0.01) + 0.01 * fills
	if abs(flt(doc.net_total, 2) - expected) > tolerance:
		frappe.throw(
			_(
				"{0} is net {1}, but it was linked to CARD sources for net {2}; delete or cancel it and link again."
			).format(doc.name, flt(doc.net_total, 2), expected),
			title=_("Linked invoice changed"),
		)


# ---------- customer side: a hand-booked Sales Invoice and its monthly cards (FR-194) ----------

CARD_DOCTYPE = "Card Monthly Card"
CANDIDATE_PAGE_LENGTH = 50
CANDIDATE_PAGE_MAX = 200


def _require_customer_link_role():
	if not CUSTOMER_LINK_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only an Accounts Manager or a System Manager may link customer invoices to CARD cards."),
			frappe.PermissionError,
		)


def _customer_link_companies():
	from card.gl.posting import POSTING_SOURCE_DOCTYPES
	from card.report_access import permitted_companies

	return permitted_companies(*POSTING_SOURCE_DOCTYPES, "Sales Invoice", "GL Posting Log")


def _card_names(cards):
	"""The card names of a request: a list, a JSON list, or one name."""
	if isinstance(cards, str):
		text = cards.strip()
		cards = json.loads(text) if text.startswith("[") else ([text] if text else [])
	names = []
	for entry in cards or []:
		name = entry.get("name") if isinstance(entry, dict) else entry
		if not name or not isinstance(name, str):
			frappe.throw(_("Choose the monthly cards this invoice bills."))
		if name in names:
			frappe.throw(_("{0} {1} is listed twice.").format(_(CARD_DOCTYPE), name))
		names.append(name)
	if not names:
		frappe.throw(_("Choose the monthly cards this invoice bills."))
	return names


def _invoice_projects(inv):
	"""The projects of a Sales Invoice: its header project and the projects of its lines (CARD's own customer
	posting writes the card's project on every line and none on the header)."""
	return {p for p in [inv.get("project"), *(i.get("project") for i in inv.get("items") or [])] if p}


@frappe.whitelist(methods=["POST"])
def link_customer_invoice(invoice: str, cards: str | list, reason: str | None = None):
	"""FR-194: record that a submitted Sales Invoice, booked by hand in ERPNext, already bills these customer
	monthly cards. The customer mirror of ``link_supplier_invoice``: a Linked GL Posting Log holds the cards, so
	CARD never builds them again, and each card gets its customer invoice link. Nothing is posted; the invoice,
	the card amounts and the ledger are not changed.

	Authorization: Accounts Manager or System Manager; the company within the caller's CARD and accounting
	scope; read on the invoice, the customer and every card; the submit right on Sales Invoice.

	Evidence: every card is a submitted, approved customer-billing card of the invoice's company, customer and
	project, without a customer invoice; the invoice net total (company currency, before VAT) equals the sum
	of the cards' customer net amounts within the reconciliation tolerance. A difference is always refused."""
	from frappe.utils import cstr, escape_html, now_datetime, strip_html_tags

	from card.constants import CUSTOMER_BILLING_DIRECTIONS, DIR_RENTED_OUT
	from card.gl.events import active_log_holding, link_sources_on_submit
	from card.open_month import STATE_OPEN_MONTH
	from card.settings import setting

	_require_customer_link_role()
	reason = strip_html_tags(cstr(reason)).strip()
	if not reason:
		frappe.throw(_("Give the reason for linking this invoice to the cards."))
	names = _card_names(cards)
	inv = frappe.get_doc("Sales Invoice", invoice)
	inv.check_permission("read")
	if inv.company not in _customer_link_companies():
		frappe.throw(
			_("You are not permitted to link invoices for company {0}.").format(inv.company),
			frappe.PermissionError,
		)
	frappe.has_permission("Sales Invoice", "submit", inv, throw=True)
	frappe.has_permission("Customer", "read", inv.customer, throw=True)
	if inv.docstatus != 1:
		frappe.throw(_("{0} is not submitted; link a submitted Sales Invoice.").format(invoice))
	if inv.get("is_return"):
		frappe.throw(_("{0} is a return (credit note); link the Sales Invoice itself.").format(invoice))
	if inv.get("is_debit_note"):
		frappe.throw(_("{0} is a debit note; link the Sales Invoice itself.").format(invoice))
	if inv.get("is_opening") == "Yes":
		frappe.throw(_("{0} is an opening invoice; it does not bill monthly cards.").format(invoice))
	existing = frappe.db.get_value(
		"GL Posting Log",
		{"posting_doctype": "Sales Invoice", "posting_doc": invoice, "status": ["in", list(ACTIVE_STATES)]},
		"name",
	)
	if existing:
		frappe.throw(_("{0} is already a CARD posting or linked ({1}).").format(invoice, existing))
	rows = {CARD_DOCTYPE: [(name, 0) for name in names]}
	lock_sources(rows)
	projects = _invoice_projects(inv)
	docs = []
	for i, name in enumerate(names):
		card = frappe.get_doc(CARD_DOCTYPE, name)
		card.check_permission("read")
		if card.docstatus != 1:
			frappe.throw(_("{0} {1} is not submitted.").format(_(CARD_DOCTYPE), name))
		if card.get("workflow_state") == STATE_OPEN_MONTH:
			frappe.throw(_("Card {0} is not approved: its month has not ended.").format(name))
		if card.card_direction not in CUSTOMER_BILLING_DIRECTIONS:
			frappe.throw(_("Card {0} is not billed to a customer.").format(name))
		if card.company != inv.company:
			frappe.throw(_("Card {0} belongs to another company than {1}.").format(name, invoice))
		if not card.customer or card.customer != inv.customer:
			frappe.throw(_("Card {0} belongs to another customer than {1}.").format(name, invoice))
		if not card.project or card.project not in projects:
			frappe.throw(
				_(
					"Card {0} is of project {1}, which is not a project of {2} (its header or its lines)."
				).format(name, card.project or "-", invoice)
			)
		if card.get("sales_invoice"):
			frappe.throw(_("Card {0} is already invoiced by {1}.").format(name, card.sales_invoice))
		holder = active_log_holding(CARD_DOCTYPE, name, "Customer")
		if holder:
			frappe.throw(_("Card {0} is already held by {1}.").format(name, holder.posting_doc))
		if card.card_direction == DIR_RENTED_OUT and frappe.utils.cint(card.get("posted")):
			# a rented-out card has the customer side only: the flag says that side is posted
			frappe.throw(
				_("Card {0} is marked posted without an invoice link; review it before linking.").format(name)
			)
		rows[CARD_DOCTYPE][i] = (name, flt(card.customer_net_amount, 2))
		docs.append(card)
	cards_net = flt(sum(amount for _name, amount in rows[CARD_DOCTYPE]), 2)
	invoice_net = flt(inv.base_net_total, 2)
	tolerance = flt(setting("reconciliation_tolerance")) or 0.01
	if abs(flt(invoice_net - cards_net, 2)) > tolerance:
		frappe.throw(
			_(
				"Cannot link: the cards total {0} net, {1} is net {2} (before VAT). Link exactly the cards this invoice bills."
			).format(cards_net, invoice, invoice_net),
			title=_("Linked amounts differ"),
		)
	posting_day = getdate(inv.posting_date)
	log = frappe.get_doc(
		{
			"doctype": "GL Posting Log",
			"origin": "Linked",
			"company": inv.company,
			"party_type": "Customer",
			"party": inv.customer,
			"month": "%02d" % posting_day.month,
			"year": posting_day.year,
			"posting_type": "Sales Invoice",
			"sequence": 1,
			"status": "Submitted",
			"posting_doctype": "Sales Invoice",
			"posting_doc": inv.name,
			"amount": flt(inv.grand_total, 2),
			"link_difference": 0,
			"remarks": _(
				"Linked by {0}: sales invoice {1} net {2} / total {3}, CARD cards net {4}, matched. {5}"
			).format(frappe.session.user, inv.name, invoice_net, flt(inv.grand_total, 2), cards_net, reason),
		}
	)
	for name, amount in rows[CARD_DOCTYPE]:
		log.append("sources", {"source_doctype": CARD_DOCTYPE, "source_name": name, "amount": amount})
	log.flags.card_gl_build = True
	log.insert(ignore_permissions=True)  # the audit record; the gate above is the authorization
	link_sources_on_submit(inv, log)
	who, when = escape_html(frappe.session.user), cstr(now_datetime().replace(microsecond=0))
	inv.add_comment(
		"Info",
		_("Linked to CARD monthly cards {0} by {1} on {2}. Reason: {3}").format(
			escape_html(", ".join(names)), who, when, escape_html(reason)
		),
	)
	for card in docs:
		card.add_comment(
			"Info",
			_("Linked to Sales Invoice {0} by {1} on {2}. Reason: {3}").format(
				escape_html(inv.name), who, when, escape_html(reason)
			),
		)
	return log.name


def _unlinked_customer_cards(company):
	"""(customers that have customer-billing cards, their submitted approved cards without a customer invoice
	link and outside every active customer posting), as the caller may read them."""
	from card.constants import CUSTOMER_BILLING_DIRECTIONS, DIR_RENTED_OUT
	from card.gl.posting import _held_by_active_log
	from card.open_month import STATE_OPEN_MONTH

	cards = frappe.get_list(
		CARD_DOCTYPE,
		filters={
			"company": company,
			"docstatus": 1,
			"card_direction": ["in", list(CUSTOMER_BILLING_DIRECTIONS)],
			"customer": ["is", "set"],
		},
		fields=[
			"name",
			"customer",
			"project",
			"month",
			"year",
			"customer_net_amount",
			"sales_invoice",
			"posted",
			"card_direction",
			"workflow_state",
		],
		order_by="year asc, month asc, name asc",
		limit_page_length=0,
	)
	customers = sorted({c.customer for c in cards})
	free = [
		c
		for c in cards
		if not c.sales_invoice
		and c.workflow_state != STATE_OPEN_MONTH
		and not (c.card_direction == DIR_RENTED_OUT and c.posted)
	]
	held = _held_by_active_log(CARD_DOCTYPE, [c.name for c in free], "Customer")
	return customers, [c for c in free if c.name not in held]


def _candidate_match(inv, projects, cards, tolerance):
	"""(match, cards to show, note) of one invoice. Two sets are tested, never every subset: the unlinked cards
	of the invoice's projects in the invoice month and the month before, then all of them."""
	if not projects:
		return "none", [], _("The invoice has no project; it cannot be linked to cards.")
	if not cards:
		return "none", [], _("No unlinked card of this customer on the projects of the invoice.")
	day = getdate(inv.posting_date)
	this_month = day.year * 12 + day.month
	recent = [
		c for c in cards if this_month - 1 <= frappe.utils.cint(c.year) * 12 + int(c.month) <= this_month
	]
	net = flt(inv.base_net_total, 2)
	for subset, note in (
		(recent, _("The cards of the invoice month and the month before total the invoice net.")),
		(cards, _("All unlinked cards of the projects of the invoice total the invoice net.")),
	):
		if subset and abs(flt(net - sum(flt(c.customer_net_amount, 2) for c in subset), 2)) <= tolerance:
			return "exact", subset, note
	return (
		"none",
		cards,
		_(
			"No tested set of cards totals the invoice net: all unlinked cards of the projects total {0}."
		).format(flt(sum(flt(c.customer_net_amount, 2) for c in cards), 2)),
	)


@frappe.whitelist(methods=["GET"])
def unlinked_customer_invoice_candidates(
	company: str, limit_start: int | str = 0, limit_page_length: int | str = CANDIDATE_PAGE_LENGTH
):
	"""FR-194, read only: the submitted Sales Invoices of ``company`` that CARD did not build and that are not
	linked (no active GL Posting Log), for every customer that has customer-billing cards; with each one, the
	customer's unlinked approved cards on the invoice's projects, and whether a tested set of them totals the
	invoice net (``match`` = "exact" or "none"). Returns and opening invoices are left out. Newest first,
	``limit_page_length`` invoices per call (at most 200). It writes nothing and links nothing."""
	from frappe.utils import cint

	from card.settings import setting

	_require_customer_link_role()
	if company not in _customer_link_companies():
		frappe.throw(
			_("You are not permitted to link invoices for company {0}.").format(company),
			frappe.PermissionError,
		)
	frappe.has_permission("Sales Invoice", "read", throw=True)
	frappe.has_permission(CARD_DOCTYPE, "read", throw=True)
	start = max(cint(limit_start), 0)
	page = min(max(cint(limit_page_length), 1), CANDIDATE_PAGE_MAX)
	result = {"invoices": [], "limit_start": start, "limit_page_length": page, "has_more": False}
	customers, cards = _unlinked_customer_cards(company)
	if not customers:
		return result
	logged = frappe.get_all(
		"GL Posting Log",
		filters={
			"company": company,
			"posting_doctype": "Sales Invoice",
			"status": ["in", list(ACTIVE_STATES)],
			"posting_doc": ["is", "set"],
		},
		pluck="posting_doc",
		limit_page_length=0,
	)
	filters = [
		["company", "=", company],
		["customer", "in", customers],
		["docstatus", "=", 1],
		["is_return", "=", 0],
		["is_debit_note", "=", 0],
		["is_opening", "in", ["No", "", None]],
	]
	if logged:
		filters.append(["name", "not in", logged])
	invoices = frappe.get_list(
		"Sales Invoice",
		filters=filters,
		fields=["name", "posting_date", "customer", "project", "base_net_total"],
		order_by="posting_date desc, name desc",
		limit_start=start,
		limit_page_length=page + 1,
	)
	result["has_more"] = len(invoices) > page
	invoices = invoices[:page]
	if not invoices:
		return result
	projects = {inv.name: {inv.project} if inv.project else set() for inv in invoices}
	for line in frappe.get_all(
		"Sales Invoice Item",
		filters={"parenttype": "Sales Invoice", "parent": ["in", list(projects)], "project": ["is", "set"]},
		fields=["parent", "project"],
		limit_page_length=0,
	):
		projects[line.parent].add(line.project)
	tolerance = flt(setting("reconciliation_tolerance")) or 0.01
	for inv in invoices:
		own = [c for c in cards if c.customer == inv.customer and c.project in projects[inv.name]]
		match, shown, note = _candidate_match(inv, projects[inv.name], own, tolerance)
		result["invoices"].append(
			{
				"invoice": inv.name,
				"posting_date": inv.posting_date,
				"customer": inv.customer,
				"projects": sorted(projects[inv.name]),
				"net_total": flt(inv.base_net_total, 2),
				"cards": [
					{
						"name": c.name,
						"month": c.month,
						"year": c.year,
						"project": c.project,
						"customer_net_amount": flt(c.customer_net_amount, 2),
					}
					for c in shown
				],
				"match": match,
				"note": note,
			}
		)
	return result


def warn_card_postings_nearby(doc):
	"""R1 operational control: a hand-booked supplier invoice of a supplier that CARD
	already posted for a nearby month is shown the CARD postings, so the accountant
	checks it is not the same operation before it reaches the ledger (not blocking:
	the supplier may send several legitimate invoices)."""
	if doc.doctype != "Purchase Invoice" or not doc.get("supplier"):
		return
	from frappe.utils import add_days

	day = getdate(doc.get("bill_date") or doc.posting_date)
	start, end = add_days(day, -EVIDENCE_DAYS_AFTER), add_days(day, EVIDENCE_DAYS_BEFORE)
	nearby = [
		log
		for log in frappe.get_all(
			"GL Posting Log",
			filters={
				"company": doc.company,
				"party_type": "Supplier",
				"party": doc.supplier,
				"status": ["in", list(ACTIVE_STATES)],
				"origin": ["in", ["Built", "", None]],
				"posting_doc": ["!=", doc.name],
			},
			fields=["posting_doc", "month", "year", "amount"],
		)
		if start <= getdate("{0}-{1}-01".format(log.year, log.month)) <= end
	]
	if nearby:
		frappe.msgprint(
			_(
				"CARD already booked postings for this supplier: {0}. Check that this invoice is not for the same operations."
			).format(
				", ".join(
					"{0} ({1}/{2}, {3})".format(n.posting_doc, n.month, n.year, flt(n.amount, 2))
					for n in nearby
				),
			),
			title=_("Check for a duplicate expense"),
			indicator="orange",
		)
