// Report: "Equipment Location History" — read-only; where each equipment was, per period
frappe.query_reports["Equipment Location History"] = {
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
			fieldname: "equipment",
			label: __("Equipment"),
			fieldtype: "Link",
			options: "Card Equipment",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("company") },
			}),
		},
	],
};
