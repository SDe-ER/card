// Copyright (c) 2026, Shams Dubai Contracting Est. (SDCE) and contributors
// For license information, please see LICENSE
frappe.query_reports["Equipment Diesel Analysis"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
			get_query: () => ({ query: "card.api.card_companies_query" }),
		},
		{
			fieldname: "from_month",
			label: __("From month"),
			fieldtype: "Select",
			options: "01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
			default: String(new Date().getMonth() + 1).padStart(2, "0"),
			reqd: 1,
		},
		{
			fieldname: "from_year",
			label: __("From year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			reqd: 1,
		},
		{
			fieldname: "to_month",
			label: __("To month"),
			fieldtype: "Select",
			options: "01\n02\n03\n04\n05\n06\n07\n08\n09\n10\n11\n12",
			default: String(new Date().getMonth() + 1).padStart(2, "0"),
		},
		{
			fieldname: "to_year",
			label: __("To year"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
		},
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
