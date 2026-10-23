// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

frappe.query_reports["Equipment Make Model Values"] = {
	filters: [
		{
			fieldname: "unlinked_only",
			label: __("Without equipment model only"),
			fieldtype: "Check",
			default: 1,
		},
	],
};
