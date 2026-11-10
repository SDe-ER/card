# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Report "Posting Source Integrity" (FR-136, risk R-25, #54).

Read-only. A CARD source (monthly card, diesel fill, transport) and the GL Posting Log that posted it are linked
two ways: the log's ``sources`` child rows are the authoritative list (card/gl/events.py), and on invoice submit
CARD writes the invoice link (``purchase_invoice`` / ``sales_invoice``) and ``posted`` onto each source with
``db.set_value`` (no Version row). A direct database edit, a data import or an older version can leave the two
out of step. This report lists every source of the company and period whose link, ``posted`` flag and posting
log disagree. It changes, links, posts and repairs nothing; the fix is a person's decision (rebuild, relink with
``link_supplier_invoice``, or a reviewed data correction)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from card.card.doctype.gl_posting_log.gl_posting_log import ACTIVE_STATES
from card.report_access import _role_reads, readable_links, resolve_company
from card.report_currency import company_currency_report

LOG = "GL Posting Log"
CARD = "Card Monthly Card"
FILL = "Project Diesel Fill"
TRANSPORT = "Equipment Transport"
DOCTYPES = (LOG, CARD, FILL, TRANSPORT)

# side link field on the source -> (party type of the posting log, invoice doctype)
SIDES = {
	"purchase_invoice": ("Supplier", "Purchase Invoice"),
	"sales_invoice": ("Customer", "Sales Invoice"),
}

# source doctype -> date field used for the period filter
SOURCE_DATE = {CARD: "to_date", FILL: "date", TRANSPORT: "date"}


def get_columns():
	return [
		{"fieldname": "check", "label": _("Integrity check"), "fieldtype": "Data", "width": 320},
		{
			"fieldname": "source_doctype",
			"label": _("Source type", context="Card"),
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "source",
			"label": _("Source"),
			"fieldtype": "Dynamic Link",
			"options": "source_doctype_name",
			"width": 160,
		},
		{"fieldname": "date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "source_status", "label": _("Source status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "posted", "label": _("Posted flag"), "fieldtype": "Check", "width": 90},
		{
			"fieldname": "purchase_invoice",
			"label": _("Purchase Invoice on the source"),
			"fieldtype": "Link",
			"options": "Purchase Invoice",
			"width": 160,
		},
		{
			"fieldname": "sales_invoice",
			"label": _("Sales Invoice on the source"),
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 160,
		},
		{
			"fieldname": "posting_log",
			"label": _("GL Posting Log"),
			"fieldtype": "Link",
			"options": LOG,
			"width": 150,
		},
		{"fieldname": "log_status", "label": _("Log status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "log_document", "label": _("Document of the log"), "fieldtype": "Data", "width": 170},
		{"fieldname": "amount", "label": _("Amount in the log"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "note", "label": _("Evidence"), "fieldtype": "Data", "width": 360},
	]


@company_currency_report(*DOCTYPES)
def execute(filters=None):
	filters = frappe._dict(filters or {})
	for doctype in DOCTYPES:
		if not _role_reads(doctype):
			frappe.throw(
				_("You need read access to {0} to run this report").format(_(doctype)), frappe.PermissionError
			)
	company = resolve_company(filters, *DOCTYPES)
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("Select the period"))
	if getdate(filters.to_date) < getdate(filters.from_date):
		frappe.throw(_("Invalid period: end is before start"))
	rows = check_sources(company, getdate(filters.from_date), getdate(filters.to_date))
	if filters.get("show", "Problems") != "All":
		rows = [r for r in rows if r["problem"]]
	columns = readable_links(get_columns(), rows)
	message = _(
		"Read only. Sources whose invoice link, posted flag and GL Posting Log disagree. Nothing is changed by this report."
	)
	return columns, rows, message, None, _summary(rows)


def check_sources(company, from_date, to_date):
	"""One row per source of ``company`` dated in the period that a posting touched (an invoice link, the posted
	flag, or a membership in an active GL Posting Log), plus one row per log source that no longer exists."""
	logs = {
		log.name: log
		for log in frappe.get_all(
			LOG,
			filters={"company": company, "status": ["in", list(ACTIVE_STATES)]},
			fields=["name", "status", "party_type", "posting_doctype", "posting_doc", "month", "year"],
			limit=0,
		)
	}
	holders = {}  # (doctype, name) -> [(log, amount)]
	if logs:
		for row in frappe.get_all(
			"GL Posting Source",
			filters={"parenttype": LOG, "parent": ["in", list(logs)]},
			fields=["parent", "source_doctype", "source_name", "amount"],
			limit=0,
		):
			holders.setdefault((row.source_doctype, row.source_name), []).append(
				(logs[row.parent], row.amount)
			)

	sources = {}
	for doctype, date_field in SOURCE_DATE.items():
		meta = frappe.get_meta(doctype)
		sides = [f for f in SIDES if meta.has_field(f)]
		for src in frappe.get_all(
			doctype,
			filters={
				"company": company,
				"docstatus": ["in", [1, 2]],
				date_field: ["between", [from_date, to_date]],
			},
			fields=["name", "docstatus", "posted", f"{date_field} as date", *sides],
			limit=0,
		):
			sources[(doctype, src.name)] = (src, sides)

	invoice_status = _invoice_status(sources)
	rows = []
	for (doctype, name), (src, sides) in sources.items():
		held = holders.get((doctype, name)) or []
		touched = src.posted or held or any(src.get(f) for f in sides)
		if touched:
			rows.append(_check(doctype, src, sides, held, invoice_status))
	rows.extend(_missing_sources(holders, sources, logs, from_date, to_date))
	rows.sort(key=lambda r: (not r["problem"], str(r["date"] or ""), r["source"] or ""))
	return rows


def _invoice_status(sources):
	"""docstatus of every invoice linked from a source, per invoice doctype."""
	status = {}
	for field, (_party_type, invoice_doctype) in SIDES.items():
		names = {src.get(field) for src, sides in sources.values() if field in sides and src.get(field)}
		found = dict(
			frappe.get_all(
				invoice_doctype,
				filters={"name": ["in", list(names)]},
				fields=["name", "docstatus"],
				as_list=True,
			)
			if names
			else []
		)
		status[invoice_doctype] = {name: found.get(name) for name in names}
	return status


def _check(doctype, src, sides, held, invoice_status):
	issues = []
	submitted = [(log, amount) for log, amount in held if log.status == "Submitted"]
	for field in sides:
		party_type, invoice_doctype = SIDES[field]
		link = src.get(field)
		side_logs = [log for log, _amount in submitted if log.party_type == party_type]
		invoice_logs = [log for log in side_logs if log.posting_doctype == invoice_doctype]
		if len(side_logs) > 1:
			issues.append(
				_("Held by more than one submitted {0} posting: {1}").format(
					_(party_type), ", ".join(sorted(log.name for log in side_logs))
				)
			)
		if link:
			if not invoice_logs:
				issues.append(
					_(
						"{0} {1} is linked on the source, but no submitted GL Posting Log lists the source"
					).format(_(invoice_doctype), link)
				)
			elif link not in {log.posting_doc for log in invoice_logs}:
				issues.append(
					_("{0} {1} is linked on the source, but the GL Posting Log posted it on {2}").format(
						_(invoice_doctype), link, ", ".join(sorted(log.posting_doc for log in invoice_logs))
					)
				)
			docstatus = invoice_status.get(invoice_doctype, {}).get(link)
			if docstatus is None:
				issues.append(_("The linked {0} {1} does not exist").format(_(invoice_doctype), link))
			elif docstatus != 1:
				issues.append(_("The linked {0} {1} is not submitted").format(_(invoice_doctype), link))
		elif invoice_logs:
			issues.append(
				_(
					"Submitted GL Posting Log {0} posted the source on {1}, but the source has no {2} link"
				).format(invoice_logs[0].name, invoice_logs[0].posting_doc, _(invoice_doctype))
			)
	posted_by = bool(submitted) or any(src.get(f) for f in sides)
	if src.posted and not posted_by:
		issues.append(_("Marked posted, but no submitted posting and no invoice link"))
	if not src.posted and submitted:
		issues.append(_("A submitted posting lists the source, but it is not marked posted"))
	if src.docstatus == 2 and (submitted or any(src.get(f) for f in sides)):
		issues.append(_("The source is cancelled but still posted"))

	log, amount = (submitted or held or [(None, None)])[0]
	return {
		"check": "; ".join(issues) if issues else _("Consistent"),
		"problem": int(bool(issues)),
		"source_doctype": _(doctype),
		"source_doctype_name": doctype,
		"source": src.name,
		"date": src.date,
		"source_status": _("Cancelled") if src.docstatus == 2 else _("Submitted"),
		"posted": int(src.posted or 0),
		"purchase_invoice": src.get("purchase_invoice"),
		"sales_invoice": src.get("sales_invoice"),
		"posting_log": log.name if log else None,
		"log_status": _(log.status) if log else "",
		"log_document": "{0} {1}".format(_(log.posting_doctype or ""), log.posting_doc or "") if log else "",
		"amount": flt(amount, 2) if log else None,
		"note": _("Held by {0} active posting log(s)").format(len(held)) if held else "",
	}


def _missing_sources(holders, sources, logs, from_date, to_date):
	"""Active logs of a month inside the period that list a source which no longer exists."""
	in_period = {}
	for (doctype, name), held in holders.items():
		if (doctype, name) in sources:
			continue
		for log, amount in held:
			try:
				month_start = getdate("{0}-{1:02d}-01".format(int(log.year), int(log.month)))
			except (TypeError, ValueError):
				continue
			if from_date <= month_start <= to_date or (
				month_start.year == from_date.year and month_start.month == from_date.month
			):
				in_period.setdefault(doctype, {}).setdefault(name, (log, amount))
	rows = []
	for doctype, names in in_period.items():
		existing = set(frappe.get_all(doctype, filters={"name": ["in", list(names)]}, pluck="name"))
		for name, (log, amount) in names.items():
			if name in existing:
				continue
			rows.append(
				{
					"check": _("GL Posting Log {0} lists {1} {2}, which no longer exists").format(
						log.name, _(doctype), name
					),
					"problem": 1,
					"source_doctype": _(doctype),
					"source_doctype_name": doctype,
					"source": name,
					"date": None,
					"source_status": _("Missing"),
					"posted": 0,
					"purchase_invoice": None,
					"sales_invoice": None,
					"posting_log": log.name,
					"log_status": _(log.status),
					"log_document": "{0} {1}".format(_(log.posting_doctype or ""), log.posting_doc or ""),
					"amount": flt(amount, 2),
					"note": "",
				}
			)
	return rows


def _summary(rows):
	problems = [r for r in rows if r["problem"]]
	return [
		{"label": _("Sources listed"), "value": len(rows), "datatype": "Int"},
		{
			"label": _("Sources to review"),
			"value": len(problems),
			"datatype": "Int",
			"indicator": "Red" if problems else "Green",
		},
	]
