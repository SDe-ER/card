# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-141 (#41, closure plan WP-M1, C-16 / O-08): dated rate agreements, built opt-in and not wired yet.

A Card Rate Agreement (submittable) gives, for one company, the rates per basis (hour, day, month, quantity unit)
and the paying party per cost category of one equipment, or of every equipment of one equipment type, with a
supplier and/or a customer, optionally for one project and one work zone, between ``valid_from`` and ``valid_to``
(empty = open-ended). A changed rate is a new agreement (cancel and amend, or a new one from a new date): a
submitted agreement is never edited.

``resolve()`` is the one lookup. Nothing calls it yet: monthly cards, posting and transport keep the equipment
rates until the opt-in wiring (WP-M2..M4) is merged and enabled per company. It never picks between several
matches: more than one active agreement is an error the user resolves (#41 "no automatic billing when several
match").

The agreement key (``agreement_key``) is company, equipment, equipment type, supplier, customer, project and work
zone. Two submitted agreements with the same key and overlapping dates are refused. Agreements with different keys
may overlap (for example one for an equipment type and one for a single equipment of that type); ``resolve()``
then refuses the date on which both match, so the user ends one of them."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

DOCTYPE = "Card Rate Agreement"
RESPONSIBILITY_TABLE = "responsibilities"
KEY_FIELDS = ("company", "equipment", "equipment_type", "supplier", "customer", "project", "zone")
RATE_FIELDS = ("hourly_rate", "daily_rate", "monthly_rate", "quantity_rate")
PARTY_TYPES = ("Supplier", "Customer")
PAYER_FIELD = {"Customer": "customer", "Supplier": "supplier", "Other party": "other_party"}


class AmbiguousAgreementError(frappe.ValidationError):
	"""More than one active agreement matches: the caller must not choose one."""


class OverlappingAgreementError(frappe.ValidationError):
	"""A submitted agreement with the same key already covers part of the period."""


def _value(value):
	return (value or "").strip() if isinstance(value, str) else (value or "")


def agreement_key(doc):
	"""The tuple that two agreements must not share over overlapping dates (empty values compare equal)."""
	return tuple(_value(doc.get(field)) for field in KEY_FIELDS)


def _overlaps(from_a, to_a, from_b, to_b):
	"""Two closed date ranges overlap; an empty end is open-ended."""
	from_a, from_b = getdate(from_a), getdate(from_b)
	to_a = getdate(to_a) if to_a else None
	to_b = getdate(to_b) if to_b else None
	return (to_b is None or from_a <= to_b) and (to_a is None or from_b <= to_a)


def _in_force(row, date):
	return getdate(row.valid_from) <= date and (not row.valid_to or getdate(row.valid_to) >= date)


def _normalise_party(party):
	"""(party_type, name) from a (type, name) pair, a {"party_type", "party"} dict or a plain name (None type:
	matched against the supplier and the customer). None for no party filter."""
	if not party:
		return None
	if isinstance(party, dict):
		party_type, name = party.get("party_type"), party.get("party")
	elif isinstance(party, list | tuple):
		if len(party) != 2:
			frappe.throw(_("CARD rate agreement: a party is given as (party type, party)."))
		party_type, name = party
	else:
		party_type, name = None, party
	if party_type and party_type not in PARTY_TYPES:
		frappe.throw(_("CARD rate agreement: party type {0} is not Supplier or Customer.").format(party_type))
	return (party_type, name) if name else None


def _party_matches(row, party):
	if party is None:
		return True
	party_type, name = party
	if party_type == "Supplier":
		return row.supplier == name
	if party_type == "Customer":
		return row.customer == name
	return name in (row.supplier, row.customer)


def resolve(company, equipment, party, date, project=None, zone=None):
	"""The one submitted Card Rate Agreement in force for ``equipment`` of ``company`` on ``date``, or None.

	An agreement matches when it is submitted, of ``company``, in force on ``date`` (``valid_from`` <= date <=
	``valid_to``, empty end = open), for ``equipment`` itself or (no equipment on the agreement) for its equipment
	type, for ``party`` (a Supplier/Customer pair matches that side, a plain name either side, None any party), for
	``project`` or for no project (``project=None``: agreements without a project only) and, when ``zone`` is given,
	for that zone or for no zone (``zone=None``: the zone is not considered).

	Returns None when nothing matches, the agreement document when exactly one matches, and raises
	``AmbiguousAgreementError`` naming every match when more than one does: the caller never picks one.
	Raises ValidationError when the equipment does not exist or belongs to another company.

	A server-side helper, not a whitelisted method: it reads agreements without a permission check, so a caller
	checks the permission of its own document (the card, the posting) before using the result."""
	if not company or not equipment or not date:
		frappe.throw(_("CARD rate agreement: company, equipment and date are required to find an agreement."))
	date = getdate(date)
	equipment_row = frappe.db.get_value(
		"Card Equipment", equipment, ["company", "equipment_type"], as_dict=True
	)
	if not equipment_row:
		frappe.throw(_("CARD rate agreement: equipment {0} does not exist.").format(equipment))
	if equipment_row.company != company:
		frappe.throw(
			_("CARD rate agreement: equipment {0} does not belong to company {1}.").format(equipment, company)
		)
	party = _normalise_party(party)
	zone = _value(zone)
	rows = frappe.get_all(
		DOCTYPE,
		filters={"docstatus": 1, "company": company, "valid_from": ["<=", date]},
		fields=["name", "valid_from", "valid_to", *KEY_FIELDS[1:]],
		order_by="valid_from desc, name asc",
	)
	matches = []
	for row in rows:
		if not _in_force(row, date):
			continue
		if row.equipment:
			if row.equipment != equipment:
				continue
		elif not equipment_row.equipment_type or row.equipment_type != equipment_row.equipment_type:
			continue
		if row.project and row.project != project:
			continue  # another project, or a project agreement while no project is given
		if zone and _value(row.zone) not in ("", zone):
			continue
		if not _party_matches(row, party):
			continue
		matches.append(row.name)
	if not matches:
		return None
	if len(matches) > 1:
		frappe.throw(
			_(
				"CARD rate agreement: {0} active agreements match equipment {1} on {2}: {3}. "
				"End or cancel all but one; CARD does not choose between them."
			).format(len(matches), equipment, frappe.format(date, "Date"), ", ".join(matches)),
			AmbiguousAgreementError,
		)
	return frappe.get_doc(DOCTYPE, matches[0])


# ---------- controller rules (called by CardRateAgreement) ----------
def validate_agreement(doc):
	_check_dates(doc)
	_check_scope(doc)
	_check_rates(doc)
	_check_responsibilities(doc)
	if doc.docstatus < 2:
		check_overlap(doc)


def _check_dates(doc):
	if doc.valid_to and getdate(doc.valid_to) < getdate(doc.valid_from):
		frappe.throw(_("CARD rate agreement: the end date is before the start date."))


def _check_scope(doc):
	if not doc.equipment and not doc.equipment_type:
		frappe.throw(_("CARD rate agreement: choose an equipment or an equipment type."))
	if not doc.supplier and not doc.customer:
		frappe.throw(_("CARD rate agreement: choose a supplier, a customer or both."))
	if doc.equipment:
		row = frappe.db.get_value(
			"Card Equipment", doc.equipment, ["company", "equipment_type"], as_dict=True
		)
		if not row:
			frappe.throw(_("CARD rate agreement: equipment {0} does not exist.").format(doc.equipment))
		if row.company != doc.company:
			frappe.throw(
				_("CARD rate agreement: equipment {0} belongs to another company.").format(doc.equipment),
				frappe.ValidationError,
			)
		if doc.equipment_type and doc.equipment_type != row.equipment_type:
			frappe.throw(
				_("CARD rate agreement: equipment {0} is not of equipment type {1}.").format(
					doc.equipment, doc.equipment_type
				)
			)
	if doc.project:
		project_company = frappe.db.get_value("Project", doc.project, "company")
		if project_company != doc.company:
			frappe.throw(
				_("CARD rate agreement: project {0} belongs to another company.").format(doc.project),
				frappe.ValidationError,
			)
	if doc.get("amended_from"):
		original_company = frappe.db.get_value(DOCTYPE, doc.amended_from, "company")
		if original_company != doc.company:
			frappe.throw(
				_("CARD rate agreement: an amendment keeps the company of agreement {0}.").format(
					doc.amended_from
				),
				frappe.ValidationError,
			)
	if doc.zone:
		doc.zone = doc.zone.strip()


def _check_rates(doc):
	# O-17: rates are in the company currency (no conversion); the field is fetched and read only
	doc.currency = frappe.get_cached_value("Company", doc.company, "default_currency") or doc.currency
	for field in RATE_FIELDS:
		if flt(doc.get(field)) < 0:
			frappe.throw(_("CARD rate agreement: a rate cannot be negative."))
	if flt(doc.quantity_rate) > 0 and not doc.quantity_uom:
		frappe.throw(_("CARD rate agreement: a rate per quantity needs its unit."))
	if not any(flt(doc.get(field)) > 0 for field in RATE_FIELDS) and not doc.get(RESPONSIBILITY_TABLE):
		frappe.throw(_("CARD rate agreement: enter at least one rate or one cost responsibility row."))


def _check_responsibilities(doc):
	from card.company_scope import check_child_companies

	rows = doc.get(RESPONSIBILITY_TABLE) or []
	if not rows:
		return
	check_child_companies(doc, RESPONSIBILITY_TABLE, "equipment")
	totals, seen = {}, set()
	for row in rows:
		if flt(row.split_percent) <= 0 or flt(row.split_percent) > 100:
			frappe.throw(
				_("CARD rate agreement: row {0}: the share must be more than 0% and at most 100%.").format(
					row.idx
				)
			)
		payer_field = PAYER_FIELD.get(row.paid_by)
		for field in PAYER_FIELD.values():
			if field != payer_field and row.get(field):
				row.set(field, None)  # only the party of the chosen payer is kept
		if payer_field and not _value(row.get(payer_field)):
			frappe.throw(
				_("CARD rate agreement: row {0}: name the paying party ({1}).").format(
					row.idx, _(row.paid_by)
				)
			)
		if row.equipment:
			if doc.equipment and row.equipment != doc.equipment:
				frappe.throw(
					_("CARD rate agreement: row {0}: the agreement is for equipment {1} only.").format(
						row.idx, doc.equipment
					)
				)
			if (
				not doc.equipment
				and frappe.db.get_value("Card Equipment", row.equipment, "equipment_type")
				!= doc.equipment_type
			):
				frappe.throw(
					_("CARD rate agreement: row {0}: equipment {1} is not of equipment type {2}.").format(
						row.idx, row.equipment, doc.equipment_type
					)
				)
		payer = (row.paid_by, _value(row.get(payer_field)) if payer_field else "")
		marker = (row.cost_category, row.equipment or "", payer)
		if marker in seen:
			frappe.throw(
				_("CARD rate agreement: row {0}: the same payer is entered twice for {1}.").format(
					row.idx, _(row.cost_category)
				)
			)
		seen.add(marker)
		group = (row.cost_category, row.equipment or "")
		totals[group] = totals.get(group, 0) + flt(row.split_percent)
	for (category, equipment), total in totals.items():
		if abs(total - 100) > 0.001:
			frappe.throw(
				_("CARD rate agreement: the shares for {0}{1} add up to {2}%, not 100%.").format(
					_(category), f" ({equipment})" if equipment else "", flt(total, 3)
				)
			)


def check_overlap(doc):
	"""Refuse a draft or a submit whose key and dates overlap a submitted agreement. At submit the company row is
	locked (SELECT ... FOR UPDATE, no write), so two agreements of one company are submitted one after the other
	and cannot both pass this check."""
	if doc.docstatus == 1:
		frappe.db.get_value("Company", doc.company, "name", for_update=True)
	key = agreement_key(doc)
	filters = {"docstatus": 1, "company": doc.company, "name": ["!=", doc.name or ""]}
	for field in ("equipment", "equipment_type", "supplier", "customer", "project"):
		filters[field] = doc.get(field) or ["is", "not set"]
	rows = frappe.get_all(DOCTYPE, filters=filters, fields=["name", "valid_from", "valid_to", *KEY_FIELDS])
	for row in rows:
		if agreement_key(row) != key:
			continue  # the work zone differs
		if _overlaps(doc.valid_from, doc.valid_to, row.valid_from, row.valid_to):
			frappe.throw(
				_(
					"CARD rate agreement: agreement {0} has the same equipment, parties, project and zone and is in force "
					"in this period. A changed rate is a new agreement from a later date: end or cancel {0} first."
				).format(row.name),
				OverlappingAgreementError,
			)
