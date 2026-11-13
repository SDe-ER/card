# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Single-card page of the party portal (FR-161, WP-O1, scaffold only).

Shows one submitted Card Monthly Card that belongs to the logged-in portal
user's party. Takes the card name from ``?name=`` on this scaffold view
(WP-O2 adds a ``website_route_rules`` entry in wave 10 that rewrites
``/card-portal/<card-name>`` to this handler so the URL becomes clean).

Scaffold rules match the landing page:

* ``PageDoesNotExistError`` (HTTP 404) when the portal is off on every
  company (hides enablement; O-16) and when the card does not pass the
  own-party + permitted-company filter (``card.portal.get_party_card``
  returns ``None`` in both cases, which keeps "not found" and "not yours"
  indistinguishable from the viewer's side);
* Guest → standard Frappe login redirect;
* Party resolved from the session — never from a client argument
  (Lesson 1).
"""

from __future__ import annotations

import frappe
from frappe import _

from card.portal import get_party_card, get_party_from_user

no_cache = 1


def get_context(context):
	from card.portal import _portal_enabled

	if not _portal_enabled():
		raise frappe.PageDoesNotExistError

	if frappe.session.user == "Guest":
		# Keep the user's requested card in the return path so the login
		# round-trip lands back on the same view.
		name = (frappe.form_dict or {}).get("name") or ""
		target = "/card-portal/view"
		if name:
			target = f"{target}?name={frappe.utils.quoted(name)}"
		frappe.local.flags.redirect_location = f"/login?redirect-to={target}"
		raise frappe.Redirect

	# The party is derived from the session, never the request.
	party = get_party_from_user()
	context.no_cache = 1
	context.show_sidebar = False
	context.party = None
	context.party_type = None
	context.card = None
	if not party:
		context.title = _("My card")
		return context
	party_type, party_name = party
	context.party_type = party_type
	context.party = party_name

	# The card name is the only request input this handler accepts; the
	# own-party + permitted-company filter inside ``get_party_card`` is the
	# authorization boundary.
	name = (frappe.form_dict or {}).get("name") or ""
	card = get_party_card(name) if name else None
	if not card:
		raise frappe.PageDoesNotExistError

	context.card = card
	context.title = _("Card {0}").format(card.name)
	return context
