// Report: "Diesel Invoice Reconciliation" (P1-1) — read-only; filters
frappe.query_reports["Diesel Invoice Reconciliation"] = {
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
			fieldname: "suppliers",
			label: __("Diesel suppliers (one delivery stream)"),
			fieldtype: "MultiSelectList",
			get_data: (txt) =>
				frappe.xcall(
					"card.diesel_reconciliation.diesel_supplier_options",
					{ txt, company: frappe.query_report.get_filter_value("company") },
					"GET",
				),
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
			fieldname: "date_window_days",
			label: __("Invoice date window (days)"),
			fieldtype: "Int",
			default: 3,
		},
		{
			fieldname: "max_delivery_litres",
			label: __("Delivery charge up to (litres)"),
			fieldtype: "Float",
			default: 60,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "status" && data) {
			const color = data.exception ? "red" : "green";
			value = `<span style="color: var(--${color}-600)">${value}</span>`;
		}
		return value;
	},
};
