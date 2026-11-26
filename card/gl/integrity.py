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
CANDIDATE_PAGE_MAX = 200
CANDIDATE_CARDS_MAX = 100


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
		if text.startswith("["):
			try:
				cards = json.loads(text)
			except ValueError:
				frappe.throw(_("Choose the monthly cards this invoice bills."))
		else:
			cards = [text] if text else []
	names = []
	for entry in cards if isinstance(cards, list) else []:
		name = entry.get("name") if isinstance(entry, dict) else entry
		name = name.strip() if isinstance(name, str) else name
		if not name or not isinstance(name, str):
			frappe.throw(_("Choose the monthly cards this invoice bills."))
		if name in names:
			frappe.throw(_("{0} {1} is listed twice.").format(_(CARD_DOCTYPE), name))
		names.append(name)
	if not names:
		frappe.throw(_("Choose the monthly cards this invoice bills."))
	return names


def _net_by_project(lines, header_project):
	"""{project: net before VAT in company currency} of the lines of a Sales Invoice. A line without a project
	takes the header project of the invoice; without that too it is under "" (CARD's own customer posting
	writes the card's project on every line and none on the header)."""
	out = {}
	for line in lines or []:
		project = line.get("project") or header_project or ""
		out[project] = flt(out.get(project, 0) + flt(line.get("base_net_amount")), 2)
	return out


def _cards_by_project(cards):
	out = {}
	for card in cards:
		out[card.project] = flt(out.get(card.project, 0) + flt(card.customer_net_amount, 2), 2)
	return out


def _project_gaps(invoice_by_project, cards_by_project, tolerance):
	"""[(project, invoice net, cards net)] of every project whose invoice lines and cards differ: a project of
	the cards the invoice bills differently, and a project (or lines without one) of the invoice that no card
	covers."""
	return [
		(project, flt(invoice_by_project.get(project), 2), flt(cards_by_project.get(project), 2))
		for project in sorted(set(invoice_by_project) | set(cards_by_project))
		if abs(flt(flt(invoice_by_project.get(project)) - flt(cards_by_project.get(project)), 2)) > tolerance
	]


def _active_customer_holder(card):
	"""The active customer-side posting log that lists the card, read with a locking read: it sees what other
	transactions committed, not the snapshot of this one."""
	source, log = frappe.qb.DocType("GL Posting Source"), frappe.qb.DocType("GL Posting Log")
	rows = (
		frappe.qb.from_(source)
		.join(log)
		.on(log.name == source.parent)
		.select(log.name, log.posting_doc)
		.where(
			(source.parenttype == "GL Posting Log")
			& (source.source_doctype == CARD_DOCTYPE)
			& (source.source_name == card)
			& (log.party_type == "Customer")
			& (log.status.isin(list(ACTIVE_STATES)))
		)
		.for_update()
		.run(as_dict=True)
	)
	return rows[0] if rows else None


@frappe.whitelist(methods=["POST"])
def link_customer_invoice(invoice: str, cards: str | list, reason: str | None = None):
	"""FR-194: record that a submitted Sales Invoice, booked by hand in ERPNext, already bills these customer
	monthly cards. The customer mirror of ``link_supplier_invoice``: a Linked GL Posting Log holds the cards, so
	CARD never builds them again, and each card gets its customer invoice link. Nothing is posted; the invoice,
	the card amounts and the ledger are not changed.

	Authorization: Accounts Manager or System Manager; the company within the caller's CARD and accounting
	scope; read on the invoice, the customer and every card; the submit right on Sales Invoice.

	Evidence: the invoice is in the company currency and has no submitted credit note; every card is a
	submitted, approved customer-billing card of the invoice's company, customer and project, without a
	customer invoice; the invoice net total (before VAT) equals the sum of the cards' customer net amounts
	within the reconciliation tolerance, in total and for each project. A difference is always refused.

	Concurrency: the invoice row and the card rows are locked, and the state that another transaction can
	change (document status, links, active logs) is read again under those locks."""
	from frappe.utils import cint, cstr, escape_html, now_datetime, strip_html_tags

	from card.constants import CUSTOMER_BILLING_DIRECTIONS, DIR_RENTED_OUT
	from card.gl.events import link_sources_on_submit
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
	# lock the invoice row; its state is the committed one, not this transaction's snapshot
	state = frappe.db.get_value(
		"Sales Invoice",
		invoice,
		["docstatus", "is_return", "is_debit_note", "is_opening", "currency"],
		as_dict=True,
		for_update=True,
	)
	if not state or state.docstatus != 1:
		frappe.throw(_("{0} is not submitted; link a submitted Sales Invoice.").format(invoice))
	if state.is_return:
		frappe.throw(_("{0} is a return (credit note); link the Sales Invoice itself.").format(invoice))
	if state.is_debit_note:
		frappe.throw(_("{0} is a debit note; link the Sales Invoice itself.").format(invoice))
	if state.is_opening == "Yes":
		frappe.throw(_("{0} is an opening invoice; it does not bill monthly cards.").format(invoice))
	if state.currency != frappe.get_cached_value("Company", inv.company, "default_currency"):
		frappe.throw(
			_("{0} is in {1}; only invoices in the company currency can be linked.").format(
				invoice, state.currency
			)
		)
	existing = frappe.db.get_value(
		"GL Posting Log",
		{"posting_doctype": "Sales Invoice", "posting_doc": invoice, "status": ["in", list(ACTIVE_STATES)]},
		"name",
		for_update=True,
	)
	if existing:
		frappe.throw(_("{0} is already a CARD posting or linked ({1}).").format(invoice, existing))
	credit_note = frappe.db.get_value(
		"Sales Invoice", {"is_return": 1, "return_against": invoice, "docstatus": 1}, "name"
	)
	if credit_note:
		frappe.throw(
			_("{0} has a credit note ({1}); link the valid Sales Invoice.").format(invoice, credit_note)
		)
	rows = {CARD_DOCTYPE: [(name, 0) for name in names]}
	lock_sources(rows)
	invoice_by_project = _net_by_project(inv.get("items"), inv.get("project"))
	docs = []
	for i, name in enumerate(names):
		card = frappe.get_doc(CARD_DOCTYPE, name)
		card.check_permission("read")
		# the database matches names without case: two spellings of one card are one row
		if any(card.name == listed.name for listed in docs):
			frappe.throw(_("{0} {1} is listed twice.").format(_(CARD_DOCTYPE), card.name))
		name = card.name
		# the fields a posting, a cancel or a reopen of another transaction changes, under the row lock
		current = frappe.db.get_value(
			CARD_DOCTYPE,
			name,
			["docstatus", "workflow_state", "sales_invoice", "posted", "gl_posting"],
			as_dict=True,
			for_update=True,
		)
		if not current or current.docstatus != 1:
			frappe.throw(_("{0} {1} is not submitted.").format(_(CARD_DOCTYPE), name))
		if current.workflow_state == STATE_OPEN_MONTH:
			frappe.throw(_("Card {0} is not approved: its month has not ended.").format(name))
		if card.card_direction not in CUSTOMER_BILLING_DIRECTIONS:
			frappe.throw(_("Card {0} is not billed to a customer.").format(name))
		if card.company != inv.company:
			frappe.throw(_("Card {0} belongs to another company than {1}.").format(name, invoice))
		if not card.customer or card.customer != inv.customer:
			frappe.throw(_("Card {0} belongs to another customer than {1}.").format(name, invoice))
		if not card.project or card.project not in invoice_by_project:
			frappe.throw(
				_(
					"Card {0} is of project {1}, which is not a project of {2} (its lines, or its header for a line without a project)."
				).format(name, card.project or "-", invoice)
			)
		if current.sales_invoice:
			frappe.throw(_("Card {0} is already invoiced by {1}.").format(name, current.sales_invoice))
		holder = _active_customer_holder(name)
		if holder:
			frappe.throw(_("Card {0} is already held by {1}.").format(name, holder.posting_doc))
		if card.card_direction == DIR_RENTED_OUT and cint(current.posted):
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
	for project, billed, listed in _project_gaps(invoice_by_project, _cards_by_project(docs), tolerance):
		if not project:
			frappe.throw(
				_(
					"Cannot link: {0} bills {1} net on lines without a project, and every card has a project."
				).format(invoice, billed),
				title=_("Linked amounts differ"),
			)
		frappe.throw(
			_(
				"Cannot link: for project {0}, {1} bills {2} net and the listed cards total {3}. Link exactly the cards this invoice bills."
			).format(project, invoice, billed, listed),
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
			escape_html(", ".join(card.name for card in docs)), who, when, escape_html(reason)
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


def _check_unlink_chain(invoice, log):
	"""FR-195: refuse a cancelled-and-amended chain that the link does not match. ``card.gl.events`` keeps one
	rule for a linked invoice: its cancel frees the cards and closes the log, and an amendment is a new
	invoice that is linked afresh with a log of its own. So the invoice of an active link is never amended by
	another invoice, and no invoice it amends (up the whole chain) still has an active posting log."""
	if log.posting_doctype != "Sales Invoice" or log.posting_doc != invoice:
		frappe.throw(
			_("Cannot unlink {0}: the posting log {1} names {2}, not this invoice.").format(
				invoice, log.name, log.posting_doc
			)
		)
	amendment = frappe.db.get_value("Sales Invoice", {"amended_from": invoice}, "name")
	if amendment:
		frappe.throw(
			_("Cannot unlink {0}: cancelled-and-amended chain mismatch: {1} amends it.").format(
				invoice, amendment
			)
		)
	earlier, seen = frappe.db.get_value("Sales Invoice", invoice, "amended_from"), {invoice}
	while earlier and earlier not in seen:
		seen.add(earlier)
		held = frappe.db.get_value(
			"GL Posting Log",
			{
				"posting_doctype": "Sales Invoice",
				"posting_doc": earlier,
				"status": ["in", list(ACTIVE_STATES)],
			},
			"name",
		)
		if held:
			frappe.throw(
				_(
					"Cannot unlink {0}: cancelled-and-amended chain mismatch: {1}, which it amends, still has the active posting log {2}."
				).format(invoice, earlier, held)
			)
		earlier = frappe.db.get_value("Sales Invoice", earlier, "amended_from")


@frappe.whitelist(methods=["POST"])
def unlink_customer_invoice(invoice: str, reason: str | None = None):
	"""FR-195: remove a wrong link between a customer Sales Invoice and its monthly cards (the undo of
	``link_customer_invoice``), for a company that cannot cancel a submitted Sales Invoice (ZATCA). Nothing is
	posted, cancelled, amended or deleted; the Sales Invoice, the card amounts and the ledger are not changed.

	Authorization: System Manager only; read on the invoice (System Manager alone gives no read on Sales Invoice:
	the caller also needs an accounts role); the company within the caller's CARD and accounting scope; read on
	every card of the link. A reason is mandatory.

	Works only on a submitted Sales Invoice that is the posting document of an ACTIVE GL Posting Log with origin
	Linked. A posting CARD built (origin Built or empty) or its credit note is always refused: its undo is the
	standard cancel or credit note.

	Refusals (nothing is partly undone; every check runs before the first write):
	- the caller cannot read a card of the link;
	- the log names another document than this exact invoice;
	- cancelled-and-amended chain mismatch: another Sales Invoice amends this one, or an invoice this one amends
	  (up the chain) still has an active posting log. A linked invoice that is cancelled frees its cards itself
	  (``card.gl.events.before_cancel``), and its amendment is linked afresh; an amendment with its own exact
	  link is unlinked as any other invoice;
	- a source of the log is not a monthly card;
	- a card changed since the link: it is not submitted, it is not marked posted, its customer invoice is not
	  this invoice, or its display link is neither this log nor the active supplier-side log that holds the card
	  (sub-rental: ``_point_display`` leaves the display link on the other side's active posting).

	Effect, with the mechanism of the cancel path of ``card.gl.events``: on each card ``sales_invoice`` is
	cleared, ``posted`` goes to 0 unless the supplier side is still posted (a purchase invoice link, or a
	submitted supplier-side log such as a linked accrual Journal Entry), ``gl_posting`` is cleared when it
	points at this log (and pointed back at the other side's active log, if any); ``modified`` is not changed.
	The log goes to Cancelled and its posting key is cleared, so the invoice and the cards can be linked again.
	The log is never deleted: its remarks keep the link text and get who, when, why and the previous links
	(cards and amounts). One Info comment is added on the invoice and on each card.

	Concurrency: the invoice row, the log row (by its name) and the card rows are locked in the order of the
	link. The invoice status, the log and the link fields of the cards are read under those locks. The
	amendment chain and the supplier-side log of a sub-rental card are plain reads: this method does not lock
	rows of the supplier side."""
	from frappe.utils import cint, cstr, escape_html, now_datetime, strip_html_tags

	from card.gl.events import _other_side_still_posted, _repoint_freed_sources

	if "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only a System Manager may unlink a customer invoice from CARD cards."), frappe.PermissionError
		)
	reason = strip_html_tags(cstr(reason)).strip()
	if not reason:
		frappe.throw(_("Give the reason for unlinking this invoice from the cards."))
	inv = frappe.get_doc("Sales Invoice", invoice)
	inv.check_permission("read")
	if inv.company not in _customer_link_companies():
		frappe.throw(
			_("You are not permitted to unlink invoices for company {0}.").format(inv.company),
			frappe.PermissionError,
		)
	invoice = inv.name
	# lock the invoice row, then the log, then the cards (the order of the link); read the state under the locks
	docstatus = frappe.db.get_value("Sales Invoice", invoice, "docstatus", for_update=True)
	if docstatus != 1:
		frappe.throw(
			_("{0} is not submitted; only the link of a submitted Sales Invoice can be removed.").format(
				invoice
			)
		)
	# the log is found with a plain read and locked by its name: a locking read on posting_doc (no index)
	# would lock rows of other postings. Its state is checked again on the locked row.
	held = frappe.db.get_value(
		"GL Posting Log",
		{"posting_doctype": "Sales Invoice", "posting_doc": invoice, "status": ["in", list(ACTIVE_STATES)]},
		"name",
	)
	log = frappe.get_doc("GL Posting Log", held, for_update=True) if held else None
	if (
		not log
		or log.status not in ACTIVE_STATES
		or log.posting_doctype != "Sales Invoice"
		or log.posting_doc != invoice
	):
		frappe.throw(_("{0} is not linked to CARD cards.").format(invoice))
	if log.origin != "Linked" or log.party_type != "Customer":
		frappe.throw(
			_(
				"{0} is a CARD posting ({1}), not a linked invoice; its link cannot be removed. Correct it with a credit note or cancel it."
			).format(invoice, log.name)
		)
	_check_unlink_chain(invoice, log)
	sources = [(row.source_doctype, row.source_name, flt(row.amount, 2)) for row in log.get("sources") or []]
	for doctype, name, _amount in sources:
		if doctype != CARD_DOCTYPE:
			frappe.throw(
				_(
					"Cannot unlink {0}: the posting log {1} holds {2} {3}, which is not a monthly card."
				).format(invoice, log.name, _(doctype), name)
			)
	lock_sources({CARD_DOCTYPE: [(name, amount) for _doctype, name, amount in sources]})
	clear_display, cards = {}, {}
	for _doctype, name, _amount in sources:
		# the caller must be able to read every card whose link is removed (as for the link)
		cards[name] = frappe.get_doc(CARD_DOCTYPE, name)
		cards[name].check_permission("read")
		current = frappe.db.get_value(
			CARD_DOCTYPE,
			name,
			["docstatus", "sales_invoice", "posted", "gl_posting"],
			as_dict=True,
			for_update=True,
		)
		if not current or current.docstatus != 1:
			frappe.throw(
				_("Cannot unlink {0}: card {1} is no longer submitted. Nothing was unlinked.").format(
					invoice, name
				)
			)
		clear_display[name] = current.gl_posting == log.name
		display_ok = clear_display[name]
		if not display_ok and current.gl_posting:
			# sub-rental: the display link may sit on the supplier side's active posting that holds the card
			other = frappe.db.get_value(
				"GL Posting Log", current.gl_posting, ["status", "party_type"], as_dict=True
			)
			display_ok = bool(
				other
				and other.status in ACTIVE_STATES
				and other.party_type == "Supplier"
				and frappe.db.exists(
					"GL Posting Source",
					{
						"parenttype": "GL Posting Log",
						"parent": current.gl_posting,
						"source_doctype": CARD_DOCTYPE,
						"source_name": name,
					},
				)
			)
		if current.sales_invoice != invoice or not display_ok:
			frappe.throw(
				_(
					"Cannot unlink {0}: card {1} changed since the link (its customer invoice is {2}, its posting log is {3}). Nothing was unlinked."
				).format(invoice, name, current.sales_invoice or "-", current.gl_posting or "-")
			)
		if not cint(current.posted):
			frappe.throw(
				_("Cannot unlink {0}: card {1} is not marked as posted. Nothing was unlinked.").format(
					invoice, name
				)
			)
	# every check passed: release the cards as the cancel of a linked invoice does (card.gl.events.before_cancel)
	for _doctype, name, _amount in sources:
		frappe.db.set_value(CARD_DOCTYPE, name, "sales_invoice", "", update_modified=False)
		frappe.db.set_value(
			CARD_DOCTYPE,
			name,
			"posted",
			1 if _other_side_still_posted(CARD_DOCTYPE, name, "sales_invoice") else 0,
			update_modified=False,
		)
		if clear_display[name]:
			frappe.db.set_value(CARD_DOCTYPE, name, "gl_posting", "", update_modified=False)
	user, when = frappe.session.user, cstr(now_datetime().replace(microsecond=0))
	previous = ", ".join("{0} ({1})".format(name, amount) for _doctype, name, amount in sources)
	log.db_set("status", "Cancelled")
	log.db_set("posting_key", None)
	log.db_set(
		"remarks",
		"{0}\n{1}".format(
			log.remarks or "",
			_("Unlinked by {0} on {1}: sales invoice {2}, posting log {3}, cards {4}. Reason: {5}").format(
				user, when, invoice, log.name, previous or "-", reason
			),
		).strip(),
	)
	_repoint_freed_sources(log)
	who = escape_html(user)
	inv.add_comment(
		"Info",
		_("Unlinked from CARD monthly cards {0} by {1} on {2} (posting log {3}). Reason: {4}").format(
			escape_html(previous or "-"), who, when, escape_html(log.name), escape_html(reason)
		),
	)
	for _doctype, name, _amount in sources:
		cards[name].add_comment(
			"Info",
			_("Unlinked from Sales Invoice {0} by {1} on {2} (posting log {3}). Reason: {4}").format(
				escape_html(invoice), who, when, escape_html(log.name), escape_html(reason)
			),
		)
	return log.name


def _customer_billing_filters(company):
	from card.constants import CUSTOMER_BILLING_DIRECTIONS

	return {
		"company": company,
		"docstatus": 1,
		"card_direction": ["in", list(CUSTOMER_BILLING_DIRECTIONS)],
		"customer": ["is", "set"],
	}


def _unlinked_customer_cards(company, customers):
	"""The submitted approved cards of ``customers`` without a customer invoice link and outside every active
	customer posting, as the caller may read them. The held cards are found with two queries for the whole list."""
	from card.constants import DIR_RENTED_OUT
	from card.gl.posting import _unheld_batch
	from card.open_month import STATE_OPEN_MONTH

	cards = frappe.get_list(
		CARD_DOCTYPE,
		filters={**_customer_billing_filters(company), "customer": ["in", customers]},
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
	free = [
		c
		for c in cards
		if not c.sales_invoice
		and c.workflow_state != STATE_OPEN_MONTH
		and not (c.card_direction == DIR_RENTED_OUT and c.posted)
	]
	return _unheld_batch(free, CARD_DOCTYPE, "Customer")


def _cards_cover(inv, invoice_by_project, cards, tolerance):
	"""The rule of the link: the cards total the invoice net, in total and for each project."""
	total = sum(flt(c.customer_net_amount, 2) for c in cards)
	return abs(flt(flt(inv.base_net_total, 2) - total, 2)) <= tolerance and not _project_gaps(
		invoice_by_project, _cards_by_project(cards), tolerance
	)


def _candidate_match(inv, invoice_by_project, cards, tolerance):
	"""(match, cards to show, note) of one invoice. Two sets are tested, never every subset: the unlinked cards
	of the invoice's projects in the invoice month and the month before, then all of them."""
	if not any(invoice_by_project):
		return "none", [], _("The invoice has no project; it cannot be linked to cards.")
	if not cards:
		return "none", [], _("No unlinked card of this customer on the projects of the invoice.")
	day = getdate(inv.posting_date)
	this_month = day.year * 12 + day.month
	recent = [
		c for c in cards if this_month - 1 <= frappe.utils.cint(c.year) * 12 + int(c.month) <= this_month
	]
	for subset, note in (
		(
			recent,
			_("The cards of the invoice month and the month before total the invoice net, for each project."),
		),
		(
			cards,
			_("All unlinked cards of the projects of the invoice total the invoice net, for each project."),
		),
	):
		if subset and _cards_cover(inv, invoice_by_project, subset, tolerance):
			return "exact", subset, note
	return (
		"none",
		cards,
		_(
			"No tested set of cards totals the invoice net for each project: all unlinked cards of the projects total {0}."
		).format(flt(sum(flt(c.customer_net_amount, 2) for c in cards), 2)),
	)


@frappe.whitelist(methods=["GET"])
def unlinked_customer_invoice_candidates(
	company: str, limit_start: int | str = 0, limit_page_length: int | str = 50
):
	"""FR-194, read only: the submitted Sales Invoices of ``company`` that CARD did not build and that are not
	linked (no active GL Posting Log), for every customer that has customer-billing cards; with each one, the
	customer's unlinked approved cards on the invoice's projects, and whether a tested set of them totals the
	invoice net for each project (``match`` = "exact" or "none"). Returns, debit notes, opening invoices and
	invoices with a submitted credit note are left out. Newest first, ``limit_page_length`` invoices per call
	(at most 200), at most 100 cards per invoice (``more_cards`` says that there are more). It writes nothing
	and links nothing."""
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
	customers = sorted(
		{
			c.customer
			for c in frappe.get_list(
				CARD_DOCTYPE,
				filters=_customer_billing_filters(company),
				fields=["customer"],
				distinct=True,
				limit_page_length=0,
			)
		}
	)
	if not customers:
		return result
	# invoices that are never candidates, by name: an invoice with an active log, an invoice with a submitted
	# credit note, an opening invoice. Named here (not filtered by value), so a row whose opening flag is
	# empty (NULL) stays in the list.
	submitted = {"company": company, "docstatus": 1}
	excluded = set(
		frappe.get_all(
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
	)
	excluded.update(
		frappe.get_all(
			"Sales Invoice",
			filters={**submitted, "is_return": 1, "return_against": ["is", "set"]},
			pluck="return_against",
			limit_page_length=0,
		)
	)
	excluded.update(
		frappe.get_all(
			"Sales Invoice", filters={**submitted, "is_opening": "Yes"}, pluck="name", limit_page_length=0
		)
	)
	filters = [
		["company", "=", company],
		["customer", "in", customers],
		["docstatus", "=", 1],
		["is_return", "=", 0],
		["is_debit_note", "=", 0],
	]
	if excluded:
		filters.append(["name", "not in", sorted(excluded)])
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
	lines = {inv.name: [] for inv in invoices}
	for line in frappe.get_all(
		"Sales Invoice Item",
		filters={"parenttype": "Sales Invoice", "parent": ["in", list(lines)]},
		fields=["parent", "project", "base_net_amount"],
		limit_page_length=0,
	):
		lines[line.parent].append(line)
	cards = _unlinked_customer_cards(company, sorted({inv.customer for inv in invoices}))
	tolerance = flt(setting("reconciliation_tolerance")) or 0.01
	for inv in invoices:
		invoice_by_project = _net_by_project(lines[inv.name], inv.project)
		own = [c for c in cards if c.customer == inv.customer and c.project in invoice_by_project]
		match, shown, note = _candidate_match(inv, invoice_by_project, own, tolerance)
		result["invoices"].append(
			{
				"invoice": inv.name,
				"posting_date": inv.posting_date,
				"customer": inv.customer,
				"projects": sorted(p for p in invoice_by_project if p),
				"net_total": flt(inv.base_net_total, 2),
				"cards": [
					{
						"name": c.name,
						"month": c.month,
						"year": c.year,
						"project": c.project,
						"customer_net_amount": flt(c.customer_net_amount, 2),
					}
					for c in shown[:CANDIDATE_CARDS_MAX]
				],
				"more_cards": len(shown) > CANDIDATE_CARDS_MAX,
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
