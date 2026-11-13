# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""Landing page of the party portal (FR-161, WP-O1, scaffold only).

Shows the submitted Card Monthly Card rows that belong to the logged-in
portal user's Supplier or Customer, inside the companies the user is
permitted to read. Guest → login. The page is wrapped by the standard web
template, so Frappe sets the header, language direction and footer.

Scaffold rules (WP-O1):

* When no company has ``enable_party_portal`` = 1, this view raises
  ``PageDoesNotExistError`` (HTTP 404) so the portal's existence stays
  hidden until the owner enables it on a company (O-16); not a 403, which
  would reveal that the feature exists.
* The party is always resolved from the session (``get_party_from_user``);
  a client ``?party=…`` query arg is ignored (Lesson 1).
* The route ``/card-portal`` is not wired in ``hooks.py`` by this wave
  (WP-O2 adds ``website_route_rules`` and ``has_website_permission`` in
  wave 10). Frappe's default page dispatch still reaches this handler by
  file location, which is why the enable-flag guard is the first thing the
  handler does.
"""

from __future__ import annotations

import frappe
from frappe import _

from card.portal import get_party_from_user, list_party_cards

no_cache = 1


def get_context(context):
	# 1. Enable guard first — 404 (not 403) when the portal is off on every
	# company, to avoid revealing enablement (O-16).
	from card.portal import _portal_enabled

	if not _portal_enabled():
		raise frappe.PageDoesNotExistError

	# 2. Guest → standard Frappe login redirect, preserving the return path.
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/card-portal"
		raise frappe.Redirect

	# 3. Resolve the party from the session — never from a client argument
	# (Lesson 1: the ``party`` and ``party_type`` query args are ignored).
	party = get_party_from_user()
	context.no_cache = 1
	context.show_sidebar = False
	context.title = _("My cards")
	context.party = None
	context.party_type = None
	context.cards = []
	if party:
		party_type, party_name = party
		context.party_type = party_type
		context.party = party_name
		context.cards = list_party_cards(party_type, party_name)
	return context
