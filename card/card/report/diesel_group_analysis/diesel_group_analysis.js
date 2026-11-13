// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
frappe.query_reports["Diesel Group Analysis"] = {
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
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "group",
			label: __("Operating group"),
			fieldtype: "Link",
			options: "Equipment Operating Group",
			get_query: () => ({
				filters: {
					company: frappe.query_report.get_filter_value("company"),
					enabled: 1,
				},
			}),
		},
	],
};
