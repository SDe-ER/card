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
	current = snapshot(doc)
	signature = full_signature(current)
	if signature in (log.built_signature, log.get("accepted_signature")):
		return
	built = json.loads(log.built_snapshot)
	diffs = describe_differences(built, current)
	hint = (
		_(
			"An Accounts Manager can accept this cost center/account correction from the invoice (Accept CARD correction)."
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


def manual_invoice_candidates(company, supplier, first_day, last_day, accounts, items):
	"""Purchase Invoices (draft or submitted) of the supplier dated in the month
	(posting or bill date) that CARD did not build and that book to a CARD
	account or item — possible evidence that the operations are already booked."""
	invoices = frappe.get_all(
		"Purchase Invoice",
		filters={"company": company, "supplier": supplier, "docstatus": ["<", 2], "is_return": 0},
		or_filters={
			"posting_date": ["between", [first_day, last_day]],
			"bill_date": ["between", [first_day, last_day]],
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
	hits = set(
		frappe.get_all(
			"Purchase Invoice Item",
			filters={"parent": ["in", names], "parenttype": "Purchase Invoice"},
			or_filters={"expense_account": ["in", list(accounts)], "item_code": ["in", list(items)]},
			pluck="parent",
		)
	)
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
	sources nor declared unrelated by an accountant for this build."""
	pending = [c for c in candidates if not c.linked_log and c.name not in reviewed]
	if pending:
		frappe.throw(
			_(
				"Supplier invoices already booked for this month may cover the same operations: {0}. Link each one to the CARD sources it pays for (Link supplier invoice), or have an accountant confirm it is unrelated, then build again."
			).format(
				", ".join(
					"{0} ({1}{2})".format(
						c.name, c.bill_no or _("no bill no."), _(", draft") if c.docstatus == 0 else ""
					)
					for c in pending
				)
			),
			title=_("Possible duplicate expense"),
		)
	if reviewed and not REVIEW_ROLES & set(frappe.get_roles()):
		frappe.throw(_("Only an accountant may declare supplier invoices unrelated."), frappe.PermissionError)
	unknown = set(reviewed) - {c.name for c in candidates}
	if unknown:
		frappe.throw(
			_("Not a candidate invoice for this supplier and month: {0}").format(", ".join(sorted(unknown)))
		)


def lock_sources(sources):
	"""Row-lock every source in a stable order, so a concurrent build or link of
	the same documents waits and then sees the first one's reservation."""
	for doctype, name in sorted((dt, n) for dt, rows in sources.items() for n, _amount in rows):
		frappe.db.get_value(doctype, name, "name", for_update=True)


@frappe.whitelist(methods=["POST"])
def link_supplier_invoice(invoice: str, sources: str | list, reason: str | None = None):
	"""Record that an existing supplier Purchase Invoice (booked by hand) already
	pays for these CARD sources. Nothing is reposted and the invoice is not
	changed: a Linked GL Posting Log reserves the sources so CARD never builds them
	again, and the sources show the invoice once it is submitted."""
	from card.gl.events import active_log_holding, link_sources_on_submit

	if not REVIEW_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only an accountant may link supplier invoices to CARD sources."), frappe.PermissionError
		)
	if isinstance(sources, str):
		sources = json.loads(sources)
	inv = frappe.get_doc("Purchase Invoice", invoice)
	inv.check_permission("read")
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
		rows[doctype].append((name, 0))
	lock_sources(rows)
	months = set()
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
			holder = active_log_holding(doctype, name, "Supplier")
			if holder:
				frappe.throw(
					_("{0} {1} is already held by {2}.").format(_(doctype), name, holder.posting_doc)
				)
			amount = flt(src.get("net_amount") if doctype == "Card Monthly Card" else src.get("amount"), 2)
			items[i] = (name, amount)
			if doctype == "Card Monthly Card":
				months.add((int(src.month), int(src.year)))
			else:
				day = getdate(src.date)
				months.add((day.month, day.year))
	if len(months) != 1:
		frappe.throw(_("Link the sources of one month at a time."))
	month, year = months.pop()
	sources_total = flt(sum(a for items in rows.values() for _n, a in items), 2)
	log = frappe.get_doc(
		{
			"doctype": "GL Posting Log",
			"origin": "Linked",
			"company": inv.company,
			"party_type": "Supplier",
			"party": inv.supplier,
			"month": "%02d" % month,
			"year": year,
			"posting_type": "Purchase Invoice",
			"sequence": 1,
			"status": "Submitted" if inv.docstatus == 1 else "Draft",
			"posting_doctype": "Purchase Invoice",
			"posting_doc": inv.name,
			"amount": flt(inv.grand_total, 2),
			"remarks": _(
				"Linked by {0}: supplier invoice {1} (bill no. {2}) net {3}, CARD sources {4}, difference {5}. {6}"
			).format(
				frappe.session.user,
				inv.name,
				inv.bill_no or "-",
				flt(inv.net_total, 2),
				sources_total,
				flt(flt(inv.net_total, 2) - sources_total, 2),
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
