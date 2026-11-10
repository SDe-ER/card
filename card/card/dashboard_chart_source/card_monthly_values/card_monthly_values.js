// Copyright (c) 2026, SDCE and contributors
// For license information, please see LICENSE

frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Card Monthly Values"] = {
	method: "card.card.dashboard_chart_source.card_monthly_values.card_monthly_values.get",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
		},
		{
			fieldname: "include_drafts",
			label: __("Include draft cards"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
