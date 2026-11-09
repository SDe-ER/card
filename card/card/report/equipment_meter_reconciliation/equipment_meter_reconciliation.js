// Report: "Equipment Meter Reconciliation" (maintenance plan R1) — read-only; filters
frappe.query_reports["Equipment Meter Reconciliation"] = {
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
			fieldname: "equipment",
			label: __("Equipment"),
			fieldtype: "Link",
			options: "Card Equipment",
		},
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: [
				{ value: "Summary", label: __("One row per equipment") },
				{ value: "Readings", label: __("Every reading") },
			],
			default: "Summary",
		},
		{
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: [
				{ value: "Needs attention", label: __("Needs review only") },
				{ value: "All", label: __("All equipment") },
			],
			default: "Needs attention",
			depends_on: 'eval:doc.view!="Readings"',
		},
		{
			fieldname: "tolerance_pct",
			label: __("Allowed difference %"),
			fieldtype: "Float",
			default: 10,
		},
	],
};
