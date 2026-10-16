// Report: "Operating Cost by Project" — filters
frappe.query_reports["Operating Cost by Project"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Autocomplete",
			reqd: 1,
			get_query: () => ({ query: "card.api.card_company_options" }),
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "from_date", label: __("From date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To date"), fieldtype: "Date" },
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Autocomplete",
			get_query: () => ({
				query: "card.api.card_project_options",
				params: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
	],
};
