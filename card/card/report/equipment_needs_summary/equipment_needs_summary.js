// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE

frappe.query_reports["Equipment Needs Summary"] = {
	filters: [
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "approval_status",
			label: __("Management approval"),
			fieldtype: "Select",
			options: ["", "Pending", "Approved"],
			default: "Pending",
		},
	],
};
