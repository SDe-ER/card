// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
frappe.query_reports["Equipment Expenses Without Equipment"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Autocomplete",
			get_query: () => ({ query: "card.api.card_company_options" }),
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "to_date",
			label: __("To date"),
			fieldtype: "Date",
			default: frappe.datetime.year_end(),
		},
	],
};
