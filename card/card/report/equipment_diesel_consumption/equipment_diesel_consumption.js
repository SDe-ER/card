// Report: "Equipment Diesel Consumption" — filters
frappe.query_reports["Equipment Diesel Consumption"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{ fieldname: "from_date", label: __("From date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To date"), fieldtype: "Date" },
		{ fieldname: "project", label: __("Project"), fieldtype: "Link", options: "Project" },
		{
			fieldname: "equipment",
			label: __("Equipment"),
			fieldtype: "Link",
			options: "Card Equipment",
		},
	],
};
