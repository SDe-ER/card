// Report: "Equipment Diesel Consumption" — filters
frappe.query_reports["Equipment Diesel Consumption"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			get_query: () => ({ query: "card.api.card_companies_query" }),
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "from_date", label: __("From date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To date"), fieldtype: "Date" },
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			get_query: () => ({
				query: "card.api.card_projects_query",
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
		{
			fieldname: "equipment",
			label: __("Equipment"),
			fieldtype: "Link",
			options: "Card Equipment",
		},
	],
};
