# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Settlement phase 1 (owner decisions 2026-11-09, Q2): link an existing supplier
accrual Journal Entry to the CARD monthly cards it recognised.

Some supplier cards were recognised by hand with a Journal Entry (expense debit,
supplier payable credit) instead of a Purchase Invoice. Without a link CARD sees
them as "not invoiced" and its monthly posting would invoice them a second time.
The link is a controlled exception for historical supplier cards:

- nothing is posted, created or changed in ERPNext; the Journal Entry stays as it is;
- a Linked GL Posting Log of type Journal Entry lists the cards, so the monthly
  posting and every other link skip them, and the reconciliation counts them;
- cancelling the Journal Entry frees the cards again (``before_cancel`` below).
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.constants import SUPPLIER_BILLING_DIRECTIONS
from card.gl.integrity import REVIEW_ROLES, lock_sources

CARD = "Card Monthly Card"


@frappe.whitelist(methods=["POST"])
def link_accrual_journal(
	journal_entry: str, cards: str | list, reason: str | None = None, accept_difference: int | str = 0
):
	"""Record that a submitted supplier accrual Journal Entry already recognised these
	submitted supplier monthly cards. Returns the GL Posting Log name.

	Authorization: an accountant role, the company within the caller's CARD and
	accounting scope, read and submit right on the Journal Entry, read on the
	supplier and on every card.

	Evidence: the Journal Entry nets a credit to exactly one supplier (its accrual),
	and that credit equals the cards' net within the reconciliation tolerance; a gap
	is refused unless an accountant accepts it with a reason, and is then stored on
	the log as an open difference."""
	from card.gl.events import _point_display, active_log_holding
	from card.gl.posting import POSTING_SOURCE_DOCTYPES
	from card.report_access import permitted_companies
	from card.settings import setting

	if not REVIEW_ROLES & set(frappe.get_roles()):
		frappe.throw(
			_("Only an accountant may link accrual journal entries to CARD cards."), frappe.PermissionError
		)
	if isinstance(cards, str):
		cards = json.loads(cards)
	if not isinstance(cards, list) or not cards or not all(isinstance(c, str) and c for c in cards):
		frappe.throw(_("Choose the CARD monthly cards this journal entry recognised."))
	if len(set(cards)) != len(cards):
		frappe.throw(_("A card is listed twice."))

	je = frappe.get_doc("Journal Entry", journal_entry)
	je.check_permission("read")
	if je.company not in permitted_companies(*POSTING_SOURCE_DOCTYPES, "Journal Entry", "GL Posting Log"):
		frappe.throw(
			_("You are not permitted to link journal entries for company {0}.").format(je.company),
			frappe.PermissionError,
		)
	frappe.has_permission("Journal Entry", "submit", je, throw=True)
	if je.docstatus != 1:
		frappe.throw(_("Journal entry {0} is not submitted.").format(je.name))
	supplier, accrued, accrued_net = accrual_of(je)
	frappe.has_permission("Supplier", "read", supplier, throw=True)
	held = frappe.db.get_value(
		"GL Posting Log",
		{"posting_doctype": "Journal Entry", "posting_doc": je.name, "status": ["in", list(ACTIVE_STATES)]},
		"name",
	)
	if held:
		frappe.throw(_("Journal entry {0} is already linked to CARD cards ({1}).").format(je.name, held))

	lock_sources({CARD: [(name, 0) for name in cards]})
	amounts = []
	for name in cards:
		card = frappe.get_doc(CARD, name)
		card.check_permission("read")
		if card.docstatus != 1:
			frappe.throw(_("Card {0} is not submitted.").format(name))
		if card.company != je.company or card.supplier != supplier:
			frappe.throw(
				_("Card {0} belongs to another company or supplier than journal entry {1}.").format(
					name, je.name
				)
			)
		if card.card_direction not in SUPPLIER_BILLING_DIRECTIONS:
			frappe.throw(_("Card {0} is not billed by a supplier.").format(name))
		if card.purchase_invoice:
			frappe.throw(_("Card {0} is already invoiced by {1}.").format(name, card.purchase_invoice))
		holder = active_log_holding(CARD, name, "Supplier")
		if holder:
			frappe.throw(_("Card {0} is already held by {1}.").format(name, holder.posting_doc))
		amounts.append((name, flt(card.net_amount, 2)))

	cards_net = flt(sum(a for _n, a in amounts), 2)
	# the cards are net of VAT: compare them with the supplier credit less the entry's tax rows
	difference = flt(accrued_net - cards_net, 2)
	tolerance = flt(setting("reconciliation_tolerance")) or 0.01
	if abs(difference) <= tolerance:
		difference = 0
	accepted = cint(accept_difference) and (reason or "").strip()
	if difference and not accepted:
		frappe.throw(
			_(
				"Cannot confirm the link: the cards total {0} net, the journal entry credits the supplier {1}. Link only the cards it recognised, or accept the difference {2} with a reason."
			).format(cards_net, accrued_net, difference),
			title=_("Linked amounts differ"),
		)

	day = getdate(je.posting_date)
	log = frappe.get_doc(
		{
			"doctype": "GL Posting Log",
			"origin": "Linked",
			"company": je.company,
			"party_type": "Supplier",
			"party": supplier,
			"month": "%02d" % day.month,
			"year": day.year,
			"posting_type": "Journal Entry",
			"sequence": 1,
			"status": "Submitted",
			"posting_doctype": "Journal Entry",
			"posting_doc": je.name,
			"amount": accrued,
			"link_difference": difference,
			"remarks": _(
				"Linked by {0}: accrual journal entry {1} credits the supplier {2}, CARD cards net {3}, {4}. {5}"
			).format(
				frappe.session.user,
				je.name,
				accrued,
				cards_net,
				_("open difference {0} accepted").format(difference) if difference else _("matched"),
				reason or "",
			),
		}
	)
	for name, amount in amounts:
		log.append("sources", {"source_doctype": CARD, "source_name": name, "amount": amount})
	log.flags.card_gl_build = True
	log.insert(ignore_permissions=True)  # the audit record; the gate above is the authorization
	for name, _amount in amounts:
		frappe.db.set_value(CARD, name, "posted", 1, update_modified=False)
		# never take the display pointer from the customer side's active posting (sub-rental)
		_point_display(CARD, name, log.name)
	return log.name


def accrual_of(je):
	"""(supplier, credit, credit less tax rows) of an accrual Journal Entry: an ordinary
	journal entry (not an opening, debit or credit note), exactly one supplier on its
	party rows, credited on balance (credit minus debit, company currency), with no
	party row against another document (that entry settles the other document)."""
	if je.voucher_type != "Journal Entry" or je.get("is_opening") == "Yes":
		frappe.throw(_("Journal entry {0} is not an ordinary accrual entry.").format(je.name))
	totals = {}
	tax = 0.0
	for row in je.get("accounts") or []:
		if row.party and row.get("reference_type"):
			frappe.throw(
				_("Journal entry {0} is booked against {1} {2}; it is not an accrual of its own.").format(
					je.name, _(row.reference_type), row.reference_name
				)
			)
		if not row.party and frappe.get_cached_value("Account", row.account, "account_type") == "Tax":
			tax = flt(tax + flt(row.debit) - flt(row.credit), 2)
		if row.party_type == "Supplier" and row.party:
			totals[row.party] = flt(totals.get(row.party, 0) + flt(row.credit) - flt(row.debit), 2)
		elif row.party_type and row.party:
			frappe.throw(_("Journal entry {0} has a party other than a supplier.").format(je.name))
	if len(totals) != 1:
		frappe.throw(_("Journal entry {0} must recognise exactly one supplier.").format(je.name))
	supplier, credit = next(iter(totals.items()))
	if credit <= 0:
		frappe.throw(
			_("Journal entry {0} does not credit supplier {1}; it is not an accrual.").format(
				je.name, supplier
			)
		)
	return supplier, credit, flt(credit - tax, 2)


def before_cancel(doc, method=None):
	"""Cancelling a linked accrual Journal Entry frees its cards (before frappe's
	backlink check), so they count as not recognised again."""
	name = frappe.db.get_value(
		"GL Posting Log",
		{"posting_doctype": "Journal Entry", "posting_doc": doc.name, "status": ["in", list(ACTIVE_STATES)]},
		"name",
	)
	if not name:
		return
	from card.gl.events import _other_side_still_posted, _repoint_freed_sources

	log = frappe.get_doc("GL Posting Log", name)
	for row in log.get("sources") or []:
		posted = 1 if _other_side_still_posted(row.source_doctype, row.source_name, "purchase_invoice") else 0
		frappe.db.set_value(row.source_doctype, row.source_name, "posted", posted, update_modified=False)
		if frappe.db.get_value(row.source_doctype, row.source_name, "gl_posting") == log.name:
			frappe.db.set_value(row.source_doctype, row.source_name, "gl_posting", "", update_modified=False)
	log.db_set("status", "Cancelled")
	log.db_set("posting_key", None)
	log.db_set("remarks", (log.remarks or "") + " " + _("Journal entry cancelled; cards freed."))
	# sub-rental: point a freed card back at the customer side's active posting
	_repoint_freed_sources(log)
