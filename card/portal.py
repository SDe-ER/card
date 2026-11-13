# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Party portal helpers (FR-161, closure plan WP-O1).

Resolve a logged-in portal user to a ``(party_type, party)`` pair through the
standard ERPNext Contact → Dynamic Link chain, and list / load the user's own
submitted Card Monthly Card records inside the companies the user is permitted
to read.

Scope (WP-O1 scaffold only):

* No ``@frappe.whitelist`` here. The helpers are called by the ``card-portal``
  www pages (``card/www/card-portal/``) and exercised by tests. No REST
  endpoint is exposed.
* ``card/hooks.py`` is not touched in this wave. ``website_route_rules`` and
  the ``has_website_permission`` entry for ``Card Monthly Card`` are WP-O2's
  scope (wave 10). Until O2 wires them, Frappe's default page dispatch still
  reaches the pages, but every view handler short-circuits to 404 when
  ``Card Company Settings.enable_party_portal`` is 0 for every company.
* No DocPerm change, no role grant, no ``ignore_permissions``. Under WP-O1
  alone the portal is doubly inert: the enable flag is 0 on every company
  seed, and the portal roles still have no read DocPerm on Card Monthly Card
  (added by WP-O2 only on the owner's explicit approval, O-16).

The authorization boundary is the party resolution: the party is always read
from the server session (``get_party_from_user``), never from a client
argument. Callers that trust a ``(party_type, party)`` input must have
derived it from the session themselves — tests cover this (Lesson 1).
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

PARTY_DOCTYPES: tuple[str, ...] = ("Supplier", "Customer")
"""Party DocTypes the portal resolves. Order is significant: Supplier wins
when a Contact links to both, matching the Card Monthly Card field it reads
(``supplier`` before ``customer``)."""

_PARTY_FIELD = {"Supplier": "supplier", "Customer": "customer"}
"""Map of party doctype → the matching Card Monthly Card link field.
Monthly cards carry both ``supplier`` and ``customer`` (``card_monthly_card.json``
fields 28–29), so a party sees only the cards where it appears on its own
side."""

CARD_LIST_FIELDS: tuple[str, ...] = (
	"name",
	"company",
	"equipment",
	"equipment_name",
	"project",
	"month",
	"year",
	"shift",
	"supplier",
	"customer",
	"total_working_hours",
)
"""Columns the landing page shows on the list. Money fields (``amount``,
``customer_amount``, …) are not included here because WP-F (FR-007, wave 7)
moves them to permlevel 1; the list intentionally does not depend on them."""


def _portal_enabled(company: str | None = None) -> bool:
	"""Return True when ``company`` has ``enable_party_portal`` = 1 on its
	Card Company Settings row, or (with ``company`` empty) when any row does.

	The flag defaults to 0 on every company so this returns False on a fresh
	install, which is why every view handler 404s by default (hides
	enablement; O-16).

	The lookup goes through ``frappe.db.get_value`` on the DocType's own
	table: this is the pre-authentication server-state gate (a Guest or an
	anonymous portal user reaches this before any DocPerm check) and must
	see the raw state, not a permission-filtered subset. It is NOT a bypass
	that widens any user's access: the function returns a single boolean,
	no row content, and every caller still runs the own-party +
	permitted-company checks after it.
	"""

	filters: dict[str, object] = {"enable_party_portal": 1}
	if company:
		filters["company"] = company
	return bool(
		frappe.db.get_value(
			"Card Company Settings",
			filters,
			"name",
		)
	)


def get_party_from_user(user: str | None = None) -> tuple[str, str] | None:
	"""Return ``(party_type, party)`` for ``user`` through the Contact chain.

	Lookup: ``Contact.email_id`` = user → Contact → ``Contact.links`` Dynamic
	Link rows → first link whose ``link_doctype`` is one of
	``PARTY_DOCTYPES``. Ordered by the child row's ``idx`` so the Contact's
	primary party wins on the form.

	Returns ``None`` when the user is Guest / Administrator, when no Contact
	is linked by email, or when the Contact has no Supplier / Customer link.
	The party is never taken from a client argument: callers that need a
	party for the current request must go through this function. Matches the
	official ERPNext portal pattern (``erpnext/portal/utils.py:party_exists``
	and ``frappe/contacts/doctype/address/address.py:has_website_permission``).
	"""

	user = user or frappe.session.user
	if user in ("Guest", "Administrator") or not user:
		return None

	contact_name = frappe.db.get_value("Contact", {"email_id": user}, "name")
	if not contact_name:
		return None

	links = frappe.get_all(
		"Dynamic Link",
		filters={
			"parent": contact_name,
			"parenttype": "Contact",
			"parentfield": "links",
			"link_doctype": ["in", PARTY_DOCTYPES],
		},
		fields=["link_doctype", "link_name"],
		order_by="idx",
	)
	for link in links:
		if link.link_doctype in PARTY_DOCTYPES and link.link_name:
			return (link.link_doctype, link.link_name)
	return None


def _permitted_companies(user: str) -> list[str] | None:
	"""Return the companies ``user`` is restricted to for Card Monthly Card,
	or ``None`` when the user reads every company (no extra filter needed).

	Mirrors ``card.party_registry._restricted_companies`` and is kept
	inline here so the portal has no import cycle with the registry
	module."""

	from card.party_registry import _restricted_companies

	return _restricted_companies(user, "Card Monthly Card")


def list_party_cards(
	party_type: str,
	party: str,
	user: str | None = None,
) -> list[frappe._dict]:
	"""Return the submitted Card Monthly Card rows for ``(party_type, party)``
	inside the companies ``user`` (default: the session user) is permitted to
	read.

	Filters:

	* ``docstatus = 1`` — drafts and cancelled rows never reach a portal view;
	* the party link field (``supplier`` for Supplier, ``customer`` for
	  Customer) equals ``party``;
	* ``company`` is restricted to the user's permitted set when
	  ``_permitted_companies`` returns a bounded list (second-company
	  isolation).

	The ``(party_type, party)`` pair is trusted and must come from
	``get_party_from_user``; the forgery test (Lesson 1) covers the www index
	handler that never reads a party from client input. Returns ``[]`` for an
	unknown party doctype, an empty party, or an empty permitted-company set.
	"""

	if party_type not in PARTY_DOCTYPES or not party:
		return []

	field = _PARTY_FIELD[party_type]
	filters: dict[str, object] = {field: party, "docstatus": 1}

	user = user or frappe.session.user
	companies = _permitted_companies(user)
	if companies is not None:
		if not companies:
			return []
		filters["company"] = ["in", list(companies)]

	return frappe.get_all(
		"Card Monthly Card",
		filters=filters,
		fields=list(CARD_LIST_FIELDS),
		order_by="year desc, month desc, name desc",
		limit=500,
	)


def get_party_card(
	name: str,
	user: str | None = None,
) -> frappe._dict | None:
	"""Load one Card Monthly Card by ``name`` after the same filters as
	``list_party_cards``.

	The party is resolved from ``user`` (via ``get_party_from_user``); a card
	is returned only when the stored card's party link equals that resolved
	party and the stored company is inside the user's permitted set. Returns
	``None`` when any check fails — never raises, so an unauthorised view
	handler can 404 the way it does for a missing row. The lookup goes
	through ``frappe.db.get_value`` with explicit filters so a user that
	cannot read Card Monthly Card (no DocPerm) gets ``None``, matching the
	scaffold's inert posture."""

	if not name:
		return None

	user = user or frappe.session.user
	party = get_party_from_user(user)
	if not party:
		return None
	party_type, party_name = party
	field = _PARTY_FIELD[party_type]

	row = frappe.db.get_value(
		"Card Monthly Card",
		{"name": name, field: party_name, "docstatus": 1},
		list(CARD_LIST_FIELDS),
		as_dict=True,
	)
	if not row:
		return None

	companies = _permitted_companies(user)
	if companies is not None and row.company not in companies:
		return None

	return row
