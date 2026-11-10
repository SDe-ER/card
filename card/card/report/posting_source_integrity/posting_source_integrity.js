// Report: "Posting Source Integrity" (FR-136, R-25) — read-only; filters
frappe.query_reports["Posting Source Integrity"] = {
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
				{ value: "Problems", label: __("Problems only") },
				{ value: "All", label: __("All posted sources") },
			],
			default: "Problems",
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "check" && data && data.problem) {
			value = `<span style="color: var(--red-600)">${value}</span>`;
		}
		return value;
	},
};
