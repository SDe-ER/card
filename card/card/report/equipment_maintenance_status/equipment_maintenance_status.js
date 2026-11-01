// FR-100: "Equipment Maintenance Status" — read-only
frappe.query_reports["Equipment Maintenance Status"] = {
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
			fieldname: "maintenance_status",
			label: __("Maintenance status"),
			fieldtype: "Select",
			options: ["", "No Service Record", "Within Limit", "Due Soon", "Service Due"],
		},
		{ fieldname: "only_attention", label: __("Only due and due soon"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "maintenance_status" && data && data.indicator) {
			value = `<span class="indicator-pill ${data.indicator}">${value}</span>`;
		}
		return value;
	},
};
