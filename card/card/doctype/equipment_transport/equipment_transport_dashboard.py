# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""FR-152 (#35 "downstream documents are listed"): the form's Connections list the documents built from this
transport (read only; Frappe's standard dashboard data). Internal links come from the transport's own read-only
fields; the assignment is the one this transport created."""

from frappe import _


def get_data():
	return {
		"fieldname": "amended_from",
		"internal_links": {
			"GL Posting Log": "gl_posting",
			"Purchase Invoice": "purchase_invoice",
			"Card Equipment Assignment": "created_assignment",
		},
		"transactions": [
			{"label": _("Postings and invoices"), "items": ["GL Posting Log", "Purchase Invoice"]},
			{"label": _("Created assignment"), "items": ["Card Equipment Assignment"]},
			{"label": _("Amended copies"), "items": ["Equipment Transport"]},
		],
	}
