# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-152 (#35 "downstream documents are listed"): the form's Connections list the documents built from this card
(read only; Frappe's standard dashboard data). Internal links come from the card's own read-only fields."""

from frappe import _


def get_data():
	return {
		"fieldname": "amended_from",
		"internal_links": {
			"GL Posting Log": "gl_posting",
			"Purchase Invoice": "purchase_invoice",
			"Sales Invoice": "sales_invoice",
		},
		"transactions": [
			{
				"label": _("Postings and invoices"),
				"items": ["GL Posting Log", "Purchase Invoice", "Sales Invoice"],
			},
			{"label": _("Amended copies"), "items": ["Card Monthly Card"]},
		],
	}
