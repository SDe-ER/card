// Report: "Equipment Partial Margin" — read-only; partial margin, excludes depreciation, labour, insurance and overhead
frappe.query_reports["Equipment Partial Margin"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Autocomplete",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			get_query: () => ({ query: "card.api.card_company_options" }),
		},
		{
			fieldname: "from_date",
			label: __("From date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: __("To date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Autocomplete",
			get_query: () => ({
				query: "card.api.card_project_options",
				params: { company: frappe.query_report.get_filter_value("company") },
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
