// Report: "Asset Mapping Review" (maintenance plan M1) — read-only; filters
frappe.query_reports["Asset Mapping Review"] = {
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
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: [
				{ value: "Needs attention", label: __("Needs a decision only") },
				{ value: "All", label: __("All Assets") },
			],
			default: "Needs attention",
		},
	],
};
