# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""v4.0.0 operator page: a mobile page where the operator asks for his machine's needs
with his own Frappe account (no Desk). Server-rendered and translated by Frappe."""

import frappe
from frappe import _

from card.materials import portal_context

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/equipment-needs"
		raise frappe.Redirect
	context.no_cache = 1
	context.show_sidebar = False
	context.title = _("My equipment needs")
	context.data = portal_context()
	context.labels_json = frappe.as_json(
		{
			"part": _("Part or consumable"),
			"tool": _("Tool"),
			"item_placeholder": _("Search an item or describe it"),
			"qty": _("Quantity"),
			"reason": _("Reason"),
			"remove": _("Remove"),
			"no_lines": _("Add at least one line with a quantity."),
			"sent": _("Your request was sent to the supervisor."),
		}
	)
	return context
