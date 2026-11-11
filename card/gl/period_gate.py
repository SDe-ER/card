# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-154 (#49, closure plan WP-S2): the monthly posting requires an approved, current Card Period Run.

Opt-in per company: Card Company Settings ``require_period_approval`` (default 0). Off, nothing here runs beyond
reading that flag, and the posting is exactly what it was before. On, every way the monthly posting is reached
goes through ``check_posting``, which ``card.gl.posting._plan_monthly_posting`` calls for both sides: the
whitelisted ``post_month`` and ``rebuild_month``, a direct or background-job call of ``build_monthly_posting`` or
``rebuild_monthly_posting``, and the preview (``preview_month``, a dry run that shows the refusal as ``blocked``).
``rebuild_monthly_posting`` also checks the run state before it deletes the old draft (``require_run_state``).

What is checked, in this order (the first failure refuses, with its reason):

1. the company-month has an active Card Period Run (FR-147);
2. it is submitted, approved, and its approval is for its current version and snapshot;
3. it was not approved by one of its preparers while the company's ``period_run_self_approval_rule`` is Refuse
   (the stricter of the run's rule and the company's rule; a run approved before the company raised its rule);
4. document by document, every source the posting is about to bill is in the run on that side, for that party,
   with the run's fingerprint (``card.gl.period_run.document_fingerprint``, the run's fingerprint version) of the
   document as the posting read it; a fill also with the supplier VAT registration and the company diesel VAT
   basis the run was built with. Amounts are never compared with invoice amounts: the run holds GROSS source
   amounts and the posting books the net part of a VAT-inclusive diesel price; the fingerprint covers the
   source amounts themselves. VAT is never inferred;
5. the run is current: no document joined, left or changed since it was built (``check_current``).

Concurrency: in a real posting (not the preview) the run rows of the company-month are read with a locking read
(``frappe.qb ... for_update``), so an approval, a return or a cancel of the run waits for the posting or is seen
by it; step 5 rebuilds the live snapshot with locking reads (``check_current(for_update=True)``): the selection,
every source document with its rows, the company's settings row and the fill suppliers. A change committed by
another request after this request began is therefore seen, and none can be committed until the posting
commits. Step 4 reads the documents as the posting read them (the request's snapshot), so an invoice line built
from an older read than the approved run is refused too.

Reads only: the gate writes nothing; it never approves, builds or changes a run."""

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.utils import cint, cstr

from card.settings import company_setting

DOCTYPE = "Card Period Run"
FILL = "Project Diesel Fill"
_SIDE = {"Supplier": ("supplier_side", "supplier"), "Customer": ("customer_side", "customer")}


class PeriodRunRequiredError(frappe.ValidationError):
	"""The company requires an approved, current period run and the posting does not have one."""


def required(company: str) -> bool:
	"""True only when the company's row sets ``require_period_approval``; no row or 0: the posting as before."""
	return cint(company_setting(company, "require_period_approval")) == 1


def _period(month, year) -> tuple[str, int]:
	return "%02d" % int(month), int(year)


def _active_run_name(company: str, month, year, lock: bool) -> str | None:
	"""The active (draft or submitted) run of the company-month. lock: every run row of the company-month is read
	with a locking read, so a concurrent approval, return, cancel or new run of the month is serialised."""
	from card.gl import period_run

	if not lock:
		return period_run.active_run(company, month, year)
	month, year = _period(month, year)
	run = frappe.qb.DocType(DOCTYPE)
	rows = (
		frappe.qb.from_(run)
		.select(run.name, run.docstatus, run.version)
		.where(run.company == company)
		.where(run.month == month)
		.where(run.year == year)
		.orderby(run.version, order=Order.desc)
		.for_update()
	).run(as_dict=True)
	return next((r.name for r in rows if cint(r.docstatus) < 2), None)


def _refuse(message: str):
	frappe.throw(message, PeriodRunRequiredError, title=_("Approved period run required"))


def status_refusal(company: str, month, year, run) -> str | None:
	"""Steps 1-3 of the module docstring for a loaded run (or None): the reason posting is refused, or None."""
	from card.gl import period_run

	month, year = _period(month, year)
	if run is None:
		return _(
			"Company {0} requires an approved period run before posting {1}/{2}, and there is none. Build the period run, submit it and have an accountant approve it."
		).format(company, month, year)
	if run.docstatus == 0:
		return _(
			"Period run {0} for {1}/{2} is still a draft. Submit it and have an accountant approve it before posting."
		).format(run.name, month, year)
	if run.approval_status == period_run.RETURNED:
		return _(
			"Period run {0} for {1}/{2} was returned for correction ({3}). Cancel and amend it, then have the new version approved before posting."
		).format(run.name, month, year, run.return_reason or "-")
	if run.approval_status != period_run.APPROVED:
		return _(
			"Period run {0} for {1}/{2} is waiting for an accountant's approval; posting needs an approved period run."
		).format(run.name, month, year)
	if not (
		cint(run.approved_version) == cint(run.version)
		and run.approved_hash
		and run.approved_hash == run.snapshot_hash
	):
		return _(
			"The approval of period run {0} is not for its current version. Cancel and amend the run and have the new version approved before posting."
		).format(run.name)
	if cint(run.self_approved) and period_run.effective_self_approval_rule(run) == period_run.RULE_REFUSE:
		return _(
			"Period run {0} was approved by one of its preparers, and the self-approval rule of company {1} is Refuse. Cancel and amend the run and have another accountant approve the new version."
		).format(run.name, company)
	return None


def stale_refusal(run, state) -> str | None:
	"""Step 5: the reason when the run is not current, or None."""
	if state.current:
		return None
	return _(
		"The CARD documents of {0}/{1} changed after period run {2} was approved (added: {3}; removed: {4}; changed: {5}). Cancel and amend the run and have the new version approved before posting."
	).format(
		run.month,
		run.year,
		run.name,
		", ".join(state.added) or "-",
		", ".join(state.removed) or "-",
		", ".join(state.changed) or "-",
	)


def _load(company, month, year, lock):
	name = _active_run_name(company, month, year, lock)
	return frappe.get_doc(DOCTYPE, name, for_update=lock or None) if name else None


def require_run_state(company: str, month, year) -> None:
	"""Steps 1-3 only, before a rebuild deletes the old draft (the build that follows runs every step)."""
	if not required(company):
		return
	reason = status_refusal(company, month, year, _load(company, month, year, lock=False))
	if reason:
		_refuse(reason)


def _source_mismatches(run, party_type, party, sources, row, vat_registered) -> list[str]:
	"""Step 4: the sources the posting bills that the run does not hold as the posting read them."""
	from card.gl import period_run

	flag, party_field = _SIDE[party_type]
	version = cint(run.fingerprint_version) or period_run.FINGERPRINT_VERSION
	stored = {(r.source_doctype, r.source_name): r for r in run.get("sources") or []}
	out = []
	has_fill = False
	for doctype, rows in sources.items():
		for name, _amount in rows:
			held = stored.get((doctype, name))
			if not held or not cint(held.get(flag)):
				out.append(_("{0} (not in the run on this side)").format(name))
				continue
			if cstr(held.get(party_field)) != cstr(party):
				out.append(_("{0} (another party in the run)").format(name))
				continue
			# the document as the posting read it (the request's snapshot, the same reads as the invoice lines)
			if held.content_hash != period_run.document_fingerprint(frappe.get_doc(doctype, name), version):
				out.append(_("{0} (changed since the run was built)").format(name))
				continue
			if doctype == FILL:
				has_fill = True
				if cint(held.get("supplier_vat_registered")) != (1 if vat_registered else 0):
					out.append(_("{0} (supplier VAT registration changed)").format(name))
	if has_fill and row is not None:
		basis = cstr(row.get("diesel_price_vat_basis"))
		if basis != cstr(run.get("diesel_vat_basis")):
			out.append(
				_("diesel price VAT basis {0} (the run was built with {1})").format(
					basis or "-", cstr(run.get("diesel_vat_basis")) or "-"
				)
			)
	return out


def check_posting(
	company: str,
	party_type: str,
	party: str,
	month,
	year,
	sources: dict,
	row=None,
	vat_registered=None,
	lock: bool = False,
) -> str | None:
	"""The gate of one monthly posting (module docstring). Returns the run name, or None when the company does not
	require a run; raises PeriodRunRequiredError otherwise. sources: the posting's {doctype: [(name, amount)]}.
	lock: True inside a real posting (locking reads, module docstring); False for the preview."""
	if not required(company):
		return None
	from card.gl import period_run

	run = _load(company, month, year, lock)
	reason = status_refusal(company, month, year, run)
	if reason:
		_refuse(reason)
	mismatches = _source_mismatches(run, party_type, party, sources, row, vat_registered)
	if mismatches:
		_refuse(
			_(
				"Approved period run {0} does not hold these documents of {1} {2} as the posting would bill them: {3}. Cancel and amend the run and have the new version approved before posting."
			).format(run.name, _(party_type), party, "; ".join(mismatches))
		)
	reason = stale_refusal(run, period_run.check_current(run, for_update=lock))
	if reason:
		_refuse(reason)
	return run.name


def run_state(company: str, month, year) -> dict:
	"""For the posting screen: whether the company requires a run, the run's state and, when posting is refused,
	why. Reads only (it rebuilds the live snapshot of the run). The caller checks role and company. No amounts."""
	from card.gl import period_run

	month, year = _period(month, year)
	out = frappe._dict(required=required(company), company=company, month=month, year=year, run=None)
	run = _load(company, month, year, lock=False)
	if run is not None and not frappe.has_permission(DOCTYPE, "read", run):
		out.refusal = out.would_refuse = _(
			"Posting needs an approved, current period run of company {0} for {1}/{2}, and you cannot open it."
		).format(company, month, year)
		if not out.required:
			out.refusal = None
		return out
	if run is not None:
		state = period_run.check_current(run)
		out.update(
			run=run.name,
			version=cint(run.version),
			docstatus=run.docstatus,
			approval_status=run.approval_status,
			self_approved=cint(run.self_approved),
			self_approval_rule=period_run.effective_self_approval_rule(run),
			current=state.current,
			added=state.added,
			removed=state.removed,
			changed=state.changed,
		)
		reason = status_refusal(company, month, year, run) or stale_refusal(run, state)
	else:
		reason = status_refusal(company, month, year, None)
	out.refusal = reason if out.required else None
	out.would_refuse = reason
	return out
