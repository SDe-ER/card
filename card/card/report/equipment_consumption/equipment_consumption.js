// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

frappe.query_reports["Equipment Consumption"] = {
	filters: [
		{ fieldname: "from_date", label: __("From date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To date"), fieldtype: "Date" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{ fieldname: "equipment", label: __("Equipment"), fieldtype: "Link", options: "Card Equipment" },
	],
};
