// Report: "Transport Accounting Review" (P1-2) — read-only; filters
frappe.query_reports["Transport Accounting Review"] = {
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
			fieldname: "show",
			label: __("Show"),
			fieldtype: "Select",
			options: [
				{ value: "Needs attention", label: __("Needs attention") },
				{ value: "All", label: __("All transports") },
			],
			default: "Needs attention",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "review" && data && data.attention) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
