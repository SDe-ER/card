# Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
# For license information, please see LICENSE
"""H-CARD-3: read-only whitelisted functions accept GET only. With methods=None Frappe
allows GET, POST, PUT and DELETE and validates CSRF for the last three only."""

import frappe
from frappe.tests import IntegrationTestCase

READ_ONLY = (
	"card.api.party_figures",
	"card.api.card_suppliers_query",
	"card.api.card_customers_query",
	"card.api.card_project_options",
	"card.api.report_defaults",
	"card.api.card_company_options",
	"card.diesel.get_card_diesel",
	"card.card.doctype.card_equipment.card_equipment.get_shift_heatmap",
)


# Read-only, but called by the Autocomplete control, which calls frappe.call without a type (POST).
AUTOCOMPLETE_SOURCES = ("card.api.card_project_options", "card.api.card_company_options")


class TestReadEndpointsGetOnly(IntegrationTestCase):
	def test_read_only_functions_allow_expected_methods(self):
		for path in READ_ONLY:
			with self.subTest(path=path):
				fn = frappe.get_attr(path)
				expected = ["GET", "POST"] if path in AUTOCOMPLETE_SOURCES else ["GET"]
				self.assertEqual(sorted(frappe.allowed_http_methods_for_whitelisted_func[fn]), expected)
