// Report: "Unbilled Card Work" — read-only; submitted cards no invoice or linked journal entry recognises yet
frappe.query_reports["Unbilled Card Work"] = {
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
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "side",
			label: __("Billing side"),
			fieldtype: "Select",
			options: [
				{ value: "All", label: __("Both billing sides") },
				{ value: "Supplier", label: __("Supplier side") },
				{ value: "Customer", label: __("Customer side") },
			],
			default: "All",
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
		{
			fieldname: "include_drafts",
			label: __("Include cards held by a draft posting"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
