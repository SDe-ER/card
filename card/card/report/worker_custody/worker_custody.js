// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

frappe.query_reports["Worker Custody"] = {
	filters: [
		{ fieldname: "employee", label: __("Employee"), fieldtype: "Link", options: "Employee" },
	],
};
