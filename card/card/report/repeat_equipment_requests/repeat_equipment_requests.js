// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

frappe.query_reports["Repeat Equipment Requests"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "equipment", label: __("Equipment"), fieldtype: "Link", options: "Card Equipment" },
	],
};
